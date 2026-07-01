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

    def test_承接存在_requires_below_ma_count_ge_3(self):
        """承接存在 需要 below_ma_count >= 3 且 current > support。"""
        # below_ma_count=3 (current=10.05 < ma5=11, ma10=12, ma20=13)
        ma_values = {"ma5": 11.0, "ma10": 12.0, "ma20": 13.0}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=ma_values, pressure_space_pct=0.0,
        )
        # With below_ma_count=3 and current > support, should get 承接存在
        # (assuming trend_ok is True)
        assert result["theory_status"] in ("承接存在", "修复观察")

    def test_承接存在_not_triggered_below_ma_count_lt_3(self):
        """below_ma_count < 3 时不应触发承接存在。"""
        # below_ma_count=1 (current=10.05 < ma20=11, but > ma5=9, ma10=9)
        ma_values = {"ma5": 9.0, "ma10": 9.0, "ma20": 11.0}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=ma_values, pressure_space_pct=0.0,
        )
        assert result["theory_status"] != "承接存在"

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


class TestFakeBreakAndPhasedExit:
    def test_fake_break_detected(self):
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5 + [{"close": 7.0, "high": 7.5, "low": 6.5}]
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["theory_status"] == "防守观察"
        assert result["base_status"] == "防守观察"

    def test_near_stop_triggers(self):
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 30
        result = status_layers(
            current=9.36, support=9.4, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.3, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["theory_status"] == "冲高减仓"

    def test_near_stop_not_triggers(self):
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 30
        result = status_layers(
            current=10.4, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.0, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["theory_status"] != "冲高减仓"

    def test_fake_break_not_detected(self):
        """跌破止损且近3日无收盘>=hard_stop → 真跌破"""
        bars = [{"close": 7.0, "high": 7.5, "low": 6.5}] * 10
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["base_status"] == "风险回避"
        assert result["theory_status"] == "暂不碰"

    def test_exit_phased_disabled(self, monkeypatch):
        """EXIT_PHASED_ENABLED=False → 不触发_near_stop"""
        monkeypatch.setattr("trader_shared.config.EXIT_PHASED_ENABLED", False)
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 30
        result = status_layers(
            current=9.36, support=9.4, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.3, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["base_status"] != "冲高减仓"


# ── theory_fusion_conflict ────────────────────────────────────────

class TestTheoryFusionConflict:
    """低置信度冲突标记测试。"""

    def test_low_confidence_reduce_with_neutral_theory_conflict(self):
        """低置信度 + 减仓 + 修复观察 → conflict=True"""
        fusion_result = {"action": "减仓", "confidence": 0.3}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            fusion_result=fusion_result,
        )
        assert result["theory_fusion_conflict"] is True

    def test_low_confidence_empty_stop_with_neutral_theory_conflict(self):
        """低置信度 + 空仓/止损 + 修复观察 → conflict=True"""
        fusion_result = {"action": "空仓/止损", "confidence": 0.4}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            fusion_result=fusion_result,
        )
        assert result["theory_fusion_conflict"] is True

    def test_high_confidence_override_no_conflict(self):
        """高置信度（触发 override）→ conflict=False"""
        fusion_result = {"action": "减仓", "confidence": 0.7}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            fusion_result=fusion_result,
        )
        # 高置信度触发 override，fusion_override_used=True，conflict=False
        assert result["fusion_override_used"] is True
        assert result["theory_fusion_conflict"] is False

    def test_add_action_no_conflict(self):
        """增持动作不触发冲突（只有减仓/空仓类才标记）"""
        fusion_result = {"action": "增持", "confidence": 0.3}
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            fusion_result=fusion_result,
        )
        assert result["theory_fusion_conflict"] is False

    def test_no_fusion_result_no_conflict(self):
        """无 fusion_result → conflict=False"""
        result = status_layers(
            current=10.05, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["theory_fusion_conflict"] is False

    def test_bearish_theory_no_conflict(self):
        """theory_status 已是防守观察（非中性）→ conflict=False"""
        fusion_result = {"action": "减仓", "confidence": 0.3}
        # 价格远低于支撑位，theory_status 会变成 防守观察/暂不碰，非中性
        result = status_layers(
            current=8.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=7.5, position_ratio=0.0, change_pct=0.0,
            ma_values={"ma5": 11.0, "ma10": 12.0, "ma20": 13.0}, pressure_space_pct=0.5,
            fusion_result=fusion_result,
        )
        assert result["theory_fusion_conflict"] is False


# ── P0-2: 假跌破硬性熔断 ────────────────────────────────────────────

class TestHardStopSingleDayDrop:
    """P0-2: 单日跌幅超 7% 时跳过假跌破逻辑，直接返回风险回避。"""

    def test_single_day_drop_7pct_triggers_circuit_breaker(self):
        """change_pct=-7%, 有假跌破形态 → 仍返回"风险回避"（熔断优先于假跌破）"""
        # bars 中有近期收盘 >= hard_stop（假跌破形态）
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5 + [
            {"close": 7.0, "high": 7.5, "low": 6.5}
        ]
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=-7.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        # 单日跌幅 7% 触发硬性熔断，不走假跌破逻辑
        assert result["base_status"] == "风险回避"
        assert result["theory_status"] == "风险回避"
        assert result["status"] == "风险回避"

    def test_single_day_drop_8pct_triggers_circuit_breaker(self):
        """change_pct=-8%, 跌幅更大 → 同样触发熔断"""
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5 + [
            {"close": 7.0, "high": 7.5, "low": 6.5}
        ]
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=-8.5,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["base_status"] == "风险回避"
        assert result["theory_status"] == "风险回避"

    def test_single_day_drop_6pct_no_circuit_breaker(self):
        """change_pct=-6%, 跌幅未达阈值 → 假跌破逻辑正常工作"""
        # bars 中有近期收盘 >= hard_stop（假跌破形态）
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5 + [
            {"close": 7.0, "high": 7.5, "low": 6.5}
        ]
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=-6.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        # 跌幅未达 7%，假跌破逻辑生效 → "防守观察"
        assert result["base_status"] == "防守观察"
        assert result["theory_status"] == "防守观察"

    def test_single_day_drop_exactly_minus_7_boundary(self):
        """change_pct=-7.0, 刚好等于阈值 → 触发熔断"""
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5 + [
            {"close": 7.0, "high": 7.5, "low": 6.5}
        ]
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=-7.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
            bars=bars,
        )
        assert result["theory_status"] == "风险回避"

    def test_circuit_breaker_returns_required_fields(self):
        """熔断返回值包含所有必要字段，向后兼容"""
        bars = [{"close": 10.0, "high": 10.5, "low": 9.5}] * 5
        result = status_layers(
            current=7.0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=-10.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.1,
            bars=bars,
        )
        required_keys = {
            "base_status", "theory_status", "status",
            "fusion_override_used", "trend_ok", "change",
            "below_ma_count", "above_ma5_ma10", "pressure_space_pct",
            "ma250_warning", "ma250",
        }
        assert required_keys.issubset(result.keys())
        assert result["change"] == -10.0
        assert result["fusion_override_used"] is False
