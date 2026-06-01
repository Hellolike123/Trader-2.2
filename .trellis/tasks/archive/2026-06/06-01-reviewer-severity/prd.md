# Reviewer 分级 — trellis-check 加 Error/Warning/Info severity

## Goal

给 trellis-check 的检查项和报告增加严重性分级（Error / Warning / Info），使 check 结果更精细，用户可以决定哪些必须修、哪些可以暂缓。

## What I already know

- 现有 trellis-check SKILL.md（92行）有 Step 4 checklist，全部是 `- [ ]` 无分级
- 现有 trellis-check agent 报告格式只有 "Issues Found and Fixed" 和 "Issues Not Fixed" 两类
- check sub-agent 目前对所有发现的问题都直接修复，没有"Warning 但不阻塞"的中间态
- Google Reviewer 模式的核心就是分层架构：可变规则独立存储 + 错误分级输出

## Assumptions (temporary)

- 分级标准需要定义清楚：什么算 Error（必须修）、Warning（建议修）、Info（提示）
- 报告格式需要适配分级
- 现有的 checklist 项需要重新分类

## Open Questions

- 现有 checklist 项如何分类到 Error/Warning/Info？

## Requirements (evolving)

- 给 trellis-check 的 checklist 增加 severity 标注（每项固定分级）
- 报告格式增加分级展示
- Error 级别发现必须修复才能通过，Warning/Info 可以不修但需记录

## Severity 分级标准

**Error（必须修）：**
- Linter 不过
- Type checker 不过
- 测试不过
- 有 debug logging 残留
- 有 suppressed warnings 或 type-safety bypasses

**Warning（建议修）：**
- 新函数没加单元测试
- Bug fix 没加回归测试
- 行为变了但没更新已有测试
- 跨层数据流读写不正确
- 类型/Schema 在层间传递不一致
- 错误没有正确传播到调用方
- 存在重复代码没提取
- Import 路径不正确
- 循环依赖
- 同层其他地方用了相同概念但不一致

**Info（提示）：**
- Spec 是否需要更新（新 pattern、convention、lesson learned）

## Acceptance Criteria (evolving)

- [ ] SKILL.md checklist 项有 severity 标注（Error/Warning/Info）
- [ ] agent 报告格式支持分级展示（分 Error/Warning/Info 三组）
- [ ] Error 级别问题必须修复才能通过 check
- [ ] Warning/Info 级别问题可以不修复但需记录在报告中

## Decision (ADR-lite)

**Context**: 分级标准如何定义
**Decision**: 方案 1 — 按检查项固定分级，每个 checklist 项写死 severity
**Consequences**: 简单明确，agent 不需要额外判断逻辑

## Definition of Done

- 修改后的 trellis-check 通过自身验证

## Out of Scope (explicit)

- 修改 trellis-implement 或其他 agent
- 修改 Python 代码逻辑

## Technical Notes

- SKILL.md: `.opencode/skills/trellis-check/SKILL.md`
- Agent: `.opencode/agents/trellis-check.md`
