## Why

缓存层和信号层存在 5 个运维层面的问题：`cache_utils.py` 无文件锁导致并发写损坏、缓存过期后 API 挂掉时完全没数据、`signals.jsonl` 无轮转机制导致文件无限增长、两套读写逻辑（`signal_store` vs `DataManager`）行为不一致、坏行静默丢弃无诊断。这些问题在单进程日常使用中暂时不暴露，但在多进程并发、API 故障、长期运行等场景下会导致数据损坏或丢失。

## What Changes

**P0：增强 cache_utils.py（1 天）**
- `set_cached()` 增加 `fcntl.flock` 文件锁，防止并发写损坏
- `.tmp` 文件名改为唯一（含 PID），防止多进程冲突
- `get_cached()` 返回 `CacheResult` 包装器，支持 stale-while-revalidate

**P1：统一 signal lifecycle（半天）**
- 合并 `signal_store._read_store()` 和 `DataManager.load_signals()` 为统一路径
- 坏行计数 + 诊断信息（哪一行、什么原因、什么时候）
- `signals.jsonl` 超过 90 天自动归档到 `signals-archive-YYYYQ#.jsonl`

## Capabilities

### New Capabilities

- `cache-resilience`: 缓存弹性层 — 文件锁 + stale-while-revalidate + 唯一 tmp 文件名
- `signal-lifecycle`: 信号生命周期管理 — 统一读写路径 + 坏行诊断 + 自动轮转

### Modified Capabilities

（无）

## Impact

受影响文件：
- `02-共享模块-shared/trader_shared/cache_utils.py` — 缓存层增强
- `02-共享模块-shared/trader_shared/signal_store.py` — 统一读写路径
- `02-共享模块-shared/trader_shared/data_manager.py` — 合并到 signal_store

新增数据结构：
- `CacheResult` dataclass（data, stale, age_seconds, source）

无 API 变更，`get_cached()` 返回类型从 `Any | None` 变为 `CacheResult | None`，但现有调用点只需加 `.data` 即可兼容。
