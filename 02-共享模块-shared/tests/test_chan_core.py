from __future__ import annotations

import sys

for mod in ("trader_shared.chan_core", "light_data"):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.chan_core import (
    handle_inclusion,
    find_fractions,
    build_strokes,
    build_zones,
    detect_buy_points,
    detect_divergence,
    chanlun_analysis,
    _check_macd_for_2nd_buy,
)


def _make_bar(open_, high, low, close, volume=1000):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


class TestHandleInclusion:
    def test_inclusion_up(self):
        bars = [
            _make_bar(10, 12, 10, 11),
            _make_bar(11, 14, 9, 13),
        ]
        result = handle_inclusion(bars)
        assert len(result) == 1
        assert result[0]["high"] == 14
        assert result[0]["low"] == 9

    def test_no_inclusion(self):
        bars = [
            _make_bar(10, 12, 10, 11),
            _make_bar(11, 13, 11, 12),
        ]
        result = handle_inclusion(bars)
        assert len(result) == 2

    def test_inclusion_recursive(self):
        bars = [
            _make_bar(20, 20, 10, 15),   # A
            _make_bar(21, 22, 12, 21),   # B — does not contain A
            _make_bar(12, 23, 11, 12),   # C — contains B, direction=up
            _make_bar(9, 24, 9, 10),     # D — contains merged BC, direction=up
        ]
        result = handle_inclusion(bars)
        assert len(result) == 2
        assert result[1]["high"] == 24
        assert result[1]["low"] == 12


class TestFindFractions:
    def test_top_fraction(self):
        bars = [
            _make_bar(9, 10, 8, 9),
            _make_bar(13, 15, 12, 14),
            _make_bar(12, 13, 11, 12),
        ]
        result = find_fractions(bars)
        assert len(result) == 1
        assert result[0]["type"] == "top"

    def test_bottom_fraction(self):
        bars = [
            _make_bar(13, 14, 11, 13),
            _make_bar(9, 10, 8, 9),
            _make_bar(11, 12, 10, 11),
        ]
        result = find_fractions(bars)
        assert len(result) == 1
        assert result[0]["type"] == "bottom"

    def test_no_fraction(self):
        bars = [
            _make_bar(9, 10, 8, 9),
            _make_bar(11, 12, 10, 11),
            _make_bar(13, 14, 12, 13),
        ]
        result = find_fractions(bars)
        assert len(result) == 0


class TestBuildStrokes:
    def test_stroke_up(self):
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 4, "high": 15.0, "low": 14.5, "close": 14.8},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 1
        assert result[0]["direction"] == "up"
        assert result[0]["start_type"] == "bottom"
        assert result[0]["end_type"] == "top"

    def test_stroke_down(self):
        fractions = [
            {"type": "top", "index": 0, "high": 15.0, "low": 14.5, "close": 14.8},
            {"type": "bottom", "index": 4, "low": 10.0, "high": 10.5, "close": 10.2},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 1
        assert result[0]["direction"] == "down"
        assert result[0]["start_type"] == "top"
        assert result[0]["end_type"] == "bottom"

    def test_insufficient_fractions(self):
        fractions = [{"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2}]
        result = build_strokes(fractions)
        assert len(result) == 0


class TestBuildZones:
    def test_zone_valid(self):
        strokes = [
            {"start_price": 10, "end_price": 50, "direction": "up"},
            {"start_price": 50, "end_price": 30, "direction": "down"},
            {"start_price": 30, "end_price": 60, "direction": "up"},
        ]
        result = build_zones(strokes)
        assert len(result) == 1
        assert result[0]["valid"] is True
        assert result[0]["zh_top"] > result[0]["zh_bottom"]

    def test_zone_nonoverlapping(self):
        strokes = [
            {"start_price": 10, "end_price": 50, "direction": "up"},
            {"start_price": 50, "end_price": 50, "direction": "down"},
            {"start_price": 50, "end_price": 80, "direction": "up"},
        ]
        result = build_zones(strokes)
        assert len(result) == 0


class TestDetectBuyPoints:
    def test_buy_point_1(self):
        strokes = [{"direction": "down", "end_price": 10.0}]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0, macd_hist_current=-0.5, macd_hist_prev=-1.0)
        types = [bp["type"] for bp in result]
        assert "一类买" in types

    def test_buy_point_2(self):
        strokes = [
            {"direction": "down", "end_price": 8.0},
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.0},
        ]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0, macd_divergence_ok=True)
        types = [bp["type"] for bp in result]
        assert "二类买" in types

    def test_buy_point_2_requires_macd_divergence(self):
        """二类买点需要 MACD 确认，否则不触发。"""
        strokes = [
            {"direction": "down", "end_price": 8.0},
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.0},
        ]
        zones = []
        # macd_divergence_ok defaults to False → should NOT trigger 二类买
        result = detect_buy_points(strokes, zones, 10.0)
        types = [bp["type"] for bp in result]
        assert "二类买" not in types

    def test_buy_point_3(self):
        strokes = [{"direction": "up", "end_price": 11.0}]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.15)
        types = [bp["type"] for bp in result]
        assert "三类买" in types


class TestCheckMacdFor2ndBuy:
    """_check_macd_for_2nd_buy 函数测试。"""

    def _make_bars_with_macd(self, macd_values, closes=None):
        """Helper: create bars with macd_histogram and optional close values."""
        bars = []
        for i, macd in enumerate(macd_values):
            bar = {"macd_histogram": macd, "close": closes[i] if closes else 10.0 + i * 0.1}
            bars.append(bar)
        return bars

    def test_empty_bars_returns_false(self):
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy([], strokes) is False

    def test_empty_strokes_returns_false(self):
        bars = self._make_bars_with_macd([-1.0] * 15)
        assert _check_macd_for_2nd_buy(bars, []) is False

    def test_insufficient_down_strokes_returns_false(self):
        bars = self._make_bars_with_macd([-1.0] * 15)
        strokes = [{"direction": "down", "end_price": 8.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is False

    def test_insufficient_macd_data_returns_false(self):
        bars = self._make_bars_with_macd([-1.0] * 5)  # < 10
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is False

    def test_macd_divergence_detected(self):
        """MACD 底背驰：最近5根柱状线最小值比前面5根高（更浅）。"""
        # earlier: -2.0, -1.8, -1.5, -1.3, -1.0 (min = -2.0)
        # recent:  -1.5, -1.2, -1.0, -0.8, -0.5 (min = -1.5, which is > -2.0 and < 0)
        macd_values = [-2.0, -1.8, -1.5, -1.3, -1.0, -1.5, -1.2, -1.0, -0.8, -0.5]
        bars = self._make_bars_with_macd(macd_values)
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is True

    def test_macd_recovery_detected(self):
        """MACD 止跌：最后3根柱状线都为负但逐步回升。"""
        # last 3: -1.0, -0.8, -0.5 (all negative, last > first)
        macd_values = [-2.0, -1.8, -1.5, -1.3, -1.2, -1.1, -1.0, -0.9, -0.8, -0.5]
        bars = self._make_bars_with_macd(macd_values)
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is True

    def test_bearish_alignment_rejects(self):
        """空头排列（所有收盘价低于MA5/MA10/MA20）→ 拒绝二类买。"""
        # MACD shows divergence, but closes are all below MAs
        macd_values = [-2.0, -1.8, -1.5, -1.3, -1.0, -1.5, -1.2, -1.0, -0.8, -0.5]
        # Create 30 bars with declining closes (all below MAs)
        closes = [20.0 - i * 0.5 for i in range(30)]  # 20.0, 19.5, 19.0, ... → downtrend
        bars = self._make_bars_with_macd(macd_values * 3, closes)
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is False

    def test_no_macd_data_returns_false(self):
        """没有 macd_histogram 数据 → False。"""
        bars = [{"close": 10.0 + i} for i in range(15)]
        strokes = [{"direction": "down", "end_price": 8.0}, {"direction": "down", "end_price": 9.0}]
        assert _check_macd_for_2nd_buy(bars, strokes) is False


class TestDetectDivergence:
    def test_divergence_top(self):
        bars = [
            {"high": 10, "low": 8, "macd_histogram": 0.5},
            {"high": 11, "low": 9, "macd_histogram": 1.0},
            {"high": 12, "low": 10, "macd_histogram": 2.0},
            {"high": 9, "low": 7, "macd_histogram": 1.0},
            {"high": 14, "low": 12, "macd_histogram": 1.0},
            {"high": 13, "low": 11, "macd_histogram": 0.5},
            {"high": 12, "low": 10, "macd_histogram": 0.3},
        ]
        result = detect_divergence(bars)
        assert result["top_divergence"] is True

    def test_divergence_bottom(self):
        bars = [
            {"high": 12, "low": 10, "macd_histogram": -0.5},
            {"high": 11, "low": 9, "macd_histogram": -1.0},
            {"high": 10, "low": 8, "macd_histogram": -2.0},
            {"high": 10, "low": 9, "macd_histogram": -1.5},
            {"high": 11, "low": 6, "macd_histogram": -1.0},
            {"high": 12, "low": 7, "macd_histogram": -0.5},
            {"high": 13, "low": 8, "macd_histogram": -0.3},
        ]
        result = detect_divergence(bars)
        assert result["bottom_divergence"] is True


class TestChanlunAnalysis:
    def test_api_empty(self):
        result = chanlun_analysis([], 10.0)
        assert result == {}

    def test_insufficient_bars(self):
        bars = [_make_bar(10, 12, 10, 11) for _ in range(19)]
        result = chanlun_analysis(bars, 10.0)
        assert result == {}

    def test_macd_written_back_to_bars(self):
        """_calc_macd 应将 MACD 写回 bars（macd_histogram 字段）。"""
        from trader_shared.chan_core import _calc_macd
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = _calc_macd(bars)
        has_macd = any(b.get("macd_histogram") is not None for b in result)
        assert has_macd is True, "MACD histogram should be written to returned bars"

    def test_macd_available_for_divergence(self):
        """MACD 透传后，背驰检测应能读到 macd_histogram。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        assert "divergence" in result
        assert "top_divergence" in result["divergence"]
        assert "bottom_divergence" in result["divergence"]
