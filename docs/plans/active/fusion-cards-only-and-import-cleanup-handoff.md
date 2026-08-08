# Fusion Cards-Only + trader_shared Import Cleanup — Handoff

> **status**: active
> **日期**: 2026-08-08
> **法源**: `BUSINESS.md` §2.7；`docs/designs/analysis-strategy-boundaries.md` §5；`AGENTS.md`「Fusion 生产路径」/「改代码去哪」
> **范围**: P1 引擎收口 + P2 流程落地（先写 handoff 再实现）

---

## 1. 目标

1. 删除 `fusion_core` 里 `classic` / `compare` 的 DeprecationWarning 兼容分支；`FUSION_FROM_CARDS` 只保留 cards 生产路径。
2. 迁移 tests / 工具中的裸 import（`pipeline` / `signal_tracker` / `market_env` / `calibrator` / `self_calibration`）到 `trader_shared.*`。
3. 删除 `trader_shared/__init__.py` 的 `scripts/` path 注入和 `sys.modules` 裸名别名。
4. 同步相关文档与测试，跑相关 pytest 和门禁，验证后提交。

## 2. 行为合同

| `FUSION_FROM_CARDS` / `fusion_from_cards` | 行为 |
|-------------------------------------------|------|
| 未设置 / `cards` / `true` / `1` / `on` / `auto` | cards 生产路径；适配失败 → `cards_failed` 中性 |
| `classic` / `compare` / `false` / `0` / `off` / `both` / `dual` | 显式 `ValueError`，不再告警后静默当 cards |

`merge_decisions(..., fusion_from_cards=False)` 同样拒绝，禁止把旧布尔值当 cards。

## 3. 禁止项

- 禁止恢复 classic / compare 生产路径或 `fusion_compare` 输出。
- 禁止改动 fusion 权重、`decision_view`、support / stop 等决策行为。
- 禁止改写 git 历史；活动树退役清理见 `retire-residue-cleanup-handoff.md`。
- 禁止改动 skill 包 identity shim 的 `sys.modules[__name__] = _impl` 机制。
- 禁止把 `docs/plans/active/` 之外的母法源移出或改名。

## 4. 可改文件

- `02-共享模块-shared/trader_shared/fusion_core.py`
- `02-共享模块-shared/trader_shared/__init__.py`
- `02-共享模块-shared/scripts/backtest_engine.py`
- `02-共享模块-shared/tests/` 下涉及裸 import 与 fusion 模式的测试
- `scripts/run-gate-tests.sh` 如需同步门禁子集
- 文档：`AGENTS.md` / `AGENTS_DEEP.md` / `ARCHITECTURE.md` / `BUSINESS.md` / `docs/designs/analysis-strategy-boundaries.md` / `docs/designs/README.md` / `docs/architecture/ci-gate.md` / `01-功能包-packages/*/references/agent-rules.md`

## 5. 验收表

| # | 验收 | 证据 |
|---|------|------|
| 1 | 未设置 / cards / true / 1 / on / auto → `cards` | `test_production_path_defaults` |
| 2 | classic / compare / false / 0 / off / both / dual → `ValueError` | fusion 模式测试 |
| 3 | 生产模块无 `_warn_retired_fusion_mode` / `_warn_deprecated_fusion_classic` | `rg` |
| 4 | 仓库无裸 import 五个收编模块 | `rg` |
| 5 | `trader_shared/__init__.py` 无 `scripts/` path 注入、无裸名别名 | `sed` / `rg` |
| 6 | `import trader_shared` 与 `from trader_shared.pipeline import ...` 可用 | 导入冒烟 |
| 7 | 相关 pytest + 门禁通过 | 命令输出 |
| 8 | 文档不再写「告警后仍 cards」 | `rg` |

## 6. 完成定义

所有验收项通过后，本 handoff 移入 `docs/plans/done/` 或按仓库规则更新状态；commit 至少包含代码、测试、文档三部分。
