# Review JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `quote.current_price` | float | 收盘价 | 14.29 |
| `cost` | float | 持仓成本 | 13.50 |
| `pnl_pct` | float | 浮盈浮亏 % | 5.85 |
| `conclusion_text` | str | 复盘结论 | "弱修复观察，还不能按反转处理" |
| `one_liner_text` | str | 一句话总结 | "防守观察，等确认" |

## 五层评分

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `theory.scores.structure` | int | 结构分 0-100 | 65 |
| `theory.scores.volume_price` | int | 量价分 0-100 | 45 |
| `theory.scores.chip` | int | 筹码分 0-100 | 50 |
| `theory.scores.momentum` | int | 动能分 0-100 | 50 |
| `theory.scores.fusion` | int | 融合分 0-100 | 60 |

## 信号字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `theory.supports` | list | 看多信号 | ["站回VWAP", "MACD绿柱缩短"] |
| `theory.blocks` | list | 看空信号 | ["跌破MA5"] |

## 价位字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `levels.main_support` | float | 支撑位 | 13.50 |
| `levels.confirm_price` | float | 确认位 | 14.80 |
| `levels.hard_stop` | float | 止损位 | 13.20 |

## 大单字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `big_order.direction_summary` | str | 大单方向 | 买方更强/卖方更强 |
| `big_order.total_hands` | float | 总手数 | 15000 |
| `big_order.events` | list | 大单事件 | [{"time": "14:35", "side": "主动买入", "hands": 4000}] |

## 筹码字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `chip_distribution.poc` | float | 控制节点价格 | 14.00 |
| `chip_distribution.va_high` | float | 价值区上沿 | 14.50 |
| `chip_distribution.va_low` | float | 价值区下沿 | 13.50 |

## 主力行为字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `main_force.stage` | str | 主力阶段 | accumulation/markup/unknown |
| `main_force.confidence` | float | 置信度 | 0.6 |
| `main_force.cum_flow_5d_wan` | float | 5 日净流入（万元） | 3200 |
