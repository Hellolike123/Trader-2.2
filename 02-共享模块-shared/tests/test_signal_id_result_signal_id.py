#!/usr/bin/env python3
"""verify _compute_results_for_sig writes signal_id into result records."""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_p = Path(__file__).resolve().parent.parent / "scripts"
if str(_p.resolve()) not in sys.path:
    sys.path.insert(0, str(_p.resolve()))

from signal_tracker import _compute_results_for_sig, make_signal_id


def test_compute_results_for_sig_includes_signal_id():
    """When _compute_results_for_sig returns a result, signal_id is present and correct."""
    sig = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "low_buy_watch",
        "source_skill": "trader",
        "trigger": {"price": 10.5, "type": "price_confirm", "text": "test"},
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

    assert result is not None, "_compute_results_for_sig should return a result, not None"
    assert "signal_id" in result, f"Result should have signal_id: {list(result.keys())}"
    assert len(result["signal_id"]) == 16

    # Verify signal_id matches expected computation
    # _compute_results_for_sig extracts price from trigger.price and uses trade_date
    expected = make_signal_id(
        "688248.SH", "2025-05-02", "low_buy_watch", f"{10.5:.2f}"
    )
    assert result["signal_id"] == expected


def test_compute_results_for_sig_signal_id_with_fallback_price():
    """signal_id uses signal_bar.close when trigger.price is missing."""
    sig = {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "trade_date": "2025-05-02",
        "signal_type": "buy",
        "source_skill": "trader",
        "trigger": {"type": "time_confirm", "text": "test"},
        "position": {"max_total_pct": 20, "max_single_move_pct": 20},
    }

    mock_bars = [
        {"date": "2025-05-02", "close": "12.30", "atr14": "0.40"},
        {"date": "2025-05-05", "close": "12.50", "atr14": "0.40"},
    ]

    with patch("signal_tracker.resolve_security", return_value="000001.SZ"), \
         patch("signal_tracker.fetch_qfq_daily", return_value=mock_bars), \
         patch("signal_tracker.HttpClient", return_value=MagicMock()), \
         patch("signal_tracker.to_float", side_effect=lambda v: float(v) if v else None):
        result = _compute_results_for_sig(sig)

    assert result is not None
    assert "signal_id" in result
    # Should fall back to signal_bar.close = 12.30
    expected = make_signal_id(
        "000001.SZ", "2025-05-02", "buy", f"{12.30:.2f}"
    )
    assert result["signal_id"] == expected


def test_compute_results_for_sig_signal_id_normalized():
    """symbol and signal_type get canonicalized in the signal_id."""
    sig = {
        "symbol": "688248",  # bare 6-digit, should normalize to .SH
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "signal_type": "low_buy_watch",
        "source_skill": "trader",
        "trigger": {"price": 9.00, "type": "price_confirm", "text": ""},
        "position": {"max_total_pct": 10, "max_single_move_pct": 10},
    }

    mock_bars = [
        {"date": "2025-05-02", "close": "9.00", "atr14": "0.30"},
        {"date": "2025-05-05", "close": "9.30", "atr14": "0.30"},
    ]

    with patch("signal_tracker.resolve_security", return_value="688248.SH"), \
         patch("signal_tracker.fetch_qfq_daily", return_value=mock_bars), \
         patch("signal_tracker.HttpClient", return_value=MagicMock()), \
         patch("signal_tracker.to_float", side_effect=lambda v: float(v) if v else None):
        result = _compute_results_for_sig(sig)

    assert result is not None
    assert "signal_id" in result
    # _normalize_symbol("688248") => "688248.SH"
    expected = make_signal_id(
        "688248.SH", "2025-05-02", "low_buy_watch", f"{9.00:.2f}"
    )
    assert result["signal_id"] == expected
