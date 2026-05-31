## ADDED Requirements

### Requirement: Fake breakdown uses correct comparison

`_fake_break` MUST 检查 `prev_close >= hard_stop` 而非 `prev_close >= support`。

#### Scenario: Genuine breakdown from support to below hard_stop
- **WHEN** current <= hard_stop，且近 3 日有收盘 >= hard_stop
- **THEN** SHALL 判定为"假跌破"（防守观察）

#### Scenario: Genuine breakdown with no recent close above hard_stop
- **WHEN** current <= hard_stop，且近 3 日所有收盘 < hard_stop
- **THEN** SHALL 判定为真跌破（风险回避）

### Requirement: Confidence score continuity

`_score_to_confidence` 在 score=40/41 边界 MUST 连续。

#### Scenario: Score 40 to 41 monotonicity
- **WHEN** score 从 40 变到 41
- **THEN** confidence SHALL 不下降（单调递增或持平）

### Requirement: Weight normalization after clamping

`_apply_main_force_weights()` 在 clamp 后 MUST 正确归一化。

#### Scenario: Markdown stage with low chan weight
- **WHEN** 初始 chan 权重 0.10，markdown 调整 -0.15
- **THEN** chan SHALL 被 clamp 到 0.0，其余权重 SHALL 按比例归一化到总和 1.0

### Requirement: Minimum decay for zero turnover

`chip_distribution.py` 在 `turnover_rate=0` 时 MUST 应用最低衰减。

#### Scenario: Limit-up bar with zero turnover
- **WHEN** 涨停无换手，turnover_rate=0
- **THEN** decay_rate SHALL 为最低值（如 0.01），筹码仍会衰减

### Requirement: Confidence gate threshold appropriate

置信度门限 MUST 与最大理论置信度匹配。

#### Scenario: Two dimensions agree on same stage
- **WHEN** 量价=主升(80), MA=主升(75), ATR=不同(55)
- **THEN** 置信度 = 80*0.5 + 75*0.3 = 62.5，SHALL 通过门限

### Requirement: confirm_buffer has floor

`confirm_buffer` MUST 有下限 clamp。

#### Scenario: Calibrated confirm_buffer near zero
- **WHEN** 校准值接近 0，累积乘法后 confirm_buffer = 0.01
- **THEN** SHALL 被 clamp 到下限（如 0.5）

### Requirement: Stage priority for ties

阶段平局时 MUST 有显式优先级。

#### Scenario: Two stages with equal score
- **WHEN** accumulation=0.5, markup=0.5
- **THEN** SHALL 按优先级选择（markup > accumulation > testing > distribution > markdown）
