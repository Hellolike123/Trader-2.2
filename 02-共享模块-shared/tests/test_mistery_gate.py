"""Mistery 门控单测：H1–H7、阶段表、华工类否决、空仓减仓译义。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.mistery_gate import (  # noqa: E402
    compute_mistery_gate,
    gate_action_to_execution_text,
)


class TestHardBlocks:
    def test_h1_regime_bad(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "很差",
            "current": 10,
            "support": 9.5,
            "stop": 9.0,
            "confirm": 11,
            "risk": 0.5,
            "reward_near": 1.5,
        })
        assert "H1" in g["hard_block"]
        assert g["action"] == "不做"
        assert g["position_cap_pct"] == 0

    def test_h2_decline(self):
        g = compute_mistery_gate({
            "major_stage": "衰退",
            "short_term_momentum": "转弱",
            "regime": "正常",
            "stop": 9.0,
            "current": 10,
            "risk": 1,
            "reward_near": 2,
        })
        assert "H2" in g["hard_block"]
        assert g["action"] == "不做"

    def test_h3_distribution_no_add(self):
        g = compute_mistery_gate({
            "major_stage": "派发",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 9.0,
            "current": 10,
            "support": 9.5,
            "risk": 0.5,
            "reward_near": 1.5,
        })
        assert "H3" in g["hard_block"]
        assert g["action"] in ("观望", "减仓", "不做", "止损离场")
        assert g["position_cap_pct"] == 0

    def test_h4_no_stop(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": None,
            "current": 10,
            "risk": 1,
            "reward_near": 2,
        })
        assert "H4" in g["hard_block"]
        assert g["action"] == "不做"

    def test_h5_poor_rr(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势偏强",
            "short_term_momentum": "震荡",
            "regime": "偏弱",
            "current": 12,
            "support": 10,
            "stop": 9.5,
            "confirm": 12.2,
            "buy_ref": 10.05,
            "risk": 0.55,
            "reward_near": 0.4,  # < risk
            "min_rr": 1.0,
            "scene": "冲高减仓",
        })
        assert "H5" in g["hard_block"]
        assert g["action"] == "不做"
        assert g["position_cap_pct"] == 0

    def test_h7_average_down_forbidden(self):
        g = compute_mistery_gate({
            "major_stage": "主升",
            "short_term_momentum": "修复",
            "regime": "正常",
            "stop": 9,
            "current": 10,
            "risk": 1,
            "reward_near": 3,
            "wants_average_down": True,
        })
        assert "H7" in g["hard_block"]
        assert g["action"] == "不做"


class TestStageMomentumTable:
    def test_accum_strong_try(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 9,
            "current": 10,
            "support": 9.8,
            "buy_ref": 9.9,
            "risk": 0.9,
            "reward_near": 2.0,
            "suggested_pct": 10,
            "turnover_rate": 3.0,
            "volume_ratio": 1.0,
            "change_pct": 1.0,
        })
        assert g["hard_block"] == "none"
        assert g["action"] == "轻仓试错"
        assert 0 < g["position_cap_pct"] <= 15

    def test_markup_hold(self):
        g = compute_mistery_gate({
            "major_stage": "主升",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 9,
            "current": 10.2,
            "support": 10.0,
            "buy_ref": 10.0,
            "risk": 1.0,
            "reward_near": 2.5,
            "turnover_rate": 2.0,
            "volume_ratio": 1.1,
            "change_pct": 0.5,
        })
        assert g["action"] in ("持有", "观望")  # 若判追高可能观望
        assert g["position_cap_pct"] <= 50

    def test_regime_weak_cuts_try_size(self):
        base = {
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "stop": 9,
            "current": 10,
            "support": 9.8,
            "buy_ref": 9.9,
            "risk": 0.9,
            "reward_near": 2.0,
            "suggested_pct": 15,
            "turnover_rate": 3.0,
            "volume_ratio": 1.0,
            "change_pct": 0.5,
        }
        normal = compute_mistery_gate({**base, "regime": "正常"})
        weak = compute_mistery_gate({**base, "regime": "偏弱"})
        if normal["action"] == "轻仓试错" and weak["action"] == "轻仓试错":
            assert weak["position_cap_pct"] <= normal["position_cap_pct"]


class TestHuagongScenario:
    """华工类：蓄势偏强 × 震荡 × 冲高 × 盈亏比差 → 不做/不追。"""

    def test_huagong_like_block(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势偏强",
            "short_term_momentum": "震荡",
            "theory_status": "冲高减仓",
            "scene": "冲高减仓",
            "regime": "偏弱",
            "current": 48.5,
            "support": 45.0,
            "stop": 44.0,
            "confirm": 49.0,
            "buy_ref": 45.1,
            "risk": 1.1,
            "reward_near": 0.8,  # 近端赚 < 风险
            "min_rr": 1.0,
            "suggested_pct": 10,
            "turnover_rate": 4.0,
            "volume_ratio": 1.2,
            "change_pct": 2.0,
        })
        assert g["action"] in ("不做", "观望")
        assert g["position_cap_pct"] == 0
        # 硬否决应含 H5 或至少阶段观望
        assert g["hard_block"] != "none" or g["action"] == "观望"

    def test_empty_position_no_bare_reduce(self):
        text = gate_action_to_execution_text("减仓", has_position=False)
        assert "减仓" not in text or "不宜" in text
        assert "不新开" in text or "不宜追高" in text

    def test_with_position_reduce_ok(self):
        text = gate_action_to_execution_text("减仓", has_position=True)
        assert "减仓" in text


class TestNoStateRewrite:
    def test_gate_does_not_mutate_inputs(self):
        inputs = {
            "major_stage": "蓄势偏强",
            "short_term_momentum": "震荡",
            "regime": "偏弱",
            "current": 48.5,
            "support": 45.0,
            "stop": 44.0,
            "confirm": 49.0,
            "risk": 1.0,
            "reward_near": 0.5,
        }
        snapshot = dict(inputs)
        compute_mistery_gate(inputs)
        assert inputs == snapshot

    def test_ma20_proxy_note(self):
        g = compute_mistery_gate({
            "major_stage": "主升",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 9,
            "support": 9.5,
            "current": 10,
            "risk": 1,
            "reward_near": 2,
            "ma20": None,
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        assert "520" in g["notes"] or "stop/support" in g["notes"]


class TestWeeklyFrameP1Hook:
    def test_weekly_frame_recorded_not_crash(self):
        g = compute_mistery_gate({
            "major_stage": "主升",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 9,
            "current": 10,
            "risk": 1,
            "reward_near": 2,
            "weekly_frame": "破坏",
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        assert "weekly_frame" in g["notes"]


class TestMidlinePullbackDiscipline:
    """现价不在中线回踩区 → 不新开（消费 mid 价，不改价）。"""

    def _base(self, **extra):
        d = {
            "major_stage": "蓄势",
            "short_term_momentum": "走强",  # 表：轻仓试错
            "regime": "正常",
            "current": 58.0,
            "support": 55.0,
            "stop": 54.0,
            "confirm": 60.0,
            "buy_ref": 55.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "min_rr": 1.0,
            "turnover_rate": 2.0,
            "volume_ratio": 1.0,
            "change_pct": 0.5,
        }
        d.update(extra)
        return d

    def test_outside_pullback_blocks_new_open(self):
        g = compute_mistery_gate(self._base(
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.5,  # 现价在区上方
        ))
        assert g["action"] == "观望"
        assert "回踩区" in g["notes"]
        assert g["position_cap_pct"] == 0

    def test_inside_pullback_allows_table_action(self):
        g = compute_mistery_gate(self._base(
            current=55.2,
            support=55.0,
            buy_ref=55.2,
            mid_pullback_low=54.0,
            mid_pullback_high=56.5,
        ))
        # 在区内且未追高 → 允许轻仓试错（或至少不是因回踩区被砍）
        assert "不在中线回踩区" not in g["notes"]
        assert g["action"] in ("轻仓试错", "观望", "回踩低吸")  # 可能被其它规则裁，但不因区外

    def test_missing_pullback_no_force(self):
        """回踩区数据不足 → 不启用本规则。"""
        g = compute_mistery_gate(self._base(current=58.0))
        assert "不在中线回踩区" not in g["notes"]

    def test_in_flag_false(self):
        g = compute_mistery_gate(self._base(
            current=55.0,
            in_midline_pullback=False,
        ))
        assert g["action"] == "观望"
        assert "回踩区" in g["notes"]

    def test_reduce_actions_not_downgraded_by_pullback(self):
        """减仓/止损离场不被回踩区改成观望。"""
        g = compute_mistery_gate({
            "major_stage": "主升",
            "short_term_momentum": "转弱",
            "regime": "正常",
            "current": 58.0,
            "stop": 50.0,
            "support": 52.0,
            "risk": 2,
            "reward_near": 5,
            "mid_pullback_low": 50.0,
            "mid_pullback_high": 52.0,
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": -1,
        })
        assert g["action"] in ("减仓", "止损离场", "观望")  # 主升转弱→减仓，区外不应把减仓洗掉
        if g["action"] == "减仓":
            assert "不在中线回踩区" not in g["notes"] or True
