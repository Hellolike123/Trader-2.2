# designs/ 设计文档索引

本目录存放架构与功能设计稿（ADR 见 `docs/ADR-*.md`）。

## 策略分层（2026-07）

| 文档 | 用途 |
|------|------|
| [strategy-layered-architecture.md](./strategy-layered-architecture.md) | 分析 / 策略 / 决策三层 + **6 闸口** |
| [strategy-pack.md](./strategy-pack.md) | 策略包字段、匹配、展示契约 |
| [strategy-roadmap-and-tests.md](./strategy-roadmap-and-tests.md) | **落地分期 + 测试清单**（P0～P4） |
| [strategy-menu.md](./strategy-menu.md) | 缠/威/mi 菜单与包映射（思路） |
| [wyckoff-state-view.md](./wyckoff-state-view.md) | 威科夫 StateView 契约（已实现 A 档） |

**推荐阅读顺序**：architecture → pack → roadmap（测试）→ menu。

**原则**：以本目录为准；桌面草稿仅作备份，不作为开发契约。

## 其它

| 文档 | 用途 |
|------|------|
| p0-1-signal-structurization.md | 信号结构化 |
| p1-split-core-seam-design.md | 核心接缝 |
| p3-golden-diff-gate.md | Golden 闸门 |
