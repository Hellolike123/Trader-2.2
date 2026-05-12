# Signal ID Phases 3-4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up deprecated signal ID code after Phase 1 is complete and `migrate_signal_ids()` has run.

**Architecture:** Two changes to `signal_tracker.py`: (1) mark `stable_id()` as deprecated, (2) remove the 3-key fallback from `check_recent()` and `backfill()`. Keep 4-key fallback for un-migrated records, keep MD5 fallback in `fill()` and `log_safe()` (signal_log is irreversible). One test line in `test_signal_tracker_fixes.py` needs `signal_price` added for 4-key to match.

**Tech Stack:** Python 3, hashlib SHA256, pytest, signal_tracker module

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `02-共享模块-shared/scripts/signal_tracker.py` | Modify | Add deprecation to `stable_id()`, remove 3-key fallback from check_recent/backfill |
| `02-共享模块-shared/tests/test_v2_infra.py` | Modify | Add `test_stable_id_deprecated` to verify warning fires |
| `02-共享模块-shared/tests/test_signal_tracker_fixes.py` | Modify | Verify `signal_price: 20` is present on test fixture |

---

### Task 1: Deprecate `stable_id()` function

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test** (verify deprecation warning fires)

```python
# In tests/test_v2_infra.py (existing test), add assertion that warns:
def test_stable_id_deprecated():
    import signal_tracker as st
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sid = st.stable_id("trader", "南网科技", "2026-05-04", "低吸观察")
        assert len(w) == 1
        assert "deprecated" in str(w[0].message).lower()
```

Run: `cd 02-共享模块-shared && python -m pytest tests/test_v2_infra.py::test_stable_id_deprecated -v`
Expected: FAIL (no deprecation warning)

- [ ] **Step 2: Add deprecation warning to stable_id()**

Add `import warnings` at top of signal_tracker.py (if not already there).

Change `stable_id()` function to:

```python
def stable_id(skill: str, target: str, date: str, signal_type: str, price: float | None = None) -> str:
    """[已弃用] 旧信号 ID 生成函数。请使用 make_signal_id() 替代。将在 v0.7 中移除。"""
    warnings.warn("stable_id() is deprecated, use make_signal_id() instead", stacklevel=2)
    key = f"{date}::{skill}::{target}::{signal_type}"
    if price is not None:
        key += f"::{price:.2f}"
    return hashlib.md5(key.encode()).hexdigest()[:12]
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_v2_infra.py::test_stable_id_deprecated -v`
Expected: PASS

- [ ] **Step 4: Ensure existing tests still pass**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS (existing tests may trigger deprecation warning but should still pass)

- [ ] **Step 5: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_v2_infra.py
git commit -m "phase-3: deprecate stable_id() with warning"
```

---

### Task 2: Remove 3-key fallback from check_recent and backfill

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`
- Modify: `02-共享模块-shared/tests/test_signal_tracker_fixes.py` (add `signal_price: 20`)

**Rationale**: Pre-existing test `test_dedup_with_mixed_case_symbol` creates a result without `signal_price`. The old 3-key fallback matched it by (symbol, date, type) alone. Without 3-key, 4-key requires `signal_price` to match. Adding `signal_price: 20` to the test fixture lets 4-key match instead.

- [ ] **Step 1: Verify the test fixture needs signal_price**

Check current test at `test_signal_tracker_fixes.py` line 147-152:
```python
# Current test — result dict has NO signal_price
existing = json.dumps({
    "symbol": "688248.SH", "name": "南网科技",
    "signal_date": today, "signal_type": "track",
    "r_5d": 3.0, "schema_version": "v1",
})
```

This will NOT match via 4-key (signal price from signal trigger.price="20" != result's missing signal_price). After removing 3-key, this test fails.

- [ ] **Step 2: Verify test fixture already has signal_price**

Check `test_signal_tracker_fixes.py` line 147-152 — `signal_price: 20` should already be present (added in prior cleanup pass). If missing, add it:

```python
existing = json.dumps({
    "symbol": "688248.SH", "name": "南网科技",
    "signal_date": today, "signal_type": "track",
    "signal_price": 20,
    "r_5d": 3.0, "schema_version": "v1",
})
```

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker_fixes.py::TestDedupNormalization::test_dedup_with_mixed_case_symbol -v`
Expected: PASS (4-key matches with signal_price)

- [ ] **Step 3: Remove 3-key from check_recent**

In `signal_tracker.py`, `check_recent()` function. Two changes:

**Change A** — Remove `existing_keys_3` dict (around line 509):
```python
# Before:
existing_keys_3: dict[tuple[str, str, str], dict] = {}
# After: remove this line entirely
```

**Change B** — Remove 3-key index build (around line 528):
```python
# Before:
existing_keys_3[(key_symbol, raw_date, raw_type)] = r
# After: remove this line entirely
```

**Change C** — Remove 3-key from dedup loop (around line 544):
```python
# Before:
if key in existing_keys_4 or (key[0], key[1], key[2]) in existing_keys_3:
# After:
if key in existing_keys_4:
```

- [ ] **Step 4: Same changes in backfill()**

Find `backfill()` (around line 954). Apply the same three removals (`existing_keys_3` declaration, 3-key index build, 3-key dedup).

- [ ] **Step 5: Run full regression suite**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS (289 tests)

- [ ] **Step 6: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_tracker_fixes.py
git commit -m "phase-4a: remove 3-key fallback from check_recent/backfill"
```

---

## Summary of Changes

| File | Changes |
|------|--------|
| `signal_tracker.py` | `stable_id()` gains `warnings.warn` + docstring; 3-key dict and fallback removed from check_recent and backfill |
| `test_signal_tracker_fixes.py` | test_dedup_with_mixed_case_symbol adds signal_price: 20 |
| `test_v2_infra.py` | new test_stable_id_deprecated |

## Notes for Implementer

1. Phase 4b is intentionally skipped (keep fill() and log_safe() MD5 fallback).
2. `signal_log.jsonl` MD5 is irreversible — `fill()` still needs `signal_id_md5` matching for manual outcome entry.
3. 4-key fallback is kept for results that were written before `migrate_signal_ids()` ran.
