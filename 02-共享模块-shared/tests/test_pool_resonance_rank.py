"""选股池共振档：离散排序 / 执行降级（无网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.resonance import (  # noqa: E402
    apply_resonance_admission,
    demote_execution_for_resonance,
    extract_resonance_grade,
    resonance_grade_label,
    resonance_pool_rank,
)


def test_pool_rank_aligned_above_conflict():
    assert resonance_pool_rank("aligned") > resonance_pool_rank("missing_chip")
    assert resonance_pool_rank("missing_chip") > resonance_pool_rank("empty")
    assert resonance_pool_rank("empty") > resonance_pool_rank("momentum_veto")
    assert resonance_pool_rank("momentum_veto") > resonance_pool_rank("conflict")


def test_demote_conflict_and_veto_only():
    assert demote_execution_for_resonance("conflict") is True
    assert demote_execution_for_resonance("momentum_veto") is True
    assert demote_execution_for_resonance("aligned") is False
    assert demote_execution_for_resonance("missing_structure") is False
    assert demote_execution_for_resonance("empty") is False


def test_apply_admission_demotes_execution():
    st, reason = apply_resonance_admission("执行", "结构成立", "conflict")
    assert st == "观察"
    assert "降为观察" in reason
    assert "冲突" in reason or "共振" in reason

    st2, reason2 = apply_resonance_admission("执行", "结构成立", "aligned")
    assert st2 == "执行"
    assert reason2 == "结构成立"


def test_extract_grade_from_item_or_report():
    assert extract_resonance_grade({"resonance_grade": "aligned"}) == "aligned"
    assert extract_resonance_grade({"resonance": {"grade": "conflict"}}) == "conflict"
    assert extract_resonance_grade({}) == "empty"


def test_label_zh():
    assert "齐" in resonance_grade_label("aligned")
    assert "反调" in resonance_grade_label("momentum_veto") or "拆台" in resonance_grade_label("momentum_veto")


def test_score_report_excludes_fusion_from_total():
    """fusion 仪表分可记录，但不计入 total_score（入池门槛）。"""
    scripts = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pool_cmds.scoring import score_report

    base = {
        "current": 10.0,
        "confirm": 10.1,
        "stop": 9.0,
        "support": 9.5,
        "take": 11.0,
        "stage": "走强",
        "scene": "等转强",
        "chan_buy_point_types": [],
        "chan_strokes_count": 3,
        "chan_trend_label": "上行",
        "bars": [],
        "fusion": {"weighted_score": 1.0, "disagreement": 0.0},
    }
    with_fusion = score_report(base)
    without = score_report({**base, "fusion": {"weighted_score": 0.0, "disagreement": 0.0}})
    assert with_fusion["fusion_score"] > 0
    assert without["fusion_score"] == 0
    assert with_fusion["total_score"] == without["total_score"]
    structure = (
        with_fusion["chanlun_score"]
        + with_fusion["wyckoff_score"]
        + with_fusion["chip_score"]
        + with_fusion["momentum_score"]
    )
    assert with_fusion["total_score"] == min(100, structure)


def test_sort_items_unified_prefers_aligned():
    """同 status 下 aligned 排在 conflict 前（经 pool_cmds.scoring）。"""
    scripts = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pool_cmds.scoring import sort_items_unified

    items = [
        {
            "name": "冲突票",
            "status": "观察",
            "resonance_grade": "conflict",
            "total_score": 90,
            "fusion_confidence": 0.9,
            "major_stage": "主升",
        },
        {
            "name": "齐票",
            "status": "观察",
            "resonance_grade": "aligned",
            "total_score": 70,
            "fusion_confidence": 0.5,
            "major_stage": "蓄势",
        },
    ]
    ordered = sort_items_unified(items)
    assert ordered[0]["name"] == "齐票"
    assert ordered[1]["name"] == "冲突票"


def test_sort_tightens_stale_execution_conflict():
    scripts = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pool_cmds.scoring import sort_items_unified

    items = [
        {
            "name": "假执行",
            "status": "执行",
            "resonance_grade": "momentum_veto",
            "total_score": 95,
            "fusion_confidence": 0.9,
            "major_stage": "主升",
        },
        {
            "name": "真观察齐",
            "status": "观察",
            "resonance_grade": "aligned",
            "total_score": 60,
            "fusion_confidence": 0.4,
            "major_stage": "蓄势",
        },
    ]
    ordered = sort_items_unified(items)
    # 假执行被收紧为观察后，齐票因共振档更高排前；或同为观察时齐票优先
    assert ordered[0]["name"] == "真观察齐"
    fake = next(x for x in ordered if x["name"] == "假执行")
    assert fake["status"] == "观察"


def _scripts_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )


def _ensure_scripts_path() -> None:
    p = str(_scripts_path())
    if p not in sys.path:
        sys.path.insert(0, p)


def test_admission_for_ignores_fusion_weighted_score():
    """同结构分时，仅改 fusion.weighted_score → admission_for 结果不变。"""
    _ensure_scripts_path()
    from pool_cmds.scoring import admission_for, score_report

    base = {
        "current": 10.0,
        "confirm": 10.1,
        "stop": 9.0,
        "support": 9.5,
        "take": 11.0,
        "stage": "走强",
        "scene": "等转强",
        "major_stage": "蓄势",
        "chan_buy_point_types": [],
        "chan_strokes_count": 3,
        "chan_trend_label": "上行",
        "bars": [],
        "resonance": {"grade": "aligned"},
    }
    high = {**base, "fusion": {"weighted_score": 1.0, "disagreement": 0.0}}
    low = {**base, "fusion": {"weighted_score": -1.0, "disagreement": 0.0}}
    scores_high = score_report(high)
    scores_low = score_report(low)
    assert scores_high["total_score"] == scores_low["total_score"]
    assert scores_high["fusion_score"] != scores_low["fusion_score"]
    assert admission_for(high, scores_high) == admission_for(low, scores_low)


def test_sort_items_unified_ignores_fusion_confidence():
    """同 status/共振/总分/阶段时，仅改 fusion_confidence → 顺序不变。"""
    _ensure_scripts_path()
    from pool_cmds.scoring import sort_items_unified

    a = {
        "name": "A",
        "status": "观察",
        "resonance_grade": "aligned",
        "total_score": 70,
        "major_stage": "蓄势",
        "fusion_confidence": 0.95,
    }
    b = {
        "name": "B",
        "status": "观察",
        "resonance_grade": "aligned",
        "total_score": 70,
        "major_stage": "蓄势",
        "fusion_confidence": 0.1,
    }
    names = [x["name"] for x in sort_items_unified([a, b])]
    swapped = [
        {**a, "fusion_confidence": 0.1},
        {**b, "fusion_confidence": 0.95},
    ]
    assert [x["name"] for x in sort_items_unified(swapped)] == names == ["A", "B"]
    # 高 confidence 不得单独把后票抬前（并列保输入顺序）
    assert [x["name"] for x in sort_items_unified([b, a])] == ["B", "A"]


def test_pool_briefing_group_sort_ignores_fusion_score():
    """组内排序：同共振/结构时仅改 fusion.weighted_score 不改相对顺序。"""
    _ensure_scripts_path()
    from pool_briefing import sort_group_items

    def _report(name: str, ws: float) -> dict:
        return {
            "name": name,
            "major_stage": "蓄势",
            "stage": "走强",
            "scene": "等转强",
            "current": 10.0,
            "confirm": 10.1,
            "stop": 9.0,
            "support": 9.5,
            "take": 11.0,
            "chan_buy_point_types": [],
            "chan_strokes_count": 3,
            "chan_trend_label": "上行",
            "bars": [],
            "resonance": {"grade": "aligned"},
            "fusion": {"weighted_score": ws, "disagreement": 0.0},
        }

    items = [(_report("高融合", 1.0), ""), (_report("低融合", -1.0), "")]
    ordered = sort_group_items(items)
    names = [r["name"] for r, _ in ordered]
    # 结构键相同 → 保输入顺序，高融合分不得把后者抬前
    assert names == ["高融合", "低融合"]
    flipped = [(_report("低融合", -1.0), ""), (_report("高融合", 1.0), "")]
    assert [r["name"] for r, _ in sort_group_items(flipped)] == ["低融合", "高融合"]
