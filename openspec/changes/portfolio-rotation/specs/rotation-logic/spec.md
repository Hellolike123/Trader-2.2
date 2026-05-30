## ADDED Requirements

### Requirement: 四阶段轮动决策

系统 SHALL 根据两只票的大阶段决定是否轮动。

#### Scenario: 主升期不轮动
- **WHEN** A 票为主升期
- **THEN** 不轮动，让利润跑

#### Scenario: 派发期轮动
- **WHEN** A 票为派发期，B 票为蓄势/主升期
- **THEN** 根据技术指标决定轮动比例（强轮1/3或轻轮1/6）

#### Scenario: 衰退期必须轮
- **WHEN** A 票为衰退期
- **THEN** 必须轮动（止损/清仓）

#### Scenario: 蓄势期看指标
- **WHEN** A、B 票都为蓄势期
- **THEN** 看技术指标决定是否轮动
