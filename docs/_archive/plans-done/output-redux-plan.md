# Trader 3.0 输出精简改造方案（方案B：数据层+渲染层）

> 创建日期：2026-06-25 | 改造范围：`trader` 技能单票分析报告

---

## 改造目标

现状：11 段报告，有效信息密度约 40%，手机上需要翻屏，交易员难以快速决策。

改造后：7 段报告，手机一屏，阅读路径清晰：环境 → 位置 → 价位 → 风险 → 决定。所有分析逻辑保留，砍掉重复表述和裸数据堆砌。

---

## 最终输出模板

```
分析报告 — {name}（{code}）
🏦 大盘{env_level}（{hmm_regime_cn}）｜{industry}板块{sector_strength}

现价 {price}（{change_pct}）｜MA20 {ma20}｜MA250 {ma250}{ma250_warning}
ATR {atr14}（{atr_ratio}%）{atr_level}

📊 位置：{major_stage} + {momentum} → {stage_action}（{stage_desc}）
   缠论：{chan_signal}｜威科夫：{wyk_signal}｜动能：{mom_signal}
   融合：{fusion_emoji} {fusion_ws} {fusion_action} ｜ 置信度 {fusion_conf}%{fusion_disclaimer}

📍 买卖点
  {stop} 止损
  {support} ← 试探买 {position_cap}%（{buy_label}）确认：放量站上 {confirm}
  {current} 当前{has_position_note}
  {exit_plan_rows}
  R:R = {rr_value} {rr_verdict} ｜ 风险 {risk_pct}% ｜ 收益 {reward_pct}%

📌 持仓（成本 {cost_price}，{pnl_text}）                         ← 仅 has_position=true 时显示
  {holding_action}

🔍 筹码｜{chip_one_liner}{chip_migration_alert}

✅ 亮点：{bullish_signals}
⚠️ 风险：{bearish_signals}

回复 1 入池（当前池 {pool_count}/10）
```

---

## 改造清单

### 一、数据层改动：`run_analysis.py`

#### 1.1 把 `ma250` 挂到 `report["ma_raw"]` 中

**位置**：第 753-758 行，`report["ma_raw"]` 定义处

**现状**：
```python
"ma_raw": {
    "ma5": levels["ma_values"].get("ma5"),
    "ma10": levels["ma_values"].get("ma10"),
    "ma20": levels["ma_values"].get("ma20"),
    "ma30": levels["ma_values"].get("ma30"),
},
```

**改为**：
```python
"ma_raw": {
    "ma5": levels["ma_values"].get("ma5"),
    "ma10": levels["ma_values"].get("ma10"),
    "ma20": levels["ma_values"].get("ma20"),
    "ma30": levels["ma_values"].get("ma30"),
    "ma250": ma250,   # 已在第669行计算，直接挂上
},
```

**说明**：`ma250` 在第 669 行已计算：`ma250 = sum(closes_250) / len(closes_250)`（None 时表示不足 250 天数据），只差没放入 report。

---

#### 1.2 把 `volume_ratio` 挂到 report 中

**问题**：`volume_ratio` 在 `new_render.py` 多处被读取（第 176、350 行），但 `build_report()` 的返回字典中从未设置此字段，导致渲染器始终拿到 0。

**位置**：第 797 行（`report` 字典闭括号 `}` 前），或放在 `"atr_cap"` 所在段旁边

**改为**：在 report 字典中新增一行：
```python
"volume_ratio": _compute_volume_ratio_from_bars(bars),
```

**新增辅助函数**（放在 `build_report` 函数上方或 `run_analysis.py` 末尾）：
```python
def _compute_volume_ratio_from_bars(bars: list[dict[str, Any]]) -> float:
    """从日线 bars 计算当日量比（今日量 / 近5日均量）。"""
    if not bars or len(bars) < 6:
        return 0.0
    volumes = [float(b.get("volume") or 0) for b in bars]
    today_vol = volumes[-1]
    avg_5 = sum(volumes[-6:-1]) / 5  # 不含今日
    return round(today_vol / avg_5, 2) if avg_5 > 0 else 0.0
```

---

#### 1.3 大盘环境的中文 HMM 标签

**问题**：`report["market_env"]` 已有 `hmm_regime_en`（`bull`/`bear`/`range`），但渲染时需要中文。

**方案**：在渲染层做映射（无需改数据层）：
```python
HMM_REGIME_CN = {"bull": "牛市", "bear": "熊市", "range": "震荡市"}
```

---

#### 1.4 板块数据采集（可选，本期不强制）

**现状**：`fetch_quote` 不返回板块/行业信息。腾讯行情 API 的原始返回中可能有行业字段（field[13] 左右），但当前代码未解析。

**方案**：本期不做板块采集。报告中该行降级为只显示大盘，砍掉板块部分：
```
🏦 大盘偏弱（熊市）
```
板块数据作为后续迭代 todo。

**替代方案**：东方财富 API 有现成接口 `http://push2.eastmoney.com/api/qt/stock/get`，可直接返回行业名称。如要加入，新增一个 `_fetch_sector()` 函数，调用该接口取 `industry` 字段并写入 `report["sector"]`。

---

### 二、渲染层改动：`new_render.py`

整个 `render_markdown` 函数重写为 7 段结构。以下按函数体从上到下说明。

#### 2.1 删掉的旧代码

以下段落整体删除：
- `💡 为什么这么操作` 段（约第 198-218 行）：理由合并到 `📊 位置` 段
- `🎯 信号判断` 段（约第 342-363 行）：信号分解已合并到 `📊 位置` 段
- `📊 五层打分` 独立段（约第 314-326 行）：裸分数对交易决策无增量信息，保留在 JSON 中

#### 2.2 用 7 段替换整个函数体（从第 113 行 `render_markdown` 开始）

完整的替换目标代码见下文。保留 `_load_historical_win_rate` 和 `_get_buy_label` 不动的引用。

---

### 三、完整替换代码

以下是 `new_render.py` 中 `render_markdown` 函数的完整新版：

```python
def render_markdown(r: dict) -> str:
    # ── 数据提取 ──────────────────────────────────────────
    ma = r.get("ma") or {}
    ma_raw = r.get("ma_raw") or ma
    display_code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    name = str(r.get("name", ""))

    atr14 = float(r.get("atr14", 0) or 0)
    atr_ratio = float(r.get("atr_ratio", 0) or 0)
    atr_level = str(r.get("atr_level") or "")

    current_price = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    stop = float(r.get("stop") or 0)
    support = float(r.get("support") or 0)
    confirm = float(r.get("confirm") or 0)
    resistance_val = float(r.get("resistance") or 0)
    position_cap = int(r.get("position_cap") or 10)

    major_stage = str(r.get("major_stage") or "")
    momentum = str(r.get("short_term_momentum") or "")
    stage_action_map = {"蓄势": "低吸高抛", "主升": "持股待涨", "派发": "逢高减仓", "衰退": "不碰"}
    stage_action_text = stage_action_map.get(major_stage, major_stage)

    stage_desc_map = {
        "蓄势": "区间震荡，低吸高抛",
        "主升": "趋势向上，持股待涨",
        "派发": "高位震荡，逢高减仓",
        "衰退": "趋势向下，不碰",
    }
    stage_desc = stage_desc_map.get(major_stage, "")

    # ── 大盘环境 ──────────────────────────────────────────
    market_env = r.get("market_env") or {}
    env_level = str(market_env.get("level") or "未知")
    hmm_regime_en = str(market_env.get("hmm_regime_en") or "range")
    HMM_REGIME_CN = {"bull": "牛市", "bear": "熊市", "range": "震荡市"}
    hmm_cn = HMM_REGIME_CN.get(hmm_regime_en, hmm_regime_en)

    # ── MA 值 ─────────────────────────────────────────────
    def _ma_text(val) -> str:
        return f"{val:.2f}" if isinstance(val, (int, float)) else "--"

    ma20_text = _ma_text(ma_raw.get("ma20"))
    ma250_val = ma_raw.get("ma250")
    ma250_text = _ma_text(ma250_val) if ma250_val is not None else "--"
    ma250_warning = ""
    if ma250_val is not None and isinstance(ma250_val, (int, float)) and current_price < ma250_val:
        ma250_warning = " ⚠️年线下方，趋势偏空"

    # ── 融合层 ────────────────────────────────────────────
    fusion = r.get("fusion") or {}
    ws = float(fusion.get("weighted_score") or 0)
    conf = float(fusion.get("confidence") or 0)
    fusion_verbatim = str(fusion.get("fusion_verbatim") or "")
    # 零置信度守门：conf < 0.2 且 |ws| < 0.15 → 无信号
    _conf_pct = int(conf * 100)
    if conf < 0.2 and abs(ws) < 0.15:
        fusion_display = "⚪ 无明确信号，建议观望"
    elif fusion_verbatim and fusion_verbatim != "融合｜数据异常":
        fusion_display = fusion_verbatim.replace("融合｜", "")
    else:
        fusion_display = "⚪ 信号偏弱"

    # ── 缠论/威科夫/动能信号提取 ──────────────────────────
    signals = fusion.get("signals_detail") or {}
    chan_data = signals.get("chan") or {}
    wyk_data = signals.get("wyckoff") or {}
    mom_data = signals.get("momentum") or {}

    chan_reason = str(chan_data.get("reason", "")) if isinstance(chan_data, dict) else ""
    if not chan_reason:
        chan_reason = "无信号"

    wyk_desc = "无信号"
    wyk_full = r.get("wyckoff") or {}
    if isinstance(wyk_full, dict):
        wyk_desc = str(wyk_full.get("description") or "无信号")

    mom_reason_val = str(r.get("momentum_reason") or "")
    volume_ratio_val = float(r.get("volume_ratio") or 0)
    if not mom_reason_val and volume_ratio_val > 0:
        mom_reason_val = f"量比 {volume_ratio_val:.2f}"
    if not mom_reason_val:
        mom_reason_val = "中性"

    # ── 第1段：标题 + 环境 ─────────────────────────────────
    lines = [
        f"分析报告 — {name}（{display_code}）",
        f"🏦 大盘{env_level}（{hmm_cn}）",
    ]

    # ── 第2段：现价 + 均线 + ATR ────────────────────────────
    lines.append("")
    lines.append(f"现价 {current_price:.2f}（{change_pct:+.2f}%）｜MA20 {ma20_text}｜MA250 {ma250_text}{ma250_warning}")
    if atr14 > 0:
        lines.append(f"ATR {atr14:.2f}（{atr_ratio*100:.1f}%）{atr_level}")

    # ── 第3段：位置 + 信号 ─────────────────────────────────
    lines.append("")
    lines.append(f"📊 位置：{major_stage} + {momentum} → {stage_action_text}（{stage_desc}）")
    lines.append(f"   缠论：{chan_reason}｜威科夫：{wyk_desc}｜动能：{mom_reason_val}")
    lines.append(f"   融合：{fusion_display} ｜ 置信度 {_conf_pct}%")

    # ── 第4段：买卖点 + R:R ────────────────────────────────
    lines.append("")
    lines.append("📍 买卖点")
    if stop > 0:
        lines.append(f"  {stop:.2f} 止损")
    if support > 0:
        vol_ratio_for_label = float(r.get("volume_ratio") or 0)
        buy_label = _get_buy_label(change_pct, vol_ratio_for_label)
        lines.append(f"  {support:.2f} ← 试探买 {position_cap}%（{buy_label}）")
        if confirm > 0:
            lines.append(f"                  确认：放量站上 {confirm:.2f}")
        if stop > 0 and support > stop:
            invalid_price = support - (support - stop) * 0.3
            lines.append(f"                  失效：跌破 {invalid_price:.2f}")

    has_position = r.get("has_position", False)
    pos_note = ""
    if has_position:
        cost_price_val = float(r.get("cost_price") or 0)
        pnl_text_val = str(r.get("pnl_text") or "")
        if cost_price_val > 0:
            pos_note = f" ｜ 持仓成本 {cost_price_val:.2f}"

    if current_price > 0:
        lines.append(f"  {current_price:.2f} 当前{pos_note}")

    # 退出计划
    exit_plan = r.get("exit_plan") or {}
    exit_plan_items = exit_plan.get("exit_plan") or []
    for item in exit_plan_items:
        p = item.get("price")
        ratio = item.get("ratio", 0)
        reason = item.get("reason", "")
        if p is not None and p > 0:
            lines.append(f"  {p:.2f} → 卖 {ratio:.0%}（{reason}）")
    if resistance_val > 0:
        lines.append(f"  {resistance_val:.2f} 压力")

    # R:R 计算
    if stop > 0 and resistance_val > 0 and current_price > stop:
        risk_amt = current_price - stop
        reward_amt = resistance_val - current_price
        if risk_amt > 0:
            rr = round(reward_amt / risk_amt, 2)
            risk_pct = round(risk_amt / current_price * 100, 2)
            reward_pct = round(reward_amt / current_price * 100, 2)
            if rr >= 1.5:
                rr_line = f"  R:R = {rr} ✅ 可做 ｜ 风险 {risk_pct}% ｜ 收益 {reward_pct}%"
            else:
                rr_line = f"  R:R = {rr} ⚠️ 性价比不足 ｜ 风险 {risk_pct}% ｜ 收益 {reward_pct}%"
            lines.append(rr_line)

    # ── 第5段：持仓建议（仅持有仓位时显示）───────────────
    if has_position:
        cost_price_val = float(r.get("cost_price") or 0)
        pnl_pct_val = float(r.get("pnl_pct") or 0)
        pnl_text_val = str(r.get("pnl_text") or "")
        lines.append("")
        lines.append(f"📌 持仓（成本 {cost_price_val:.2f}，{pnl_text_val}）")

        if pnl_pct_val >= 0:
            if major_stage == "主升":
                holding_action = "持有，让利润跑"
            elif major_stage == "派发":
                holding_action = "减仓，锁定利润"
            else:
                holding_action = "部分止盈，留底仓等突破"
        else:
            if major_stage == "衰退":
                holding_action = "止损，认亏走人"
            elif major_stage == "主升":
                holding_action = "持有，主升期大概率会回来"
            else:
                holding_action = "持有，不加仓"

        lines.append(f"  {holding_action}")
        if cost_price_val > stop:
            lines.append(f"  反弹到 {cost_price_val:.2f} → 减 50%（保本）")
        if stop > 0:
            lines.append(f"  跌破 {stop:.2f} → 清仓")

    # ── 第6段：筹码（精简版）───────────────────────────
    chip_current_pct = r.get("chip_current_pct")
    chip_migration = r.get("chip_migration") or {}
    has_chip_history = chip_migration.get("has_history", False)
    migration_pct = chip_migration.get("migration_pct", 0)
    # 跳过同日对比的假变化
    if has_chip_history and migration_pct == 0 and not chip_migration.get("support_migration"):
        has_chip_history = False

    chip_peaks = r.get("chip_peaks") or []
    lines.append("")

    if chip_current_pct is not None:
        pct_above = 100 - chip_current_pct
        if pct_above > 60:
            chip_verdict = f"大部分筹码套牢于上方（{pct_above:.0f}%），承接薄弱"
        elif chip_current_pct > 45:
            chip_verdict = f"当前筹码分布均衡，{chip_current_pct:.0f}%在下方"
        else:
            chip_verdict = f"上方套牢{100-chip_current_pct:.0f}%，下方承接弱"
        lines.append(f"🔍 筹码｜{chip_verdict}")
    elif chip_peaks:
        lines.append(f"🔍 筹码｜有 {len(chip_peaks)} 个筹码峰，当前无明确方向")
    else:
        lines.append(f"🔍 筹码｜数据不足")

    # 筹码搬家仅在异常时展开
    if has_chip_history:
        warning_level = chip_migration.get("warning_level", "none")
        warning_text = str(chip_migration.get("warning_text", ""))
        if warning_level in ("warning", "critical") or "出货" in warning_text:
            lines.append(f"  ⚠️ {warning_text}")

    # ── 第7段：亮点 + 风险 ─────────────────────────────────
    lines.append("")
    bullish_parts = []
    bearish_parts = []

    # 亮点
    if current_price >= support:
        bullish_parts.append(f"仍站防守位 {support:.2f} 上方")
    else:
        bullish_parts.append(f"超跌区间，关注 {support:.2f} 附近企稳")

    chan_dir = chan_data.get("direction", 0) if isinstance(chan_data, dict) else 0
    if chan_dir > 0:
        bullish_parts.append("缠论结构偏多")

    if bullish_parts:
        lines.append(f"✅ 亮点：{' | '.join(bullish_parts)}")

    # 风险
    if ma250_val is not None and isinstance(ma250_val, (int, float)) and current_price < ma250_val:
        bearish_parts.append(f"年线下方趋势偏空")

    if chip_current_pct is not None and (100 - chip_current_pct) > 60:
        bearish_parts.append(f"上方 {100-chip_current_pct:.0f}% 筹码压力大")

    if confirm > current_price:
        bearish_parts.append(f"突破 {confirm:.2f} 前不宜追高")

    # 筹码搬家风险
    warning_text_val = str(chip_migration.get("warning_text", ""))
    if "出货" in warning_text_val or "搬家" in warning_text_val:
        bearish_parts.append("主力在出货")

    if bearish_parts:
        lines.append(f"⚠️ 风险：{' | '.join(bearish_parts)}")

    # ── Footer：入池提示 ───────────────────────────────────
    lines.append("")
    pool_count = _pool_count()
    if pool_count > 0:
        lines.append(f"回复 1 入池（当前池 {pool_count}/10）")
    else:
        lines.append("回复 1 入池")

    return "\n".join(lines)
```

---

## 改造对照表

| 原段落 | 处理后 |
|--------|--------|
| 标题+现价+MA5/MA10/MA20/MA30 | → 标题+环境+现价+MA20+**MA250**+ATR |
| 📊 阶段+动能 | → 合并到 📊 位置段 |
| 💡 为什么这么操作 | → **砍掉**（描述性文案合并到 📊 行的括号） |
| 📍 买卖点 | → **保留+增强**（+R:R、+确认位、+失效位） |
| 📌 持仓建议 | → 条件显示，**仅 has_position=true** |
| 🔍 主力筹码（6-8行） | → **精华化**：1-2行（异常时追加 ⚠️） |
| 📊 五层打分（独立段） | → **砍掉**（裸分数对下单无增量信息） |
| 🎯 信号判断（独立段） | → **砍掉**（信号结论已在 📊 位置段展示） |
| ✅ 亮点 + ⚠️ 风险 | → **保留+增强**（条件化生成，不会空荡荡） |
| 当前池 X/10 | → 保留为 footer |

**总段数：11 → 7，行数约减半。**

---

## 需要修改的文件

| 文件 | 改动 |
|------|------|
| `01-功能包-packages/trader/scripts/run_analysis.py` | ① `ma250` 挂到 `report["ma_raw"]`  ② `volume_ratio` 挂到 report |
| `01-功能包-packages/trader/scripts/new_render.py` | ① `_compute_volume_ratio_from_bars` 辅助函数（新增）  ② `render_markdown` 全文替换为 7 段版本 |

---

## 验证方式

改完后跑一只票的实报：

```bash
cd 01-功能包-packages/trader
python scripts/final_report.py --target 688248
```

检查点：
- [ ] 报告总行数 ≤ 30 行（原来约 50 行）
- [ ] MA250 出现且有年线下方警告
- [ ] R:R 行出现且数值正确
- [ ] 无持仓时不显示 📌 段
- [ ] 筹码搬家预警出现（如有历史数据）
- [ ] 融合置信度为 0% 时显示「无明确信号，建议观望」
- [ ] `--output json` 输出不受影响（只改了渲染层）

---

## 后续迭代

- [ ] 板块数据采集（东方财富 API）
- [ ] T0 卡片精简（`t0_core.py`）
- [ ] Review 复盘新增「明日作战卡」（`review_render.py`）
- [ ] 历史胜率样本不足时不显示裸数字
