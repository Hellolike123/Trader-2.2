# Trader3.0 项目长期记忆

## 代码位置与提交约定（关键）

- **规范源码**在仓库：`02-共享模块-shared/trader_shared/`（trader_shared 包）与 `01-功能包-packages/trader/scripts/run_analysis.py`（打包副本）。仓库比旧 skill 副本更新，含 ma250 年线警告、T+1 隔离锁、重构后的 📍决策渲染等。
- **⚠️ skill 有 TWO 安装位，修复必须两边都打**（07-08 踩坑教训）：
  - `~/.workbuddy/skills/trader/` —— 本 WorkBuddy 会话 agent 加载的副本。
  - `~/.hermes/skills/trader/` —— 打包脚本 `pack_all.py` 的 `auto_install` 目标位，也是用户「另一个 agent」实际跑 skill 的位置。
  - 07-07 只装了 workbuddy 那份 → hermes 仍 stale（带 batch-8 旧 bug `from mootdx.quotes import Q`），导致 agent 又报 `data_status=partial`。07-08 已把 4 个 zip 干净安装到 hermes，两副本现 digest 一致 (`02c554c66579b09d`) 且关键文件 diff 无差异。
  - **正确流程**：仓库改 → commit → `pack_all.py --no-install` 出 zip → 把 zip **同时**干净安装到两个安装位（各先备份）。或 `pack_all.py`（无 --no-install）只装 hermes，再手动补 workbuddy。
  - `trader_test`（`~/.hermes/skills/trader_test/trader`，06-09）仍是旧 `import Q` 测试副本，未修；若 agent 用它需另修。
- **⚠️ 改完 skill 副本后提交，必须把改动回灌到仓库源码，且禁止整文件覆盖分叉文件**（会丢仓库更新功能）：
  - 纯新增/严格超集文件 → 整文件复制（先 `diff` 确认 repo 独有行=0）；
  - 已分叉文件（momentum_plugin 的 analyze 多 quote 参数、run_analysis 含 ma250/T+1/决策重构）→ 精合，保留 repo 更新部分再叠加特性。
- 验证优先：仓库上下文实跑 `final_report.py` + 跑 `test_fusion_integration.py` 防回归。
- 提交落在 Trader3.0 仓库，**默认不推送**（用户未要求时不 push）。

## 决策框架（勿破坏）

- 融合层三评委：chan / momentum / wyckoff + HMM regime 动态权重（`get_regime_weights` + `_apply_main_force_weights`）。新增指标**不要**当第 4 个固定权重评委。
- 展示型指标（如 Supertrend/VWAP）走 `plugins/` + `display_only=True`，`merge_decisions_from_plugins` 只把 chan/mom/wyk 喂融合 → 天然污染不到 `weighted_score`。
- 止损以 `structure_core` ATR trailing + `stage_positioning` 三者取高（只紧不松）为准，新增趋势带只标「参考」不替换。

## 测试

- 单测 venv：`/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest`（已装 pytest）。
- 跑测试设 `PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts` 才能 import `trader_shared`。
- `test_contract.py` 有 3 项既有失败（契约/测试漂移），非改动引入，勿盲目修测试对齐。

## ⚠️ 模块命名冲突陷阱（2026-07-13 踩坑）
- `trader_shared/report_renderer/` 是**已被追踪的包**（另一套渲染实验：render_single/render_short_midline/render_pool_summary/render_backtest；`01-功能包-packages/trader/tests/test_report_renderer.py` 在用）。**切勿新建同名 `report_renderer.py` 模块**——同名目录会抢先被当包，导致 `from .report_renderer import ...` → ImportError。
- ADR-003b 拆出的展示层已命名为 **`trader_shared/report_presentation.py`**（避开冲突）。以后新模块别叫 `report_renderer`。

## 大文件拆分方法论（ADR-003b 验证有效）
- 拆大文件（如 report_builder 2870 行）用 **AST 精确提取**（`ast.get_source_segment` 按函数名分类），**不要**用 sed/行号区间切片——行号易错（混合带、函数边界偏移）。
- 等价性闸门模式：分裂前后各跑一次全离线确定性 mock 桩（覆盖所有网络泄漏点：set_provider/TencentFetcher/get_env_for_skill/fetch_fund_flow_cached/tushare_client.get_client/chip_data.get_cyq_perf），日期掩码后 diff/md5，证明行为零回归。
- 测试桩内**所有全局改写必须走 `monkeypatch.setattr`**（自动还原），否则污染后续测试（如 fetcher 全局状态测试）。裸赋值 `_fetchers.TencentFetcher = MockFetcher` 不还原会踩坑。
