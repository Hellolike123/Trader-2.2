# Memory + Signal + Schema Optimization

## Overview

Three optimizations to improve memory efficiency, signal management, and schema versioning.

## Issues to Fix

### 1. Memory Loading Optimization

**Problem**: K-line data loaded entirely into memory, causing OOM risk with large datasets.

**Requirements**:
- Implement chunked/batch reading for K-line data
- Add memory-efficient streaming for large bar histories
- Keep backward compatibility with existing callers
- Add memory usage logging

**Files to modify**:
- `02-共享模块-shared/trader_shared/light_data.py` — Add batch reading
- `02-共享模块-shared/trader_shared/cache_utils.py` — Support chunked cache reads

### 2. signals.jsonl Expiry Cleanup

**Problem**: `signals.jsonl` grows unbounded, slowing down reads and wasting disk space.

**Requirements**:
- Add `signal_store.cleanup_old_signals(max_age_days=90)` function
- Archive old signals to `signals_archive_YYYYMM.jsonl` before deletion
- Keep signals that are still `active` (not completed/expired)
- Integrate into `warm_pool_cache()` or add separate command
- Log how many signals were archived/deleted

**Files to modify**:
- `02-共享模块-shared/trader_shared/signal_store.py` — Add cleanup function

### 3. JSONL Schema Version Field

**Problem**: No version field in JSONL records, making future schema migrations risky.

**Requirements**:
- Add `"schema_version": 1` field to all new signal records
- Maintain backward compatibility (read records without version field)
- Add version validation on read
- Document version history

**Files to modify**:
- `02-共享模块-shared/trader_shared/signal_store.py` — Add version field
- `02-共享模块-shared/trader_shared/models.py` — Update SignalRecord TypedDict

## Verification

1. Run all tests: `python3 -m pytest 02-共享模块-shared/tests/`
2. Verify signal store tests pass
3. Verify cache tests pass
4. Check memory usage with large datasets (manual test)

## Success Criteria

- K-line data loads in chunks, not all at once
- Old signals are automatically archived and cleaned
- New signals include `schema_version` field
- All existing tests pass
