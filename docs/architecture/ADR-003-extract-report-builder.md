# ADR-003: 把分析逻辑从 `run_analysis.py` 抽离为 `report_builder.py`

- **Status**: Accepted（已在 `refactor/trader-architecture` 分支执行并通过 golden 回归）
- **Branch**: `refactor/trader-architecture`（基于 `2bc3493`，ADR-001 已落地）
- **前置**: ADR-001（真库）已完成

---

## Context（问题动机）

架构评审把 `run_analysis.py`（原 3010 行）列为 P1 巨型 monolith：「混编编排 + 计算 + 渲染」。
下游技能（`trader` skill）只调用 `build_report()`，但整个分析+渲染逻辑挤在一个脚本里，
CLI 入口 `main()`/`parse_args()` 与领域逻辑纠缠，无法单独测试、组合或复用。

## 实测发现（关键）

抽离前我核了 `build_report` 的真实依赖闭包，**比"只搬 build_report"复杂得多**：

- `build_report` 不只调分析 helper（`determine_stage`/`structure_replay`/`ma_text`/`sync_report_with_data`/`numeric_values`/`price`/`pct`/`_get_kelly_data`/`_degraded_quote_report`/`today_text`），
- **还直接调渲染/信号 helper**：`volume_observation` / `_get_buy_label` / `action_text_for_scene` / `signal_max_total_pct` / `signal_risk_flags` / `upward_momentum_observation` / `_calc_volume_ratio_from_bars`。

也就是说 `build_report` 与"展示层"**并未分层**——它内联调用了渲染辅助函数。
若只搬 `build_report` 本身，会触发 `NameError`（golden 测试第一轮就抓到了 `volume_observation` 未定义）。

## Decision（决策）

把 **原 `run_analysis.py` 除 `main`/`parse_args`（CLI 入口）外的全部逻辑**整体搬入
`trader_shared/report_builder.py`；`run_analysis.py` 退化为 ~207 行的 **CLI 壳**：

- 头部 import 保留（sys.path 引导 + trader_shared 导入）
- 中间一行 `from trader_shared.report_builder import (...)` 再导出所有被渲染层/CLI 共用的函数
- 尾部仅留 `parse_args()` + `main()`

代码**逐行重定位、零改写**（由一次性切片脚本 `scripts/_extract_report_builder.py` 完成，附 git 历史），
因此行为 100% 等价于原文件——由 golden 行为测试守护。

## Consequences（后果）

- ✅ `run_analysis.py` 从 3010 行 → 207 行，纯 CLI 壳；核心逻辑进可独立导入的 `trader_shared` 真库
- ✅ 下游 skill 调用 `build_report` / `render_markdown` 不变（签名、返回结构一致）
- ✅ 打包后 `trader_shared/report_builder.py` 随库分发，`run_analysis.py` 仅 CLI 入口
- ⚠️ `report_builder.py` 仍有 2881 行——**本次只是"逻辑库 vs CLI"分层，未再做领域/展示内部分层**
- 📌 **建议后续（非本次范围）**：把 `report_builder.py` 进一步拆为
  `report_builder`（领域：`build_report` + 分析 helper）与 `report_renderer`（展示：`render_markdown` + 信号视图 + 共用 helper 如 `volume_observation`/`signal_max_total_pct`），
  消除 domain→presentation 的调用方向，实现真正的展示/领域分离。

## 验证

- `py_compile` 两文件通过
- `trader_shared.report_builder` 与 `run_analysis` 均可导入，`build_report`/`render_markdown`/`main` 均 callable
- `tests/test_build_report_golden.py`：**1 passed**（守门：report 形状 / `weighted_score` 范围 / 中线 key / 5 策略全调用）

---

## 后续：domain/presentation 拆分（ADR-003b，已执行）

把 `report_builder.py` 进一步拆为**领域层** `report_builder.py` 与**展示层**
`report_presentation.py`，消除 domain→presentation 的调用方向，实现真正的展示/领域分离。

### 分类（按函数名，AST 精确提取，非行号切片）
- **领域层 `report_builder.py`**（~1635 行）：`build_report` / `_degraded_quote_report` /
  `determine_stage` / `structure_replay` / `sync_report_with_data` / `_calc_volume_ratio_from_bars`
  + 模块常量 `_logger` / `SCRIPT_DIR`
- **展示层 `report_presentation.py`**（~1304 行）：`render_markdown` + 全部视图/格式 helper
  （`today_text`/`_signal_type_label`/`_fusion_breakdown`/`price`/`pct`/`numeric_values`/`ma_text`/
  `chunks`/`short_date`/`volume_observation`/`upward_momentum_observation`/`_get_buy_label`/
  `signal_state`/`signal_max_total_pct`/`signal_risk_flags`/`structure_view`/`volume_view`/
  `generate_alert`/`build_watch_alert`/`action_text_for_scene`）+ 两个展示支撑 fetcher
  `_get_kelly_data` / `_get_major_stage`（**仅被展示函数调用**，不被 `build_report` 调用）+ 模块常量
  `_kelly_cache` / `CONTRACT_VERSION` / `_SIGNAL_TYPE_LABELS`

### 关键设计点
- **`build_report` 仍需内联调用 4 个展示 helper**（`volume_observation`/`volume_view`/
  `upward_momentum_observation`/`structure_view`）→ `report_builder.py` 底部
  `from .report_presentation import (...)` 同时**承担 re-export 职责**，使
  `run_analysis.py` 的 31 名 import 不受影响（API 稳定）。
- **依赖方向严格 builder → presentation**，无循环导入（展示层不反 import 领域层）。
- 模块常量按使用方归属：被展示函数用的 `_kelly_cache`/`CONTRACT_VERSION`/`_SIGNAL_TYPE_LABELS`
  随迁展示层；`_logger` 两份各持一份（无害）。

### ⚠️ 命名陷阱（重要）
仓库已存在一个**被追踪的** `trader_shared/report_renderer/` **包**（另一套渲染实验：
`render_single`/`render_short_midline`/`render_pool_summary`/`render_backtest`，
`01-功能包-packages/trader/tests/test_report_renderer.py` 在用）。它与本次拆分的展示层**同名冲突**：
同名目录会抢先被当成包，导致 `from .report_renderer import ...` 报
`ImportError: cannot import name ...`。**本次新模块命名为 `report_presentation.py` 避开了冲突**，
`report_renderer/` 包保持原样不动。

### 等价性闸门（防行为退化）
- `scripts/_render_eq_capture.py`：在**全离线确定性 mock 桩**下跑 `build_report`+`render_markdown`，
  日期掩码后落盘（桩覆盖 6 个网络泄漏点：`set_provider`/`TencentFetcher`/`get_env_for_skill`/
  `fetch_fund_flow_cached`/`tushare_client.get_client`/`chip_data.get_cyq_perf`）。
- 分裂前(2870行)与分裂后(1635+1304行)渲染输出 **md5 完全一致** → 拆分行为保持。
- `tests/test_report_render_equivalence.py`：复跑同一桩，断言输出 == `tests/fixtures/report_render_baseline.txt`。
- 测试隔离：桩内所有全局改写必须经 `monkeypatch.setattr`（自动还原），否则会污染后续
  `test_arch_refactoring` 的 fetcher 全局状态测试（首版裸赋值 `_fetchers.TencentFetcher = MockFetcher`
  未还原即踩此坑，已修）。

### Consequences
- ✅ `report_builder.py` 2870 → 1635 行；纯领域编排，展示逻辑独立可单测
- ✅ `run_analysis.py` 31 名 import 经 re-export 零改动
- ✅ 全测试 61 passed（imports smoke + golden + ADR-002 equivalence + render equivalence + arch/registry + indicator + 旧 report_renderer 包）
- ⚠️ 仍非"完美"分层：`build_report` 仍内联调 4 个展示 helper（靠 re-export 桥接，可接受）
