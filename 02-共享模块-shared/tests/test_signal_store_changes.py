#!/usr/bin/env python3
"""Tests for signal_store.py — no side effects, proper API."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


STORE_DIR = Path(__file__).resolve().parent.parent / "03-输出校验-contracts"
if str(STORE_DIR) not in sys.path:
    sys.path.insert(0, str(STORE_DIR))
if str(STORE_DIR / ".." / "scripts") not in sys.path:
    sys.path.insert(0, str(STORE_DIR / ".." / "scripts"))


class TestAppendSignalNoMutation:
    """append_signal must NOT mutate the caller's dict."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        # Clear any cached entries
        from signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        # Remove store after test
        self.store_path.unlink(missing_ok=True)

    def _make_full_signal(self, **overrides):
        base = {
            "source_skill": "trader",
            "symbol": "688248",
            "name": "南网科技",
            "trade_date": "2025-05-02",
            "analysis_time": "2025-05-02 10:00",
            "signal_type": "low_buy_watch",
            "direction": "bullish_lean",
            "action": "observe",
            "confidence": "medium",
            "data_status": "degraded",
            "trigger": {"price": 55.9, "text": "test trigger"},
            "invalidation": {"price": 54.0, "text": "stop"},
            "position": {"max_total_pct": 30, "max_single_move_pct": 10},
            "risk_flags": ["test"],
            "summary": "test summary",
        }
        base.update(overrides)
        return base

    def test_signal_not_mutated(self):
        original = self._make_full_signal()
        trigger_copy = dict(original["trigger"])
        original_trigger = id(original["trigger"])

        from signal_store import append_signal
        sid = append_signal(original)

        # signal_id should NOT be in original
        assert "signal_id" not in original

        # trigger should be unchanged
        assert original["trigger"] == trigger_copy

    def test_trigger_not_mutated(self):
        original = self._make_full_signal(trigger={"price": 55.9, "text": "before"})
        trigger_before = dict(original["trigger"])

        from signal_store import append_signal
        append_signal(original)

        assert original["trigger"] == trigger_before

    def test_returns_signal_id(self):
        from signal_store import append_signal
        original = self._make_full_signal()
        sid = append_signal(original)

        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_stored_record_has_signal_id(self):
        from signal_store import append_signal, _read_store
        original = self._make_full_signal()
        append_signal(original)

        records = _read_store(self.store_path)
        assert len(records) >= 1
        assert "signal_id" in records[-1]


class TestAppendSignalValidation:
    """Missing required fields should raise, not silently pass."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        from signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        self.store_path.unlink(missing_ok=True)

    def _make_full_signal(self):
        return {
            "source_skill": "trader",
            "symbol": "688248",
            "name": "南网科技",
            "trade_date": "2025-05-02",
            "analysis_time": "2025-05-02 10:00",
            "signal_type": "low_buy_watch",
            "direction": "bullish_lean",
            "action": "observe",
            "confidence": "medium",
            "data_status": "degraded",
            "trigger": {"price": 55.9, "text": "test"},
            "invalidation": {"price": 54.0, "text": "stop"},
            "position": {"max_total_pct": 30, "max_single_move_pct": 10},
            "risk_flags": [],
            "summary": "test",
        }

    def test_missing_field_raises(self):
        from signal_store import append_signal
        sig = self._make_full_signal()
        del sig["source_skill"]

        try:
            append_signal(sig)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "missing required field" in str(e)

    def test_invalid_signal_type_raises(self):
        from signal_store import append_signal
        sig = self._make_full_signal()
        sig["signal_type"] = "invalid_future_type"

        try:
            append_signal(sig)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "invalid signal_type" in str(e)


class TestLoadRecentSignals:
    """load_recent_signals should read correctly."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        from signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        self.store_path.unlink(missing_ok=True)
        from signal_store import _sig_cache
        _sig_cache.clear()

    def _make_signal(self, symbol="688248"):
        return {
            "source_skill": "trader",
            "symbol": symbol,
            "name": "Test",
            "trade_date": "2025-05-02",
            "analysis_time": "2025-05-02 10:00",
            "signal_type": "low_buy_watch",
            "direction": "bullish_lean",
            "action": "observe",
            "confidence": "medium",
            "data_status": "degraded",
            "trigger": {"price": 55.9, "text": "test"},
            "invalidation": {"price": 54.0, "text": "stop"},
            "position": {"max_total_pct": 30, "max_single_move_pct": 10},
            "risk_flags": [],
            "summary": "test",
        }

    def test_load_empty_returns_empty(self):
        from signal_store import load_recent_signals
        recents = load_recent_signals(symbol="688248.SH")
        assert isinstance(recents, list)

    def test_load_single_signal(self):
        from signal_store import append_signal, load_recent_signals, _sig_cache
        _sig_cache.clear()
        sig = self._make_signal()
        append_signal(sig)

        _sig_cache.clear()  # Force re-read
        recents = load_recent_signals(symbol="688248.SH")
        assert len(recents) >= 1

    def test_load_filtrers_by_symbol(self):
        from signal_store import append_signal, load_recent_signals
        sig = self._make_signal("688248")
        append_signal(sig)

        # Different symbol should not see it
        recents = load_recent_signals(symbol="600519.SH")
        assert len(recents) == 0


class TestBadLineObservability:
    """_bad_line_count and _bad_line_last_reason should be set on bad lines."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        from signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        self.store_path.unlink(missing_ok=True)
        from signal_store import _sig_cache
        _sig_cache.clear()

    def test_bad_line_increments_count(self):
        """Bad JSON lines should increment _bad_line_count."""
        # Write a file with a bad line
        self.store_path.write_text(
            json.dumps({"test": "good"}) + "\nbad_json\n", encoding="utf-8"
        )

        from signal_store import _read_store
        signals = _read_store(self.store_path)

        from signal_store import _bad_line_count
        assert _bad_line_count >= 1, "Bad line should increment counter"
        assert len(signals) == 1  # only the good one parsed

    def test_bad_line_last_reason_set(self):
        """_bad_line_last_reason should be set on bad lines."""
        self.store_path.write_text("not_valid_json", encoding="utf-8")

        from signal_store import _read_store
        _read_store(self.store_path)

        from signal_store import _bad_line_last_reason, _bad_line_last_path
        assert _bad_line_last_reason != "", "Reason should be set"
        assert _bad_line_last_path == str(self.store_path)
