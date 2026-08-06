# P1 大文件拆分 · 接缝设计文档（DRAFT）

> **状态**：草稿（待评审批准，暂不实现）
> **分支**：`refactor/p1-split-core`（基于 `855af94`）
> **关联**：架构评审 `architecture-review-2026-07-14.md` §六 P1「大文件拆分」；ADR-003 / ADR-003b（报告层拆分先例）；`docs/designs/p3-golden-diff-gate.md`（等价性闸门）
> **目标读者**：实现工程师（零上下文也可执行）

---

## 一、Context（为什么拆）

架构评审把三个"策略单体"列为 P1 巨型文件，且明确指出它们与全局可变状态、测试噪声是**同一根因的不同切面**：

| 文件 | 行数 | 外部导入面 |
|------|------|-----------|
| `stage_positioning.py` | 2368 | `assess_stage` / `compute_exit_plan` / `compute_stage_stop` / `check_time_stop` / `evaluate_position_state` / `_detect_major_stage` / `compute_position_with_env` / `action_for_holding_state` … |
| `chan_core.py` | 2216 | `unwrap_chan` / `ChanlunEngine` / `format_chanlun_theory_line` / `chanlun_strategy` / `chanlun_strategy_midline` … |
| `wyckoff_core.py` | 2115 | `format_wyckoff_oneline` / `wyckoff_strategy` / `wyckoff_strategy_midline` / `wyckoff_analysis` / `calculate_wyckoff_score` … |

**痛点**：
1. 单文件职责过重，难单测（如 `test_chan_core` 126 passed 但混着 pre-existing 漂移，回归信号被噪声淹没）。
2. 隐藏副作用藏在文件内部：`wyckoff_core._save_phase_state` / `stage_positioning._save_stage_state` 直接写盘（D1 phase 只进不退、D3 打分偷偷写盘这类 bug 的温床）。
3. 并行演进阻塞——改威科夫事件探测逻辑要动 2100 行文件，牵一发动全身。

**本设计的定位**：只做**行为保持的接缝拆分**（behavior-preserving seam split），不改任何函数逻辑、签名、返回结构。它是架构评审 P1「全局状态收敛」的**前置使能**——把持久化 helper 隔离进独立 submodule 后，后续 P1 收敛才能精准注入/打桩。

---

## 二、Goals / Non-Goals

**Goals**
- 每个单体 → 1 个**门面（facade）+ N 个内聚 submodule**，严格分层、无环。
- 外部导入面**零改动**：原模块退化为只做 re-export 的薄壳。
- 等价性闸门守护：拆分前后计算/渲染输出**逐字节等价**（canonical diff）。

**Non-Goals**
- ❌ 不改函数逻辑（这是 seam split，不是重构逻辑）。
- ❌ 不在此文档落地 P1「全局状态收敛」本身（只把状态 helper 隔离出来，为后续收敛铺路）。
- ❌ 不改任何 `def` 的入参/返回值形状。

---

## 三、方法论（复用 ADR-003b 已验证）

| 环节 | 做法 | 先例 |
|------|------|------|
| **抽取** | `ast.get_source_segment` 按**函数名**精确提取，**禁止** sed/行号区间切片（行号偏移是 D 类 bug 来源） | `scripts/_extract_report_builder.py` |
| **门面** | 原文件保留文件名，内容改为 `from .submodule import (...)` 并 re-export 全部公开名 | ADR-003b `report_builder.py` → `report_presentation.py` |
| **等价闸门** | 离线确定性桩下捕获输出 → canonical JSON（sort_keys + 日期掩码）diff；全全局改写走 `monkeypatch.setattr` | `test_report_render_equivalence.py` + `scripts/_render_eq_capture.py` + `docs/designs/p3-golden-diff-gate.md` |
| **命名陷阱** | 新 submodule 名必须 glob 校验不与已追踪模块/包冲突（曾踩 `report_renderer/` 包同名冲突） | ADR-003b §命名陷阱 |

**已预检命名冲突**（全部 OK，无 `*.py` 也无同名目录）：
`wyckoff_events` / `wyckoff_phase` / `chan_geometry` / `chan_structure` / `stage_state` / `stage_detect` / `stage_stops` / `stage_position`。

---

## 四、接缝设计（逐文件）

> 行号取自 `wc -l` + `grep '^(def|class )'`，作为**切割草图**；实现时用 AST 按函数名提取，不依赖行号。
> 依赖方向一律 **facade → 上层 submodule → 下层 submodule**，下层为叶子，**禁止回边**。

### 4.1 `wyckoff_core.py`（2115 → facade + 2 submodule）

| 新模块 | 行区间（草图） | 函数组 | 依赖 |
|--------|---------------|--------|------|
| `wyckoff_events.py` | 114–1293 | 全部事件探测器 `_detect_*`（`_detect_buying_climax`/`_detect_selling_climax`/`_detect_sign_of_weakness`/`_detect_spring`/`_detect_upthrust`/`_detect_volume_divergence`/`_detect_ar`/`_detect_sos`/`_detect_st`/`_detect_lps`/`_detect_lpsy`/`_detect_effort_vs_result`/`_detect_compression`/`_detect_trend_pullback`）+ 叶子 helper（`_spring_breach_level`/`_price_pos_pct`/`_is_bc_high_position`/`_is_frozen_board`/`_board_vol_scale`/`_is_trading_range`/`_compute_dynamic_support`） | 无（叶子） |
| `wyckoff_phase.py` | 1293–1606 | 相位状态机：`_scan_for_signal` / `_detect_phase` / `_phase_key` / `_load_phase_state` / `_save_phase_state` / `_transition_phase` | → `wyckoff_events` |
| `wyckoff_core.py`（facade） | 1606–2115 | 公开策略 API：`wyckoff_analysis` / `wyckoff_strategy` / `wyckoff_strategy_midline` / `calculate_wyckoff_score` / `format_wyckoff_oneline` + 全量 re-export | → `wyckoff_phase` + `wyckoff_events` |

**关键点**：写盘副作用 `_save_phase_state` 收口进 `wyckoff_phase` —— 这正是 D1/D3 类 bug 的隔离点，为后续 P1 收敛打桩留口。

**Facade 必须 re-export 的公开名**（来自外部 import 扫描）：
`format_wyckoff_oneline`、`wyckoff_strategy`、`wyckoff_strategy_midline`、`wyckoff_analysis`、`calculate_wyckoff_score`，以及测试可能引用的 `_detect_phase` / `_transition_phase`。

---

### 4.2 `chan_core.py`（2216 → facade + 2 submodule，可选 3）

| 新模块 | 行区间（草图） | 函数组 | 依赖 |
|--------|---------------|--------|------|
| `chan_geometry.py` | 10–805 | 几何构建层：`unwrap_chan` / `_calc_macd` / `handle_inclusion` / `find_fractions` / `_aggregate_bars` / `_higher_level_trend` / `build_strokes` / `_valid_strokes` / `_merge_char_element` / `build_segments` / `_merge_zones` / `build_zones` / `_has_entry_exit_segments` / `_detect_unilateral` | 无（叶子） |
| `chan_structure.py` | 840–1664 | 结构分类 + 置信 + 买卖点 + 背离：`_structure_conf_thresholds` / `_structure_confidence` / `classify_structure` / `_stroke_*` / `_check_macd_for_2nd_*` / `_zone_last_end_index` / `detect_buy_points` / `detect_sell_points` / `detect_divergence` | → `chan_geometry` |
| `chan_core.py`（facade） | 1664–2216 | 公开引擎 API：`_chanlun_compute` / `chanlun_analysis` / `ChanlunEngine` / `_chan_json_default` / `_chan_type_canonical` / `chanlun_strategy` / `chanlun_strategy_midline` / `format_chanlun_theory_line` + 全量 re-export | → `chan_structure` + `chan_geometry` |

**可选第 3 个 submodule `chan_points.py`**：若实现时发现 `detect_buy_points`（1232–1414）+ `detect_sell_points`（1414–1577，约 345 行）与 `chan_structure` 的其余部分无强耦合，可单独拆出。→ **待批准项**（见 §八）。

**Facade 必须 re-export 的公开名**（来自外部 import 扫描）：
`unwrap_chan`、`ChanlunEngine`、`format_chanlun_theory_line`、`chanlun_strategy`、`chanlun_strategy_midline`、`chanlun_analysis`，以及测试/内部引用的 `build_strokes` / `build_segments` / `build_zones` / `classify_structure` / `detect_buy_points` / `detect_sell_points` / `detect_divergence`。

---

### 4.3 `stage_positioning.py`（2368 → facade + 4 submodule，轮辐结构）

| 新模块 | 行区间（草图） | 函数组 | 依赖 |
|--------|---------------|--------|------|
| `stage_state.py`（叶子） | 44–223 | 状态持久化 + 组合相关：`calc_portfolio_correlation` / `_load_stage_state` / `_save_stage_state` | 无（叶子，读写 `~/.trader/stage_state.json` / 组合文件） |
| `stage_detect.py` | 224–1230 | 阶段探测引擎：`_bearish_alignment` / `_assess_volume_price` / `_detect_main_force_stage` / `_volume_price_confirm` / `_downgrade_stage` / `_upgrade_stage` / `_detect_major_stage` / `_detect_short_term_momentum` / `_layer1..4_*` / `compute_position_with_env` / `assess_stage` / `action_for_holding_state` | → `stage_state` |
| `stage_stops.py` | 1230–1692 | 止损/退出：`compute_stop_losses` / `compute_exit_plan` / `compute_stage_stop` / `check_time_stop` / `compute_stop_summary` | → `stage_state`（按需） |
| `stage_position.py` | 1692–2368 | 持仓状态评估 + 打分 + 止盈：`evaluate_position_state` / `_calc_pullback_add_score` / `_calc_reentry_score` / `_calc_rally_reduce_score` / `_assess_resistance_strength` / `_make_position_state` / `_empty_position_state` / `compute_conditional_take_profit` / `compute_take_profit` | → `stage_state`（save） |
| `stage_positioning.py`（facade） | — | 全量 re-export 上述四者 | → 四 submodule |

**轮辐约束**：`stage_state` 是唯一叶子；`detect`/`stops`/`position` 都只依赖 `stage_state`，彼此**不直接互调**。若实现时发现某两群之间存在**真实互调**（如 `assess_stage` 调 `compute_stop_losses`），则该对函数必须并入**同一个** submodule 以消除回边——这是实现时的发现步骤，见 §七 任务 0。

**Facade 必须 re-export 的公开名**（来自外部 import 扫描）：
`assess_stage` / `compute_exit_plan` / `compute_stage_stop` / `check_time_stop` / `evaluate_position_state` / `_detect_major_stage` / `compute_position_with_env` / `action_for_holding_state` / `compute_stop_losses` / `compute_stop_summary` / `compute_conditional_take_profit` / `compute_take_profit` / `calc_portfolio_correlation`。

> ⚠️ `_detect_major_stage` 是下划线私有名但被 `report_presentation` 跨模块 import —— **必须继续 re-export**（不要因为下划线就丢弃）。

---

## 五、依赖方向与导入契约（全局）

```
stage_positioning.py  ──re-export──▶  stage_detect / stage_stops / stage_position / stage_state
chan_core.py          ──re-export──▶  chan_structure / chan_geometry
wyckoff_core.py       ──re-export──▶  wyckoff_phase / wyckoff_events

外部调用方（report_presentation / report_builder / report_core / fusion_core /
decision_core / plugin_registry / realtime_chan / cache_utils / midline_structure /
conclusion_block / structure_core / plugins/*）──▶  只认原模块名，import 行零改动
```

- 包内新 submodule 一律用**相对 import**（`from .wyckoff_events import ...`），避免与同名顶层模块歧义。
- 若 submodule 间确需共享常量（如 `_logger`、配置常量），**各 submodule 各持一份**（ADR-003b 已验证无害），不引入跨 submodule 的可变全局。

---

## 六、等价性闸门（复用 p3-golden-diff-gate）

每个文件拆完，必须过一道**计算等价闸门**（与报告层 render equivalence 同机制，但比对的是**计算 dict** 而非渲染 md）：

1. **捕获脚本**：新增 `scripts/_capture_<module>_split_baseline.py`（镜像 `_render_eq_capture.py`），在**全离线确定性桩**下（bars 取自固定 fixture；`monkeypatch.setattr` 打掉 `_save_phase_state`/`_save_stage_state`/网络 fetcher）跑：
   - `wyckoff_analysis(...)` / `calculate_wyckoff_score(...)`
   - `chanlun_analysis(...)` / `ChanlunEngine(...).analyze(...)`
   - `assess_stage(...)` / `evaluate_position_state(...)`
   输出经 `json.dumps(obj, sort_keys=True, default=<date-mask>)` 落盘为 baseline。
2. **测试**：新增 `tests/test_<module>_split_equivalence.py`，复跑同一桩，断言 post-split 输出 `==` baseline（结构化 diff，非 md5）。
3. **入 CI 门禁**：把 3 个 equivalence 测试加进 `scripts/run-gate-tests.sh` 的 `TESTS` 数组（当前基线 68 passed / 14 项）。
4. **桩纪律**：所有全局改写（env / 客户端 / 文件写）必经 `monkeypatch.setattr`，否则会污染后续测试（首版裸赋值踩坑已记 ADR-003b）。

---

## 七、实施任务骨架（每个文件一轮，独立 commit）

> 以下为 bite-sized 骨架，完整 plan 经批准后再展开为带失败测试/实现的 TDD 步骤。

**Task 0（每文件先做）**：AST 扫描原文件内部跨群调用，确认 §四 的分组无真实环；若有环，合并相关群（更新本设计文档的分组表）。

**Task 1 · wyckoff_core**：建 `wyckoff_events.py` + `wyckoff_phase.py` → 原文件改 facade re-export → 加 `test_wyckoff_split_equivalence.py` → gate 绿 → commit `refactor(p1): split wyckoff_core into events+phase`.

**Task 2 · chan_core**：建 `chan_geometry.py` + `chan_structure.py`[+可选 `chan_points.py`] → facade → equivalence 测试 → gate 绿 → commit.

**Task 3 · stage_positioning**：建 `stage_state.py` + `stage_detect.py` + `stage_stops.py` + `stage_position.py` → facade → equivalence 测试 → gate 绿 → commit.

每轮 commit 顺序：**抽 submodule → 替换 facade → 加 equivalence 测试 → 跑全 gate 绿**。

---

## 八、Risks / Mitigations

| 风险 | 缓解 |
|------|------|
| 内部跨群互调导致环 | Task 0 预扫；有环则合并群（§四 已标注 stage 轮辐约束） |
| 下划线私有名被外部 import（`_detect_major_stage`） | facade 继续 re-export，不丢名 |
| 模块级全局（`_logger`/缓存）拆分后丢失或重复 | 各 submodule 各持一份，无跨 submodule 可变全局 |
| 测试文件直接 import 内部名 | facade re-export 覆盖；等价测试独立于单测 |
| `ChanlunEngine` 是有状态类，路径变更影响 `realtime_chan`/`cache_utils` | facade re-export `ChanlunEngine`，import 路径不变 |
| 行号草图偏移 | 实现用 AST 按函数名提取，不依赖行号 |

---

## 九、Consequences

- ✅ 三个单体降至 ≤ ~800 行 submodule，单测/演进成本骤降。
- ✅ 写盘副作用（`_save_phase_state` / `_save_stage_state`）被隔离进 `wyckoff_phase` / `stage_state`，为 P1 全局状态收敛提供精准打桩点。
- ✅ 外部导入面零改动，下游 skill / fusion / 报告层无感。
- ⚠️ facade 文件仍存在（薄壳），属可接受的中间态（同 ADR-003b）。

---

## 十、待批准项（Open Questions）

1. `chan_core` 是否启用可选第 3 个 `chan_points.py`？（推荐：先 2 模块，若 `detect_buy/sell_points` 与 structure 其余部分解耦再拆）
2. `stage_position` 是否把止盈（`compute_*_take_profit`）单独成 `stage_profit.py`？（当前设计并入 `stage_position`，保持 4 submodule）
3. 实施顺序是否同意 wyckoff → chan → stage（推荐：wyckoff 分层最干净且自带活 bug，最适合先验证 facade 机制）？

> 批准后我将展开为完整 TDD 实施 plan（`docs/plans/`）或直接进入实现。
