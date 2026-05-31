## 1. 缓存层增强（cache_utils.py）

- [x] 1.1 定义 `CacheResult` dataclass（data, stale, age_seconds, source）
- [x] 1.2 修改 `set_cached()` — 增加 `fcntl.flock(LOCK_EX)` 排他锁，`.tmp` 文件名加 PID 后缀
- [x] 1.3 修改 `get_cached()` — TTL 过期后仍读取数据，返回 `CacheResult(stale=True)` 而非 None
- [x] 1.4 修改 `get_cached()` — 缓存命中返回 `CacheResult(stale=False)`，未命中返回 None
- [x] 1.5 添加兼容辅助函数 `get_cached_data()` — 返回 `CacheResult.data` 或 None，方便调用方迁移
- [x] 1.6 适配所有 `get_cached()` 调用点（约 5 处）— 改用 `get_cached_data()` 或直接读 `.data`
- [x] 1.7 为 cache_utils.py 编写测试 — 覆盖命中/未命中/stale/损坏/并发写场景

## 2. 信号生命周期统一（signal_store.py + data_manager.py）

- [x] 2.1 修改 `DataManager.load_signals()` — 委托给 `signal_store._read_store()`，保持返回格式
- [x] 2.2 统一坏行诊断 — `signal_store` 的 `_bad_line_count` / `_bad_line_last_reason` 作为唯一来源
- [x] 2.3 在 `signal_store.py` 中实现轮转逻辑 — `append_signal()` 前检查文件大小，超过 10MB 时归档
- [x] 2.4 归档文件命名 `signals-archive-YYYYQ#.jsonl`，已有时追加不覆盖
- [x] 2.5 为信号轮转编写测试 — 覆盖正常追加/触发归档/归档追加/坏行诊断场景
- [x] 2.6 跑全量测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/`
