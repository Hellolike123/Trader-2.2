from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
for _p in (SCRIPTS, SHARED_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for name in ("config", "trader_shared", "price_point_engine", "indicators"):
    sys.modules.pop(name, None)

import importlib

indicators = importlib.import_module("indicators")
calculate_adx = indicators.calculate_adx

price_point_engine = importlib.import_module("price_point_engine")
detect_buy_trigger = price_point_engine.detect_buy_trigger
detect_sell_trigger = price_point_engine.detect_sell_trigger

from indicators import calculate_adx
from price_point_engine import detect_buy_trigger, detect_sell_trigger


def _up_5m(start_close: float, n: int, step: float = 0.01) -> list[dict]:
    bars: list[dict] = []
    c = start_close
    for _ in range(n):
        bars.append({"open": c - 0.01, "high": c + 0.02, "low": c - 0.02, "close": c, "volume": 1000})
        c += step
    return bars


def _down_5m(start_close: float, n: int, step: float = 0.01) -> list[dict]:
    bars: list[dict] = []
    c = start_close
    for _ in range(n):
        bars.append({"open": c + 0.01, "high": c + 0.02, "low": c - 0.02, "close": c, "volume": 1000})
        c -= step
    return bars


def _flat_5m(price: float, n: int) -> list[dict]:
    return [{"open": price - 0.01, "high": price + 0.02, "low": price - 0.02, "close": price, "volume": 1000} for _ in range(n)]


class TestCalculateAdx:
    def test_adx_basic_shape(self):
        bars = _up_5m(10.0, 60, step=0.02)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = calculate_adx(highs, lows, closes, period=14)
        adx_vals = [v for v in result["adx"] if v is not None]
        assert len(adx_vals) > 0
        assert all(v > 0 for v in adx_vals)
        assert result["plus_di"][-1] is not None
        assert result["minus_di"][-1] is not None

    def test_adx_uptrend_di_plus_higher(self):
        bars = _up_5m(10.0, 60, step=0.02)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = calculate_adx(highs, lows, closes, period=14)
        pdi = [v for v in result["plus_di"] if v is not None]
        mdi = [v for v in result["minus_di"] if v is not None]
        if pdi and mdi:
            assert pdi[-1] > mdi[-1]

    def test_adx_downtrend_di_minus_higher(self):
        bars = _down_5m(10.0, 60, step=0.02)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = calculate_adx(highs, lows, closes, period=14)
        pdi = [v for v in result["plus_di"] if v is not None]
        mdi = [v for v in result["minus_di"] if v is not None]
        if pdi and mdi:
            assert mdi[-1] > pdi[-1]

    def test_adx_flat_low_adx(self):
        bars = _flat_5m(10.0, 60)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = calculate_adx(highs, lows, closes, period=14)
        adx_vals = [v for v in result["adx"] if v is not None]
        if adx_vals:
            assert all(v < 25 for v in adx_vals)

    def test_adx_returns_none_short_data(self):
        closes = [10.0] * 10
        highs = [10.02] * 10
        lows = [9.98] * 10
        result = calculate_adx(highs, lows, closes, period=14)
        assert result["adx"] == [None] * 10
        assert result["plus_di"] == [None] * 10
        assert result["minus_di"] == [None] * 10


class TestAdxDirectionFilter:
    def test_buy_aux_cleared_in_strong_downtrend(self):
        """Strong bearish trend + only aux conditions = should NOT trigger buy."""
        bars = _down_5m(10.0, 50, step=0.03)
        report: dict = {
            "current_price": 9.5,
            "kline_5m": bars[:30],
            "kline_5m_completed": bars[:30],
            "daily_bars": [{"close": 10.0, "date": "2026-05-01", "high": 10.2, "low": 9.8, "volume": 1000}] * 30,
            "kline_15m": [],
            "kline_30m": [],
            "quote": {"current_price": 9.5, "pre_close": 9.6, "high": 9.7, "low": 9.3},
            "data_status": "fresh",
            "space_state": "good",
            "t0_net_space_pct": 0.02,
        }
        closes = [b["close"] for b in bars[:30]]
        highs = [b["high"] for b in bars[:30]]
        lows = [b["low"] for b in bars[:30]]
        adx = calculate_adx(highs, lows, closes, period=14)
        state: dict = {
            "rsi": [30.0] * 30,
            "volume_ratio": 0.6,
            "closes": closes,
            "macd_ready": True,
            "hist": [-0.5, -0.6, -0.4],
            "last_hist": -0.4,
            "prev_hist": -0.6,
            "last_rsi": 30.0,
            "prev_rsi": 32.0,
            "vwap": 9.6,
            "prev_vwap": None,
            "pct_b": -0.2,
            "bb_squeeze": False,
            "adx": adx["adx"][-1] if adx["adx"] else None,
            "plus_di": adx["plus_di"][-1] if adx["plus_di"] else None,
            "minus_di": adx["minus_di"][-1] if adx["minus_di"] else None,
            "strong_trend": (adx["adx"][-1] if adx["adx"] else 0) > 25 if adx["adx"] and adx["adx"][-1] else False,
            "weak_trend": False,
            "di_uptrend": False,
            "di_downtrend": True,
        }
        zones = {
            "buy_zone": {"main_support": 9.45, "lower": 9.4, "upper": 9.5, "width_pct": 0.005, "source": "5日低点"},
        }
        result = detect_buy_trigger(report, zones, state)
        assert result["status"] != "已触发"

    def test_sell_aux_cleared_in_strong_uptrend(self):
        """Strong bullish trend + only aux conditions = should NOT trigger sell."""
        bars = _up_5m(10.0, 50, step=0.03)
        report: dict = {
            "current_price": 11.0,
            "kline_5m": bars[:30],
            "kline_5m_completed": bars[:30],
            "daily_bars": [{"close": 10.0, "date": "2026-05-01", "high": 10.2, "low": 9.8, "volume": 1000}] * 30,
            "kline_15m": [],
            "kline_30m": [],
            "quote": {"current_price": 11.0, "pre_close": 10.5, "high": 11.2, "low": 10.8},
            "data_status": "fresh",
            "space_state": "good",
            "t0_net_space_pct": 0.02,
        }
        closes = [b["close"] for b in bars[:30]]
        highs = [b["high"] for b in bars[:30]]
        lows = [b["low"] for b in bars[:30]]
        adx = calculate_adx(highs, lows, closes, period=14)
        state: dict = {
            "rsi": [70.0] * 30,
            "volume_ratio": 0.9,
            "closes": closes,
            "macd_ready": True,
            "hist": [0.5, 0.6, 0.4],
            "last_hist": 0.4,
            "prev_hist": 0.6,
            "last_rsi": 70.0,
            "prev_rsi": 68.0,
            "vwap": 10.8,
            "prev_vwap": 10.7,
            "pct_b": 1.2,
            "bb_squeeze": False,
            "adx": adx["adx"][-1] if adx["adx"] else None,
            "plus_di": adx["plus_di"][-1] if adx["plus_di"] else None,
            "minus_di": adx["minus_di"][-1] if adx["minus_di"] else None,
            "strong_trend": (adx["adx"][-1] if adx["adx"] else 0) > 25 if adx["adx"] and adx["adx"][-1] else False,
            "weak_trend": False,
            "di_uptrend": True,
            "di_downtrend": False,
        }
        zones: dict = {
            "sell_zone": {"main_resistance": 11.1, "lower": 11.0, "upper": 11.2, "width_pct": 0.005, "source": "5日高点"},
        }
        result = detect_sell_trigger(report, zones, state)
        assert result["status"] != "已触发"
