#!/usr/bin/env python3
"""volume_price 单元测试。"""

from __future__ import annotations

import pytest
from trader_shared.volume_price import (
    _calc_volume_ratio,
    detect_volume_divergence,
    VolumeWarning,
)


def _make_bar(close: float, volume: float, high: float | None = None, low: float | None = None, open_: float | None = None) -> dict:
    h = high if high is not None else close + 0.5
    l = low if low is not None else close - 0.5
    o = open_ if open_ is not None else close
    return {"close": close, "volume": volume, "high": h, "low": l, "open": o}


class TestCalcVolumeRatio:
    def test_insufficient_data_returns_1(self):
        bars = [_make_bar(10, 1000)] * 5
        assert _calc_volume_ratio(bars) == 1.0

    def test_equal_volumes_returns_1(self):
        bars = [_make_bar(10, 1000)] * 20
        ratio = _calc_volume_ratio(bars)
        assert ratio == pytest.approx(1.0)

    def test_recent_heavier_returns_above_1(self):
        bars = [_make_bar(10, 500)] * 5 + [_make_bar(10, 2000)] * 5
        ratio = _calc_volume_ratio(bars, window=5)
        # ratio = prev_avg / recent_avg = 2000/500 = 4.0
        assert ratio > 1.0

    def test_recent_lighter_returns_below_1(self):
        bars = [_make_bar(10, 2000)] * 5 + [_make_bar(10, 500)] * 5
        ratio = _calc_volume_ratio(bars, window=5)
        # ratio = prev_avg / recent_avg = 500/2000 = 0.25
        assert ratio < 1.0


class TestDetectVolumeDivergence:
    def test_too_few_bars(self):
        bars = [_make_bar(10, 1000)] * 5
        result = detect_volume_divergence(bars)
        assert result.warning_type == "none"
        assert result.signal == 0
        assert "数据不足" in result.reason

    def test_normal_volume(self):
        bars = [_make_bar(10, 1000)] * 15
        result = detect_volume_divergence(bars)
        assert result.warning_type == "none"
        assert result.signal == 0
        assert result.volume_ratio == pytest.approx(1.0)

    def test_stagnation_detection(self):
        # High volume but flat price
        bars = [_make_bar(10, 1000, high=10.5, low=9.5, open_=10.0)] * 5
        bars += [_make_bar(10.05, 5000, high=10.5, low=9.5, open_=10.0)] * 5
        result = detect_volume_divergence(bars)
        assert result.warning_type == "stagnation"
        assert result.signal == -1
        assert result.volume_ratio > 1.0

    def test_climactic_detection(self):
        # Build 16 bars where last 5 all have high volume (ratio >= 2.0)
        # and last bar makes new high with no upper shadow
        bars = []
        for i in range(11):
            bars.append(_make_bar(10 + i * 0.2, 1000, high=10 + i * 0.2, low=10 + i * 0.2 - 0.1, open_=10 + i * 0.2 - 0.05))
        for i in range(5):
            price = 12.2 + i * 0.2
            bars.append(_make_bar(price, 5000, high=price, low=price - 0.1, open_=price - 0.05))
        result = detect_volume_divergence(bars, climactic_threshold=2.0)
        assert result.warning_type == "climactic"
        assert result.signal == -1

    def test_volume_warning_to_signal(self):
        from trader_shared.volume_price import volume_warning_to_signal
        w = VolumeWarning(warning_type="stagnation", signal=-1, confidence=0.5, reason="test")
        sig = volume_warning_to_signal(w)
        assert sig["direction"] == -1
        assert sig["confidence"] == 0.5
        assert sig["raw_key"] == "volume_price"
