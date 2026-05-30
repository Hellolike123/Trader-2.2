## ADDED Requirements

### Requirement: 四阶段仓位管理

系统 SHALL 根据大阶段确定仓位上限，持仓亏损时禁止加仓。

#### Scenario: 蓄势期仓位
- **WHEN** 大阶段为蓄势期
- **THEN** 仓位上限 30%，第一笔 10%

#### Scenario: 主升期仓位
- **WHEN** 大阶段为主升期
- **THEN** 仓位上限 80%

#### Scenario: 衰退期仓位
- **WHEN** 大阶段为衰退期
- **THEN** 仓位 0%，禁止建仓

#### Scenario: 持仓亏损禁止加仓
- **WHEN** 持仓浮盈 < 0
- **THEN** 禁止加仓操作
