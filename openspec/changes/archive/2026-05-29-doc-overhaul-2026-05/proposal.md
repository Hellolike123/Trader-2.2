# Doc Overhaul 2026-05 — 全面文档整顿

> 状态：草案
> 创建：2026-05-29

---

## 问题

代码快速迭代期间，多个功能从"设计→实现"跳过了文档同步。当前存在 5 个文档的过时或缺失：

| 文档 | 状态 | 影响 |
|------|------|------|
| AGENTS.md | 缺失 6 个功能的描述 | AI Agent 无法感知一票否决、移动止损等关键行为 |
| AGENTS_DEEP.md | 过时：status_for→status_layers、参数变更 | Agent 深度参考与实际代码脱节 |
| decision-fusion-layer.md | 过时：签名、输出、默认值 | 融合层设计文档不再准确 |
| trader-refactor-plan.md | 过时：静态止损→动态移动止损 | ATR 体系文档指向旧方案 |
| phase2-improvement-plan.md | 过时：C-13 已修复但未标记 | 审计记录不准确 |

另外，`PLAN_SECTOR_STRENGTH.md` 有方案但代码未实现（P2），本次不处理。

---

## 目标

1. 为已实现但无文档的功能补写规格文档（250日线、移动止损、假跌破、分阶段退出）
2. 同步更新所有过时文档，使其与当前代码一致
3. 更新 AGENTS.md / AGENTS_DEEP.md，确保 AI Agent 能准确理解系统行为

---

## 范围

### 新增文档
- `specs/trend-filter/spec.md` — 250日线趋势过滤规格
- `specs/exit-strategy/spec.md` — ATR移动止损 + 假跌破 + 分阶段退出规格

### 更新文档
- `docs/designs/decision-fusion-layer.md` — 同步融合层最新实现
- `docs/trader-refactor-plan.md` — 更新 ATR 止损机制描述
- `docs/phase2-improvement-plan.md` — 标记 C-13 为已修复
- `AGENTS.md` — 添加趋势过滤、退出策略、融合覆盖的描述
- `AGENTS_DEEP.md` — 更新状态机、数据流图、函数签名

### 不在范围内
- `PLAN_SECTOR_STRENGTH.md` — 代码未实现，保持现状
- 任何代码变更 — 本次只做文档

---

## 验收标准

- [ ] 每个已实现功能在 docs/ 下有对应的 spec 或 design 文档
- [ ] AGENTS.md 中描述的每个行为都能在代码中找到对应实现
- [ ] AGENTS_DEEP.md 中的函数签名、参数列表、状态列表与 config.py / decision_core.py 一致
- [ ] phase2-improvement-plan.md 中已修复的 issue 标记为 resolved
- [ ] decision-fusion-layer.md 中的示例输出与实际代码输出格式一致
