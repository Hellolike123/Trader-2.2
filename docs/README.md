# Trader3.0 文档入口

> **从这里开始。** 根目录一堆历史 plan 已按生命周期归类；现行契约在 `designs/` 与仓库根 `AGENT.md` / `ARCHITECTURE.md` / `BUSINESS.md`。

---

## 日常必读（现行真相）

| 文档 | 用途 |
|------|------|
| [../AGENT.md](../AGENT.md) | **Agent 开发主入口** |
| [../AGENTS.md](../AGENTS.md) | 业务速查、命令、微信输出红线 |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | 架构 |
| [../BUSINESS.md](../BUSINESS.md) | 业务规则 |
| [../README.md](../README.md) | 项目简介 |
| [guide/user-guide.md](./guide/user-guide.md) | 用户操作手册 |

---

## 设计（在做 / 已定稿）

索引：[designs/README.md](./designs/README.md)

| 主题 | 文档 |
|------|------|
| **目标架构法源（Agent 必读）** | [designs/resonance-and-orchestration.md](./designs/resonance-and-orchestration.md) — 五层+编排、共振、T0/池/仓位、加模块 |
| **架构边界（Agent 必读）** | [designs/analysis-strategy-boundaries.md](./designs/analysis-strategy-boundaries.md) |
| **策略分层 · 6 闸口** | [designs/strategy-layered-architecture.md](./designs/strategy-layered-architecture.md) |
| **分析意见卡（P0 ✅）** | [designs/analysis-opinion-cards.md](./designs/analysis-opinion-cards.md) |
| **六闸口（P1 ✅）** | [designs/strategy-gates.md](./designs/strategy-gates.md) |
| **策略匹配（P2 ✅）** | `trader_shared/strategy_match.py` |
| **报告 📐（P3 ✅）** | `report_core` + `strategy_match` |
| 策略包契约 | [designs/strategy-pack.md](./designs/strategy-pack.md) |
| **落地 + 测试 P0～P4** | [designs/strategy-roadmap-and-tests.md](./designs/strategy-roadmap-and-tests.md) |
| 策略菜单（缠/威/mi） | [designs/strategy-menu.md](./designs/strategy-menu.md) |
| 威科夫 StateView | [designs/wyckoff-state-view.md](./designs/wyckoff-state-view.md) |

**开发节奏**：分析契约（P0 ✅）→ 策略闸口（P1–P2）→ 报告 📐（P3）。见 roadmap。

---

## 架构决策 ADR

| ADR | 说明 |
|-----|------|
| [architecture/ADR-001](./architecture/ADR-001-colocate-shared-library.md) | 共享库共置 |
| [architecture/ADR-002](./architecture/ADR-002-route-via-plugin-registry.md) | PluginRegistry |
| [architecture/ADR-003](./architecture/ADR-003-extract-report-builder.md) | report_builder |
| [architecture/ci-gate.md](./architecture/ci-gate.md) | CI 门禁 |

根目录 `docs/ADR-00x-*.md` 为**跳转桩**，防旧链接失效。

---

## 计划 plans/

| 目录 | 含义 |
|------|------|
| [plans/active/](./plans/active/) | 尚未做完 / 仍可能执行 |
| [plans/done/](./plans/done/) | 已落地或历史方案（考古用） |

新计划请直接建在 `plans/active/`，**不要**再丢到 `docs/` 根目录。

---

## 审查 reviews/

| 目录 | 内容 |
|------|------|
| [reviews/2026-06/](./reviews/2026-06/) | 报告多轮体检等 |
| [reviews/2026-07/](./reviews/2026-07/) | 代码审查、缠/威 handoff |

---

## 审计 audit/

批次审查报告、模块 review 底稿。日常开发不必通读；对症搜文件名即可。

---

## 其它

| 路径 | 用途 |
|------|------|
| [methodology/](./methodology/) | Skill 设计方法等 |
| [_deprecated/](./_deprecated/) | 废弃规格与旧 superpowers |
| [guide/](./guide/) | 用户手册、缠论操盘 playbook |

---

## 仓库根文档（勿重复发明）

- `AGENT.md` — Agent 主规范  
- `AGENTS.md` / `AGENTS_DEEP.md` — 业务与深文档  
- `ARCHITECTURE.md` / `BUSINESS.md` — 架构与业务  

Agent 改架构/业务规则时：**先改这两份 + designs，再改代码。**

---

*文档整理批次：2026-07-18（分类归档，无业务代码变更）。*
