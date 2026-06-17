# 代码文档对齐 — 第一批 Skill 参考文件

## Goal

对齐 3 个 Skill（trader/t0/review）的 references 文件与 SKILL.md，确保 AI 按文档生成的输出与实际代码一致。

## What I already know

- AGENTS.md / AGENTS_DEEP.md 已在上一轮对齐（commit 8073412）
- 剩余高风险文档主要是 Skill 参考文件（output-template.md, ai-guide.md, style-guide.md, commands.md, SKILL.md）
- 3 个 Skill：trader（单票分析+选股池）、t0（盘中盯盘）、review（盘后复盘+仓位轮动+信号追踪）

## Requirements

- [x] trader 参考文件对齐（4 文件）
  - `references/output-template.md` — 输出模板字段名匹配 `build_report()` 实际返回值
  - `references/ai-guide.md` — JSON 字段路径匹配代码
  - `references/output-style-guide.md` — 样式规范匹配渲染输出
  - `SKILL.md` — 命令表和函数签名
- [x] t0 参考文件对齐（4 文件）
  - `references/output-template.md`
  - `references/ai-guide.md`
  - `references/output-style-guide.md`
  - `SKILL.md`
- [x] review 参考文件对齐（4 文件）
  - `references/review_output-contract.md`（review 的 output-template 代替品）
  - `references/ai-guide.md`
  - `references/output-style-guide.md`（如果存在）
  - `SKILL.md`

## Acceptance Criteria

- [ ] 所有 output-template 中的字段名在代码 `build_report()`, `build_plan()`, `build_review()` 返回值中存在
- [ ] 所有 ai-guide 中的 JSON 路径与实际代码返回结构一致
- [ ] 所有 SKILL.md 命令表引用的是实际存在的入口脚本

## Out of Scope

- `docs/user-guide.md`（第二批）
- `.trellis/spec/` 目录结构/数据库规范（第二批）
- AGENTS.md / AGENTS_DEEP.md（已对齐）
- 废弃文档（`docs/_deprecated/`）
