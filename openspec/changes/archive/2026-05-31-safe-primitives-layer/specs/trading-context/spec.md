## ADDED Requirements

### Requirement: Centralized trading day judgment

`is_trading_day(date)` MUST 综合周末和节假日判断某天是否为交易日。

#### Scenario: Normal weekday
- **WHEN** 传入周三且不属于节假日
- **THEN** SHALL 返回 `True`

#### Scenario: Weekend
- **WHEN** 传入周六
- **THEN** SHALL 返回 `False`

#### Scenario: Weekday holiday
- **WHEN** 传入周三且属于法定节假日（如国庆节）
- **THEN** SHALL 返回 `False`

#### Scenario: Holiday bridge day
- **WHEN** 传入周四且属于调休工作日但股市不开盘
- **THEN** SHALL 返回 `False`

### Requirement: Centralized trading time judgment

`is_trading_time()` MUST 综合交易日判断和时段判断。

#### Scenario: Trading hours on normal day
- **WHEN** 周三 10:00
- **THEN** SHALL 返回 `True`

#### Scenario: Trading hours on holiday
- **WHEN** 节假日 10:00
- **THEN** SHALL 返回 `False`

#### Scenario: After hours
- **WHEN** 周三 20:00
- **THEN** SHALL 返回 `False`

#### Scenario: Lunch break
- **WHEN** 周三 12:00
- **THEN** SHALL 返回 `False`

### Requirement: Current session identification

`current_session()` MUST 返回当前所处的交易时段。

#### Scenario: Pre-market
- **WHEN** 周三 9:00
- **THEN** SHALL 返回 `"pre_market"`

#### Scenario: Morning session
- **WHEN** 周三 10:00
- **THEN** SHALL 返回 `"trading"`

#### Scenario: Lunch break
- **WHEN** 周三 12:00
- **THEN** SHALL 返回 `"lunch_break"`

#### Scenario: After close
- **WHEN** 周三 15:30
- **THEN** SHALL 返回 `"post_market"`

#### Scenario: Non-trading day
- **WHEN** 周六 10:00
- **THEN** SHALL 返回 `"non_trading"`

### Requirement: Data freshness tracking

`data_freshness()` MUST 返回当前数据的新鲜度标签。

#### Scenario: During trading hours
- **WHEN** 周三 10:00
- **THEN** SHALL 返回 `"live"`

#### Scenario: After hours
- **WHEN** 周三 20:00
- **THEN** SHALL 返回 `"stale"`

#### Scenario: Weekend
- **WHEN** 周六 10:00
- **THEN** SHALL 返回 `"stale"`

### Requirement: Backward compatible is_trading_time

原有 `light_data.is_trading_time()` MUST 改为调用 `trading_context.is_trading_time()`，保持签名不变。

#### Scenario: Existing caller
- **WHEN** 任何模块调用 `from light_data import is_trading_time`
- **THEN** SHALL 行为与新 `trading_context.is_trading_time()` 一致（增加节假日检查）
