"""ADR-002 equivalence gate — routing build_report through PluginRegistry.analyze_all
must NOT change behavior.

Why this test exists:
  Golden (test_build_report_golden.py) only asserts *range* of weighted_score
  (-1..1) and that the 5 strategies are invoked. That is enough to catch the
  midline-drop regression (trap #1) but NOT the daily-chan silent drift when
  weekly_bars is dropped from the chan call (trap #2) — a drifted chan still
  lands inside [-1, 1].

  This test diffs EXACT fields from the pre-change code (captured in
  tests/fixtures/report_baseline.json by scripts/_capture_adr002_baseline.py)
  against the current build_report output:
    - fusion.weighted_score / confidence / action / disagreement
    - report["chanlun_midline"] / report["wyckoff_midline"] (full recursive)

  Only if these match within float epsilon is ADR-002 considered safe.

Run:
  pytest tests/test_build_report_adr002_equivalence.py -q

  # if strategy internals legitimately change, regenerate the baseline:
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
    python scripts/_capture_adr002_baseline.py
"""
from __future__ import annotations

import faulthandler
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Never let a refactor hang the suite: dump + exit if one call exceeds 90s.
faulthandler.dump_traceback_later(90, exit=True)

_SHARED = Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

try:
    from trader_shared.report_builder import build_report  # post-ADR-003
except ImportError:
    _PKG_SCRIPTS = _SHARED.parent / "01-功能包-packages" / "trader" / "scripts"
    if str(_PKG_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_PKG_SCRIPTS))
    from run_analysis import build_report  # pre-ADR-003

_FIXTURE = _SHARED / "tests" / "fixtures" / "report_baseline.json"


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
            daily_bars=daily,
            bars_5m=bars_5m,
            weekly_bars=weekly,
            monthly_bars=monthly,
            data_status="full",
        )


@pytest.fixture
def adr002_env(monkeypatch):
    """Patch provider + network branches (mirror golden_env, no call-count wrap)."""
    from trader_shared.data_provider import set_provider
    from trader_shared import fetchers as _fetchers

    set_provider(_MockProvider())
    monkeypatch.setattr(_fetchers, "TencentFetcher", _fetchers.MockFetcher)
    try:
        import run_analysis as _ra
        if hasattr(_ra, "TencentFetcher"):
            monkeypatch.setattr(_ra, "TencentFetcher", _fetchers.MockFetcher)
    except Exception:
        pass

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


def _approx_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """Recursive approximate equality tolerant of float/numpy type differences."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_approx_equal(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_approx_equal(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    # numpy scalars
    try:
        import numpy as _np
        if isinstance(a, _np.floating) and isinstance(b, (int, float, _np.floating)):
            return abs(float(a) - float(b)) <= tol
        if isinstance(b, _np.floating) and isinstance(a, (int, float, _np.floating)):
            return abs(float(a) - float(b)) <= tol
    except Exception:
        pass
    return a == b


def test_build_report_adr002_equivalence(adr002_env):
    """ADR-002 routing must be behavior-preserving (exact field diff vs baseline)."""
    assert _FIXTURE.exists(), (
        "baseline fixture missing — run scripts/_capture_adr002_baseline.py first"
    )
    baseline = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    report = build_report("600000")
    fusion = report.get("fusion") or {}

    # 1) fusion layer exact values (consumes daily-chan weekly_bars context → trap #2 gate)
    assert _approx_equal(fusion.get("weighted_score"), baseline["fusion_weighted_score"]), (
        f"weighted_score drifted after ADR-002 routing: "
        f"{fusion.get('weighted_score')} != {baseline['fusion_weighted_score']}"
    )
    assert _approx_equal(fusion.get("confidence"), baseline["fusion_confidence"]), (
        f"confidence drifted: {fusion.get('confidence')} != {baseline['fusion_confidence']}"
    )
    assert fusion.get("action") == baseline["fusion_action"], (
        f"action drifted: {fusion.get('action')} != {baseline['fusion_action']}"
    )
    assert _approx_equal(fusion.get("disagreement"), baseline["fusion_disagreement"]), (
        f"disagreement drifted: {fusion.get('disagreement')} != {baseline['fusion_disagreement']}"
    )

    # 2) midline exact values (trap #1 gate: midline must not be dropped/altered)
    assert _approx_equal(report.get("chanlun_midline"), baseline["chanlun_midline"]), (
        "chanlun_midline drifted after ADR-002 routing"
    )
    assert _approx_equal(report.get("wyckoff_midline"), baseline["wyckoff_midline"]), (
        "wyckoff_midline drifted after ADR-002 routing"
    )
