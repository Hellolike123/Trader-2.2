"""日线 ~100× 缩放坏点修复。"""
from __future__ import annotations

from trader_shared.light_data import fix_daily_scale_glitches


def test_fix_100x_up_glitch():
    bars = [
        {"date": "2026-07-01", "open": 10, "high": 10.5, "low": 9.8, "close": 10.0},
        {"date": "2026-07-02", "open": 1000, "high": 1050, "low": 980, "close": 1000.0},
    ]
    n = fix_daily_scale_glitches(bars)
    assert n == 1
    assert abs(bars[1]["close"] - 10.0) < 1e-6
    assert abs(bars[1]["open"] - 10.0) < 1e-6


def test_fix_100x_down_glitch():
    bars = [
        {"date": "2026-07-01", "open": 10, "high": 10.5, "low": 9.8, "close": 10.0},
        {"date": "2026-07-02", "open": 0.1, "high": 0.105, "low": 0.098, "close": 0.1},
    ]
    n = fix_daily_scale_glitches(bars)
    assert n == 1
    assert abs(bars[1]["close"] - 10.0) < 1e-6


def test_normal_move_untouched():
    bars = [
        {"date": "2026-07-01", "open": 10, "high": 10.5, "low": 9.8, "close": 10.0},
        {"date": "2026-07-02", "open": 10.1, "high": 11.0, "low": 10.0, "close": 10.8},
    ]
    n = fix_daily_scale_glitches(bars)
    assert n == 0
    assert bars[1]["close"] == 10.8
