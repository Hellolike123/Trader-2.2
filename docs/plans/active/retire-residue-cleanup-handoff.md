# Retire Residue Cleanup — Handoff

> **status**: active
> **日期**: 2026-08-08
> **法源**: `BUSINESS.md` §2.7；`AGENTS.md`「Fusion 生产路径」；`docs/designs/analysis-strategy-boundaries.md` §5
> **范围**: 清理已退役但仍在活动树中的 fusion 对账/映射残留，git 历史保留

## 1. 删除清单（从活动树删除，git 历史保留）

- `scripts/compare_fusion_paths.py`：纯退役 CLI，无测试依赖。
- `02-共享模块-shared/trader_shared/fusion_path_compare.py`：classic vs cards 对账纯函数，仅被自身测试引用。
- `02-共享模块-shared/tests/test_fusion_path_compare.py`：上述对账逻辑的专属测试。
- `02-共享模块-shared/trader_shared/_deprecated/fusion_classic_mappers.py`：classic mapper 归档，仅被历史 parity 测试引用。
- `02-共享模块-shared/trader_shared/_deprecated/__init__.py`：归档包空壳，随 mapper 一并移出活动树。

## 2. 同步修改

- `02-共享模块-shared/tests/test_fusion_core.py`：删除只测 classic mapper 的测试类与方法。
- `02-共享模块-shared/tests/test_p0_signal_structurization.py`：删除依赖 `_chan_to_signal` 的 parity 断言，保留 signal_schema / vpf 契约测试。
- `scripts/run-gate-tests.sh`：移除 `test_fusion_path_compare.py`。
- `AGENTS.md` / `BUSINESS.md` / `docs/designs/analysis-strategy-boundaries.md` / `docs/architecture/ci-gate.md` / `docs/plans/active/fusion-cards-only-and-import-cleanup-handoff.md`：更新退役路径表述。

## 3. 禁止项

- 禁止改写 git 历史、force push 或物理删除归档历史。
- 禁止恢复 classic / compare 生产路径或 `fusion_compare` 输出。
- 禁止改动 fusion 权重、`decision_view`、support / stop 等决策行为。
- 禁止把 signal_schema 的现行契约测试整文件删掉；本任务只去掉依赖已删 mapper 的部分。

## 4. 验收

| # | 验收 | 证据 |
|---|------|------|
| 1 | 上述 5 个文件不在活动树 | `git status` / `ls` |
| 2 | 无代码 import / 门禁引用；`test_arch_boundaries.py` 的防重建检查可保留 | `rg` / pytest |
| 3 | `test_fusion_core.py` / `test_p0_signal_structurization.py` 可独立运行 | pytest |
| 4 | 门禁通过 | `scripts/run-gate-tests.sh` |
| 5 | 双 Agent 审查通过 | 查 Agent 结论 |
