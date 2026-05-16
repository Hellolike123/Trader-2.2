import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

from signal_tracker import (
    SIGNAL_STATUS_VALUES,
    signal_is_trackable,
    set_signal_status,
)

def test_signal_is_trackable_no_status():
    assert signal_is_trackable({}) is True
    assert signal_is_trackable({"status": ""}) is True
    assert signal_is_trackable({"signal_type": "track"}) is True

def test_signal_is_trackable_active():
    assert signal_is_trackable({"status": "active"}) is True

def test_signal_is_trackable_completed():
    assert signal_is_trackable({"status": "completed"}) is False

def test_signal_is_trackable_expired():
    assert signal_is_trackable({"status": "expired"}) is False

def test_set_signal_status_valid():
    rec = {}
    set_signal_status(rec, "active")
    assert rec["status"] == "active"
    assert "status_updated_at" in rec

def test_set_signal_status_invalid_value():
    import pytest
    rec = {}
    with pytest.raises(ValueError):
        set_signal_status(rec, "invalid")

def test_set_signal_status_forbidden_transition():
    import pytest
    rec = {"status": "completed"}
    with pytest.raises(ValueError):
        set_signal_status(rec, "active")

def test_set_signal_status_allowed_transition():
    rec = {"status": "active"}
    set_signal_status(rec, "completed")
    assert rec["status"] == "completed"

def test_signal_status_values():
    assert SIGNAL_STATUS_VALUES == {"active", "completed", "expired"}


import json
from unittest.mock import MagicMock, patch


def test_check_recent_skips_completed(tmp_path, monkeypatch):
    """check_recent should skip signals with status=completed (lifecycle_skipped)."""
    import signal_tracker as st

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    signal = {
        "symbol": "688248.SH", "trade_date": "2026-05-12",
        "signal_type": "low_buy_watch", "status": "completed",
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


def test_backfill_signal_status(tmp_path, monkeypatch):
    """Signals with matching results get status=completed after backfill."""
    import signal_tracker as st
    import json

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    sig = {"symbol": "688248.SH", "signal_type": "track", "signal_id": "abc"}
    store.write_text(json.dumps(sig) + "\n", encoding="utf-8")

    result = {"signal_id": "abc", "r_5d": 2.5, "outcome": "up"}
    results.write_text(json.dumps(result) + "\n", encoding="utf-8")

    st.backfill_signal_status()

    updated = json.loads(store.read_text(encoding="utf-8").strip().splitlines()[0])
    assert updated.get("status") == "completed"
    assert "status_updated_at" in updated


def test_check_recent_sets_completed_on_signal(tmp_path, monkeypatch):
    """After computing result, signal's status in signals.jsonl becomes completed."""
    import signal_tracker as st

    store = tmp_path / "signals.jsonl"
    results = tmp_path / "signal_results.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(st, "STORE_PATH", store)
    monkeypatch.setattr(st, "RESULT_PATH", results)

    signal = {
        "symbol": "688248.SH", "trade_date": "2026-05-12",
        "signal_type": "low_buy_watch",
        "trigger": {"price": 10.5},
    }
    store.write_text(json.dumps(signal) + "\n", encoding="utf-8")

    bars = [{"date": "2026-05-12", "close": 10.5, "atr14": 0.3}]

    with patch.object(st, "HttpClient", return_value=MagicMock()), \
         patch.object(st, "resolve_security", return_value="688248.SH"), \
         patch.object(st, "fetch_qfq_daily", return_value=bars), \
         patch.object(st, "to_float", side_effect=lambda v: float(v) if v else None):
        result = st.check_recent(days=5)

    assert result.get("updated", 0) >= 1, f"Should compute result: {result}"
    updated_signal = json.loads(store.read_text(encoding="utf-8").strip().splitlines()[0])
    assert updated_signal.get("status") == "completed", "Signal should be marked completed"
    assert "status_updated_at" in updated_signal
