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
