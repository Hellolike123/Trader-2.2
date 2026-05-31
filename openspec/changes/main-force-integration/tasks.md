## 1. 接入主力引擎

- [x] 1.1 `run_analysis.py` — 在 `build_report()` 中导入 `fetch_fund_flow_cached`、`calc_fund_flow_features`、`detect_main_force_stage`
- [x] 1.2 `run_analysis.py` — 在获取 bars/quote 后调用 `fetch_fund_flow_cached(symbol)` 获取资金流向
- [x] 1.3 `run_analysis.py` — 调用 `calc_fund_flow_features(daily_flow, bars)` 计算特征
- [x] 1.4 `run_analysis.py` — 调用 `detect_main_force_stage(features, bars, chip_info, position_ratio)` 识别阶段
- [x] 1.5 `run_analysis.py` — 将 `main_force_env=mf_result["stage"]` 传入 `merge_decisions()`
- [x] 1.6 `run_analysis.py` — 将 `format_main_force_section(mf_result)` 加入报告输出
- [x] 1.7 `run_analysis.py` — 错误处理：API 失败时 `main_force_env="unknown"`，不影响主流程

## 2. 复盘输出

- [ ] 2.1 `review_core.py` — 在复盘模板中增加主力行为段落

## 3. 验证

- [x] 3.1 跑测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/ -q`（593 passed）
- [ ] 3.2 手动验证：`trader script --target 南网科技` 输出包含主力行为段落
