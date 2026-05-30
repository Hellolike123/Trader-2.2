## MODIFIED Requirements

### Requirement: T0 输出精简

T0 单次检查卡 SHALL 精简为 4 部分：扫描、盘中动态、下一步。

#### Scenario: 正常输出
- **WHEN** 用户执行 T0 单次检查
- **THEN** 输出包含 4 部分：扫描（扫描结果+关键价位）、盘中动态（盘口+大单+事件）、下一步（仓位+操作指引）

#### Scenario: 告警触发
- **WHEN** 价格触发关注位
- **THEN** 额外显示告警卡（不计入 4 部分）
