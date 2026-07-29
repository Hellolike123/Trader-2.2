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
    def test_weekly_frame_break_tightens_open_action(self):
        """weekly_frame 破坏主裁在 chan；gate 仅双保险收紧开仓类。"""
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
        # 不崩溃；若表本可开仓则收紧为观望
        assert g["action"] in ("观望", "减仓", "止损离场", "不做", "轻仓试错", "回踩低吸", "持有")
        # 主升×走强通常可开仓 → 破坏后应收紧
        assert g["action"] not in ("轻仓试错", "回踩低吸", "持有") or g.get("position_cap_pct", 0) == 0


class TestMidlinePullbackMigratedOut:
    """回踩区纪律已迁至 chan_discipline；gate 不再写该 notes。"""

    def _base(self, **extra):
        d = {
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
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

    def test_gate_no_pullback_note(self):
        g = compute_mistery_gate(self._base(
            mid_pullback_low=54.0,
            mid_pullback_high=56.5,
        ))
        assert "不在中线回踩区" not in (g.get("notes") or "")

    def test_missing_pullback_no_force(self):
        g = compute_mistery_gate(self._base(current=58.0))
        assert "不在中线回踩区" not in (g.get("notes") or "")


class TestMidViewMigratedOut:
    """mid_view / 缠侧 conf / 筹码否决已迁至 chan_discipline。"""

    def test_gate_no_mid_view_note(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 55.2,
            "stop": 54.0,
            "support": 54.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "mid_view": "盘整偏空 · 暂缓跟踪",
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        assert "中线看法偏空" not in (g.get("notes") or "")

    def test_gate_mid_quality_not_low_conf_alone(self):
        """仅 mid_quality/structure_confidence 不再触发 gate.low_confidence。"""
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 55.2,
            "stop": 54.0,
            "support": 54.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "mid_quality": "partial",
            "structure_confidence": "low",
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        # 无 fusion/data 低置信时，gate 不应仅因缠侧 conf 标记 low_confidence
        assert g.get("low_confidence") is False

    def test_gate_no_chip_note(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 55.2,
            "stop": 54.0,
            "support": 54.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "chip_migration_warning": True,
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        assert "筹码" not in (g.get("notes") or "")


class TestDataStatusLowConfidence:
    """partial / degraded / failed 均应触发 gate 低置信。"""

    def _base(self, **extra):
        raw = {
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 55.2,
            "stop": 54.0,
            "support": 54.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        }
        raw.update(extra)
        return raw

    def test_partial(self):
        g = compute_mistery_gate(self._base(data_status="partial"))
        assert g.get("low_confidence") is True

    def test_degraded(self):
        g = compute_mistery_gate(self._base(data_status="degraded"))
        assert g.get("low_confidence") is True
        assert "数据degraded" in str(g.get("notes") or "")

    def test_failed(self):
        g = compute_mistery_gate(self._base(data_status="failed"))
        assert g.get("low_confidence") is True
        assert "数据failed" in str(g.get("notes") or "")

    def test_full_not_alone(self):
        g = compute_mistery_gate(self._base(data_status="full"))
        assert g.get("low_confidence") is False
