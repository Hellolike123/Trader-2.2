## ADDED Requirements

### Requirement: trader --output json 输出完整 report dict
`final_report.py --output json` MUST 输出 `build_report()` 返回的 report dict 的完整 JSON 序列化，包含所有 63 个字段，外加补全的缺失字段。

#### Scenario: 正常输出完整 JSON
- **WHEN** 执行 `python3 final_report.py --target 688248 --output json`
- **THEN** 输出有效的 JSON 对象，包含 report dict 的全部字段，以及 `one_liner`、`t0_ref`、`macd_status` 补全字段

#### Scenario: JSON 包含 fusion 详情
- **WHEN** fusion 层有决策结果
- **THEN** JSON 中 `fusion` 字段包含 action、confidence、weighted_score、signals_detail

#### Scenario: JSON 包含阶段定位详情
- **WHEN** 四阶段定位完成
- **THEN** JSON 中包含 major_stage、major_reason、short_term_momentum、momentum_reason、stage_action、stage_label、confidence、max_position_pct

### Requirement: trader JSON 补全缺失字段
report dict 中需要补全以下字段，这些字段当前在 render_markdown() 中动态生成但未存储。

#### Scenario: one_liner 字段
- **WHEN** build_report() 返回
- **THEN** report dict 包含 `one_liner` 字段，值为 `one_sentence()` 函数的输出

#### Scenario: t0_ref 字段
- **WHEN** build_report() 返回
- **THEN** report dict 包含 `t0_ref` 字段，值为 `{"low_buy": float, "high_sell": float, "stop": float}`

#### Scenario: macd_status 字段
- **WHEN** momentum_strategy() 有结果
- **THEN** report dict 包含 `macd_status` 字段，值为 "偏多"/"偏空"/"中性"
