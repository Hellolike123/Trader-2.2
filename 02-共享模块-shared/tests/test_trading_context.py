from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest

from trader_shared.trading_context import (
    is_trading_day,
    is_trading_time,
    current_session,
    data_freshness,
)


class TestIsTradingDay:
    def test_normal_weekday(self):
        assert is_trading_day(date(2025, 10, 15)) is True

    def test_weekend(self):
        assert is_trading_day(date(2025, 10, 11)) is False

    def test_weekday_holiday(self):
        assert is_trading_day(date(2025, 10, 1)) is False

    def test_spring_festival(self):
        assert is_trading_day(date(2026, 2, 18)) is False


class TestIsTradingTime:
    @patch("trader_shared.trading_context.datetime")
    def test_trading_hours_normal_day(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 10, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_trading_time() is True

    @patch("trader_shared.trading_context.datetime")
    def test_after_hours(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 20, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_trading_time() is False

    @patch("trader_shared.trading_context.datetime")
    def test_lunch_break(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 12, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_trading_time() is False

    @patch("trader_shared.trading_context.datetime")
    def test_holiday_during_trading_hours(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 1, 10, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_trading_time() is False


class TestCurrentSession:
    @patch("trader_shared.trading_context.datetime")
    def test_pre_market(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 9, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert current_session() == "pre_market"

    @patch("trader_shared.trading_context.datetime")
    def test_trading(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 10, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert current_session() == "trading"

    @patch("trader_shared.trading_context.datetime")
    def test_lunch_break(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 12, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert current_session() == "lunch_break"

    @patch("trader_shared.trading_context.datetime")
    def test_post_market(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 15, 15, 30)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert current_session() == "post_market"

    @patch("trader_shared.trading_context.datetime")
    def test_non_trading(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 10, 11, 10, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert current_session() == "non_trading"


class TestDataFreshness:
    @patch("trader_shared.trading_context.is_trading_time")
    def test_live_during_trading(self, mock_itt):
        mock_itt.return_value = True
        assert data_freshness() == "live"

    @patch("trader_shared.trading_context.is_trading_time")
    def test_stale_after_hours(self, mock_itt):
        mock_itt.return_value = False
        assert data_freshness() == "stale"
