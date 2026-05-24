"""Tests for pytdx3 data source provider and physical Tick aggregation."""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
MARKETDATA = SHARED / "01-行情数据-market-data"
for p in (SHARED, MARKETDATA):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

from unittest.mock import MagicMock, patch
import pytest


@patch("light_data._API_RATE_LIMITER.check_and_record", return_value=True)
@patch("light_data._get_tdx3_client")
def test_fetch_ticks_tdx3_mapping(mock_get_client, mock_rate):
    """Verify that _fetch_ticks_tdx3 maps raw tdx transaction ticks to standard formats."""
    import light_data
    orig_avail = light_data._TDX3_AVAILABLE
    light_data._TDX3_AVAILABLE = True
    try:
        # Mock pytdx3 client
        mock_client = MagicMock()
        # Mock api.get_transaction_data to return raw ticks
        mock_client.get_transaction_data.return_value = [
            {"time": "14:59:02", "price": 1290.2, "vol": 798, "buyorsell": 1},
            {"time": "14:59:15", "price": 1290.1, "vol": 300, "buyorsell": 0},
            {"time": "15:00:00", "price": 1290.2, "vol": 100, "buyorsell": 2},
        ]
        mock_get_client.return_value = mock_client

        sec = light_data.resolve_security("600519")
        ticks = light_data._fetch_ticks_tdx3(sec, count=3)

        assert ticks is not None
        assert len(ticks) == 3
        assert ticks[0]["buyorsell"] == "buy"
        assert ticks[0]["vol"] == 798.0
        assert ticks[1]["buyorsell"] == "sell"
        assert ticks[2]["buyorsell"] == "neutral"
    finally:
        light_data._TDX3_AVAILABLE = orig_avail


@patch("light_data._API_RATE_LIMITER.check_and_record", return_value=True)
@patch("light_data._get_tdx3_client")
def test_fetch_ticks_historic_fallback(mock_get_client, mock_rate):
    """Verify weekend or midnight auto-fallback to get_history_transaction_data."""
    import light_data
    orig_avail = light_data._TDX3_AVAILABLE
    light_data._TDX3_AVAILABLE = True
    try:
        mock_client = MagicMock()
        # First call get_transaction_data returns None (weekend/closed)
        mock_client.get_transaction_data.return_value = None
        # Mock K-line daily fetch returning last day date
        mock_client.get_security_bars.return_value = [
            {"open": 100.0, "close": 101.0, "high": 102.0, "low": 99.0, "vol": 10000.0, "amount": 1.0e7, "datetime": "2026-05-22 15:00"}
        ]
        # Mock get_history_transaction_data returning standard history ticks
        mock_client.get_history_transaction_data.return_value = [
            {"time": "14:59", "price": 101.0, "vol": 1200, "buyorsell": 1}
        ]
        mock_get_client.return_value = mock_client

        sec = light_data.resolve_security("600519")
        ticks = light_data._fetch_ticks_tdx3(sec, count=5)

        assert ticks is not None
        assert len(ticks) == 1
        assert ticks[0]["buyorsell"] == "buy"
        assert ticks[0]["price"] == 101.0
        # Verify api.get_history_transaction_data was called with date_int 20260522
        mock_client.get_history_transaction_data.assert_called_once_with(1, "600519", 0, 5, 20260522)
    finally:
        light_data._TDX3_AVAILABLE = orig_avail


@patch("light_data._API_RATE_LIMITER.check_and_record", return_value=True)
@patch("light_data._get_tdx3_client")
def test_tick_big_order_aggregation(mock_get_client, mock_rate):
    """Test physical tick minute-level aggregation and noise reduction inside big_order."""
    import light_data
    from trader_shared.big_order import analyze_big_orders

    orig_avail = light_data._TDX3_AVAILABLE
    light_data._TDX3_AVAILABLE = True
    try:
        mock_client = MagicMock()
        mock_client.get_transaction_data.return_value = [
            {"time": "14:52:01", "price": 10.0, "vol": 2500, "buyorsell": 1}, # Big (buy)
            {"time": "14:52:15", "price": 10.0, "vol": 3000, "buyorsell": 1}, # Big (buy, same min)
            {"time": "14:52:30", "price": 10.0, "vol": 50, "buyorsell": 0},   # Small noise (ignored)
            {"time": "14:53:02", "price": 10.0, "vol": 4000, "buyorsell": 0}, # Big (sell)
        ]
        mock_get_client.return_value = mock_client

        sec = light_data.resolve_security("002594")
        ticks = light_data._fetch_ticks_tdx3(sec, count=10)

        # Empty 5m bars for validation
        bars_5m = [{"time": "2026-05-22 14:55", "open": 10.0, "close": 10.0, "high": 10.0, "low": 10.0}]

        result = analyze_big_orders(bars_5m, tick_data=ticks)
        events = result["events"]

        assert len(events) == 2
        # First event: buy aggregated (2500 + 3000 = 5500 hands)
        assert events[0]["time"] == "14:52"
        assert events[0]["side"] == "主动买入"
        assert events[0]["hands"] == 5500.0

        # Second event: sell (4000 hands)
        assert events[1]["time"] == "14:53"
        assert events[1]["side"] == "主动卖出"
        assert events[1]["hands"] == 4000.0
    finally:
        light_data._TDX3_AVAILABLE = orig_avail


def test_rate_limiter_throttling():
    """Verify rate limiter blocks when calls exceed limit."""
    from light_data import APIRequestRateLimiter
    import os
    
    test_file = "/tmp/test_api_limits.json"
    if os.path.exists(test_file):
        try:
            os.remove(test_file)
        except Exception:
            pass
            
    limiter = APIRequestRateLimiter(limit_file=test_file)
    
    # Force mock database load to return high call counts
    with patch.object(limiter, "_load") as mock_load:
        # Pretend there are 15 calls in the last minute
        import time
        now = time.time()
        mock_load.return_value = {"calls": [now - 10] * 16}
        
        # Rate limit should trigger and block
        allowed = limiter.check_and_record(max_per_min=15, max_per_hour=80)
        assert allowed is False
        
    if os.path.exists(test_file):
        try:
            os.remove(test_file)
        except Exception:
            pass
