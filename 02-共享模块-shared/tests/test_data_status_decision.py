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
        bars = [{"close": 10.0, "data_status": "full"} for _ in range(100)]
        bars[50] = {"close": 9.9, "data_status": "partial"}  # 个别质量 partial
        return bars

    def fake_5m(sec, http, datalen=60):
        return [{"close": 10.0, "data_status": "full"} for _ in range(60)]

    def fake_weekly(sec, http, datalen=80):
        return [{"close": 10.0, "data_status": "full"} for _ in range(80)]

    def fake_monthly(sec, http, datalen=60):
        return [{"close": 10.0, "data_status": "full"} for _ in range(60)]

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
