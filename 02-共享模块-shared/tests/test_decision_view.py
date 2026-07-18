# -*- coding: utf-8 -*-
"""阶段 3：decision_view 薄决策 — 共振∧策略∧纪律。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.decision_view import apply_decision_view, build_decision_view  # noqa: E402


def _report(
    *,
    discipline_allow: bool = True,
    grade: str = "aligned",
    entry_id: str | None = "entry.chan_buy1_probe",
    execution: str = "回踩轻仓试探",
):
    sm = {"schema_version": "strategy_match_v1", "gates": {}}
    if entry_id:
        sm["gates"]["entry"] = {
            "primary": {"id": entry_id, "name": "结构试探·一买"},
            "mode": "active",
            "executable": True,
        }
    else:
        sm["gates"]["entry"] = {"primary": None, "mode": "off", "executable": False}
    return {
        "discipline": {
            "allow_new_entry": discipline_allow,
            "entry_checklist": {
                "all_green": discipline_allow,
                "missing_labels": [],
                "entry_line": "新开：可试探（清单全绿）" if discipline_allow else "新开：否",
            },
            "entry_line": "新开：可试探（清单全绿）" if discipline_allow else "新开：否",
        },
        "resonance": {
            "grade": grade,
            "scene": "pullback_probe",
            "conflict": grade == "conflict",
            "posts": {},
        },
        "strategy_match": sm,
        "conclusion": {"execution": execution, "reason": "测试"},
    }


def test_allow_when_all_three_green():
    r = _report()
    v = build_decision_view(r)
    assert v["allow_new_recommend"] is True
    assert v["resonance_ok"] is True
    assert v["strategy_entry_lit"] is True
    assert v["discipline_allow"] is True
    assert "可试探" in v["summary_line"]


def test_block_when_resonance_not_aligned():
    r = _report(grade="missing_structure")
    v = build_decision_view(r)
    assert v["allow_new_recommend"] is False
    assert any("共振" in x for x in v["block_reasons"])


def test_block_when_no_entry_strategy():
    r = _report(entry_id=None)
    v = build_decision_view(r)
    assert v["allow_new_recommend"] is False
    assert any("策略" in x for x in v["block_reasons"])


def test_block_when_discipline_forbids():
    r = _report(discipline_allow=False)
    v = build_decision_view(r)
    assert v["allow_new_recommend"] is False
    assert any("纪律" in x for x in v["block_reasons"])


def test_apply_tightens_discipline_only():
    r = _report(grade="empty", execution="回踩轻仓试探")
    assert r["discipline"]["allow_new_entry"] is True
    v = apply_decision_view(r, tighten_discipline=True)
    assert v["allow_new_recommend"] is False
    assert r["discipline"]["allow_new_entry"] is False
    assert r["decision_view"] is v
    assert v["applied_tighten"] is True
    assert "不买" in r["conclusion"]["execution"] or "不追" in r["conclusion"]["execution"]


def test_apply_does_not_loosen():
    r = _report(discipline_allow=False, grade="aligned")
    apply_decision_view(r, tighten_discipline=True)
    assert r["discipline"]["allow_new_entry"] is False


def test_no_tighten_when_recommend_true():
    r = _report()
    v = apply_decision_view(r, tighten_discipline=True)
    assert v["allow_new_recommend"] is True
    assert r["discipline"]["allow_new_entry"] is True
    assert v["applied_tighten"] is False
