"""Tests for mootdx integration in light_data.py.

mootdx replaces Tencent/Sina as the primary K-line and quote data source.
Tests verify field mapping, date formatting, and fallback behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
MARKETDATA = SHARED / "01-行情数据-market-data"
for p in (SHARED, MARKETDATA):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

import pandas as pd
from unittest.mock import MagicMock, patch


def _make_bars_df(n=3, symbol="600036"):
    """Create a pandas DataFrame that mimics mootdx.bars() output."""
    return pd.DataFrame([
        {"open": 38.0, "close": 38.5, "high": 39.0, "low": 37.5, "vol": 800000.0, "amount": 3.0e9, "datetime": "2026-05-14 15:00", "volume": 800000.0},
        {"open": 38.5, "close": 38.0, "high": 38.8, "low": 37.8, "vol": 700000.0, "amount": 2.7e9, "datetime": "2026-05-15 15:00", "volume": 700000.0},
        {"open": 38.0, "close": 37.6, "high": 38.2, "low": 37.5, "vol": 650000.0, "amount": 2.5e9, "datetime": "2026-05-16 15:00", "volume": 650000.0},
    ])


def _make_quotes_df(symbol="600036"):
    """Create a pandas DataFrame that mimics mootdx.quotes() output."""
    return pd.DataFrame([{
        "market": 1, "code": symbol, "price": 37.6, "last_close": 38.0,
        "open": 38.0, "high": 38.2, "low": 37.5,
        "vol": 650000.0, "amount": 2.5e9,
        "servertime": "15:00:01",
        "cur_vol": 5000, "s_vol": 300000, "b_vol": 350000,
    }])


@patch("light_data._get_mootdx_client")
def test_fetch_qfq_mootdx_fields(mock_get_client):
    """Verify mootdx K-line fields are correctly mapped to BarData format."""
    mock_client = MagicMock()
    mock_client.bars.return_value = _make_bars_df()
    mock_get_client.return_value = mock_client

    from light_data import resolve_security, _fetch_qfq_mootdx

    sec = resolve_security("600036")
    bars = _fetch_qfq_mootdx(sec, days=5)

    assert bars is not None
    assert len(bars) == 3
    bar = bars[0]

    assert bar["date"] == "2026-05-14"
    assert bar["open"] == 38.0
    assert bar["close"] == 38.5
    assert bar["high"] == 39.0
    assert bar["low"] == 37.5
    assert bar["volume"] == 800000.0
    assert bar["amount"] == 3.0e9
    assert bars[-1]["date"] == "2026-05-16"
    assert bars[-1]["close"] == 37.6


@patch("light_data._get_mootdx_client")
def test_fetch_qfq_mootdx_ascending_order(mock_get_client):
    """Verify bars are returned in chronological order (oldest first)."""
    mock_client = MagicMock()
    mock_client.bars.return_value = _make_bars_df()
    mock_get_client.return_value = mock_client

    from light_data import resolve_security, _fetch_qfq_mootdx

    sec = resolve_security("600036")
    bars = _fetch_qfq_mootdx(sec, days=5)

    dates = [b["date"] for b in bars]
    assert dates == sorted(dates)


@patch("light_data._get_mootdx_client")
def test_fetch_quote_mootdx_fields(mock_get_client):
    """Verify mootdx quote fields are correctly mapped to QuoteData format."""
    mock_client = MagicMock()
    mock_client.quotes.return_value = _make_quotes_df()
    mock_get_client.return_value = mock_client

    from light_data import resolve_security, _fetch_quote_mootdx

    sec = resolve_security("600036")
    q = _fetch_quote_mootdx(sec)

    assert q is not None
    assert q["symbol"] == "600036.SH"
    assert q["current_price"] == 37.6
    assert q["pre_close"] == 38.0
    assert q["open"] == 38.0
    assert q["high"] == 38.2
    assert q["low"] == 37.5
    assert q["volume"] == 650000.0
    assert q["amount"] == 2.5e9
    # change_pct = (37.6/38.0 - 1) * 100 = -1.05
    assert q["current_change_pct"] == -1.05


def test_mootdx_import_fallback():
    """Verify light_data handles mootdx import failure gracefully."""
    from light_data import _MOOTDX_AVAILABLE
    assert isinstance(_MOOTDX_AVAILABLE, bool)


@patch("light_data._get_mootdx_client", return_value=None)
def test_fetch_qfq_mootdx_returns_none_when_unavailable(mock_get_client):
    """When mootdx client unavailable, _fetch_qfq_mootdx returns None."""
    from light_data import resolve_security, _fetch_qfq_mootdx

    sec = resolve_security("600036")
    bars = _fetch_qfq_mootdx(sec, days=5)

    assert bars is None


@patch("light_data._get_mootdx_client")
def test_fetch_qfq_mootdx_returns_none_on_error(mock_get_client):
    """When mootdx.bars() raises, _fetch_qfq_mootdx returns None."""
    mock_client = MagicMock()
    mock_client.bars.side_effect = Exception("connection error")
    mock_get_client.return_value = mock_client

    from light_data import resolve_security, _fetch_qfq_mootdx

    sec = resolve_security("600036")
    bars = _fetch_qfq_mootdx(sec, days=5)

    assert bars is None


@patch("light_data._fetch_mins_fallback", return_value=None)
@patch("light_data._get_mootdx_client")
def test_fetch_5m_from_mootdx(mock_get_client, mock_fallback):
    """fetch_5m should use mootdx 5-minute bars when available."""
    mock_client = MagicMock()
    df_5m = pd.DataFrame([
        {"open": 38.0, "close": 38.2, "high": 38.3, "low": 37.9, "vol": 50000.0, "amount": 1.9e6, "datetime": "2026-05-16 09:35", "volume": 50000.0},
        {"open": 38.2, "close": 38.1, "high": 38.3, "low": 38.0, "vol": 45000.0, "amount": 1.7e6, "datetime": "2026-05-16 09:40", "volume": 45000.0},
    ])
    mock_client.bars.return_value = df_5m
    mock_get_client.return_value = mock_client

    from light_data import resolve_security, fetch_5m, HttpClient

    sec = resolve_security("600036")
    http = HttpClient()
    bars = fetch_5m(sec, http, datalen=5)

    assert len(bars) == 2
    assert bars[0]["open"] == 38.0
    assert bars[0]["close"] == 38.2
    assert bars[0]["volume"] == 50000.0


@patch("light_data._get_mootdx_client", return_value=None)
def test_fetch_quote_fast_path_with_tencent(mock_get_client):
    """fetch_quote tries Tencent HTTP first (new order).
    We mock the Tencent HTTP call so the fast path succeeds immediately.
    Tencent HTTP quote format: prefix="field0~field1~..."  (re.search(r'="([^"]*)")' captures body)
    """
    from light_data import resolve_security, fetch_quote, HttpClient

    fake_content = ["0"] * 41
    fake_content[1] = "平安银行"
    fake_content[3] = "38.50"
    fake_content[4] = "38.00"
    fake_content[5] = "38.00"
    fake_content[32] = "1.32"
    fake_content[33] = "38.50"
    fake_content[34] = "37.50"
    fake_content[36] = "800000"
    fake_content[37] = "3000000000"
    fake_content[38] = "0.35"

    # Tencent HTTP format: prefix="fields"
    fake_text = 'sh600035="' + "~".join(fake_content) + '"'

    def fake_get_text(url, encoding="gbk"):
        return fake_text

    sec = resolve_security("600036")
    http = HttpClient()
    with patch.object(http, "get_text", fake_get_text):
        q = fetch_quote(sec, http)

    assert q["current_price"] == 38.5
    assert q["turnover_rate"] == 0.35
    assert q["data_source"] == "tencent-http"
    assert q["data_status"] == "full"
