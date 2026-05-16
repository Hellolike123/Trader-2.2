#!/usr/bin/env python3
"""Tests for check_recent / backfill triple-degradation signal_results matching.

Matching priority (after this change):
1. signal_id exact match (primary)
2. 4-key normalized match: (symbol, _norm_date, _normalize_signal_type, price_str)
3. 3-key normalized match: (symbol, _norm_date, _normalize_signal_type)

The KEY FIX: existing keys are built with raw signal_date/signal_type from
the JSONL record, but NOW they are normalized on read-back so that old
non-zero-padded dates and Chinese old-type names match.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Path setup (same as existing tests) ──
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent  # 02-共享模块-shared/
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

import signal_tracker as st


class _TempPaths:
    """Temporarily replace RESULT_PATH / LOG_PATH / STORE_PATH."""

    def __init__(self, tmp_dir: Path):
        self._orig: dict[str, Path] = {}
        tmp_dir.mkdir(exist_ok=True, parents=True)
        self.result_path = tmp_dir / "signal_results.jsonl"
        self.log_path = tmp_dir / "signal_log.jsonl"
        self.store_path = tmp_dir / "signals.jsonl"

    def apply(self) -> None:
        self._orig = {
            "RESULT_PATH": st.RESULT_PATH,
            "LOG_PATH": st.LOG_PATH,
            "STORE_PATH": st.STORE_PATH,
        }
        st.RESULT_PATH = self.result_path
        st.LOG_PATH = self.log_path
        st.STORE_PATH = self.store_path

    def restore(self) -> None:
        for k, v in self._orig.items():
            setattr(st, k, v)


# ── Helpers ──

def _make_sig(
    symbol: str = "688248.SH",
    name: str = "南网科技",
    trade_date: str = "2026-04-29",
    signal_type: str = "low_buy_watch",
    price: float = 10.0,
    signal_id: str | None = None,
    analysis_time: str = "2026-04-29T09:30:00",
) -> dict:
    sig: dict = {
        "symbol": symbol,
        "name": name,
        "trade_date": trade_date,
        "analysis_time": analysis_time,
        "signal_type": signal_type,
        "direction": "bullish_lean",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "data_status": "full",
        "trigger": {"price": price, "type": "price_confirm", "text": ""},
        "invalidation": {"price": price - 0.5, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 30},
        "risk_flags": [],
        "summary": "test",
    }
    if signal_id:
        sig["signal_id"] = signal_id
    return sig


# ═══════ Test 1: signal_id is primary match key ═══════

class TestSignalIdPrimaryMatch:
    """check_recent() uses signal_id as primary match key."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_sid_primary")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_check_recent_skip_existing_by_signal_id(self):
        """Signal with signal_id already has result with same signal_id → skipped."""
        self.tmp.apply()

        today = datetime.now()
        date_str = (today - timedelta(days=3)).strftime("%Y-%m-%d")
        analysis_time = f"{date_str}T10:00:00"
        sig_id = hashlib.sha256(
            f"688248.SH|{date_str}|low_buy_watch|10.00".encode()
        ).hexdigest()[:16]

        # Write signal with signal_id
        sig = _make_sig(
            trade_date=date_str,
            price=10.0,
            signal_id=sig_id,
            analysis_time=analysis_time,
        )
        self.tmp.store_path.write_text(
            json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # Pre-write matching result with same signal_id
        result = {
            "signal_id": sig_id,
            "symbol": "688248.SH",
            "name": "南网科技",
            "signal_date": date_str,
            "signal_type": "low_buy_watch",
            "signal_price": 10.0,
            "r_5d": 2.5,
            "outcome": "up",
        }
        self.tmp.result_path.write_text(
            json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # HttpClient must NOT be None or check_recent returns early (line 495)
        # We also mock _compute_results_for_sig to return None so it doesn't reach HTTP
        with patch.object(st, "HttpClient", MagicMock()):
            with patch.object(st, "_compute_results_for_sig", return_value=None):
                ret = st.check_recent(days=5)

        assert ret.get("skipped", 0) >= 1, f"Expected >=1 skipped by signal_id, got {ret}"


# ═══════ Test 2: 4-key matching normalizes date ═══════

class TestDateNormalization:
    """4-key matching calls _norm_date on read-back from results."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_date_norm")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_non_zero_padded_date_matches(self):
        """Old result with signal_date='2026-4-29' matches new trade_date='2026-04-29'."""
        self.tmp.apply()

        today = datetime.now()
        date_padded = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        # Strip leading zeros: 2026-04-29 → 2026-4-29
        parts = date_padded.split("-")
        date_unpadded = "-".join(str(int(p)) for p in parts)
        analysis_time = f"{date_padded}T10:00:00"

        sig = _make_sig(
            trade_date=date_padded,
            price=10.5,
            analysis_time=analysis_time,
        )
        self.tmp.store_path.write_text(
            json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # OLD result with UNNORMALIZED date — the bug we're fixing
        old_result = {
            "symbol": "688248.SH",
            "name": "南网科技",
            "signal_date": date_unpadded,  # Non-zero-padded — the classic bug
            "signal_type": "low_buy_watch",
            "signal_price": 10.5,
            "r_5d": 0.0,
            "outcome": "flat",
        }
        self.tmp.result_path.write_text(
            json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        with patch.object(st, "HttpClient", MagicMock()):
            with patch.object(st, "_compute_results_for_sig", return_value=None):
                ret = st.check_recent(days=5)

        assert ret.get("skipped", 0) >= 1, (
            f"Expected 1 skipped (4-key + _norm_date fix), got {ret}"
        )


# ═══════ Test 3: 3-key fallback normalizes signal_type ═══════

class TestTypeNormalization:
    """3-key fallback normalizes signal_type via _normalize_signal_type on read-back."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_type_norm")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_chinese_signal_type_normalizes(self):
        """Chinese old-name signal_type normalizes to match English normalized type."""
        self.tmp.apply()

        today = datetime.now()
        date_str = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        analysis_time = f"{date_str}T10:00:00"

        sig = _make_sig(
            trade_date=date_str,
            price=10.5,
            signal_type="低吸观察",  # Chinese old name → _normalize_signal_type → low_buy_watch
            analysis_time=analysis_time,
        )
        self.tmp.store_path.write_text(
            json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # Result with ENGLISH normalized type
        old_result = {
            "symbol": "688248.SH",
            "name": "南网科技",
            "signal_date": date_str,
            "signal_type": "low_buy_watch",
            "signal_price": 10.5,
            "r_5d": 0.0,
            "outcome": "flat",
        }
        self.tmp.result_path.write_text(
            json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        with patch.object(st, "HttpClient", MagicMock()):
            with patch.object(st, "_compute_results_for_sig", return_value=None):
                ret = st.check_recent(days=5)

        assert ret.get("skipped", 0) >= 1, (
            f"Expected 1 skipped (3-key + _normalize_signal_type), got {ret}"
        )


# ═══════ Test 4: No match for different symbols ═══════

class TestNoMatchDifferentSymbol:
    """check_recent() does not match if symbol differs."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_diff_symbol")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_different_symbols_not_matched(self):
        self.tmp.apply()

        sig = _make_sig(
            symbol="600519.SH",
            name="贵州茅台",
            trade_date="2026-04-29",
            price=1600.0,
            signal_type="low_buy_watch",
            analysis_time="2026-04-29T10:00:00",
        )
        self.tmp.store_path.write_text(
            json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # Result for DIFFERENT symbol
        old_result = {
            "symbol": "688248.SH",
            "name": "南网科技",
            "signal_date": "2026-04-29",
            "signal_type": "low_buy_watch",
            "signal_price": 10.5,
            "r_5d": 0.0,
            "outcome": "flat",
        }
        self.tmp.result_path.write_text(
            json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        with patch.object(st, "HttpClient", MagicMock()):
            with patch.object(st, "_compute_results_for_sig", return_value=None):
                ret = st.check_recent(days=5)

        assert ret.get("skipped", 0) == 0, (
            f"Expected 0 skipped (different symbols), got {ret}"
        )


# ═══════ Test 5: Helper normalization correctness ═══════

class TestNormalizationHelpers:
    """Verify normalization helpers behave correctly."""

    def test_norm_date_fix(self):
        """_norm_date converts non-zero-padded to zero-padded."""
        assert st._norm_date("2026-4-1") == "2026-04-01"
        assert st._norm_date("2026-5-2") == "2026-05-02"
        assert st._norm_date("2026-04-01") == "2026-04-01"

    def test_normalize_signal_type_fix(self):
        """_normalize_signal_type maps Chinese old names."""
        assert st._normalize_signal_type("低吸观察") == "low_buy_watch"
        assert st._normalize_signal_type("低吸已触发") == "low_buy_triggered"
        assert st._normalize_signal_type("low_buy_watch") == "low_buy_watch"

    def test_make_signal_key_normalizes(self):
        """_make_signal_key already normalizes inputs internally."""
        sig = _make_sig(signal_type="低吸观察", trade_date="2026-4-1")
        nk = st._make_signal_key(sig)
        assert nk[1] == "2026-04-01", f"Expected '2026-04-01', got '{nk[1]}'"
        assert nk[2] == "low_buy_watch", f"Expected 'low_buy_watch', got '{nk[2]}'"


# ═══════ Test 6: backfill uses same normalized matching ═══════

class TestBackfillNormalization:
    """backfill() should also normalize existing_keys on read-back."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_backfill")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_backfill_normalizes_date(self):
        """backfill() 4-key matching also normalizes read-back signal_date."""
        self.tmp.apply()

        sig = _make_sig(
            trade_date="2026-04-29",
            price=10.5,
            analysis_time="2026-04-29T10:00:00",
        )
        self.tmp.store_path.write_text(
            json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        # OLD result with non-zero-padded date
        old_result = {
            "symbol": "688248.SH",
            "name": "南网科技",
            "signal_date": "2026-4-29",  # Non-zero-padded
            "signal_type": "low_buy_watch",
            "signal_price": 10.5,
            "r_5d": 0.0,
            "outcome": "flat",
        }
        self.tmp.result_path.write_text(
            json.dumps(old_result, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        with patch.object(st, "HttpClient", MagicMock()):
            with patch.object(st, "_compute_results_for_sig", return_value=None):
                ret = st.backfill(days_window=365)

        assert ret.get("skipped", 0) >= 1, (
            f"Expected 1 skipped (backfill 4-key + _norm_date), got {ret}"
        )
