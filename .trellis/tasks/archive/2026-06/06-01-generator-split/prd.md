# Generator 模式拆分 — output-contract 拆为模板+风格指南

## Goal

将现有 `output-contract.md` 按 Google Generator 模式拆分为两个独立文件：模板（定义结构）和风格指南（定义表达方式），使 AI 可按需加载，减少 token 浪费和格式漂移。

## What I already know

- 现有 2 个 output-contract 文件：`trader/references/output-contract.md`（57行）和 `t0/references/output-contract.md`（60行）
- 每个文件同时包含：结构定义（section 顺序、必填字段）+ 风格规则（禁用 markdown 语法、旧格式检测）
- AGENTS.md 中已有详细的"微信端格式红线"规则（禁用 #标题、---水平线、**粗体**、表格、>引用、列表符）
- 目前所有规则混在一个文件里，AI 加载时无法区分"只需要结构"和"需要完整约束"的场景

## Assumptions (temporary)

- 拆分后两个文件都放在同一个 `references/` 目录下（与原 output-contract.md 同级）
- 现有 SKILL.md 和其他引用 output-contract 的地方需要同步更新路径
- review skill 也可能需要类似的 output-contract（待确认）

## Open Questions

- review skill 是否也需要拆分 output-contract？

## Requirements (evolving)

- 将 output-contract.md 拆为 output-template.md + output-style-guide.md
- output-template.md 只包含结构定义（section 顺序、必填字段、数据来源）
- output-style-guide.md 包含 output-contract 特有的格式规则（旧格式检测、ATR 行位置等），全局微信红线通过引用指向 AGENTS.md
- 更新所有引用 output-contract.md 的文件

## Decision (ADR-lite)

**Context**: 风格指南是否需要复制 AGENTS.md 的全局微信红线
**Decision**: 方案 1 — 只保留 output-contract 特有规则，全局红线通过引用指向 AGENTS.md
**Consequences**: 改一处就够了，不会出现两份文件不同步的问题；AI 加载 style-guide 时需要额外加载 AGENTS.md 获取完整红线

**Context**: 原 output-contract.md 如何处理
**Decision**: 方案 1 — 直接删除，所有引用改为指向新的两个文件
**Consequences**: 干净彻底，不留历史包袱

## Acceptance Criteria (evolving)

- [ ] `trader/references/output-template.md` 存在且只包含结构定义
- [ ] `trader/references/output-style-guide.md` 存在且只包含风格规则
- [ ] `t0/references/output-template.md` 存在且只包含结构定义
- [ ] `t0/references/output-style-guide.md` 存在且只包含风格规则
- [ ] 原 `output-contract.md`（trader + t0）已删除
- [ ] `AGENTS.md` 引用已更新
- [ ] `AGENTS_DEEP.md` 引用已更新
- [ ] `docs/user-guide.md` 引用已更新
- [ ] `.trellis/spec/backend/directory-structure.md` 引用已更新

## Definition of Done

- 拆分后的文件通过 trellis-check 验证
- 无遗漏引用

## Out of Scope (explicit)

- review skill 的 output-contract（本次只处理 trader 和 t0）
- 修改实际的 Python 代码逻辑

## Technical Notes

- trader output-contract: `01-功能包-packages/trader/references/output-contract.md`
- t0 output-contract: `01-功能包-packages/t0/references/output-contract.md`
- AGENTS.md 中的格式红线规则（Section "通用输出格式约束"）
