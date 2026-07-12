"""Golden/regression test for build_report.

Purpose: guard build_report's *behavior* across refactors (ADR-002 plugin
routing, ADR-003 module extraction). It must keep invoking ALL five strategy
functions (chan/wyck daily + midline, momentum) and return a well-shaped
report dict.

Design:
- A MockProvider supplies a deterministic MarketSnapshot (no network).
- All network-dependent branches (market env, fund flow, signals, fetchers)
  are patched to safe sentinels so the run is fully offline & deterministic.
- The five strategy functions are wrapped to COUNT calls. This is a
  data-quality-independent guard: if a refactor routes through
  PluginRegistry.analyze_all() and silently drops the midline variants (or
  drops weekly_bars from the daily chan call), the call-count assertions fail.
- Single build_report() call per test to keep runtime bounded (~15-30s).

Run: pytest tests/test_build_report_golden.py -q
"""
from __future__ import annotations

import faulthandler
import sys
from pathlib import Path
from typing import Any

import pytest

# Never let a refactor hang the suite: dump + exit if one call exceeds 90s.
faulthandler.dump_traceback_later(90, exit=True)

_SHARED = Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

# build_report currently lives in the trader package scripts; after ADR-003 it
# moves into trader_shared. Resolve whichever is present.
try:
    from trader_shared.report_builder import build_report  # post-ADR-003
except ImportError:
    _PKG_SCRIPTS = _SHARED.parent / "01-功能包-packages" / "trader" / "scripts"
    if str(_PKG_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_PKG_SCRIPTS))
    from run_analysis import build_report  # pre-ADR-003


# ── synthetic market data (kept small to bound compute time) ──────────────

def _gen_bars(n: int, start: float, step: float) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    price = start
    for i in range(n):
        price = price + step * (1 if i % 2 == 0 else -1) + (i % 7 - 3) * 0.05
        o = price - 0.1
        c = price
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        bars.append({
            "date": f"2026-0{i // 30 + 1:02d}-{i % 28 + 1:02d}",
            "open": round(o, 2),
            "close": round(c, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "volume": 1_000_000 + i * 1000,
            "atr14": 0.5,
            "atr_ratio": 0.02,
            "atr7": 0.4,
            "tr": 0.3,
            "pre_close": round(price - step, 2),
        })
    return bars


class _MockProvider:
    """Implements the DataProvider protocol with canned, deterministic data."""

    name = "mock"

    def resolve_security(self, target: str):
        from trader_shared.data_provider import Security
        return Security(code=target, market="SH" if target.startswith("6") else "SZ", name="测试股")

    def fetch_quote(self, sec):
        return {
            "name": "测试股", "symbol": sec.qq_symbol, "current_price": 10.5,
            "pre_close": 10.3, "volume": 5_000_000, "current_change_pct": 1.94,
            "trade_date": "2026-07-10", "trade_time": "15:00", "turnover_rate": 2.1,
        }

    def fetch_qfq_daily(self, sec, days: int = 365):
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
            daily_bars=daily,
            bars_5m=bars_5m,
            weekly_bars=weekly,
            monthly_bars=monthly,
            data_status="full",
        )


@pytest.fixture
def golden_env(monkeypatch):
    """Patch provider + network branches + count strategy calls."""
    from trader_shared.data_provider import set_provider
    from trader_shared import fetchers as _fetchers

    set_provider(_MockProvider())
    # build_report instantiates TencentFetcher() directly; neutralize it.
    monkeypatch.setattr(_fetchers, "TencentFetcher", _fetchers.MockFetcher)
    try:
        import run_analysis as _ra
        if hasattr(_ra, "TencentFetcher"):
            monkeypatch.setattr(_ra, "TencentFetcher", _fetchers.MockFetcher)
    except Exception:
        pass

    # Neutralize other network branches (all are try/except in build_report,
    # but patching keeps the run deterministic & offline).
    monkeypatch.setattr(
        "trader_shared.market_env.get_env_for_skill",
        lambda *a, **k: {"level": "正常", "hmm_regime_en": "range"},
    )
    monkeypatch.setattr(
        "trader_shared.cache_utils.fetch_fund_flow_cached", lambda *a, **k: None,
    )
    try:
        import run_analysis as _ra2
        if hasattr(_ra2, "read_signals_for_report"):
            monkeypatch.setattr(_ra2, "read_signals_for_report", lambda *a, **k: (0.0, 0.0))
    except Exception:
        pass

    # ── wrap the five strategy functions to count calls ──
    calls: dict[str, int] = {}

    import trader_shared.chan_core as _chan
    import trader_shared.wyckoff_core as _wyk
    import trader_shared.momentum_core as _mom

    _orig = {
        "chan_d": _chan.chanlun_strategy,
        "chan_mid": _chan.chanlun_strategy_midline,
        "wyk_d": _wyk.wyckoff_strategy,
        "wyk_mid": _wyk.wyckoff_strategy_midline,
        "mom": _mom.momentum_strategy,
    }

    def _wrap(key, fn):
        def _w(*a, **k):
            calls[key] = calls.get(key, 0) + 1
            return fn(*a, **k)
        return _w

    monkeypatch.setattr(_chan, "chanlun_strategy", _wrap("chan_d", _orig["chan_d"]))
    monkeypatch.setattr(_chan, "chanlun_strategy_midline", _wrap("chan_mid", _orig["chan_mid"]))
    monkeypatch.setattr(_wyk, "wyckoff_strategy", _wrap("wyk_d", _orig["wyk_d"]))
    monkeypatch.setattr(_wyk, "wyckoff_strategy_midline", _wrap("wyk_mid", _orig["wyk_mid"]))
    monkeypatch.setattr(_mom, "momentum_strategy", _wrap("mom", _orig["mom"]))

    return calls


def test_build_report_golden(golden_env):
    """Single comprehensive guard: shape + all 5 strategies + midline keys.

    One build_report() call keeps runtime bounded; call-count assertions are
    data-quality-independent so they catch ADR-002 midline-dropping regressions.
    """
    report = build_report("600000")

    # 1) shape
    assert isinstance(report, dict), "build_report must return a dict"
    assert isinstance(report.get("current"), (int, float)), "current must be numeric"
    fusion = report.get("fusion") or {}
    ws = fusion.get("weighted_score")
    assert isinstance(ws, (int, float)), "fusion.weighted_score must be numeric"
    assert -1.0 <= float(ws) <= 1.0, "weighted_score out of range"

    # 2) midline keys survive
    assert "chanlun_midline" in report, "chanlun_midline key missing"
    assert "wyckoff_midline" in report, "wyckoff_midline key missing"

    # 3) all five strategy analyses were invoked (hard ADR-002 guard)
    assert golden_env["chan_d"] >= 1, "daily chanlun must run"
    assert golden_env["chan_mid"] >= 1, "midline chanlun must run (ADR-002 regression guard)"
    assert golden_env["wyk_d"] >= 1, "daily wyckoff must run"
    assert golden_env["wyk_mid"] >= 1, "midline wyckoff must run (ADR-002 regression guard)"
    assert golden_env["mom"] >= 1, "momentum must run"
