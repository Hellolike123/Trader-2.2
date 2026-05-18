from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED = ROOT.parents[1] / "02-共享模块-shared"

for p in (SCRIPTS, SHARED):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
from run_analysis import sync_report_with_data

# ---------------------------------------------------------------------------
# Helper – minimal report + levels, ready for every check
# ---------------------------------------------------------------------------

def _base_report(**overrides: float) -> dict:
    base: dict = {
        "current": 50.0,
        "support": 48.00,
        "resistance": 55.00,
        "confirm": 52.00,
        "stop": 47.00,
        "take": 60.00,
        "scene": "低吸观察",
        "state_label": "修复观察，未确认转强",
    }
    base.update(overrides)
    return base


def _base_levels(**overrides) -> dict:
    base: dict = {"ma_values": {"ma5": 50.5, "ma10": 49.5, "ma20": None, "ma30": None}}
    base.update(overrides)
    return base


# =========================================================================
# 1. MA trend vs state_label contradiction
# =========================================================================

class TestMaTrendLabel:
    def test_ma5_gt_ma10_does_not_clobber_no_kongtou(self):
        """When labels don't contain 空头/多头, MA mismatch should NOT change them."""
        report = _base_report(scene="观望")
        report["state_label"] = "震荡观察"  # no 空头/多头
        levels = _base_levels()
        # ma5=51 > ma10=49 = bullish, but label is neutral → nothing to fix
        sync_report_with_data(report, levels)
        assert report["state_label"] == "震荡观察"

    def test_ma5_lt_ma10_cleans_kongtou(self):
        """ma5 < ma10 is bearish. If label says 多头, correct to 空头."""
        report = _base_report(current=49.0)
        report["state_label"] = "修复多头"  # incorrectly says bullish
        levels = _base_levels()
        levels["ma_values"]["ma5"] = 48.0  # bearish
        levels["ma_values"]["ma10"] = 49.5

        sync_report_with_data(report, levels)
        assert "空头" in report["state_label"]

    def test_ma5_gt_ma10_cleans_ma10多头(self):
        """ma5 > ma10 is bullish. If label says 空头, correct to 多头."""
        report = _base_report(current=51.0)
        report["state_label"] = "修复空头"  # incorrectly says bearish
        levels = _base_levels()  # ma5=50.5 > ma10=49.5 = bullish

        sync_report_with_data(report, levels)
        assert "多头" in report["state_label"]


# =========================================================================
# 2. Support > Resistance contradiction
# =========================================================================

class TestSupportResistance:
    def test_support_gt_resistance_swapped(self):
        """When support >= resistance, swap them to a reasonable 3%/3% gap."""
        report = _base_report()
        report["support"] = 56.00  # > resistance 55.00
        report["resistance"] = 55.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["support"] < report["resistance"]

    def test_support_eq_resistance_swapped(self):
        """When support == resistance, still swapped."""
        report = _base_report()
        report["support"] = 55.00
        report["resistance"] = 55.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["support"] < report["resistance"]

    def test_no_swap_when_valid(self):
        """support < resistance should remain unchanged."""
        report = _base_report()
        levels = _base_levels()
        orig_support = report["support"]
        orig_resistance = report["resistance"]

        sync_report_with_data(report, levels)
        assert report["support"] == orig_support
        assert report["resistance"] == orig_resistance


# =========================================================================
# 3. Stop >= Support contradiction
# =========================================================================

class TestStopSupport:
    def test_stop_above_support_pulled_below(self):
        """If stop >= support, pull stop down below support."""
        report = _base_report()
        report["support"] = 48.00
        report["stop"] = 49.00  # above support ← wrong
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["stop"] < report["support"]

    def test_stop_eq_support_pulled_below(self):
        """stop == support should also be corrected."""
        report = _base_report()
        report["support"] = 48.00
        report["stop"] = 48.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["stop"] < report["support"]

    def test_stop_below_support_unchanged(self):
        """stop < support is correct, should remain unchanged."""
        report = _base_report()
        orig_stop = report["stop"]
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["stop"] == orig_stop


# =========================================================================
# 4. Take <= Confirm contradiction
# =========================================================================

class TestTakeConfirm:
    def test_take_below_confirm_pushed_up(self):
        """If take <= confirm, push take above confirm."""
        report = _base_report()
        report["confirm"] = 58.00
        report["take"] = 55.00  # below confirm ← wrong
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["take"] > report["confirm"]

    def test_take_eq_confirm_pushed_up(self):
        """take == confirm should also be corrected."""
        report = _base_report()
        report["confirm"] = 60.00
        report["take"] = 60.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["take"] > report["confirm"]

    def test_take_above_confirm_unchanged(self):
        """take > confirm is correct, should remain unchanged."""
        report = _base_report()
        orig_take = report["take"]
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["take"] == orig_take


# =========================================================================
# 5. Breakout scene but confirm > current
# =========================================================================

class TestBreakoutDowngrade:
    def test_breakout_confirm_scene_downgraded_to_watch(self):
        """突破确认/突破观察 but confirm > current → 观望 + 未确认."""
        report = _base_report()
        report["scene"] = "突破确认"
        report["confirm"] = 55.00  # > current 50
        report["state_label"] = "突破确认中"
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "观望"
        assert report["state_label"] == "未确认"

    def test_breakout_observe_scene_downgraded_to_watch(self):
        """突破观察 but confirm > current → 观望."""
        report = _base_report()
        report["scene"] = "突破观察"
        report["confirm"] = 55.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "观望"


# =========================================================================
# 6. Chasing scene but current < support
# =========================================================================

class TestChaseDowngrade:
    def test_low_buy_below_support_downgraded(self):
        """低吸观察 but current < support → 破位下行."""
        report = _base_report()
        report["scene"] = "低吸观察"
        report["current"] = 46.00  # < support 48
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "破位下行"
        assert report["state_label"] == "破位下行"

    def test_defense_below_support_downgraded(self):
        """防守观察 but current < support → 破位下行."""
        report = _base_report()
        report["scene"] = "防守观察"
        report["current"] = 47.00
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "破位下行"

    def test_gaochong_below_support_downgraded(self):
        """冲高减仓 but current < support → 低吸观察."""
        report = _base_report()
        report["scene"] = "冲高减仓"
        report["current"] = 47.00  # < support
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "低吸观察"


# =========================================================================
# 7. Breakout observe promoted to confirm
# =========================================================================

class TestBreakoutPromote:
    def test_breakout_observe_promoted_when_above_confirm(self):
        """突破观察 but current >= confirm → 突破确认 + 趋势走强."""
        report = _base_report()
        report["scene"] = "突破观察"
        report["current"] = 55.00
        report["confirm"] = 52.00  # current >= confirm
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "突破确认"
        assert report["state_label"] == "趋势走强"


# =========================================================================
# 8. Space-not-enough but current < support
# =========================================================================

class TestSpaceNotEnough:
    def test_space_insufficient_below_support(self):
        """空间不足 but current < support → 修复观察."""
        report = _base_report()
        report["scene"] = "空间不足"
        report["current"] = 46.00  # < support
        levels = _base_levels()

        sync_report_with_data(report, levels)
        assert report["scene"] == "修复观察"
        assert report["state_label"] == "修复观察"


# =========================================================================
# 9. All zeros – no crash
# =========================================================================

class TestEdgeCases:
    def test_all_zeros_no_crash(self):
        """Zero/negative values should not cause errors."""
        report = {
            "current": 0, "support": 0, "resistance": 0,
            "confirm": 0, "stop": 0, "take": 0,
            "scene": "", "state_label": "",
        }
        levels = {}
        sync_report_with_data(report, levels)

    def test_null_values_no_crash(self):
        """Null/missing values should not cause errors."""
        report = {
            "current": None, "support": None, "resistance": None,
            "confirm": None, "stop": None, "take": None,
            "scene": None, "state_label": None,
        }
        levels = {"ma_values": {}}
        sync_report_with_data(report, levels)
