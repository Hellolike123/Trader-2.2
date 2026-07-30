# -*- coding: utf-8 -*-
"""回踩试探岗位共振 — 阶段 1 离线单测。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.resonance import (  # noqa: E402
    attach_resonance,
    build_resonance,
)


def _base_report(**kwargs):
    r = {
        "current": 10.0,
        "major_stage": "蓄势",
        "analysis_cards": {
            "chan": {
                "type_short": "二买",
                "direction": 1,
                "summary_line": "二买",
            },
            "wyckoff_midline": {
                "direction": 0,
                "bias": "neutral",
                "summary_line": "威科夫中性",
            },
            "chip": {
                "raw_available": True,
                "summary_line": "有峰",
            },
            "momentum": {
                "direction": 0,
                "confidence": 0.4,
                "summary_line": "中性",
            },
        },
        "chip_peaks": [{"price": 9.5, "strength": 0.3}],
        "key_prices": {"buy_zone_low": 9.5, "buy_zone_high": 10.2},
    }
    r.update(kwargs)
    return r


def test_aligned_when_abc_ok_momentum_neutral():
    res = build_resonance(_base_report())
    assert res["schema_version"] == "resonance_v1"
    assert res["scene"] == "pullback_probe"
    assert res["grade"] == "aligned"
    assert res["posts"]["background"]["ok"] is True
    assert res["posts"]["structure"]["ok"] is True
    assert res["posts"]["chip"]["ok"] is True
    assert res["posts"]["momentum"]["ok"] is True
    assert res["missing"] == []
    assert "四岗齐了" in res["summary_line"] or "共振齐" in res["summary_line"]


def test_missing_structure_when_no_buy_and_far_from_zone():
    r = _base_report()
    r["analysis_cards"]["chan"] = {"type_short": "", "direction": 0}
    r["key_prices"] = {"buy_zone_low": 7.0, "buy_zone_high": 7.5}
    r["current"] = 12.0
    res = build_resonance(r)
    assert res["grade"] == "missing_structure"
    assert res["posts"]["structure"]["ok"] is False
    assert "structure" in res["missing"]  # 内部键仍英文
    assert "还差" in res["summary_line"] or "缠论" in res["summary_line"]
    assert "structure" not in res["summary_line"]  # 可见面中文
    assert "momentum" not in res["summary_line"]


def test_conflict_when_structure_ok_but_stage_distribution():
    r = _base_report(major_stage="派发")
    res = build_resonance(r)
    assert res["grade"] == "conflict"
    assert res["conflict"] is True
    assert res["posts"]["background"]["ok"] is False
    assert res["posts"]["structure"]["ok"] is True


def test_momentum_veto_when_strong_bear():
    r = _base_report()
    r["analysis_cards"]["momentum"] = {
        "direction": -1,
        "confidence": 0.8,
        "score": -0.5,
    }
    res = build_resonance(r)
    assert res["grade"] == "momentum_veto"
    assert res["posts"]["momentum"]["ok"] is False


def test_missing_chip_when_migration_clear():
    r = _base_report()
    r["chip_migration"] = {"clear_signal": True, "summary": "底峰搬走"}
    res = build_resonance(r)
    assert res["grade"] == "missing_chip"
    assert res["posts"]["chip"]["ok"] is False


def test_attach_writes_report_key():
    r = _base_report()
    out = attach_resonance(r)
    assert r["resonance"] is out
    assert r["resonance"]["grade"] == "aligned"


def test_empty_report_safe():
    res = build_resonance(None)
    assert res["grade"] == "empty"
    assert "background" in res["posts"]
