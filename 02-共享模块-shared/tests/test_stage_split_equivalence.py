"""P1 equivalence gate: stage_positioning split (4 submodules) is behavior-preserving.
Ground truth: tests/fixtures/stage_split_baseline.json.
The DETECT/POSITION partitions are also verified by the full CI gate
(build_report_golden → assess_stage → detect/stops/position all pass).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_FIXTURE = _SHARED / "tests" / "fixtures" / "stage_split_baseline.json"

if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import (
    apply_seam, dumps_fields, loads_fields, approx_equal,
)


def test_stage_split_equivalence(monkeypatch):
    """Split stage output must match the pre-split baseline (behavior preserved)."""
    if not _FIXTURE.exists():
        pytest.skip(f"fixture missing: {_FIXTURE}")

    apply_seam(monkeypatch)
    import trader_shared.stage_positioning as sp
    monkeypatch.setattr(sp, "_save_stage_state", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_load_stage_state", lambda *a, **k: None)

    actual = {
        "check_time_stop": sp.check_time_stop(
            "2026-07-01", "蓄势", 20, False,
        ),
    }

    expected = loads_fields(_FIXTURE.read_text(encoding="utf-8"))
    assert approx_equal(actual, expected), (
        "stage_positioning split changed behavior.\n"
        f"expected {len(dumps_fields(expected))} bytes, got {len(dumps_fields(actual))} bytes.\n"
        "Re-run scripts/_capture_stage_split_baseline.py ONLY after confirming the change "
        "is intended."
    )
