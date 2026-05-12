# Signal Lifecycle Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `status` field (active/completed/expired) to signal records with state transition guards, so `check_recent` can skip completed/expired signals.

**Architecture:** 3 new functions + 2 modified loops. `signal_is_trackable()` filters signals before computation. `set_signal_status()` enforces transition rules. `check_recent`/`backfill` set `status=completed` after writing results. Backfill tool for existing data.

**Tech Stack:** Python 3, signal_tracker module, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `02-共享模块-shared/scripts/signal_tracker.py` | Modify | Add `SIGNAL_STATUS_VALUES`, `signal_is_trackable()`, `set_signal_status()`, `backfill_signal_status()`, modify `check_recent()`/`backfill()` loops |
| `02-共享模块-shared/tests/test_signal_lifecycle.py` | Create | Tests for status functions and check_recent filtering |

---

### Task 1: Add status constants and functions

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`
- Test: `02-共享模块-shared/tests/test_signal_lifecycle.py`

- [ ] **Step 1: Write failing tests**

```python
# test_signal_lifecycle.py
from signal_tracker import (
    SIGNAL_STATUS_VALUES,
    signal_is_trackable,
    set_signal_status,
)

def test_signal_is_trackable_no_status():
    """Signal without status = trackable (default active)."""
    assert signal_is_trackable({}) is True
    assert signal_is_trackable({"status": ""}) is True
    assert signal_is_trackable({"signal_type": "track"}) is True

def test_signal_is_trackable_active():
    """status=active → trackable."""
    assert signal_is_trackable({"status": "active"}) is True

def test_signal_is_trackable_completed():
    """status=completed → not trackable."""
    assert signal_is_trackable({"status": "completed"}) is False

def test_signal_is_trackable_expired():
    """status=expired → not trackable."""
    assert signal_is_trackable({"status": "expired"}) is False

def test_set_signal_status_valid():
    """Set legal status values."""
    rec = {}
    set_signal_status(rec, "active")
    assert rec["status"] == "active"
    assert "status_updated_at" in rec

def test_set_signal_status_invalid_value():
    """Reject illegal status value."""
    import pytest
    rec = {}
    with pytest.raises(ValueError):
        set_signal_status(rec, "invalid")

def test_set_signal_status_forbidden_transition():
    """Reject completed→active."""
    import pytest
    rec = {"status": "completed"}
    with pytest.raises(ValueError):
        set_signal_status(rec, "active")

def test_set_signal_status_allowed_transition():
    """Allow active→completed."""
    rec = {"status": "active"}
    set_signal_status(rec, "completed")
    assert rec["status"] == "completed"

def test_signal_status_values():
    """Status values are the expected set."""
    assert SIGNAL_STATUS_VALUES == {"active", "completed", "expired"}
```

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py -v`
Expected: FAIL (functions not defined)

- [ ] **Step 2: Implement constants and functions**

Add to `signal_tracker.py` in the "新信号追踪逻辑" section (after `_SIGNAL_TYPE_MAP`):

```python
# ── 信号生命周期状态 ──

SIGNAL_STATUS_VALUES = {"active", "completed", "expired"}

_FORBIDDEN_TRANSITIONS: dict[tuple[str, str], bool] = {
    ("completed", "active"): True,
    ("completed", "expired"): True,
    ("expired", "active"): True,
    ("expired", "completed"): True,
}


def signal_is_trackable(sig: dict) -> bool:
    """信号是否应被 check_recent 处理。
    
    没有 status 字段 = active（默认追踪）
    status 为 active = 追踪
    status 为 completed/expired = 跳过
    """
    status = sig.get("status")
    if status is None:
        return True
    return status == "active"


def set_signal_status(rec: dict, new_status: str) -> None:
    """设置信号状态，校验合法值和迁移规则。"""
    if new_status not in SIGNAL_STATUS_VALUES:
        raise ValueError(f"Invalid signal status: {new_status}")
    
    current = rec.get("status")
    if current and (current, new_status) in _FORBIDDEN_TRANSITIONS:
        raise ValueError(
            f"Transition not allowed: {current} → {new_status}"
        )
    
    rec["status"] = new_status
    rec["status_updated_at"] = datetime.now().isoformat()
```

- [ ] **Step 3: Run tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_lifecycle.py
git commit -m "lifecycle: add signal_is_trackable() and set_signal_status()"
```

---

### Task 2: Modify check_recent/backfill to set status on the signal

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write failing tests**

Add to `test_signal_lifecycle.py`:

```python
def test_check_recent_skips_completed(tmp_path, monkeypatch):
    """check_recent should skip signals with status=completed."""
    import signal_tracker as st
    import json
    from unittest.mock import MagicMock, patch

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    signal = {
        "symbol": "688248.SH", "trade_date": "2026-05-02",
        "signal_type": "low_buy_watch",
        "status": "completed",
        "trigger": {"price": 10.5},
    }
    store.write_text(json.dumps(signal) + "\n", encoding="utf-8")

    with patch.object(st, "HttpClient", MagicMock()), \
         patch.object(st, "resolve_security", return_value="688248.SH"), \
         patch.object(st, "fetch_qfq_daily", return_value=[]), \
         patch.object(st, "to_float", return_value=None):
        result = st.check_recent(days=5)

    assert result.get("lifecycle_skipped", 0) >= 1, f"Should skip completed signal: {result}"
    assert result.get("updated", 0) == 0


def test_check_recent_sets_completed_after_result(tmp_path, monkeypatch):
    """After computing result, signal's status in signals.jsonl becomes completed."""
    import signal_tracker as st
    import json
    from unittest.mock import MagicMock, patch

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    signal = {
        "symbol": "688248.SH", "trade_date": "2026-05-02",
        "signal_type": "low_buy_watch",
        "trigger": {"price": 10.5},
    }
    store.write_text(json.dumps(signal) + "\n", encoding="utf-8")

    bars = [{"date": "2026-05-02", "close": 10.5, "atr14": 0.3}]

    with patch.object(st, "HttpClient", return_value=MagicMock()), \
         patch.object(st, "resolve_security", return_value="688248.SH"), \
         patch.object(st, "fetch_qfq_daily", return_value=bars), \
         patch.object(st, "to_float", side_effect=lambda v: float(v) if v else None):
        result = st.check_recent(days=5)

    assert result.get("updated", 0) >= 1
    
    # Status should be set on signals.jsonl (not on results)
    updated_signal = json.loads(store.read_text(encoding="utf-8").strip().splitlines()[0])
    assert updated_signal.get("status") == "completed"
    assert "status_updated_at" in updated_signal
```

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py::test_check_recent_skips_completed -v`
Expected: FAIL (check_recent doesn't check status)

- [ ] **Step 2: Modify check_recent() and backfill()**

**Change A** — Add `lifecycle_skipped` counter to the result:

```python
    result_lines: list[str] = []
    updated = 0
    skipped = 0
    lifecycle_skipped = 0
```

**Change B** — In the signal-scanning loop, add lifecycle check BEFORE computation:

```python
    for sig in recent:
        if not signal_is_trackable(sig):
            lifecycle_skipped += 1; continue
        # ... existing signal_id + 4-key matching ...
        std = sig.get("signal_id")
        ...
```

**Change C** — After result computation, update the in-memory signal dict:

```python
    result = _compute_results_for_sig(sig)
    if result:
        set_signal_status(sig, "completed")  # Update signal, not result
        result_lines.append(...)
        updated += 1
```

**Change D** — After the loop, write back modified signals to signals.jsonl:

```python
    if updated > 0:
        # Re-read signals, apply status changes
        sig_lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
        updated_sig_ids = {r.get("signal_id") for r in sig_results_lines if ...}
        new_sig_lines = []
        for line in sig_lines:
            ...
```

Actually, simpler: keep a list of modified signals:

```python
    for sig in recent:
        if not signal_is_trackable(sig):
            lifecycle_skipped += 1; continue
        ...
        result = _compute_results_for_sig(sig)
        if result:
            set_signal_status(sig, "completed")
            ...
    
    if updated > 0:
        # Re-read signals.jsonl and apply status changes
        sig_lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
        new_sig_lines = []
        for line in sig_lines:
            if not line.strip():
                new_sig_lines.append(line); continue
            sig_rec = json.loads(line)
            signal_id = sig_rec.get("signal_id")
            if signal_id and signal_id in {s.get("signal_id") for s in recent if s.get("status") == "completed"}:
                sig_rec["status"] = "completed"
                sig_rec["status_updated_at"] = datetime.now().isoformat()
            new_sig_lines.append(json.dumps(sig_rec, ensure_ascii=False))
        tmp = STORE_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_sig_lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), STORE_PATH)
```

**Change E** — Update return dict:

```python
    return {
        "updated": updated,
        "skipped": skipped,
        "lifecycle_skipped": lifecycle_skipped,
    }
```

Same changes in `backfill()`.

- [ ] **Step 3: Run tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 4: Full regression**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS (existing tests may need minor assertion updates for the new `lifecycle_skipped` return key)

- [ ] **Step 5: Fix any existing tests that assert exact return keys**

If any test asserts `result == {"updated": 0, "skipped": 0}` and now gets `{"updated": 0, "skipped": 0, "lifecycle_skipped": 0}`, update the assertion.

- [ ] **Step 6: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_lifecycle.py
git commit -m "lifecycle: check_recent/backfill filter by status, set completed on signal"
```

---

### Task 3: Add backfill_signal_status() migration tool

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`
- Modify: `02-共享模块-shared/tests/test_signal_lifecycle.py`

- [ ] **Step 1: Write failing test**

```python
def test_backfill_signal_status(tmp_path, monkeypatch):
    """backfill_signal_status() sets status=completed for signals with results."""
    import signal_tracker as st
    import json

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"

    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    # Signal with matching result
    sig = {"symbol": "688248.SH", "signal_type": "track", "signal_id": "abc123"}
    store.write_text(json.dumps(sig) + "\n", encoding="utf-8")

    result = {"signal_id": "abc123", "r_5d": 2.5, "outcome": "up"}
    results.write_text(json.dumps(result) + "\n", encoding="utf-8")

    st.backfill_signal_status()

    updated = json.loads(store.read_text(encoding="utf-8").strip().splitlines()[0])
    assert updated.get("status") == "completed"
    assert "status_updated_at" in updated
```

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py::test_backfill_signal_status -v`
Expected: FAIL

- [ ] **Step 2: Implement backfill_signal_status()**

Add to `signal_tracker.py` (near `migrate_signal_ids()`):

```python
def backfill_signal_status() -> dict[str, int]:
    """为已有结果记录的信号补充 status=completed。
    
    幂等：已有 status 的记录跳过。无结果匹配的信号保留 implicit active。
    """
    if not STORE_PATH.exists():
        return {"updated": 0}
    
    # Build set of signal_ids from results
    result_ids: set[str] = set()
    if RESULT_PATH.exists():
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get("signal_id"):
                    result_ids.add(r["signal_id"])
            except (json.JSONDecodeError, ValueError):
                continue
    
    if not result_ids:
        return {"updated": 0}
    
    lines = STORE_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated = 0
    
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            sig = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            new_lines.append(line)
            continue
        
        if sig.get("status"):
            new_lines.append(line)
            continue
        if sig.get("signal_id") in result_ids:
            sig["status"] = "completed"
            sig["status_updated_at"] = datetime.now().isoformat()
            new_lines.append(json.dumps(sig, ensure_ascii=False))
            updated += 1
        else:
            new_lines.append(line)
    
    if updated:
        tmp = STORE_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.replace(str(tmp), STORE_PATH)
    
    return {"updated": updated}
```

- [ ] **Step 3: Run test**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_lifecycle.py::test_backfill_signal_status -v`
Expected: PASS

- [ ] **Step 4: Full regression**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_lifecycle.py
git commit -m "lifecycle: add backfill_signal_status() migration tool"
```
---

### Task 4: Run backfill on existing data + final regression

**Files:**
- Existing user data at `~/.trader/signals.jsonl`

- [ ] **Step 1: Run backfill on real data**

```bash
cd 02-共享模块-shared && python3 -c "
from signal_tracker import backfill_signal_status
result = backfill_signal_status()
print(f'Updated: {result}')
"
```

Expected: Updates any old signals that have matching signal_results.jsonl entries.

- [ ] **Step 2: Final full regression**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add -A && git diff --cached --stat
# Add any changed files
```

---

## Summary

| Task | Files | Key Change |
|------|-------|------------|
| 1 | signal_tracker.py | Add status constants + validation functions |
| 2 | signal_tracker.py | check_recent/backfill filter + auto-set completed |
| 3 | signal_tracker.py | backfill_signal_status() migration tool |
| 4 | user data | Run backfill on existing signals |
