# 250日线趋势过滤 — 规格

> 来源：commit 676ae0e
> 状态：已实现，本文档为补写

---

## 功能概述

当股价位于 250 日均线（年线）下方时，直接返回"暂不碰"，跳过所有后续分析（融合层、Wyckoff、缠论等）。这是一个硬门控（hard gate）。

---

## 触发条件

```
if current_price < MA250:
    → 一票否决，返回 "暂不碰"
    → 跳过 status_layers() 全部分析
```

- 需要 `TREND_FILTER_ENABLED = True`（config.py）
- 需要 bars 数据 >= 250 根（不足时不触发，放行）
- 检查点：`status_layers()` 入口处，优先级高于所有其他逻辑

---

## 实现位置

| 文件 | 位置 | 作用 |
|------|------|------|
| `decision_core.py` | `_ma250_check()` (line ~148) | 一票否决判定 |
| `decision_core.py` | `status_layers()` 入口 (line ~277) | 调用 _ma250_check |
| `config.py` | `TREND_MA_LONG = 250` | 长期均线周期 |
| `config.py` | `LOOKBACK_DAYS = 300` | K线回溯天数（需 > 250） |
| `config.py` | `TREND_MA_LOOKBACK = 300` | 均线计算所需最小数据量 |
| `light_data.py` | 所有 fetch 函数 `days=300` | 数据拉取默认天数 |

---

## 返回值

一票否决时返回的 dict：

```python
{
    "base_status": "暂不碰",
    "theory_status": "暂不碰",
    "status": "暂不碰",
    "ma250_blocked": True,
    "ma250": <250日均线值, round 2位>,
    # 其他字段为默认空值
}
```

---

## 与其他功能的交互

- **融合层**：年线下方直接跳过，不调用 `merge_decisions()`
- **Wyckoff / 缠论 / 动量**：年线下方不执行任何分析
- **ATR 移动止损**：年线过滤在止损计算之前，被否决的股票不会走到止损逻辑
- **T0 交易**：T0 的 `LOOKBACK_DAYS = 30`（独立配置），不触发 250 日线过滤

---

## 历史演进

| 阶段 | TREND_MA_LONG | 说明 |
|------|---------------|------|
| 原始设计 | 900 | phase2 审计发现需要 3.5 年数据，实际只拉 30 天 |
| C-13 修复 | 60 | 临时修复，60日均线过于灵敏 |
| 当前实现 | 250 | 年线，经典技术分析水平，配合 LOOKBACK_DAYS=300 |
