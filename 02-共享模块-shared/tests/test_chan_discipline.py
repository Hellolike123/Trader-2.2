"""chan_discipline + merge_discipline 单测（方案 B：T1–T7；R1–R9）。"""
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
    compute_pivot_position,
    compute_weekly_frame,
    needs_same_level_tag,
    append_same_level_tag,
    build_entry_checklist,
    format_entry_line_c1,
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

    def test_data_status_degraded_low_conf(self):
        out = apply_chan_discipline(_open_setup(data_status="degraded"))
        assert out["low_confidence"] is True
        assert any("degraded" in str(n) for n in (out.get("discipline_notes") or []))

    def test_data_status_failed_low_conf(self):
        out = apply_chan_discipline(_open_setup(data_status="failed"))
        assert out["low_confidence"] is True

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



# ── R1–R9（P1/P2 打包）──────────────────────────────────────


class TestR1BuyPointCap:
    """R1: 一类 cap≤5；二类≤10；三类+中线非弱可到阶段上限；有一类优先最严。"""

    def test_buy1_cap_5(self):
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["一类买"],
            suggested_pct=20,
            max_position_pct=50,
        ))
        assert out["allow_new_entry"] is True
        assert out["suggested_pct_cap"] <= 5
        assert out["suggested_pct_cap_short"] <= 5
        assert "buy1_cap" in out["rules_fired"]

    def test_buy2_cap_10(self):
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["二类买"],
            suggested_pct=30,
        ))
        assert out["suggested_pct_cap"] <= 10
        assert "buy2_cap" in out["rules_fired"]

    def test_like2_buy_no_buy2_cap(self):
        """类二买不进正式二买仓位帽（买侧放宽档）。"""
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["类二买"],
            suggested_pct=30,
        ))
        assert "buy2_cap" not in out["rules_fired"]
        assert out["suggested_pct_cap"] == 30

    def test_like2_buy_not_c1_short_trigger(self):
        """C1 买点信号不因类二买点绿。"""
        cl = build_entry_checklist(
            stage="蓄势",
            buy_point_types=["类二买"],
            in_pullback=True,
        )
        assert cl["items"]["short_trigger"] is False
        assert "买点信号" in (cl.get("missing_labels") or [])
        cl2 = build_entry_checklist(
            stage="蓄势",
            buy_point_types=["二类买"],
            in_pullback=True,
        )
        assert cl2["items"]["short_trigger"] is True

    def test_buy1_strictest_over_buy3(self):
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["三类买", "一类买"],
            suggested_pct=40,
        ))
        assert out["suggested_pct_cap"] <= 5
        assert "buy1_cap" in out["rules_fired"]

    def test_buy3_main_when_mid_ok(self):
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["三类买"],
            suggested_pct=30,
            max_position_pct=50,
            mid_view="上涨趋势未坏 · 可跟踪、不加仓",
        ))
        # 三类不额外压到 5/10；可到 suggested 30
        assert out["suggested_pct_cap"] >= 10 or out["suggested_pct_cap"] == 30
        assert out["suggested_pct_cap"] <= 50
        assert "buy3_main_cap" in out["rules_fired"]

    def test_no_buy_point_no_force(self):
        out = apply_chan_discipline(_open_setup(suggested_pct=15))
        assert "buy1_cap" not in out["rules_fired"]
        assert "buy2_cap" not in out["rules_fired"]
        assert out["suggested_pct_cap"] == 15


class TestR2PanZhengNoHeavy:
    """R2: 盘整 → cap≤10，不做趋势重仓。"""

    def test_daily_pan_zheng_cap(self):
        out = apply_chan_discipline(_open_setup(
            structure_type_daily="盘整",
            suggested_pct=30,
        ))
        assert out["suggested_pct_cap"] <= 10
        notes = "；".join(out["discipline_notes"])
        assert "盘整不做趋势重仓" in notes
        assert out["action_override"] in (None, "轻仓试错", "观望")
        if out["allow_new_entry"]:
            assert out["action_override"] in ("轻仓试错", None) or out["suggested_pct_cap"] <= 10

    def test_weekly_pan_zheng_cap(self):
        out = apply_chan_discipline(_open_setup(
            structure_type_weekly="盘整",
            suggested_pct=25,
        ))
        assert out["suggested_pct_cap"] <= 10
        assert "pan_zheng_cap" in out["rules_fired"]

    def test_pan_zheng_with_table_open_stays_light(self):
        gate = {
            "action": "轻仓试错",
            "position_cap_pct": 15.0,
            "notes": "",
            "hard_block": "none",
            "invalidation": "",
            "style": "趋势",
        }
        chan = apply_chan_discipline(_open_setup(
            structure_type_daily="盘整",
            suggested_pct=15,
        ))
        disc = merge_discipline(gate, chan)
        assert disc["suggested_pct_cap"] <= 10
        assert disc["action"] not in ("持有", "回踩低吸") or disc["allow_new_entry"] is False


class TestR3LowZoneShortGate:
    """R3: 现价不在 low_zone → allow_new_entry_short=False。"""

    def test_outside_low_zone_blocks_short(self):
        out = apply_chan_discipline(_open_setup(
            current=55.2,
            low_zone_lower=50.0,
            low_zone_upper=52.0,
        ))
        assert out["allow_new_entry_short"] is False
        assert out["allow_new_entry"] is False
        assert "low_zone_out" in out["rules_fired"]

    def test_inside_low_zone_ok(self):
        out = apply_chan_discipline(_open_setup(
            current=55.2,
            mid_pullback_low=54.0,
            mid_pullback_high=56.5,
            low_zone_lower=54.5,
            low_zone_upper=55.8,
        ))
        assert out["allow_new_entry_short"] is True
        assert "low_zone_out" not in out["rules_fired"]

    def test_missing_low_zone_skips(self):
        out = apply_chan_discipline(_open_setup(
            low_zone_lower=None,
            low_zone_upper=None,
        ))
        assert "low_zone_out" not in out["rules_fired"]
        assert out["allow_new_entry_short"] is True


class TestR4SplitGates:
    """R4: mid/short 分闸；总闸 = mid AND short。"""

    def test_total_equals_mid_and_short(self):
        out = apply_chan_discipline(_open_setup(
            current=58.0,  # 回踩区外 → mid False
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
            low_zone_lower=57.0,
            low_zone_upper=59.0,  # short 可 True
        ))
        assert out["allow_new_entry_mid"] is False
        assert out["allow_new_entry_short"] is True
        assert out["allow_new_entry"] == (
            out["allow_new_entry_mid"] and out["allow_new_entry_short"]
        )

    def test_short_only_blocks_total(self):
        out = apply_chan_discipline(_open_setup(
            current=55.2,
            low_zone_lower=50.0,
            low_zone_upper=51.0,
        ))
        assert out["allow_new_entry_mid"] is True
        assert out["allow_new_entry_short"] is False
        assert out["allow_new_entry"] is False

    def test_caps_split_and_total_min(self):
        out = apply_chan_discipline(_open_setup(
            buy_point_types=["一类买"],
            structure_type_weekly="盘整",
            suggested_pct=40,
        ))
        assert out["suggested_pct_cap_mid"] is not None
        assert out["suggested_pct_cap_short"] is not None
        assert out["suggested_pct_cap"] == min(
            out["suggested_pct_cap_mid"], out["suggested_pct_cap_short"]
        )


class TestR6PivotPosition:
    """R6: compute_pivot_position。"""

    def test_inside(self):
        assert compute_pivot_position(55.0, [
            {"valid": True, "zh_top": 58.0, "zh_bottom": 51.0},
        ]) == "中枢内"

    def test_above_pullback(self):
        pos = compute_pivot_position(59.0, [
            {"valid": True, "zh_top": 58.0, "zh_bottom": 51.0},
        ])
        assert pos == "中枢上(回踩中)"

    def test_below_rebound(self):
        pos = compute_pivot_position(50.0, [
            {"valid": True, "zh_top": 58.0, "zh_bottom": 51.0},
        ])
        assert pos == "中枢下(反抽中)"

    def test_unknown(self):
        assert compute_pivot_position(None, []) == "未知"
        assert compute_pivot_position(50.0, []) == "未知"

    def test_far_outside(self):
        pos = compute_pivot_position(90.0, [
            {"valid": True, "zh_top": 58.0, "zh_bottom": 51.0},
        ])
        assert pos == "中枢外"


class TestR7SameLevelTag:
    """R7: 买卖点/背驰加（本周期）——非区间套确认。"""

    def test_divergence_text(self):
        assert needs_same_level_tag(text="顶背驰 · 看跌") is True
        assert "（本周期）" in append_same_level_tag("顶背驰 · 看跌", True)

    def test_buy_points_obj(self):
        assert needs_same_level_tag({"buy_points": [{"type": "一类买"}]}) is True

    def test_no_signal(self):
        assert needs_same_level_tag({"structure_type": "盘整"}, text="盘整·中性") is False
        assert append_same_level_tag("盘整·中性", False) == "盘整·中性"


class TestR8LifeZhBreak:
    """R8: 破生命线/中枢下沿 → 不新开；有仓倾向减仓。"""

    def test_break_life_blocks(self):
        out = apply_chan_discipline(_open_setup(
            current=53.0,
            life_line=54.0,
            mid_pullback_low=52.0,
            mid_pullback_high=56.0,
        ))
        assert out["allow_new_entry"] is False
        assert out["broke_life_line"] is True
        assert "life_break" in out["rules_fired"]

    def test_break_zh_blocks(self):
        out = apply_chan_discipline(_open_setup(
            current=50.0,
            zh_bottom=51.0,
            mid_pullback_low=49.0,
            mid_pullback_high=56.0,
        ))
        assert out["allow_new_entry"] is False
        assert out["broke_zh_bottom"] is True

    def test_break_life_with_position_reduce(self):
        out = apply_chan_discipline(_open_setup(
            current=53.0,
            life_line=54.0,
            has_position=True,
            mid_pullback_low=52.0,
            mid_pullback_high=56.0,
        ))
        assert out["allow_new_entry"] is False
        assert out["action_override"] == "减仓"


class TestR9WeeklyFrame:
    """R9: weekly_frame 完好|紧张|破坏；破坏不新开。"""

    def test_compute_break(self):
        assert compute_weekly_frame(49.0, 50.0) == "破坏"

    def test_compute_tense(self):
        # 50 在 50 的 2% 内
        assert compute_weekly_frame(50.5, 50.0) == "紧张"

    def test_compute_ok(self):
        assert compute_weekly_frame(55.0, 50.0) == "完好"

    def test_compute_none(self):
        assert compute_weekly_frame(50.0, None, zh_bottom=None) is None

    def test_break_blocks_entry(self):
        out = apply_chan_discipline(_open_setup(
            current=55.2,
            weekly_frame="破坏",
        ))
        assert out["allow_new_entry"] is False
        assert "weekly_frame_break" in out["rules_fired"]

    def test_merge_preserves_split_fields(self):
        gate = {
            "action": "轻仓试错",
            "position_cap_pct": 10.0,
            "notes": "",
            "hard_block": "none",
            "invalidation": "",
            "style": "趋势",
        }
        chan = apply_chan_discipline(_open_setup(buy_point_types=["二类买"]))
        disc = merge_discipline(gate, chan)
        assert "allow_new_entry_mid" in disc
        assert "allow_new_entry_short" in disc
        assert disc["allow_new_entry"] == (
            disc["allow_new_entry_mid"] and disc["allow_new_entry_short"]
        )


class TestC1EntryChecklist:
    """C1：新开：先别买 · 人话缺项｜全绿才可试探。"""

    def test_missing_pullback_line(self):
        out = apply_chan_discipline(_open_setup(
            current=58.0,
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
            buy_point_types=["二类买"],
        ))
        line = out.get("entry_line") or ""
        assert line.startswith("新开：先别买")
        assert "未回到买区" in line or "回踩到位" in line
        assert out["entry_checklist"]["all_green"] is False
        # 内部缺项仍用正式名
        assert "回踩到位" in (out["entry_checklist"].get("missing_labels") or [])

    def test_all_green_line(self):
        out = apply_chan_discipline(_open_setup(
            current=55.2,
            buy_point_types=["二类买"],
            mid_pullback_low=54.0,
            mid_pullback_high=56.5,
        ))
        assert out["entry_checklist"]["all_green"] is True
        assert "可试探" in (out.get("entry_line") or "")
        assert out["entry_checklist"]["missing_labels"] == []

    def test_format_c1_helper(self):
        assert format_entry_line_c1(all_green=True) == "新开：可试探 · 五项齐了"
        assert "未回到买区" in format_entry_line_c1(all_green=False, missing=["回踩到位"])

    def test_c1_conf_ok_label_is_fusion_confidence(self):
        """C1 conf_ok 展示为「融合置信」，不是误导性的「信号一致」。"""
        from trader_shared.chan_discipline import build_entry_checklist

        cl = build_entry_checklist(
            stage="蓄势",
            in_pullback=True,
            buy_point_types=["二类买"],
            low_confidence=True,
        )
        assert cl["all_green"] is False
        assert "融合置信" in (cl.get("missing_labels") or [])
        assert "信号一致" not in (cl.get("missing_labels") or [])

    def test_merge_demotes_open_when_not_all_green(self):
        gate = {
            "action": "轻仓试错",
            "position_cap_pct": 15.0,
            "notes": "",
            "hard_block": "none",
            "invalidation": "x",
            "style": "趋势",
        }
        chan = apply_chan_discipline(_open_setup(
            current=58.0,  # 区外 → 不全绿
            mid_pullback_low=54.0,
            mid_pullback_high=56.0,
            buy_point_types=["二类买"],
        ))
        disc = merge_discipline(gate, chan)
        assert disc["allow_new_entry"] is False
        assert disc["action"] == "观望"
        assert "可试探" not in (disc.get("entry_line") or "")
        assert "新开：先别买" in (disc.get("entry_line") or "") or "新开：否" in (disc.get("entry_line") or "")
