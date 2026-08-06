# Trader 3.0 输出精简改造方案（修订版）

> 创建日期：2026-06-25 | 改造范围：`trader` 技能单票分析报告
> 目标：生产输出从 ~70 行 → ~28 行，手机一屏可读

---

## 最终输出模板（目标效果）

```
分析报告 — 南网科技（688248）

现价：65.31元（+6.79%）｜MA20 61.34｜MA250 --
ATR 3.69（6.1%）波幅偏高

📊 蓄势期 + 走强 → 低吸试盘
   融合｜⚪ 半仓试 (多方主导但有分歧)（加权分 0.00，置信度 30%，信号冲突建议等待）
   EXPMA 偏多排列（6/10）｜共振 无共振（分歧）（4/10）

📍 买卖点
  59.74 止损
  61.20 ← 试探买 5%（缩量整理）确认：放量站上 67.76
  65.31 当前
  62.66 → 卖 25%（1R 保本）→ 67.49 → 卖 25%（阻力位）
  R:R = 0.39 ⚠️ 性价比不足 ｜ 风险 -8.4% ｜ 收益 +3.3%

📌 持仓（成本 57.50，盈 +13.6%）
  部分止盈，留底仓等突破
  反弹到 57.50 → 减 50%（保本）
  跌破 59.74 → 清仓

🔍 筹码 ｜ 当前价以下 87%

📊 股性回测
  买入信号 1次，0胜1负，胜率 0%，平均 -0.88%
  ⚠️ 样本不足，仅供参考

✅ 亮点：仍站防守位 61.20 上方 ｜ 缠论结构偏多
⚠️ 风险：突破 67.76 前不宜追高

回复 1 入池（当前池 5/10）
```

约 28 行，无 `**` 粗体、无表格、无 `#` 标题，符合微信输出红线。

---

## 原输出问题诊断

当前 `run_analysis.py:render_markdown` 生产输出 ~70 行，问题：

1. **冗余段落**："💡 为什么这么操作"与融合 verbatim 重复，"🎯 信号判断"也与融合层重复
2. **冗长列表**：筹码逐行对比（支撑/阻力分别变化率）、Fibonacci 扩展目标位、EXPMA 详细值
3. **板块冲突**：主力行为评分（6/15）和历史回测混在同一个区域
4. **信息密度低**：大量描述性文案 vs 核心价位/分数

---

## 改动对照表

| 原段落 | 处理后 | 说明 |
|--------|--------|------|
| 标题 + 现价 + MA5/MA10/MA20/MA30 | 标题 + 现价 + MA20 + **MA250** | 保留 MA20，新增 MA250 |
| ATR 行 | 保留 | 不动 |
| 量能显示（量比、换手、20日高低距离） | **砍掉** | 次要信息，手机端不需要 |
| 相对大盘强度行 | **砍掉** | 个股分析场景，大盘强度非必需 |
| 数据完整性警告 | **砍掉** | 冗余，数据不足时价位会显示 -- |
| 📊 阶段 + 动能 → 动作 | **保留**，合并 EXPMA 和共振 | 1 行 → EXPMA 和共振各缩为 1 行 |
| 融合层 verbatim | **保留**，放在阶段行下方 | 核心决策信息 |
| "💡 为什么这么操作" | **砍掉** | 描述性文案与融合层重复 |
| 📍 买卖点 | **保留+精简** | 确认价并到试探买行，卖出位用 `→` 串联，新增 R:R |
| EXPMA 详细状态（~5行） | **保留**，缩为 1 行 | 趋势判断有增量信息 |
| 多时间窗共振（~3行） | **保留**，缩为 1 行 | 周/日/60min 共振有价值 |
| 持仓建议 | 条件显示（仅 has_position=true） | 不动 |
| 🔍 主力筹码（~15行筹码峰+搬家详表） | **精华化**：1 行（当前价以下占比） | 异常时追加 ⚠️ |
| 主力行为评分（~6行） | **砍掉** | 裸分数无明确操作含义 |
| 📊 五层打分 + 缠论买卖点（~8行） | **砍掉** | 已在融合层展示结论 |
| 📊 股性与历史回测 | **保留+独立**，单独标题 | 历史统计是重要参考 |
| "🎯 信号判断"（偏多/警惕列表） | **砍掉** | 与融合 verbatim 重复 |
| ✅ 亮点 + ⚠️ 风险 | **保留+条件化** | 不会空行 |
| 当前池 X/10 | 保留为 footer | 不动 |

---

## 具体改动清单

### 改动文件：`01-功能包-packages/trader/scripts/run_analysis.py`

> ⚠️ 注意：`new_render.py` 是平行未使用文件，**不改**。只改生产入口 `run_analysis.py` 的 `render_markdown` 函数（约 1188-1700 行）。

#### 1. 数据层：`report` dict 新增两个字段

**位置**：`build_report()` 函数中 `report` 字典闭括号前（约第 797 行）

**改动**：
```python
# 新增 ma250（已在第 669 行计算，直接挂上）
"ma_raw": {
    "ma5": levels["ma_values"].get("ma5"),
    "ma10": levels["ma_values"].get("ma10"),
    "ma20": levels["ma_values"].get("ma20"),
    "ma30": levels["ma_values"].get("ma30"),
    "ma250": ma250,
},

# 新增 volume_ratio（渲染层需要，当前为 None）
"volume_ratio": _compute_volume_ratio_from_bars(bars),
```

**新增辅助函数**（放在 `build_report` 上方或 `run_analysis.py` 末尾）：
```python
def _compute_volume_ratio_from_bars(bars: list) -> float:
    """从日线 bars 计算当日量比（今日量 / 近5日均量）。"""
    if not bars or len(bars) < 6:
        return 0.0
    volumes = [float(b.get("volume") or 0) for b in bars]
    today_vol = volumes[-1]
    avg_5 = sum(volumes[-6:-1]) / 5
    return round(today_vol / avg_5, 2) if avg_5 > 0 else 0.0
```

#### 2. 渲染层：`render_markdown` 函数重写

从第 1188 行 `def render_markdown(r: dict) -> str:` 开始，到函数结束，全文替换为以下结构。

**核心保留字段**（不改动数据层，只调整输出顺序）：
```python
# 基础信息
name, symbol, current, change_pct
ma_raw.ma20, ma_raw.ma250
atr14, atr_ratio, atr_level

# 阶段与融合
major_stage, short_term_momentum, stage_action
fusion.fusion_verbatim
expma_status.total_score, expma_status.trend_label
resonance.total_score, resonance.resonance_label

# 价位
support, stop, confirm, resistance
exit_plan.exit_plan (list of {price, ratio, reason})

# 持仓
has_position, cost_price, pnl_pct, pnl_text

# 筹码
chip_peaks, chip_current_pct, chip_migration

# 回测
win_rate_data (从 report dict 读取)

# 亮点风险
当前价 vs 支撑位关系
缠论方向
突破确认判断
筹码搬家警告
```

**输出结构**（10 段）：

```
段 1: 标题 + 现价 + MA + ATR（3-4 行）
段 2: 阶段 + 融合 + EXPMA/共振（3 行）
段 3: 买卖点（7-9 行）
段 4: 持仓建议（条件显示，3-5 行）
段 5: 筹码（1-2 行）
段 6: 股性回测（3-4 行，条件显示）
段 7: 亮点 + 风险（2-4 行）
段 8: Footer（1 行）
```

#### 3. 买卖点格式规范

```
  {stop:.2f} 止损
  {support:.2f} ← 试探买 {position_cap}%（{buy_label}）确认：放量站上 {confirm:.2f}
  {current:.2f} 当前
  {price1:.2f} → 卖 {ratio1:.0%}（{reason1}）→ {price2:.2f} → 卖 {ratio2:.0%}（{reason2}）
  R:R = {rr:.2f} {emoji} {verdict} ｜ 风险 {risk_pct:.1f}% ｜ 收益 {reward_pct:.1f}%
```

- 确认价并到试探买行（原占 2 行 → 1 行）
- 所有卖出位用 `→` 串联在一行（原占 N 行 → 1 行）
- R:R = 收益/风险，>= 1.5 显示 ✅，< 1.5 显示 ⚠️
- 风险 = (current - stop) / current，收益 = (resistance - current) / current
- 风险用 `-` 号格式，收益用 `+` 号格式

#### 4. 筹码格式规范

```
🔍 筹码 ｜ 当前价以下 {current_pct:.0f}%
```

仅当 `chip_migration.warning_level in ("warning", "critical")` 时追加：
```
  ⚠️ {warning_text}
```

原筹码峰逐行对比表（~12 行）全部砍掉，只保留当前价以下占比。

#### 5. 股性回测格式规范

```
📊 股性回测
  买入信号 {count}次，{wins}胜{count-wins}负，胜率 {win_rate}%，平均 {avg_pnl:+.2f}%
  ⚠️ 样本不足，仅供参考          （仅当 sample_warning=True 时显示）
```

不混入主力行为评分（裸分数无操作含义）。

#### 6. 亮点/风险格式规范

- 亮点：仍站防守位上方 → `仍站防守位 {support:.2f} 上方`；缠论结构偏多 → `缠论结构偏多`；用 ` ｜ ` 连接
- 风险：突破确认位前 → `突破 {confirm:.2f} 前不宜追高`；筹码搬家出货 → 单独一行追加

---

## 验证方式

```bash
cd 01-功能包-packages/trader
python scripts/final_report.py --target 688248
```

检查点：
- [ ] 报告总行数 ≤ 35 行
- [ ] 无 `**` 粗体和表格（符合微信红线）
- [ ] MA250 出现且年线下方有 ⚠️ 警告
- [ ] R:R 行出现且数值合理（风险用 - 号，收益用 + 号）
- [ ] 确认价并到试探买行（同一行）
- [ ] 卖出位用 `→` 串联在一行
- [ ] 无持仓时不显示 📌 段
- [ ] 筹码只有一行（当前价以下占比），异常时追加 ⚠️
- [ ] 股性回测单独成段，不带主力行为评分
- [ ] 无"为什么这么操作"、"信号判断"段落
- [ ] `--output json` 输出不受影响（只改渲染层）

---

## 不改动的内容

- `run_analysis.py` 中 `build_report` 的数据计算逻辑
- `run_analysis.py` 中 `build_signal`、`_get_cost_from_signals` 等辅助函数
- `final_report.py` 的入口和参数解析
- `new_render.py`（未使用的平行文件，后续清理）
- `__main__.py` 的 argparse 入口
