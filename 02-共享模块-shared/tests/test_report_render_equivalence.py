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

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_FIXTURE = _SHARED / "tests" / "fixtures" / "report_render_baseline.txt"

from trader_shared.testing.mock_seam import render_under_seam


def test_report_render_equivalence(monkeypatch):
    """render_markdown output must be byte-identical to the pre-split baseline."""
    if not _FIXTURE.exists():
        pytest.skip(f"fixture missing: {_FIXTURE}")

    expected = _FIXTURE.read_text(encoding="utf-8")
    actual = render_under_seam(monkeypatch)

    assert actual == expected, (
        "render_markdown output changed after domain/presentation split.\n"
        f"expected {len(expected)} chars, got {len(actual)} chars.\n"
        "Run scripts/golden_diff_gate.py capture to refresh, ONLY after confirming "
        "the change is intended."
    )
