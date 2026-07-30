"""作战表「结构短板」：只报拖后腿，不贴总分榜。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED = ROOT.parents[1] / "02-共享模块-shared"
for p in (str(SCRIPTS), str(SHARED)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pool_cmds.plan_view import (  # noqa: E402
    _structure_weak_lines,
    _structure_weak_parts,
    render_plan,
)


def test_weak_parts_resonance_and_rr():
    item = {
        "name": "天齐",
        "status": "执行",
        "resonance_grade": "missing_structure",
        "chanlun_score": 33,
        "chip_score": 25,
        "risk_reward": 0.1,
        "current": 45.0,
        "trigger": 47.0,
    }
    parts = _structure_weak_parts(item)
    assert "还差缠论" in parts
    assert "缠偏弱" not in parts  # 与还差缠论不叠
    assert "赔率偏弱" in parts


def test_weak_lines_skips_stale_and_eliminated():
    items = [
        {
            "name": "过期票",
            "status": "执行",
            "resonance_grade": "missing_structure",
            "chanlun_score": 20,
            "chip_score": 25,
            "current": 12.0,
            "trigger": 10.0,
            "risk_reward": 2.0,
        },
        {
            "name": "淘汰票",
            "status": "淘汰",
            "resonance_grade": "aligned",
            "chanlun_score": 20,
            "chip_score": 25,
            "current": 10.0,
            "trigger": 10.1,
        },
        {
            "name": "观察弱缠",
            "status": "观察",
            "resonance_grade": "aligned",
            "chanlun_score": 20,
            "chip_score": 25,
            "current": 10.0,
            "trigger": 10.1,
            "risk_reward": 2.0,
        },
    ]
    lines = _structure_weak_lines(items)
    assert len(lines) == 1
    assert "观察弱缠" in lines[0]
    assert "缠偏弱" in lines[0]


def test_render_plan_has_weak_section_not_scoreboard():
    items = [
        {
            "name": "南网科技",
            "status": "执行",
            "resonance_grade": "missing_structure",
            "chanlun_score": 32,
            "wyckoff_score": 14,
            "chip_score": 25,
            "momentum_score": 8,
            "total_score": 79,
            "current": 10.0,
            "trigger": 10.2,
            "defense": 9.0,
            "risk_reward": 0.5,
            "major_stage": "蓄势",
        }
    ]
    md = render_plan(items)
    assert "结构短板" in md
    assert "还差缠论" in md
    assert "评分参考" not in md
    assert "总79" not in md
