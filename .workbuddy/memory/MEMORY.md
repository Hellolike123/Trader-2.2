# Trader3.0 项目长期记忆

## 代码位置与提交约定（关键）

- **运行的代码**在 `~/.workbuddy/skills/trader/scripts/`（skill 副本），但它是**比仓库 HEAD 更旧**的副本。
- **规范源码**在仓库：`02-共享模块-shared/trader_shared/`（trader_shared 包）与 `01-功能包-packages/trader/scripts/run_analysis.py`（打包副本）。
- 仓库 `02-共享模块-shared/trader_shared/` 比 skill 副本**更新**，含 ma250 年线警告、T+1 隔离锁、重构后的 📍决策渲染等。
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
