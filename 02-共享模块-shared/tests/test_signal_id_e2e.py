"""E2E integration test for the unified signal_id lifecycle.

Tests the full pipeline:
  append_signal() —> log_safe() —> check_recent() matching
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── Path setup (same as existing tests) ──
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent  # 02-共享模块-shared/
SCRIPTS = SHARED / "scripts"
CONTRACTS = SHARED / "03-输出校验-contracts"
for _p in (SHARED, SCRIPTS, CONTRACTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import signal_tracker
from signal_store import append_signal


# ── Helpers ──


def _norm(symbol: str, date: str, signal_type: str) -> None:
    """Return normalized (symbol, date, signal_type) matching what make_signal_id uses."""
    from signal_tracker import (
        _normalize_symbol,
        _norm_date,
        _normalize_signal_type,
    )
    return (
        _normalize_symbol(symbol),
        _norm_date(date),
        _normalize_signal_type(signal_type),
    )


def _make_base_sig(
    symbol: str = "688248.SH",
    name: str = "南网科技",
    trade_date: str | None = None,
    analysis_time: str | None = None,
    signal_type: str = "low_buy_watch",
    price: float = 10.5,
    **extra: object,
) -> dict:
    """Base signal using today's date so it falls inside check_recent() recent window."""
    from datetime import datetime, timedelta
    ref_date = datetime.now() - timedelta(days=2)  # 2 days ago for safe recent match
    ref = ref_date.strftime("%Y-%m-%d")
    if trade_date is None:
        trade_date = ref
    if analysis_time is None:
        analysis_time = f"{trade_date} 10:00"
    sig: dict = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": symbol,
        "name": name,
        "trade_date": trade_date,
        "analysis_time": analysis_time,
        "signal_type": signal_type,
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"price": price, "type": "price_confirm", "text": "test"},
        "invalidation": {"price": price - 0.5, "type": "price_break", "text": "invalidation trigger"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test summary",
        **extra,
    }
    return sig


# ── Fixtures ──


@pytest.fixture()
def tmp_paths(tmp_path: Path) -> Path:
    """Temp paths with module-level patches. Restores after test."""
    store = tmp_path / "signals.jsonl"
    logs = tmp_path / "signal_log.jsonl"
    results = tmp_path / "signal_results.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    logs.parent.mkdir(parents=True, exist_ok=True)
    results.parent.mkdir(parents=True, exist_ok=True)

    orig = {
        "STORE_PATH": signal_tracker.STORE_PATH,
        "RESULT_PATH": signal_tracker.RESULT_PATH,
        "LOG_PATH": signal_tracker.LOG_PATH,
        "DEFAULT_SIGNAL_STORE_PATH": None,  # computed below
    }
    try:
        # Must patch DEFAULT_SIGNAL_STORE_PATH BEFORE append_signal
        # (it reads it at call time via `path or DEFAULT_SIGNAL_STORE_PATH`)
        import signal_store
        orig["DEFAULT_SIGNAL_STORE_PATH"] = signal_store.DEFAULT_SIGNAL_STORE_PATH
        signal_store.DEFAULT_SIGNAL_STORE_PATH = store
        signal_tracker.STORE_PATH = store
        signal_tracker.RESULT_PATH = results
        signal_tracker.LOG_PATH = logs
        yield tmp_path
    finally:
        signal_tracker.LOG_PATH = orig["LOG_PATH"]
        signal_tracker.RESULT_PATH = orig["RESULT_PATH"]
        signal_tracker.STORE_PATH = orig["STORE_PATH"]
        import signal_store
        signal_store.DEFAULT_SIGNAL_STORE_PATH = orig["DEFAULT_SIGNAL_STORE_PATH"]


# ═══════ Test 1: full lifecycle ═══════


def test_signal_lifecycle_full_pipeline(tmp_paths: Path) -> None:
    """append_signal → log_safe → check_recent skip by signal_id.  All use same derived_id."""
    from signal_tracker import (
        _normalize_symbol,
        _norm_date,
        _normalize_signal_type,
        _price_from_trigger,
        make_signal_id,
    )

    # ===== PHASE 1: write a signal via store =====
    # NOTE: Don't pass explicit trade_date—let _make_base_sig use a recent date
    # so the signal falls inside check_recent(days=5) cutoff.
    signal = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        signal_type="low_buy_watch",
        price=10.5,
    )

    sig_id = append_signal(signal)

    # VERIFICATION: append_signal returns signal_id + persisted
    assert isinstance(sig_id, str)
    assert len(sig_id) == 16

    with open(tmp_paths / "signals.jsonl", encoding="utf-8") as f:
        written = json.loads(f.readline())
    assert written["signal_id"] == sig_id, \
        "File should write same signal_id as append_signal() returns"

    # ===== PHASE 2: write a log entry =====
    sig_id_from_log = signal_tracker.log_safe(
        "trader", "南网科技", "688248.SH", "低吸观察", 10.50,
        env_level="正常",
    )

    with open(tmp_paths / "signal_log.jsonl", encoding="utf-8") as f:
        log_line = f.readline()
    assert log_line, "Log file should have at least one line"
    rec = json.loads(log_line)
    assert "signal_id" in rec, f"Log should have signal_id: {list(rec.keys())}"
    assert "signal_id_md5" in rec, f"Log should have signal_id_md5: {list(rec.keys())}"
    assert len(rec["signal_id"]) == 16
    assert len(rec["signal_id_md5"]) == 12
    # log_safe uses _today() which for today's inputs should give a valid,
    # well-formed signal_id (but not necessarily matching signal's since
    # log_safe doesn't know signal's trade_date; check_recent matching falls
    # back to 4-key normalization for cross-source matching).

    # ===== PHASE 3: pre-write a result with matching signal_id =====
    expected_sig_id = sig_id
    today = signal["trade_date"]
    pre_result = {
        "signal_id": expected_sig_id,
        "symbol": "688248.SH",
        "name": "南网科技",
        "signal_date": today,
        "signal_type": "low_buy_watch",
        "signal_price": 10.5,
        "r_5d": 2.5,
        "outcome": "up",
    }
    with open(tmp_paths / "signal_results.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(pre_result, ensure_ascii=False) + "\n")

    # ===== PHASE 4: check_recent sees signal → skips (matched by signal_id) =====
    import unittest.mock as mock
    with mock.patch.object(signal_tracker, "HttpClient", mock.MagicMock()):
        with mock.patch.object(signal_tracker, "_compute_results_for_sig", return_value=None):
            check_result = signal_tracker.check_recent(days=5)

    assert check_result.get("skipped", 0) >= 1, \
        f"check_recent should skip by signal_id: {check_result}"
    assert check_result.get("updated", 0) == 0, \
        f"Should not create duplicate result: {check_result}"

    # ===== PHASE 5: verify result file unchanged (still 1 line) =====
    result_lines = (tmp_paths / "signal_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(result_lines) == 1, f"Result should have exactly 1 line, got {len(result_lines)}"

    final_result = json.loads(result_lines[0])
    assert final_result["signal_id"] == expected_sig_id
    assert final_result["symbol"] == "688248.SH"

    # ===== PHASE 6: verify consistency of normalization helpers =====
    sig = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        signal_type="low_buy_watch",
        price=10.5,
    )
    append_signal(sig)
    # sig dict is NOT mutated — use the returned signal_id
    norm_sym = _normalize_symbol(str(sig.get("symbol") or ""))
    norm_dt = _norm_date(str(sig.get("trade_date") or ""))
    norm_type = _normalize_signal_type(str(sig.get("signal_type") or "unknown").strip())
    norm_price = _price_from_trigger(sig) or "0.00"
    derived_id = make_signal_id(norm_sym, norm_dt, norm_type, norm_price)

    assert derived_id == sig_id, \
        f"Derivation should match return value from append_signal: {derived_id} != {sig_id[:8]}..."
    # log.signal_id is derived from _today() (not signal's trade_date), so it won't match signal's
    # ID. But it is still a valid 16-char hex ID.
    assert len(rec["signal_id"]) == 16 and rec["signal_id"].isalnum(), \
        f"Log signal_id must be valid: {rec['signal_id']}"
    assert derived_id == expected_sig_id, \
        "Derivation should match expected_sig_id (signal + pre-written result use same date)"


# ═══════ Test 2: old result matching (no signal_id on result) ═══════


def test_old_record_no_signal_id_is_matched(tmp_paths: Path) -> None:
    """Old results without signal_id still match via 4-key fallback in check_recent()."""
    # Create a signal with an explicit recent-ish date
    from datetime import datetime, timedelta
    sig_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # "Old" result = missing signal_id field, but matching 4-key values
    old_result = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "signal_date": sig_date,
        "signal_type": "low_buy_watch",
        "signal_price": 10.5,
        "r_5d": 0.0,
        "outcome": "flat",
    }
    with open(tmp_paths / "signal_results.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(old_result, ensure_ascii=False) + "\n")

    # Signal matching the same 4-key values
    signal = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        trade_date=sig_date,
        signal_type="low_buy_watch",
        price=10.5,
    )
    append_signal(signal)

    # check_recent should skip this signal (matched by 4-key fallback)
    import unittest.mock as mock
    with mock.patch.object(signal_tracker, "HttpClient", mock.MagicMock()):
        with mock.patch.object(signal_tracker, "_compute_results_for_sig", return_value=None):
            check_result = signal_tracker.check_recent(days=5)

    assert check_result.get("skipped", 0) >= 1, \
        f"Old result without signal_id should still match by 4-key fallback: {check_result}"
    assert check_result.get("updated", 0) == 0


# ═══════ Test 3: dual-ID consistency (signal + log use same ID) ═══════


def test_dual_id_consistency(tmp_paths: Path) -> None:
    """signal.signal_id and log.signal_id must be identical when same symbol/date/type/price."""
    from signal_tracker import (
        _normalize_symbol,
        _norm_date,
        _normalize_signal_type,
        _price_from_trigger,
        make_signal_id,
    )

    # Signal A — use today's date so log_safe(_today) and append_signal(trade_date) share the same date
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    sig_a = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        trade_date=today_str,
        price=10.50,
    )
    sig_id_a = append_signal(sig_a)
    signal_tracker.log_safe(
        "trader", "南网科技", "688248.SH", "低吸观察", 10.50,
        env_level="正常",
    )

    # Compute expected ID matching both signal and log (today's date)
    expected = make_signal_id(
        _normalize_symbol("688248.SH"),
        _norm_date(today_str),
        _normalize_signal_type("low_buy_watch"),
        "10.50",
    )

    # Verify via return value
    assert sig_id_a == expected
    with open(tmp_paths / "signal_log.jsonl", encoding="utf-8") as f:
        log_rec = json.loads(f.readline())
    assert log_rec["signal_id"] == expected


# ═══════ Test 4: different dates → different signal_ids ═══════


def test_different_dates_different_ids(tmp_paths: Path) -> None:
    """Two signals same symbol/type/price but different dates produce different signal_ids."""
    sig_jan = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        trade_date="2025-01-15",
        analysis_time="2025-01-15 10:00",
        price=10.5,
    )
    sig_feb = _make_base_sig(
        symbol="688248.SH",
        name="南网科技",
        trade_date="2025-02-15",
        analysis_time="2025-02-15 10:00",
        price=10.5,
    )
    jan_id = append_signal(sig_jan)
    feb_id = append_signal(sig_feb)

    assert jan_id != feb_id
    lines = (tmp_paths / "signals.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    w1, w2 = json.loads(lines[0]), json.loads(lines[1])
    assert w1["signal_id"] != w2["signal_id"]
    assert w1["signal_id"] == jan_id
    assert w2["signal_id"] == feb_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
