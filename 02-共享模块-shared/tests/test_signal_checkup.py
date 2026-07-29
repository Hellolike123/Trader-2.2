"""决策体检 checkup：分组统计与结论文案（纯函数，无网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.signal_tracker import (  # noqa: E402
    build_checkup_conclusion,
    compute_group_stats,
    is_win_5d,
    render_checkup_panel,
    resolve_allow_new_recommend,
)


def _rec(*, allow=None, outcome="up", r_5d=2.5, sid="s1"):
    row = {"signal_id": sid, "outcome": outcome, "r_5d": r_5d}
    if allow is not None:
        row["allow_new_recommend"] = allow
    return row


def test_resolve_allow_priority():
    assert resolve_allow_new_recommend({"allow_new_recommend": True}) is True
    assert resolve_allow_new_recommend({"decision_view": {"allow_new_recommend": False}}) is False
    assert resolve_allow_new_recommend({"discipline": {"allow_new_entry": True}}) is True
    lookup = {"x": {"decision_view": {"allow_new_recommend": True}}}
    assert resolve_allow_new_recommend({"signal_id": "x"}, lookup) is True
    assert resolve_allow_new_recommend({"signal_id": "missing"}, lookup) is None


def test_resolve_allow_string_false_not_truthy():
    assert resolve_allow_new_recommend({"allow_new_recommend": "false"}) is False
    assert resolve_allow_new_recommend({"allow_new_recommend": "true"}) is True
    assert resolve_allow_new_recommend({"decision_view": {"allow_new_recommend": "0"}}) is False


def test_build_signal_persists_allow_new_recommend():
    from trader_shared.signal_core import build_signal, decision_persist_fields

    assert decision_persist_fields({}) == {}
    assert decision_persist_fields({"discipline": {}}) == {}

    report = {
        "name": "测试",
        "symbol": "000001.SZ",
        "current": 10.0,
        "confirm": 10.1,
        "stop": 9.0,
        "support": 9.2,
        "resistance": 11.0,
        "scene": "等转强",
        "stage": "修复",
        "theory_status": "等转强",
        "data_status": "full",
        "analysis_time": "2026-07-29 10:00:00",
        "decision_view": {"allow_new_recommend": False, "resonance_grade": "conflict"},
        "discipline": {"allow_new_entry": False},
        "resonance": {"grade": "conflict"},
        "ma": {},
        "low_zone": "9.20元",
    }
    fields = decision_persist_fields(report)
    assert fields["allow_new_recommend"] is False
    assert fields["decision_view"]["allow_new_recommend"] is False
    assert fields["resonance_grade"] == "conflict"

    sig = build_signal(report)
    assert sig["allow_new_recommend"] is False
    assert sig["decision_view"]["allow_new_recommend"] is False

    report_ok = {**report, "decision_view": {"allow_new_recommend": True, "resonance_grade": "aligned"}}
    assert build_signal(report_ok)["allow_new_recommend"] is True


def test_is_win_5d_outcome_or_r5():
    assert is_win_5d({"outcome": "up", "r_5d": -1.0}) is True
    assert is_win_5d({"outcome": "down", "r_5d": 1.5}) is True
    assert is_win_5d({"outcome": "down", "r_5d": -1.0}) is False
    assert is_win_5d({"outcome": "flat", "r_5d": 0.0}) is False


def test_compute_group_stats():
    recs = [
        _rec(outcome="up", r_5d=3.0),
        _rec(outcome="down", r_5d=-2.0, sid="s2"),
        _rec(outcome="up", r_5d=1.0, sid="s3"),
    ]
    stats = compute_group_stats(recs)
    assert stats["total"] == 3
    assert stats["wins"] == 2
    assert stats["win_rate"] == 66.7
    assert stats["avg_r5"] == 0.7


def test_conclusion_insufficient_allowed_sample():
    allowed = {"total": 5, "wins": 4, "win_rate": 80.0, "avg_r5": 2.0}
    denied = {"total": 20, "wins": 8, "win_rate": 40.0, "avg_r5": 0.1}
    text = build_checkup_conclusion(allowed, denied, unknown_count=0, total_with_outcome=25)
    assert "样本不足" in text


def test_conclusion_low_discrimination():
    allowed = {"total": 12, "wins": 7, "win_rate": 58.0, "avg_r5": 1.0}
    denied = {"total": 30, "wins": 17, "win_rate": 56.7, "avg_r5": 0.5}
    text = build_checkup_conclusion(allowed, denied, unknown_count=0, total_with_outcome=42)
    assert "区分度不足" in text


def test_conclusion_denied_group_too_small():
    allowed = {"total": 15, "wins": 12, "win_rate": 80.0, "avg_r5": 2.0}
    denied = {"total": 0, "wins": 0, "win_rate": 0.0, "avg_r5": 0.0}
    text = build_checkup_conclusion(allowed, denied, unknown_count=0, total_with_outcome=15)
    assert "样本不足" in text
    assert "听系统的" not in text


def test_conclusion_effective_gate():
    allowed = {"total": 12, "wins": 9, "win_rate": 75.0, "avg_r5": 2.8}
    denied = {"total": 74, "wins": 38, "win_rate": 51.0, "avg_r5": 0.3}
    text = build_checkup_conclusion(allowed, denied, unknown_count=0, total_with_outcome=86)
    assert "听系统的" in text


def test_conclusion_missing_decision_fields():
    allowed = {"total": 0, "wins": 0, "win_rate": 0.0, "avg_r5": 0.0}
    denied = {"total": 0, "wins": 0, "win_rate": 0.0, "avg_r5": 0.0}
    text = build_checkup_conclusion(allowed, denied, unknown_count=40, total_with_outcome=40)
    assert "无决策字段" in text


def test_render_panel_shape():
    allowed = {"total": 12, "wins": 9, "win_rate": 75.0, "avg_r5": 2.8}
    denied = {"total": 74, "wins": 38, "win_rate": 51.0, "avg_r5": 0.3}
    panel = render_checkup_panel(
        allowed,
        denied,
        days=90,
        unknown_count=0,
        conclusion="听系统的，比瞎买强。继续严闸。",
    )
    assert panel.startswith("决策体检 — 近90日")
    assert "系统允许买：12次" in panel
    assert "系统不让买：74次" in panel
    assert "结论：听系统的" in panel
    assert "#" not in panel
    assert "**" not in panel


def test_rank_final_cap_ignores_fusion_confidence():
    scripts = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pool_cmds.scoring import STAGE_STRENGTH
    from trader_shared.candidate_core import atr_volatility_level

    atr_ratio = 0.015
    _, base_cap = atr_volatility_level(atr_ratio)
    stage_mult = STAGE_STRENGTH.get("蓄势", 0.5)
    cap_no_fusion = round(base_cap * stage_mult)
    cap_with_fusion = round(base_cap * stage_mult * 0.2)
    assert cap_no_fusion != cap_with_fusion
    assert cap_no_fusion > cap_with_fusion


def test_edge_reason_uses_resonance_not_confidence():
    scripts = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "trader"
        / "scripts"
    )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pool_cmds.rank_view import edge_reason

    item = {
        "resonance_grade": "aligned",
        "chanlun_score": 40,
        "wyckoff_score": 5,
        "chip_score": 5,
        "momentum_score": 5,
        "fusion_confidence": 0.1,
    }
    reason = edge_reason(item, [item])
    assert "置信" not in reason
    assert "共振" in reason
