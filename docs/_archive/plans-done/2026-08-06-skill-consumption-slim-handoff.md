# Skill 消费底层优化 — docs 节食 + 导航接线 handoff

> 状态：active（2026-08-06 起）
> 法源：`docs/README.md`（文档索引）· AGENTS.md（Agent 主入口）· 本 repo「先 handoff 再实现」纪律

## 目标

降低 Agent 跑 skill 时的**内容消费成本**（导航搜索空间 + 上下文膨胀），不动引擎、不动 skill 行为。

## 背景量化

- docs/ 152 文件 / 1.5MB / 2.4 万行；其中无权威入口引用的 ≈ 85%
- 合同四件套起步 ≈ 37k tokens（AGENTS 5.1k + DEEP 20.7k + BUSINESS 7.3k + ARCH 4.2k）
- import 实测 0.33s；慢在文档丛林，不在脚本

## 必须（验收表）

| # | 必须项 | 验收 |
|---|--------|------|
| 1 | 权威入口引用（AGENTS/AGENTS_DEEP/BUSINESS/ARCHITECTURE/README/references）指向的文件**零移动** | 归档后重跑引用 grep，全部存活 |
| 2 | `docs/plans/wyckoff-phase-fail-copy-handoff.md`、`docs/plans/chanlun-skill-slim-b-handoff.md` 保留（references 引用） | grep 存活 |
| 3 | `docs/plans/done/` 保留 `range-diff-fixes-handoff.md`、`wyckoff-phase-accuracy-handoff-2026-07-31.md`（BUSINESS 引用） | grep 存活 |
| 4 | `docs/audit/wyckoff-original-concept-inventory.md` 保留（BUSINESS 引用） | grep 存活 |
| 5 | `docs/designs/` 的 strategy-* 系列 + resonance + wyckoff-state-view + analysis-* 保留（docs/README 索引的现行契约） | 原位 |
| 6 | 归档用 `git mv`，保历史可回滚 | git log 连续 |
| 7 | 断链修复（trader/references/output-template.md:7）先于归档，同一批内无中间态 | commit 顺序 |
| 8 | 归档后更新 `docs/README.md` 索引 + AGENTS.md 接线（指向 docs/README） | 文件内容 |
| 9 | AGENTS.md 瘦身只去重（推荐工作流→skill-usage §五），不改核心导航 | diff 可读 |

## 禁止（勿改）

- 禁止删除任何 docs 文件（只 `git mv` 归档）
- 禁止移动 AGENTS/AGENTS_DEEP/BUSINESS/ARCHITECTURE/README（根）
- 禁止改 engine / skill 行为 / 输出契约内容（output-template 只改路径行）
- 禁止动 `.workbuddy/memory/`、`.claude/`、`.tmp/`、`.zcode/`、`.trellis/` 等工具目录
- 归档区内组内互引（audit↔plans）允许失效——考古区不承诺链接活性

## 归档目标（`docs/_archive/`）

| 源 | 去 | 例外 |
|----|----|------|
| `docs/reviews/**` | `_archive/reviews/` | 无 |
| `docs/methodology/**` | `_archive/methodology/` | 无 |
| `docs/_deprecated/**` | `_archive/_deprecated/` | 无 |
| `docs/plans/done/` 40 个 | `_archive/plans-done/` | range-diff-fixes / wyckoff-phase-accuracy |
| `docs/plans/` 根 21 个 | `_archive/plans/` | 9 个被引用 + README |
| `docs/audit/` 21 个 | `_archive/audit/` | wyckoff-original-concept-inventory |
| `docs/designs/` 4 个 | `_archive/designs/` | 见必须 #5 |

## 可改文件白名单

- `01-功能包-packages/trader/references/output-template.md`（仅第 7 行路径）
- `docs/README.md`（索引更新）
- `AGENTS.md`（接线一行 + 推荐工作流去重 + 持久化标注）
- `docs/plans/active/2026-08-06-skill-consumption-slim-handoff.md`（本文件）

## 执行顺序

1. commit 1：修断链（output-template.md）
2. commit 2：归档 + docs/README 更新 + AGENTS 接线
3. commit 3：AGENTS.md 瘦身
4. 验收：重跑引用 grep + 冒烟（agent-quickstart 命令）
5. 本 handoff 移至 `docs/plans/done/`
