# T0 JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `current_price` | float | 当前价格 | 14.29 |
| `today_action` | str | 今日操作 | 低吸优先/高抛优先/等待 |
| `data_status` | str | 数据状态 | full/partial/degraded |
| `name` | str | 股票名称 | 南网科技 |
| `symbol` | str | 股票代码 | 688248.SH |

## 低吸字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `buy.status` | str | 低吸状态 | 已触发/观察中/未进入候选区/被阻断/数据不足 |
| `buy.observation_price` | float | 低吸观察价 | 13.50 |
| `buy.execution_price` | float | 低吸执行价 | 13.40 |
| `buy.acceptable_price` | float | 最高可接受价 | 13.80 |
| `buy.invalid_price` | float | 低吸止损价 | 13.20 |
| `buy.matched_count` | int | 触发信号数 | 3 |
| `buy.reasons` | list | 触发原因 | ["5m不再创新低", "MACD绿柱缩短"] |
| `buy.blocked_reasons` | list | 阻断原因 | ["放量跌破主支撑"] |

## 高抛字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `sell.status` | str | 高抛状态 | 已触发/观察中/未进入候选区/被阻断 |
| `sell.observation_price` | float | 高抛观察价 | 14.80 |
| `sell.execution_price` | float | 高抛执行价 | 14.90 |
| `sell.acceptable_price` | float | 最低可接受价 | 14.50 |
| `sell.invalid_price` | float | 高抛失效价 | 15.10 |

## 辅助字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `volume_ratio` | float | 量比 | 1.5 |
| `vwap` | float | VWAP | 14.25 |
| `atr_info.atr14` | float | ATR | 0.35 |
| `atr_info.atr_ratio` | float | ATR 占比 | 0.025 |
| `atr_info.level` | str | 波动率级别 | 波动正常 |
| `big_orders` | list | 大单异动 | [{"time": "10:15", "side": "主动买入", "hands": 3000}] |
