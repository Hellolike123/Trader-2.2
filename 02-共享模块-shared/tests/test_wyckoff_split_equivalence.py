"""P1 equivalence gate: wyckoff_core split (events+phase+facade) is behavior-preserving.

The ORIGINAL wyckoff_core.py (events/phase/API in one file) and the SPLIT
version (wyckoff_events.py + wyckoff_phase.py + wyckoff_core.py facade) must
produce IDENTICAL wyckoff_analysis / calculate_wyckoff_score output for the
same deterministic input. Ground truth: tests/fixtures/wyckoff_split_baseline.json
(captured from the original via scripts/_capture_wyckoff_split_baseline.py).

Mirrors the ADR-003b render-equivalence gate; reuses mock_seam for the offline
deterministic seam.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_FIXTURE = _SHARED / "tests" / "fixtures" / "wyckoff_split_baseline.json"

if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import (
    apply_seam, gen_bars, dumps_fields, loads_fields, approx_equal,
)

SYMBOL = "SPLITTEST"
BARS = gen_bars(120, 9.0, 0.05)  # must match _capture_wyckoff_split_baseline.py


def test_wyckoff_split_equivalence(monkeypatch):
    """Split wyckoff output must match the pre-split baseline (behavior preserved)."""
    if not _FIXTURE.exists():
        pytest.skip(f"fixture missing: {_FIXTURE}")

    apply_seam(monkeypatch)

    import trader_shared.wyckoff_core as wc
    # kill phase disk persistence for offline determinism (same as baseline capture)
    monkeypatch.setattr(wc, "_save_phase_state", lambda *a, **k: None)
    monkeypatch.setattr(wc, "_load_phase_state", lambda *a, **k: None)

    actual = {
        "wyckoff_analysis": wc.wyckoff_analysis(BARS, symbol=SYMBOL),
        "calculate_wyckoff_score": wc.calculate_wyckoff_score(BARS, symbol=SYMBOL),
    }

    expected = loads_fields(_FIXTURE.read_text(encoding="utf-8"))
    assert approx_equal(actual, expected), (
        "wyckoff_core split changed behavior.\n"
        f"expected {len(dumps_fields(expected))} bytes, got {len(dumps_fields(actual))} bytes.\n"
        "Re-run scripts/_capture_wyckoff_split_baseline.py ONLY after confirming the "
        "change is intended."
    )
