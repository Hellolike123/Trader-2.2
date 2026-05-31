## 1. 安全原语层

- [x] 1.1 新建 `02-共享模块-shared/trader_shared/safe_cast.py`，实现 `safe_float`、`safe_dict`、`safe_max`、`safe_min`、`require_positive` 五个函数
- [x] 1.2 为 safe_cast.py 编写完整测试 `02-共享模块-shared/tests/test_safe_cast.py`，覆盖 None/零值/正常值/类型错误/空序列等场景
- [x] 1.3 `structure_core.py` — 将所有 `float(dict.get("key", 0))` 替换为 `safe_float(dict, "key")`（约 5 处：line 304/319/332/386/452）
- [x] 1.4 `decision_core.py` — 将 `or float("inf")` 和 `or current` 等模式替换为 safe_float/safe_dict（约 4 处：line 269/448/452）
- [x] 1.5 `t0_candidate_core.py` — 将 `to_float(x) or 0.0` 替换为 `safe_float({"v": x}, "v")`（约 3 处：line 179/194/262）
- [x] 1.6 `fusion_core.py` — 将 `float(dict.get("confidence", 0))` 替换为 safe_float（约 3 处）
- [x] 1.7 `big_order.py` — 将 `to_float(x) or 0.0` 替换为 safe_float（约 1 处：line 162）
- [x] 1.8 `price_point_engine.py` — 将 `max(bb.keys(), default=-1)` 替换为 `safe_max(bb.keys())`（约 1 处：line 296）
- [x] 1.9 `monitor.py` — 将 `plan.get("buy", {})` 替换为 `safe_dict(plan, "buy")`（约 2 处：line 393-394）
- [x] 1.10 跑全量测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/ && python3 -m pytest 01-功能包-packages/*/tests/`

## 2. 交易时间感知层

- [x] 2.1 新建 `02-共享模块-shared/trader_shared/trading_context.py`，实现 `is_trading_day`、`is_trading_time`、`current_session`、`data_freshness` 四个函数，内含 2025-2027 节假日硬编码
- [x] 2.2 `config.py` — 增加注释提醒每年年底更新节假日集合
- [x] 2.3 `light_data.py` — 将 `is_trading_time()` 改为调用 `trading_context.is_trading_time()`，保持签名兼容
- [x] 2.4 `market_env.py` — `assess()` 返回值增加 `data_freshness` 字段，非交易时段设为 "stale"
- [x] 2.5 `light_data.py` — `fetch_quote()` 返回值增加 `data_freshness` 字段
- [x] 2.6 `monitor.py:run_monitor()` — 在主循环中增加收盘检测，收盘后 sleep 到下一个交易时段
- [x] 2.7 为 trading_context.py 编写完整测试 `02-共享模块-shared/tests/test_trading_context.py`，覆盖节假日/周末/交易时段/午休/盘后
- [x] 2.8 跑全量测试确认无回归
