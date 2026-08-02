"""测试 data_access.py 简化接口

验证：
1. 所有函数可正确导入
2. provider 失败时返回安全默认值（空列表/空字典/None），不抛出异常
3. 调用方只需传字符串，无需关心 Security / provider 细节
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "02-共享模块-shared"))


# 构造最小 mock provider
def _make_mock_provider(daily=None, bars_5m=None, bars_15m=None,
                         bars_30m=None, weekly=None, monthly=None,
                         quote=None, ticks=None):
    p = MagicMock()
    sec = MagicMock()
    p.resolve_security.return_value = sec
    p.fetch_qfq_daily.return_value = daily or [{"close": 10.0}]
    p.fetch_5m.return_value = bars_5m or [{"close": 10.1}]
    p.fetch_15m.return_value = bars_15m or [{"close": 10.2}]
    p.fetch_30m.return_value = bars_30m or [{"close": 10.3}]
    p.fetch_weekly.return_value = weekly or [{"close": 10.4}]
    p.fetch_monthly.return_value = monthly or [{"close": 10.5}]
    p.fetch_quote.return_value = quote or {"current": 10.0, "change_pct": 0.5}
    p.fetch_ticks.return_value = ticks or [{"price": 10.0}]
    return p


class TestDataAccessImports:
    def test_all_functions_importable(self):
        from trader_shared.data_access import (
            get_daily, get_5m, get_15m, get_30m,
            get_weekly, get_monthly, get_quote, get_quotes, get_ticks, get_snapshot,
        )
        for f in [get_daily, get_5m, get_15m, get_30m,
                  get_weekly, get_monthly, get_quote, get_quotes, get_ticks, get_snapshot]:
            assert callable(f)


class TestGetDaily:
    def test_returns_bars_on_success(self):
        mock_p = _make_mock_provider(daily=[{"close": 20.0}] * 5)
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_daily
            result = get_daily("688248", days=5)
        assert result == [{"close": 20.0}] * 5

    def test_returns_empty_list_on_failure(self):
        with patch("trader_shared.data_access.get_provider", side_effect=RuntimeError("网络异常")):
            from trader_shared.data_access import get_daily
            result = get_daily("688248")
        assert result == []

    def test_provider_called_with_correct_days(self):
        mock_p = _make_mock_provider()
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_daily
            get_daily("688248", days=100)
        mock_p.fetch_qfq_daily.assert_called_once()
        _, kwargs = mock_p.fetch_qfq_daily.call_args
        assert kwargs.get("days") == 100 or mock_p.fetch_qfq_daily.call_args[0][1] == 100


class TestGet5m:
    def test_returns_bars_on_success(self):
        mock_p = _make_mock_provider(bars_5m=[{"close": 9.9}] * 3)
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_5m
            result = get_5m("688248")
        assert result == [{"close": 9.9}] * 3

    def test_returns_empty_list_on_failure(self):
        with patch("trader_shared.data_access.get_provider", side_effect=Exception("超时")):
            from trader_shared.data_access import get_5m
            result = get_5m("688248")
        assert result == []


class TestGetWeekly:
    def test_returns_weekly_bars(self):
        mock_p = _make_mock_provider(weekly=[{"close": 10.4}] * 10)
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_weekly
            result = get_weekly("688248", datalen=10)
        assert len(result) == 10

    def test_returns_empty_on_failure(self):
        with patch("trader_shared.data_access.get_provider", side_effect=Exception("失败")):
            from trader_shared.data_access import get_weekly
            assert get_weekly("688248") == []


class TestGetQuote:
    def test_returns_quote_dict(self):
        mock_p = _make_mock_provider(quote={"current": 58.7, "change_pct": -3.77})
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_quote
            result = get_quote("688248")
        assert result["current"] == 58.7

    def test_returns_empty_dict_on_failure(self):
        with patch("trader_shared.data_access.get_provider", side_effect=Exception("失败")):
            from trader_shared.data_access import get_quote
            assert get_quote("688248") == {}


class TestGetQuotes:
    def test_batch_returns_per_target(self):
        mock_p = _make_mock_provider(quote={"current_price": 10.0, "current_change_pct": 1.0})
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_quotes
            result = get_quotes(["688248", "600519"])
        assert set(result) == {"688248", "600519"}
        assert result["688248"]["current_price"] == 10.0
        assert mock_p.fetch_quote.call_count == 2

    def test_empty_targets(self):
        from trader_shared.data_access import get_quotes
        assert get_quotes([]) == {}


class TestGetSnapshot:
    def test_returns_snapshot_on_success(self):
        mock_snap = MagicMock()
        mock_p = _make_mock_provider()
        mock_p.load_market_snapshot.return_value = mock_snap
        with patch("trader_shared.data_access.get_provider", return_value=mock_p):
            from trader_shared.data_access import get_snapshot
            result = get_snapshot("688248")
        assert result is mock_snap

    def test_returns_none_on_failure(self):
        with patch("trader_shared.data_access.get_provider", side_effect=Exception("失败")):
            from trader_shared.data_access import get_snapshot
            assert get_snapshot("688248") is None
