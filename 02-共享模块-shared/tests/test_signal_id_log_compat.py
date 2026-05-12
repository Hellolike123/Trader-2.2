import sys
from pathlib import Path
_sh = Path(__file__).resolve().parent.parent / "scripts"
if str(_sh) not in sys.path:
    sys.path.insert(0, str(_sh))

import json
import hashlib
from datetime import datetime

import pytest


def test_log_safe_creates_dual_fields(tmp_path):
    """New log record carries both signal_id and signal_id_md5."""
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
        
        lines = (tmp_path / "signal_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"
        rec = json.loads(lines[0])
        
        assert "signal_id" in rec, f"Missing signal_id: {rec.keys()}"
        assert "signal_id_md5" in rec, f"Missing signal_id_md5: {rec.keys()}"
        
        assert len(rec["signal_id"]) == 16
        assert len(rec["signal_id_md5"]) == 12
        assert rec["signal_id"] != rec["signal_id_md5"]
        
        # Verify signal_id matches expected
        expected = signal_tracker.make_signal_id(
            symbol=signal_tracker._normalize_symbol("688248.SH"),
            date=datetime.now().strftime("%Y-%m-%d"),
            signal_type=signal_tracker._normalize_signal_type("低吸观察"),
            price=f"{10.50:.2f}",
        )
        assert rec["signal_id"] == expected
        
        # Verify signal_id_md5 matches expected
        today = datetime.now().strftime("%Y-%m-%d")
        expected_md5 = hashlib.md5(f"{today}::trader::南网科技::低吸观察".encode()).hexdigest()[:12]
        assert rec["signal_id_md5"] == expected_md5
    finally:
        signal_tracker.LOG_PATH = old_path


def test_log_safe_dedup_checking_both_fields(tmp_path):
    """log_safe() dedup checks BOTH signal_id AND signal_id_md5."""
    import signal_tracker
    
    old_path = signal_tracker.LOG_PATH
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    
    try:
        sig_id1 = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        sig_id2 = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        lines = (tmp_path / "signal_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line (dedup), got {len(lines)}"
        assert sig_id1 == sig_id2
    finally:
        signal_tracker.LOG_PATH = old_path


def test_log_safe_finds_old_record_via_md5(tmp_path):
    """Old record (MD5 in signal_id_md5) is found by signal_id_md5 match so log_safe skips dedup."""
    import signal_tracker
    
    old_path = signal_tracker.LOG_PATH
    
    # Pre-compute what md5 log_safe will create for today
    today = datetime.now().strftime("%Y-%m-%d")
    expected_md5 = hashlib.md5(f"{today}::trader::南网科技::低吸观察".encode()).hexdigest()[:12]
    
    signal_tracker.LOG_PATH = tmp_path / "signal_log.jsonl"
    try:
        old_record = {
            "signal_id_md5": expected_md5,
            "timestamp": "2025-05-01 10:00",
            "skill": "trader", "target": "南网科技", "symbol": "688248.SH",
            "signal_type": "低吸观察", "price": 10.50,
            "outcome_pnl_pct": None, "outcome_days": None, "outcome": None, "filled_at": None,
        }
        (tmp_path / "signal_log.jsonl").write_text(json.dumps(old_record, ensure_ascii=False) + "\n", encoding="utf-8")
        
        sig_id = signal_tracker.log_safe(
            skill="trader", target="南网科技", symbol="688248.SH",
            signal_type="低吸观察", price=10.50,
        )
        
        # Should return early from dedup (found signal_id_md5 match) without writing a new line
        lines = (tmp_path / "signal_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"Expected 1 line (found old record via md5 dedup), got {len(lines)}"
    finally:
        signal_tracker.LOG_PATH = old_path
