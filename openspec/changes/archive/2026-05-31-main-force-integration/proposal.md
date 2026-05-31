## Why

主力行为引擎（main_force.py）已实现并有 23 个测试覆盖，但从未接入生产管线。`run_analysis.py` 调用 `merge_decisions()` 时未传 `main_force_env` 参数，导致 `_apply_main_force_weights()` 是死代码。需要将主力引擎接入分析流程，使其成为第三个环境修正因子（与 market_env、hmm_regime 并列）。

## What Changes

- `run_analysis.py` — 在获取 bars/quote 后调用 `fetch_fund_flow()` + `calc_fund_flow_features()` + `detect_main_force_stage()`，将 `main_force_env` 传入 `merge_decisions()`
- `run_analysis.py` — 将主力行为结果加入报告输出（调用 `format_main_force_section()`）
- `review_core.py` — 复盘输出中增加主力行为段落
- `fund_flow_data.py` — 将 `import requests` 改为 `urllib.request`（在 main-force-bugfix 中修复，这里依赖那个修复）

## Capabilities

### New Capabilities

（无，这是已有功能的接入）

### Modified Capabilities

- `mainforce-fusion`: 主力行为作为环境因子接入融合层

## Impact

受影响文件：
- `01-功能包-packages/trader/scripts/run_analysis.py` — 主入口接入
- `01-功能包-packages/review/scripts/review_core.py` — 复盘输出
- `02-共享模块-shared/trader_shared/fund_flow_data.py` — 依赖 requests→urllib 修复

无 API 变更，无 breaking change。
