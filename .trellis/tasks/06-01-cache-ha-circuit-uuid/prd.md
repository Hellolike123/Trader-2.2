# Cache Lock + HA Failover + Circuit Breaker + UUID Cache

## Overview

Four reliability and performance optimizations for the data and signal layers.

## Issues to Fix (in order)

### 1. File Cache Process Locking

**Location**: `cache_utils.py`

**Problem**: Multiple processes can read/write cache files simultaneously, causing corruption.

**Requirements**:
- Add `fcntl.flock()` file lock before writing cache
- Add shared lock before reading cache (prevents reading half-written files)
- 5-second timeout, then give up and log warning
- Use `LOCK_EX` for write, `LOCK_SH` for read

### 2. light_data.py Single Point of Failure

**Location**: `light_data.py` / `data_provider.py`

**Problem**: If Tencent API fails, all skills fail. No automatic fallback to Sina API.

**Requirements**:
- Tencent API timeout or failure → auto-switch to Sina API
- Track `consecutive_failures` per source
- After 3 consecutive failures, trigger fallback
- Log which source failed and which is being used
- Keep existing `MarketDataSourceController` pattern

### 3. Circuit Breaker for API Calls

**Location**: `light_data.py`

**Problem**: No circuit breaker — keeps retrying failed APIs, wasting time.

**Requirements**:
- After 5 consecutive failures, pause requests for 60 seconds
- During pause, return cached data or raise error
- After 60 seconds, resume and try again
- Successful request resets failure counter
- Add `_CircuitBreaker` class or extend `MarketDataSourceController`

### 4. UUID Deduplication Efficiency

**Location**: `signal_store.py`

**Problem**: Every write reads the entire JSONL file to check for duplicates.

**Requirements**:
- Cache UUIDs in memory `set` on process startup
- New writes update both memory set and file
- `_load_uuid_cache()` — loads all UUIDs from signals.jsonl on first access
- `_uuid_cache` — module-level set for fast lookup
- Avoid re-reading file on every `log_safe()` call

## Verification

```bash
python3 -m pytest 02-共享模块-shared/tests/
```

## Success Criteria

- Cache reads/writes are process-safe with file locks
- Tencent API failure auto-switches to Sina API
- Circuit breaker pauses after 5 failures, resumes after 60s
- UUID deduplication uses in-memory cache
- All existing tests pass
