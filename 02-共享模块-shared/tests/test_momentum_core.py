from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "02-候选逻辑-candidate"
MARKET = ROOT / "01-行情数据-market-data"
for _p in (CANDIDATE, MARKET):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for name in ("momentum_core", "light_data"):
    sys.modules.pop(name, None)

from momentum_core import calc_rsi, calc_macd, calc_adx, calc_bollinger, assess_momentum, momentum_strategy


def _bars(closes: list[float]) -> list[dict]:
    return [{"close": c, "high": c + 0.02, "low": c - 0.02, "volume": 1000} for c in closes]


class TestCalcRsi:
    def test_rsi_basic(self):
        closes = [10.0 + i * 0.1 for i in range(20)]
        rsi = calc_rsi(closes)
        assert rsi[-1] is not None and 0 <= rsi[-1] <= 100

    def test_rsi_oversold(self):
        closes = [10.0 - i * 0.5 for i in range(20)]
        rsi = calc_rsi(closes)
        assert rsi[-1] is None or rsi[-1] < 30

    def test_rsi_overbought(self):
        closes = [10.0 + i * 0.5 for i in range(20)]
        rsi = calc_rsi(closes)
        assert rsi[-1] is None or rsi[-1] > 70

    def test_rsi_short_data(self):
        assert calc_rsi([10.0] * 5) == [None] * 5


class TestCalcMacd:
    def test_macd_basic(self):
        closes = [10.0 + i * 0.1 for i in range(45)]
        m = calc_macd(closes)
        assert m["macd_line"] is not None
        assert m["dea"] is not None

    def test_macd_short_data(self):
        m = calc_macd([10.0] * 10)
        assert m["macd_line"] is None

    def test_macd_uptrend(self):
        closes = [10.0 + i * 0.3 for i in range(45)]
        m = calc_macd(closes)
        assert m["macd_line"] is None or m["macd_line"] > 0


class TestCalcAdx:
    def test_adx_uptrend(self):
        closes = [10.0 + i * 0.2 for i in range(40)]
        highs = [c + 0.05 for c in closes]
        lows = [c - 0.05 for c in closes]
        a = calc_adx(highs, lows, closes)
        assert a["adx"] is not None
        assert a["adx"] > 0

    def test_adx_short(self):
        closes = [10.0] * 10
        highs = [10.05] * 10
        lows = [9.95] * 10
        a = calc_adx(highs, lows, closes)
        assert a["adx"] is None


class TestCalcBollinger:
    def test_bollinger_basic(self):
        closes = [10.0 + (i % 5) * 0.1 for i in range(25)]
        b = calc_bollinger(closes)
        assert b["upper"] > b["middle"] > b["lower"]
        assert b["pct_b"] is not None

    def test_bollinger_short(self):
        assert calc_bollinger([10.0] * 10)["upper"] is None


class TestAssessMomentum:
    def test_momentum_basic(self):
        bars = _bars([10.0 + i * 0.1 for i in range(35)])
        m = assess_momentum(bars)
        assert "direction" in m
        assert "score" in m
        assert 0 <= m["score"] <= 100

    def test_momentum_bullish(self):
        bars = _bars([10.0 + i * 0.5 for i in range(35)])
        m = assess_momentum(bars)
        assert m["direction"] in ("bullish", "neutral")

    def test_momentum_bearish(self):
        bars = _bars([10.0 - i * 0.5 for i in range(35)])
        m = assess_momentum(bars)
        assert m["direction"] in ("bearish", "neutral")

    def test_momentum_insufficient(self):
        m = assess_momentum(_bars([10.0] * 10))
        assert m["strength"] == "insufficient"
        assert m["direction"] == "neutral"

    def test_momentum_strategy_wrapper(self):
        bars = _bars([10.0 + i * 0.1 for i in range(35)])
        result = momentum_strategy(12.0, bars)
        assert "momentum" in result
        assert "direction" in result["momentum"]
