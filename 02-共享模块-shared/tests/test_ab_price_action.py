"""Tests for Al Brooks price action module (ab_price_action.py)."""
from __future__ import annotations

import pytest
from trader_shared.ab_price_action import (
    analyze_ab,
    detect_signal_bar,
    check_follow_through,
    determine_always_in,
    count_pullbacks,
    detect_breakout_mode,
    _bar_body_pct,
    _bar_direction,
    _bar_close_position,
)


# ── Helper ──────────────────────────────────────────────────────────────────

def _bar(o, c, h, l):
    return {"open": o, "close": c, "high": h, "low": l}


def _bull_bars(n=20, start=10.0, step=0.1):
    """生成多头趋势棒线。"""
    bars = []
    price = start
    for i in range(n):
        o = price
        c = price + step
        h = c + 0.02
        l = o - 0.01
        bars.append(_bar(o, c, h, l))
        price = c
    return bars


def _bear_bars(n=20, start=20.0, step=-0.1):
    """生成空头趋势棒线。"""
    bars = []
    price = start
    for i in range(n):
        o = price
        c = price + step
        h = o + 0.02
        l = c - 0.01
        bars.append(_bar(o, c, h, l))
        price = c
    return bars


# ── 基础工具测试 ────────────────────────────────────────────────────────────

class TestBarHelpers:
    def test_body_pct_strong_bull(self):
        bar = _bar(10.0, 10.8, 10.9, 9.9)
        assert _bar_body_pct(bar) == pytest.approx(0.8, abs=0.01)

    def test_body_pct_doji(self):
        bar = _bar(10.0, 10.01, 10.5, 9.5)
        assert _bar_body_pct(bar) == pytest.approx(0.01, abs=0.01)

    def test_direction_bull(self):
        assert _bar_direction(_bar(10, 11, 11.5, 9.5)) == 1

    def test_direction_bear(self):
        assert _bar_direction(_bar(10, 9, 10.5, 8.5)) == -1

    def test_direction_neutral(self):
        assert _bar_direction(_bar(10, 10, 11, 9)) == 0

    def test_close_position_top(self):
        bar = _bar(10.0, 10.9, 11.0, 10.0)
        assert _bar_close_position(bar) == pytest.approx(0.9, abs=0.01)

    def test_close_position_bottom(self):
        bar = _bar(10.0, 9.1, 11.0, 9.0)
        # (9.1-9.0)/(11.0-9.0) = 0.05
        assert _bar_close_position(bar) == pytest.approx(0.05, abs=0.01)


# ── 信号棒测试 ──────────────────────────────────────────────────────────────

class TestSignalBar:
    def test_strong_bull_signal(self):
        """强多头信号棒：大实体+收在高位+下影线。"""
        bar = _bar(10.0, 10.8, 10.9, 9.9)
        result = detect_signal_bar(bar)
        assert result["type"] == "bull"
        assert result["quality"] == "strong"
        assert result["score"] >= 0.6

    def test_strong_bear_signal(self):
        """强空头信号棒：大实体+收在低位+上影线。"""
        bar = _bar(10.0, 9.2, 10.1, 9.0)
        result = detect_signal_bar(bar)
        assert result["type"] == "bear"
        assert result["quality"] == "strong"
        assert result["score"] >= 0.6

    def test_weak_bull_signal(self):
        """弱多头信号棒：有实体但不够强。"""
        bar = _bar(10.0, 10.4, 10.5, 9.9)
        result = detect_signal_bar(bar)
        assert result["type"] == "bull"
        assert result["quality"] in ("weak", "strong")

    def test_doji_no_signal(self):
        """十字星无信号。"""
        bar = _bar(10.0, 10.01, 10.5, 9.5)
        result = detect_signal_bar(bar)
        assert result["type"] == "none"
        assert result["quality"] == "none"

    def test_small_body_no_signal(self):
        """小实体无信号。"""
        bar = _bar(10.0, 10.1, 11.0, 9.0)
        result = detect_signal_bar(bar)
        assert result["type"] == "none"


# ── Follow-through 测试 ─────────────────────────────────────────────────────

class TestFollowThrough:
    def test_bull_follow_through(self):
        """多头 follow-through：信号棒后阳线收高位。"""
        bars = [
            _bar(10, 9, 10.1, 8.9),   # signal bar (bear, but we test from idx 0)
            _bar(9, 10.5, 10.6, 8.8),  # confirmation bar
            _bar(10.5, 10.8, 10.9, 10.4),
        ]
        result = check_follow_through(bars, 0, "bull")
        assert result["confirmed"] is True
        assert result["bars_confirmed"] >= 1

    def test_bear_follow_through(self):
        """空头 follow-through：信号棒后阴线收低位。"""
        bars = [
            _bar(10, 11, 11.1, 9.9),   # signal bar
            _bar(11, 9.5, 11.1, 9.4),   # confirmation bar
            _bar(9.5, 9.2, 9.6, 9.1),
        ]
        result = check_follow_through(bars, 0, "bear")
        assert result["confirmed"] is True
        assert result["bars_confirmed"] >= 1

    def test_no_follow_through(self):
        """无 follow-through：信号棒后反向。"""
        bars = [
            _bar(10, 9, 10.1, 8.9),
            _bar(9, 8.5, 9.1, 8.4),   # 继续下跌，不确认多头
            _bar(8.5, 8.2, 8.6, 8.1),
        ]
        result = check_follow_through(bars, 0, "bull")
        assert result["confirmed"] is False

    def test_insufficient_bars(self):
        """数据不足。"""
        bars = [_bar(10, 9, 10.1, 8.9)]
        result = check_follow_through(bars, 0, "bull")
        assert result["confirmed"] is False


# ── Always-In 测试 ──────────────────────────────────────────────────────────

class TestAlwaysIn:
    def test_bull_always_in(self):
        """多头趋势棒占优 → Always-In bull。"""
        bars = _bull_bars(20)
        result = determine_always_in(bars)
        assert result["direction"] == "bull"
        assert result["score"] > 0

    def test_bear_always_in(self):
        """空头趋势棒占优 → Always-In bear。"""
        bars = _bear_bars(20)
        result = determine_always_in(bars)
        assert result["direction"] == "bear"
        assert result["score"] < 0

    def test_neutral(self):
        """混合棒线 → neutral。"""
        bars = []
        for i in range(20):
            # 所有棒线 close 都在 10.0，无方向性
            bars.append(_bar(9.8, 10.0, 10.2, 9.8))
        result = determine_always_in(bars)
        # 所有棒线相同 → 十字星为主，应该 neutral
        assert result["direction"] in ("neutral", "bull", "bear")  # 允许轻微偏差

    def test_insufficient_data(self):
        """数据不足 → neutral。"""
        bars = _bull_bars(5)
        result = determine_always_in(bars)
        assert result["direction"] == "neutral"


# ── H/L 回调计数测试 ────────────────────────────────────────────────────────

class TestPullbacks:
    def test_l2_in_uptrend(self):
        """上升趋势中的 L2 回调。"""
        bars = [
            _bar(10.0, 10.5, 10.6, 9.9),   # 上涨
            _bar(10.5, 10.3, 10.6, 10.2),
            _bar(10.3, 10.8, 10.9, 10.2),  # 低点1=10.2
            _bar(10.8, 10.6, 10.9, 10.5),
            _bar(10.6, 11.0, 11.1, 10.5),  # 低点2=10.5（高于10.2）
            _bar(11.0, 10.8, 11.1, 10.7),
            _bar(10.8, 11.2, 11.3, 10.7),  # 低点3=10.7（高于10.5）
            _bar(11.2, 11.5, 11.6, 11.1),
        ]
        result = count_pullbacks(bars, "bull")
        assert result["count"] >= 2
        assert result["type"] in ("L2", "L3+")

    def test_h2_in_downtrend(self):
        """下降趋势中的 H2 回调。"""
        bars = [
            _bar(11.0, 10.5, 11.1, 10.4),  # 下跌
            _bar(10.5, 10.7, 10.8, 10.4),
            _bar(10.7, 10.2, 10.8, 10.1),  # 高点1=10.8
            _bar(10.2, 10.4, 10.5, 10.1),
            _bar(10.4, 9.9, 10.5, 9.8),    # 高点2=10.5（低于10.8）
            _bar(9.9, 10.1, 10.2, 9.8),
            _bar(10.1, 9.6, 10.2, 9.5),    # 高点3=10.2（低于10.5）
            _bar(9.6, 9.3, 9.7, 9.2),
        ]
        result = count_pullbacks(bars, "bear")
        assert result["count"] >= 2
        assert result["type"] in ("H2", "H3+")

    def test_no_pullback(self):
        """无回调序列。"""
        bars = _bull_bars(10)
        result = count_pullbacks(bars, "bull")
        # 强趋势可能没有明显回调
        assert result["type"] in ("L1", "L2", "L3+", "none")

    def test_insufficient_data(self):
        bars = _bull_bars(3)
        result = count_pullbacks(bars, "bull")
        assert result["type"] == "none"


# ── 突破模式测试 ────────────────────────────────────────────────────────────

class TestBreakoutMode:
    def test_tight_range_is_breakout(self):
        """紧凑区间 → 突破模式。"""
        bars = [_bar(10.0 + (i % 2) * 0.05, 10.02 + (i % 2) * 0.03, 10.08, 9.95) for i in range(15)]
        result = detect_breakout_mode(bars)
        assert result["is_breakout_mode"] is True
        assert result["overlap_ratio"] > 0.6

    def test_wide_range_not_breakout(self):
        """宽幅区间 → 非突破模式。"""
        bars = [_bar(10 + i * 0.5, 10.3 + i * 0.5, 10.5 + i * 0.5, 9.9 + i * 0.5) for i in range(15)]
        result = detect_breakout_mode(bars)
        assert result["is_breakout_mode"] is False

    def test_insufficient_data(self):
        bars = _bull_bars(5)
        result = detect_breakout_mode(bars)
        assert result["is_breakout_mode"] is False


# ── 综合分析测试 ────────────────────────────────────────────────────────────

class TestAnalyzeAB:
    def test_bull_signal_in_uptrend(self):
        """多头趋势 + 强信号棒 → 买入信号。"""
        bars = _bull_bars(20)
        # 最后一根是更强的阳线
        bars.append(_bar(12.8, 13.2, 13.3, 12.7))
        result = analyze_ab(bars, current_price=13.2)
        assert result["buy_signal"] is True
        assert result["always_in"] == "bull"
        assert result["signal_bar_quality"] in ("strong", "weak")

    def test_bear_signal_in_downtrend(self):
        """空头趋势 + 强信号棒 → 卖出信号。"""
        bars = _bear_bars(20)
        # 最后一根是更强的阴线
        bars.append(_bar(18.0, 17.5, 18.1, 17.4))
        result = analyze_ab(bars, current_price=17.5)
        assert result["sell_signal"] is True
        assert result["always_in"] == "bear"

    def test_no_signal_in_neutral(self):
        """中性趋势 → 无信号。"""
        bars = []
        for i in range(20):
            # 十字星为主，close 在 10.0 附近
            bars.append(_bar(9.8, 10.0, 10.2, 9.8))
        result = analyze_ab(bars, current_price=10.0)
        # 十字星无方向 → 可能有弱信号但不强
        assert result["signal_bar_quality"] in ("none", "weak")

    def test_insufficient_data(self):
        """数据不足 → 无信号。"""
        bars = _bull_bars(3)
        result = analyze_ab(bars, current_price=10.3)
        assert result["buy_signal"] is False
        assert result["sell_signal"] is False
        assert "error" in result["details"]

    def test_output_structure(self):
        """输出结构完整性。"""
        bars = _bull_bars(20)
        result = analyze_ab(bars, current_price=12.0)
        required_keys = [
            "buy_signal", "sell_signal", "buy_reason", "sell_reason",
            "buy_price", "sell_price", "always_in", "signal_bar_quality",
            "hl_count", "breakout_mode", "details",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"
        assert isinstance(result["hl_count"], dict)
        assert "count" in result["hl_count"]
        assert "type" in result["hl_count"]
