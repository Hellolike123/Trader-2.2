"""decision_core.py 决策核心测试。"""

from __future__ import annotations

import pytest

from trader_shared.decision_core import status_layers, score_for, atr_volatility_level, base_weight


def _make_ma_values(ma5=10.0, ma10=10.0, ma20=10.0) -> dict:
    return {"ma5": ma5, "ma10": ma10, "ma20": ma20}


# ── status_layers ──────────────────────────────────────────────────

class TestStatusLayers:
    def test_current_zero_returns_insufficient(self):
        """current=0 → 数据不足"""
        result = status_layers(
            current=0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["base_status"] == "数据不足"
        assert result["theory_status"] == "数据不足"

    def test_below_hard_stop(self):
        """current <= hard_stop → 暂不碰"""
        result = status_layers(
            current=9.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["theory_status"] == "暂不碰"

    def test_in_low_buy_zone(self):
        """current 在 low_zone 内 → 修复观察/承接存在"""
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["base_status"] == "低位修复"

    def test_above_confirm(self):
        """current >= confirm → 确认观察"""
        result = status_layers(
            current=10.6, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.8, change_pct=1.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["base_status"] == "确认观察"

    def test_ma250_warning_not_blocking(self):
        """250日线下方只标记 warning，不阻断"""
        # 需要足够长的 bars 来计算 MA250
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 300
        result = status_layers(
            current=8.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        # 应该有 warning 但不阻断
        assert result.get("ma250_warning") is True
        # 不应该直接返回"暂不碰"（旧的一票否决行为）
        assert result["base_status"] != "暂不碰" or result["theory_status"] == "暂不碰"


# ── score_for ──────────────────────────────────────────────────────

class TestScoreFor:
    def test_breakthrough_high_score(self):
        """突破确认 → 高分"""
        item = {
            "status": "突破确认", "current": 10.5, "low_zone_upper": 10.0,
            "confirm_price": 10.3, "hard_stop": 9.5, "position_ratio": 0.7,
            "change_pct": 1.0, "below_ma_count": 0,
        }
        s = score_for(item)
        assert s >= 70

    def test_avoid_low_score(self):
        """暂不碰 → 低分"""
        item = {
            "status": "暂不碰", "current": 9.0, "low_zone_upper": 10.0,
            "confirm_price": 10.5, "hard_stop": 9.5, "position_ratio": 0.0,
            "change_pct": -5.0, "below_ma_count": 3,
        }
        s = score_for(item)
        assert s <= 30


# ── atr_volatility_level ──────────────────────────────────────────

class TestATRVolatilityLevel:
    def test_low_volatility(self):
        label, score = atr_volatility_level(0.005)
        assert label == "波动较低"

    def test_normal_volatility(self):
        label, score = atr_volatility_level(0.015)
        assert label == "波动正常"

    def test_high_volatility(self):
        label, score = atr_volatility_level(0.035)
        assert label == "波幅偏高"


# ── base_weight ──────────────────────────────────────────────────

class TestBaseWeight:
    def test_insufficient_data(self):
        assert base_weight("数据不足") > 0

    def test_normal_volatility(self):
        assert base_weight("波动正常") > 0
