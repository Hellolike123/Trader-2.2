"""Single source of truth for the OFFLINE, DETERMINISTIC mock seam.

Every golden / equivalence gate in this repo (build_report behavior, ADR-002
routing, ADR-003b presentation split, and the new golden-diff gate) previously
copied this seam ~4 times, each with a slightly different patch style — the
standalone capture scripts even used *bare attribute assignment* on
``_fetchers.TencentFetcher`` (a known footgun: it leaks MockFetcher into later
tests). This module consolidates the seam into one faithful implementation.

Key guarantees
--------------
- All network leak points are patched through a *patcher* object that exposes a
  ``setattr`` method. Under pytest we pass the real ``monkeypatch`` fixture;
  standalone (the CLI) we pass a :class:`_Patcher` that restores on ``undo``.
  No global leakage either way.
- Data is synthetic & deterministic, so assertions (call-count / shape / exact
  field diff / byte-identical render) catch *behavioral* regressions regardless
  of live market data.
- ``apply_seam`` reproduces exactly the patch set of the legacy fixtures, so
  existing baselines stay valid.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_SHARED = Path(__file__).resolve().parent.parent.parent  # 02-共享模块-shared
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))


# ── synthetic market data (kept small to bound compute time) ──────────────

def gen_bars(n: int, start: float, step: float) -> list[dict[str, Any]]:
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


class MockProvider:
    """Implements the DataProvider protocol with canned, deterministic data."""

    name = "mock"

    def resolve_security(self, target: str):
        from trader_shared.data_provider import Security
        code = str(target)
        return Security(code=code, market="SH" if code.startswith("6") else "SZ", name="测试股")

    def fetch_quote(self, sec):
        return {
            "name": "测试股", "symbol": sec.qq_symbol, "current_price": 10.5,
            "pre_close": 10.3, "volume": 5_000_000, "current_change_pct": 1.94,
            "trade_date": "2026-07-10", "trade_time": "15:00", "turnover_rate": 2.1,
        }

    def fetch_qfq_daily(self, sec, days: int = 365):
        return gen_bars(80, 9.0, 0.05)

    def fetch_kline(self, sec, **kw):
        return []

    def load_market_snapshot(self, target, days=365, include_5m=True,
                             include_weekly=True, include_monthly=True, include_ticks=True):
        from trader_shared.data_provider import MarketSnapshot
        daily = gen_bars(80, 9.0, 0.05)
        weekly = gen_bars(40, 9.0, 0.12)
        monthly = gen_bars(16, 9.0, 0.4)
        bars_5m = gen_bars(10, 10.4, 0.02)
        return MarketSnapshot(
            security=self.resolve_security(target),
            quote=self.fetch_quote(self.resolve_security(target)),
            daily_bars=daily,
            bars_5m=bars_5m,
            weekly_bars=weekly,
            monthly_bars=monthly,
            data_status="full",
        )


class UnavailableClient:
    """Tushare client stub that reports unavailable (no real HTTP calls)."""

    available = False


class _MISSING:
    pass


class _Patcher:
    """Minimal ``monkeypatch``-compatible patcher for standalone (CLI) use.

    Records originals and restores them on :meth:`undo`. Satisfies the
    ``setattr(obj, name, value)`` contract that :func:`apply_seam` relies on,
    so the same seam code path runs under pytest and under the CLI.
    """

    def __init__(self) -> None:
        self._originals: list[tuple[Any, str, Any]] = []

    def setattr(self, obj, name, value):
        original = getattr(obj, name, _MISSING)
        self._originals.append((obj, name, original))
        setattr(obj, name, value)

    def undo(self) -> None:
        for obj, name, original in reversed(self._originals):
            if original is _MISSING:
                try:
                    delattr(obj, name)
                except AttributeError:
                    pass
            else:
                setattr(obj, name, original)


def apply_seam(patcher) -> None:
    """Patch provider + ALL network leak points via ``patcher`` (restored after).

    ``patcher`` must expose ``setattr(obj, name, value)`` — i.e. the pytest
    ``monkeypatch`` fixture, or :class:`_Patcher` for standalone use.
    """
    from trader_shared.data_provider import set_provider
    from trader_shared import fetchers as _fetchers

    # Provider is set as a module global (matches legacy fixtures). Deterministic
    # for every test, so cross-test leakage is benign.
    set_provider(MockProvider())
    patcher.setattr(_fetchers, "TencentFetcher", _fetchers.MockFetcher)
    try:
        import run_analysis as _ra
        if hasattr(_ra, "TencentFetcher"):
            patcher.setattr(_ra, "TencentFetcher", _fetchers.MockFetcher)
    except Exception:
        pass

    import trader_shared.market_env as _me
    import trader_shared.cache_utils as _cu
    import trader_shared.tushare_client as _tc
    import trader_shared.chip_data as _chip
    patcher.setattr(
        _me, "get_env_for_skill",
        lambda *a, **k: {"level": "正常", "hmm_regime_en": "range"},
    )
    patcher.setattr(_cu, "fetch_fund_flow_cached", lambda *a, **k: None)
    patcher.setattr(_tc, "get_client", lambda *a, **k: UnavailableClient())
    patcher.setattr(_chip, "get_cyq_perf", lambda *a, **k: None)
    try:
        import run_analysis as _ra2
        if hasattr(_ra2, "read_signals_for_report"):
            patcher.setattr(_ra2, "read_signals_for_report", lambda *a, **k: (0.0, 0.0))
    except Exception:
        pass


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def mask_dates(text: str) -> str:
    """Replace ISO dates with ``DATE`` so the gate is date-stable."""
    return _DATE_RE.sub("DATE", text)


def build_under_seam(patcher, target: str = "600000") -> dict:
    """Run ``build_report`` fully offline & deterministic; return the raw dict."""
    apply_seam(patcher)
    from trader_shared.report_builder import build_report
    return build_report(target)


def render_under_seam(patcher, target: str = "600000") -> str:
    """Run build_report + render_markdown under the seam; return date-masked md."""
    report = build_under_seam(patcher, target)
    from trader_shared.report_builder import render_markdown
    return mask_dates(render_markdown(report))


def extract_fields(report: dict, paths: list[str]) -> dict:
    """Extract a flat {dotted.path: value} subset for exact-field diffing."""
    out: dict[str, Any] = {}
    for p in paths:
        cur: Any = report
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        out[p] = cur
    return out


def _json_default(o):
    if isinstance(o, bool):
        return o
    if isinstance(o, (int,)) and not isinstance(o, bool):
        return int(o)
    if isinstance(o, float):
        return float(o)
    try:
        import numpy as _np
        if isinstance(o, _np.floating):
            return float(o)
        if isinstance(o, _np.integer):
            return int(o)
        if isinstance(o, _np.ndarray):
            return o.tolist()
    except Exception:
        pass
    if isinstance(o, set):
        return sorted(o)
    if o is None:
        return None
    return str(o)


def dumps_fields(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default)


def loads_fields(text: str) -> Any:
    import json
    return json.loads(text)


def approx_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """Recursive approximate equality tolerant of float/numpy type differences."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(approx_equal(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(approx_equal(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    try:
        import numpy as _np
        if isinstance(a, _np.floating) or isinstance(b, _np.floating):
            return abs(float(a) - float(b)) <= tol
    except Exception:
        pass
    return a == b
