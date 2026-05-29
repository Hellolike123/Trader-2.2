## Why

当前 Trader Hermes skill 的迭代流程是「看到输出问题 → 直接改代码」，缺乏结构化的变更追踪。常见场景包括：性能瓶颈修复、数据源异常处理、分析结论/建议的增删改、输出格式调整。由于没有标准化流程，容易出现改了哪里不清楚、回滚困难、变更之间缺乏关联等问题。需要建立一套轻量级的 skill 输出迭代工作流，让每次改动都有据可查、有迹可循。

## What Changes

- 建立「观察 → 诊断 → 提案 → 执行 → 验证」的 skill 迭代标准流程
- 定义四类常见变更模板：性能优化、数据修复、功能增改、显示调整
- 将 Hermes skill 输出质量检查纳入日常循环（复盘时自动对比前后输出）
- 为每次变更生成可追溯的 proposal → design → tasks 链路

## Capabilities

### New Capabilities

- `skill-iteration-workflow`: skill 输出迭代的标准工作流定义，覆盖从发现问题到验证修复的全链路
- `change-classification`: 四类变更（性能/数据/功能/显示）的模板与快速提案机制

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- 涉及文件：`AGENTS.md`（工作流说明）、各 skill 的 `SKILL.md`（迭代流程引用）
- 新增 `openspec/changes/` 下的变更模板目录
- 影响日常开发习惯：从「直接改」转向「先提案再改」
