## ADDED Requirements

### Requirement: 四类变更分类

系统 SHALL 支持四类 skill 输出变更分类：性能优化（performance）、数据修复（data-fix）、功能增改（feature）、显示调整（display）。

#### Scenario: 变更分类选择

- **WHEN** 开发者创建一个新的 skill 输出变更
- **THEN** 系统 SHALL 提供四类分类选项，并根据分类预填充对应的检查清单模板

### Requirement: 性能优化类变更模板

性能优化类变更 SHALL 包含以下必填项：问题现象（哪个 skill、什么条件下慢）、性能数据（耗时对比）、优化方案。

#### Scenario: 创建性能优化变更

- **WHEN** 开发者选择「性能优化」分类创建变更
- **THEN** 变更 proposal SHALL 包含问题现象、当前耗时、目标耗时、优化方案等字段

#### Scenario: 性能验证

- **WHEN** 性能优化变更执行完成
- **THEN** 开发者 SHALL 运行 benchmark 对比优化前后的耗时数据

### Requirement: 数据修复类变更模板

数据修复类变更 SHALL 包含以下必填项：数据问题描述（哪个字段、错误值是什么）、正确数据来源、修复方案。

#### Scenario: 创建数据修复变更

- **WHEN** 开发者选择「数据修复」分类创建变更
- **THEN** 变更 proposal SHALL 包含问题数据截图/日志、正确数据来源、修复逻辑

#### Scenario: 数据一致性验证

- **WHEN** 数据修复变更执行完成
- **THEN** 开发者 SHALL 对比修复前后输出，确认数据正确且未引入新问题

### Requirement: 功能增改类变更模板

功能增改类变更 SHALL 包含以下必填项：新增/修改的分析逻辑、影响的输出字段、预期输出示例。

#### Scenario: 创建功能增改变更

- **WHEN** 开发者选择「功能增改」分类创建变更
- **THEN** 变更 proposal SHALL 包含功能描述、影响范围、预期输出示例

### Requirement: 显示调整类变更模板

显示调整类变更 SHALL 包含以下必填项：当前显示效果、预期显示效果、影响的输出格式。

#### Scenario: 创建显示调整变更

- **WHEN** 开发者选择「显示调整」分类创建变更
- **THEN** 变更 proposal SHALL 包含当前输出截图、目标输出样式、微信端兼容性检查
