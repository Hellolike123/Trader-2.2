"""Pre-push golden-diff gate.

Runs scripts/golden_diff_gate.py `check` against the committed golden baselines
in tests/golden/. If any ticker's build_report output drifts from its golden,
the gate fails (exit 1). This is the consolidated, CLI-driven successor to the
three ad-hoc equivalence tests (build_report golden / ADR-002 routing /
ADR-003b render split).

Run standalone:  python scripts/golden_diff_gate.py check
Run here:        pytest tests/test_golden_diff_gate.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent  # Trader3.0 repo root
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import golden_diff_gate  # noqa: E402


def test_golden_diff_gate_passes():
    rc = golden_diff_gate.main(["check"])
    assert rc == 0, "golden-diff gate detected behavioral drift from baseline"
