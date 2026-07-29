# Pool + T0 输出优化方案

> **已归档（2026-07-29）**：路径过时。选股池实现在 `pool_cmds/`；T0 引擎在 `trader_shared/t0_*.py`。勿按本文 `final_pool.py` 行号施工。  
> 创建日期：2026-06-25 | 原改造范围：`final_pool.py` / `pool_briefing.py` / `t0_core.py`

---

## 一、Pool Rank（明日作战表）— 星空了但不知道为什么星

### 改动文件

`01-功能包-packages/trader/scripts/final_pool.py` → `render_rank()` 第 1089-1248 行

### 问题

现有输出：
```
🥇  ⭐⭐⭐  南网科技  低吸观察  54.29  波动正常(2.5%)
🥈  ⭐⭐⭐  中国铝业  等转强    12.80  波动偏大(3.1%)
🥉  ⭐⭐⭐  中航沈飞  防守观察  38.50  波动正常(1.8%)
```

三只都是 ⭐⭐⭐，看不出区别。排名依赖 `fusion_confidence` 池内分位（Top20% = ⭐⭐⭐），但交易员需要的是**选哪只的理由**。

### 改法

`⭐⭐⭐` 替换为**排第一的理由**（4-6 个字），从 JSON 数据中按优先级穷举：

| 条件 | 显示 |
|------|------|
| R:R > 2.0 且 ws > 0.2 | 「性价比最高」 |
| chan.direction > 0 且 ws > 0.2 | 「结构最强」 |
| 筹码当前价以下 > 45% | 「支撑最强」 |
| ws 池内最高 | 「信号最明确」 |
| momentum.direction > 0 且 ws > 0.1 | 「动能领先」 |
| ATR 池内最低且 major_stage=蓄势 | 「风险最小」 |
| 默认 | 「可关注」 |

修改 `render_rank()` 中第 1099-1123 行（星级计算段），新增一个 `edge_reason()` 函数：

```python
def edge_reason(item: dict, sorted_items: list) -> str:
    """返回这只票排第一的理由（4-6字），替代无区分度的 ⭐⭐⭐"""
    current = to_float(item.get("current")) or 0
    stop_val = to_float(item.get("stop")) or 0
    resistance = to_float(item.get("resistance")) or 0
    fusion = item.get("fusion") or {}
    ws = float(fusion.get("weighted_score") or 0)
    chip_pct = to_float(item.get("chip_current_pct")) or 0
    signals = fusion.get("signals_detail") or {}
    chan_dir = signals.get("chan", {}).get("direction", 0) if isinstance(signals.get("chan"), dict) else 0
    mom_dir = signals.get("momentum", {}).get("direction", 0) if isinstance(signals.get("momentum"), dict) else 0
    atr_ratio = to_float(item.get("atr_ratio")) or 0
    major_stage = str(item.get("major_stage") or "")

    # R:R > 2.0 且偏多
    if stop_val > 0 and resistance > 0 and current > stop_val:
        rr = (resistance - current) / (current - stop_val)
        if rr > 2.0 and ws > 0.2:
            return "性价比最高"

    # 结构偏多
    if chan_dir > 0 and ws > 0.2:
        return "结构最强"

    # 筹码支撑强
    if chip_pct > 45:
        return "支撑最强"

    # 信号最明确
    ws_list = [float((it.get("fusion") or {}).get("weighted_score") or 0) for it in sorted_items]
    if ws_list and ws == max(ws_list) and ws > 0.1:
        return "信号最明确"

    # 动能领先
    if mom_dir > 0 and ws > 0.1:
        return "动能领先"

    # 低风险（低波动蓄势）
    atr_list = [to_float(it.get("atr_ratio")) or 0 for it in sorted_items if to_float(it.get("atr_ratio")) or 0 > 0]
    if atr_list and atr_ratio == min(atr_list) and major_stage in ("蓄势", "蓄势偏强"):
        return "风险最小"

    return "可关注"
```

然后在 `render_rank()` 第 1123 行附近的 medal 变量处，把：

```python
medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f" {i+1}."
```

改为直接用 edge_reason 替代 stars 的部分展示。具体来说，第 1181 行的：

```python
lines.append(f"{medal}  {stars}  {name}  {rs}  {current:.2f}  {atr_text}")
```

改为：

```python
edge = edge_reason(item, sorted_items)
lines.append(f"{medal}  {name}  {edge}  {rs}  {current:.2f}  {atr_text}")
```

输出效果：
```
🥇  南网科技  结构最强  低吸观察  54.29  波动正常(2.5%)
🥈  中国铝业  动能领先  等转强    12.80  波动偏大(3.1%)
🥉  中航沈飞  可关注    防守观察  38.50  波动正常(1.8%)
```

交易员一眼看到三只的区别：南网结构好，铝业动能强，沈飞再看看。

---

## 二、Pool Briefing（选股日报）— 信号标签爆炸

### 改动文件

`01-功能包-packages/trader/scripts/pool_briefing.py` → `signal_tags()` 第 73-134 行

### 问题

每只票挂 6 个标签：
```
结构强 量价健康 筹码锁定(30%) MACD零轴上 均线多头 融合看多
```

10 只票 = 60 个标签，交易员直接跳过不看。

### 改法

`signal_tags()` 改为只返回**最重要的一个多头标签和一个空头标签**。优先级从高到低：

```python
def signal_tags(r: dict) -> tuple[str, str]:
    """返回 (top_buy_tag, top_risk_tag) 各一个，多余的砍掉。"""

    # ── 多头标签优先级（只取最高优先级的一个）──
    fusion = r.get("fusion") or {}
    action = str(fusion.get("action") or "")

    buy_tag = ""

    # 优先级 1：融合明确看多
    if action in ("买入", "加仓"):
        buy_tag = "融合看多"
    # 优先级 2：结构强
    elif isinstance(fusion.get("signals", {}).get("chan"), dict):
        chan_conf = fusion["signals"]["chan"].get("confidence", 0)
        if chan_conf >= 0.6:
            buy_tag = "结构强"
    # 优先级 3：筹码锁定
    elif (r.get("chip_current_pct") or 0) > 60:
        buy_tag = f"筹码锁定({int(r.get('chip_current_pct', 0))}%)"
    # 优先级 4：量价健康
    elif isinstance(r.get("wyckoff"), dict):
        desc = str(r["wyckoff"].get("description", ""))
        if "放量" in desc:
            buy_tag = "放量健康"
    # 优先级 5：MACD 零轴上
    elif isinstance(r.get("macd_status"), dict) and r["macd_status"].get("diff", 0) > 0:
        buy_tag = "MACD偏多"

    # ── 风险标签优先级（只取最高优先级的一个）──
    risk_tag = ""

    # 优先级 1：融合空仓
    if action in ("空仓/止损",):
        risk_tag = "融合空仓"
    # 优先级 2：结构弱
    elif isinstance(fusion.get("signals", {}).get("chan"), dict):
        chan_conf = fusion["signals"]["chan"].get("confidence", 0)
        if chan_conf < 0.3:
            risk_tag = "结构弱"
    # 优先级 3：量价弱
    elif isinstance(r.get("wyckoff"), dict):
        desc = str(r["wyckoff"].get("description", ""))
        if any(kw in desc for kw in ("缩量", "无量")):
            risk_tag = "量价弱"
    # 优先级 4：MACD 零轴下
    elif isinstance(r.get("macd_status"), dict):
        diff = r["macd_status"].get("diff", 0)
        if diff is not None and diff < 0:
            risk_tag = "MACD偏空"
    # 优先级 5：均线空头
    else:
        ma = r.get("ma") or {}
        ma20 = float(ma.get("20", 0) or 0)
        cur = r.get("current", 0)
        if ma20 > 0 and cur < ma20:
            risk_tag = "均线偏空"

    return (buy_tag, risk_tag)
```

输出效果：
```
南网科技  ✅ 结构强
中国铝业  ✅ 融合看多  ⚠️ 量价弱
中航沈飞  ⚠️ 均线偏空
```

每只票最多 2 个标签，交易员一扫就知道：南网结构好、铝业有人看多但量不行、沈飞位置不好。

---

## 三、Pool Plan（盘后作战计划）— 裸分数太难读

### 改动文件

`01-功能包-packages/trader/scripts/final_pool.py` → `render_plan()` 第 1482-1490 行（评分总览段）

### 问题

```
评分总览
  南网科技  总分62  缠25/45 威18/30 筹15/25  动量⬆  执行
  中国铝业  总分58  缠22/45 威20/30 筹12/25  动量→  执行
```

交易员需要 5 秒才能反应过来：25/45 是弱还是可以？45 分是满分吗？缠论拿了一半分这个信息对我下单有什么帮助？

### 改法

把裸分数换成**一句话状态摘要**。`trade_hint()` 已经在第 1494 行做了类似的事，但评分总览段应该保持一致：

```python
def score_summary(item: dict) -> str:
    """返回评分一句话总结（替换裸分数行）。"""
    chan = item.get("chanlun_score", 0)
    wyk = item.get("wyckoff_score", 0)
    chip = item.get("chip_score", 0)
    total = item.get("total_score", 0)
    
    # 找出最强和最弱维度
    dims = [("结构", chan, 45), ("量价", wyk, 30), ("筹码", chip, 25)]
    best_name, best_val, best_max = max(dims, key=lambda d: d[1]/d[2])
    worst_name, worst_val, worst_max = min(dims, key=lambda d: d[1]/d[2])
    
    best_pct = int(best_val / best_max * 100)
    worst_pct = int(worst_val / worst_max * 100)
    
    if total >= 70:
        return f"{best_name}最佳（{best_pct}%）总分{total}"
    elif total >= 55:
        return f"{best_name}尚可 {worst_name}偏弱 总分{total}"
    else:
        return f"全面偏弱（{worst_name}{worst_pct}%）总分{total}"
```

`render_plan()` 第 1485-1489 行替换为：

```python
lines.append("评分总览")
for item in sorted_items:
    summary = score_summary(item)
    momentum_tag = item.get("momentum_tag", "")
    lines.append(
        f"  {item.get('name')}  {summary}  动量{momentum_tag}  {item['status']}"
    )
```

输出效果：
```
评分总览
  南网科技  结构最佳（56%） 总量价偏弱 总分62  动量⬆  执行
  中国铝业  量价尚可 筹码偏弱 总分58  动量→  执行
```

交易员一眼看到：南网结构最好但量不行，铝业量还行但筹码差。不需要做算术。

---

## 附、T0 — 加一个「今天不做」

T0 其他逻辑不变，只在 `t0_core.py` 的 `build_plan` 或 `render_markdown` 开头加一个提前返回：

### 改动文件

`01-功能包-packages/t0/scripts/t0_core.py` → `render_markdown()` 函数开头（约第 234 行之后）

```python
def render_markdown(plan: dict[str, Any]) -> str:
    # 日子不好时直接拦一行
    amplitude_pct = float(plan.get("amplitude_pct") or 0)
    vol_ratio = float(plan.get("volume_ratio") or 0)
    if amplitude_pct > 0 and amplitude_pct < 1.5 and vol_ratio > 0 and vol_ratio < 0.7:
        return (
            f"😴 今天休息 — {plan.get('name','')}（{plan.get('symbol','')}）\n"
            f"振幅 {amplitude_pct:.1f}% 量比 {vol_ratio:.2f}，不值得做T\n"
        )
    
    # ... 后续原有逻辑不变
```

**前提**：需要在 `build_plan` 阶段计算 `amplitude_pct`（当日振幅）和 `volume_ratio`（量比）字段，或从已抓取的行情数据中获取。

---

## 改造清单总览

| 文件 | 改动 |
|------|------|
| `01-功能包-packages/trader/scripts/final_pool.py` | ① `edge_reason()` 新增函数  ② `render_rank()` 星级替换  ③ `score_summary()` 新增函数  ④ `render_plan()` 评分总览替换 |
| `01-功能包-packages/trader/scripts/pool_briefing.py` | ① `signal_tags()` 从 6 标签降为 2 标签 |
| `01-功能包-packages/t0/scripts/t0_core.py` | ① `render_markdown()` 开头加 skip_today 提前返回 |
