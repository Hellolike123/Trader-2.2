# Error Handling

> How errors are caught, logged, and handled in this project.

---

## Overview

This project follows a **graceful degradation** philosophy: when a component fails, the system falls back to a simpler mode rather than crashing. There are no custom exception classes — the project uses standard Python exceptions with defensive `try/except` blocks at module boundaries. The `safe_cast.py` module provides safe data extraction primitives to prevent `None`/type errors from propagating.

---

## Core Error Handling Patterns

### 1. Graceful Degradation with Fallback Functions

The most common pattern: try to import/use a module, provide a no-op fallback if unavailable.

```python
# From trader_shared/structure_core.py
try:
    from hmm_regime import detect_regime as _hmm_detect_regime, regime_to_multiplier as _hmm_multiplier
    _HMM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HMM_AVAILABLE = False
    def _hmm_detect_regime(returns):
        return {"state_en": "range", "confidence": 0.5}
    def _hmm_multiplier(r):
        return {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0}
```

```python
# From run_analysis.py — graceful degradation when shared modules unavailable
try:
    from trader_shared import conflicting_signals, get_market_level, write_stock, log
    track_log = log
except ImportError:
    import warnings
    warnings.warn(
        "[trader] shared module not available — market status, signal tracking disabled.",
        stacklevel=2,
    )
    def _empty_str(*a, **k): return ""
    def _empty_fn(*a, **k): return None
    conflicting_signals = _empty_list
    get_market_level = _empty_str
    write_stock = _empty_fn
    track_log = _empty_fn
```

**Rule**: Every optional module import should have a fallback. The fallback should return neutral/empty data, not raise.

### 2. Safe Data Extraction (`safe_cast.py`)

Never access dict values directly for numeric data. Use `safe_cast` primitives:

```python
from trader_shared.safe_cast import safe_float, safe_dict, safe_max, safe_min, require_positive

# Instead of: price = data.get("price")  # could be None, "", "N/A"
price = safe_float(data, "price", default=0.0)

# Instead of: sub = data.get("details", {})  # could be None
sub = safe_dict(data, "details")  # always returns dict

# Instead of: m = max(values)  # could be empty
m = safe_max(values, default=0.0)

# Require positive value (returns None if not positive)
atr = require_positive(data.get("atr14"), name="atr14")
```

### 3. Silent Exception Catching at Boundaries

At module boundaries (data fetch, file I/O, external API), catch broad exceptions and degrade:

```python
# From cache_utils.py
def get_cached(key: str, target: str, ttl: int = TTL_DAILY) -> CacheResult | None:
    cache_file = CACHE_DIR / key / f"{target}.json"
    if not cache_file.exists():
        return None
    try:
        age = time.time() - cache_file.stat().st_mtime
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        stale = age > ttl
        return CacheResult(data=data, stale=stale, age_seconds=round(age, 1), source="file")
    except Exception:
        return None  # cache miss on any error
```

**Rule**: At I/O boundaries, catch `Exception` and return a safe default. Inside computation logic, catch specific exceptions.

### 4. Explicit Exception Types (Not Bare `except`)

Internal computation should catch specific exceptions, never bare `except`:

```python
# CORRECT — specific exception types
try:
    result = float(val)
    return result
except (TypeError, ValueError):
    return default

# WRONG — bare except swallows everything including KeyboardInterrupt
try:
    result = float(val)
except:  # NEVER do this
    pass
```

### 5. Warnings for Non-Fatal Issues

Use `warnings.warn()` for deprecation or non-fatal issues that should be visible but not crash:

```python
import warnings
warnings.warn(
    "[trader] shared module not available — pool operations disabled.",
    stacklevel=2,
)
```

Use `print(..., file=sys.stderr)` for operational warnings:

```python
print(f"WARN: rule engine loaded but evaluation failed: {exc}", file=sys.stderr)
```

### 6. Silent Degradation for Optional Features

Optional features (HMM, Bayesian fusion, volume profile) degrade silently when unavailable:

```python
# From decision_core.py — Volume Profile is optional
try:
    from volume_profile import assess_vp_breakout as _vp_assess
    _VP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _VP_AVAILABLE = False
    def _vp_assess(price, vp, is_buy_context=True):
        return {"vp_signal": "no_data", "vp_confidence": 0.5, "vp_note": "无量价分布模块"}
```

### 7. Exit Codes for CLI Entry Points

CLI scripts return `0` for success, `1` for errors:

```python
# From final_report.py
def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target)
    except Exception as exc:
        print(f"Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1
    # ... process report
    return 0
```

---

## Error Handling in Data Pipeline

### Data Fetch Errors

`light_data.py` implements a dual-source HA (High Availability) pipeline with automatic failover:

1. **Primary source** (mootdx TCP): 1.5s hard timeout via `socket.setdefaulttimeout(1.5)`
2. **Failure tracking**: `consecutive_failures >= 3` → isolate source for 30s cooldown
3. **Fallback chain**: mootdx → Tencent HTTP → Sina HTTP → akshare
4. **Data status annotation**: `data_status` field in `MarketSnapshot` tracks completeness

```python
# From data_provider.py — data status tracking
@dataclass(frozen=True)
class MarketSnapshot:
    data_status: DataStatus = "full"      # "full" | "partial" | "degraded" | "failed"
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
```

### Analysis Pipeline Errors

Each analysis module (chanlun, wyckoff, momentum) is wrapped in try/except in `run_analysis.py`:

```python
# Parallel execution with individual error handling
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(chanlun_strategy, bars): "chanlun",
        executor.submit(wyckoff_strategy, bars): "wyckoff",
        executor.submit(momentum_strategy, bars): "momentum",
    }
    for future in as_completed(futures):
        name = futures[future]
        try:
            results[name] = future.result()
        except Exception as exc:
            results[name] = {"error": str(exc)}  # degrade, don't crash
```

---

## Forbidden Patterns

1. **Bare `except:`** — Never use bare except. Always specify exception type(s).

2. **Silent swallowing in computation** — Don't catch exceptions inside core algorithms without logging. At boundaries it's OK; inside logic it hides bugs.

3. **`raise` in fallback functions** — Fallback functions must return neutral data, never raise.

4. **Using `assert` for validation** — `assert` is stripped in optimized mode. Use explicit `if/raise` for data validation.

5. **Catching `KeyboardInterrupt`/`SystemExit`** — Never catch these unless you're the top-level entry point.

---

## Common Mistakes

1. **Forgetting `stacklevel=2` in warnings**: Always use `stacklevel=2` so the warning points to the caller, not the warning line.

2. **Not checking `path.exists()` before JSON parse**: Always check file existence before `json.loads()`.

3. **Returning `None` where callers expect dict**: Use `safe_dict()` to guarantee non-None return values.

4. **Catching too broadly in loops**: When processing a list of items, catch exceptions per-item, not around the whole loop.

5. **Not cleaning up temp files on error**: Use `try/finally` or `tmp_file.unlink(missing_ok=True)` in exception handlers.
