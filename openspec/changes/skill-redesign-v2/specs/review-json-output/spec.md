## ADDED Requirements

### Requirement: review --output json 输出完整 review dict
`review_render.py` 或 `review_single.py` 的 JSON 输出 MUST 包含 build_review() 返回的核心字段。

#### Scenario: 正常输出 JSON
- **WHEN** 执行 review script --target 688248 --output json
- **THEN** 输出有效 JSON，包含 quote、cost、pnl_pct、conclusion_text、one_liner_text、theory（含 scores、supports、blocks）、levels、big_order、macd_params、atr、chip_distribution、summary

#### Scenario: 五层评分完整
- **WHEN** theory_verdicts() 计算完成
- **THEN** theory.scores 包含 structure、volume、chip、momentum、total

#### Scenario: 信号判断完整
- **WHEN** theory_verdicts() 计算完成
- **THEN** theory.supports 为偏多信号列表，theory.blocks 为警惕信号列表

### Requirement: review JSON 包含结论和策略
复盘结论和明日策略 MUST 包含在 JSON 输出中。

#### Scenario: 有结论文字
- **WHEN** _compute_display() 执行完成
- **THEN** JSON 包含 conclusion_text、model_summary_text、one_liner_text

#### Scenario: 有持仓数据
- **WHEN** 用户提供了成本价
- **THEN** JSON 包含 cost 和 pnl_pct
