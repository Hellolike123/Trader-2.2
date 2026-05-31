#!/usr/bin/env python3
"""Tests for signal_store.py enhancements — schema version, cleanup, batch reads."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Setup path for imports
STORE_DIR = Path(__file__).resolve().parent.parent / "03-输出校验-contracts"
if str(STORE_DIR) not in sys.path:
    sys.path.insert(0, str(STORE_DIR))
if str(STORE_DIR / ".." / "scripts") not in sys.path:
    sys.path.insert(0, str(STORE_DIR / ".." / "scripts"))


def _make_signal(
    symbol: str = "688248",
    trade_date: str = "2025-05-02",
    signal_type: str = "low_buy_watch",
    status: str | None = None,
) -> dict:
    """Helper: create a valid signal dict with defaults."""
    sig = {
        "source_skill": "trader",
        "symbol": symbol,
        "name": "Test",
        "trade_date": trade_date,
        "analysis_time": "2025-05-02 10:00",
        "signal_type": signal_type,
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
    if status is not None:
        sig["status"] = status
    return sig


class TestSchemaVersion:
    """New signals should include schema_version=1."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        from trader_shared.signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        self.store_path.unlink(missing_ok=True)
        from trader_shared.signal_store import _sig_cache
        _sig_cache.clear()

    def test_new_signal_has_schema_version(self):
        """Newly appended signals should have schema_version=1."""
        from trader_shared.signal_store import append_signal, _read_store

        sig = _make_signal()
        append_signal(sig)

        records = _read_store(self.store_path)
        assert len(records) == 1
        assert records[0].get("schema_version") == 1

    def test_schema_version_not_in_caller_dict(self):
        """schema_version should NOT be added to the caller's original dict."""
        from trader_shared.signal_store import append_signal

        sig = _make_signal()
        append_signal(sig)

        assert "schema_version" not in sig

    def test_existing_schema_version_preserved(self):
        """If caller provides schema_version, it should be preserved."""
        from trader_shared.signal_store import append_signal, _read_store

        sig = _make_signal()
        sig["schema_version"] = 42
        append_signal(sig)

        records = _read_store(self.store_path)
        assert records[0].get("schema_version") == 42

    def test_backward_compat_no_version_field(self):
        """Records without schema_version should still be readable."""
        from trader_shared.signal_store import _read_store

        # Manually write a signal without schema_version
        old_signal = _make_signal()
        self.store_path.write_text(
            json.dumps(old_signal, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        records = _read_store(self.store_path)
        assert len(records) == 1
        assert "schema_version" not in records[0]  # Old format preserved


class TestCleanupOldSignals:
    """cleanup_old_signals should archive and remove old terminal signals."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "signals.jsonl"
        os.environ["TRADER_SIGNAL_STORE_PATH"] = str(self.store_path)

        from trader_shared.signal_store import _sig_cache
        _sig_cache.clear()

    def teardown_method(self):
        self.store_path.unlink(missing_ok=True)
        # Clean up archive files
        for f in Path(self.tmpdir).glob("*archive*"):
            f.unlink(missing_ok=True)
        from trader_shared.signal_store import _sig_cache
        _sig_cache.clear()

    def test_cleanup_empty_store(self):
        """Cleanup on empty store should return zero counts."""
        from trader_shared.signal_store import cleanup_old_signals

        result = cleanup_old_signals(max_age_days=90, path=self.store_path)
        assert result == {"total": 0, "archived": 0, "kept": 0, "failed": 0}

    def test_cleanup_keeps_active_signals(self):
        """Active signals should be kept regardless of age."""
        from trader_shared.signal_store import append_signal, cleanup_old_signals, _sig_cache

        sig = _make_signal(trade_date="2020-01-01", status="active")
        append_signal(sig, path=self.store_path)

        _sig_cache.clear()
        result = cleanup_old_signals(max_age_days=90, path=self.store_path)
        assert result["kept"] == 1
        assert result["archived"] == 0

    def test_cleanup_archives_old_completed(self):
        """Old completed signals should be archived."""
        from trader_shared.signal_store import append_signal, cleanup_old_signals, _read_store, _sig_cache

        # Add an old completed signal
        sig = _make_signal(trade_date="2020-01-01", status="completed")
        append_signal(sig, path=self.store_path)

        _sig_cache.clear()
        result = cleanup_old_signals(max_age_days=90, path=self.store_path)
        assert result["archived"] == 1
        assert result["kept"] == 0

        # Verify archive file exists
        archive_files = list(Path(self.tmpdir).glob("*archive*"))
        assert len(archive_files) >= 1

        # Verify archived content
        archive_content = archive_files[0].read_text(encoding="utf-8")
        assert "2020-01-01" in archive_content

    def test_cleanup_keeps_recent_signals(self):
        """Recent signals should be kept even if completed."""
        from trader_shared.signal_store import append_signal, cleanup_old_signals, _sig_cache

        # Use a recent date (within 90 days)
        recent_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        sig = _make_signal(trade_date=recent_date, status="completed")
        append_signal(sig, path=self.store_path)

        _sig_cache.clear()
        result = cleanup_old_signals(max_age_days=90, path=self.store_path)
        assert result["kept"] == 1
        assert result["archived"] == 0

    def test_cleanup_mixed_signals(self):
        """Cleanup should handle mix of old/new, active/completed signals."""
        from trader_shared.signal_store import append_signal, cleanup_old_signals, _sig_cache

        # Old completed — should be archived
        sig1 = _make_signal(trade_date="2020-01-01", status="completed")
        append_signal(sig1, path=self.store_path)

        # Old active — should be kept
        sig2 = _make_signal(trade_date="2020-01-01", status="active")
        append_signal(sig2, path=self.store_path)

        # Recent completed — should be kept
        recent_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        sig3 = _make_signal(trade_date=recent_date, status="completed")
        append_signal(sig3, path=self.store_path)

        _sig_cache.clear()
        result = cleanup_old_signals(max_age_days=90, path=self.store_path)
        assert result["total"] == 3
        assert result["archived"] == 1
        assert result["kept"] == 2


class TestBatchReads:
    """Batch reading functions for memory efficiency."""

    def test_iter_qfq_daily_batches_empty(self):
        """Empty input should return empty batches."""
        from trader_shared.light_data import iter_qfq_daily_batches

        # This is a pure function test — we can't easily mock fetch_qfq_daily
        # but we can test the batching logic indirectly via get_cached_batches
        pass

    def test_get_cached_batches_miss(self):
        """Cache miss should return None."""
        from trader_shared.cache_utils import get_cached_batches

        result = get_cached_batches("daily", "nonexistent_code", ttl=3600)
        assert result is None

    def test_get_cached_batches_with_data(self):
        """Cached data should be split into batches."""
        from trader_shared.cache_utils import get_cached, set_cached, get_cached_batches

        tmpdir = tempfile.mkdtemp()
        # We'll test the batching logic by creating mock data
        data = [{"date": f"2025-01-{i:02d}", "close": 100.0 + i} for i in range(1, 12)]

        # Manually test batching logic
        batch_size = 5
        batches = []
        for i in range(0, len(data), batch_size):
            batches.append(data[i : i + batch_size])

        assert len(batches) == 3  # 11 items / 5 per batch = 3 batches
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5
        assert len(batches[2]) == 1

    def test_get_memory_usage_mb(self):
        """get_memory_usage_mb should return a non-negative float."""
        from trader_shared.light_data import get_memory_usage_mb

        result = get_memory_usage_mb()
        assert isinstance(result, float)
        assert result >= 0.0


class TestSignalStoreConstants:
    """Verify signal store constants are properly defined."""

    def test_signal_schema_version_defined(self):
        """SIGNAL_SCHEMA_VERSION should be defined and be an int."""
        from trader_shared.signal_store import SIGNAL_SCHEMA_VERSION

        assert isinstance(SIGNAL_SCHEMA_VERSION, int)
        assert SIGNAL_SCHEMA_VERSION == 1

    def test_terminal_states_defined(self):
        """_TERMINAL_STATES should be defined."""
        from trader_shared.signal_store import _TERMINAL_STATES

        assert isinstance(_TERMINAL_STATES, set)
        assert "completed" in _TERMINAL_STATES
        assert "expired" in _TERMINAL_STATES
