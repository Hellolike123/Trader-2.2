from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
CANDIDATE = SHARED / "02-候选逻辑-candidate"
MARKET = SHARED / "01-行情数据-market-data"
for p in (SHARED, CANDIDATE, MARKET):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

for mod in ("chan_core", "light_data"):
    if mod in sys.modules:
        del sys.modules[mod]

from chan_core import (
    handle_inclusion,
    find_fractions,
    build_strokes,
    build_zones,
    detect_buy_points,
    detect_divergence,
    chanlun_analysis,
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
        assert len(result) == 1
        assert result[0]["valid"] is False


class TestDetectBuyPoints:
    def test_buy_point_1(self):
        strokes = [{"direction": "down", "end_price": 10.0}]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0, macd_hist_current=1.0, macd_hist_prev=0.5)
        types = [bp["type"] for bp in result]
        assert "一类买" in types

    def test_buy_point_2(self):
        strokes = [
            {"direction": "down", "end_price": 8.0},
            {"direction": "up", "end_price": 11.0},
            {"direction": "down", "end_price": 10.0},
        ]
        zones = []
        result = detect_buy_points(strokes, zones, 10.0)
        types = [bp["type"] for bp in result]
        assert "二类买" in types

    def test_buy_point_3(self):
        strokes = [{"direction": "up", "end_price": 11.0}]
        zones = [{"zh_top": 10.0, "zh_bottom": 8.0, "valid": True}]
        result = detect_buy_points(strokes, zones, 10.15)
        types = [bp["type"] for bp in result]
        assert "三类买" in types


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
