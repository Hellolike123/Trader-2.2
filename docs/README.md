# Trader3.0 文档入口

> **从这里开始。** 现行契约在 `designs/` 与仓库根 `AGENTS.md` / `ARCHITECTURE.md` / `BUSINESS.md`。  
> **考古区 `_archive/`**：已交付 handoff、评审逐字稿、methodology、废弃规格与历史 plan 一律归档于此。**默认勿读**（Agent 快路径不导航 `_archive/`）；仅当需要追溯某次决策原文时按文件名检索。
> 其他 Agent 工具目录（`.opencode` / `.mimocode` / `.trellis` 等）属本地协同环境，**勿当业务代码清理**。

---

## 日常必读（现行真相）

| 文档 | 用途 |
|------|------|
| [../AGENTS.md](../AGENTS.md) | **Agent 主入口**（改代码地图、命令、微信红线） |
| [designs/resonance-and-orchestration.md](./designs/resonance-and-orchestration.md) | **产品/架构法源** |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | 架构 |
| [../BUSINESS.md](../BUSINESS.md) | 业务规则 |
| [../AGENT.md](../AGENT.md) | 短跳转（兼容旧链接） |
| [../README.md](../README.md) | 项目简介 |
| [guide/user-guide.md](./guide/user-guide.md) | 用户操作手册 |
| [guide/skill-usage.md](./guide/skill-usage.md) | **五 Skill 岗位用法**（含 chanlun；一天节奏 / 命令速查） |

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
| [plans/active/](./plans/active/) | 尚未做完 / 仍可能执行（空则表示无在施计划） |
| [plans/done/](./plans/done/) | 已落地且仍被现行合同引用的 2 份（其余在 `_archive/plans-done/`） |
| [_archive/](./_archive/) | 考古区：已交付 handoff / 评审 / methodology / 废弃规格 / 历史 plan（默认勿读） |

新计划请直接建在 `plans/active/`，**不要**再丢到仓库根目录。

---

## 审查 reviews/

| 目录 | 内容 |
|------|------|
| [_archive/reviews/](./_archive/reviews/) | 历史评审逐字稿（2026-06/07，考古用） |

---

## 审计 audit/

现行仅保留 `[wyckoff-original-concept-inventory.md](./audit/wyckoff-original-concept-inventory.md)`（BUSINESS 引用的原典盘点）。其余批次审查报告、模块 review 底稿已归档 `_archive/audit/`。日常开发不必通读；对症搜文件名即可。

---

## 其它

| 路径 | 用途 |
|------|------|
| [_archive/methodology/](./_archive/methodology/) | Skill 设计方法等（考古） |
| [_archive/_deprecated/](./_archive/_deprecated/) | 废弃规格与旧 superpowers（考古） |
| [guide/](./guide/) | 用户手册、缠论操盘 playbook |

---

## 仓库根文档（勿重复发明）

- `AGENTS.md` — Agent 主规范 + 改代码地图  
- `AGENTS_DEEP.md` — 深文档  
- `AGENT.md` — 短跳转（兼容）  
- `ARCHITECTURE.md` / `BUSINESS.md` — 架构与业务  

Agent 改架构/业务规则时：**先改 `AGENTS.md` + `designs/`，再改代码。**

---

*文档整理批次：2026-07-18（首次分类归档）；2026-08-06（Skill 消费优化：reviews/methodology/_deprecated/历史 plan/审计底稿迁入 `_archive/`，活跃树 152→40 文件）。*
