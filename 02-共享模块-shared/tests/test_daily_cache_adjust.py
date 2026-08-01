"""日 K 缓存分桶 + Tushare 未复权降级。"""
from __future__ import annotations

from unittest.mock import MagicMock

import trader_shared.cache_utils as cu
import trader_shared.data_provider as dp


def test_unified_provider_uses_qfq_cache_bucket(monkeypatch):
    seen: dict = {}

    def _scoped(key, target, fetch_fn, min_rows=1):
        seen["key"] = key
        seen["target"] = target
        # 真实路径会调用 fetch_fn；此处模拟命中后的 qfq 行
        rows = list(fetch_fn() or [])
        return rows or [{"date": "2026-07-10", "close": 1.0, "adjust": "qfq"}]

    monkeypatch.setattr(cu, "get_day_scoped_bars", _scoped)
    provider = dp.UnifiedProvider(backend="tencent")
    provider._http = object()  # skip ensure_http network
    monkeypatch.setattr(provider, "_ensure_http", lambda: None)
    monkeypatch.setattr(
        "trader_shared.light_data.fetch_qfq_daily",
        lambda *a, **k: [{"date": "2026-07-10", "close": 1.0, "adjust": "qfq"}],
    )
    sec = dp.Security(code="688248", market="sh", name="南网科技")
    bars = provider.fetch_qfq_daily(sec, days=30)
    assert bars
    assert seen["key"] == cu.CACHE_DAILY
    assert seen["target"] == "tencent/qfq/688248"


def test_unified_provider_does_not_poison_qfq_bucket(monkeypatch):
    """腾讯仅 day（未复权）时：可返回 bars，但禁止写入 tencent/qfq。"""
    writes: list[tuple] = []
    store: dict = {}

    def _get(key, target, ttl=0):
        return None

    def _set(key, target, data):
        writes.append((key, target, data))
        store[(key, target)] = data

    def _scoped(key, target, fetch_fn, min_rows=1):
        # 与生产 get_day_scoped_bars 一致：成功才写入 target
        rows = list(fetch_fn() or [])
        if isinstance(rows, list) and len(rows) >= min_rows:
            _set(key, target, {"fetch_date": "2026-07-10", "rows": rows})
            return rows
        return rows

    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-10")
    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)
    monkeypatch.setattr(cu, "get_day_scoped_bars", _scoped)

    unadj = [
        {
            "date": f"2026-07-{i:02d}",
            "open": 10.0,
            "close": 10.0,
            "high": 10.5,
            "low": 9.5,
            "volume": 1,
            "adjust": "none",
            "data_source": "tencent-http",
            "data_status": "partial",
        }
        for i in range(1, 25)
    ]
    provider = dp.UnifiedProvider(backend="tencent")
    provider._http = object()
    monkeypatch.setattr(provider, "_ensure_http", lambda: None)
    monkeypatch.setattr(
        "trader_shared.light_data.fetch_qfq_daily",
        lambda *a, **k: unadj,
    )
    # ensure_bars_ascending 透传，避免 ATR 依赖
    monkeypatch.setattr(
        "trader_shared.light_data.ensure_bars_ascending",
        lambda rows, **kw: (list(rows), False),
    )

    sec = dp.Security(code="688248", market="sh", name="南网科技")
    bars = provider.fetch_qfq_daily(sec, days=30)
    assert len(bars) >= 20
    assert all(b.get("adjust") == "none" for b in bars)
    qfq_writes = [w for w in writes if w[1] == "tencent/qfq/688248"]
    none_writes = [w for w in writes if w[1] == "tencent/none/688248"]
    assert not qfq_writes, f"qfq bucket poisoned: {qfq_writes}"
    assert none_writes, "expected unadjusted bars under tencent/none"


def test_daily_bars_look_qfq_helpers():
    assert dp._daily_bars_look_qfq(
        [{"adjust": "qfq", "data_source": "tencent-http"}]
    )
    assert not dp._daily_bars_look_qfq(
        [{"adjust": "none", "data_source": "tushare"}]
    )
    assert dp._daily_bars_are_unadjusted(
        [{"adjust": "none"}, {"adjust": "none"}]
    )
    assert not dp._daily_bars_are_unadjusted(
        [{"adjust": "qfq"}, {"adjust": "none"}]
    )


def test_tushare_snapshot_marks_missing_daily_qfq(monkeypatch):
    """未复权日 K → missing_sources 含 daily_qfq，data_status 不得 full。"""
    mock_client = MagicMock()
    mock_client.available = True
    provider = dp.TushareProvider.__new__(dp.TushareProvider)
    provider._client = mock_client
    provider._fallback = MagicMock()

    unadj = [
        {
            "date": f"2026-07-{i:02d}",
            "open": 10.0,
            "close": 10.0,
            "high": 10.5,
            "low": 9.5,
            "volume": 1,
            "adjust": "none",
            "data_source": "tushare",
            "data_status": "partial",
        }
        for i in range(1, 25)
    ]
    quote = {"current_price": 10.0, "data_status": "full"}

    monkeypatch.setattr(
        provider,
        "resolve_security",
        lambda t: dp.Security(code="000001", market="SZ", name="平安银行"),
    )
    monkeypatch.setattr(provider, "fetch_qfq_daily", lambda sec, days=365: unadj)
    monkeypatch.setattr(provider, "fetch_quote", lambda sec: quote)
    monkeypatch.setattr(provider, "fetch_5m", lambda sec: [{"time": "09:35"}] * 10)
    monkeypatch.setattr(provider, "fetch_weekly", lambda sec: unadj[:8])
    monkeypatch.setattr(provider, "fetch_monthly", lambda sec: unadj[:6])
    monkeypatch.setattr(provider, "fetch_ticks", lambda sec, count=500: [])
    monkeypatch.setattr(dp, "_enrich_snapshot", lambda s: s)

    snap = provider.load_market_snapshot(
        "000001",
        days=30,
        include_5m=True,
        include_weekly=True,
        include_monthly=True,
        include_ticks=False,
    )
    assert "daily_qfq" in (snap.missing_sources or [])
    assert snap.data_status == "partial"
