# -*- coding: utf-8 -*-
"""阶段 3：decision_view 薄决策 — 共振∧策略∧纪律。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.decision_view import (  # noqa: E402
    apply_decision_view,
    apply_execution_caps,
    build_decision_view,
)


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
    assert not any("missing_structure" in x for x in v["block_reasons"])
    assert any(("缺结构" in x or "缠论" in x or "未点亮" in x) for x in v["block_reasons"])


def test_block_when_no_entry_strategy():
    r = _report(entry_id=None)
    v = build_decision_view(r)
    assert v["allow_new_recommend"] is False
    assert any("策略" in x for x in v["block_reasons"])


def test_block_when_entry_plan_not_executable():
    """plan-mode / executable=False 不算策略亮，不得推荐新开。"""
    r = _report()
    r["strategy_match"]["gates"]["entry"] = {
        "primary": {"id": "entry.chan_buy1_probe", "name": "结构试探·一买"},
        "mode": "plan",
        "executable": False,
        "reason": "清单未全绿",
    }
    v = build_decision_view(r)
    assert v["strategy_entry_lit"] is False
    assert v["allow_new_recommend"] is False
    assert any("计划" in x or "可执行" in x for x in v["block_reasons"])


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


def test_apply_zeros_stale_caps_when_tightening():
    """DV deny 后由 apply_execution_caps 单一出口清零 caps/suggested_pct。"""
    r = _report(grade="empty", execution="回踩轻仓试探")
    r["discipline"]["suggested_pct_cap"] = 30
    r["discipline"]["position_cap_pct"] = 30
    r["discipline"]["suggested_pct_cap_short"] = 15
    r["suggested_pct"] = 30
    r["position_info"] = {"suggested_pct": 30}
    v = apply_decision_view(r, tighten_discipline=True)
    assert v["applied_tighten"] is True
    assert r["discipline"]["allow_new_entry"] is False
    apply_execution_caps(r, has_position=False)
    assert r["discipline"]["suggested_pct_cap"] == 0
    assert r["discipline"]["position_cap_pct"] == 0
    assert r["discipline"]["suggested_pct_cap_short"] == 0
    assert r["suggested_pct"] == 0
    assert r["position_info"]["suggested_pct"] == 0


def test_apply_execution_caps_only_on_dv_deny():
    """caps/suggested_pct 只经 apply_execution_caps 收口，非 attach 手术。"""
    r = _report(grade="empty", execution="回踩轻仓试探")
    r["discipline"]["suggested_pct_cap"] = 20
    r["suggested_pct"] = 20
    r["position_info"] = {"suggested_pct": 20}
    apply_decision_view(r, tighten_discipline=True)
    # DV 已收紧 allow，但尚未跑 caps
    assert r["discipline"]["allow_new_entry"] is False
    assert r["discipline"]["suggested_pct_cap"] == 20
    apply_execution_caps(r, has_position=False)
    assert r["suggested_pct"] == 0
    assert r["discipline"]["suggested_pct_cap"] == 0
    assert "不推荐新开" in str(r.get("suggested_pct_context") or "") or "不新开" in str(
        r.get("suggested_pct_context") or ""
    )


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
    assert r.get("decision") is v


def test_tag_fusion_instrument():
    from trader_shared.report_pipeline import tag_fusion_as_instrument

    f = tag_fusion_as_instrument({"weighted_score": 0.1, "action": "观望"})
    assert f.get("product_role") == "instrument"
    assert "decision_view" in str(f.get("product_role_note") or "")


def test_format_narrative_includes_resonance_decision_gauge():
    from trader_shared.decision_view import format_decision_narrative_lines

    r = _report(grade="missing_structure")
    apply_decision_view(r)
    r["fusion"] = {"weighted_score": 0.22, "action": "半仓试"}
    r["resonance"]["summary_line"] = "共振：缺结构"
    # 默认：不推荐时无决策行、无仪表
    lines = format_decision_narrative_lines(r)
    text = "\n".join(lines)
    assert "共振" in text
    assert "决策" not in text
    assert "新开" in text
    assert "仪表" not in text

    # 可试探时出决策；仪表需显式开关
    r2 = _report()
    apply_decision_view(r2)
    r2["fusion"] = {"weighted_score": 0.22, "action": "半仓试"}
    lines2 = format_decision_narrative_lines(r2)
    text2 = "\n".join(lines2)
    assert "决策" in text2 and "可试探" in text2

    import os

    os.environ["TRADER_SHOW_FUSION_GAUGE"] = "1"
    try:
        lines3 = format_decision_narrative_lines(r)
        text3 = "\n".join(lines3)
        assert "仪表" in text3 and "仅参考" in text3
        assert "0.22" in text3 or "+0.22" in text3
    finally:
        os.environ.pop("TRADER_SHOW_FUSION_GAUGE", None)


def test_apply_decision_to_execution_presses_soft_buy():
    from trader_shared.decision_view import apply_decision_to_execution

    r = _report(grade="empty")
    apply_decision_view(r)
    out = apply_decision_to_execution("回踩轻仓试探", r)
    assert "不买" in out or "不追" in out


def test_render_short_midline_shows_decision_narrative():
    from trader_shared.report_core import render_short_midline

    r = {
        "name": "测",
        "symbol": "000001",
        "current": 10.0,
        "change_pct": 0.0,
        "major_stage": "蓄势",
        "short_term_momentum": "震荡",
        "conclusion": {
            "midline": "观察",
            "shortline": "观察",
            "execution": "回踩轻仓试探",
            "reason": "单测",
            "stage_line": "蓄势",
        },
        "discipline": {
            "allow_new_entry": False,
            "suggested_pct_cap": 0,
            "entry_line": "新开：否（缺：共振不足）",
            "entry_checklist": {"all_green": False, "missing_labels": ["共振不足"]},
        },
        "resonance": {
            "grade": "empty",
            "summary_line": "共振：空窗/不足",
            "posts": {},
            "missing": [],
            "conflict": False,
            "scene": "pullback_probe",
        },
        "decision_view": {
            "allow_new_recommend": False,
            "summary_line": "决策：不推荐新开（共振不足｜无入场策略）",
            "block_reasons": ["共振不足", "无入场策略"],
        },
        "fusion": {
            "weighted_score": 0.18,
            "action": "半仓试",
            "regime": "正常",
            "confidence": 0.4,
            "signals_detail": {},
        },
        "key_prices": {},
        "mid_key_prices": {},
    }
    md = render_short_midline(r)
    assert "共振" in md
    assert "新开" in md
    # 不推荐场景：决策/仪表默认不上屏
    assert "决策：不推荐" not in md
    assert "仪表：" not in md
    assert "动作：" in md
