"""stage_positioning.py 四阶段定位模型测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_bar(close: float, volume: float = 1000, high: float = 0, low: float = 0) -> dict:
    h = high if high > 0 else close * 1.02
    l = low if low > 0 else close * 0.98
    return {"open": close * 0.99, "high": h, "low": l, "close": close, "volume": volume}


def _make_bars(closes: list[float], volumes: list[float] | None = None) -> list[dict]:
    if volumes is None:
        volumes = [1000] * len(closes)
    return [_make_bar(c, v) for c, v in zip(closes, volumes)]


# ── _assess_volume_price ──────────────────────────────────────────

class TestAssessVolumePrice:
    def test_accumulation_low_volume_flat(self):
        """缩量横盘 → 蓄势"""
        from trader_shared.stage_positioning import _assess_volume_price
        # 20 bars: first 15 normal volume, last 5 low volume, flat price
        closes = [10.0] * 20
        volumes = [1000] * 15 + [500] * 5
        bars = _make_bars(closes, volumes)
        stage, score, reason = _assess_volume_price(bars)
        assert stage == "蓄势"
        assert score >= 50

    def test_markup_expanding_volume_rising(self):
        """放量上涨 → 主升"""
        from trader_shared.stage_positioning import _assess_volume_price
        closes = [10.0] * 15 + [10.0, 10.3, 10.6, 10.9, 11.2]
        volumes = [1000] * 15 + [2000, 2200, 2400, 2600, 2800]
        bars = _make_bars(closes, volumes)
        stage, score, reason = _assess_volume_price(bars)
        assert stage == "主升"
        assert score >= 70

    def test_distribution_high_volume_flat(self):
        """放量滞涨 → 派发"""
        from trader_shared.stage_positioning import _assess_volume_price
        closes = [10.0] * 15 + [10.0, 10.05, 9.95, 10.02, 9.98]
        volumes = [1000] * 15 + [2000, 2100, 2200, 2300, 2400]
        bars = _make_bars(closes, volumes)
        stage, score, reason = _assess_volume_price(bars)
        assert stage == "派发"

    def test_markdown_high_volume_falling(self):
        """放量下跌 → 衰退"""
        from trader_shared.stage_positioning import _assess_volume_price
        closes = [10.0] * 15 + [9.7, 9.4, 9.1, 8.8, 8.5]
        volumes = [1000] * 15 + [2000, 2200, 2400, 2600, 2800]
        bars = _make_bars(closes, volumes)
        stage, score, reason = _assess_volume_price(bars)
        assert stage == "衰退"

    def test_insufficient_data(self):
        """数据不足 → 默认蓄势"""
        from trader_shared.stage_positioning import _assess_volume_price
        bars = _make_bars([10.0] * 5)
        stage, score, reason = _assess_volume_price(bars)
        assert stage == "蓄势"
        assert score == 30


# ── _detect_major_stage ──────────────────────────────────────────

class TestDetectMajorStage:
    def test_bullish_convergence(self):
        """量价主升 + MA多头 → 主升"""
        from trader_shared.stage_positioning import _detect_major_stage
        closes = [10.0] * 15 + [10.5, 11.0, 11.5, 12.0, 12.5]
        volumes = [1000] * 15 + [2000, 2200, 2400, 2600, 2800]
        bars = _make_bars(closes, volumes)
        ma_values = {"ma5": 12.0, "ma10": 11.5, "ma20": 11.0, "ma30": 10.5}
        stage, confidence, reason, vp_stage = _detect_major_stage(12.5, ma_values, bars)
        assert stage == "主升"
        assert confidence > 50


# ── _detect_short_term_momentum ──────────────────────────────────

class TestDetectShortTermMomentum:
    def test_missing_data(self):
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(10.0, None, 10.0, 0.0, 0.5)
        assert momentum == "震荡"

    def test_strong(self):
        """现价>=EXPMA10 且 EXPMA10>EXPMA20"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(11.0, 10.5, 10.0, 1.5, 0.7)
        assert momentum == "走强"

    def test_recovery(self):
        """现价在 EXPMA10 和 EXPMA20 之间"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(10.2, 10.5, 10.0, 0.0, 0.5)
        assert momentum == "修复"

    def test_ranging_near(self):
        """跌破EXPMA20但距离不远"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(9.8, 10.5, 10.0, -0.5, 0.4)
        assert momentum == "震荡"

    def test_weak(self):
        """跌破EXPMA20且距离较远"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(9.0, 10.5, 10.0, -2.5, 0.1)
        assert momentum == "转弱"

    def test_no_ma_data(self):
        """均线数据不足 → 震荡"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(10.0, None, None, 0.0, 0.5)
        assert momentum == "震荡"


# ── compute_position_with_env ──────────────────────────────────────

class TestComputePositionWithEnv:
    def test_markup_bullish(self):
        """主升+走强 → 仓位 >= 50%"""
        from trader_shared.stage_positioning import compute_position_with_env
        result = compute_position_with_env("主升", "走强", "牛市")
        assert result["stage_position_pct"] == 60
        assert result["suggested_pct"] > 0
        assert result["hard_rule_blocked"] is False

    def test_markdown_zero_position(self):
        """衰退 → 仓位 0，硬规则阻止"""
        from trader_shared.stage_positioning import compute_position_with_env
        result = compute_position_with_env("衰退", "走强", "牛市")
        assert result["stage_position_pct"] == 0
        assert result["hard_rule_blocked"] is True
        assert "衰退" in result["hard_rule_reason"]

    def test_losing_position_blocks_add(self):
        """持仓亏损 → 禁止加仓"""
        from trader_shared.stage_positioning import compute_position_with_env
        result = compute_position_with_env("主升", "走强", "牛市", pnl_pct=-5.0)
        assert result["hard_rule_blocked"] is True
        assert "亏损" in result["hard_rule_reason"]
        assert result["suggested_pct"] == 0

    def test_total_position_limit(self):
        """总仓位达上限 → 硬规则阻止"""
        from trader_shared.stage_positioning import compute_position_with_env
        result = compute_position_with_env("主升", "走强", "牛市", total_position_pct=80)
        assert result["hard_rule_blocked"] is True


# ── compute_stop_losses ──────────────────────────────────────────

class TestComputeStopLosses:
    def test_accumulation_stops(self):
        """蓄势期止损"""
        from trader_shared.stage_positioning import compute_stop_losses
        result = compute_stop_losses("蓄势", 10.0, 9.5, 9.8)
        assert result["technical"]["price"] == round(9.5 * 0.975, 2)
        assert result["stage_based"]["price"] == round(9.5 * 0.98, 2)
        assert result["time_limit"]["days"] == 30

    def test_markup_stops(self):
        """主升期止损"""
        from trader_shared.stage_positioning import compute_stop_losses
        result = compute_stop_losses("主升", 12.0, 10.0, 11.0)
        assert result["stage_based"]["price"] == round(11.0 * 0.98, 2)
        assert result["time_limit"]["days"] == 15

    def test_decline_stops(self):
        """衰退期止损 = 0.0（不设阶段止损，由技术止损兜底）"""
        from trader_shared.stage_positioning import compute_stop_losses
        result = compute_stop_losses("衰退", 8.0, 9.0, 8.5)
        # 衰退阶段 stage_stop 为 0.0，由技术止损兜底
        assert result["stage_based"]["price"] == 0.0
        assert result["time_limit"]["days"] == 0

    def test_no_support_fallback(self):
        """无支撑位 → 兜底止损"""
        from trader_shared.stage_positioning import compute_stop_losses
        result = compute_stop_losses("蓄势", 10.0, 0, 9.8)
        assert result["technical"]["price"] == round(10.0 * 0.95, 2)


# ── assess_stage (主入口) ──────────────────────────────────────────

class TestAssessStage:
    def test_returns_complete_dict(self):
        """主入口返回完整 dict"""
        from trader_shared.stage_positioning import assess_stage
        closes = [10.0] * 20
        bars = _make_bars(closes)
        ma_values = {"ma5": 10.0, "ma10": 10.0, "ma20": 10.0, "ma30": 10.0}
        with patch("trader_shared.stage_positioning._load_stage_state", return_value={}):
            with patch("trader_shared.stage_positioning._save_stage_state"):
                result = assess_stage(10.0, ma_values, 0.0, bars)
        assert "major_stage" in result
        assert "momentum" in result
        assert "confidence" in result
        assert result["major_stage"] in ("蓄势", "主升", "派发", "衰退")
        assert result["momentum"] in ("走强", "修复", "震荡", "转弱")


# ── compute_exit_plan ──────────────────────────────────────────

class TestComputeExitPlan:
    def test_basic_exit_plan(self):
        """基本止盈计划：1R + 阻力位 + 阶段转派发"""
        from trader_shared.stage_positioning import compute_exit_plan
        result = compute_exit_plan(
            entry_price=57.50,
            stop_price=56.11,
            resistance_price=64.00,
            current_stage="蓄势",
        )
        assert result["risk_r"] == round(57.50 - 56.11, 2)
        assert result["target_1r"] == round(57.50 + (57.50 - 56.11), 2)
        assert result["resistance_exit"] == 64.00
        assert result["stage_exit"] == "派发"
        assert len(result["exit_plan"]) == 4
        assert result["exit_plan"][0]["ratio"] == 0.25
        assert result["exit_plan"][1]["ratio"] == 0.25
        assert result["exit_plan"][2]["ratio"] == 0.25
        assert result["exit_plan"][3]["ratio"] == 0.25

    def test_no_resistance_uses_1r(self):
        """无阻力位 → 第二笔用 1R 目标（保本）"""
        from trader_shared.stage_positioning import compute_exit_plan
        result = compute_exit_plan(
            entry_price=57.50,
            stop_price=56.11,
            resistance_price=None,
            current_stage="主升",
        )
        assert result["resistance_exit"] is None
        # 第二笔应该是 1R（保本目标）
        target_1r = round(57.50 + (57.50 - 56.11), 2)
        assert result["exit_plan"][1]["price"] == target_1r

    def test_resistance_below_entry_ignored(self):
        """阻力位低于买入价 → 忽略，用 2R"""
        from trader_shared.stage_positioning import compute_exit_plan
        result = compute_exit_plan(
            entry_price=57.50,
            stop_price=56.11,
            resistance_price=55.00,
            current_stage="蓄势",
        )
        assert result["resistance_exit"] is None

    def test_invalid_entry_price(self):
        """买入价 <= 止损价 → 返回空计划"""
        from trader_shared.stage_positioning import compute_exit_plan
        result = compute_exit_plan(
            entry_price=56.00,
            stop_price=57.00,
            resistance_price=60.00,
            current_stage="蓄势",
        )
        assert result["risk_r"] == 0.0
        assert result["exit_plan"] == []

    def test_dynamic_resistance_from_bars(self):
        """无阻力位但有 K 线 → 用近 20 日最高价"""
        from trader_shared.stage_positioning import compute_exit_plan
        bars = _make_bars([55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0, 62.0,
                           63.0, 64.0, 65.0, 66.0, 67.0, 68.0, 69.0, 70.0,
                           71.0, 72.0, 73.0, 74.0])
        result = compute_exit_plan(
            entry_price=70.0,
            stop_price=68.0,
            resistance_price=None,
            current_stage="主升",
            bars=bars,
        )
        assert result["resistance_exit"] == round(74.0 * 1.02, 2)  # high = close * 1.02


# ── compute_stage_stop ──────────────────────────────────────────

class TestComputeStageStop:
    def test_accumulation_with_range_low(self):
        """蓄势期 + 有区间下沿 → 用区间下沿"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("蓄势", ma20=10.0, range_low=9.5)
        assert result["price"] == 9.5
        assert "蓄势区间下沿" in result["reason"]

    def test_accumulation_no_range_low(self):
        """蓄势期 + 无区间下沿 → 用 MA20 * 0.95"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("蓄势", ma20=10.0, range_low=None)
        assert result["price"] == round(10.0 * 0.95, 2)

    def test_markup_uses_ma20(self):
        """主升期 → 用 MA20"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("主升", ma20=11.0)
        assert result["price"] == 11.0
        assert "MA20" in result["reason"]

    def test_distribution_above_ma20(self):
        """派发期无 expma20 → fallback 到 MA20 上方"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("派发", ma20=11.0, atr_pct=0.02)
        assert result["price"] > 11.0
        assert "锁定收益" in result["reason"]
        assert "MA20" in result["reason"]

    def test_distribution_uses_expma20(self):
        """派发期有 expma20 → 优先用 EXPMA(20) 上方"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("派发", ma20=11.0, atr_pct=0.02, expma20=11.5)
        assert result["price"] > 11.5
        assert "EXPMA(20)" in result["reason"]

    def test_decline_no_hold(self):
        """衰退期 → 不持有（compute_stage_stop 仍返回 0，因为此函数无 current 参数）"""
        from trader_shared.stage_positioning import compute_stage_stop
        result = compute_stage_stop("衰退", ma20=8.0)
        assert result["price"] == 0.0
        assert "不持有" in result["reason"]


# ── check_time_stop ──────────────────────────────────────────

class TestCheckTimeStop:
    def test_accumulation_not_triggered(self):
        """蓄势期 10 天 → 未触发"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-20", "蓄势", 10, False)
        assert result["triggered"] is False
        assert result["days_left"] == 20

    def test_accumulation_triggered(self):
        """蓄势期 30 天不突破 → 触发"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-01", "蓄势", 30, False)
        assert result["triggered"] is True
        assert "走人" in result["action"]

    def test_accumulation_with_breakout(self):
        """蓄势期 30 天但已突破 → 不触发"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-01", "蓄势", 30, True)
        assert result["triggered"] is False

    def test_markup_not_triggered(self):
        """主升期 10 天 → 未触发"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-20", "主升", 10, False)
        assert result["triggered"] is False
        assert result["days_left"] == 5

    def test_markup_triggered(self):
        """主升期 15 天不创新高 → 触发"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-15", "主升", 15, False)
        assert result["triggered"] is True
        assert "减仓" in result["action"]

    def test_distribution_no_buy(self):
        """派发期 → 不建议买入"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-20", "派发", 5, False)
        assert result["triggered"] is False
        assert "不建议" in result["action"]

    def test_decline_clear(self):
        """衰退期有持仓 → 清仓"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-20", "衰退", 5, False)
        assert result["triggered"] is True
        assert "清仓" in result["action"]

    def test_decline_no_position(self):
        """衰退期空仓 → 不触发清仓"""
        from trader_shared.stage_positioning import check_time_stop
        result = check_time_stop("2026-05-20", "衰退", 5, False, has_position=False)
        assert result["triggered"] is False
        assert "空仓" in result["action"]


# ── compute_stop_summary ──────────────────────────────────────────

class TestComputeStopSummary:
    def test_nearest_stop(self):
        """取最高的止损价（最近当前价）"""
        from trader_shared.stage_positioning import compute_stop_summary
        time_stop = {"triggered": False, "action": "等待", "days_left": 20}
        result = compute_stop_summary(
            technical_stop=9.5,
            stage_stop=9.8,
            time_stop=time_stop,
            current_price=10.0,
        )
        assert result["final_stop"] == 9.8
        assert "技术止损" in result["stops"]
        assert "阶段止损" in result["stops"]

    def test_only_technical(self):
        """只有技术止损"""
        from trader_shared.stage_positioning import compute_stop_summary
        time_stop = {"triggered": False, "action": "等待", "days_left": 0}
        result = compute_stop_summary(
            technical_stop=9.5,
            stage_stop=0.0,
            time_stop=time_stop,
            current_price=10.0,
        )
        assert result["final_stop"] == 9.5


# ── action_for_holding_state ─────────────────────────────────────

class TestActionForHoldingState:
    """fusion action 持仓场景化仲裁测试。"""

    def test_reduce_with_position(self):
        """减仓 + 已有仓位 → 已有仓位者执行"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("减仓", True)
        assert result["action"] == "减仓"
        assert "已有仓位者" in result["holding_hint"]

    def test_reduce_without_position(self):
        """减仓 + 无仓位 → 未持仓者不参与"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("减仓", False)
        assert result["action"] == "减仓"
        assert "未持仓者不参与" in result["holding_hint"]

    def test_empty_stop_without_position(self):
        """空仓/止损 + 无仓位 → 未持仓者不参与"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("空仓/止损", False)
        assert "未持仓者不参与" in result["holding_hint"]

    def test_veto_without_position(self):
        """大盘否决 + 无仓位 → 未持仓者不参与"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("空仓 (大盘很差, 一票否决)", False)
        assert "未持仓者不参与" in result["holding_hint"]

    def test_add_without_position(self):
        """增持 + 无仓位 → 未持仓者建仓"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("增持", False)
        assert result["action"] == "增持"
        assert "建仓" in result["holding_hint"]

    def test_add_with_position(self):
        """增持 + 已有仓位 → 已有仓位者加仓"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("半仓试 (多方主导)", True)
        assert "已有仓位者" in result["holding_hint"]
        assert "加仓" in result["holding_hint"]

    def test_neutral_action(self):
        """观望类动作 → 观望等待"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("持股观望", False)
        assert "观望" in result["holding_hint"]

    def test_disagreement_action(self):
        """分歧降级动作 → 观望等待"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("观望 (信号冲突)", True)
        assert "观望" in result["holding_hint"]

    def test_empty_action(self):
        """空 action → 观望等待（fallback）"""
        from trader_shared.stage_positioning import action_for_holding_state
        result = action_for_holding_state("", False)
        assert "观望" in result["holding_hint"]

    def test_action_preserved(self):
        """所有情况 action 原始值不变"""
        from trader_shared.stage_positioning import action_for_holding_state
        for action in ["减仓", "增持", "持股观望", "空仓/止损"]:
            for has_pos in [True, False]:
                result = action_for_holding_state(action, has_pos)
                assert result["action"] == action
