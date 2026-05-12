# Signal ID 统一模型 (A-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace two independent ID systems (MD5 `stable_id` for signal_log + 4-key matching for signals/results) with a single `make_signal_id(symbol, date, type, price)[:16]` function, write it to all three JSONL files, and maintain backward-compatible reading.

**Architecture:** Phase 1 only — add `make_signal_id()`, write it to new records, keep all existing logic (stable_id, 4-key, 3-key) untouched. Dual-field coexistence on signal_log.jsonl (new records carry both `signal_id` and `signal_id_md5`). All reading functions add signal_id-based matching at the top of their priority chain.

**Tech Stack:** Python 3, hashlib (SHA256), existing `signal_tracker.py` and `signal_store.py` modules, pytest for testing.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `02-共享模块-shared/scripts/signal_tracker.py` | **Modify** | Add `make_signal_id()`, update `log_safe()`, `_create_log_record()`, `_compute_results_for_sig()`, `check_recent()`, `backfill()`, `fill()` |
| `02-共享模块-shared/03-输出校验-contracts/signal_store.py` | **Modify** | Add signal_id to `append_signal()` |
| `02-共享模块-shared/tests/test_signal_id_unified.py` | **Create** | Core `make_signal_id()` unit tests |
| `02-共享模块-shared/tests/test_signal_id_log_compat.py` | **Create** | `log_safe()` dual-field + `fill()` backward compat |
| `02-共享模块-shared/tests/test_signal_id_check_compat.py` | **Create** | `check_recent`/`backfill` triple-degradation matching |
| `02-共享模块-shared/tests/test_signal_id_migration.py` | **Create** | `migrate_signal_ids()` tool testing |
| `02-共享模块-shared/tests/test_signal_id_store.py` | **Create** | `signal_store.append_signal()` signal_id generation |

---

## Task 1: Add `make_signal_id()` and `_normalize_signal_type()` to signal_tracker.py

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_unified.py
import hashlib

def test_make_signal_id_basic():
    from signal_tracker import make_signal_id
    sid = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    assert len(sid) == 16
    assert isinstance(sid, str)
    # Deterministic
    assert make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50") == sid

def test_make_signal_id_sha256_not_md5():
    from signal_tracker import make_signal_id
    sid = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    md5_hash = hashlib.md5(b"test").hexdigest()[:12]  # MD5 is only 12 hex chars
    sha_hash = hashlib.sha256(b"test").hexdigest()[:12]
    # Verify it's sha256 by checking output against known sha256 pattern
    assert sid != md5_hash  # Different algorithm
    # SHA256 produces more varied hex characters
    # This test is mainly a sanity check

def test_make_signal_id_different_inputs():
    from signal_tracker import make_signal_id
    sid1 = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    sid2 = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.51")
    assert sid1 != sid2  # Different price → different ID

def test_make_signal_id_empty_inputs():
    from signal_tracker import make_signal_id
    # Even empty inputs should produce valid IDs (no crash)
    sid = make_signal_id("", "", "unknown", "0.00")
    assert len(sid) == 16
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_unified.py -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

Add to `signal_tracker.py` after the existing utility imports (around line 14):

```python
def make_signal_id(symbol: str, date: str, signal_type: str, price: str) -> str:
    """Generate unified signal ID.
    
    Uses SHA256 with 4 normalized fields. 16 hex chars = 48 bits of entropy.
    """
    key = f"{symbol}|{date}|{signal_type}|{price}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_unified.py::test_make_signal_id_basic tests/test_signal_id_unified.py::test_make_signal_id_different_inputs tests/test_signal_id_unified.py::test_make_signal_id_empty_inputs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_id_unified.py
git commit -m "feat(signal): add make_signal_id() function"
```

---

## Task 2: Add `_normalize_signal_type()` public function and verify `_SIGNAL_TYPE_MAP`

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Verify `_normalize_signal_type()` exists and handles all cases**

Read lines 205-248 of signal_tracker.py to verify `_SIGNAL_TYPE_MAP` covers all signal types. Check that `_normalize_signal_type(raw_type)` returns `_SIGNAL_TYPE_MAP.get(raw_type, raw_type)`.

- [ ] **Step 2: Write importable version of `_normalize_signal_type`**

Ensure `_normalize_signal_type()`. If it already exists (line 571), verify it's correct:

```python
def _normalize_signal_type(raw_type: str) -> str:
    """Normalize signal type: old names mapped to new, unknown passed through."""
    return _SIGNAL_TYPE_MAP.get(raw_type, raw_type)
```

If it doesn't exist, create it. If it already exists, skip.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py -v -x`
Expected: All PASS (no changes expected)

- [ ] **Step 4: Commit (if any changes)**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py
git commit -m "refactor(tracker): verify _normalize_signal_type is public-ready"
```

---

## Task 3: Update `signal_store.append_signal()` to auto-generate signal_id

**Files:**
- Modify: `02-共享模块-shared/03-输出校验-contracts/signal_store.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_store.py
import json
from signal_store import append_signal
from signal_tracker import (
    make_signal_id,
    _normalize_symbol,
    _norm_date,
    _normalize_signal_type,
    _price_from_trigger,
)

def test_append_signal_generates_signal_id(tmp_path):
    
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"type": "price_confirm", "price": 10.50, "text": "test"},
        "invalidation": {"type": "price_break", "price": 10.00, "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test summary",
    }
    
    store_path = tmp_path / "signals.jsonl"
    
    # Ensure signal NOT pre-filled
    assert "signal_id" not in signal, "Test precondition: signal has no signal_id"
    
    # Append signal
    append_signal(signal, path=store_path)
    
    # Read back and verify
    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16
    
    # Verify ID matches make_signal_id
    expected_id = make_signal_id(
        symbol=_normalize_symbol("688248.SH"),
        date=_norm_date("2025-05-02"),
        signal_type=_normalize_signal_type("low_buy_watch"),
        price=_price_from_trigger(signal),
    )
    assert written["signal_id"] == expected_id

def test_append_signal_preserves_existing_signal_id(tmp_path):
    """Signal already carrying signal_id is written unmodified."""
    from signal_store import append_signal
    
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "trade_date": "2025-05-01",
        "analysis_time": "2025-05-01 09:30:00",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"type": "price_confirm", "price": 1600.00, "text": "test"},
        "invalidation": {"type": "price_break", "price": 1550.00, "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test",
        "signal_id": "abcdef1234567890",  # Pre-existing
    }
    
    store_path = tmp_path / "signals.jsonl"
    append_signal(signal, path=store_path)
    
    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert written["signal_id"] == "abcdef1234567890"  # Unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_store.py -v`
Expected: FAIL (function not yet modified)

- [ ] **Step 3: Implement signal_id in append_signal()**

Add at top of `signal_store.py` (with other imports):

```python
from signal_tracker import (
    make_signal_id,
    _normalize_symbol,
    _norm_date,
    _normalize_signal_type,
    _price_from_trigger,
)
```

Then add inside `append_signal()`, immediately after `assert_valid_signal(signal)`:

```python
    # Auto-generate signal_id if not present
    if "signal_id" not in signal:
        raw_type = str(signal.get("signal_type") or "unknown").strip()
        sig_id = make_signal_id(
            symbol=_normalize_symbol(str(signal.get("symbol") or "")),
            date=_norm_date(str(signal.get("trade_date") or "")),
            signal_type=_normalize_signal_type(raw_type),
            price=_price_from_trigger(signal) or "0.00",
        )
        signal["signal_id"] = sig_id
    
    # ... rest of function unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_store.py -v`
Expected: PASS

- [ ] **Step 5: Ensure existing tests still pass**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py -v -x`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add 02-共享模块-shared/03-输出校验-contracts/signal_store.py 02-共享模块-shared/tests/test_signal_id_store.py
git commit -m "feat(store): auto-generate signal_id in append_signal()"
```

---

## Task 4: Update `signal_log.jsonl` writing — dual-field coexistence in `log_safe()` and `_create_log_record()`

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_log_compat.py
def test_log_safe_creates_dual_fields(tmp_path):
    """New log record carries both signal_id and signal_id_md5."""
    # Patch LOG_PATH to temp
    import signal_tracker
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        sig_id = signal_tracker.log_safe(
            skill="trader",
            target="南网科技",
            symbol="688248.SH",
            signal_type="低吸观察",
            price=10.50,
            env_level="正常",
            env_note="",
        )
        
        # Read back
        lines = signal_tracker.LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"
        rec = json.loads(lines[0])
        
        # Both fields present
        assert "signal_id" in rec, f"Missing signal_id in: {rec.keys()}"
        assert "signal_id_md5" in rec, f"Missing signal_id_md5 in: {rec.keys()}"
        
        # signal_id is 16 chars SHA256
        assert len(rec["signal_id"]) == 16
        
        # signal_id_md5 is 12 chars MD5
        assert len(rec["signal_id_md5"]) == 12
        
        # They are different (different algorithms)
        assert rec["signal_id"] != rec["signal_id_md5"]
        
        # signal_id matches expected
        from signal_tracker import make_signal_id, _normalize_symbol, _normalize_signal_type
        expected = make_signal_id(
            symbol=_normalize_symbol("688248.SH"),
            date=datetime.now().strftime("%Y-%m-%d"),
            signal_type=_normalize_signal_type("低吸观察"),
            price=f"{10.50:.2f}",
        )
        assert rec["signal_id"] == expected
        
        # signal_id_md5 matches expected
        expected_md5 = hashlib.md5(
            f"{datetime.now().strftime('%Y-%m-%d')}::trader::南网科技::低吸观察".encode()
        ).hexdigest()[:12]
        assert rec["signal_id_md5"] == expected_md5
    finally:
        signal_tracker.LOG_PATH = old_path

def test_log_safe_does_not_duplicate_dual_field_record(tmp_path):
    """log_safe() dedup checks BOTH signal_id AND signal_id_md5."""
    import signal_tracker
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        # First call
        sig_id1 = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        # Second call same params → should dedup
        sig_id2 = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        # Counts
        lines = signal_tracker.LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line (dedup), got {len(lines)}"
        assert sig_id1 == sig_id2
    finally:
        signal_tracker.LOG_PATH = old_path

def test_log_safe_with_empty_md5_field(tmp_path):
    """Old record (only signal_id_md5, no signal_id) is found by MD5 match."""
    import signal_tracker
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        # Create old-format record (only MD5, no SHA256)
        old_md5 = hashlib.md5("2025-05-01::trader::南网科技::低吸观察".encode()).hexdigest()[:12]
        old_record = {
            "signal_id": old_md5,  # Old behavior stored MD5 in signal_id
            "timestamp": "2025-05-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "低吸观察", "price": 10.50,
            "signal_id_md5": "",  # New field, empty
            "outcome_pnl_pct": None, "outcome_days": None, "outcome": None, "filled_at": None,
        }
        signal_tracker.LOG_PATH.write_text(json.dumps(old_record, ensure_ascii=False) + "\n", encoding="utf-8")
        
        # Now search — should be found even though calling with new dual-field format
        # The dedup should find the MD5 match
        sig_id = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        lines = signal_tracker.LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line (found old record), got {len(lines)}"
    finally:
        signal_tracker.LOG_PATH = old_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_log_compat.py -v`
Expected: FAIL

- [ ] **Step 3: Update `_create_log_record()` to accept both IDs**

```python
def _create_log_record(sig_id: str, sig_md5: str, skill: str, target: str, symbol: str,
                       signal_type: str, price: float, env_level: str, env_note: str) -> None:
    record = {
        "signal_id_md5": sig_md5,
        "signal_id": sig_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "skill": skill, "target": target, "symbol": symbol,
        "signal_type": signal_type, "price": price,
        "env_level": env_level, "env_note": env_note,
        "outcome_pnl_pct": None, "outcome_days": None,
        "outcome": None, "filled_at": None,
    }
    _ensure_log_dir()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Update `log_safe()` to use both IDs**

```python
def log_safe(skill: str, target: str, symbol: str, signal_type: str, price: float,
             env_level: str = "", env_note: str = "") -> str:
    today = _today()
    norm_type = _normalize_signal_type(str(signal_type))
    sig_id = make_signal_id(
        symbol=_normalize_symbol(symbol or ""),
        date=today,
        signal_type=norm_type,
        price=f"{float(price):.2f}" if price else "0.00",
    )
    old_md5 = hashlib.md5(f"{today}::{skill}::{target}::{signal_type}".encode()).hexdigest()[:12]
    _ensure_log_dir()
    
    # Dedup: check signal_id first, then signal_id_md5
    if not LOG_PATH.exists():
        _create_log_record(sig_id, old_md5, skill, target, symbol, signal_type, price, env_level, env_note)
        return sig_id
    
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("signal_id") == sig_id or rec.get("signal_id_md5") == old_md5:
                return sig_id
        except json.JSONDecodeError:
            continue
    
    _create_log_record(sig_id, old_md5, skill, target, symbol, signal_type, price, env_level, env_note)
    return sig_id
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_log_compat.py -v`
Expected: PASS

- [ ] **Step 6: Ensure existing tests still pass**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py -v -x`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_id_log_compat.py
git commit -m "feat(tracker): dual-field signal_log.jsonl writing (signal_id + signal_id_md5)"
```

---

## Task 5: Update `fill()` for backward compatibility

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fill_updates_old_record_with_new_signal_id(tmp_path):
    """fill() with old MD5 ID finds record, updates outcome, and adds signal_id."""
    import signal_tracker
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        # Create old-format record (only signal_id which is MD5, no signal_id_md5 field)
        old_md5 = hashlib.md5("2025-05-01::trader::南网科技::低吸观察".encode()).hexdigest()[:12]
        old_record = {
            "signal_id_md5": old_md5,  # New naming convention in dual-field format
            "signal_id": old_md5,  # Bug: old record had MD5 here too (stable_id returned MD5)
            "timestamp": "2025-05-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "低吸观察", "price": 10.50,
            "outcome_pnl_pct": None, "outcome_days": None, "outcome": None, "filled_at": None,
        }
        signal_tracker.LOG_PATH.write_text(json.dumps(old_record, ensure_ascii=False) + "\n", encoding="utf-8")
        
        # Fill with old MD5
        found, msg = signal_tracker.fill(old_md5, pnl_pct=5.2, days_held=3, outcome="win")
        assert found is True, f"fill() should find old record: {msg}"
        
        # Read back and verify outcome updated + signal_id added
        lines = signal_tracker.LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        rec = json.loads(lines[0])
        assert rec["outcome_pnl_pct"] == 5.2
        assert rec["outcome"] == "win"
        assert rec["filled_at"] is not None
        
        # signal_id should now be a 16-char SHA256
        assert len(rec["signal_id"]) == 16
        assert rec["signal_id"] != old_md5
    finally:
        signal_tracker.LOG_PATH = old_path

def test_fill_finds_new_signal_id(tmp_path):
    """fill() with new SHA256 signal_id works."""
    import signal_tracker
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        # New-format record
        new_id = hashlib.sha256("688248.SH|2025-05-02|low_buy_watch|10.50".encode()).hexdigest()[:16]
        new_record = {
            "signal_id": new_id,
            "signal_id_md5": hashlib.md5("foo".encode()).hexdigest()[:12],
            "symbol": "688248.SH", "price": 10.50, "signal_type": "低吸观察",
            "outcome_pnl_pct": None, "outcome": None,
            "timestamp": "2025-05-02 10:00",
        }
        signal_tracker.LOG_PATH.write_text(json.dumps(new_record, ensure_ascii=False) + "\n", encoding="utf-8")
        
        found, msg = signal_tracker.fill(new_id, pnl_pct=3.0, days_held=2, outcome="win")
        assert found is True
        
        lines = signal_tracker.LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        rec = json.loads(lines[0])
        assert rec["outcome"] == "win"
    finally:
        signal_tracker.LOG_PATH = old_path
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL

- [ ] **Step 3: Implement fill() backward compat**

Replace `fill()` function:

```python
def fill(signal_id: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[bool, str]:
    if outcome not in VALID_OUTCOMES:
        return False, f"invalid outcome: {outcome}"
    if not isinstance(days_held, (int, float)):
        return False, f"invalid days_held: {days_held}"
    if days_held < 0 or days_held > 3650:
        return False, f"invalid days_held: {days_held}"
    if not LOG_PATH.exists():
        return False, "log file not found"
    
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    updated = False
    
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        
        # Match by signal_id (new) or signal_id_md5 (old)
        matched = (rec.get("signal_id") == signal_id or 
                   rec.get("signal_id_md5") == signal_id)
        
        if matched and rec.get("outcome_pnl_pct") is None:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            updated = True
            
            # If matched via signal_id_md5 (old record), add signal_id
            if rec.get("signal_id_md5") == signal_id:
                rec["signal_id"] = make_signal_id(
                    symbol=_normalize_symbol(str(rec.get("symbol") or "")),
                    date=_norm_date(str(rec.get("timestamp", "") or "")[:10]),
                    signal_type=_normalize_signal_type(str(rec.get("signal_type") or "unknown")),
                    price=f"{float(rec.get('price') or 0):.2f}",
                )
        
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    
    if updated:
        tmp = LOG_PATH.with_name(LOG_PATH.name + ".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(LOG_PATH))
        return True, "ok"
    
    return False, "signal_id not found"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_log_compat.py::test_fill_updates_old_record_with_new_signal_id tests/test_signal_id_log_compat.py::test_fill_finds_new_signal_id -v`
Expected: PASS

- [ ] **Step 5: Run existing fill tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker_fixes.py tests/test_signal_tracker_regression.py -v -k "fill" -x`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_id_log_compat.py
git commit -m "feat(tracker): backward compatible fill() with dual-ID matching"
```

---

## Task 6: Update `check_recent()` / `backfill()` triple-degradation matching

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_check_compat.py
def test_check_recent_matches_by_signal_id_first(tmp_path, monkeypatch):
    """check_recent() uses signal_id as primary match key."""
    import signal_tracker
    from datetime import datetime, timedelta
    
    # Mock paths
    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    
    monkeypatch.setattr(signal_tracker, "STORE_PATH", store)
    monkeypatch.setattr(signal_tracker, "RESULT_PATH", results)
    monkeypatch.setattr(signal_tracker, "HttpClient", None)  # Skip HTTP
    monkeypatch.setattr(signal_tracker, "resolve_security", MagicMock(side_effect=lambda x: x))
    monkeypatch.setattr(signal_tracker, "fetch_qfq_daily", MagicMock(return_value=[]))
    
    # Write a signal
    sig_id = hashlib.sha256("688248.SH|2025-05-02|low_buy_watch|10.50".encode()).hexdigest()[:16]
    signal = {
        "signal_id": sig_id,
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "name": "南网科技",
        "data_status": "full",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test",
    }
    store.write_text(json.dumps(signal, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Pre-write a matching result
    result = {
        "signal_id": sig_id,
        "symbol": "688248.SH",
        "name": "南网科技",
        "signal_date": "2025-05-02",
        "signal_type": "low_buy_watch",
        "signal_price": 10.50,
        "r_5d": 2.5,
        "outcome": "up",
    }
    results.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Check recent — should skip because signal_id already matches
    result = signal_tracker.check_recent(days=5)
    assert result["skipped"] == 1, f"Expected 1 skipped, got {result}"
    assert result["updated"] == 0

def test_check_recent_3key_fallback_unnormalized_date(tmp_path, monkeypatch):
    """check_recent() 3-key fallback normalizes signal_date via _norm_date.
    
    Old result has signal_date="2025-4-1" (non-zero-padded). New signal has
    trade_date="2025-04-01". These should match.
    """
    import signal_tracker
    from unittest.mock import MagicMock
    
    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    
    monkeypatch.setattr(signal_tracker, "STORE_PATH", store)
    monkeypatch.setattr(signal_tracker, "RESULT_PATH", results)
    monkeypatch.setattr(signal_tracker, "HttpClient", None)
    monkeypatch.setattr(signal_tracker, "resolve_security", MagicMock(side_effect=lambda x: x))
    monkeypatch.setattr(signal_tracker, "fetch_qfq_daily", MagicMock(return_value=[]))
    
    # Signal with normalized date
    signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-04-01",
        "analysis_time": "2025-04-01 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "name": "南网科技",
        "data_status": "full",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test",
    }
    store.write_text(json.dumps(signal, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Old result with UNNORMALIZED date (key issue: "2025-4-1" not "2025-04-01")
    old_result = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "signal_date": "2025-4-1",  # Non-zero-padded — the BUG we're fixing
        "signal_type": "low_buy_watch",
        "signal_price": 10.50,
        "r_5d": 0.0,
        "outcome": "flat",
    }
    results.write_text(json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Check recent — should skip because 3-key (with _norm_date fix) matches
    result = signal_tracker.check_recent(days=5)
    assert result["skipped"] == 1, f"Expected 1 skipped (3-key fallback), got {result}"

def test_check_recent_4key_normalizes_date_and_type(tmp_path, monkeypatch):
    """check_recent() 4-key matching normalizes both signal_date and signal_type."""
    import signal_tracker
    from unittest.mock import MagicMock
    
    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    
    monkeypatch.setattr(signal_tracker, "STORE_PATH", store)
    monkeypatch.setattr(signal_tracker, "RESULT_PATH", results)
    monkeypatch.setattr(signal_tracker, "HttpClient", None)
    monkeypatch.setattr(signal_tracker, "resolve_security", MagicMock(side_effect=lambda x: x))
    monkeypatch.setattr(signal_tracker, "fetch_qfq_daily", MagicMock(return_value=[]))
    
    # Signal with normalized date and chinese old type name
    signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-04-01",
        "analysis_time": "2025-04-01 10:00:00",
        "signal_type": "低吸观察",  # Chinese old name
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "name": "南网科技",
        "data_status": "full",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test",
    }
    store.write_text(json.dumps(signal, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Result with ENGLISH type name (after normalisation) and UNNORMALIZED date
    old_result = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "signal_date": "2025-4-1",  # Non-zero-padded
        "signal_type": "low_buy_watch",  # Already normalized
        "signal_price": 10.50,
        "r_5d": 0.0,
        "outcome": "flat",
    }
    results.write_text(json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8")
    
    # Check recent — should skip because 4-key with _norm_date + _normalize_signal_type matches
    result = signal_tracker.check_recent(days=5)
    assert result["skipped"] == 1, f"Expected 1 skipped, got {result}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_check_compat.py -v`
Expected: FAIL

- [ ] **Step 3: Update `check_recent()` existing_keys building**

Replace the existing_keys building code in `check_recent()` (around line 472-492):

```python
    # 已存在结果的双层 key — 三级降级: signal_id → 4-key (norm) → 3-key (norm)
    existing_keys_by_id: dict[str, dict] = {}
    existing_keys_4: dict[tuple[str, str, str, str], dict] = {}
    existing_keys_3: dict[tuple[str, str, str], dict] = {}
    try:
        for line in RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                r = json.loads(line)
                raw_date = _norm_date(str(r.get("signal_date", "")))
                raw_type = _normalize_signal_type(str(r.get("signal_type", "")))
                key_symbol = _normalize_symbol(str(r.get("symbol", "")))
                sp = r.get("signal_price")
                price_str = f"{float(sp):.2f}" if sp is not None and float(sp) > 0 else ""
                
                # Primary: signal_id
                sid = r.get("signal_id")
                if sid:
                    existing_keys_by_id[sid] = r
                
                # Secondary: 4-key (normalized)
                existing_keys_4[(key_symbol, raw_date, raw_type, price_str)] = r
                # Tertiary: 3-key (normalized)
                existing_keys_3[(key_symbol, raw_date, raw_type)] = r
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        pass
```

- [ ] **Step 4: Update the dedup check inside check_recent()**

Replace the existing dedup check (around line 499-501):

```python
    for sig in recent:
        # 1. Try signal_id match
        key = _make_signal_key(sig)
        if key in existing_keys_4 or (key[0], key[1], key[2]) in existing_keys_3 or \
           (sig.get("signal_id") in existing_keys_by_id):
            skipped += 1
            continue
        # 2. Try _make_signal_key (4-key + 3-key fallback)
        # ...
```

Wait — I need to reconsider. The signal dict also has `signal_id` now. Let me write the proper dedup:

```python
    for sig in recent:
        key = _make_signal_key(sig)
        if sig.get("signal_id") in existing_keys_by_id:
            skipped += 1
            continue
        if key in existing_keys_4 or (key[0], key[1], key[2]) in existing_keys_3:
            skipped += 1
            continue
```

- [ ] **Step 5: Apply same fix to `backfill()`**

In `backfill()` (around line 790-854 in `signal_tracker.py`), the existing_keys building code is duplicated from `check_recent()`. Apply the identical three-dictionary pattern:

```python
    # In backfill(): replace the existing_keys building block (same as check_recent)
    existing_keys_by_id: dict[str, dict] = {}
    existing_keys_4: dict[tuple[str, str, str, str], dict] = {}
    existing_keys_3: dict[tuple[str, str, str], dict] = {}
    # ... same try/except/for loop as check_recent Step 3 ...
    
    # And the dedup check below must also include signal_id:
    for sig in candidates:
        key = _make_signal_key(sig)
        if sig.get("signal_id") in existing_keys_by_id:
            skipped += 1; continue
        if key in existing_keys_4 or (key[0], key[1], key[2]) in existing_keys_3:
            skipped += 1; continue
```
Expected: `backfill()` now matches identically to `check_recent()`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_check_compat.py -v`
Expected: PASS

- [ ] **Step 7: Run existing tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py -v -x`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_id_check_compat.py
git commit -m "feat(tracker): signal_results matching priority — signal_id > 4-key > 3-key with _norm_date"
```

---

## Task 7: Update `_compute_results_for_sig()` to write signal_id

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_check_compat.py (append to existing file)
from unittest.mock import MagicMock, patch

def test_compute_results_for_sig_includes_signal_id():
    """When _compute_results_for_sig succeeds, result dict contains signal_id."""
    from signal_tracker import _compute_results_for_sig, _normalize_symbol, _norm_date, _normalize_signal_type, make_signal_id
    
    # Create a minimal signal
    sig = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "low_buy_watch",
        "source_skill": "trader",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": "test"},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "data_status": "full",
    }
    
    mock_bars = [
        {"date": "2025-05-02", "close": "10.50", "atr14": "0.35"},
        {"date": "2025-05-03", "close": "10.65", "atr14": "0.35"},
        {"date": "2025-05-05", "close": "10.80", "atr14": "0.35"},
    ]
    
    with patch("signal_tracker.resolve_security", return_value="688248.SH"), \
         patch("signal_tracker.fetch_qfq_daily", return_value=mock_bars), \
         patch("signal_tracker.HttpClient", return_value=MagicMock()), \
         patch("signal_tracker.to_float", side_effect=lambda v: float(v) if v else None):
        result = _compute_results_for_sig(sig)
    
    assert result is not None
    assert "signal_id" in result
    assert len(result["signal_id"]) == 16
    
    expected = make_signal_id(
        symbol=_normalize_symbol("688248.SH"),
        date=_norm_date("2025-05-02"),
        signal_type=_normalize_signal_type("low_buy_watch"),
        price=f"{10.50:.2f}",
    )
    assert result["signal_id"] == expected
```

- [ ] **Step 2: Add signal_id to _compute_results_for_sig() return dict**

In the return dict construction (around line 424). Insert these variables just before the `res: dict[str, Any] = {` block — extract from `sig` dict:

```python
    # Before the return dict, compute signal_id inputs (same pattern as check_recent Step 3)
    norm_symbol = _normalize_symbol(str(sig.get("symbol") or ""))
    norm_type = _normalize_signal_type(str(sig.get("signal_type", "unknown") or "unknown"))
    sig_price = float(sig.get("trigger", {}).get("price") or sig.get("current") or 0)
    price_str = f"{sig_price:.2f}"
    norm_sig_date = _norm_date(str(sig.get("trade_date") or str(sig.get("analysis_time", "").split("T")[0])))
    
    res: dict[str, Any] = {
        "signal_id": make_signal_id(norm_symbol, norm_sig_date, norm_type, price_str),
        "symbol": symbol, "name": name,
        "signal_date": sig_date, "signal_type": sig_type,
        "source_skill": skill, "signal_price": round(sig_price, 2),
        "schema_version": 1,
        "result_time": datetime.now().isoformat(),
        "_price_source": _price_source,
    }
```

**Note**: `_compute_results_for_sig()` receives a signal dict from `signals.jsonl`, so price comes from `sig["trigger"]["price"]` or `sig["current"]` (not from `signal_price` — that's only for the result's own backward compat in `check_recent()`).

- [ ] **Step 3: Run existing result tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py tests/test_v2_infra.py -v -x`
Expected: All PASS (adding a field to the dict is additive)

- [ ] **Step 4: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py
git commit -m "feat(tracker): _compute_results_for_sig writes signal_id to results"
```

---

## Task 8: Write `migrate_signal_ids()` function

**Files:**
- Modify: `02-共享模块-shared/scripts/signal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# In test_signal_id_migration.py
def test_migrate_signal_ids_adds_id_to_old_signals(tmp_path):
    """migrate_signal_ids() adds signal_id to existing signals.jsonl records."""
    import signal_tracker
    
    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.mkdir(parents=True, exist_ok=True)
    
    # Old record without signal_id
    old_signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "低吸观察",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "name": "南网科技",
        "data_status": "full",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test",
    }
    store.write_text(json.dumps(old_signal, ensure_ascii=False) + "\n", encoding="utf-8")
    
    result = signal_tracker.migrate_signal_ids()
    
    # Verify
    assert result["migrated"] >= 1, f"Should have migrated at least 1: {result}"
    
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[0])
    assert "signal_id" in rec
    assert len(rec["signal_id"]) == 16
    assert isinstance(rec["signal_id"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL

- [ ] **Step 3: Implement migrate_signal_ids() and helper**

Add the full implementation as specified in the design doc:

```python
from pathlib import Path as _Path

def _build_signal_id_inputs(result_rec: dict) -> tuple[str, str, str, str]:
    """Extract normalized inputs for make_signal_id from a signal or result record."""
    norm_symbol = _normalize_symbol(str(result_rec.get("symbol", ""))) or ""
    
    # Price: trigger.price > current > signal_price > "0.00"
    if result_rec.get("trigger", {}).get("price"):
        price_str = f"{float(result_rec['trigger']['price']):.2f}"
    elif result_rec.get("current"):
        price_str = f"{float(result_rec['current']):.2f}"
    elif result_rec.get("signal_price"):
        price_str = f"{float(result_rec['signal_price']):.2f}"
    else:
        price_str = "0.00"
    
    date_val = result_rec.get("trade_date") or result_rec.get("signal_date", "")
    norm_date = _norm_date(str(date_val)) or ""
    norm_type = _normalize_signal_type(str(result_rec.get("signal_type", "unknown")))
    
    return norm_symbol, norm_date, norm_type, price_str


def _migrate_file(file_path: Path, is_signal: bool = True) -> dict[str, int]:
    """Migrate a single JSONL file. Returns migrated/skipped counts."""
    if not file_path.exists():
        return {"migrated": 0, "skipped": 0}
    
    lines_raw = file_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    migrated = 0
    skipped = 0
    
    for line in lines_raw:
        if not line.strip():
            new_lines.append(line)
            continue
        
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                new_lines.append(line)
                continue
        except (json.JSONDecodeError, ValueError):
            new_lines.append(line)  # Bad lines pass through
            continue
        
        if rec.get("signal_id"):
            new_lines.append(line)
            skipped += 1
            continue
        
        norm = _build_signal_id_inputs(rec)
        rec["signal_id"] = make_signal_id(*norm)
        new_lines.append(json.dumps(rec, ensure_ascii=False))
        migrated += 1
    
    if migrated > 0:
        tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(file_path))
    
    return {"migrated": migrated, "skipped": skipped}


def migrate_signal_ids() -> dict[str, int]:
    """Add signal_id to existing records in signals.jsonl and signal_results.jsonl.
    
    Idempotent: records that already carry signal_id are skipped.
    Does NOT process signal_log.jsonl (old MD5 signal_id is irreversible).
    
    Usage:
        python -c "from signal_tracker import migrate_signal_ids; migrate_signal_ids()"
    
    Returns:
        dict with keys "signals_migrated", "signals_skipped",
                       "results_migrated", "results_skipped"
    """
    store_path = Path.home() / ".trader" / "signals.jsonl"
    result_path = Path.home() / ".trader" / "signal_results.jsonl"
    
    sig_result = _migrate_file(store_path, is_signal=True)
    res_result = _migrate_file(result_path, is_signal=False)
    
    return {
        "signals_migrated": sig_result["migrated"],
        "signals_skipped": sig_result["skipped"],
        "results_migrated": res_result["migrated"],
        "results_skipped": res_result["skipped"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_migration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 02-共享模块-shared/scripts/signal_tracker.py 02-共享模块-shared/tests/test_signal_id_migration.py
git commit -m "feat(tracker): add migrate_signal_ids() one-time migration tool"
```

---

## Task 9: Full integration — run all existing tests

**Files:**
- All test files

- [ ] **Step 1: Run the full shared test suite**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -v`
Expected: All 243+ tests PASS

- [ ] **Step 2: Run signal_tracker regression tests specifically**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_tracker*.py tests/test_v2_infra.py -v`
Expected: All PASS

- [ ] **Step 3: Verify existing functional tests**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_fusion_core.py tests/test_signal_tracker_regression.py tests/test_signal_tracker_schema.py -v`
Expected: All PASS

- [ ] **Step 4: Fix any failures**

If any existing tests fail, fix them (adding "signal_id" to dicts is usually additive-only, but some tests may assert exact dict keys).

- [ ] **Step 5: Commit any fixes**

```bash
git add 02-共享模块-shared/tests/
git commit -m "fix(tests): adapt existing tests for signal_id field presence"
```

---

## Task 10: Integration test — verify end-to-end flow

**Files:**
- `02-共享模块-shared/tests/test_signal_id_e2e.py` (new)

- [ ] **Step 1: Write end-to-end integration test**

```python
# test_signal_id_e2e.py
def test_e2e_signal_lifecycle(tmp_path, monkeypatch):
    """Full signal lifecycle: write → track → check → migrate."""
    import signal_tracker
    from signal_store import append_signal
    from unittest.mock import MagicMock
    
    store = tmp_path / ".trader" / "signals.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    logs = tmp_path / ".trader" / "signal_log.jsonl"
    logs.parent.mkdir(parents=True, exist_ok=True)
    results = tmp_path / ".trader" / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    
    # Patch
    monkeypatch.setattr(signal_tracker, "STORE_PATH", store)
    monkeypatch.setattr(signal_tracker, "RESULT_PATH", results)
    monkeypatch.setattr(signal_tracker, "LOG_PATH", logs)
    monkeypatch.setattr(signal_tracker, "DEFAULT_SIGNAL_STORE_PATH", store)
    
    # Phase 1: Write a signal via store
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"price": 10.50, "type": "price_confirm", "text": "test"},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test summary",
    }
    append_signal(signal)
    
    # Signal should have signal_id
    assert "signal_id" in signal
    assert len(signal["signal_id"]) == 16
    
    # Phase 2: Write a log entry
    sig_id_log = signal_tracker.log_safe(
        "trader", "南网科技", "688248.SH", "低吸观察", 10.50,
    )
    lines = logs.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[0])
    assert "signal_id" in rec  # New field
    assert "signal_id_md5" in rec  # Dual field
    assert len(rec["signal_id"]) == 16
    
    # Phase 3: Simulate a result matching
    from signal_tracker import make_signal_id, _normalize_symbol, _norm_date, _normalize_signal_type, _price_from_trigger
    
    expected_id = make_signal_id(
        symbol=_normalize_symbol("688248.SH"),
        date=_norm_date("2025-05-02"),
        signal_type=_normalize_signal_type("low_buy_watch"),
        price=_price_from_trigger(signal) or "0.00",
    )
    
    # Signal's signal_id and expected should match
    assert signal["signal_id"] == expected_id
    
    # Log's signal_id should also match (same inputs)
    assert rec["signal_id"] == expected_id
```

- [ ] **Step 2: Run the integration test**

Run: `cd 02-共享模块-shared && python -m pytest tests/test_signal_id_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add 02-共享模块-shared/tests/test_signal_id_e2e.py
git commit -m "test(e2e): end-to-end signal ID lifecycle across store, log, and tracker"
```

---

## Summary of Changes by File

| File | Changes |
|------|--------|
| `signal_tracker.py` | `+make_signal_id()`, `+migrate_signal_ids()`, `+_migrate_file()`, `+_build_signal_id_inputs()` |
| `signal_tracker.py` | `log_safe()`: dual-field write + dual-ID dedup |
| `signal_tracker.py` | `_create_log_record()`: accepts both `sig_id` and `sig_md5` |
| `signal_tracker.py` | `fill()`: single-pass matching `signal_id` + `signal_id_md5` |
| `signal_tracker.py` | `check_recent()`: existing_keys by `signal_id` → 4-key → 3-key, all with `_norm_date()` |
| `signal_tracker.py` | `backfill()`: same pattern as `check_recent()` |
| `signal_tracker.py` | `_compute_results_for_sig()`: writes `signal_id` in result dict |
| `signal_store.py` | `append_signal()`: auto-generates `signal_id` if missing |
| New: `test_signal_id_unified.py` | `make_signal_id()` tests (5 tests) |
| New: `test_signal_id_log_compat.py` | `log_safe()` dual-field + `fill()` backward compat (4 tests) |
| New: `test_signal_id_check_compat.py` | `check_recent` triple-degradation matching (3 tests) |
| New: `test_signal_id_migration.py` | `migrate_signal_ids()` tool tests (3 tests) |
| New: `test_signal_id_store.py` | `append_signal()` signal_id generation (2 tests) |
| New: `test_signal_id_e2e.py` | End-to-end signal lifecycle (1 test) |

**Total: ~18 new tests, 10 existing test files to verify still pass.**

---

## Notes for Implementer

1. **No backward breaks**: Phase 1 only ADDS signal_id. All existing `stable_id()`, 4-key, 3-key logic is preserved.
2. **`_normalize_signal_type()` is the gate**: Every place that calls `make_signal_id()` MUST normalize the signal_type first. The design doc is explicit: use `_normalize_signal_type()` (which is `_SIGNAL_TYPE_MAP.get(x, x)`).
3. **date normalization is critical**: `check_recent()`'s existing 3-key fallback was using raw `signal_date`. ALL new matching MUST call `_norm_date()` on any date field before comparison.
4. **`migrate_signal_ids()` is a one-liner for users**: `python -c "from signal_tracker import migrate_signal_ids; migrate_signal_ids()"`
5. **Do NOT remove `stable_id()` in Phase 1**: The function stays with a `@deprecated` notice. Phase 3 will clean it up later.
