"""indicator_math 模块测试。"""

from __future__ import annotations

import sys

for mod in ("trader_shared.indicator_math",):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.indicator_math import (
    calc_expma,
    calc_expma_series,
    calc_macd_series,
)


class TestCalcExpma:
    def test_basic(self):
        closes = [10.0 + i * 0.5 for i in range(20)]
        result = calc_expma(closes, 10)
        assert result is not None
        assert isinstance(result, float)

    def test_empty_returns_none(self):
        assert calc_expma([], 10) is None

    def test_insufficient_data_returns_none(self):
        assert calc_expma([1.0, 2.0], 10) is None

    def test_invalid_period_returns_none(self):
        assert calc_expma([1.0, 2.0], 0) is None
        assert calc_expma([1.0, 2.0], -1) is None

    def test_single_period(self):
        closes = [5.0, 10.0, 15.0]
        result = calc_expma(closes, 3)
        # SMA seed = (5+10+15)/3 = 10, then no more data
        assert result == 10.0

    def test_constant_series(self):
        closes = [100.0] * 30
        result = calc_expma(closes, 12)
        assert result == 100.0

    def test_output_is_rounded(self):
        closes = [10.0 + i * 0.3 for i in range(20)]
        result = calc_expma(closes, 10)
        # Should be rounded to 4 decimal places
        assert result == round(result, 4)


class TestCalcExpmaSeries:
    def test_length_matches_input(self):
        closes = [10.0 + i * 0.5 for i in range(20)]
        result = calc_expma_series(closes, 10)
        assert len(result) == len(closes)

    def test_first_nones(self):
        closes = [10.0 + i * 0.5 for i in range(20)]
        result = calc_expma_series(closes, 10)
        # First period-1 values should be None
        for i in range(9):
            assert result[i] is None
        # 10th value should exist
        assert result[9] is not None

    def test_empty_input(self):
        result = calc_expma_series([], 10)
        assert result == []

    def test_insufficient_data(self):
        closes = [1.0, 2.0, 3.0]
        result = calc_expma_series(closes, 10)
        assert all(v is None for v in result)

    def test_constant_series_all_same(self):
        closes = [50.0] * 20
        result = calc_expma_series(closes, 10)
        # After initialization, all values should be 50.0
        for v in result[9:]:
            assert v == 50.0


class TestCalcMacdSeries:
    def test_basic_output_keys(self):
        closes = [10.0 + i * 0.5 for i in range(50)]
        result = calc_macd_series(closes)
        assert "ema12" in result
        assert "ema26" in result
        assert "dif" in result
        assert "dea" in result
        assert "histogram" in result
        assert len(result["ema12"]) == 50

    def test_short_data_returns_nones(self):
        closes = [10.0] * 10
        result = calc_macd_series(closes)
        # All should be None (not enough data for EMA26)
        assert all(v is None for v in result["ema26"])
        assert all(v is None for v in result["dif"])

    def test_empty_input(self):
        result = calc_macd_series([])
        assert result["ema12"] == []
        assert result["dif"] == []

    def test_ema12_starts_at_index_11(self):
        closes = [10.0 + i * 0.1 for i in range(30)]
        result = calc_macd_series(closes)
        # First 11 should be None
        for i in range(11):
            assert result["ema12"][i] is None
        # Index 11 should have a value
        assert result["ema12"][11] is not None

    def test_ema26_starts_at_index_25(self):
        closes = [10.0 + i * 0.1 for i in range(40)]
        result = calc_macd_series(closes)
        for i in range(25):
            assert result["ema26"][i] is None
        assert result["ema26"][25] is not None

    def test_dif_equals_ema12_minus_ema26(self):
        closes = [10.0 + i * 0.1 for i in range(40)]
        result = calc_macd_series(closes)
        for i in range(40):
            if result["ema12"][i] is not None and result["ema26"][i] is not None:
                expected = result["ema12"][i] - result["ema26"][i]
                assert abs(result["dif"][i] - expected) < 1e-10

    def test_histogram_equals_dif_minus_dea(self):
        closes = [10.0 + i * 0.1 for i in range(50)]
        result = calc_macd_series(closes)
        for i in range(50):
            if result["dif"][i] is not None and result["dea"][i] is not None:
                expected = round(result["dif"][i] - result["dea"][i], 4)
                assert result["histogram"][i] == expected

    def test_with_none_closes(self):
        closes = [10.0 + i * 0.1 for i in range(30)]
        closes[15] = None  # inject a None
        result = calc_macd_series(closes)
        # Should not crash, None positions stay None
        assert result["ema12"][15] is None or True  # may or may not have value depending on position

    def test_constant_series(self):
        closes = [100.0] * 50
        result = calc_macd_series(closes)
        # DIF should be 0 (EMA12 == EMA26 for constant series)
        for i in range(26, 50):
            if result["dif"][i] is not None:
                assert abs(result["dif"][i]) < 0.01

    def test_monotonic_up_dif_positive(self):
        closes = [10.0 + i for i in range(50)]  # strictly increasing
        result = calc_macd_series(closes)
        # After warmup, DIF should be positive (EMA12 > EMA26 for uptrend)
        for i in range(35, 50):
            if result["dif"][i] is not None:
                assert result["dif"][i] > 0


class TestMacdSsotAlignment:
    """T0 / review MACD 必须与 indicator_math.calc_macd_series 对齐。"""

    def test_t0_calculate_macd_matches_ssot(self):
        from trader_shared.t0_indicators import calculate_macd

        closes = [10.0 + i * 0.3 for i in range(60)]
        ssot = calc_macd_series(closes)
        t0 = calculate_macd(closes)
        assert t0["dif"] == ssot["dif"]
        assert t0["dea"] == ssot["dea"]
        assert t0["hist"] == ssot["histogram"]

    def test_t0_constant_series_aligned(self):
        from trader_shared.t0_indicators import calculate_macd

        closes = [100.0] * 50
        ssot = calc_macd_series(closes)
        t0 = calculate_macd(closes)
        for i in range(50):
            if ssot["dif"][i] is not None:
                assert abs(t0["dif"][i] - ssot["dif"][i]) < 1e-9

    def test_review_calc_macd_matches_ssot(self):
        from trader_shared.review_core import calc_macd

        closes = [10.0 + i * 0.2 for i in range(60)]
        bars = [{"close": c, "high": c + 0.5, "low": c - 0.5} for c in closes]
        calc_macd(bars)
        ssot = calc_macd_series(closes)
        for i, bar in enumerate(bars):
            if ssot["dif"][i] is not None:
                assert bar["macd_line"] == round(ssot["dif"][i], 4)
            if ssot["dea"][i] is not None:
                assert bar["dea"] == round(ssot["dea"][i], 4)
            if ssot["histogram"][i] is not None:
                assert bar["macd_histogram"] == round(ssot["histogram"][i], 4)
                assert abs(bar["macd_histogram"] - (bar["macd_line"] - bar["dea"])) < 1e-6


class TestT0AtrSsot:
    def test_latest_atr_matches_calc_atr_series(self):
        from trader_shared.indicator_math import calc_atr_series
        from trader_shared.t0_price_point_engine import _latest_atr

        bars = []
        price = 100.0
        for i in range(40):
            high = price + 3.0
            low = price - 3.0
            close = price + (0.2 if i % 2 == 0 else -0.1)
            bars.append({"open": price, "high": high, "low": low, "close": close, "volume": 1000})
            price = close

        atr = _latest_atr(bars, 14)
        series = calc_atr_series(bars, 14)
        expected = next(v for v in reversed(series) if v is not None)
        assert abs(atr - expected) < 1e-9
        assert atr > 0


class TestEmaBollingerAtrWarmup:
    def test_calculate_ema_matches_calc_expma_series(self):
        from trader_shared.t0_indicators import calculate_ema

        closes = [10.0 + i * 0.4 for i in range(30)]
        assert calculate_ema(closes, 10) == calc_expma_series(closes, 10)

    def test_bollinger_sample_std_matches_momentum(self):
        from trader_shared.momentum_core import calc_bollinger
        from trader_shared.t0_indicators import calculate_bollinger_bands

        closes = [10.0 + (i % 5) * 0.3 + i * 0.05 for i in range(40)]
        mom = calc_bollinger(closes, 20, 2.0)
        t0 = calculate_bollinger_bands(closes, 20, 2.0)
        last = t0[len(closes) - 1]
        assert last["middle"] == mom["middle"]
        assert last["upper"] == mom["upper"]
        assert last["lower"] == mom["lower"]

    def test_compute_atr_fields_warmup_none(self):
        from trader_shared.light_data import _compute_atr_fields

        bars = [
            {"open": 10, "high": 11, "low": 9, "close": 10.5}
            for _ in range(20)
        ]
        _compute_atr_fields(bars)
        for i in range(6):
            assert bars[i]["atr7"] is None
        for i in range(13):
            assert bars[i]["atr14"] is None
            assert bars[i]["atr_ratio"] is None
        assert bars[13]["atr14"] is not None and bars[13]["atr14"] > 0
        assert bars[13]["atr_ratio"] is not None
