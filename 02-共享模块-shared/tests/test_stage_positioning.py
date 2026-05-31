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
        stage, confidence, reason = _detect_major_stage(12.5, ma_values, bars)
        assert stage == "主升"
        assert confidence > 50


# ── _detect_short_term_momentum ──────────────────────────────────

class TestDetectShortTermMomentum:
    def test_strengthening(self):
        """MA5 > MA10, change > 1% → 走强"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(11.0, 10.8, 10.5, 2.0, 0.5)
        assert momentum == "走强"

    def test_weakening(self):
        """MA5 < MA10, change < -2% → 转弱"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(9.5, 10.0, 10.5, -3.0, 0.3)
        assert momentum == "转弱"

    def test_repairing(self):
        """站上MA5但MA5 < MA10 → 修复"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(10.5, 10.3, 10.8, 0.5, 0.4)
        assert momentum == "修复"

    def test_oscillating(self):
        """跌破MA5但MA5 > MA10，不在MA10附近 → 震荡"""
        from trader_shared.stage_positioning import _detect_short_term_momentum
        momentum, reason = _detect_short_term_momentum(9.0, 10.5, 10.0, -0.5, 0.4)
        assert momentum == "震荡"

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
        assert result["stage_position_pct"] == 70
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
        """衰退期止损 = 0"""
        from trader_shared.stage_positioning import compute_stop_losses
        result = compute_stop_losses("衰退", 8.0, 9.0, 8.5)
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
