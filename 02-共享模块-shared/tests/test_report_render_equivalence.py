"""ADR-003b equivalence gate: domain/presentation split is behavior-preserving.

build_report (domain, in report_builder.py) and the presentation layer
(report_presentation.py) must produce EXACTLY the same render_markdown output
as before the split. This catches any accidental change introduced while moving
render_* / view helpers out of report_builder.py.

The output is captured under a fully offline, deterministic mock seam (all
network leak points patched) and date tokens are masked, so the gate is stable
and fast. Ground truth: tests/fixtures/report_render_baseline.txt
(captured pre-split with the identical seam).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_FIXTURE = _SHARED / "tests" / "fixtures" / "report_render_baseline.txt"


def _mask_dates(text: str) -> str:
    return re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", text)


def _gen_bars(n, start, step):
    bars = []
    price = start
    for i in range(n):
        price = price + step * (1 if i % 2 == 0 else -1) + (i % 7 - 3) * 0.05
        o = price - 0.1
        c = price
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        bars.append({
            "date": f"2026-0{i // 30 + 1:02d}-{i % 28 + 1:02d}",
            "open": round(o, 2), "close": round(c, 2),
            "high": round(h, 2), "low": round(l, 2),
            "volume": 1_000_000 + i * 1000,
            "atr14": 0.5, "atr_ratio": 0.02, "atr7": 0.4, "tr": 0.3,
            "pre_close": round(price - step, 2),
        })
    return bars


class _MockProvider:
    name = "mock"

    def resolve_security(self, target):
        from trader_shared.data_provider import Security
        return Security(code=target, market="SH" if target.startswith("6") else "SZ", name="测试股")

    def fetch_quote(self, sec):
        return {
            "name": "测试股", "symbol": sec.qq_symbol, "current_price": 10.5,
            "pre_close": 10.3, "volume": 5_000_000, "current_change_pct": 1.94,
            "trade_date": "2026-07-10", "trade_time": "15:00", "turnover_rate": 2.1,
        }

    def fetch_qfq_daily(self, sec, days=365):
        return _gen_bars(80, 9.0, 0.05)

    def fetch_kline(self, sec, **kw):
        return []

    def load_market_snapshot(self, target, days=365, include_5m=True,
                             include_weekly=True, include_monthly=True, include_ticks=True):
        from trader_shared.data_provider import MarketSnapshot
        daily = _gen_bars(80, 9.0, 0.05)
        weekly = _gen_bars(40, 9.0, 0.12)
        monthly = _gen_bars(16, 9.0, 0.4)
        bars_5m = _gen_bars(10, 10.4, 0.02)
        return MarketSnapshot(
            security=self.resolve_security(target),
            quote=self.fetch_quote(self.resolve_security(target)),
            daily_bars=daily, bars_5m=bars_5m,
            weekly_bars=weekly, monthly_bars=monthly, data_status="full",
        )


class _UnavailableClient:
    available = False


def _render_under_seam(monkeypatch, target: str = "600000") -> str:
    import trader_shared.tushare_client as _tc
    import trader_shared.chip_data as _chip
    import trader_shared.market_env as _me
    import trader_shared.cache_utils as _cu
    from trader_shared import fetchers as _fetchers
    from trader_shared.data_provider import set_provider

    set_provider(_MockProvider())
    # All patches go through monkeypatch so global state is restored after the
    # test (otherwise TencentFetcher stays MockFetcher and breaks later tests).
    monkeypatch.setattr(_fetchers, "TencentFetcher", _fetchers.MockFetcher)
    monkeypatch.setattr(
        _me, "get_env_for_skill",
        lambda *a, **k: {"level": "正常", "hmm_regime_en": "range"},
    )
    monkeypatch.setattr(_cu, "fetch_fund_flow_cached", lambda *a, **k: None)
    monkeypatch.setattr(_tc, "get_client", lambda *a, **k: _UnavailableClient())
    monkeypatch.setattr(_chip, "get_cyq_perf", lambda *a, **k: None)

    from trader_shared.report_builder import build_report, render_markdown

    report = build_report(target)
    return _mask_dates(render_markdown(report))


def test_report_render_equivalence(monkeypatch):
    """render_markdown output must be byte-identical to the pre-split baseline."""
    if not _FIXTURE.exists():
        pytest.skip(f"fixture missing: {_FIXTURE}")

    expected = _FIXTURE.read_text(encoding="utf-8")
    actual = _render_under_seam(monkeypatch)

    assert actual == expected, (
        "render_markdown output changed after domain/presentation split.\n"
        f"expected {len(expected)} chars, got {len(actual)} chars.\n"
        "Run scripts/_render_eq_capture.py to refresh, ONLY after confirming the "
        "change is intended."
    )
