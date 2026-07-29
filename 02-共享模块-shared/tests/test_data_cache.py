"""Tests for data cache optimization: validate_bars, set_cached_validated, merge_daily_bars_with_quote."""
from __future__ import annotations

import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_bars(n: int = 250, start_date: str = "2025-01-01", close_base: float = 10.0) -> list[dict]:
    """Generate synthetic daily bars for testing."""
    from datetime import datetime, timedelta
    bars = []
    dt = datetime.strptime(start_date, "%Y-%m-%d")
    for i in range(n):
        bars.append({
            "date": dt.strftime("%Y-%m-%d"),
            "open": close_base + i * 0.1,
            "high": close_base + i * 0.1 + 0.5,
            "low": close_base + i * 0.1 - 0.5,
            "close": close_base + i * 0.1,
            "volume": 1000000 + i * 1000,
        })
        dt += timedelta(days=1)
    return bars


class TestValidateBars:
    def test_valid_bars(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(250)
        assert validate_bars(bars) is True

    def test_too_few_bars(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(199)
        assert validate_bars(bars) is False

    def test_empty_list(self):
        from trader_shared.cache_utils import validate_bars
        assert validate_bars([]) is False

    def test_not_a_list(self):
        from trader_shared.cache_utils import validate_bars
        assert validate_bars("not a list") is False

    def test_zero_close_rejected(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(250)
        bars[100]["close"] = 0
        assert validate_bars(bars) is False

    def test_negative_close_rejected(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(250)
        bars[100]["close"] = -5.0
        assert validate_bars(bars) is False

    def test_none_close_rejected(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(250)
        bars[100]["close"] = None
        assert validate_bars(bars) is False

    def test_non_monotonic_date_rejected(self):
        from trader_shared.cache_utils import validate_bars
        bars = _make_bars(250)
        bars[100]["date"] = "2020-01-01"  # earlier than previous
        assert validate_bars(bars) is False


class TestSetCachedValidated:
    def test_writes_on_valid(self, tmp_path):
        from trader_shared.cache_utils import set_cached_validated
        with patch("trader_shared.cache_utils.CACHE_DIR", tmp_path):
            data = {"test": "data"}
            result = set_cached_validated("test", "target", data, lambda d: True)
            assert result is True
            cached = json.loads((tmp_path / "test" / "target.json").read_text())
            assert cached == data

    def test_rejects_on_invalid(self, tmp_path):
        from trader_shared.cache_utils import set_cached_validated
        with patch("trader_shared.cache_utils.CACHE_DIR", tmp_path):
            result = set_cached_validated("test", "target", {"bad": True}, lambda d: False)
            assert result is False
            assert not (tmp_path / "test" / "target.json").exists()

    def test_no_validator(self, tmp_path):
        from trader_shared.cache_utils import set_cached_validated
        with patch("trader_shared.cache_utils.CACHE_DIR", tmp_path):
            result = set_cached_validated("test", "target", {"ok": True})
            assert result is True


class TestMergeDailyBarsWithQuote:
    def test_appends_today(self):
        from trader_shared.cache_utils import merge_daily_bars_with_quote
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        bars = _make_bars(5, start_date="2026-05-25")
        quote = {"current_price": "59.33", "open": "58.00", "high": "60.00", "low": "57.50", "volume": "5000000"}
        result = merge_daily_bars_with_quote(bars, quote)
        assert len(result) == 6
        assert result[-1]["date"] == today
        assert result[-1]["close"] == 59.33

    def test_replaces_existing_today(self):
        from trader_shared.cache_utils import merge_daily_bars_with_quote
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        bars = _make_bars(5, start_date="2026-05-26")
        # Last bar is today with old price
        bars[-1]["date"] = today
        bars[-1]["close"] = 58.00
        quote = {"current_price": "59.33", "open": "58.00", "high": "60.00", "low": "57.50", "volume": "5000000"}
        result = merge_daily_bars_with_quote(bars, quote)
        assert len(result) == 5  # same count, replaced
        assert result[-1]["close"] == 59.33

    def test_empty_quote_returns_original(self):
        from trader_shared.cache_utils import merge_daily_bars_with_quote
        bars = _make_bars(5)
        result = merge_daily_bars_with_quote(bars, {})
        assert result == bars

    def test_empty_bars_returns_empty(self):
        from trader_shared.cache_utils import merge_daily_bars_with_quote
        result = merge_daily_bars_with_quote([], {"current_price": "10.0"})
        assert result == []

    def test_uses_quote_trade_date(self):
        from trader_shared.cache_utils import merge_daily_bars_with_quote
        bars = _make_bars(3, start_date="2026-07-25")
        quote = {
            "trade_date": "2026-07-28",
            "current_price": "12.5",
            "open": "12.0",
            "high": "12.8",
            "low": "11.9",
            "volume": "1000",
        }
        result = merge_daily_bars_with_quote(bars, quote)
        assert result[-1]["date"] == "2026-07-28"
        assert result[-1]["close"] == 12.5
