from __future__ import annotations

import sys

for mod in ("trader_shared.chan_core", "light_data"):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.chan_core import (
    handle_inclusion,
    find_fractions,
    build_strokes,
    build_segments,
    build_zones,
    classify_structure,
    detect_buy_points,
    detect_divergence,
    chanlun_analysis,
    chanlun_strategy,
    _check_macd_for_2nd_buy,
    _aggregate_bars,
    _higher_level_trend,
    _merge_zones,
    _chan_type_canonical,
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


class TestBuildSegments:
    """build_segments 测试。"""

    def test_insufficient_strokes(self):
        """不足 3 笔返回空。"""
        strokes = [
            {"direction": "up", "start_price": 10, "end_price": 20},
            {"direction": "down", "start_price": 20, "end_price": 15},
        ]
        assert build_segments(strokes) == []

    def test_minimal_up_segment(self):
        """3 笔构成最小向上线段（上-下-上）。"""
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},
            {"direction": "down", "start_price": 20, "end_price": 15},
            {"direction": "up",   "start_price": 15, "end_price": 25},
        ]
        segs = build_segments(strokes, min_strokes=3)
        assert len(segs) == 1
        assert segs[0]["direction"] == "up"
        assert segs[0]["start_price"] == 10
        assert segs[0]["end_price"] == 25
        assert segs[0]["strokes_count"] == 3

    def test_minimal_down_segment(self):
        """3 笔构成最小向下线段（下-上-下）。"""
        strokes = [
            {"direction": "down", "start_price": 20, "end_price": 10},
            {"direction": "up",   "start_price": 10, "end_price": 15},
            {"direction": "down", "start_price": 15, "end_price": 8},
        ]
        segs = build_segments(strokes, min_strokes=3)
        assert len(segs) == 1
        assert segs[0]["direction"] == "down"
        assert segs[0]["start_price"] == 20
        assert segs[0]["end_price"] == 8

    def test_segment_termination(self):
        """特征序列反转导致线段终结。"""
        # 向上线段：特征序列取向下笔低点
        # 第1根向下笔低点=15，第2根向下笔低点=13 < 15 → 终结
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},  # 0
            {"direction": "down", "start_price": 20, "end_price": 15},  # 1
            {"direction": "up",   "start_price": 15, "end_price": 25},  # 2
            {"direction": "down", "start_price": 25, "end_price": 13},  # 3 — 低点13 < 15 → 终结
            {"direction": "up",   "start_price": 13, "end_price": 18},  # 4
        ]
        segs = build_segments(strokes, min_strokes=3)
        # 应该有2段：第1段终结于笔2，第2段从笔2开始
        assert len(segs) >= 2
        assert segs[0]["direction"] == "up"
        assert segs[0]["end_index"] == 2
        assert segs[1]["direction"] == "down"

    def test_multiple_segments(self):
        """多段线段正确分割。"""
        # 向上线段 1: up(10→20), down(20→15), up(15→25)
        # 终结: down(25→14) 低点14 < 15
        # 向下线段 2: down(25→14), up(14→18), down(18→12)
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},
            {"direction": "down", "start_price": 20, "end_price": 15},
            {"direction": "up",   "start_price": 15, "end_price": 25},
            {"direction": "down", "start_price": 25, "end_price": 14},
            {"direction": "up",   "start_price": 14, "end_price": 18},
            {"direction": "down", "start_price": 18, "end_price": 12},
        ]
        segs = build_segments(strokes, min_strokes=3)
        assert len(segs) >= 2
        assert segs[0]["direction"] == "up"
        assert segs[1]["direction"] == "down"


class TestClassifyStructure:
    """classify_structure 测试。"""

    def _make_strokes(self, n=6):
        """生成 n 笔交替的测试数据。"""
        strokes = []
        for i in range(n):
            if i % 2 == 0:
                strokes.append({"direction": "up", "start_price": 10.0, "end_price": 15.0})
            else:
                strokes.append({"direction": "down", "start_price": 15.0, "end_price": 10.0})
        return strokes

    def test_no_zones_no_strokes(self):
        """0 中枢 0 笔 → 无结构。"""
        result = classify_structure([], strokes=[])
        assert result["structure_type"] == "无结构"

    def test_no_zones_insufficient_segments(self):
        """0 中枢有笔但线段不足 → 线段不足X/5。"""
        strokes = self._make_strokes(6)
        result = classify_structure([], segments=[{"direction": "up"}], strokes=strokes)
        assert "线段不足" in result["structure_type"]

    def test_insufficient_segments_for_consolidation(self):
        """1 中枢但线段不足 5 → 线段不足3/5。"""
        zones = [{"zh_top": 20.0, "zh_bottom": 15.0, "valid": True}]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=[{}, {}, {}], strokes=strokes)
        assert result["structure_type"] == "线段不足3/5"
        assert result["structure_zones_count"] == 1

    def test_consolidation(self):
        """1 中枢 + 5 段线段 → 盘整。"""
        zones = [{"zh_top": 20.0, "zh_bottom": 15.0, "valid": True}]
        segs = [{"direction": "up"} for _ in range(5)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "盘整"
        assert result["structure_zones_count"] == 1

    def test_insufficient_segments_for_trend(self):
        """2 个递增中枢但线段不足 11 → 线段不足5/11。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(5)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "线段不足5/11"

    def test_uptrend(self):
        """2 个递增中枢 + 11 段线段 → 上涨趋势。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(11)]
        strokes = self._make_strokes(12)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "上涨趋势"
        assert result["structure_zones_count"] == 2

    def test_downtrend(self):
        """2 个递减中枢 + 11 段线段 → 下跌趋势。"""
        zones = [
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
        ]
        segs = [{"direction": "down"} for _ in range(11)]
        strokes = self._make_strokes(12)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "下跌趋势"
        assert result["structure_zones_count"] == 2


class TestChanlunAnalysisIntegration:
    """chanlun_analysis 集成测试：验证新增字段。"""

    def test_full_pipeline_has_segments(self):
        """验证 chanlun_analysis 返回 segments 和 structure_type 字段。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        assert "segments" in result
        assert "segments_count" in result
        assert "structure_type" in result
        assert "structure_segments_count" in result
        assert isinstance(result["segments"], list)
        assert isinstance(result["segments_count"], int)

    def test_backward_compat_fields(self):
        """验证所有旧字段仍然存在。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        legacy_fields = [
            "strokes", "zones", "buy_points", "sell_points",
            "trend_label", "buy_point_text", "sell_point_text",
            "strokes_count", "zones_count", "divergence",
            "last_valid_zone_last_price", "last_valid_zone_first_price",
        ]
        for field in legacy_fields:
            assert field in result, f"缺少旧字段: {field}"

    def test_new_enhancement_fields(self):
        """验证 E1-E3 新增字段存在且类型正确。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        # E3: fractions
        assert "fractions" in result
        assert isinstance(result["fractions"], list)
        # E1: higher_trend
        assert "higher_trend" in result
        assert "higher_trend_conflict" in result
        assert isinstance(result["higher_trend_conflict"], bool)
        # E2: merged_zones / pivot_count
        assert "merged_zones" in result
        assert isinstance(result["merged_zones"], list)
        assert "pivot_count" in result
        assert isinstance(result["pivot_count"], int)


class TestAggregateBars:
    """E1: 粗K线聚合测试。"""

    def test_basic_aggregation(self):
        bars = [_make_bar(10 + i, 11 + i, 9 + i, 10.5 + i) for i in range(10)]
        result = _aggregate_bars(bars, chunk=5)
        assert len(result) == 2
        # 第 1 组: open=10, high=max(11..15)=15, low=min(9..13)=9, close=14.5
        assert result[0]["high"] == 15
        assert result[0]["low"] == 9
        assert result[0]["open"] == 10
        assert result[0]["close"] == 14.5

    def test_short_series(self):
        bars = [_make_bar(10, 11, 9, 10) for _ in range(3)]
        result = _aggregate_bars(bars, chunk=5)
        assert len(result) == 3  # chunk > len → return copy

    def test_chunk_1(self):
        bars = [_make_bar(10, 11, 9, 10) for _ in range(5)]
        result = _aggregate_bars(bars, chunk=1)
        assert len(result) == 5


class TestHigherLevelTrend:
    """E1: 上级别趋势估计测试。"""

    def test_short_series_returns_none(self):
        bars = [_make_bar(10, 11, 9, 10) for _ in range(5)]
        result = _higher_level_trend(bars, chunk=5)
        assert result["trend"] is None
        assert result["confidence"] == 0.0

    def test_result_has_keys(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(50)]
        result = _higher_level_trend(bars, chunk=5)
        assert "trend" in result
        assert "confidence" in result
        assert "segments_count" in result

    def test_not_downweight_when_none(self):
        """higher_trend=None 时不得抑制买点。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        assert result["higher_trend"] is None or result["higher_trend_conflict"] is False


class TestBuildZonesMerge:
    """E2: 中枢合并测试。"""

    def test_single_zone_no_merge(self):
        strokes = [
            {"start_price": 10, "end_price": 50, "direction": "up"},
            {"start_price": 50, "end_price": 30, "direction": "down"},
            {"start_price": 30, "end_price": 60, "direction": "up"},
        ]
        raw = build_zones(strokes, merge=False)
        merged = build_zones(strokes, merge=True)
        assert len(raw) == 1
        assert len(merged) == 1
        assert merged[0]["valid"] is True

    def test_overlapping_zones_merge(self):
        """两个重叠的滑动窗口中枢应合并为 1 个。"""
        # 5 个 items → 滑动窗口产生 3 个 raw zones（重叠）
        items = [
            {"start_price": 10, "end_price": 30, "direction": "up"},
            {"start_price": 30, "end_price": 15, "direction": "down"},
            {"start_price": 15, "end_price": 35, "direction": "up"},
            {"start_price": 35, "end_price": 18, "direction": "down"},
            {"start_price": 18, "end_price": 40, "direction": "up"},
        ]
        raw = build_zones(items, merge=False)
        merged = build_zones(items, merge=True)
        assert len(raw) >= 2  # 至少 2 个 raw zones
        assert len(merged) == 1  # 合并为 1 个
        assert "members" in merged[0]

    def test_merge_disabled(self):
        items = [
            {"start_price": 10, "end_price": 30, "direction": "up"},
            {"start_price": 30, "end_price": 15, "direction": "down"},
            {"start_price": 15, "end_price": 35, "direction": "up"},
            {"start_price": 35, "end_price": 18, "direction": "down"},
            {"start_price": 18, "end_price": 40, "direction": "up"},
        ]
        import trader_shared.chan_core as cc
        orig = cc.CHAN_ZONE_MERGE_ENABLED
        try:
            cc.CHAN_ZONE_MERGE_ENABLED = False
            result = build_zones(items, merge=True)
            assert len(result) >= 2  # 不合并
        finally:
            cc.CHAN_ZONE_MERGE_ENABLED = orig


class TestClassifyStructureMerged:
    """E2: 基于合并中枢的拓扑分类测试。"""

    def test_merged_zones_pivot_count_present(self):
        zones = [{"zh_top": 20.0, "zh_bottom": 15.0, "valid": True}]
        result = classify_structure(zones, segments=[{"direction": "up"} for _ in range(5)],
                                    strokes=[{"direction": "up", "start_price": 10, "end_price": 15} for _ in range(6)])
        assert "merged_zones" in result
        assert "pivot_count" in result
        assert result["pivot_count"] == 1

    def test_structure_zones_count_raw(self):
        """structure_zones_count 应等于输入 zones 长度（原始数量）。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        result = classify_structure(zones, segments=[{"direction": "up"} for _ in range(11)],
                                    strokes=[{"direction": "up", "start_price": 10, "end_price": 15} for _ in range(12)])
        assert result["structure_zones_count"] == 2


class TestFractionsBugFix:
    """E3: fractions 暴露 + _find_pivot_index 修复测试。"""

    def test_chanlun_analysis_returns_fractions(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        assert "fractions" in result
        assert isinstance(result["fractions"], list)

    def test_fractions_have_type(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        for frac in result["fractions"]:
            assert "type" in frac
            assert frac["type"] in ("top", "bottom")


class TestSignalIdStandardization:
    """E4: 买卖点信号标准化测试。"""

    def test_signal_id_added_when_symbol_date_present(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5, symbol="688248.SH", analysis_date="2026-07-07")
        for bp in result["buy_points"]:
            assert "signal_id" in bp
            assert isinstance(bp["signal_id"], str)
            assert len(bp["signal_id"]) == 16
        for sp in result["sell_points"]:
            assert "signal_id" in sp
            assert isinstance(sp["signal_id"], str)

    def test_no_signal_id_when_missing_symbol(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        for bp in result["buy_points"]:
            assert "signal_id" not in bp or bp.get("signal_id") is None

    def test_signal_id_stable_across_runs(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        r1 = chanlun_analysis(bars, 10.5, symbol="688248.SH", analysis_date="2026-07-07")
        r2 = chanlun_analysis(bars, 10.5, symbol="688248.SH", analysis_date="2026-07-07")
        ids1 = [bp.get("signal_id") for bp in r1["buy_points"]]
        ids2 = [bp.get("signal_id") for bp in r2["buy_points"]]
        assert ids1 == ids2

    def test_chanlun_strategy_derives_from_quote(self):
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        quote = {"symbol": "688248.SH", "trade_date": "2026-07-07"}
        result = chanlun_strategy(10.5, bars, quote=quote)
        chan = result["chanlun"]
        has_id = any(bp.get("signal_id") for bp in chan["buy_points"]) or any(sp.get("signal_id") for sp in chan["sell_points"])
        assert has_id or chan["buy_points"] == []  # 有买卖点时应有 id


class TestChanTypeCanonical:
    """E4: _chan_type_canonical 映射测试。"""

    def test_buy_types(self):
        assert _chan_type_canonical("一类买") == "chan_buy_1"
        assert _chan_type_canonical("二类买") == "chan_buy_2"
        assert _chan_type_canonical("三类买") == "chan_buy_3"

    def test_sell_types(self):
        assert _chan_type_canonical("一类卖") == "chan_sell_1"
        assert _chan_type_canonical("二类卖") == "chan_sell_2"
        assert _chan_type_canonical("三类卖") == "chan_sell_3"

    def test_unknown_passthrough(self):
        assert _chan_type_canonical("未知类型") == "未知类型"
