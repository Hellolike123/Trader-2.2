"""P1 equivalence gate: chan_core split (geometry+structure+facade) is behavior-preserving.

ORIGINAL chan_core.py (geometry/structure/engine in one file) and the SPLIT
version (chan_geometry.py + chan_structure.py + chan_core.py facade) must produce
IDENTICAL chanlun_analysis / ChanlunEngine.get_analysis output for the same
deterministic input. Ground truth: tests/fixtures/chan_split_baseline.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_FIXTURE = _SHARED / "tests" / "fixtures" / "chan_split_baseline.json"

if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import (
    apply_seam, gen_bars, dumps_fields, loads_fields, approx_equal,
)

SYMBOL = "SPLITTEST"
BARS = gen_bars(120, 9.0, 0.05)


def test_chan_split_equivalence(monkeypatch):
    """Split chan output must match the pre-split baseline (behavior preserved)."""
    if not _FIXTURE.exists():
        pytest.skip(f"fixture missing: {_FIXTURE}")

    apply_seam(monkeypatch)
    import trader_shared.chan_core as cc

    current = BARS[-1]["close"]
    actual = {
        "chanlun_analysis": cc.chanlun_analysis(BARS, current=current, symbol=SYMBOL),
        "chanlun_engine": cc.ChanlunEngine(BARS).get_analysis(current=current, symbol=SYMBOL),
    }

    expected = loads_fields(_FIXTURE.read_text(encoding="utf-8"))
    assert approx_equal(actual, expected), (
        "chan_core split changed behavior.\n"
        f"expected {len(dumps_fields(expected))} bytes, got {len(dumps_fields(actual))} bytes.\n"
        "Re-run scripts/_capture_chan_split_baseline.py ONLY after confirming the change is intended."
    )
