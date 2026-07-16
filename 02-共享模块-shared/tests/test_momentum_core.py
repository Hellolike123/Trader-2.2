from __future__ import annotations

import sys

for name in ("trader_shared.momentum_core", "light_data"):
    sys.modules.pop(name, None)

from trader_shared.momentum_core import calc_rsi, calc_macd, calc_adx, calc_bollinger, assess_momentum, momentum_strategy


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

    def test_macd_cross_flags_are_mutually_exclusive(self):
        closes = [10.0 + i * 0.2 for i in range(40)] + [18.0 - i * 0.3 for i in range(20)]
        m = calc_macd(closes)
        assert not (m["golden_cross"] and m["death_cross"])


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

    def test_momentum_skips_incomplete_ohlc_rows(self):
        bars = _bars([10.0 + i * 0.1 for i in range(40)])
        bars[5].pop("high")
        bars[12]["low"] = None
        bars[20].pop("close")
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
        # 数据不足：方向应为 insufficient（非 neutral），分数显式 None（不再用假 50 占位）
        assert m["direction"] == "insufficient"
        assert m["score"] is None

    def test_momentum_strategy_wrapper(self):
        bars = _bars([10.0 + i * 0.1 for i in range(35)])
        result = momentum_strategy(12.0, bars)
        assert "momentum" in result
        assert "direction" in result["momentum"]
        assert "strength" in result["momentum"]

    def test_success_path_has_strength(self):
        bars = _bars([10.0 + i * 0.1 for i in range(40)])
        m = assess_momentum(bars)
        assert m.get("strength") in ("strong", "moderate", "neutral")


class TestSupertrendNudge:
    def test_bearish_confirm_lowers_score(self):
        """空头同向确认应减分（更空），旧逻辑误加分会推向中性。"""
        from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge

        raw = {
            "momentum": {
                "direction": "bearish",
                "score": 28.0,
                "signals": ["ADX强趋势(下跌)"],
            }
        }
        out = apply_supertrend_nudge(raw, "down")
        assert out["momentum"]["score"] == 20.0  # 28 - 8
        assert out["momentum"]["direction"] == "bearish"
        assert out["momentum"]["supertrend_nudge"] == -8

    def test_bullish_confirm_raises_score(self):
        from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge

        raw = {
            "momentum": {
                "direction": "bullish",
                "score": 70.0,
                "signals": [],
            }
        }
        out = apply_supertrend_nudge(raw, "up")
        assert out["momentum"]["score"] == 78.0
        assert out["momentum"]["direction"] == "bullish"

    def test_nudge_remaps_direction_across_threshold(self):
        """中性偏多 + ST 向上确认 → 分数跨 65 后 direction 须变为 bullish。"""
        from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge

        raw = {
            "momentum": {
                "direction": "neutral",
                "score": 58.0,
                "signals": [],
            }
        }
        out = apply_supertrend_nudge(raw, "up")
        assert out["momentum"]["score"] == 66.0
        assert out["momentum"]["direction"] == "bullish"

    def test_nudge_skips_insufficient(self):
        from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge

        raw = {
            "momentum": {
                "direction": "insufficient",
                "score": None,
                "signals": [],
            }
        }
        out = apply_supertrend_nudge(raw, "up")
        assert out["momentum"]["score"] is None
        assert out["momentum"]["direction"] == "insufficient"

    def test_opposite_st_no_punish(self):
        from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge

        raw = {
            "momentum": {
                "direction": "bullish",
                "score": 70.0,
                "signals": [],
            }
        }
        out = apply_supertrend_nudge(raw, "down")
        assert out["momentum"]["score"] == 70.0
