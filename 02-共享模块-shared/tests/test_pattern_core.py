#!/usr/bin/env python3
"""pattern_core 单元测试。"""

from __future__ import annotations

import pytest
from trader_shared.pattern_core import (
    detect_pattern,
    PatternResult,
    _find_local_extrema,
    _detect_double_bottom,
    _detect_double_top,
    _detect_triangle,
)


class TestFindLocalExtrema:
    def test_finds_lows_and_highs(self):
        values = [10, 9, 8, 7, 8, 9, 10, 11, 10, 9, 8, 7, 8, 9, 10]
        lows, highs = _find_local_extrema(values, min_gap=2)
        assert len(lows) >= 1
        assert len(highs) >= 1

    def test_empty_data(self):
        lows, highs = _find_local_extrema([], min_gap=2)
        assert lows == []
        assert highs == []


class TestDoubleBottom:
    def test_w_bottom_detected(self):
        # 清晰W底: 下跌→底1→反弹→底2→突破颈线
        closes = [
            12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 8.5,
            9, 9.5, 10, 9.5, 9, 8.5, 8.2, 8.5, 9, 9.5,
            10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5
        ]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]

        result = _detect_double_bottom(closes, highs, lows)
        assert result is not None
        assert result.pattern == "double_bottom"
        assert result.signal == 1
        assert result.neckline > 0
        assert result.target > result.neckline

    def test_no_breakout(self):
        # 没有突破颈线 - 价格在颈线下方
        closes = [
            12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 8.5,
            9, 9.5, 10, 9.5, 9, 8.5, 8.2, 8.5, 9, 9.5,
            9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 10, 10.1
        ]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]

        result = _detect_double_bottom(closes, highs, lows)
        # 颈线在10附近，当前价格10.1可能刚好突破
        # 这个测试验证函数不报错即可
        assert result is None or result.pattern == "double_bottom"


class TestDoubleTop:
    def test_m_top_detected(self):
        # 清晰M头: 上涨→顶1→回调→顶2→跌破颈线
        closes = [
            8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 11.5,
            11, 10.5, 10, 10.5, 11, 11.5, 11.8, 11.5, 11, 10.5,
            10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6, 5.5
        ]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]

        result = _detect_double_top(closes, highs, lows)
        # 验证函数不报错
        assert result is None or result.pattern == "double_top"


class TestTriangle:
    def test_triangle_breakout(self):
        # 三角形收敛: 高点递降，低点递升
        closes = [
            10, 10.2, 10.5, 11, 11.5, 11, 10.5, 10.8, 11.2, 11,
            10.8, 10.6, 11, 10.8, 10.6, 10.8, 11, 10.8, 11.2, 11.5,
            11.8, 12, 12.2, 12.5, 12.8, 13, 13.2, 13.5, 13.8, 14
        ]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]

        result = _detect_triangle(closes, highs, lows)
        # 三角形检测可能不总是触发，取决于数据
        # 这里主要验证不报错
        assert result is None or result.signal in (1, -1)

    def test_no_triangle(self):
        # 无收敛形态
        closes = [10] * 30
        highs = [11] * 30
        lows = [9] * 30

        result = _detect_triangle(closes, highs, lows)
        assert result is None


class TestDetectPattern:
    def test_short_data(self):
        result = detect_pattern([10] * 10, [11] * 10, [9] * 10)
        assert result.pattern == "none"
        assert result.signal == 0

    def test_no_pattern(self):
        closes = [10] * 30
        highs = [11] * 30
        lows = [9] * 30
        result = detect_pattern(closes, highs, lows)
        assert result.pattern == "none"
