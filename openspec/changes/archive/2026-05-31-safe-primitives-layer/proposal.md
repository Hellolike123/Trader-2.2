## Why

全量扫描发现 56 个 bug，其中 25+ 个属于同一类模式：dict.get() 值为 None 时崩溃、`or 0` 吞合法零值、max() 空序列返回哨兵值。这些模式在 7 个文件中重复出现，每个文件各自处理，写法不一致。逐个修复只能解决当前问题，新增代码仍然会犯同样的错。需要在架构层面根治。

## What Changes

**新增 `trader_shared/safe_cast.py`** — 5 个安全原语函数，全局统一处理 None/空序列/类型转换：

- `safe_float(d, key, default=0.0)` — 从 dict 安全提取浮点值，None→default，不吞合法 0.0
- `safe_dict(d, key)` — 从 dict 安全提取子 dict，None→{}，保证返回 dict
- `safe_max(iterable, default=None)` — 空序列返回 default，不用 -1 哨兵
- `safe_min(iterable, default=None)` — 同上
- `require_positive(value, name="value")` — ≤0 或 None 返回 None

**新增 `trader_shared/trading_context.py`** — 集中式时间/状态感知：

- `is_trading_day(date)` — 节假日日历 + 周末判断
- `is_trading_time()` — 交易时段判断（含节假日）
- `current_session()` — 返回 盘前/盘中/午休/盘后/非交易日
- `data_freshness()` — 返回 live/stale

**全局替换** — 用安全原语替换所有脆弱写法（约 25 处）。

## Capabilities

### New Capabilities

- `safe-cast`: 统一数据安全提取原语 — 定义 safe_float/safe_dict/safe_max 等函数的语义和全局使用规范
- `trading-context`: 集中式交易时间感知 — 统一节假日日历、交易时段、数据新鲜度判断

### Modified Capabilities

（无）

## Impact

新增文件：
- `02-共享模块-shared/trader_shared/safe_cast.py`
- `02-共享模块-shared/trader_shared/trading_context.py`

受影响文件（全局替换）：
- `02-共享模块-shared/trader_shared/structure_core.py` — safe_float 替换 float(get)
- `02-共享模块-shared/trader_shared/decision_core.py` — safe_float/safe_dict 替换 or 模式
- `02-共享模块-shared/trader_shared/t0_candidate_core.py` — safe_float 替换 to_float or
- `02-共享模块-shared/trader_shared/fusion_core.py` — safe_float 替换 float(get)
- `02-共享模块-shared/trader_shared/momentum_core.py` — safe_max 替换 max(default=-1)
- `02-共享模块-shared/trader_shared/big_order.py` — safe_float 替换 to_float or
- `02-共享模块-shared/trader_shared/light_data.py` — trading_context 替换 is_trading_time
- `02-共享模块-shared/scripts/market_env.py` — trading_context 替换手动检查
- `01-功能包-packages/t0/scripts/monitor.py` — trading_context 替换手动检查
- `01-功能包-packages/t0/scripts/price_point_engine.py` — safe_max 替换 max(default=-1)

无 API 变更，无 breaking change。安全原语是纯新增，替换是内部实现细节。
