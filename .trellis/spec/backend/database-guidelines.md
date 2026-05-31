# Database Guidelines

> Data persistence patterns and conventions for this project.

---

## Overview

This project does **not** use a traditional database (no SQL, no ORM, no migrations). All persistent data is stored as **JSON/JSONL files** in `~/.trader/` and **file-based caches** in `~/.trader/cache/`. The design prioritizes simplicity, offline operation, and easy debugging over query performance.

---

## Storage Architecture

### Persistent Files (`~/.trader/`)

| File | Format | Writer | Reader | Purpose |
|------|--------|--------|--------|---------|
| `signals.jsonl` | JSONL | t0, trader | review, trader | Signal event stream (single source of truth) |
| `pool.json` | JSON | trader | trader | Active stock pool state |
| `pending.json` | JSON | trader | trader | Pending confirmation pool |
| `last_plan.json` | JSON | trader | trader | Last battle plan |
| `calibrated_params.json` | JSON | self_calibration | structure_core | Calibrated parameters (zone_width, etc.) |
| `signal_results.jsonl` | JSONL | signal_tracker | review, self_calibration | Signal settlement results |

### Cache Files (`~/.trader/cache/`)

| Subdirectory | TTL | Content |
|-------------|-----|---------|
| `daily/` | 24h | Daily K-line bars |
| `enrich/` | 12h | Extended data (shareholders, EPS, unlock dates) |
| `market_env/` | 24h | Market environment assessment |
| `fund_flow/` | 24h | Fund flow data |

---

## JSONL Patterns

### Signal Store (`signals.jsonl`)

One JSON object per line. Atomic writes via temp file + `os.fsync()` + `os.replace()`:

```python
# From trader_shared/signal_store.py
def append_signal(signal: dict[str, Any], path: Path | None = None) -> str:
    """Append a signal to the store. Does NOT mutate the caller's dict."""
    working = dict(signal)
    if "signal_id" not in working:
        working["signal_id"] = normalize_signal_id(...)
    # Write to temp file, fsync, then atomic replace
    tmp_file = store_path.with_suffix(f".{os.getpid()}.tmp")
    # ... write + fsync + replace pattern
```

**Key rules:**
- Every signal must have a `signal_id` (16-char hex from SHA256 deterministic hash)
- UUID is computed from: normalized symbol + date + signal_type + trigger price
- File rotation at 10MB (quarterly archive: `signals-archive-2026Q2.jsonl`)
- Bad lines are silently skipped on read (never crash on corrupt data)

### Reading JSONL

```python
# Safe JSONL reading pattern
def _load_all(path: Path) -> list[dict]:
    results = []
    if not path.exists():
        return results
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue  # skip bad lines silently
    return results
```

---

## JSON File Patterns

### Pool State (`pool.json`)

```json
{
  "items": [
    {
      "name": "南网科技",
      "code": "688248",
      "status": "观察",
      "score": 76,
      "added_at": "2026-05-28",
      "stage": "蓄势走强"
    }
  ],
  "updated_at": "2026-05-28T15:30:00"
}
```

### Atomic JSON Write Pattern

All JSON writes use the temp-file + fsync + replace pattern to prevent corruption:

```python
# From trader_shared/cache_utils.py
def set_cached(key: str, target: str, data: Any) -> None:
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = cache_file.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        with open(cache_file, "a") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                tmp_file.replace(cache_file)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    except Exception:
        tmp_file.unlink(missing_ok=True)
        raise
```

---

## File Locking

The project uses `fcntl.flock()` for concurrent access protection:

- **Signal store**: `fcntl.LOCK_EX` during append operations
- **Cache writes**: `fcntl.LOCK_EX` during atomic replace
- **Rotation**: Lock before appending to archive, then truncate current file

```python
# Pattern from signal_store.py
with open(archive_path, "ab") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    try:
        f.write(content)
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
```

---

## Cache Patterns

### TTL-based Cache with Stale-While-Revalidate

```python
from trader_shared.cache_utils import get_cached, set_cached, CacheResult

# Read with TTL
result = get_cached("daily", "688248", ttl=86400)
if result is not None:
    data = result.data
    if result.stale:
        # Data is old but usable — refresh in background or on next call
        pass
else:
    data = fetch_from_api(...)
    set_cached("daily", "688248", data)
```

### Cache Validation Before Write

```python
from trader_shared.cache_utils import set_cached_validated

def validate_bars(bars: list[dict]) -> bool:
    """Validate bar data: count >= 200, close > 0, dates monotonic."""
    if not isinstance(bars, list) or len(bars) < 200:
        return False
    # ... validation logic
    return True

set_cached_validated("daily", "688248", data, validator=validate_bars)
```

---

## Query Patterns

Since there's no database, "queries" are file reads + in-memory filtering:

```python
# Find signals for a specific stock
def load_signals_for_target(target: str) -> list[dict]:
    all_signals = _load_all(DEFAULT_SIGNAL_STORE_PATH)
    return [s for s in all_signals if s.get("symbol", "").startswith(target)]
```

```python
# Find active pool items
pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
active = [item for item in pool_data.get("items", [])
          if item.get("status") not in ("淘汰", "已退出")]
```

---

## Common Mistakes

1. **Writing JSON without fsync**: Always use the temp-file + fsync + replace pattern. Direct `path.write_text()` can corrupt on crash.

2. **Not handling missing files**: Always check `path.exists()` before reading. Use `try/except` for JSON parse errors.

3. **Mutating caller's dict**: `append_signal()` deep-copies the input dict before modifying it. Follow this pattern.

4. **Cache without date dedup**: When merging cached bars with real-time data, deduplicate by date to prevent cache bloat (the `market_env.py` bug that caused 20700 bars).

5. **Using `fetch_kline(scale="240")` for daily data**: This returns Sina minute bars, not daily bars. Use `fetch_qfq_daily()` for daily data.

---

## Naming Conventions

- **JSONL files**: `snake_case.jsonl` (e.g., `signals.jsonl`, `signal_results.jsonl`)
- **JSON files**: `snake_case.json` (e.g., `pool.json`, `calibrated_params.json`)
- **Cache subdirectories**: `snake_case/` (e.g., `daily/`, `market_env/`, `fund_flow/`)
- **Archive files**: `{original}-archive-{YYYY}Q{N}.jsonl`
- **Temp files**: `{original}.{pid}.tmp`
