## ADDED Requirements

### Requirement: Skill 输出迭代标准流程

系统 SHALL 定义一套 skill 输出迭代的标准流程，包含以下阶段：观察（运行 skill 并检查输出）、诊断（定位问题根因）、提案（创建 OpenSpec change）、执行（修改代码）、验证（重新运行 skill 确认修复）。

#### Scenario: 发现输出问题后的标准处理

- **WHEN** 开发者运行 skill 并发现输出内容有问题（数据错误、格式异常、逻辑矛盾等）
- **THEN** 开发者 SHALL 按「观察 → 诊断 → 提案 → 执行 → 验证」流程处理，其中提案阶段使用 OpenSpec 创建变更记录

#### Scenario: 小改动的快速通道

- **WHEN** 改动仅涉及单个字段显示调整或简单的文案修改
- **THEN** 开发者 MAY 跳过完整的 OpenSpec 流程，仅在代码注释中标注变更原因

### Requirement: 变更可追溯性

每次 skill 输出相关的代码变更 SHALL 有关联的变更记录，记录问题描述、根因分析、修复方案。

#### Scenario: 变更记录创建

- **WHEN** 开发者确认需要修改 skill 输出相关代码
- **THEN** 系统 SHALL 在 `openspec/changes/` 下创建变更目录，包含 proposal.md 描述问题和方案

#### Scenario: 变更历史查询

- **WHEN** 开发者需要回顾某个 skill 的历史改动
- **THEN** 可通过 `openspec list` 查看所有变更记录，并通过变更目录下的文档了解详情

### Requirement: 复盘时集成输出质量检查

在盘后复盘流程中，SHALL 包含对 skill 输出质量的回顾环节。

#### Scenario: 复盘时检查输出

- **WHEN** 开发者执行盘后复盘（review-trader）
- **THEN** 复盘流程 SHALL 包含对当天 skill 输出的检查，记录发现的问题并创建待处理变更
