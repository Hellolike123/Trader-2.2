from trader_shared.momentum_core import calc_rsi, calc_macd


class TestCalcRsiAccuracy:
    def test_rising_prices_rsi_above_50(self):
        closes = [10.0 + i * 0.2 for i in range(30)]
        rsi = calc_rsi(closes)
        last = rsi[-1]
        assert last is not None and last > 50, f"RSI should be > 50 for uptrend, got {last}"

    def test_falling_prices_rsi_below_50(self):
        closes = [30.0 - i * 0.3 for i in range(30)]
        rsi = calc_rsi(closes)
        last = rsi[-1]
        assert last is not None and last < 50, f"RSI should be < 50 for downtrend, got {last}"

    def test_flat_prices_rsi_50(self):
        closes = [25.0] * 20
        rsi = calc_rsi(closes)
        last = rsi[-1]
        assert last is None or abs(last - 50) < 0.01, f"RSI should be 50 for flat prices, got {last}"

    def test_rsi_range_0_to_100(self):
        closes = [10.0 + i * 0.5 for i in range(30)]
        rsi = calc_rsi(closes)
        for val in rsi:
            if val is not None:
                assert 0 <= val <= 100, f"RSI out of range: {val}"

    def test_rsi_oversold(self):
        closes = [50.0 - i * 1.0 for i in range(20)]
        rsi = calc_rsi(closes)
        last = rsi[-1]
        assert last is None or last < 30, f"RSI should be < 30 for oversold, got {last}"

    def test_rsi_overbought(self):
        closes = [10.0 + i * 1.0 for i in range(20)]
        rsi = calc_rsi(closes)
        last = rsi[-1]
        assert last is None or last > 70, f"RSI should be > 70 for overbought, got {last}"

    def test_short_data_returns_none(self):
        rsi = calc_rsi([10.0] * 5)
        assert rsi == [None] * 5, f"Short data should return all None, got {rsi}"


class TestCalcMacdAccuracy:
    def test_uptrend_macd_positive(self):
        closes = [10.0 + i * 0.2 for i in range(45)]
        m = calc_macd(closes)
        assert m["macd_line"] is not None and m["macd_line"] > 0, (
            f"MACD should be positive for uptrend, got macd_line={m['macd_line']}"
        )

    def test_downtrend_macd_negative(self):
        closes = [30.0 - i * 0.3 for i in range(45)]
        m = calc_macd(closes)
        assert m["macd_line"] is not None and m["macd_line"] < 0, (
            f"MACD should be negative for downtrend, got macd_line={m['macd_line']}"
        )

    def test_short_data_returns_none(self):
        m = calc_macd([10.0] * 10)
        assert m["macd_line"] is None
        assert m["dea"] is None
        assert m["histogram"] is None

    def test_golden_cross_in_uptrend(self):
        closes = [10.0 + i * 0.15 for i in range(30)] + [14.5 + j * 0.3 for j in range(20)]
        m = calc_macd(closes)
        assert m["golden_cross"] is True or m["macd_line"] > m["dea"], (
            f"Expected golden cross or macd > dea in uptrend, got gc={m['golden_cross']}, "
            f"macd={m['macd_line']}, dea={m['dea']}"
        )

    def test_death_cross_in_downtrend(self):
        closes = [20.0 + i * 0.2 for i in range(30)] + [26.0 - j * 0.4 for j in range(20)]
        m = calc_macd(closes)
        assert m["death_cross"] is True or (m["macd_line"] is not None and m["dea"] is not None
                                             and m["macd_line"] < m["dea"]), (
            f"Expected death cross or macd < dea in downtrend, got dc={m['death_cross']}"
        )

    def test_cross_flags_are_mutually_exclusive(self):
        closes = [10.0 + i * 0.2 for i in range(40)] + [18.0 - j * 0.3 for j in range(20)]
        m = calc_macd(closes)
        assert not (m["golden_cross"] and m["death_cross"]), "golden_cross and death_cross cannot both be True"
