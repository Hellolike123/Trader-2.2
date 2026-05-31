"""structure_core.py 结构分析测试。"""

from __future__ import annotations

import pytest

from trader_shared.structure_core import (
    moving_average,
    moving_averages,
    choose_level,
    add_level,
    average_atr_pct,
    average_amplitude_pct,
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
