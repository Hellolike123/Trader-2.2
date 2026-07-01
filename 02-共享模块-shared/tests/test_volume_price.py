#!/usr/bin/env python3
"""volume_price 单元测试。"""

from __future__ import annotations

import pytest
from trader_shared.volume_price import (
    _calc_volume_ratio,
    _is_noise_window,
    _parse_hhmm,
    calc_weighted_volume,
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


def _make_5m_bar(time_str: str, volume: float, amount: float = 0.0, close: float = 10.0) -> dict:
    """构造 5 分钟 bar。"""
    bar = {"time": time_str, "volume": volume, "close": close, "high": close, "low": close, "open": close}
    if amount > 0:
        bar["amount"] = amount
    return bar


class TestParseHhmm:
    def test_full_datetime(self):
        assert _parse_hhmm({"time": "2026-05-16 09:35"}) == 935

    def test_time_only(self):
        assert _parse_hhmm({"time": "14:45"}) == 1445

    def test_time_with_seconds(self):
        assert _parse_hhmm({"time": "2026-05-16 10:30:00"}) == 1030

    def test_fallback_to_date_field(self):
        assert _parse_hhmm({"date": "2026-05-16 09:30"}) == 930

    def test_missing_returns_none(self):
        assert _parse_hhmm({}) is None

    def test_invalid_format_returns_none(self):
        assert _parse_hhmm({"time": "abc"}) is None


class TestIsNoiseWindow:
    def test_open_noise_start(self):
        assert _is_noise_window(930) is True

    def test_open_noise_mid(self):
        assert _is_noise_window(937) is True

    def test_open_noise_end(self):
        assert _is_noise_window(945) is True

    def test_close_noise_start(self):
        assert _is_noise_window(1445) is True

    def test_close_noise_end(self):
        assert _is_noise_window(1500) is True

    def test_normal_midday(self):
        assert _is_noise_window(1000) is False

    def test_normal_afternoon(self):
        assert _is_noise_window(1400) is False

    def test_before_open(self):
        assert _is_noise_window(925) is False


class TestCalcWeightedVolume:
    def test_empty_bars(self):
        assert calc_weighted_volume([]) == 0.0

    def test_all_noise_bars(self):
        bars = [
            _make_5m_bar("2026-05-16 09:30", 10000, 100000),
            _make_5m_bar("2026-05-16 09:35", 15000, 150000),
            _make_5m_bar("2026-05-16 09:40", 12000, 120000),
            _make_5m_bar("2026-05-16 09:45", 8000, 80000),
            _make_5m_bar("2026-05-16 14:50", 20000, 200000),
            _make_5m_bar("2026-05-16 14:55", 18000, 180000),
        ]
        assert calc_weighted_volume(bars) == 0.0

    def test_insufficient_filtered_bars(self):
        """Only 2 bars survive filtering → returns 0.0."""
        bars = [
            _make_5m_bar("2026-05-16 09:30", 10000, 100000),  # noise
            _make_5m_bar("2026-05-16 10:00", 5000, 50000),
            _make_5m_bar("2026-05-16 10:05", 6000, 60000),
        ]
        assert calc_weighted_volume(bars) == 0.0

    def test_vwap_with_amount(self):
        """With amount field → VWAP = total_amount / total_volume."""
        bars = [
            _make_5m_bar("2026-05-16 10:00", 10000, 200000, close=20.0),
            _make_5m_bar("2026-05-16 10:05", 20000, 400000, close=20.0),
            _make_5m_bar("2026-05-16 10:10", 15000, 300000, close=20.0),
        ]
        result = calc_weighted_volume(bars)
        # VWAP = (200000 + 400000 + 300000) / (10000 + 20000 + 15000)
        #      = 900000 / 45000 = 20.0
        assert result == pytest.approx(20.0)

    def test_simple_avg_without_amount(self):
        """Without amount field → simple average volume."""
        bars = [
            _make_5m_bar("2026-05-16 10:00", 10000),
            _make_5m_bar("2026-05-16 10:05", 20000),
            _make_5m_bar("2026-05-16 10:10", 30000),
        ]
        result = calc_weighted_volume(bars)
        # Simple avg = (10000 + 20000 + 30000) / 3 = 20000
        assert result == pytest.approx(20000.0)

    def test_noise_bars_excluded(self):
        """Noise bars (open/close) should be excluded from calculation."""
        bars = [
            _make_5m_bar("2026-05-16 09:30", 50000, 500000),  # open noise
            _make_5m_bar("2026-05-16 09:35", 40000, 400000),  # open noise
            _make_5m_bar("2026-05-16 10:00", 10000, 200000),
            _make_5m_bar("2026-05-16 10:05", 20000, 400000),
            _make_5m_bar("2026-05-16 10:10", 15000, 300000),
            _make_5m_bar("2026-05-16 14:50", 30000, 300000),  # close noise
            _make_5m_bar("2026-05-16 14:55", 25000, 250000),  # close noise
        ]
        result = calc_weighted_volume(bars)
        # Only 3 bars survive: VWAP = 900000 / 45000 = 20.0
        assert result == pytest.approx(20.0)

    def test_zero_volume_bars_skipped(self):
        """Bars with volume=0 should be skipped."""
        bars = [
            _make_5m_bar("2026-05-16 10:00", 0, 0),
            _make_5m_bar("2026-05-16 10:05", 10000, 200000),
            _make_5m_bar("2026-05-16 10:10", 20000, 400000),
            _make_5m_bar("2026-05-16 10:15", 15000, 300000),
        ]
        result = calc_weighted_volume(bars)
        # 3 bars survive (1 skipped): VWAP = 900000 / 45000 = 20.0
        assert result == pytest.approx(20.0)

    def test_backward_compatible(self):
        """calc_weighted_volume does not affect existing functions."""
        bars = [_make_bar(10, 1000)] * 20
        ratio = _calc_volume_ratio(bars)
        assert ratio == pytest.approx(1.0)
