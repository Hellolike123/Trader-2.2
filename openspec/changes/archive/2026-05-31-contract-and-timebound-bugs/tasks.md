## 1. 交易日历

- [x] 1.1 新建 `02-共享模块-shared/trader_shared/trading_calendar.py`，定义 `CHINA_HOLIDAYS_2025_2027` set 和 `is_trading_day(date)` 函数
- [x] 1.2 `light_data.py` — 修改 `is_trading_time()`，在周末检查之后增加 `is_trading_day(today)` 检查
- [x] 1.3 `config.py` — 增加注释提醒每年年底更新节假日集合
- [x] 1.4 添加测试：验证节假日返回 False、普通工作日返回 True

## 2. 数据新鲜度标记

- [x] 2.1 `light_data.py` — `fetch_quote()` 返回值增加 `data_freshness` 字段，非交易时段设为 "stale"
- [x] 2.2 `light_data.py` — `load_market_snapshot()` 返回值增加 `data_freshness` 字段
- [x] 2.3 `market_env.py` — `assess()` 返回值增加 `data_freshness` 字段，非交易时段设为 "stale"
- [x] 2.4 添加测试：验证交易时段返回 "live"，非交易时段返回 "stale"

## 3. 零价格防护

- [x] 3.1 `decision_core.py:status_layers()` — 入口增加 `if current <= 0` 前置检查，返回 "数据不足" 状态
- [x] 3.2 添加测试：验证 current=0 时返回 "数据不足"

## 4. T0 Monitor 收盘后休眠

- [x] 4.1 `monitor.py:run_monitor()` — 在主循环中增加收盘检测，收盘后计算到下一个交易时段的 sleep 时长
- [x] 4.2 利用新增的 `is_trading_day()` 判断明天是否交易日，决定 sleep 到明天 9:25 还是下周一 9:25
- [x] 4.3 添加测试：验证 15:05 时 sleep_until_next_interval 返回正确的秒数

## 5. 降级 Fusion Map

- [x] 5.1 `t0_candidate_core.py` — 将 `decision_core.py` 中的 `_FUSION_STATUS_MAP` 完整复制到 fallback 路径
- [x] 5.2 添加测试：验证降级路径下 fusion override 正常映射
