# T0 JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `current_price` | float | 当前价格 | 14.29 |
| `current_change_pct` | float | 今日涨跌幅 % | 1.5 |
| `today_action` | str | 今日操作 | 低吸优先/高抛优先/等待，不主动操作/等待下一次触发 |
| `data_status` | str | 数据状态 | full/partial/degraded |
| `name` | str | 股票名称 | 南网科技 |
| `symbol` | str | 股票代码 | 688248.SH |
| `max_move` | str | 建议仓位 | 底仓的 10%-20%/底仓的 20%-30%/不动 |
| `position_score` | int | 多空位置评分 1-10 | 5 |
| `volume_score` | int | 量价评分 1-10 | 6 |
| `amplitude_pct` | float | 日内振幅 | 0.025 |
| `space_state` | str | 振幅状态 | too_small/normal/good |
| `vwap` | float | VWAP | 14.25 |
| `volume_ratio` | float | 量比 | 1.5 |
| `buy_display_status` | str | 低吸显示状态 | 到价关注/未触发/已错过/被阻断/数据不足（旧「可执行」已废弃，读入归一化为到价关注） |
| `sell_display_status` | str | 高抛显示状态 | 到价关注/未触发/已错过/被阻断/数据不足 |
| `atr_info.atr14` | float | ATR | 0.35 |
| `atr_info.atr_ratio` | float | ATR 占比 | 0.025 |
| `atr_info.level` | str | 波动率级别 | 波动正常/波幅偏高 |
| `ict_signal.summary` | str | ICT信号摘要 | ICT执行辅助未启用。 |
| `ict_signal.buy_confirmed` | bool | ICT买入确认 | true/false |
| `ict_signal.sell_confirmed` | bool | ICT卖出确认 | true/false |
| `wyckoff` | dict | 威科夫分析结果 | 包含BC/UTAD/SOW信号字段 |
| `exit_plan.exit_plan` | list | 分批止盈计划 | [{"price":14.80,"ratio":0.33,"reason":"阻力位"}] |
| `chip_migration` | dict | 筹码搬家 | {"migration_pct":5,"warning_level":"none","has_history":true} |

## 低吸字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `buy.status` | str | 低吸状态 | 已触发/观察中/未进入候选区/被阻断/数据不足/触发过期/买 10%/买 23%/熔断中 |
| `buy.observation_price` | float | 低吸观察价 | 13.50 |
| `buy.execution_price` | float | 低吸执行价 | 13.40 |
| `buy.acceptable_price` | float | 最高可接受价 | 13.80 |
| `buy.invalid_price` | float | 低吸止损价 | 13.20 |
| `buy.trigger_price` | float | 触发价 | 13.35 |
| `buy.trigger_time` | str | 触发时间 | 14:05 |
| `buy.matched_count` | int | 触发信号数 | 3 |
| `buy.reasons` | list | 触发原因 | ["5m不再创新低", "MACD绿柱缩短"] |
| `buy.blocked_reasons` | list | 阻断原因 | ["放量跌破主支撑"] |
| `buy.observation_valid` | bool | 观察价是否有效 | true/false |
| `buy.observation_reason` | str | 无效原因 | 盘中数据不足 |

## 高抛字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `sell.status` | str | 高抛状态 | 已触发/观察中/未进入候选区/被阻断/数据不足/触发过期 |
| `sell.observation_price` | float | 高抛观察价 | 14.80 |
| `sell.execution_price` | float | 高抛执行价 | 14.90 |
| `sell.acceptable_price` | float | 最低可接受价 | 14.50 |
| `sell.invalid_price` | float | 高抛失效价 | 15.10 |
| `sell.trigger_price` | float | 触发价 | 14.75 |
| `sell.trigger_time` | str | 触发时间 | 14:05 |
| `sell.matched_count` | int | 触发信号数 | 3 |
| `sell.reasons` | list | 触发原因 | ["MACD红柱缩短", "RSI高位拐头"] |
| `sell.blocked_reasons` | list | 阻断原因 | ["最近5m持续创新高"] |
| `sell.observation_valid` | bool | 观察价是否有效 | true/false |
| `sell.observation_reason` | str | 无效原因 | 高抛观察位距离现价太近 |
