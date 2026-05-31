## ADDED Requirements

### Requirement: stage_positioning volume-price assessment tests

`_assess_volume_price()` MUST 有测试覆盖量价关系的四种场景。

#### Scenario: Accumulation (蓄势) — low volume, flat price
- **WHEN** bars 显示连续 10 天缩量、价格窄幅震荡
- **THEN** 返回 `("蓄势", confidence, reason)`，confidence > 0.5

#### Scenario: Markup (主升) — expanding volume, rising price
- **WHEN** bars 显示连续 5 天放量上涨
- **THEN** 返回 `("主升", confidence, reason)`，confidence > 0.6

#### Scenario: Distribution (派发) — high volume, flat/declining price
- **WHEN** bars 显示高位放量滞涨
- **THEN** 返回 `("派势", confidence, reason)`

#### Scenario: Markdown (衰退) — declining volume, falling price
- **WHEN** bars 显示连续下跌、量能萎缩
- **THEN** 返回 `("衰退", confidence, reason)`

### Requirement: stage_positioning major stage detection tests

`_detect_major_stage()` MUST 综合量价、MA 结构、ATR 三维度判定大阶段。

#### Scenario: Bullish stage with high confidence
- **WHEN** 量价=主升(0.8), MA=多头排列(0.9), ATR=适中(0.7)
- **THEN** 返回 `("主升", weighted_confidence, ...)`

#### Scenario: Conflicting signals
- **WHEN** 量价=主升(0.8), MA=空头排列(0.3), ATR=高波动(0.5)
- **THEN** 返回加权结果，confidence 因冲突而降低

### Requirement: stage_positioning short-term momentum tests

`_detect_short_term_momentum()` MUST 基于 MA5/MA10 + change_pct 判定短期动能。

#### Scenario: Strengthening (走强)
- **WHEN** MA5 > MA10, change_pct > 0
- **THEN** 返回 `"走强"`

#### Scenario: Weakening (转弱)
- **WHEN** MA5 < MA10, change_pct < -2%
- **THEN** 返回 `"转弱"`

### Requirement: stage_positioning position sizing tests

`compute_position_with_env()` MUST 根据阶段和大盘环境计算仓位上限。

#### Scenario: Markup stage + bullish market
- **WHEN** 阶段=主升, 大盘=牛市
- **THEN** 仓位上限 >= 50%

#### Scenario: Markdown stage
- **WHEN** 阶段=衰退
- **THEN** 仓位上限 = 0%

#### Scenario: Losing position blocks add
- **WHEN** pnl_pct < 0
- **THEN** hard_blocked = True

### Requirement: decision_core status_layers tests

`status_layers()` MUST 覆盖所有状态分支。

#### Scenario: Price below hard stop
- **WHEN** current <= hard_stop
- **THEN** base_status = "暂不碰"

#### Scenario: Price in low buy zone
- **WHEN** current 在 low_zone_lower ~ low_zone_upper 之间
- **THEN** base_status = "低吸观察"

#### Scenario: Price above confirm
- **WHEN** current >= confirm_price
- **THEN** base_status 可能是 "突破确认" 或 "等转强"

#### Scenario: Current price is zero
- **WHEN** current = 0
- **THEN** 返回 "数据不足"

### Requirement: decision_core score_for tests

`score_for()` MUST 根据状态返回 0-100 分。

#### Scenario: High score status
- **WHEN** status = "突破确认"
- **THEN** score >= 80

#### Scenario: Low score status
- **WHEN** status = "暂不碰"
- **THEN** score <= 30

### Requirement: structure_core build_structure_context tests

`build_structure_context()` MUST 返回完整的结构上下文 dict。

#### Scenario: Normal stock with sufficient bars
- **WHEN** 传入 300 根 bars + 正常 current/change_pct
- **THEN** 返回 dict 包含 main_support, resistance, confirm_price, hard_stop, ma_values 等 key

#### Scenario: Stock with insufficient bars
- **WHEN** 传入 10 根 bars
- **THEN** 仍返回 dict，ma_values 中不足的周期为 None

### Requirement: structure_core moving_average tests

`moving_average()` MUST 正确计算 SMA。

#### Scenario: Sufficient data
- **WHEN** 30 根 bars, period=20
- **THEN** 返回最近 20 根 close 的算术平均

#### Scenario: Insufficient data
- **WHEN** 10 根 bars, period=20
- **THEN** 返回 None

### Requirement: structure_core choose_level tests

`choose_level()` MUST 选择最接近 current 的支撑/阻力位。

#### Scenario: Multiple levels below current
- **WHEN** levels=[10, 12, 14], current=15, below=True
- **THEN** 返回 14（最接近的下方价位）

#### Scenario: No levels below current
- **WHEN** levels=[16, 18], current=15, below=True
- **THEN** 抛出 RuntimeError 或返回安全默认值

#### Scenario: Empty levels list
- **WHEN** levels=[], current=15
- **THEN** 抛出 RuntimeError 或返回安全默认值
