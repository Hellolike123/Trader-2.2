#!/usr/bin/env python3
"""expma_status 单元测试。"""

from __future__ import annotations

import pytest
from trader_shared.expma_status import (
    calc_expma_status,
    _score_alignment,
    _score_deviation,
)


class TestCalcExpmaStatus:
    def test_empty_closes(self):
        result = calc_expma_status([], 10.0)
        assert result["total_score"] == 0
        assert result["trend_label"] == "数据不足"

    def test_short_closes(self):
        result = calc_expma_status([10.0] * 5, 10.0)
        assert result["total_score"] == 0
        assert result["trend_label"] == "数据不足"

    def test_returns_all_keys(self):
        closes = [10.0 + i * 0.1 for i in range(60)]
        result = calc_expma_status(closes, closes[-1])
        assert "total_score" in result
        assert "alignment_score" in result
        assert "slope_score" in result
        assert "cross_score" in result
        assert "deviation_score" in result
        assert "expma_values" in result
        assert "trend_label" in result
        assert "detail" in result

    def test_score_range(self):
        closes = [10.0 + i * 0.1 for i in range(60)]
        result = calc_expma_status(closes, closes[-1])
        assert 0 <= result["total_score"] <= 10
        assert 0 <= result["alignment_score"] <= 3
        assert 0 <= result["slope_score"] <= 2
        assert 0 <= result["cross_score"] <= 2
        assert 0 <= result["deviation_score"] <= 3


class TestScoreAlignment:
    def test_bullish_alignment(self):
        vals = {"10": 12.0, "20": 11.0, "30": 10.0}
        assert _score_alignment(vals) == 3

    def test_bearish_alignment(self):
        vals = {"10": 8.0, "20": 9.0, "30": 10.0}
        assert _score_alignment(vals) == 0

    def test_partial_bullish(self):
        vals = {"10": 12.0, "20": 11.0}
        assert _score_alignment(vals) == 2

    def test_missing_data(self):
        vals = {}
        assert _score_alignment(vals) == 0


class TestScoreDeviation:
    def test_slightly_above(self):
        vals = {"5": 100.0}
        assert _score_deviation(102.0, vals) == 3

    def test_slightly_below(self):
        vals = {"5": 100.0}
        assert _score_deviation(98.0, vals) == 2

    def test_overbought(self):
        vals = {"5": 100.0}
        assert _score_deviation(110.0, vals) == 0

    def test_oversold(self):
        vals = {"5": 100.0}
        assert _score_deviation(90.0, vals) == 0

    def test_no_data(self):
        assert _score_deviation(100.0, {}) == 1
