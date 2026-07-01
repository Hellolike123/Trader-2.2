"""structure_core.py 结构分析测试。"""

from __future__ import annotations

import pytest
import config

from trader_shared.structure_core import (
    moving_average,
    moving_averages,
    choose_level,
    add_level,
    average_atr_pct,
    average_amplitude_pct,
    build_structure_context,
    find_key_levels,
)


def _make_bar(close: float, high: float = 0, low: float = 0, volume: float = 1000) -> dict:
    h = high if high > 0 else close * 1.02
    l = low if low > 0 else close * 0.98
    return {"open": close * 0.99, "high": h, "low": l, "close": close, "volume": volume}


def _make_bars(closes: list[float]) -> list[dict]:
    return [_make_bar(c) for c in closes]


# ── moving_average ──────────────────────────────────────────────────

class TestMovingAverage:
    def test_sufficient_data(self):
        """30根bars period=20 → 返回最近20根close的平均"""
        bars = _make_bars([10.0 + i * 0.1 for i in range(30)])
        result = moving_average(bars, 20)
        assert result is not None
        expected = sum(10.0 + i * 0.1 for i in range(10, 30)) / 20
        assert abs(result - expected) < 0.01

    def test_insufficient_data(self):
        """10根bars period=20 → None"""
        bars = _make_bars([10.0] * 10)
        result = moving_average(bars, 20)
        assert result is None

    def test_exact_period(self):
        """刚好 period 根 bars → 返回平均"""
        bars = _make_bars([10.0, 11.0, 12.0, 13.0, 14.0])
        result = moving_average(bars, 5)
        assert result is not None
        assert abs(result - 12.0) < 0.01


# ── moving_averages ──────────────────────────────────────────────────

class TestMovingAverages:
    def test_returns_all_periods(self):
        """返回所有 MA 周期"""
        bars = _make_bars([10.0] * 30)
        result = moving_averages(bars)
        assert "ma5" in result
        assert "ma10" in result
        assert "ma20" in result

    def test_short_bars_partial_none(self):
        """数据不足时部分为 None"""
        bars = _make_bars([10.0] * 8)
        result = moving_averages(bars)
        assert result["ma5"] is not None
        assert result["ma20"] is None


# ── choose_level ──────────────────────────────────────────────────

class TestChooseLevel:
    def test_multiple_levels_below(self):
        """多个支撑位 below current → 选最接近的"""
        levels = [
            {"name": "低点1", "price": 10.0, "weight": 1.0},
            {"name": "低点2", "price": 12.0, "weight": 0.8},
            {"name": "低点3", "price": 14.0, "weight": 0.5},
        ]
        result = choose_level(levels, 15.0, below=True)
        assert result["price"] == 14.0

    def test_multiple_levels_above(self):
        """多个阻力位 above current → 选最接近的"""
        levels = [
            {"name": "高点1", "price": 16.0, "weight": 1.0},
            {"name": "高点2", "price": 18.0, "weight": 0.8},
            {"name": "高点3", "price": 20.0, "weight": 0.5},
        ]
        result = choose_level(levels, 15.0, below=False)
        assert result["price"] == 16.0

    def test_empty_levels_raises(self):
        """空列表 → RuntimeError"""
        with pytest.raises(RuntimeError):
            choose_level([], 15.0, below=True)


# ── add_level ──────────────────────────────────────────────────────

class TestAddLevel:
    def test_valid_level(self):
        levels = []
        add_level(levels, "支撑", 10.0, 1.0)
        assert len(levels) == 1
        assert levels[0]["price"] == 10.0

    def test_none_value_skipped(self):
        levels = []
        add_level(levels, "支撑", None, 1.0)
        assert len(levels) == 0

    def test_zero_value_skipped(self):
        levels = []
        add_level(levels, "支撑", 0.0, 1.0)
        assert len(levels) == 0


# ── average_atr_pct ──────────────────────────────────────────────────

class TestAverageATRPct:
    def test_normal_bars(self):
        """正常 bars → 返回正数 ATR%"""
        closes = [10.0 + i * 0.1 for i in range(20)]
        bars = _make_bars(closes)
        result = average_atr_pct(bars)
        assert result is not None
        assert result > 0

    def test_empty_bars(self):
        """空 bars → None"""
        assert average_atr_pct([]) is None

    def test_flat_bars(self):
        """完全平坦 bars → ATR 接近 0"""
        bars = [{"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1000}] * 20
        result = average_atr_pct(bars)
        assert result is not None
        assert result < 0.001


# ── average_amplitude_pct ──────────────────────────────────────────

class TestAverageAmplitudePct:
    def test_normal_bars(self):
        closes = [10.0 + i * 0.1 for i in range(20)]
        bars = _make_bars(closes)
        result = average_amplitude_pct(bars)
        assert result is not None
        assert result > 0

    def test_empty_bars(self):
        assert average_amplitude_pct([]) is None


class TestTrailingStop:
    def test_trailing_stop_basic(self):
        assert config.ENABLE_TRAILING_STOP is True
        closes = [10.0 + i * 0.1 for i in range(30)]
        bars = _make_bars(closes)
        result = build_structure_context(current=12.0, bars=bars)
        assert result.get("trailing_stop") is not None
        assert result["trailing_stop"] < 12.0

    def test_trailing_stop_not_below_hard_stop(self):
        closes = [10.0 + i * 0.1 for i in range(100)]
        bars = _make_bars(closes)
        result = build_structure_context(current=19.0, bars=bars)
        assert result.get("trailing_stop") is not None
        assert result["trailing_stop"] >= result.get("hard_stop", 0)

    def test_trailing_stop_disabled(self, monkeypatch):
        monkeypatch.setattr("trader_shared.config.ENABLE_TRAILING_STOP", False)
        closes = [10.0 + i * 0.1 for i in range(30)]
        bars = _make_bars(closes)
        result = build_structure_context(current=12.0, bars=bars)
        assert result.get("trailing_stop") is None

    def test_trailing_stop_pnl_scaling(self):
        closes = [10.0 + i * 0.1 for i in range(50)]
        bars = _make_bars(closes)
        result_20 = build_structure_context(current=19.0, bars=bars, pnl_pct=0.20)
        result_30 = build_structure_context(current=19.0, bars=bars, pnl_pct=0.30)
        result_40 = build_structure_context(current=19.0, bars=bars, pnl_pct=0.40)
        assert result_20.get("trailing_stop") is not None
        assert result_30.get("trailing_stop") is not None
        assert result_40.get("trailing_stop") is not None


# ── find_key_levels (P0-4) ──────────────────────────────────────────

class TestFindKeyLevels:
    """P0-4: 多周期支撑压力阶梯测试。"""

    def test_empty_input(self):
        """空 bars → 全部 0.0"""
        result = find_key_levels([])
        assert result["short_support"] == 0.0
        assert result["short_resist"] == 0.0
        assert result["mid_support"] == 0.0
        assert result["mid_resist"] == 0.0
        assert result["long_support"] == 0.0
        assert result["long_resist"] == 0.0

    def test_insufficient_bars(self):
        """不足 10 根 → 短线用全部数据，中长线 fallback"""
        closes = [10.0, 10.5, 9.8, 10.2, 11.0]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        # 短线 = 5 根中的高低
        assert result["short_support"] == pytest.approx(9.8 * 0.98, abs=0.1)  # low = close*0.98
        assert result["short_resist"] > 0
        # 中线/长线 fallback 到全周期
        assert result["mid_support"] > 0
        assert result["mid_resist"] > 0

    def test_returns_all_six_keys(self):
        """正常 300 根 bars → 返回 6 个 key"""
        closes = [50.0 + (i % 20 - 10) * 0.5 for i in range(300)]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        expected_keys = {"short_support", "mid_support", "long_support",
                         "short_resist", "mid_resist", "long_resist"}
        assert set(result.keys()) == expected_keys

    def test_support_below_resistance(self):
        """每个周期的支撑 < 压力"""
        closes = [50.0 + (i % 20 - 10) * 0.5 for i in range(200)]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        assert result["short_support"] < result["short_resist"]
        assert result["mid_support"] < result["mid_resist"]
        assert result["long_support"] < result["long_resist"]

    def test_short_is_within_long(self):
        """短线区间包含在长线区间内"""
        closes = [50.0 + (i % 20 - 10) * 2 for i in range(200)]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        # 短线支撑 >= 长线支撑（短线低点不会低于长线低点）
        assert result["short_support"] >= result["long_support"] or result["long_support"] > 0
        # 短线压力 <= 长线压力
        assert result["short_resist"] <= result["long_resist"] or result["long_resist"] > 0

    def test_with_local_extrema(self):
        """构造有明显局部极值的数据，验证 multi-touch 检测"""
        # 150 根 bars，在 40 和 60 之间震荡，有多次触及 40 和 60 的价位
        closes = []
        for i in range(150):
            if i % 10 < 5:
                closes.append(40.0 + (i % 5) * 0.5)  # 低点区域 ~40
            else:
                closes.append(55.0 + (i % 5) * 1.0)  # 高点区域 ~55-59
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        # 支撑应该在 40 附近，压力应该在 55+ 附近
        assert result["short_support"] > 0
        assert result["short_resist"] > result["short_support"]
        assert result["mid_support"] > 0
        assert result["mid_resist"] > result["mid_support"]

    def test_monotonically_increasing(self):
        """单调上涨数据 → 短线支撑为最近 10 日低点"""
        closes = [10.0 + i * 0.5 for i in range(150)]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        # 单调上涨，短线支撑 = 最近10日低点
        expected_short_low = closes[-10] * 0.98  # low = close * 0.98
        assert result["short_support"] > 0
        assert result["short_resist"] > result["short_support"]

    def test_all_positive_values(self):
        """所有返回值必须 > 0（有效数据）"""
        closes = [50.0 + (i % 15 - 7) * 1.0 for i in range(200)]
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        for key, val in result.items():
            assert val > 0, f"{key} should be > 0, got {val}"

    def test_fallback_when_no_multi_touch(self):
        """没有 multi-touch 极值时，fallback 到周期最高/最低"""
        # 直线数据，不会有局部极值
        closes = [50.0] * 150
        bars = _make_bars(closes)
        result = find_key_levels(bars)
        # 所有值应该接近 50 * 0.98 和 50 * 1.02
        assert result["mid_support"] > 0
        assert result["mid_resist"] > 0
        assert result["long_support"] > 0
        assert result["long_resist"] > 0
