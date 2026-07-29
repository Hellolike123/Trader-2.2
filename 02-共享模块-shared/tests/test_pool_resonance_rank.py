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
    assert "拆台" in resonance_grade_label("momentum_veto")


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
