from trader_shared.pattern_core import detect_pattern, _detect_double_bottom, _detect_double_top
from tests.benchmark.conftest import generate_double_bottom_bars, generate_double_top_bars


class TestDoubleBottomAccuracy:
    def test_detect_w_bottom(self):
        bars = generate_double_bottom_bars()
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = detect_pattern(closes, highs, lows)
        assert result.pattern == "double_bottom", f"Expected double_bottom, got {result.pattern}"
        assert result.signal == 1, f"Expected signal=1 (bullish), got {result.signal}"
        assert result.neckline > 0, f"Expected positive neckline, got {result.neckline}"
        assert result.target > result.neckline, f"Expected target > neckline, got target={result.target}, neckline={result.neckline}"

    def test_double_bottom_no_breakout(self):
        closes = [
            12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 8.5,
            9, 9.5, 10, 9.5, 9, 8.5, 8.2, 8.5, 9, 9.5,
            9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 10, 10.1,
        ]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]
        result = detect_pattern(closes, highs, lows)
        assert result.pattern != "double_bottom", "Should not detect double_bottom without breakout"


class TestDoubleTopAccuracy:
    def test_detect_m_top(self):
        bars = generate_double_top_bars()
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        result = detect_pattern(closes, highs, lows)
        assert result.pattern == "double_top", f"Expected double_top, got {result.pattern}"
        assert result.signal == -1, f"Expected signal=-1 (bearish), got {result.signal}"


class TestGeneralAccuracy:
    def test_insufficient_data(self):
        closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        result = detect_pattern(closes, highs, lows)
        assert result.pattern == "none", f"Expected no pattern with insufficient data, got {result.pattern}"

    def test_length_mismatch(self):
        closes = [1, 2, 3] * 10
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes[:25]]
        result = detect_pattern(closes, highs, lows[:15])
        assert result.pattern == "none", f"Expected no pattern with length mismatch, got {result.pattern}"
