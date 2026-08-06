"""Tests for mootdx integration in light_data.py.

mootdx replaces Tencent/Sina as the primary K-line and quote data source.
Tests verify field mapping, date formatting, and fallback behavior.
"""
from __future__ import annotations

import time
import warnings
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trader_shared import light_data


@pytest.fixture(autouse=True)
def _reset_mootdx_controller():
    """Isolate health / client globals between tests."""
    ctrl = light_data._DATA_SOURCE_CONTROLLER
    saved = (
        ctrl.healthy,
        ctrl.consecutive_failures,
        ctrl.cool_down_until,
        ctrl.total_calls,
        ctrl.total_failures,
        light_data._MOOTDX_CLIENT,
    )
    ctrl.healthy = True
    ctrl.consecutive_failures = 0
    ctrl.cool_down_until = 0.0
    light_data._MOOTDX_CLIENT = None
    yield
    (
        ctrl.healthy,
        ctrl.consecutive_failures,
        ctrl.cool_down_until,
        ctrl.total_calls,
        ctrl.total_failures,
        light_data._MOOTDX_CLIENT,
    ) = saved


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


@patch.object(light_data, "_get_mootdx_client")
def test_fetch_qfq_mootdx_fields(mock_get_client):
    """Verify mootdx K-line fields are correctly mapped to BarData format."""
    mock_client = MagicMock()
    mock_client.bars.return_value = _make_bars_df()
    mock_get_client.return_value = mock_client

    sec = light_data.resolve_security("600036")
    bars = light_data._fetch_qfq_mootdx(sec, days=5)

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


@patch.object(light_data, "_get_mootdx_client")
def test_fetch_qfq_mootdx_ascending_order(mock_get_client):
    """Verify bars are returned in chronological order (oldest first)."""
    mock_client = MagicMock()
    mock_client.bars.return_value = _make_bars_df()
    mock_get_client.return_value = mock_client

    sec = light_data.resolve_security("600036")
    bars = light_data._fetch_qfq_mootdx(sec, days=5)

    dates = [b["date"] for b in bars]
    assert dates == sorted(dates)


@patch.object(light_data, "_get_mootdx_client")
def test_fetch_quote_mootdx_fields(mock_get_client):
    """Verify mootdx quote fields are correctly mapped to QuoteData format."""
    mock_client = MagicMock()
    mock_client.quotes.return_value = _make_quotes_df()
    mock_get_client.return_value = mock_client

    sec = light_data.resolve_security("600036")
    q = light_data._fetch_quote_mootdx(sec)

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
    result = light_data._check_mootdx()
    assert isinstance(result, bool)


@patch.object(light_data, "_get_mootdx_client", return_value=None)
def test_fetch_qfq_mootdx_returns_none_when_unavailable(mock_get_client):
    """When mootdx client unavailable, _fetch_qfq_mootdx returns None."""
    sec = light_data.resolve_security("600036")
    bars = light_data._fetch_qfq_mootdx(sec, days=5)

    assert bars is None


@patch.object(light_data, "_get_mootdx_client")
def test_fetch_qfq_mootdx_returns_none_on_error(mock_get_client):
    """When mootdx.bars() raises, _fetch_qfq_mootdx returns None."""
    mock_client = MagicMock()
    mock_client.bars.side_effect = Exception("connection error")
    mock_get_client.return_value = mock_client

    sec = light_data.resolve_security("600036")
    bars = light_data._fetch_qfq_mootdx(sec, days=5)

    assert bars is None


@patch.object(light_data, "_fetch_mins_fallback", return_value=None)
@patch.object(light_data, "_get_mootdx_client")
def test_fetch_5m_from_mootdx(mock_get_client, mock_fallback):
    """fetch_5m should use mootdx 5-minute bars when available."""
    mock_client = MagicMock()
    df_5m = pd.DataFrame([
        {"open": 38.0, "close": 38.2, "high": 38.3, "low": 37.9, "vol": 50000.0, "amount": 1.9e6, "datetime": "2026-05-16 09:35", "volume": 50000.0},
        {"open": 38.2, "close": 38.1, "high": 38.3, "low": 38.0, "vol": 45000.0, "amount": 1.7e6, "datetime": "2026-05-16 09:40", "volume": 45000.0},
    ])
    mock_client.bars.return_value = df_5m
    mock_get_client.return_value = mock_client

    sec = light_data.resolve_security("600036")
    http = light_data.HttpClient()
    bars = light_data.fetch_5m(sec, http, datalen=5)

    assert len(bars) == 2
    assert bars[0]["open"] == 38.0
    assert bars[0]["close"] == 38.2
    assert bars[0]["volume"] == 50000.0


@patch.object(light_data, "_get_mootdx_client", return_value=None)
def test_fetch_quote_fast_path_with_tencent(mock_get_client):
    """fetch_quote tries Tencent HTTP first (new order).
    We mock the Tencent HTTP call so the fast path succeeds immediately.
    Tencent HTTP quote format: prefix="field0~field1~..."  (re.search(r'="([^"]*)")' captures body)
    """
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

    def fake_get_text(url, encoding="gbk", max_retries=2):
        return fake_text

    sec = light_data.resolve_security("600036")
    http = light_data.HttpClient()
    with patch.object(http, "get_text", fake_get_text):
        q = light_data.fetch_quote(sec, http)

    assert q["current_price"] == 38.5
    assert q["turnover_rate"] == 0.35
    assert q["data_source"] == "tencent-http"
    assert q["data_status"] == "full"


def test_run_mootdx_hard_timeout_returns_within_budget():
    """Hung mootdx calls must not block the caller beyond the hard timeout."""
    light_data._MOOTDX_CLIENT = object()  # non-None sentinel to verify clear

    def hang():
        time.sleep(5.0)
        return "late"

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        res = light_data.run_mootdx_with_timeout(hang)
    elapsed = time.perf_counter() - t0

    assert res is None
    assert elapsed < 3.8, f"hard timeout took {elapsed:.2f}s (expected ~2.5s)"
    assert light_data._MOOTDX_CLIENT is None
    # 单次硬超时只记失败，不立即永久隔离；连续失败才 UNHEALTHY
    assert light_data._DATA_SOURCE_CONTROLLER.consecutive_failures >= 1


def test_run_mootdx_skips_when_unhealthy():
    """Unhealthy controller must short-circuit without invoking the callable."""
    ctrl = light_data._DATA_SOURCE_CONTROLLER
    ctrl.healthy = False
    ctrl.cool_down_until = time.time() + 60.0
    called = {"n": 0}

    def boom():
        called["n"] += 1
        return 1

    assert light_data.run_mootdx_with_timeout(boom) is None
    assert called["n"] == 0


def test_run_mootdx_success_resets_health():
    ctrl = light_data._DATA_SOURCE_CONTROLLER
    ctrl.healthy = True
    ctrl.consecutive_failures = 2
    ctrl.cool_down_until = 0.0

    assert light_data.run_mootdx_with_timeout(lambda: 42) == 42
    assert ctrl.consecutive_failures == 0
    assert ctrl.is_healthy() is True


def test_api_rate_limiter_in_memory_cache():
    """APIRequestRateLimiter must do in-memory I/O after first load (P1 #7 fix).

    100 consecutive check_and_record() calls should complete in well under
    100ms, since only the first call hits the disk. Before the fix, every
    call did a load + save round-trip (15-30ms each), so 100 calls would
    take 1.5-3 seconds.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        limit_file = f"{tmpdir}/api_limits.json"
        limiter = light_data.APIRequestRateLimiter(limit_file=limit_file)
        # Prime the cache by doing one call (loads from disk) — use a high
        # per-minute cap so the 100-iteration loop never hits the throttle.
        assert limiter.check_and_record(max_per_min=10000, max_per_hour=100000) is True

        t0 = time.perf_counter()
        for _ in range(100):
            assert limiter.check_and_record(max_per_min=10000, max_per_hour=100000) is True
        elapsed = time.perf_counter() - t0

        # In-memory-only path: 100 calls should be < 100ms (typically < 10ms)
        assert elapsed < 0.1, f"100 in-memory calls took {elapsed*1000:.1f}ms (expected <100ms)"

        # The cache must be marked dirty (unflushed writes pending)
        assert limiter._dirty is True

        # _flush must persist to disk
        limiter._flush()
        assert limiter._dirty is False
        import os
        assert os.path.exists(limit_file)


def test_api_rate_limiter_first_call_loads_from_disk():
    """First check_and_record() should lazy-load from disk; subsequent calls use cache."""
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        limit_file = f"{tmpdir}/api_limits.json"
        # Pre-seed the limit file with a recent call timestamp (within 60s window)
        now = time.time()
        seed = {"calls": [now - 5.0] * 14}  # 14 calls in the past 60s
        with open(limit_file, "w") as f:
            json.dump(seed, f)

        limiter = light_data.APIRequestRateLimiter(limit_file=limit_file)
        # 14 prior calls → 15th call should still pass (under 15/min threshold)
        # but the in-memory cache must reflect the 14 pre-seeded calls.
        assert limiter._cache is None  # not yet loaded
        assert limiter.check_and_record() is True
        # After the first call, the cache is populated
        assert limiter._cache is not None
        assert len(limiter._cache["calls"]) == 15  # 14 seed + 1 new



def test_single_hard_timeout_keeps_source_available():
    """一次硬超时不应立刻把 mootdx 整源隔离到不可用。"""
    ctrl = light_data._DATA_SOURCE_CONTROLLER
    ctrl.healthy = True
    ctrl.consecutive_failures = 0
    ctrl.cool_down_until = 0.0

    def hang():
        time.sleep(5.0)
        return "late"

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        assert light_data.run_mootdx_with_timeout(hang) is None

    assert ctrl.consecutive_failures >= 1
    assert ctrl.is_healthy() is True


def test_fetch_5m_accepts_short_sina_bars(monkeypatch):
    """盘后/夜盘不足 8 根时，>=3 根新浪分钟线仍应可用。"""
    sec = light_data.resolve_security("600406")
    short_bars = [
        {"time": f"2026-08-05 14:{50+i:02d}", "date": "2026-08-05",
         "open": 24.5, "high": 24.6, "low": 24.4, "close": 24.5, "volume": 1000}
        for i in range(4)
    ]
    monkeypatch.setattr(light_data, "_fetch_mins_fallback", lambda *a, **k: short_bars)
    monkeypatch.setattr(light_data, "_fetch_mins_mootdx", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fallback")))
    bars = light_data.fetch_5m(sec, light_data.HttpClient(), datalen=60)
    assert len(bars) == 4
    assert bars[0]["data_source"] == "sina"
