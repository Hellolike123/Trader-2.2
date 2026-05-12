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
