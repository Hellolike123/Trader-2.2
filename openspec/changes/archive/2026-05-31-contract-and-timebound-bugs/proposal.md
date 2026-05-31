## Why

跨模块契约和时间边界审计发现 16 个问题（排除用户自行关注的解禁否决）。核心问题是两个：系统没有中国股市节假日日历导致节假日假告警，以及非交易时段返回过期数据无 stale 标记。此外 current_price=0 时输出语义错误、T0 monitor 收盘后空转、降级安装时 fusion override 失效等问题也需要修复。

## What Changes

**第一批：时间边界（5 个）**
- 新增 `trading_calendar.py` — 中国股市节假日日历，`is_trading_time()` 增加节假日检查
- `light_data.py` — `fetch_quote()` / `load_market_snapshot()` 增加 `data_freshness` 字段（stale/live）
- `decision_core.py` — `status_layers()` 增加 `current <= 0` 前置检查，返回"数据不足"
- `market_env.py` — `assess()` 在非交易时段设置 `data_freshness="stale"`
- `monitor.py` — `run_monitor()` 收盘后进入长休眠而非持续空转

**第二批：跨模块契约（2 个）**
- `t0_candidate_core.py` — fallback 路径的 `_FUSION_STATUS_MAP` 从 `decision_core.py` 复制完整映射
- `structure_core.py` — 清理未被消费的输出 key 或标记为调试字段

## Capabilities

### New Capabilities

- `trading-calendar`: 中国股市交易日历 — 覆盖周末、节假日、交易时段判断，防止非交易时段触发假告警

### Modified Capabilities

（无）

## Impact

受影响文件：
- **新增** `02-共享模块-shared/trader_shared/trading_calendar.py`
- `02-共享模块-shared/trader_shared/light_data.py` — is_trading_time + data_freshness
- `02-共享模块-shared/trader_shared/decision_core.py` — current=0 前置检查
- `02-共享模块-shared/scripts/market_env.py` — stale 标记
- `01-功能包-packages/t0/scripts/monitor.py` — 收盘后长休眠
- `02-共享模块-shared/trader_shared/t0_candidate_core.py` — fusion map 补全

无 API 变更，无 breaking change。`data_freshness` 是新增字段，不影响现有消费者。
