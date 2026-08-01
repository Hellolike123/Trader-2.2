# -*- coding: utf-8 -*-
"""回踩试探岗位共振 — 阶段 1 离线单测。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.resonance import (  # noqa: E402
    _chan_buy_like,
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


def test_chan_buy_like_rejects_soft_sell_substring():
    """正式买点才进结构探针；类一/类二观察档与卖点一律非买点（BUSINESS §2.1）。"""
    assert _chan_buy_like("类二卖") is False
    assert _chan_buy_like("类二卖", direction=-1) is False
    assert _chan_buy_like("一卖") is False
    assert _chan_buy_like("二卖") is False
    assert _chan_buy_like("类二买") is False
    assert _chan_buy_like("类一买") is False
    assert _chan_buy_like("二买") is True
    assert _chan_buy_like("一类买") is True
    assert _chan_buy_like("二买", direction=-1) is False


def test_a5_like_buys_do_not_green_structure_post():
    """A5：类二买不得把回踩共振结构岗点绿。"""
    r = _base_report()
    r["analysis_cards"]["chan"] = {
        "type_short": "类二买",
        "type_raw": "类二买",
        "direction": 1,
        "summary_line": "类二买 · 回踩偏弱",
    }
    r["current"] = 12.0
    r["key_prices"] = {"buy_zone_low": 9.5, "buy_zone_high": 10.2}
    res = build_resonance(r)
    assert res["posts"]["structure"]["ok"] is False
    assert res["grade"] == "missing_structure"


def test_soft_sell_does_not_green_structure_post():
    """三花类：类二卖看跌 → 结构岗不得因买点子串 / 价在买区变绿 → 缺结构。"""
    r = _base_report()
    r["analysis_cards"]["chan"] = {
        "type_short": "类二卖",
        "type_raw": "类二卖",
        "direction": -1,
        "summary_line": "类二卖 · 反抽偏弱 · 看跌",
    }
    # 即使现价落在买点区，卖点也不得把结构岗点绿
    r["current"] = 10.0
    r["key_prices"] = {"buy_zone_low": 9.5, "buy_zone_high": 10.2}
    res = build_resonance(r)
    assert res["posts"]["structure"]["ok"] is False
    assert "类二卖" in res["posts"]["structure"]["note"] or "偏空" in res["posts"]["structure"]["note"]
    assert res["grade"] == "missing_structure"
    assert "四岗齐了" not in res["summary_line"]
    assert "共振齐" not in res["summary_line"]


def test_background_prefers_midline_stage_over_major_xushi():
    """报告阶段=转弱时，不得因 major_stage=蓄势把背景岗洗白。"""
    r = _base_report(major_stage="蓄势", midline_stage="转弱", midline_bias="bear")
    res = build_resonance(r)
    assert res["posts"]["background"]["ok"] is False
    assert "转弱" in res["posts"]["background"]["note"]
    assert res["conflict"] is True or res["grade"] == "conflict"


def test_background_midline_verdict_stage_when_no_midline_stage():
    """无 midline_stage 时可读 midline_verdict.stage。"""
    r = _base_report(
        major_stage="蓄势",
        midline_verdict={"stage": "派发·警惕", "bias": "bear"},
        midline_bias="bear",
    )
    res = build_resonance(r)
    assert res["posts"]["background"]["ok"] is False
    assert "派发" in res["posts"]["background"]["note"] or "不宜" in res["posts"]["background"]["note"]
