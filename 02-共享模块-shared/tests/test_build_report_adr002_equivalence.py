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

from trader_shared.testing.mock_seam import apply_seam, build_under_seam, approx_equal


def test_build_report_adr002_equivalence(monkeypatch):
    """ADR-002 routing must be behavior-preserving (exact field diff vs baseline)."""
    assert _FIXTURE.exists(), (
        "baseline fixture missing — run scripts/_capture_adr002_baseline.py first"
    )
    baseline = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    apply_seam(monkeypatch)
    report = build_under_seam(monkeypatch, "600000")
    fusion = report.get("fusion") or {}

    # 1) fusion layer exact values (consumes daily-chan weekly_bars context → trap #2 gate)
    assert approx_equal(fusion.get("weighted_score"), baseline["fusion_weighted_score"]), (
        f"weighted_score drifted after ADR-002 routing: "
        f"{fusion.get('weighted_score')} != {baseline['fusion_weighted_score']}"
    )
    assert approx_equal(fusion.get("confidence"), baseline["fusion_confidence"]), (
        f"confidence drifted: {fusion.get('confidence')} != {baseline['fusion_confidence']}"
    )
    assert fusion.get("action") == baseline["fusion_action"], (
        f"action drifted: {fusion.get('action')} != {baseline['fusion_action']}"
    )
    assert approx_equal(fusion.get("disagreement"), baseline["fusion_disagreement"]), (
        f"disagreement drifted: {fusion.get('disagreement')} != {baseline['fusion_disagreement']}"
    )

    # 2) midline exact values (trap #1 gate: midline must not be dropped/altered)
    assert approx_equal(report.get("chanlun_midline"), baseline["chanlun_midline"]), (
        "chanlun_midline drifted after ADR-002 routing"
    )
    assert approx_equal(report.get("wyckoff_midline"), baseline["wyckoff_midline"]), (
        "wyckoff_midline drifted after ADR-002 routing"
    )
