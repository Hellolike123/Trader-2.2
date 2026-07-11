# PRD — 缠论引擎 N1 加固 + Phase 2 接入（T0 实时 / cache warm）

## 目标
在 Phase 1（`d77b07b` ChanlunEngine）基础上完成两项遗留工作：
1. **N1 加固**：还原 `_higher_level_trend` 入参为原始 `bars`，实现字节级 100% 兼容
2. **Phase 2 接入**：`ChanlunEngine` 接入 `cache warm`（预建状态）+ T0 盯盘（实时缠论，opt-in 默认关）

完整规格见 `.mimocode/plans/1783685710500-chanlun-phase2.md`（Part A/B/C 三段）。

## 范围
- Part A（chan_core.py）：`_chanlun_compute` 加 `raw_bars`；`chanlun_analysis` 传 `raw_bars=bars`；`get_analysis` line 1867 用 `self._raw`
- Part B（cache_utils.py）：新增 `warm_chanlun_states()`，`warm_pool_cache` 末尾调用合并
- Part C（realtime_chan.py 新模块 + monitor.py）：`T0_REALTIME_CHAN=1` 开启时实时缠论 diff alert，默认关、零改动现有路径

## 不在范围
- 下游消费方（review_core / backtest / run_analysis / fusion / decision / structure）零改动
- 工作树中其他任务的未提交文件（fund_flow_data.py / fusion_regime.py / test_fusion_core.py / test_main_force.py）严禁触碰

## 验收门槛（优先级）
1. **N1 兼容**：批量 chunk 回退路径输出与预重构 `_higher_level_trend(bars)` 口径一致（新增单测）
2. **cache warm**：pool 股票生成 `CHANLUN_STATE_DIR/{code}.json`，load 一致；warm 原计数不变
3. **T0 隔离**：`T0_REALTIME_CHAN=1` 跨 tick diff 触发 alert；未设时 `run_once` 行为零变化
4. **无回归**：test_chan_core / test_cache_utils / test_realtime_chan / test_t0_contract / test_fusion_core / test_structure_core 全绿

## 核心约束
- Part C 所有改动必须在 `os.environ.get("T0_REALTIME_CHAN") == "1"` 分支内，默认跳过——这是硬性隔离约束
- 复用纯函数与 `_chanlun_compute`，不重实现缠论算法
- Part B/C 失败必须容错（try/except），绝不阻断主流程
