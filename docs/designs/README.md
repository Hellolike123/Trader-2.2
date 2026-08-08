# designs/ 设计文档索引

本目录存放架构与功能设计稿（ADR 见 `docs/ADR-*.md`）。

## 策略分层（2026-07）

| 文档 | 用途 |
|------|------|
| [strategy-layered-architecture.md](./strategy-layered-architecture.md) | 分析 / 策略 / 决策三层 + **6 闸口** |
| [analysis-strategy-boundaries.md](./analysis-strategy-boundaries.md) | **架构边界（Agent 必读）** 依赖方向 / `analysis/`·`strategy/` 包 / 加减模块菜谱 |
| [analysis-opinion-cards.md](./analysis-opinion-cards.md) | **P0 分析意见卡**字段冻结 |
| [strategy-gates.md](./strategy-gates.md) | **P1 六闸口 IO / 互斥** |
| [strategy-gates.md](./strategy-gates.md) | **买点「盖」生命周期**摘要（完整规格已归档，走 git 历史） |
| [strategy-pack.md](./strategy-pack.md) | 策略包字段、匹配、展示契约 |
| [strategy-roadmap-and-tests.md](./strategy-roadmap-and-tests.md) | **落地分期 + 测试清单**（P0～P4） |
| [strategy-menu.md](./strategy-menu.md) | 缠/威/mi 菜单与包映射（思路） |
| [wyckoff-state-view.md](./wyckoff-state-view.md) | 威科夫 StateView 契约（已实现 A 档） |
| [resonance-and-orchestration.md](./resonance-and-orchestration.md) | **目标架构法源**：五层+编排、共振非厚打分、T0/池/候选池/仓位、加模块菜谱、阶段 0～5 |

**推荐阅读顺序（开发 Agent）**：  
**resonance-and-orchestration（产品方向）** → `analysis-strategy-boundaries`（import 红线）→ analysis-opinion-cards → strategy-gates → strategy-pack → roadmap。

**原则**：以本目录为准；桌面草稿仅作备份，不作为开发契约。

**Fusion 默认（与代码一致）**：`FUSION_FROM_CARDS` **缺省 = cards**；`classic` / `compare` 已退役，设了也仍走 cards。见 `analysis-strategy-boundaries.md` §5。  
**产品方向**：主路径走向「共振 + 策略 + 纪律」；fusion 分不作总司令。见 resonance 文档。

## 其它

| 文档 | 用途 |
|------|------|
| p0-1-signal-structurization.md | 信号结构化 |
| p1-split-core-seam-design.md | 核心接缝 |
| p3-golden-diff-gate.md | Golden 闸门 |
