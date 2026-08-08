"""_transition_phase 直接单测（report-wyckoff-state-fixes-handoff §1.3）。"""
from __future__ import annotations

from trader_shared.wyckoff_phase import _PHASE_ORDER, _transition_phase


def _old(phase: str) -> dict:
    return {
        "phase": phase,
        "phase_label": phase,
        "phase_confidence_delta": 0.0,
        "first_seen": phase,
    }


def test_distribution_b_in_phase_order():
    assert "distribution_b" in _PHASE_ORDER
    assert _PHASE_ORDER["markdown"] < _PHASE_ORDER["distribution_d"] < _PHASE_ORDER["distribution_c"]
    assert _PHASE_ORDER["distribution_c"] < _PHASE_ORDER["distribution_b"] < _PHASE_ORDER["distribution_a"]
    assert abs(_PHASE_ORDER["distribution_a"]) < abs(_PHASE_ORDER["distribution_b"]) < abs(_PHASE_ORDER["distribution_c"])


def test_distribution_a_to_c_upgrades():
    out = _transition_phase(_old("distribution_a"), "distribution_c", "c", 0.0)
    assert out["phase"] == "distribution_c"


def test_distribution_c_to_d_upgrades():
    out = _transition_phase(_old("distribution_c"), "distribution_d", "d", 0.0)
    assert out["phase"] == "distribution_d"


def test_distribution_c_to_markdown_upgrades():
    out = _transition_phase(_old("distribution_c"), "markdown", "markdown", 0.0)
    assert out["phase"] == "markdown"


def test_distribution_b_to_c_upgrades():
    out = _transition_phase(_old("distribution_b"), "distribution_c", "c", 0.0)
    assert out["phase"] == "distribution_c"


def test_distribution_c_to_a_downgrade_blocked():
    out = _transition_phase(_old("distribution_c"), "distribution_a", "a", 0.0)
    assert out["phase"] == "distribution_c"


def test_distribution_b_to_accumulation_a_flips():
    out = _transition_phase(_old("distribution_b"), "accumulation_a", "a", 0.0)
    assert out["phase"] == "accumulation_a"


def test_accumulation_progression_still_works():
    out = _transition_phase(_old("accumulation_a"), "accumulation_c", "c", 0.0)
    assert out["phase"] == "accumulation_c"
    blocked = _transition_phase(_old("accumulation_c"), "accumulation_a", "a", 0.0)
    assert blocked["phase"] == "accumulation_c"
