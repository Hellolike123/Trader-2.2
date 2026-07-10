"""chan_discipline + merge_discipline 单测（方案 B：T1–T7）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.chan_discipline import (  # noqa: E402
    apply_chan_discipline,
    merge_discipline,
)
from trader_shared.mistery_gate import (  # noqa: E402
    compute_mistery_gate,
    gate_action_to_execution_text,
)
from trader_shared.conclusion_block import build_conclusion_block  # noqa: E402


def _open_setup(**extra):
    """蓄势×走强 倾向轻仓试错的基础盘面。"""
    d = {
        "current": 55.2,
        "mid_pullback_low": 54.0,
        "mid_pullback_high": 56.5,
        "mid_view": "上涨趋势未坏 · 可跟踪、不加仓",
        "mid_quality": "full",
        "structure_confidence": "high",
        "major_stage": "蓄势",
        "suggested_pct": 10,
        "max_position_pct": 50,
        "has_position": False,
    }
    d.update(extra)
    return d


class TestT1PullbackOutside:
    """T1: 回踩区外 + 日线一类买语义 → allow_new_entry=False。"""

    def test_outside_blocks_even_with_buy_point(self):
        out = apply_chan_discipline(_open_setup(
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
            buy_point_types=["一类买"],
        ))
        assert out["allow_new_entry"] is False
        assert "回踩区" in (out["entry_block_reason"] or "")
        assert "pullback_out" in out["rules_fired"]
        text = gate_action_to_execution_text(out["action_override"] or "观望")
        assert "可按买点挂" not in text

    def test_inside_allows(self):
        out = apply_chan_discipline(_open_setup(current=55.2))
        assert out["allow_new_entry"] is True
        assert out["entry_block_reason"] is None

    def test_missing_pullback_skips(self):
        out = apply_chan_discipline(_open_setup(
            current=58.0,
            mid_pullback_low=None,
            mid_pullback_high=None,
        ))
        assert "pullback_out" not in out["rules_fired"]
        assert out["allow_new_entry"] is True


class TestT2PaifaConflict:
    """T2: 派发 + 缠多/三类买 → notes 含冲突，不允许新开。"""

    def test_paifa_with_buy_points(self):
        out = apply_chan_discipline(_open_setup(
            major_stage="派发",
            buy_point_types=["三类买"],
            mid_view="上涨趋势未坏 · 可跟踪、不加仓",
        ))
        assert out["allow_new_entry"] is False
        notes = "；".join(out["discipline_notes"])
        assert "派发" in notes or "冲突" in notes or "风控" in notes
        assert "stage_risk" in out["rules_fired"] or "stage_buy_conflict" in out["rules_fired"]


class TestT3MergeTightenOnly:
    """T3: gate 观望时 merge 后不得变轻仓/回踩/持有。"""

    def test_gate_watch_not_loosened_by_chan(self):
        gate = {
            "action": "观望",
            "position_cap_pct": 0.0,
            "notes": "远离买点/支撑，禁止竖着追高",
            "hard_block": "none",
            "invalidation": "跌破止损",
            "style": "趋势",
        }
        # 恶意/错误：chan 试图放宽
        chan = {
            "allow_new_entry": True,
            "action_override": "轻仓试错",
            "suggested_pct_cap": 15,
            "discipline_notes": [],
            "entry_block_reason": None,
            "rules_fired": [],
        }
        disc = merge_discipline(gate, chan)
        assert disc["action"] not in ("轻仓试错", "回踩低吸", "持有")
        assert disc["action"] == "观望"
        assert disc["allow_new_entry"] is False

    def test_chan_blocks_gate_open(self):
        gate = {
            "action": "轻仓试错",
            "position_cap_pct": 10.0,
            "notes": "",
            "hard_block": "none",
            "invalidation": "",
            "style": "趋势",
        }
        chan = apply_chan_discipline(_open_setup(
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
        ))
        disc = merge_discipline(gate, chan)
        assert disc["allow_new_entry"] is False
        assert disc["action"] == "观望"
        assert disc["suggested_pct_cap"] == 0 or disc["position_cap_pct"] == 0

    def test_reduce_not_loosened(self):
        gate = {
            "action": "减仓",
            "position_cap_pct": 0.0,
            "notes": "主升动能转弱",
            "hard_block": "none",
            "invalidation": "",
            "style": "趋势",
        }
        chan = apply_chan_discipline(_open_setup())  # allow
        disc = merge_discipline(gate, chan)
        assert disc["action"] == "减仓"
        assert disc["allow_new_entry"] is False


class TestT4ReportDisciplineShape:
    """T4: discipline 字段契约。"""

    def test_merge_output_keys(self):
        gate = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "stop": 54,
            "current": 55.2,
            "support": 54.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        chan = apply_chan_discipline(_open_setup())
        disc = merge_discipline(gate, chan)
        for k in (
            "allow_new_entry",
            "action",
            "suggested_pct_cap",
            "discipline_notes",
            "entry_block_reason",
            "notes",
            "hard_block",
        ):
            assert k in disc


class TestT5ReasonVisible:
    """T5: 渲染/原因可见回踩区或中线偏空。"""

    def test_conclusion_shows_pullback_reason(self):
        gate = {
            "action": "轻仓试错",
            "hard_block": "none",
            "position_cap_pct": 10,
            "notes": "",
        }
        chan = apply_chan_discipline(_open_setup(
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
        ))
        disc = merge_discipline(gate, chan)
        c = build_conclusion_block(
            major_stage="蓄势",
            mistery_gate={**gate, "action": disc["action"], "position_cap_pct": 0,
                          "notes": disc["notes"]},
            discipline=disc,
            key_prices={"chase_ok": False, "risk_chase": 2, "reward_chase": 1},
            fusion={"weighted_score": 0.1},
        )
        assert "回踩区" in c["reason"] or "不买" in c["execution"]
        assert "可按买点挂" not in c["execution"]

    def test_conclusion_shows_mid_weak(self):
        gate = {
            "action": "轻仓试错",
            "hard_block": "none",
            "position_cap_pct": 10,
            "notes": "",
        }
        chan = apply_chan_discipline(_open_setup(
            mid_view="盘整偏空 · 暂缓跟踪",
        ))
        disc = merge_discipline(gate, chan)
        c = build_conclusion_block(
            major_stage="蓄势",
            mistery_gate={**gate, "action": disc["action"], "notes": disc["notes"],
                          "position_cap_pct": 0},
            discipline=disc,
            key_prices={"chase_ok": False},
            fusion={},
        )
        assert "中线看法偏空" in c["reason"] or "暂缓" in c["reason"] or "不买" in c["execution"]


class TestT6MidViewWeak:
    """T6: mid_view 暂缓 → allow_new_entry=False。"""

    def test_mid_view_zan_huan(self):
        out = apply_chan_discipline(_open_setup(
            mid_view="盘整偏空 · 暂缓跟踪",
        ))
        assert out["allow_new_entry"] is False
        assert "mid_weak" in out["rules_fired"]
        assert "中线看法偏空" in (out["entry_block_reason"] or "")


class TestT7LowConfidence:
    """T7: low conf → cap 下降或观望。"""

    def test_structure_low_blocks(self):
        out = apply_chan_discipline(_open_setup(
            mid_quality="partial",
            structure_confidence="low",
        ))
        assert out["allow_new_entry"] is False or out["suggested_pct_cap"] < 10
        assert out["low_confidence"] is True
        notes = "；".join(out["discipline_notes"])
        assert "置信" in notes or out["action_override"] == "观望"

    def test_chip_blocks(self):
        out = apply_chan_discipline(_open_setup(chip_migration_warning=True))
        assert out["allow_new_entry"] is False
        assert "筹码" in "；".join(out["discipline_notes"])

    def test_fund_blocks(self):
        out = apply_chan_discipline(_open_setup(fund_flow_outflow_veto=True))
        assert out["allow_new_entry"] is False
        assert "流出" in "；".join(out["discipline_notes"])


class TestHasPosition:
    def test_position_still_blocks_new_not_force_reduce_alone(self):
        """有持仓：仍否决新开；action_override 为观望不强制减仓指令。"""
        out = apply_chan_discipline(_open_setup(
            has_position=True,
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
        ))
        assert out["allow_new_entry"] is False
        assert out["action_override"] == "观望"  # 不写成强制减仓


class TestGateNoLongerOwnsMigratedRules:
    """B3: gate 不再因回踩区/mid_view 单独否决（由 chan 负责）。"""

    def test_gate_outside_pullback_still_table_open_if_other_ok(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 58.0,
            "support": 55.0,
            "stop": 54.0,
            "buy_ref": 55.5,
            "risk": 1.5,
            "reward_near": 4.0,
            "turnover_rate": 2.0,
            "volume_ratio": 1.0,
            "change_pct": 0.5,
            "mid_pullback_low": 54.0,
            "mid_pullback_high": 56.0,
        })
        # gate 可能因追高仍观望；但 notes 不应再写「不在中线回踩区」
        assert "不在中线回踩区" not in (g.get("notes") or "")

    def test_gate_mid_view_not_in_notes(self):
        g = compute_mistery_gate({
            "major_stage": "蓄势",
            "short_term_momentum": "走强",
            "regime": "正常",
            "current": 55.2,
            "support": 54.5,
            "stop": 54.0,
            "risk": 1.5,
            "reward_near": 4.0,
            "mid_view": "盘整偏空 · 暂缓跟踪",
            "turnover_rate": 2,
            "volume_ratio": 1,
            "change_pct": 0.5,
        })
        assert "中线看法偏空" not in (g.get("notes") or "")
