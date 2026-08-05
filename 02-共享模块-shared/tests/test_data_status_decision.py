"""data_status 完备度判定回归测试。

修复背景（batch-8 排查）：
1. `_check_mootdx` 原用 `from mootdx.quotes import Q`（导出名错误，实际为 `Quotes`），
   导致 mootdx 备份通道整体失效，周月线永远取不到 → 每次分析 data_status=partial。
2. `fetch_weekly`/`fetch_monthly` 把取到的周月线 bar 无条件标 `partial`（mootdx 是周月线
   唯一主源，取到即完整），加剧整体 partial。
3. `load_market_snapshot` 的 data_status 判定曾检查各源 internal bar 的 data_status，
   而 `daily_bars` 总有个别 bar 因非前复权等细节标 partial，导致「即使所有源都取到数据，
   整体也永远 partial」。修复后 data_status 只看 `missing_sources`（分项源是否整体缺失）
   + 核心 `quote` 是否降级，内部个别 bar 的质量标记不再反向降级整体完备度。

本测试用 mock 数据源锁定上述第 3 点逻辑，不依赖网络。
"""
from types import SimpleNamespace

import trader_shared.light_data as ld


def _patch_full_sources(monkeypatch):
    """所有源都成功取到，且 daily_bars 含 1 条质量 partial bar（模拟非前复权）。"""
    def fake_quote(sec, http):
        return {"current_price": 10.0, "data_status": "full"}

    def fake_daily(sec, http, days=300):
        # 带日期，避免周线护栏/正序逻辑把无日期序列判废
        bars = [
            {"date": f"2026-01-{(i % 28) + 1:02d}", "close": 10.0, "data_status": "full"}
            for i in range(100)
        ]
        bars[50] = {"date": "2026-02-20", "close": 9.9, "data_status": "partial"}  # 个别质量 partial
        return bars

    def fake_5m(sec, http, datalen=60):
        return [
            {"time": f"2026-08-05 10:{i:02d}", "close": 10.0, "data_status": "full"}
            for i in range(60)
        ]

    def fake_weekly(sec, http, datalen=80):
        # 周级间距，避免被 weekly_bars_look_like_weekly 判成日线后聚合清空
        return [
            {"date": f"2024-{(i % 12) + 1:02d}-{((i % 3) * 7) + 1:02d}", "close": 10.0, "data_status": "full"}
            for i in range(80)
        ]

    def fake_monthly(sec, http, datalen=60):
        return [
            {"date": f"{2020 + (i // 12)}-{(i % 12) + 1:02d}-01", "close": 10.0, "data_status": "full"}
            for i in range(60)
        ]

    def fake_ticks(sec, n):
        return []

    monkeypatch.setattr(ld, "resolve_security",
                        lambda t: SimpleNamespace(code="688248", market="SH"))
    monkeypatch.setattr(ld, "fetch_quote", fake_quote)
    monkeypatch.setattr(ld, "fetch_qfq_daily", fake_daily)
    monkeypatch.setattr(ld, "fetch_5m", fake_5m)
    monkeypatch.setattr(ld, "fetch_weekly", fake_weekly)
    monkeypatch.setattr(ld, "fetch_monthly", fake_monthly)
    monkeypatch.setattr(ld, "_fetch_ticks_tdx3", fake_ticks)


def test_data_status_full_when_daily_has_partial_bar(monkeypatch):
    """daily_bars 含个别质量 partial bar 时，整体 data_status 仍应为 full。"""
    _patch_full_sources(monkeypatch)
    snap = ld.load_market_snapshot("688248")
    assert snap.data_status == "full"
    assert snap.missing_sources == []


def test_data_status_partial_when_weekly_missing(monkeypatch):
    """分项源（周线）整体缺失时，data_status 应降级为 partial 且 missing_sources 记录。"""
    _patch_full_sources(monkeypatch)

    def fake_weekly_empty(sec, http, datalen=80):
        return []

    monkeypatch.setattr(ld, "fetch_weekly", fake_weekly_empty)
    snap = ld.load_market_snapshot("688248")
    assert snap.data_status == "partial"
    assert "weekly_bars" in snap.missing_sources


def test_data_status_full_when_quote_full_all_sources_present(monkeypatch):
    """所有源齐全且 quote 为 full 时，data_status 应为 full（核心 happy path）。"""
    _patch_full_sources(monkeypatch)
    snap = ld.load_market_snapshot("688248")
    assert snap.data_status == "full"
    assert snap.quote.get("data_status") == "full"


def _make_tushare_provider(monkeypatch):
    """构造可注入 fetch_* 的 TushareProvider（跳过真实 client）。"""
    from trader_shared.data_provider import TushareProvider
    from trader_shared.market_types import Security

    provider = TushareProvider.__new__(TushareProvider)
    provider._client = None
    provider._fallback = SimpleNamespace()
    provider.resolve_security = lambda t: Security(code="688248", market="SH", name="南网科技")

    def _enrich(snap):
        return snap

    monkeypatch.setattr(
        "trader_shared.data_provider._enrich_snapshot",
        _enrich,
    )
    return provider


def test_tushare_data_status_partial_when_weekly_missing(monkeypatch):
    """Tushare 路径：周线缺失应 partial，且写入 missing_sources（与 light_data 对齐）。"""
    provider = _make_tushare_provider(monkeypatch)
    provider.fetch_qfq_daily = lambda sec, days=365: [{"close": 10.0} for _ in range(50)]
    provider.fetch_quote = lambda sec: {"current_price": 10.0, "data_status": "full"}
    provider.fetch_5m = lambda sec, datalen=60: [{"close": 10.0} for _ in range(20)]
    provider.fetch_weekly = lambda sec, n=80: []
    provider.fetch_monthly = lambda sec, datalen=60: [{"close": 10.0}]
    provider.fetch_ticks = lambda sec, count=500: []

    snap = provider.load_market_snapshot(
        "南网科技",
        include_5m=True,
        include_weekly=True,
        include_monthly=False,
        include_ticks=False,
    )
    assert snap.data_status == "partial"
    assert "weekly_bars" in snap.missing_sources


def test_tushare_data_status_full_when_requested_sources_ok(monkeypatch):
    """Tushare 路径：请求的源齐全 → full。"""
    provider = _make_tushare_provider(monkeypatch)
    provider.fetch_qfq_daily = lambda sec, days=365: [{"close": 10.0} for _ in range(50)]
    provider.fetch_quote = lambda sec: {"current_price": 10.0, "data_status": "full"}
    provider.fetch_5m = lambda sec, datalen=60: [{"close": 10.0} for _ in range(20)]
    provider.fetch_weekly = lambda sec, n=80: [{"close": 10.0} for _ in range(20)]
    provider.fetch_monthly = lambda sec, datalen=60: []
    provider.fetch_ticks = lambda sec, count=500: []

    snap = provider.load_market_snapshot(
        "南网科技",
        include_5m=True,
        include_weekly=True,
        include_monthly=False,
        include_ticks=False,
    )
    assert snap.data_status == "full"


def test_enrich_payload_useful_rejects_none_shell():
    from trader_shared.data_provider import _enrich_payload_useful

    assert not _enrich_payload_useful(
        {"shareholder": None, "consensus_eps": None},
        {"unlocks": None, "theme_harden": None},
        None,
        None,
        None,
        None,
    )
    assert _enrich_payload_useful(
        {"shareholder": {"count": 1}, "consensus_eps": None},
        {},
        None,
        None,
        None,
        None,
    )



def test_report_builder_missing_data_message(monkeypatch):
    """核心行情缺失时，错误应点名 missing quote/daily，而不是一句空话。"""
    import pytest
    from trader_shared.market_types import MarketSnapshot, Security

    class _P:
        def load_market_snapshot(self, *a, **k):
            return MarketSnapshot(
                security=Security(code="600406", market="SH", name="国电南瑞"),
                quote={},
                daily_bars=[],
                data_status="failed",
                missing_sources=["quote", "daily"],
                source_errors={"quote": "empty"},
            )

    # build_report 内部 from trader_shared.data_provider import get_provider
    monkeypatch.setattr(
        "trader_shared.data_provider.get_provider",
        lambda: _P(),
    )
    from trader_shared.report_builder import build_report
    with pytest.raises(RuntimeError) as ei:
        build_report("国电南瑞")
    msg = str(ei.value)
    assert "missing required market data" in msg
    assert "quote" in msg
    assert "daily" in msg
