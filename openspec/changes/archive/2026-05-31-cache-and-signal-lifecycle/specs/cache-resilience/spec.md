## ADDED Requirements

### Requirement: File locking on cache writes

`set_cached()` MUST 使用 `fcntl.flock(LOCK_EX)` 防止并发写损坏。`.tmp` 文件名 MUST 包含 PID 防止多进程冲突。

#### Scenario: Two processes write same key simultaneously
- **WHEN** 进程 A 和进程 B 同时调用 `set_cached("daily", "688248", data)`
- **THEN** 两个进程 MUST 使用不同的 `.tmp` 文件名（如 `688248.12345.tmp` 和 `688248.67890.tmp`），写入完成后原子 rename，不互相覆盖

#### Scenario: Process killed mid-write
- **WHEN** 进程在 `set_cached()` 写 `.tmp` 文件过程中被 kill
- **THEN** `.tmp` 文件 MAY 残留但不影响 `.json` 缓存文件的完整性

### Requirement: CacheResult with stale-while-revalidate

`get_cached()` MUST 返回 `CacheResult` 包装器，支持 stale 数据返回。

#### Scenario: Cache hit within TTL
- **WHEN** 缓存文件存在且未过期
- **THEN** 返回 `CacheResult(data=..., stale=False, age_seconds=..., source="file")`

#### Scenario: Cache expired but file exists
- **WHEN** 缓存文件存在但 TTL 已过期
- **THEN** 返回 `CacheResult(data=..., stale=True, age_seconds=..., source="file")`，数据仍可读取

#### Scenario: Cache file missing
- **WHEN** 缓存文件不存在
- **THEN** 返回 `None`

#### Scenario: Cache file corrupted
- **WHEN** 缓存文件存在但 JSON 解析失败
- **THEN** 返回 `None`（与现有行为一致）

### Requirement: Backward compatible get_cached callers

所有 `get_cached()` 调用点 MUST 适配 `CacheResult` 返回类型。

#### Scenario: Existing caller uses result directly
- **WHEN** 代码写 `data = get_cached(...)` 然后 `data.get("key")`
- **THEN** MUST 改为 `result = get_cached(...)` 然后 `result.data.get("key")`（或使用兼容辅助函数）
