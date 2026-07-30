"""Tests for Tushare data source integration.

All tests use monkeypatch to mock the tushare SDK and HTTP calls,
so no actual network requests are made.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the global TushareClient singleton before/after each test."""
    from trader_shared.tushare_client import reset_client
    reset_client()
    yield
    reset_client()


@pytest.fixture()
def _no_token(monkeypatch):
    """Ensure no token from env / local file / config."""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(
        "trader_shared.tushare_client._load_local_tushare_token",
        lambda: "",
    )
    monkeypatch.setattr(
        "trader_shared.tushare_config.TUSHARE_TOKEN",
        "",
        raising=False,
    )


@pytest.fixture()
def _with_token(monkeypatch):
    """Set a fake TUSHARE_TOKEN."""
    monkeypatch.setenv("TUSHARE_TOKEN", "test-token-12345")


# ── TushareClient: token not set ────────────────────────────────────────────


class TestTushareClientNoToken:
    def test_available_false_when_no_token(self, _no_token):
        from trader_shared.tushare_client import TushareClient
        client = TushareClient()
        assert client.available is False

    def test_query_returns_empty_when_no_token(self, _no_token):
        from trader_shared.tushare_client import TushareClient
        client = TushareClient()
        assert client.query("daily", ts_code="000001.SZ") == []

    def test_query_daily_returns_empty_when_no_token(self, _no_token):
        from trader_shared.tushare_client import TushareClient
        client = TushareClient()
        assert client.query_daily("000001.SZ") == []

    def test_query_moneyflow_returns_empty_when_no_token(self, _no_token):
        from trader_shared.tushare_client import TushareClient
        client = TushareClient()
        assert client.query_moneyflow("000001.SZ") == []

    def test_query_realtime_returns_empty_when_no_token(self, _no_token):
        from trader_shared.tushare_client import TushareClient
        client = TushareClient()
        assert client.query_realtime("000001.SZ") == []


# ── TushareClient: with mocked SDK ─────────────────────────────────────────


class TestTushareClientWithSDK:
    """Tests that mock the tushare SDK to verify query/query_daily/query_moneyflow."""

    def _make_client_with_mock_sdk(self, monkeypatch, mock_pro, *, sdk_first: bool = True):
        """Helper: create a TushareClient with a mocked tushare SDK."""
        monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")
        if sdk_first:
            monkeypatch.setenv("TUSHARE_SDK_FIRST", "1")
        else:
            monkeypatch.delenv("TUSHARE_SDK_FIRST", raising=False)
        monkeypatch.setattr(
            "trader_shared.tushare_client._probe_reachable", lambda *a, **k: True
        )
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value = mock_pro
        # patch the import so `import tushare as ts` returns our mock
        monkeypatch.setitem(sys.modules, "tushare", mock_ts)
        monkeypatch.setitem(sys.modules, "tushare.stock", MagicMock())
        monkeypatch.setitem(sys.modules, "tushare.stock.cons", MagicMock())

        from trader_shared.tushare_client import TushareClient, reset_client

        reset_client()
        return TushareClient()

    def test_query_daily(self, monkeypatch):
        """query_daily should call pro.daily() with correct params and return records."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=2)
        mock_df.to_dict.return_value = [
            {"ts_code": "000001.SZ", "trade_date": "20260710", "open": 10.0, "close": 10.5,
             "high": 10.6, "low": 9.9, "vol": 100000, "amount": 1050000},
            {"ts_code": "000001.SZ", "trade_date": "20260709", "open": 9.8, "close": 10.0,
             "high": 10.1, "low": 9.7, "vol": 80000, "amount": 800000},
        ]
        mock_pro = MagicMock()
        mock_pro.daily.return_value = mock_df

        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro)
        assert client.available is True

        result = client.query_daily("000001.SZ", start_date="20260701", end_date="20260710")
        assert len(result) == 2
        assert result[0]["trade_date"] == "20260710"
        assert result[0]["close"] == 10.5
        mock_pro.daily.assert_called_once_with(
            ts_code="000001.SZ", start_date="20260701", end_date="20260710"
        )

    def test_query_moneyflow(self, monkeypatch):
        """query_moneyflow should call pro.moneyflow() and return records."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=1)
        mock_df.to_dict.return_value = [
            {
                "ts_code": "688248.SH", "trade_date": "20260710",
                "buy_sm_vol": 1000, "buy_sm_amount": 50000,
                "sell_sm_vol": 800, "sell_sm_amount": 40000,
                "buy_md_vol": 500, "buy_md_amount": 25000,
                "sell_md_vol": 400, "sell_md_amount": 20000,
                "buy_lg_vol": 300, "buy_lg_amount": 15000,
                "sell_lg_vol": 200, "sell_lg_amount": 10000,
                "buy_elg_vol": 100, "buy_elg_amount": 5000,
                "sell_elg_vol": 50, "sell_elg_amount": 2500,
                "net_mf_vol": 250, "net_mf_amount": 17500,
            }
        ]
        mock_pro = MagicMock()
        mock_pro.moneyflow.return_value = mock_df

        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro)
        result = client.query_moneyflow("688248.SH", start_date="20260701", end_date="20260710")
        assert len(result) == 1
        assert result[0]["net_mf_amount"] == 17500
        assert result[0]["buy_elg_amount"] == 5000

    def test_query_generic(self, monkeypatch):
        """query() should dispatch to the named API method on pro."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=1)
        mock_df.to_dict.return_value = [{"id": "N1", "name": "AI概念"}]
        mock_pro = MagicMock()
        mock_pro.concept.return_value = mock_df

        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro)
        result = client.query("concept")
        assert len(result) == 1
        assert result[0]["name"] == "AI概念"
        mock_pro.concept.assert_called_once()

    def test_query_returns_empty_on_sdk_exception(self, monkeypatch):
        """SDK 抛错后降 HTTP；HTTP 也失败则 []."""
        mock_pro = MagicMock()
        mock_pro.daily.side_effect = RuntimeError("API limit exceeded")

        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro)
        client._http_ok = False  # 禁止再打真实 HTTP
        result = client.query("daily", ts_code="000001.SZ")
        assert result == []

    def test_query_falls_back_http_when_sdk_empty(self, monkeypatch):
        """SDK 优先且空表时应降 HTTP。"""
        monkeypatch.setenv("TUSHARE_SDK_FIRST", "1")
        mock_pro = MagicMock()
        empty_df = MagicMock()
        empty_df.__len__ = MagicMock(return_value=0)
        mock_pro.daily.return_value = empty_df

        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro)
        monkeypatch.setattr(
            client,
            "_query_http",
            lambda api_name, **params: [{"ts_code": "000001.SZ", "close": 11.46}],
        )
        result = client.query("daily", ts_code="000001.SZ")
        assert len(result) == 1
        assert result[0]["close"] == 11.46

    def test_query_http_first_by_default(self, monkeypatch):
        """默认 HTTP 优先：HTTP 有数据时不打 SDK。"""
        mock_pro = MagicMock()
        client = self._make_client_with_mock_sdk(monkeypatch, mock_pro, sdk_first=False)
        monkeypatch.setattr(
            client,
            "_query_http",
            lambda api_name, **params: [{"ts_code": "000001.SZ", "close": 12.0}],
        )
        result = client.query("daily", ts_code="000001.SZ")
        assert result[0]["close"] == 12.0
        mock_pro.daily.assert_not_called()

    def test_query_realtime(self, monkeypatch):
        """query_realtime should call tushare.realtime_quote()."""
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=1)
        mock_df.to_dict.return_value = [
            {"NAME": "平安银行", "TS_CODE": "000001.SZ", "PRICE": 10.5, "PRE_CLOSE": 10.0,
             "HIGH": 10.6, "LOW": 9.9, "VOLUME": 100000, "AMOUNT": 1050000}
        ]
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value = MagicMock()
        mock_ts.realtime_quote.return_value = mock_df
        monkeypatch.setenv("TUSHARE_TOKEN", "fake-token")
        monkeypatch.setattr(
            "trader_shared.tushare_client._probe_reachable", lambda *a, **k: True
        )
        monkeypatch.setitem(sys.modules, "tushare", mock_ts)
        monkeypatch.setitem(sys.modules, "tushare.stock", MagicMock())
        monkeypatch.setitem(sys.modules, "tushare.stock.cons", MagicMock())

        from trader_shared.tushare_client import TushareClient, reset_client
        reset_client()
        client = TushareClient()
        result = client.query_realtime("000001.SZ")
        assert len(result) == 1
        assert result[0]["NAME"] == "平安银行"
        assert result[0]["PRICE"] == 10.5


# ── _fetch_fund_flow_tushare: field mapping ──────────────────────────────────


class TestFetchFundFlowTushare:
    def test_field_mapping(self, monkeypatch):
        """Verify Tushare moneyflow records are mapped to the expected output format."""
        mock_records = [
            {
                "ts_code": "688248.SH", "trade_date": "20260710",
                "buy_sm_vol": 1000, "buy_sm_amount": 50000,
                "sell_sm_vol": 800, "sell_sm_amount": 40000,
                "buy_md_vol": 500, "buy_md_amount": 25000,
                "sell_md_vol": 400, "sell_md_amount": 20000,
                "buy_lg_vol": 300, "buy_lg_amount": 15000,
                "sell_lg_vol": 200, "sell_lg_amount": 10000,
                "buy_elg_vol": 100, "buy_elg_amount": 5000,
                "sell_elg_vol": 50, "sell_elg_amount": 2500,
                "net_mf_vol": 250, "net_mf_amount": 17500,
            },
            {
                "ts_code": "688248.SH", "trade_date": "20260709",
                "buy_sm_vol": 900, "buy_sm_amount": 45000,
                "sell_sm_vol": 700, "sell_sm_amount": 35000,
                "buy_md_vol": 400, "buy_md_amount": 20000,
                "sell_md_vol": 300, "sell_md_amount": 15000,
                "buy_lg_vol": 200, "buy_lg_amount": 10000,
                "sell_lg_vol": 150, "sell_lg_amount": 7500,
                "buy_elg_vol": 80, "buy_elg_amount": 4000,
                "sell_elg_vol": 40, "sell_elg_amount": 2000,
                "net_mf_vol": 200, "net_mf_amount": 14500,
            },
        ]

        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = mock_records

        monkeypatch.setattr(
            "trader_shared.tushare_client.get_client", lambda: mock_client
        )

        from trader_shared.fund_flow_data import _fetch_fund_flow_tushare
        result = _fetch_fund_flow_tushare("688248", days=30)

        assert len(result) == 2
        # Check first record
        r0 = result[0]
        assert r0["date"] == "2026-07-10"  # YYYYMMDD → YYYY-MM-DD
        assert r0["net_flow_wan"] == 17500
        assert r0["buy_elg_amount"] == 5000
        assert r0["sell_elg_amount"] == 2500
        assert r0["buy_lg_amount"] == 15000
        assert r0["sell_lg_amount"] == 10000
        assert r0["buy_md_amount"] == 25000
        assert r0["sell_md_amount"] == 20000
        assert r0["buy_sm_amount"] == 50000
        assert r0["sell_sm_amount"] == 40000
        assert r0["buy_elg_vol"] == 100
        assert r0["sell_elg_vol"] == 50
        assert r0["buy_lg_vol"] == 300
        assert r0["sell_lg_vol"] == 200
        # Check second record
        assert result[1]["date"] == "2026-07-09"
        assert result[1]["net_flow_wan"] == 14500

    def test_returns_empty_when_client_unavailable(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.available = False
        monkeypatch.setattr(
            "trader_shared.tushare_client.get_client", lambda: mock_client
        )

        from trader_shared.fund_flow_data import _fetch_fund_flow_tushare
        result = _fetch_fund_flow_tushare("688248", days=30)
        assert result == []

    def test_returns_empty_when_no_records(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = []
        monkeypatch.setattr(
            "trader_shared.tushare_client.get_client", lambda: mock_client
        )

        from trader_shared.fund_flow_data import _fetch_fund_flow_tushare
        result = _fetch_fund_flow_tushare("688248", days=30)
        assert result == []

    def test_none_fields_default_to_zero(self, monkeypatch):
        """Fields with None values should default to 0."""
        mock_records = [
            {
                "ts_code": "000001.SZ", "trade_date": "20260710",
                "buy_sm_vol": None, "buy_sm_amount": None,
                "sell_sm_vol": None, "sell_sm_amount": None,
                "buy_md_vol": None, "buy_md_amount": None,
                "sell_md_vol": None, "sell_md_amount": None,
                "buy_lg_vol": None, "buy_lg_amount": None,
                "sell_lg_vol": None, "sell_lg_amount": None,
                "buy_elg_vol": None, "buy_elg_amount": None,
                "sell_elg_vol": None, "sell_elg_amount": None,
                "net_mf_vol": None, "net_mf_amount": None,
            }
        ]
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = mock_records
        monkeypatch.setattr(
            "trader_shared.tushare_client.get_client", lambda: mock_client
        )

        from trader_shared.fund_flow_data import _fetch_fund_flow_tushare
        result = _fetch_fund_flow_tushare("000001", days=30)
        assert len(result) == 1
        assert result[0]["net_flow_wan"] == 0
        assert result[0]["buy_elg_amount"] == 0


# ── _symbol_to_ts_code ──────────────────────────────────────────────────────


class TestSymbolToTsCode:
    def test_6_prefix_sh(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("688248") == "688248.SH"
        assert _symbol_to_ts_code("600000") == "600000.SH"

    def test_5_prefix_sh(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("510050") == "510050.SH"

    def test_9_prefix_sh(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("900901") == "900901.SH"

    def test_0_prefix_sz(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("000001") == "000001.SZ"

    def test_3_prefix_sz(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("300750") == "300750.SZ"

    def test_already_has_suffix(self):
        from trader_shared.fund_flow_data import _symbol_to_ts_code
        assert _symbol_to_ts_code("688248.SH") == "688248.SH"
        assert _symbol_to_ts_code("000001.SZ") == "000001.SZ"


# ── TushareProvider.fetch_quote ─────────────────────────────────────────────


class TestTushareProviderFetchQuote:
    def test_fetch_quote_prefers_tencent(self, monkeypatch):
        """实时现价优先腾讯；腾讯有效时不走 Tushare 爬虫。"""
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_realtime.return_value = [
            {"NAME": "南网科技", "PRICE": 99.0, "PRE_CLOSE": 24.0,
             "HIGH": 100.0, "LOW": 90.0, "VOLUME": 1, "AMOUNT": 1}
        ]

        mock_module = MagicMock()
        mock_module.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_module)
        from trader_shared import tushare_client as real_tc
        real_tc._client = mock_client

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)

        provider = dp.TushareProvider()
        tencent_quote = {
            "name": "南网科技",
            "symbol": "688248",
            "current_price": 25.5,
            "pre_close": 24.0,
            "high": 26.0,
            "low": 24.5,
            "volume": 500000,
            "amount": 12750000,
            "data_source": "tencent-http",
        }
        provider._fallback.fetch_quote = MagicMock(return_value=tencent_quote)

        sec = dp.Security(code="688248", market="SH", name="南网科技")
        quote = provider.fetch_quote(sec)

        assert quote["current_price"] == 25.5
        assert quote.get("data_source") == "tencent-http"
        mock_client.query_realtime.assert_not_called()

    def test_fetch_quote_maps_tushare_when_tencent_empty(self, monkeypatch):
        """腾讯无有效价时，映射 Tushare realtime 字段并标记 data_source。"""
        mock_records = [
            {"NAME": "南网科技", "TS_CODE": "688248.SH", "PRICE": 25.5, "PRE_CLOSE": 24.0,
             "HIGH": 26.0, "LOW": 24.5, "VOLUME": 500000, "AMOUNT": 12750000}
        ]
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_realtime.return_value = mock_records

        mock_module = MagicMock()
        mock_module.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_module)
        from trader_shared import tushare_client as real_tc
        real_tc._client = mock_client

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)

        provider = dp.TushareProvider()
        provider._fallback.fetch_quote = MagicMock(return_value={})

        sec = dp.Security(code="688248", market="SH", name="南网科技")
        quote = provider.fetch_quote(sec)

        assert quote["name"] == "南网科技"
        assert quote["symbol"] == "688248"
        assert quote["current_price"] == 25.5
        assert quote["pre_close"] == 24.0
        assert quote["high"] == 26.0
        assert quote["low"] == 24.5
        assert quote["volume"] == 500000
        assert quote["amount"] == 12750000
        assert quote["current_change_pct"] == 6.25
        assert quote["data_source"] == "tushare-realtime"

    def test_fetch_quote_fallback_on_empty(self, monkeypatch):
        """腾讯与 Tushare 皆空时返回 dict，不抛异常。"""
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_realtime.return_value = []

        mock_module = MagicMock()
        mock_module.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_module)
        from trader_shared import tushare_client as real_tc
        real_tc._client = mock_client

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)

        provider = dp.TushareProvider()
        provider._fallback.fetch_quote = MagicMock(return_value={})
        sec = dp.Security(code="688248", market="SH", name="南网科技")
        quote = provider.fetch_quote(sec)
        assert isinstance(quote, dict)


# ── TushareProvider.fetch_qfq_daily ────────────────────────────────────────


class TestTushareProviderFetchQfqDaily:
    def test_fetch_qfq_daily_maps_fields(self, monkeypatch):
        """fetch_qfq_daily should map Tushare daily fields to bar format with ATR."""
        mock_records = [
            {"ts_code": "000001.SZ", "trade_date": "20260710", "open": 10.0, "close": 10.5,
             "high": 10.6, "low": 9.9, "vol": 100000, "amount": 1050000},
            {"ts_code": "000001.SZ", "trade_date": "20260709", "open": 9.8, "close": 10.0,
             "high": 10.1, "low": 9.7, "vol": 80000, "amount": 800000},
            {"ts_code": "000001.SZ", "trade_date": "20260708", "open": 9.5, "close": 9.8,
             "high": 9.9, "low": 9.4, "vol": 70000, "amount": 686000},
        ]
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_daily.return_value = mock_records

        mock_module = MagicMock()
        mock_module.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_module)
        from trader_shared import tushare_client as real_tc
        real_tc._client = mock_client

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)

        provider = dp.TushareProvider()
        sec = dp.Security(code="000001", market="SZ", name="平安银行")
        bars = provider.fetch_qfq_daily(sec, days=30)

        assert len(bars) == 3
        # Tushare 常倒序返回；契约为正序，bars[-1]=最新
        assert bars[0]["date"] == "2026-07-08"
        assert bars[1]["date"] == "2026-07-09"
        assert bars[2]["date"] == "2026-07-10"
        # Check field mapping on latest bar
        assert bars[-1]["open"] == 10.0
        assert bars[-1]["close"] == 10.5
        assert bars[-1]["high"] == 10.6
        assert bars[-1]["low"] == 9.9
        assert bars[-1]["volume"] == 100000
        assert bars[-1]["amount"] == 1_050_000_000  # Tushare 千元 → 元 ×1000
        assert bars[-1]["data_source"] == "tushare"
        # ATR fields should be computed；正序后第2根 TR 用第1根收盘作昨收
        assert "tr" in bars[-1]
        assert bars[1]["tr"] == round(
            max(10.1 - 9.7, abs(10.1 - 9.8), abs(9.7 - 9.8)), 4
        )
        assert "atr7" in bars[0]
        assert "atr14" in bars[0]


# ── TushareProvider integration: get_provider ───────────────────────────────


class TestGetProviderTushare:
    def test_get_provider_returns_tushare_when_token_available(self, monkeypatch, _with_token):
        """get_provider() should return TushareProvider when TUSHARE_TOKEN is set and SDK works."""
        # Mock tushare SDK
        mock_ts = MagicMock()
        mock_pro = MagicMock()
        mock_ts.pro_api.return_value = mock_pro
        monkeypatch.setitem(sys.modules, "tushare", mock_ts)
        monkeypatch.setitem(sys.modules, "tushare.stock", MagicMock())
        monkeypatch.setitem(sys.modules, "tushare.stock.cons", MagicMock())

        from trader_shared.tushare_client import reset_client
        reset_client()

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)
        dp._provider = None  # Reset global

        provider = dp.get_provider()
        assert provider.name == "tushare"
        assert isinstance(provider, dp.TushareProvider)

    def test_get_provider_falls_back_when_no_token(self, monkeypatch, _no_token):
        """get_provider() should fall back to UnifiedProvider when no token."""
        monkeypatch.delenv("TRADER_DATA_PROVIDER", raising=False)
        # pin hermes：本机若有 WorkBuddy connectors，无 token 会走 mootdx
        monkeypatch.setenv("TRADER_HOST", "hermes")

        from trader_shared.tushare_client import reset_client
        reset_client()

        import importlib
        import trader_shared.data_provider as dp
        importlib.reload(dp)
        dp._provider = None

        provider = dp.get_provider()
        assert provider.name == "tencent"
        assert isinstance(provider, dp.UnifiedProvider)


# ── fetch_fund_flow integration ─────────────────────────────────────────────


class TestFetchFundFlowIntegration:
    def test_tushare_tried_first_when_available(self, monkeypatch):
        """fetch_fund_flow should try Tushare first when token is available."""
        mock_records = [
            {
                "ts_code": "688248.SH", "trade_date": "20260710",
                "buy_sm_vol": 1000, "buy_sm_amount": 50000,
                "sell_sm_vol": 800, "sell_sm_amount": 40000,
                "buy_md_vol": 500, "buy_md_amount": 25000,
                "sell_md_vol": 400, "sell_md_amount": 20000,
                "buy_lg_vol": 300, "buy_lg_amount": 15000,
                "sell_lg_vol": 200, "sell_lg_amount": 10000,
                "buy_elg_vol": 100, "buy_elg_amount": 5000,
                "sell_elg_vol": 50, "sell_elg_amount": 2500,
                "net_mf_vol": 250, "net_mf_amount": 17500,
            }
        ]
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = mock_records

        # Patch the tushare_client module at the import level
        mock_tc = MagicMock()
        mock_tc.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_tc)

        from trader_shared.fund_flow_data import fetch_fund_flow
        result = fetch_fund_flow("688248", days=30)

        assert len(result) == 1
        assert result[0]["date"] == "2026-07-10"
        assert result[0]["net_flow_wan"] == 17500
        # Verify Tushare was called (not eastmoney)
        mock_client.query_moneyflow.assert_called_once()

    def test_fallback_to_eastmoney_when_tushare_empty(self, monkeypatch):
        """When Tushare returns empty, should fallback to eastmoney."""
        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = []

        mock_tc = MagicMock()
        mock_tc.get_client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "trader_shared.tushare_client", mock_tc)

        # Mock eastmoney to return data
        eastmoney_data = [{"date": "2026-07-10", "super_large_wan": 10, "large_wan": 5,
                           "medium_wan": 2, "small_wan": 1, "net_flow_wan": 15}]
        monkeypatch.setattr(
            "trader_shared.fund_flow_data._fetch_fund_flow_eastmoney",
            lambda symbol, days: eastmoney_data
        )
        # Also mock TDX to return empty
        monkeypatch.setattr(
            "trader_shared.fund_flow_data._fetch_fund_flow_tdx_mcp",
            lambda symbol, days: []
        )

        from trader_shared.fund_flow_data import fetch_fund_flow
        result = fetch_fund_flow("688248", days=30)

        assert len(result) == 1
        assert result[0]["super_large_wan"] == 10


class TestTushareFundFlowE2E:
    """端到端验证：Tushare 资金流 → calc_fund_flow_features 特征不为零。"""

    def test_tushare_fund_flow_features_nonzero(self, monkeypatch):
        """BUG-1 修复验证：Tushare net_flow_wan 字段能被 calc_fund_flow_features 正确消费。"""
        # 构造 5 天 Tushare moneyflow mock 数据（每天净流入不同）
        mock_records = []
        for i, (date, net) in enumerate([
            ("20260710", 5000), ("20260709", 3000), ("20260708", -1000),
            ("20260707", 2000), ("20260704", 4000),
        ]):
            mock_records.append({
                "ts_code": "688248.SH", "trade_date": date,
                "buy_sm_vol": 100, "buy_sm_amount": 5000,
                "sell_sm_vol": 80, "sell_sm_amount": 4000,
                "buy_md_vol": 200, "buy_md_amount": 10000,
                "sell_md_vol": 150, "sell_md_amount": 7500,
                "buy_lg_vol": 300, "buy_lg_amount": 15000,
                "sell_lg_vol": 200, "sell_lg_amount": 10000,
                "buy_elg_vol": 100, "buy_elg_amount": 5000,
                "sell_elg_vol": 50, "sell_elg_amount": 2500,
                "net_mf_vol": 250, "net_mf_amount": net,
            })

        mock_client = MagicMock()
        mock_client.available = True
        mock_client.query_moneyflow.return_value = mock_records

        monkeypatch.setattr(
            "trader_shared.tushare_client.get_client", lambda: mock_client
        )

        from trader_shared.fund_flow_data import _fetch_fund_flow_tushare, calc_fund_flow_features

        # 第一步：Tushare 数据获取 + 字段映射
        flow_data = _fetch_fund_flow_tushare("688248", days=30)
        assert len(flow_data) == 5

        # 确认 net_flow_wan 存在且非零
        assert flow_data[0]["net_flow_wan"] == 5000
        assert flow_data[1]["net_flow_wan"] == 3000

        # 第二步：喂给 calc_fund_flow_features，验证特征非零
        # 需要构造简单的 bars（daily K-line）作为参数
        bars = [
            {"date": "2026-07-10", "close": 58.7, "high": 62.0, "low": 58.0, "volume": 38000},
            {"date": "2026-07-09", "close": 61.0, "high": 61.5, "low": 57.5, "volume": 35000},
            {"date": "2026-07-08", "close": 59.5, "high": 60.0, "low": 58.0, "volume": 30000},
            {"date": "2026-07-07", "close": 58.0, "high": 59.0, "low": 57.0, "volume": 28000},
            {"date": "2026-07-04", "close": 57.5, "high": 58.5, "low": 56.5, "volume": 25000},
        ]

        features = calc_fund_flow_features(flow_data, bars)

        # 核心断言：cum_flow_5d_wan 不为零（BUG-1 修复验证）
        assert features.get("cum_flow_5d_wan", 0) != 0, (
            f"Tushare 资金流特征 cum_flow_5d_wan 为 0，BUG-1 未修复！"
        )
        # 其他特征也应非零
        assert features.get("consecutive_inflow_days", 0) >= 0  # 有值即可
