# P1 大文件拆分 · TDD 实施 Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> 关联设计：`docs/designs/p1-split-core-seam-design.md`（已批准：先2模块 chan / 止盈并入 stage_position / 顺序 wyckoff→chan→stage / 批准即实现）

**Goal:** 把 `wyckoff_core.py` / `chan_core.py` / `stage_positioning.py` 三个策略单体行为保持地拆分为 facade + 内聚 submodule，外部导入面零改动，由等价性闸门守护。

**Architecture:** 每个原文件 → 薄壳 facade（re-export 全量公开名）+ N 个按职责内聚的 submodule，严格单向依赖、无环。AST 按函数名精确提取（不靠行号），复用 ADR-003b + `docs/designs/p3-golden-diff-gate.md`。

**Tech Stack:** Python 3.11/3.13、`ast` 提取脚本、`pytest`、canonical-JSON 等价闸门、`monkeypatch` 桩。

---

## 全局约定（每轮通用）

- 抽取工具：`scripts/_split_<module>.py`（一次脚本，提交进仓库，便于审计/复跑）。
- 等价闸门：新增 `scripts/_capture_<module>_split_baseline.py` + `tests/test_<module>_split_equivalence.py`，并入 `scripts/run-gate-tests.sh` 的 `TESTS`。
- 每轮 commit 顺序：抽 submodule → 替换 facade → 加 equivalence 测试 → 跑全 gate 绿 → commit。
- 全局改写（env / 客户端 / 文件写）一律 `monkeypatch.setattr`。

---

## Round 1 · wyckoff_core.py（2115 → facade + wyckoff_events + wyckoff_phase）

分区（已用 grep 锁定函数名）：
- **EVENTS**（叶子，无内部跨分区调用）：`_spring_breach_level` `_price_pos_pct` `_is_bc_high_position` `_is_frozen_board` `_board_vol_scale` `_is_trading_range` `_compute_dynamic_support` `_detect_buying_climax` `_detect_selling_climax` `_detect_sign_of_weakness` `_detect_spring` `_detect_upthrust` `_detect_volume_divergence` `_detect_ar` `_detect_sos` `_detect_st` `_detect_lps` `_detect_lpsy` `_detect_effort_vs_result` `_detect_compression` `_detect_trend_pullback`
- **PHASE**：`_scan_for_signal` `_detect_phase` `_phase_key` `_load_phase_state` `_save_phase_state` `_transition_phase`（常量 `_WYCKOFF_PHASE_FILE` `_PHASE_ORDER` 随迁）
- **CORE**（留 facade）：`wyckoff_analysis` `wyckoff_strategy` `wyckoff_strategy_midline` `calculate_wyckoff_score` `format_wyckoff_oneline`

依赖：`core → phase → events`，events 叶子。

### Task 1.1: 写失败测试（捕获当前行为基线）
**Files:** Test: `02-共享模块-shared/tests/test_wyckoff_split_equivalence.py`
**Step 1:** 写测试，调用 `scripts/_capture_wyckoff_split_baseline.py` 生成的 baseline 文件，断言拆分后 `wyckoff_analysis(...)` 等输出 canonical-diff 一致。
**Step 2:** 跑测试，预期 FAIL（baseline 尚未生成）。
Run: `pytest 02-共享模块-shared/tests/test_wyckoff_split_equivalence.py -v`

### Task 1.2: 写抽取脚本并生成 submodule
**Files:** Create: `scripts/_split_wyckoff_core.py`；Create: `trader_shared/wyckoff_events.py` `trader_shared/wyckoff_phase.py`；Modify: `trader_shared/wyckoff_core.py`
**Step 1:** 脚本用 `ast` 按函数名提取，写入两个 submodule（各带原 import 块 + `_logger` + 跨分区相对 import），原文件改写为 facade（保留 5 个 CORE 函数 + `from .wyckoff_events/.wyckoff_phase import (...)` 全量 re-export）。
**Step 2:** `py_compile` 三文件通过。
**Step 3:** 验证 `import trader_shared.wyckoff_core` 且 `wyckoff_analysis` / `format_wyckoff_oneline` / `wyckoff_strategy_midline` 可调用。

### Task 1.3: 生成基线 + 过等价闸门
**Files:** Create: `scripts/_capture_wyckoff_split_baseline.py`；Test: `02-共享模块-shared/tests/test_wyckoff_split_equivalence.py`（补全）
**Step 1:** 在离线桩下（bars fixture + monkeypatch 打掉 `_save_phase_state`/网络）捕获 `wyckoff_analysis`/`calculate_wyckoff_score` 输出为 baseline（canonical JSON，日期掩码）。
**Step 2:** 跑测试，预期 PASS（拆分前后一致）。

### Task 1.4: 入 CI 门禁 + 全量绿 + commit
**Step 1:** 把 `test_wyckoff_split_equivalence.py` 加进 `scripts/run-gate-tests.sh` 的 `TESTS`。
**Step 2:** 跑 `bash scripts/run-gate-tests.sh`，预期全绿（当前基线 68 passed → +1）。
**Step 3:** commit `refactor(p1): split wyckoff_core into events+phase, facade re-export`

---

## Round 2 · chan_core.py（2216 → facade + chan_geometry + chan_structure）

分区：
- **GEOMETRY**（叶子）：`unwrap_chan` `_calc_macd` `handle_inclusion` `find_fractions` `_aggregate_bars` `_higher_level_trend` `build_strokes` `_valid_strokes` `_merge_char_element` `build_segments` `_merge_zones` `build_zones` `_has_entry_exit_segments` `_detect_unilateral`
- **STRUCTURE**：`_structure_conf_thresholds` `_structure_confidence` `classify_structure` `_stroke_macd_area` `_stroke_force_weaker` `_stroke_force_weaker_multi` `_stroke_force_not_much_stronger` `_check_macd_for_2nd_buy` `_check_macd_for_2nd_sell` `_zone_last_end_index` `detect_buy_points` `detect_sell_points` `detect_divergence`
- **CORE**（留 facade）：`_chanlun_compute` `chanlun_analysis` `ChanlunEngine` `_chan_json_default` `_chan_type_canonical` `chanlun_strategy` `chanlun_strategy_midline` `format_chanlun_theory_line`

依赖：`core → structure → geometry`。
（已批准：不拆 `chan_points`，detect_buy/sell_points 留在 chan_structure。）

> 任务细分同 Round 1（Task 2.1 失败测试 → 2.2 抽脚本 → 2.3 基线+闸门 → 2.4 门禁+commit）。

---

## Round 3 · stage_positioning.py（2368 → facade + 4 submodule，轮辐）

分区：
- **STATE**（叶子）：`calc_portfolio_correlation` `_load_stage_state` `_save_stage_state`
- **DETECT**：`_bearish_alignment` `_assess_volume_price` `_detect_main_force_stage` `_volume_price_confirm` `_downgrade_stage` `_upgrade_stage` `_detect_major_stage` `_detect_short_term_momentum` `_layer1_multi_day_confirm` `_layer2_confidence_gate` `_layer3_cross_validation` `_layer4_stage_lock` `compute_position_with_env` `assess_stage` `action_for_holding_state`
- **STOPS**：`compute_stop_losses` `compute_exit_plan` `compute_stage_stop` `check_time_stop` `compute_stop_summary`
- **POSITION**：`evaluate_position_state` `_calc_pullback_add_score` `_calc_reentry_score` `_calc_rally_reduce_score` `_assess_resistance_strength` `_make_position_state` `_empty_position_state` `compute_conditional_take_profit` `compute_take_profit`
- **CORE**（facade）：全量 re-export 上述四者

依赖：detect/stops/position 都只依赖 state（轮辐，无环）。
（已批准：止盈并入 POSITION，不设 stage_profit。）

> 任务细分同 Round 1（Task 3.1 → 3.4）。实现前先 AST 扫描内部跨群互调，确认无环；若有，合并相关群并回写设计文档 §4.3。

---

## 完成判定
- 三文件均拆完，facade 仅 re-export + 保留公开函数。
- 三个 equivalence 测试入 `run-gate-tests.sh`，全量 gate 绿。
- 外部调用方 import 行零改动（`git grep "from trader_shared.\(wyckoff_core\|chan_core\|stage_positioning\) import"` 仍解析）。
