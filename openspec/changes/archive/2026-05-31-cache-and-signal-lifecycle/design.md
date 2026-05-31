## Context

`cache_utils.py` 是一个 250 行的简单文件缓存，无锁、无 stale 支持。`signal_store.py` 和 `data_manager.py` 两套读写 `signals.jsonl` 的逻辑并存，行为不一致。需要在不改变外部 API 的前提下增强这两个模块。

## Goals / Non-Goals

**Goals:**
- 缓存并发写安全（fcntl.flock + 唯一 tmp）
- 缓存过期后仍可返回 stale 数据（stale-while-revalidate）
- 信号读写路径统一，坏行有诊断
- signals.jsonl 自动轮转

**Non-Goals:**
- 不引入分布式缓存（Redis 等）
- 不改变信号格式或 UUID 算法
- 不做 FrozenBars（理论风险，当前无实际 bug）

## Decisions

### 1. CacheResult 返回类型

**问题**：`get_cached()` 返回 `None` 表示缓存未命中，无法区分"没有数据"和"有过期数据"。

**决策**：返回 `CacheResult` dataclass，包含 `data`、`stale`、`age_seconds`、`source` 四个字段。

**理由**：
- 调用方可以根据 `stale` 决定是否使用过期数据
- `age_seconds` 用于日志/监控
- `source` 标记数据来源（memory/file/live）
- 替代方案：返回 `(data, stale)` tuple，但扩展性差

### 2. 文件锁策略

**问题**：`set_cached()` 无锁，并发写同一 key 时 `.tmp` 文件冲突。

**决策**：写操作用 `fcntl.flock(LOCK_EX)` 排他锁，`.tmp` 文件名加 PID 后缀。

**理由**：
- `signal_store.py` 已有 `fcntl.flock` 模式，照搬即可
- PID 后缀防止多进程写同一 tmp 文件
- 替代方案：用 `filelock` 第三方库，但增加依赖

### 3. stale-while-revalidate 策略

**问题**：缓存过期后返回 None，API 挂掉时完全没数据。

**决策**：TTL 过期后仍读取数据，标记 `stale=True`，调用方决定是否使用。

**理由**：
- 1 分钟前的缓存数据在大多数场景下完全可用
- 调用方可以 `if result.stale: log_warning()` 但仍然使用数据
- 替代方案：返回 None + 独立的 `get_stale()` 函数，但调用方需要两次调用

### 4. 信号读写统一

**问题**：`signal_store._read_store()` 和 `DataManager.load_signals()` 两套逻辑。

**决策**：保留 `signal_store` 作为唯一读写路径，`DataManager` 委托给它。

**理由**：
- `signal_store` 已有坏行计数和诊断，更成熟
- `DataManager` 的 `fcntl.flock` 写逻辑保留，但读逻辑委托给 `signal_store`
- 替代方案：删除 `DataManager`，但影响范围过大

### 5. 信号轮转策略

**问题**：`signals.jsonl` 无大小限制，长期运行后无限增长。

**决策**：每次写入前检查文件大小，超过 10MB 时归档到 `signals-archive-YYYYQ#.jsonl`。

**理由**：
- 10MB 大约对应 3-6 个月的信号量
- 按季度归档便于后续分析
- 替代方案：按天归档，但文件数量太多
