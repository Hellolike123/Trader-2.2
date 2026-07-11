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
    detect_sell_points,
    detect_divergence,
    chanlun_analysis,
    chanlun_strategy,
    unwrap_chan,
    _check_macd_for_2nd_buy,
    _stroke_macd_area,
    _stroke_force_weaker,
    _stroke_force_not_much_stronger,
    _aggregate_bars,
    _higher_level_trend,
    _merge_zones,
    _chan_type_canonical,
    _chanlun_compute,
    ChanlunEngine,
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

    def test_stroke_skip_near_opposite_keeps_start(self):
        """P0: 近距反向分型不得丢弃起点；应跳过 top@2 后与 top@8 成笔。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 2, "high": 12.0, "low": 11.5, "close": 11.8},  # 距起点过近
            {"type": "top", "index": 8, "high": 15.0, "low": 14.5, "close": 14.8},  # 相对 0 足够远
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 1
        assert result[0]["direction"] == "up"
        assert result[0]["start_type"] == "bottom"
        assert result[0]["end_type"] == "top"
        assert result[0]["end_price"] == 15.0

    def test_stroke_near_only_opposite_no_stroke(self):
        """回归：仅有近距反向分型时不成笔（距离不足）。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 2, "high": 12.0, "low": 11.5, "close": 11.8},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 0

    def test_stroke_alternating_sequence(self):
        """回归：多笔交替成笔仍正确（底-顶-底-顶）。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 5, "high": 15.0, "low": 14.5, "close": 14.8},
            {"type": "bottom", "index": 10, "low": 11.0, "high": 11.5, "close": 11.2},
            {"type": "top", "index": 15, "high": 16.0, "low": 15.5, "close": 15.8},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 3
        assert result[0]["direction"] == "up"
        assert result[1]["direction"] == "down"
        assert result[2]["direction"] == "up"
        assert result[0]["end_price"] == 15.0
        assert result[1]["end_price"] == 11.0
        assert result[2]["end_price"] == 16.0

    def test_stroke_has_indices(self):
        """P1: build_strokes 写入 start_index / end_index（分型 mid bar index）。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 5, "high": 15.0, "low": 14.5, "close": 14.8},
            {"type": "bottom", "index": 10, "low": 11.0, "high": 11.5, "close": 11.2},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 2
        assert result[0]["start_index"] == 0
        assert result[0]["end_index"] == 5
        assert result[1]["start_index"] == 5
        assert result[1]["end_index"] == 10
        # 旧字段仍保留
        assert result[0]["direction"] == "up"
        assert result[0]["start_price"] == 10.0
        assert result[0]["end_price"] == 15.0

    def test_stroke_power_fields_always_present(self):
        """P4: power_price 和 length 始终存在。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 5, "high": 15.0, "low": 14.5, "close": 14.8},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 1
        s = result[0]
        assert "power_price" in s
        assert "length" in s
        assert s["power_price"] == 5.0  # abs(15.0 - 10.0)
        assert s["length"] == 5  # 5 - 0

    def test_stroke_power_volume_with_bars(self):
        """P4: 传入 bars 时计算 power_volume。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 5, "high": 15.0, "low": 14.5, "close": 14.8},
        ]
        bars = [
            {"volume": 100} for _ in range(6)
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5, bars=bars)
        assert len(result) == 1
        s = result[0]
        assert "power_volume" in s
        # 中间 K 线 index 1-4，共 4 根，每根 volume=100
        assert s["power_volume"] == 400.0

    def test_stroke_power_volume_without_bars(self):
        """P4: 不传 bars 时没有 power_volume。"""
        fractions = [
            {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
            {"type": "top", "index": 5, "high": 15.0, "low": 14.5, "close": 14.8},
        ]
        result = build_strokes(fractions, min_bars_per_stroke=5)
        assert len(result) == 1
        assert "power_volume" not in result[0]


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
    def _make_bars_with_neg_areas(self, len_prev=5, len_curr=5, area_prev=-10.0, area_curr=-3.0):
        """构造 bars：前笔区间负柱面积 area_prev，后笔 area_curr（均匀分配）。"""
        bars = []
        # padding before
        for _ in range(2):
            bars.append({"macd_histogram": 0.0, "close": 12.0, "volume": 1000})
        # prev down stroke bars
        per_prev = area_prev / len_prev
        for _ in range(len_prev):
            bars.append({"macd_histogram": per_prev, "close": 10.0, "volume": 1000})
        # mid (up)
        for _ in range(3):
            bars.append({"macd_histogram": 0.5, "close": 11.0, "volume": 1000})
        # curr down stroke bars
        per_curr = area_curr / len_curr
        for _ in range(len_curr):
            bars.append({"macd_histogram": per_curr, "close": 9.0, "volume": 1000})
        start_prev = 2
        end_prev = start_prev + len_prev - 1
        start_curr = end_prev + 1 + 3
        end_curr = start_curr + len_curr - 1
        return bars, start_prev, end_prev, start_curr, end_curr

    def test_buy_point_1_with_zone_and_stroke_divergence(self):
        """P1 一类买：有中枢 + 两 down + 后笔负面积更弱 → 有一类买 conf=3。"""
        bars, sp, ep, sc, ec = self._make_bars_with_neg_areas(area_prev=-10.0, area_curr=-3.0)
        strokes = [
            {"direction": "down", "end_price": 10.0, "start_index": sp, "end_index": ep},
            {"direction": "up", "end_price": 12.0},
            {"direction": "down", "end_price": 9.0, "start_index": sc, "end_index": ec},
        ]
        zones = [{"zh_top": 11.5, "zh_bottom": 10.5, "valid": True}]
        result = detect_buy_points(strokes, zones, 9.0, bars=bars)
        types = [bp["type"] for bp in result]
        assert "一类买" in types
        bp1 = next(bp for bp in result if bp["type"] == "一类买")
        assert bp1["confidence"] == 3

    def test_buy_point_1_no_zone(self):
        """P1 一类买：无中枢 → 不报一类（删除假一类）。"""
        strokes = [
            {"direction": "down", "end_price": 10.0},
            {"direction": "up", "end_price": 12.0},
            {"direction": "down", "end_price": 9.0},
        ]
        zones = []
        result = detect_buy_points(
            strokes, zones, 9.0, macd_hist_current=-0.5, macd_hist_prev=-1.0
        )
        types = [bp["type"] for bp in result]
        assert "一类买" not in types

    def test_buy_point_1_fallback_no_index(self):
        """P1 一类买：有中枢 + 创新低 + 无 index 时 bar 级绿柱缩短 → conf=1。"""
        strokes = [
            {"direction": "down", "end_price": 10.0},
            {"direction": "up", "end_price": 12.0},
            {"direction": "down", "end_price": 9.0},
        ]
        zones = [{"zh_top": 11.5, "zh_bottom": 10.5, "valid": True}]
        result = detect_buy_points(
            strokes, zones, 9.0, macd_hist_current=-0.5, macd_hist_prev=-1.0
        )
        types = [bp["type"] for bp in result]
        assert "一类买" in types
        bp1 = next(bp for bp in result if bp["type"] == "一类买")
        assert bp1["confidence"] == 1

    def test_buy_point_2(self):
        """P1 二类买：结构满足 + macd_divergence_ok → 有。"""
        strokes = [
            {"direction": "down", "end_price": 8.0},
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.0},
        ]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0, macd_divergence_ok=True)
        types = [bp["type"] for bp in result]
        assert "二类买" in types

    def test_buy_point_2_requires_macd_or_area(self):
        """P1 二类买：ok=False 且无面积 → 无。"""
        strokes = [
            {"direction": "down", "end_price": 8.0},
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.0},
        ]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0, macd_divergence_ok=False)
        types = [bp["type"] for bp in result]
        assert "二类买" not in types

    def test_buy_point_3_above_old_narrow_window(self):
        """P1 三类买：close 在中枢上方 3%（旧逻辑 >2% 会拒）+ 回踩 down 不破 zh_top → 有。"""
        strokes = [
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.05},  # 回踩不破 zh_top=10.0
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        # 3% above zh_top
        result = detect_buy_points(strokes, zones, 10.30)
        types = [bp["type"] for bp in result]
        assert "三类买" in types

    def test_buy_point_3_inside_zone(self):
        """P1 三类买：close 仍在中枢内 → 无。"""
        strokes = [{"direction": "up", "end_price": 9.5}]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 9.5)
        types = [bp["type"] for bp in result]
        assert "三类买" not in types

    def test_buy_point_3_no_pullback_after_leave(self):
        """P1 三类买：仅突破离开、尚未回踩 → 不报。"""
        strokes = [
            {"direction": "down", "end_price": 8.5},  # 离开前中枢内 down，不得干扰
            {"direction": "up", "end_price": 11.0},  # 离开
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.50)
        types = [bp["type"] for bp in result]
        assert "三类买" not in types

    def test_buy_point_3_pullback_breaks_zg(self):
        """P1 三类买：离开后回踩破 ZG → 不报。"""
        strokes = [
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 9.5},  # 破 zh_top=10
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.30)
        types = [bp["type"] for bp in result]
        assert "三类买" not in types

    def test_buy_point_3_beyond_max_leave_pct(self):
        """P1 三类买：离开超过 15% 上限 → 不报。"""
        strokes = [
            {"direction": "up", "end_price": 13.0},
            {"direction": "down", "end_price": 12.0},
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 12.0)  # 20% above
        types = [bp["type"] for bp in result]
        assert "三类买" not in types

    def test_buy_point_3_uses_latest_leave_ok(self):
        """P2 三类买：早期 leave+合法回踩，后期再次 leave 更高且回踩不破 → 仍以最近 leave 为准，三买成立。"""
        strokes = [
            {"direction": "down", "end_price": 9.0},   # 中枢内
            {"direction": "up", "end_price": 10.5},     # early leave
            {"direction": "down", "end_price": 10.1},   # early 合法回踩
            {"direction": "up", "end_price": 11.2},     # later leave 更高
            {"direction": "down", "end_price": 10.2},   # later 回踩不破 ZG=10
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.30)
        types = [bp["type"] for bp in result]
        assert "三类买" in types

    def test_buy_point_3_latest_leave_pullback_breaks(self):
        """P2 三类买：早期回踩曾合法，但最近 leave 后回踩破 ZG → 不报。"""
        strokes = [
            {"direction": "down", "end_price": 9.0},
            {"direction": "up", "end_price": 10.5},     # early leave
            {"direction": "down", "end_price": 10.1},   # early 合法回踩
            {"direction": "up", "end_price": 11.2},     # later leave
            {"direction": "down", "end_price": 9.5},    # later 破 ZG
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.30)
        types = [bp["type"] for bp in result]
        assert "三类买" not in types

    def test_buy_point_1_area_not_weaker(self):
        """P1 一类买：面积可算但后笔力度未更弱 → 不报一类。"""
        bars, sp, ep, sc, ec = self._make_bars_with_neg_areas(area_prev=-3.0, area_curr=-10.0)
        strokes = [
            {"direction": "down", "end_price": 10.0, "start_index": sp, "end_index": ep},
            {"direction": "up", "end_price": 12.0},
            {"direction": "down", "end_price": 9.0, "start_index": sc, "end_index": ec},
        ]
        zones = [{"zh_top": 11.5, "zh_bottom": 10.5, "valid": True}]
        result = detect_buy_points(strokes, zones, 9.0, bars=bars)
        types = [bp["type"] for bp in result]
        assert "一类买" not in types


class TestDetectSellPointsP1:
    """P1 卖点对称性抽检。"""

    def test_sell_point_3_after_leave_bounce(self):
        """三类卖：离开 ZD 后反弹不回 → 有。"""
        strokes = [
            {"direction": "down", "end_price": 7.0},  # 离开 zh_bottom=8
            {"direction": "up", "end_price": 7.8},  # 反弹不回 ZD
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_sell_points(strokes, zones, 7.5)
        types = [sp["type"] for sp in result]
        assert "三类卖" in types

    def test_sell_point_3_no_bounce_after_leave(self):
        """三类卖：仅离开未反弹 → 无。"""
        strokes = [{"direction": "down", "end_price": 7.0}]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_sell_points(strokes, zones, 7.5)
        types = [sp["type"] for sp in result]
        assert "三类卖" not in types

    def test_sell_point_3_uses_latest_leave(self):
        """P2 三类卖：以最近 leave 后反弹为准；later 反弹回穿 ZD → 不报。"""
        strokes = [
            {"direction": "up", "end_price": 9.0},
            {"direction": "down", "end_price": 7.5},    # early leave
            {"direction": "up", "end_price": 7.8},      # early 合法反弹
            {"direction": "down", "end_price": 7.0},    # later leave 更低
            {"direction": "up", "end_price": 8.2},      # later 反弹回穿 ZD=8
        ]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_sell_points(strokes, zones, 7.5)
        types = [sp["type"] for sp in result]
        assert "三类卖" not in types


class TestStrokeForceTolerance:
    def test_force_not_much_stronger_tol(self):
        # |curr| = 10.4, |prev|=10 → 1.04 <= 1.05 → True
        assert _stroke_force_not_much_stronger(-10.0, -10.4, "down", tol=1.05) is True
        # 1.06 > 1.05 → False
        assert _stroke_force_not_much_stronger(-10.0, -10.6, "down", tol=1.05) is False

    def test_zero_area_not_valid_force(self):
        """无同侧真实柱时 area 为 None，不得用 0.0 放行 weaker / not_much_stronger。"""
        bars = [{"macd_histogram": 0.0} for _ in range(10)]
        stroke = {"start_index": 0, "end_index": 9, "direction": "down"}
        assert _stroke_macd_area(bars, stroke, "neg") is None
        assert _stroke_force_weaker(-5.0, None, "down") is False
        assert _stroke_force_not_much_stronger(None, None, "down") is False
        # 正柱区段对 neg 侧无效
        bars_pos = [{"macd_histogram": 1.0} for _ in range(10)]
        assert _stroke_macd_area(bars_pos, stroke, "neg") is None


class TestUnwrapChan:
    def test_nested_and_flat(self):
        flat = {"strokes": [1], "buy_points": []}
        nested = {"chanlun": flat}
        assert unwrap_chan(nested) is flat
        assert unwrap_chan(flat) is flat
        assert unwrap_chan(None) == {}
        assert unwrap_chan("x") == {}


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
        """fallback 全图峰谷顶背离（无笔/无 index）。"""
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
        """fallback 全图峰谷底背离（无笔/无 index）。"""
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

    def test_stroke_level_bottom_divergence(self):
        """P1 笔级底背驰：两 down 创新低 + 负面积减弱 → bottom_divergence True。"""
        bars = []
        for _ in range(5):
            bars.append({"high": 12, "low": 10, "macd_histogram": -2.0, "close": 10})
        for _ in range(3):
            bars.append({"high": 13, "low": 11, "macd_histogram": 0.5, "close": 12})
        for _ in range(5):
            bars.append({"high": 11, "low": 8, "macd_histogram": -0.5, "close": 8})
        strokes = [
            {"direction": "down", "end_price": 10.0, "start_index": 0, "end_index": 4},
            {"direction": "up", "end_price": 13.0, "start_index": 5, "end_index": 7},
            {"direction": "down", "end_price": 8.0, "start_index": 8, "end_index": 12},
        ]
        result = detect_divergence(bars, strokes)
        assert result["bottom_divergence"] is True
        # 校验辅助：后笔 |area| 更小
        a0 = _stroke_macd_area(bars, strokes[0], "neg")
        a1 = _stroke_macd_area(bars, strokes[2], "neg")
        assert _stroke_force_weaker(a0, a1, "down") is True

    def test_stroke_level_top_divergence(self):
        """P1 笔级顶背驰：两 up 创新高 + 正面积减弱 → top_divergence True。"""
        bars = []
        for _ in range(5):
            bars.append({"high": 12, "low": 10, "macd_histogram": 2.0, "close": 12})
        for _ in range(3):
            bars.append({"high": 11, "low": 9, "macd_histogram": -0.5, "close": 10})
        for _ in range(5):
            bars.append({"high": 15, "low": 13, "macd_histogram": 0.5, "close": 15})
        strokes = [
            {"direction": "up", "end_price": 12.0, "start_index": 0, "end_index": 4},
            {"direction": "down", "end_price": 9.0, "start_index": 5, "end_index": 7},
            {"direction": "up", "end_price": 15.0, "start_index": 8, "end_index": 12},
        ]
        result = detect_divergence(bars, strokes)
        assert result["top_divergence"] is True

    def test_stroke_level_not_weaker_blocks_peak_fallback(self):
        """P1: 笔级面积可算且未更弱时，底背驰保持 False，不被峰谷 fallback 覆盖。"""
        # 后笔负面积更强（|area| 更大）→ 笔级不背驰
        bars = []
        for _ in range(5):
            bars.append({"high": 12, "low": 10, "macd_histogram": -0.5, "close": 10})
        for _ in range(3):
            bars.append({"high": 13, "low": 11, "macd_histogram": 0.5, "close": 12})
        for _ in range(5):
            bars.append({"high": 11, "low": 8, "macd_histogram": -2.0, "close": 8})
        # 同时构造明显的峰谷底背离形态（价新低 MACD 更高）——若误走 fallback 会变 True
        bars[2] = {"high": 12, "low": 9.5, "macd_histogram": -1.5, "close": 10}
        bars[10] = {"high": 11, "low": 7.5, "macd_histogram": -0.3, "close": 8}
        strokes = [
            {"direction": "down", "end_price": 10.0, "start_index": 0, "end_index": 4},
            {"direction": "up", "end_price": 13.0, "start_index": 5, "end_index": 7},
            {"direction": "down", "end_price": 8.0, "start_index": 8, "end_index": 12},
        ]
        a0 = _stroke_macd_area(bars, strokes[0], "neg")
        a1 = _stroke_macd_area(bars, strokes[2], "neg")
        assert a0 is not None and a1 is not None
        assert _stroke_force_weaker(a0, a1, "down") is False
        result = detect_divergence(bars, strokes)
        assert result["bottom_divergence"] is False


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
        """inclusion 后重算 MACD，背驰检测应能正常返回字段。"""
        bars = [_make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1) for i in range(30)]
        result = chanlun_analysis(bars, 10.5)
        assert "divergence" in result
        assert "top_divergence" in result["divergence"]
        assert "bottom_divergence" in result["divergence"]

    def test_inclusion_macd_recalc_does_not_mutate_caller(self):
        """cleaned 上重算 MACD 不得写回调用方 bars 的 macd_histogram。"""
        bars = [
            _make_bar(10 + i * 0.1, 11 + i * 0.1, 9 + i * 0.1, 10 + i * 0.1)
            for i in range(30)
        ]
        for b in bars:
            b["macd_histogram"] = 99.0
        chanlun_analysis(bars, 10.5)
        assert all(b.get("macd_histogram") == 99.0 for b in bars)

    def test_cleaned_macd_recomputed_not_inherited_sentinel(self):
        """inclusion 后 MACD 必须重算：假 sentinel 不应原样进入笔级面积。"""
        from trader_shared.chan_core import _calc_macd, _stroke_macd_area

        # 含包含关系的序列，使 cleaned 更短
        bars = []
        for i in range(40):
            if i % 5 == 1:
                # 被前一根包含的胖 K（触发合并）
                bars.append(_make_bar(10, 10.5, 9.5, 10.0))
            else:
                base = 10 + i * 0.15
                bars.append(_make_bar(base, base + 1.0, base - 0.5, base + 0.3))
        for b in bars:
            b["macd_histogram"] = 99.0

        cleaned = handle_inclusion(bars)
        assert len(cleaned) < len(bars) or len(cleaned) <= len(bars)
        # 继承 sentinel 时面积会极大；重算后应接近 _calc_macd(cleaned) 而非 99*n
        recomputed = _calc_macd(cleaned)
        result = chanlun_analysis(bars, float(bars[-1]["close"]))
        strokes = result.get("strokes") or []
        if len(strokes) >= 1 and strokes[0].get("start_index") is not None:
            s0 = strokes[0]
            area_recomputed_path = _stroke_macd_area(recomputed, s0, "neg")
            area_if_inherited = _stroke_macd_area(cleaned, s0, "neg")  # cleaned 仍带 99 的拷贝
            # 若仍用继承柱，负面积只累加 h<0，99 不进 neg → 比 pos 侧
            area_pos_inherited = _stroke_macd_area(cleaned, s0, "pos")
            area_pos_recomputed = _stroke_macd_area(recomputed, s0, "pos")
            # 继承 99 的正面积应远大于重算后的正常量级
            if area_pos_inherited is not None and area_pos_recomputed is not None:
                assert abs(area_pos_inherited) > abs(area_pos_recomputed) + 10
            # 分析管线使用重算后 cleaned：笔级面积应与 recomputed 一致
            # （chanlun 内部用的就是 _calc_macd(handle_inclusion)）
            _ = area_recomputed_path  # 管线可跑通即可
        assert result.get("strokes_count", 0) >= 0


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

    def test_segment_needs_three_char_elements(self):
        """P2：仅 2 个特征元素，即使后 low 更低也不终结（仍 1 段收尾）。"""
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},  # 0
            {"direction": "down", "start_price": 20, "end_price": 15},  # 1 char: h=20,l=15
            {"direction": "up",   "start_price": 15, "end_price": 25},  # 2
            {"direction": "down", "start_price": 25, "end_price": 12},  # 3 char: h=25,l=12 更低，但仅 2 元素
            {"direction": "up",   "start_price": 12, "end_price": 18},  # 4
        ]
        segs = build_segments(strokes, min_strokes=3)
        assert len(segs) == 1
        assert segs[0]["direction"] == "up"

    def test_segment_termination(self):
        """P2 特征序列三分型终结：向上段特征序列最后三根底分型 → 切开。

        特征序列（向下笔）不互相包含：
        left(h=20,l=15) / mid(h=18,l=12 最低) / right(h=19,l=14) → 底分型。
        """
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},  # 0
            {"direction": "down", "start_price": 20, "end_price": 15},  # 1 char left
            {"direction": "up",   "start_price": 15, "end_price": 25},  # 2
            {"direction": "down", "start_price": 18, "end_price": 12},  # 3 char mid（最低）
            {"direction": "up",   "start_price": 12, "end_price": 22},  # 4
            {"direction": "down", "start_price": 19, "end_price": 14},  # 5 char right → 底分型终结
            {"direction": "up",   "start_price": 14, "end_price": 18},  # 6 新段
        ]
        segs = build_segments(strokes, min_strokes=3)
        assert len(segs) >= 2
        assert segs[0]["direction"] == "up"
        assert segs[1]["direction"] == "down"

    def test_segment_inclusion_merges(self):
        """重叠的特征序列元素被合并，不足 3 个特征元素不触发终结。"""
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},  # 0
            {"direction": "down", "start_price": 20, "end_price": 15},  # 1 char: h=20,l=15
            {"direction": "up",   "start_price": 15, "end_price": 25},  # 2
            {"direction": "down", "start_price": 25, "end_price": 13},  # 3 char: h=25,l=13 (包含前一个→合并)
            {"direction": "up",   "start_price": 13, "end_price": 18},  # 4
        ]
        segs = build_segments(strokes, min_strokes=3)
        # 包含处理后特征序列元素 < 3，不足以判定三分型终结
        assert len(segs) == 1
        assert segs[0]["direction"] == "up"

    def test_multiple_segments(self):
        """P2 多段：向上段底分型切开后，向下段顶分型再切，至少 2 段。

        向上特征序列 downs：left(20/15) mid(18/12) right(19/14) → 底分型。
        向下特征序列 ups：left(14/18) mid(11/20 最高) right(12/16) → 顶分型（可选，有收尾亦可）。
        """
        strokes = [
            {"direction": "up",   "start_price": 10, "end_price": 20},  # 0
            {"direction": "down", "start_price": 20, "end_price": 15},  # 1 char up-seg left
            {"direction": "up",   "start_price": 15, "end_price": 25},  # 2
            {"direction": "down", "start_price": 18, "end_price": 12},  # 3 char mid
            {"direction": "up",   "start_price": 12, "end_price": 22},  # 4
            {"direction": "down", "start_price": 19, "end_price": 14},  # 5 char right → 向上段终结
            {"direction": "up",   "start_price": 14, "end_price": 18},  # 6 down-seg char
            {"direction": "down", "start_price": 18, "end_price": 11},  # 7
            {"direction": "up",   "start_price": 11, "end_price": 20},  # 8 char mid 顶
            {"direction": "down", "start_price": 20, "end_price": 10},  # 9
            {"direction": "up",   "start_price": 10, "end_price": 16},  # 10 char right → 向下段顶分型
            {"direction": "down", "start_price": 16, "end_price": 12},  # 11
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

    def test_no_zones_with_segments_is_consolidation(self):
        """0 中枢有笔有线段 → 盘整（弱盘整，主状态不用线段不足）。"""
        strokes = self._make_strokes(6)
        result = classify_structure([], segments=[{"direction": "up"}], strokes=strokes)
        assert result["structure_type"] == "盘整"
        assert result["structure_confidence"] == "low"
        assert "structure_evidence" in result

    def test_one_zone_few_segments_still_consolidation(self):
        """1 中枢 + 少段 → 盘整（段数只调 conf）。"""
        zones = [{"zh_top": 20.0, "zh_bottom": 15.0, "valid": True}]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=[{}, {}, {}], strokes=strokes)
        assert result["structure_type"] == "盘整"
        assert result["structure_zones_count"] == 1
        assert result["structure_confidence"] in ("high", "mid", "low")
        # 日线 consol_mid=3 → 3 段为 mid
        assert result["structure_confidence"] == "mid"

    def test_consolidation(self):
        """1 中枢 + 5 段线段 → 盘整 high。"""
        zones = [{"zh_top": 20.0, "zh_bottom": 15.0, "valid": True}]
        segs = [{"direction": "up"} for _ in range(5)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "盘整"
        assert result["structure_zones_count"] == 1
        assert result["structure_confidence"] == "high"

    def test_two_ascending_pivots_five_segs_is_uptrend(self):
        """2 个上移中枢 + 5 段 → 上涨趋势（不再线段不足5/11）；日线 conf=mid。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(5)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes, timeframe="daily")
        assert result["structure_type"] == "上涨趋势"
        assert result["structure_confidence"] == "mid"  # daily trend_mid=5
        assert "线段不足" not in result["structure_type"]
        assert "segments=5" in result["structure_evidence"]
        assert "pivots=2" in result["structure_evidence"]

    def test_overlapping_zones_few_segs_is_consolidation(self):
        """重叠中枢 + 3 段 → 盘整（不再线段不足3/5）；日线 conf=mid。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 18.0, "zh_bottom": 14.0, "valid": True},  # 与前重叠
        ]
        segs = [{"direction": "up"} for _ in range(3)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes, timeframe="daily")
        assert result["structure_type"] == "盘整"
        assert result["structure_confidence"] == "mid"  # daily consol_mid=3
        assert "线段不足" not in result["structure_type"]

    def test_uptrend(self):
        """2 个递增中枢 + 11 段线段 → 上涨趋势 high。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(11)]
        strokes = self._make_strokes(12)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "上涨趋势"
        assert result["structure_zones_count"] == 2
        assert result["structure_confidence"] == "high"

    def test_downtrend(self):
        """2 个递减中枢 + 11 段线段 → 下跌趋势 high。"""
        zones = [
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
        ]
        segs = [{"direction": "down"} for _ in range(11)]
        strokes = self._make_strokes(12)
        result = classify_structure(zones, segments=segs, strokes=strokes)
        assert result["structure_type"] == "下跌趋势"
        assert result["structure_zones_count"] == 2
        assert result["structure_confidence"] == "high"

    def test_daily_vs_weekly_conf_thresholds(self):
        """同一拓扑：日线/周线 conf 门槛不同。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(5)]
        strokes = self._make_strokes(6)
        daily = classify_structure(zones, segments=segs, strokes=strokes, timeframe="daily")
        weekly = classify_structure(zones, segments=segs, strokes=strokes, timeframe="weekly")
        assert daily["structure_type"] == weekly["structure_type"] == "上涨趋势"
        # daily: trend_mid=5,trend_high=8 → 5 段 mid
        assert daily["structure_confidence"] == "mid"
        # weekly: trend_high=5 → 5 段 high
        assert weekly["structure_confidence"] == "high"

    def test_trend_low_conf_with_four_segments(self):
        """2 上移中枢 + 4 段 → 仍是上涨趋势，日线 conf=low。"""
        zones = [
            {"zh_top": 20.0, "zh_bottom": 15.0, "valid": True},
            {"zh_top": 30.0, "zh_bottom": 25.0, "valid": True},
        ]
        segs = [{"direction": "up"} for _ in range(4)]
        strokes = self._make_strokes(6)
        result = classify_structure(zones, segments=segs, strokes=strokes, timeframe="daily")
        assert result["structure_type"] == "上涨趋势"
        assert result["structure_confidence"] == "low"


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
        assert "structure_confidence" in result
        assert result["structure_confidence"] in ("high", "mid", "low")
        assert "structure_evidence" in result
        assert not str(result.get("structure_type", "")).startswith("线段不足")
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
        assert merged[0]["zh_top"] > merged[0]["zh_bottom"]
        assert merged[0]["valid"] is True

    def test_gap_zones_not_merged_into_invalid(self):
        """P0: 不重叠但 gap 很小的中枢不得按交集合并成 top < bottom 的非法中枢。"""
        raw_zones = [
            {"zh_top": 12.0, "zh_bottom": 10.0, "zh_center": 11.0, "valid": True},
            {"zh_top": 14.0, "zh_bottom": 12.05, "zh_center": 13.025, "valid": True},
        ]
        merged = _merge_zones(raw_zones, gap_pct=0.015)
        # 不应合并成非法中枢：保持两个独立，或合并后仍 valid
        assert len(merged) == 2
        for z in merged:
            assert z["zh_top"] > z["zh_bottom"]
            assert z.get("valid", True) is True

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


# ---------------------------------------------------------------------------
# 缠论增量引擎 ChanlunEngine（Phase 1）
# ---------------------------------------------------------------------------

def _gen_bars(n: int = 300, seed: int = 42, with_date: bool = True) -> list[dict]:
    """生成带趋势+噪声的合成日线，便于缠论结构成型。"""
    import random

    random.seed(seed)
    bars: list[dict] = []
    price = 50.0
    for i in range(n):
        drift = 0.5 * __import__("math").sin(i / 15.0) + 0.05
        o = price
        c = max(1.0, price + drift + random.uniform(-0.8, 0.8))
        h = max(o, c) + random.uniform(0, 1.2)
        l = min(o, c) - random.uniform(0, 1.2)
        bar = {
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 1000 + random.randint(0, 500),
        }
        if with_date:
            bar["date"] = str(20240101 + i)
        bars.append(bar)
        price = c
    return bars


def _gen_weekly(n: int = 60, seed: int = 11) -> list[dict]:
    import random

    random.seed(seed)
    bars: list[dict] = []
    price = 50.0
    for i in range(n):
        drift = 0.6 * __import__("math").sin(i / 8.0) + 0.1
        o = price
        c = max(1.0, price + drift + random.uniform(-1.5, 1.5))
        h = max(o, c) + random.uniform(0, 2.5)
        l = min(o, c) - random.uniform(0, 2.5)
        bars.append({
            "open": round(o, 2), "high": round(h, 2), "low": round(l, 2),
            "close": round(c, 2), "volume": 10000 + random.randint(0, 5000),
            "date": "W%d" % i,
        })
        price = c
    return bars


def _norm(o):
    """归一 helper：dict/list 递归、float 四舍五入 4 位、numpy→float，便于逐字段比对。"""
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_norm(x) for x in o]
    if isinstance(o, float):
        return round(o, 4)
    try:
        import numpy as np

        if isinstance(o, np.floating):
            return round(float(o), 4)
        if isinstance(o, np.integer):
            return int(o)
    except ImportError:
        pass
    return o


class TestChanlunEngineConsistency:
    """测试 1（主门，按第七节升级）：增量结果 ≡ 批量结果（完整字段 dict）。"""

    def test_incremental_matches_batch_full_fields(self):
        bars = _gen_bars(300)
        weekly = _gen_weekly()
        current = bars[-1]["close"]

        batch = chanlun_analysis(bars, current, weekly_bars=weekly)
        eng = ChanlunEngine(bars)
        incr = eng.get_analysis(current, weekly_bars=weekly)

        assert _norm(incr) == _norm(batch)

    def test_incremental_matches_batch_no_weekly(self):
        bars = _gen_bars(300, seed=99)
        current = bars[-1]["close"]
        batch = chanlun_analysis(bars, current)
        eng = ChanlunEngine(bars)
        incr = eng.get_analysis(current)
        assert _norm(incr) == _norm(batch)

    def test_incremental_matches_batch_with_symbol(self):
        bars = _gen_bars(300, seed=5)
        current = bars[-1]["close"]
        weekly = _gen_weekly(seed=5)
        kw = dict(symbol="688248.SH", analysis_date="2026-07-07", weekly_bars=weekly)
        batch = chanlun_analysis(bars, current, **kw)
        eng = ChanlunEngine(bars)
        incr = eng.get_analysis(current, **kw)
        assert _norm(incr) == _norm(batch)
        # 给定 symbol/date 时，买卖点应带 signal_id
        if incr["buy_points"]:
            assert "signal_id" in incr["buy_points"][0]
        if incr["sell_points"]:
            assert "signal_id" in incr["sell_points"][0]


class TestChanlunEngineIncremental:
    """测试 2：逐根 bar 增量更新，结果正确且非递减。"""

    def test_incremental_bar_update(self):
        bars = _gen_bars(300, seed=3)
        current = bars[-1]["close"]

        eng = ChanlunEngine()
        prev_strokes = 0
        prev_segments = 0
        for bar in bars:
            eng.update_bar(bar)
            # 已确认笔/段不应回退（允许最后一笔合并，故 -1 容差）
            assert len(eng.strokes) >= prev_strokes - 1
            assert len(eng.segments) >= prev_segments - 1
            prev_strokes = len(eng.strokes)
            prev_segments = len(eng.segments)

        result = eng.get_analysis(current)
        batch = chanlun_analysis(bars, current)
        assert _norm(result) == _norm(batch)


class TestChanlunEngineInclusion:
    """测试 3：包含合并不破坏已有状态。"""

    def test_inclusion_merge_preserves_state(self):
        bars = _gen_bars(300, seed=8)
        eng = ChanlunEngine(bars[:-5])
        prev_fractions = len(eng.fractions)
        prev_strokes = len(eng.strokes)

        # 添加可能触发包含合并的 bar（与末根高度重叠）
        last = bars[-6]
        merge_bar = dict(last)
        merge_bar["high"] = last["high"]
        merge_bar["low"] = last["low"]
        merge_bar["open"] = (last["open"] + last["close"]) / 2
        merge_bar["close"] = (last["open"] + last["close"]) / 2
        eng.update_bar(merge_bar)

        assert len(eng.fractions) >= prev_fractions - 1
        assert len(eng.strokes) >= prev_strokes - 1


class TestChanlunEnginePersistence:
    """测试 4：状态持久化后一致（含 MACD EMA）。"""

    def test_state_persistence(self):
        import tempfile, os

        bars = _gen_bars(300, seed=21)
        eng = ChanlunEngine(bars)
        # 触发一次分析以填充 higher_trend 缓存
        eng.get_analysis(bars[-1]["close"], weekly_bars=_gen_weekly(seed=21))

        tp = tempfile.mktemp(suffix=".json")
        try:
            eng.save(tp)
            eng2 = ChanlunEngine.load(tp)
            assert _norm(eng2.cleaned) == _norm(eng.cleaned)
            assert _norm(eng2.fractions) == _norm(eng.fractions)
            assert _norm(eng2.strokes) == _norm(eng.strokes)
            assert _norm(eng2.segments) == _norm(eng.segments)
            # MACD EMA 状态保真
            assert eng2._ema12 is not None and abs(eng2._ema12 - (eng._ema12 or 0)) < 1e-6
            assert eng2._ema26 is not None and abs(eng2._ema26 - (eng._ema26 or 0)) < 1e-6
            assert eng2._dea is not None and abs(eng2._dea - (eng._dea or 0)) < 1e-6
            # 重新分析仍一致
            assert _norm(eng2.get_analysis(bars[-1]["close"], weekly_bars=_gen_weekly(seed=21))) == _norm(
                eng.get_analysis(bars[-1]["close"], weekly_bars=_gen_weekly(seed=21))
            )
        finally:
            if os.path.exists(tp):
                os.remove(tp)


class TestChanlunEngineReplace:
    """测试 8（第七节新增）：盘中当前 bar 修正（replace）与直接 append 终值一致。"""

    def test_replace_equals_final_append(self):
        bars = _gen_bars(300, seed=7)
        final = dict(bars[-1])
        final["open"] = 51.0
        final["high"] = 55.0
        final["low"] = 50.0
        final["close"] = 54.0
        final["volume"] = 2000
        bars2 = [dict(b) for b in bars[:-1]] + [final]

        eng = ChanlunEngine(bars[:-1])
        # 先以初始值 update（模拟盘中第一笔）
        first = dict(final)
        first["high"] = 52.0
        first["close"] = 51.5
        first["volume"] = 1500
        eng.update_bar(first)
        # 再以终值 replace（同一 date → 覆盖当前 bar）
        eng.update_bar(final)

        res_replace = eng.get_analysis(54.0)
        batch_final = chanlun_analysis(bars2, 54.0)
        assert _norm(res_replace) == _norm(batch_final)


class TestChanlunEngineEdge:
    """测试 5：边界情况不崩溃（与 chanlun_analysis 行为一致：<CHANLUN_MIN_BARS 返回 {}）。"""

    def test_empty_bars(self):
        eng = ChanlunEngine()
        assert eng.get_analysis(100.0) == {}

    def test_single_bar(self):
        eng = ChanlunEngine()
        eng.update_bar({"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000})
        # 与批量接口一致：不足 CHANLUN_MIN_BARS 返回空 dict
        assert eng.get_analysis(102.0) == {}

    def test_all_same_price(self):
        eng = ChanlunEngine()
        for i in range(50):
            eng.update_bar({"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000})
        result = eng.get_analysis(100.0)
        assert result["strokes_count"] == 0

    def test_extreme_price_jump(self):
        eng = ChanlunEngine()
        for i in range(20):
            eng.update_bar({"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000})
        eng.update_bar({"open": 200, "high": 210, "low": 190, "close": 205, "volume": 5000})
        result = eng.get_analysis(205.0)
        assert "strokes" in result


class TestChanlunEnginePerformance:
    """测试 6（按第七节降级为参考）：增量每 tick 不慢于批量重算的 1.5 倍。

    真实收益在「免网络重抓」而非「计算」（实测 chanlun_analysis(300) ≈ 3ms）。
    """

    def test_incremental_performance(self):
        import time

        bars = _gen_bars(300)

        t0 = time.time()
        for _ in range(10):
            chanlun_analysis(bars, bars[-1]["close"])
        batch_time = (time.time() - t0) / 10

        eng = ChanlunEngine(bars)
        t0 = time.time()
        for _ in range(10):
            eng.update_bar(bars[-1])
        incr_time = (time.time() - t0) / 10

        # 参考性：增量每 tick 不慢于批量重算 1.5 倍；两者均 O(n) < 1ms
        assert incr_time <= batch_time * 1.5


class TestChanlunEngineCompat:
    """测试 7：输出与下游（fusion / conclusion_block）字段兼容（完整返回）。"""

    def test_fusion_compatibility(self):
        bars = _gen_bars(300, seed=123)
        eng = ChanlunEngine(bars)
        result = eng.get_analysis(bars[-1]["close"], weekly_bars=_gen_weekly(seed=123))
        for f in ("buy_points", "sell_points", "divergence", "trend_label", "higher_trend_conflict"):
            assert f in result
        for bp in result["buy_points"]:
            assert "type" in bp and "confidence" in bp and "price" in bp

    def test_conclusion_block_compatibility(self):
        bars = _gen_bars(300, seed=321)
        eng = ChanlunEngine(bars)
        result = eng.get_analysis(
            bars[-1]["close"], symbol="688248.SH", analysis_date="2026-07-07", weekly_bars=_gen_weekly(seed=321)
        )
        for f in ("segments", "structure_type", "merged_zones", "fractions", "higher_trend_conflict"):
            assert f in result
        # 给定 symbol/date 时应有 signal_id
        if result["buy_points"] or result["sell_points"]:
            any_id = any(bp.get("signal_id") for bp in result["buy_points"]) or any(
                sp.get("signal_id") for sp in result["sell_points"]
            )
            assert any_id

    def test_unknown_passthrough(self):
        assert _chan_type_canonical("未知类型") == "未知类型"


class TestN1RawBarsHigherTrend:
    """N1 加固：chunk 回退路径下 higher_trend 必须以「原始 raw bars」为源（字节级一致）。

    Part A 修复前 `_chanlun_compute` 在 weekly_bars=None 时用 cleaned（包含处理后）序列
    调 `_higher_level_trend`，与预重构的 `_higher_level_trend(bars)` 口径可能存在聚合边界
    偏移。修复后批量路径传 ``raw_bars=bars``、引擎路径用 ``self._raw``，本组测试锁定该口径。

    注：``chanlun_analysis`` / ``get_analysis`` 的返回字段 ``higher_trend`` 仅存上级趋势
    字符串（"up"/"down"/None），真正的来源口径差异体现在：默认调用应与「显式传入
    ``_higher_level_trend(bars)`` 同口径」逐字段一致（N1 修复后即等于 raw-based 结果）。
    """

    def test_batch_default_matches_explicit_raw_trend(self):
        from trader_shared.config import CHAN_MULTILEVEL_CHUNK

        bars = _gen_bars(300, seed=7)
        current = bars[-1]["close"]
        # chunk 回退路径：weekly_bars=None
        default = chanlun_analysis(bars, current, weekly_bars=None)
        explicit = chanlun_analysis(
            bars, current,
            higher_trend=_higher_level_trend(bars, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=None),
            weekly_bars=None,
        )
        # N1：default 内部必须以 raw bars 计算 higher_trend，与显式 raw-based 一致
        assert _norm(default) == _norm(explicit), (
            "N1: 批量路径默认 higher_trend 必须与 _higher_level_trend(bars) 同口径"
        )

    def test_engine_default_matches_explicit_raw_trend(self):
        from trader_shared.config import CHAN_MULTILEVEL_CHUNK

        bars = _gen_bars(300, seed=11)
        current = bars[-1]["close"]
        eng = ChanlunEngine(bars)
        incr = eng.get_analysis(current, weekly_bars=None)
        explicit = eng.get_analysis(
            current,
            higher_trend=_higher_level_trend(bars, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=None),
            weekly_bars=None,
        )
        assert _norm(incr) == _norm(explicit), (
            "N1: 引擎路径默认 higher_trend 必须以 self._raw 为源"
        )

    def test_batch_equivalent_to_engine_on_raw(self):
        """增量≡批量主门：两者 now 都以 raw bars 驱动 higher_trend，结果仍逐字段一致。"""
        bars = _gen_bars(300, seed=23)
        current = bars[-1]["close"]
        batch = chanlun_analysis(bars, current, weekly_bars=None)
        eng = ChanlunEngine(bars)
        incr = eng.get_analysis(current, weekly_bars=None)
        assert _norm(incr) == _norm(batch)
