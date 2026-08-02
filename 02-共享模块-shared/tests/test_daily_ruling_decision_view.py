"""日线裁定听 decision_view / 共振，fusion 不得单独推宜追。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.conclusion_block import build_daily_ruling  # noqa: E402


def test_fusion_bullish_without_dv_no_chase():
    """有融合偏多但无 decision 绿灯 → 不宜宜追。"""
    out = build_daily_ruling(
        {"weighted_score": 0.5, "action": "偏多试探"},
        scene="突破确认",
        chase_ok=True,
        gate_action="轻仓试探",
        decision_view={"allow_new_recommend": False},
    )
    assert "不宜追高" in out


def test_dv_green_and_breakout_can_chase():
    out = build_daily_ruling(
        {"weighted_score": 0.5, "action": "偏多"},
        scene="突破确认",
        chase_ok=True,
        gate_action="轻仓试探",
        decision_view={"allow_new_recommend": True},
        resonance={"grade": "aligned"},
    )
    assert "宜追" in out


def test_resonance_conflict_blocks_chase():
    out = build_daily_ruling(
        {"weighted_score": 0.8, "action": "偏多"},
        scene="突破确认",
        chase_ok=True,
        gate_action="轻仓试探",
        decision_view={"allow_new_recommend": True},
        resonance={"grade": "conflict"},
    )
    assert "不宜追高" in out


def test_fusion_action_reduce_alone_does_not_tighten():
    """A4：仅 fusion.action=减仓、纪律未挡、DV 绿、chase_ok、无 conflict → 不得因 action 收紧。"""
    out = build_daily_ruling(
        {"weighted_score": 0.5, "action": "减仓"},
        scene="突破确认",
        chase_ok=True,
        gate_action="轻仓试探",
        decision_view={"allow_new_recommend": True},
        resonance={"grade": "aligned"},
    )
    assert "不宜追高" not in out
    assert "宜追" in out


def test_fusion_action_empty_alone_does_not_tighten():
    """A4：仅 fusion.action=空仓 → 不得因 action 变不宜追高。"""
    out = build_daily_ruling(
        {"weighted_score": 0.5, "action": "空仓"},
        scene="突破确认",
        chase_ok=True,
        gate_action="轻仓试探",
        decision_view={"allow_new_recommend": True},
        resonance={"grade": "aligned"},
    )
    assert "不宜追高" not in out
    assert "宜追" in out


def test_gate_action_reduce_still_blocks_chase():
    """A4/F2e：gate_action=减仓 → 仍不宜追高（覆盖旧 reduce_like 意图）。"""
    out = build_daily_ruling(
        {"weighted_score": 0.5, "action": "偏多"},
        scene="突破确认",
        chase_ok=True,
        gate_action="减仓",
        decision_view={"allow_new_recommend": True},
        resonance={"grade": "aligned"},
    )
    assert "不宜追高" in out
