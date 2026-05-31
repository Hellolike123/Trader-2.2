## ADDED Requirements

### Requirement: Chinese market holiday awareness

系统 MUST 知道中国股市法定节假日，在节假日将 `is_trading_time()` 返回 False。

#### Scenario: Weekday holiday
- **WHEN** 当前日期是周三且属于法定节假日（如国庆节）
- **THEN** `is_trading_time()` SHALL 返回 `False`

#### Scenario: Normal weekday
- **WHEN** 当前日期是周三且不属于节假日
- **THEN** `is_trading_time()` SHALL 按正常交易时段判断（9:25-11:30, 13:00-15:00）

#### Scenario: Weekend
- **WHEN** 当前日期是周六
- **THEN** `is_trading_time()` SHALL 返回 `False`（与现有行为一致）

### Requirement: Data freshness tracking

系统在非交易时段返回的数据 MUST 标记为 stale，使下游消费者能区分实时数据和过期数据。

#### Scenario: Quote fetched during trading hours
- **WHEN** 9:35 调用 `fetch_quote()`
- **THEN** 返回的 dict SHALL 包含 `data_freshness="live"`

#### Scenario: Quote fetched at 3 AM
- **WHEN** 凌晨 3 点调用 `fetch_quote()`
- **THEN** 返回的 dict SHALL 包含 `data_freshness="stale"`

#### Scenario: Market env assessed on weekend
- **WHEN** 周六调用 `market_env.assess()`
- **THEN** 返回的 dict SHALL 包含 `data_freshness="stale"`

### Requirement: Zero price data guard

当 `current_price <= 0` 时，`status_layers()` MUST 返回"数据不足"状态，而非"风险回避"。

#### Scenario: Suspended stock with price 0
- **WHEN** 停牌股 current_price=0，调用 `status_layers()`
- **THEN** 返回 SHALL 为 `{"base_status": "数据不足", "theory_status": "数据不足", ...}`

#### Scenario: Normal stock with positive price
- **WHEN** 正常交易股 current_price=15.0
- **THEN** `status_layers()` SHALL 按正常逻辑判定状态

### Requirement: T0 monitor efficient idle

T0 monitor 在收盘后 MUST 进入长休眠而非持续空转。

#### Scenario: Market closed at 15:05
- **WHEN** `run_monitor()` 检测到当前时间 > 15:00
- **THEN** SHALL sleep 到次日 9:25，而非每 5 分钟检查一次

#### Scenario: Market closed on weekend
- **WHEN** `run_monitor()` 检测到今天是周末
- **THEN** SHALL sleep 到下周一 9:25

### Requirement: Fusion status map in degraded T0

降级 T0 安装（无 `decision_core`）时，`_FUSION_STATUS_MAP` MUST 包含完整映射。

#### Scenario: Fusion override in degraded install
- **WHEN** `decision_core` 不可导入，fusion confidence >= threshold
- **THEN** `_FUSION_STATUS_MAP.get(action)` SHALL 返回对应的状态字符串，而非 None
