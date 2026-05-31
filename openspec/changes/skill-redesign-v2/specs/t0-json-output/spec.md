## ADDED Requirements

### Requirement: t0 --output json 输出完整 plan dict
`t0_core.py` 或 `t0_run.py` 的 JSON 输出 MUST 包含 build_plan() 返回的核心字段。

#### Scenario: 正常输出 JSON
- **WHEN** 执行 t0 script --target 688248 --once --output json
- **THEN** 输出有效 JSON，包含 current_price、today_action、buy（status/observation_price/trigger_price/invalid_price）、sell（status/observation_price/trigger_price）、volume_ratio、vwap、atr_info、data_status

#### Scenario: buy/sell 模型字段完整
- **WHEN** 价格点模型计算完成
- **THEN** buy 和 sell 各包含 status、observation_price、trigger_price、invalid_price、confidence、reasons

### Requirement: t0 JSON 包含大单事件
盘中大单检测结果 MUST 包含在 JSON 输出中。

#### Scenario: 有大单事件
- **WHEN** 检测到大单
- **THEN** JSON 中 big_orders 列表非空，每条包含 time、direction、amount_wan

#### Scenario: 无大单事件
- **WHEN** 未检测到大单
- **THEN** JSON 中 big_orders 为空列表
