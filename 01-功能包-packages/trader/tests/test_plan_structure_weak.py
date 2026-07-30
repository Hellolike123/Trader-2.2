"""作战表分道骨架：可盯 / 等齐 / 先别碰 / 计划过时 + 评分参考附录。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED = ROOT.parents[1] / "02-共享模块-shared"
for p in (str(SCRIPTS), str(SHARED)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pool_cmds.plan_view import render_plan  # noqa: E402


def test_render_plan_lanes_and_score_appendix():
    items = [
        {
            "name": "可盯票",
            "status": "执行",
            "resonance_grade": "aligned",
            "chanlun_score": 32,
            "wyckoff_score": 14,
            "chip_score": 25,
            "momentum_score": 8,
            "total_score": 79,
            "current": 10.0,
            "trigger": 10.2,
            "confirm": 10.2,
            "defense": 9.0,
            "risk_reward": 2.0,
            "major_stage": "蓄势",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": True,
            },
            "chan_buy_point_types": ["一买"],
            "wyckoff": {
                "sc_signal": True,
                "ar_signal": True,
                "st_signal": True,
                "lps_signal": True,
                "sos_signal": False,
            },
        },
        {
            "name": "等齐票",
            "status": "观察",
            "resonance_grade": "missing_structure",
            "total_score": 70,
            "chanlun_score": 20,
            "wyckoff_score": 14,
            "chip_score": 20,
            "momentum_score": 8,
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "defense": 9.0,
            "major_stage": "蓄势",
            "buy_point_lifecycle": {"status": "none"},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": False,
                "allow_new_recommend": False,
            },
            "chan_buy_point_types": [],
        },
        {
            "name": "先别碰票",
            "status": "观察",
            "resonance_grade": "aligned",
            "total_score": 80,
            "chanlun_score": 30,
            "wyckoff_score": 14,
            "chip_score": 20,
            "momentum_score": 10,
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "defense": 9.0,
            "buy_point_lifecycle": {"status": "failed", "lid_price": 10.2},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": False,
            },
            "major_stage": "蓄势",
        },
        {
            "name": "过时票",
            "status": "观察",
            "resonance_grade": "aligned",
            "total_score": 75,
            "chanlun_score": 30,
            "wyckoff_score": 14,
            "chip_score": 20,
            "momentum_score": 10,
            "current": 12.0,
            "trigger": 10.0,
            "confirm": 10.0,
            "defense": 9.0,
            "major_stage": "蓄势",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.5},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": True,
            },
        },
    ]
    md = render_plan(items)
    assert "选股池作战表" in md
    assert "可盯 1" in md
    assert "等齐 1" in md
    assert "先别碰 1" in md
    assert "计划过时 1" in md
    assert "明日只盯" in md
    assert "可盯票" in md
    assert "威：SC→AR→ST→LPS，还差SOS" in md
    assert "事件 4/5" not in md
    assert "事件4/5" not in md
    assert "等齐（1只）" in md
    assert "先别碰（1只）" in md
    assert "计划过时（1只" in md
    assert "评分参考（缠/威/筹/动 · 不决定盯谁）" in md
    assert "总79" in md
    assert "结构短板" not in md
