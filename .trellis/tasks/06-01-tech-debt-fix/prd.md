# Technical Debt Refactoring

## Overview

Fix all identified technical debt issues in the Trader codebase to improve stability, testability, and maintainability.

## Issues to Fix

### Phase 1: Error Handling + Cache Cleanup (2h)

#### 1.1 Replace `try/except: pass` with proper logging

**Problem**: Many places silently swallow errors, hiding bugs.

**Files to audit**:
- `02-共享模块-shared/trader_shared/` — all modules
- `01-功能包-packages/*/scripts/` — all skill scripts

**Pattern to replace**:
```python
# WRONG
try:
    risky_operation()
except:
    pass

# CORRECT
try:
    risky_operation()
except (ValueError, KeyError) as e:
    logger.warning(f"Operation failed: {e}")
    return default_value
```

**Requirements**:
- Scan all Python files for `except.*pass` patterns
- Replace with specific exception types + logging
- Add `import logging` and create module-level logger where missing
- Keep `try/except` for graceful degradation (fallback functions), but add logging

#### 1.2 Add cache cleanup mechanism

**Problem**: `~/.trader/` files grow unbounded.

**Requirements**:
- Add `cache_utils.cleanup_old_cache(max_age_days=30)` function
- Call it during `cache warm` command
- Remove cache files older than 30 days
- Log how many files were cleaned

### Phase 2: Signal Lock + Config Safety (2h)

#### 2.1 Add file locking for signal writes

**Problem**: Multiple processes writing to `signals.jsonl` can corrupt data.

**Requirements**:
- Use `fcntl.flock()` for Unix file locking
- Wrap `signal_store.py` write operations with lock
- Add timeout to prevent deadlocks
- Log lock contention

#### 2.2 Make config immutable at runtime

**Problem**: Global config values can be overwritten during execution.

**Requirements**:
- Make `config.py` values immutable after import
- Use `__all__` to control exports
- Add validation on config load
- Consider using `dataclass(frozen=True)` for config

### Phase 3: sys.path Refactoring + API Rate Limiting (2h)

#### 3.1 Fix import paths

**Problem**: `sys.path.insert(0, parents[3])` is fragile.

**Requirements**:
- Use relative imports within packages
- Use `pyproject.toml` entry points for scripts
- Remove all `sys.path` hacks
- Test that `pip install -e .` still works

#### 3.2 Add API rate limiting

**Problem**: No frequency control for Tencent/Sina API calls.

**Requirements**:
- Add `time.sleep(0.1)` between API calls
- Implement exponential backoff on 429/503
- Log API call frequency
- Add configurable rate limits

## Verification

1. Run all tests: `python3 -m pytest 02-共享模块-shared/tests/`
2. Run all skill tests: `python3 -m pytest 01-功能包-packages/*/tests/`
3. Verify `pip install -e .` works
4. Verify all CLI commands still work:
   - `python3 scripts/final_report.py --target 南网科技`
   - `python3 scripts/final_t0.py --target 南网科技 --once`
   - `python3 scripts/final_review.py --target 南网科技`

## Success Criteria

- Zero `try/except: pass` patterns remaining
- All cache files have cleanup mechanism
- Signal writes are process-safe
- Config values are immutable
- No `sys.path` hacks
- API calls have rate limiting
- All existing tests pass
