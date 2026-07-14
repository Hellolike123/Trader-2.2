"""Golden/regression test for build_report.

Purpose: guard build_report's *behavior* across refactors (ADR-002 plugin
routing, ADR-003 module extraction). It must keep invoking ALL five strategy
functions (chan/wyck daily + midline, momentum) and return a well-shaped
report dict.

Design:
- A single shared offline seam (trader_shared.testing.mock_seam) supplies a
  deterministic MarketSnapshot and patches every network branch, so the run is
  fully offline & deterministic (no copy-pasted mocks across tests).
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

from trader_shared.testing.mock_seam import apply_seam


@pytest.fixture
def golden_env(monkeypatch):
    """Patch provider + network branches via shared seam, then count strategy calls."""
    import trader_shared.chan_core as _chan
    import trader_shared.momentum_core as _mom
    import trader_shared.wyckoff_core as _wyk

    apply_seam(monkeypatch)

    # ── wrap the five strategy functions to count calls ──
    calls: dict[str, int] = {}
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
    """Single comprehensive guard: shape + all 5 strategies + midline keys."""
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
