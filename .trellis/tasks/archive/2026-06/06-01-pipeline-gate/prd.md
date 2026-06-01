# Pipeline 门控 — workflow 加显式用户确认步骤

## Goal

在 Trellis workflow 的关键阶段切换点增加显式用户确认门控，防止 AI 在用户未确认的情况下自动推进到下一步。

## What I already know

- 现有 workflow 阶段切换靠 task.json status 自动流转，无显式用户确认
- Phase 1 → Phase 2：`task.py start` 自动切换（用户说"可以了"就直接 start）
- Phase 2 → Phase 3：自动流转（status 一直是 in_progress）
- Phase 3.4 commit：已有确认（commit plan 需要用户 ok）
- Google Pipeline 模式的核心是"显式定义阶段关卡，每步需显式确认才能继续"

## Assumptions (temporary)

- 门控加在 workflow.md 的状态块中，通过 prompt 文本要求 AI 等待用户确认
- 不需要修改 task.py 脚本（纯 prompt 层面的门控）

## Open Questions

- 门控应该加在哪些阶段切换点？

## Requirements (evolving)

- 在 Phase 1 → Phase 2 切换点增加显式用户确认门控
- AI 在 `task.py start` 之前必须展示 PRD 摘要并等待用户确认
- 门控通过 workflow.md 的 planning 状态块 prompt 文本实现

## Decision (ADR-lite)

**Context**: 门控加在哪些阶段切换点
**Decision**: 方案 1 — 只在 Phase 1 → Phase 2 加门控
**Consequences**: 最小改动，Phase 2 → Phase 3 的 check 结果已有报告展示，commit 已有确认

## Acceptance Criteria (evolving)

- [ ] planning 状态块中有显式用户确认门控提示
- [ ] AI 在 `task.py start` 前必须展示 PRD 摘要并等待用户确认
- [ ] 门控不影响现有 task.py 脚本逻辑

## Definition of Done

- 修改后的 workflow.md 通过 trellis-check 验证

## Out of Scope (explicit)

- 修改 task.py 脚本
- 修改其他 agent 文件

## Technical Notes

- workflow.md: `.trellis/workflow.md`
- 状态块在 Phase Index section 中
