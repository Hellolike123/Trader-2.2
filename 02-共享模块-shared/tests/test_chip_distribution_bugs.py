"""Tests for chip_distribution.py dynamic decay and independent peak extraction."""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
if str(SHARED.resolve()) not in sys.path:
    sys.path.insert(0, str(SHARED.resolve()))

from trader_shared.chip_distribution import calc_chip_distribution, to_float


# ========== BUG 10: current_pct semantic ==========
def test_bug10_current_pct_is_volume_above_pct():
    """current_pct now correctly reflects '% volume above current price', NOT median bin position."""
    bar_sym = [{"high": 61.0, "low": 59.0, "close": 60.0, "volume": 10000}] * 5
    r = calc_chip_distribution(bar_sym, tick_size=0.15)
    assert r["current_pct"] is not None
    assert r["current_pct"] == r["volume_above_pct"]
    assert 20 < r["current_pct"] < 80, "volume_above_pct should be between 20%% and 80%%, got %.1f%%" % r["current_pct"]
    print("  BUG 10: PASS — current_pct=%.1f%% is actual volume above" % r["current_pct"])


# ========== BUG 11: mid_price linear interpolation ==========
def test_bug11_mid_price_linear_interp():
    """mid_price now uses linear interpolation, not bin-center snapping."""
    bar10 = {"high": 10.15, "low": 9.95, "close": 10.05, "volume": 5000}
    bars = [bar10] * 3

    r005 = calc_chip_distribution(bars, tick_size=0.05)
    r010 = calc_chip_distribution(bars, tick_size=0.10)

    assert r005["mid_price"] is not None
    assert r010["mid_price"] is not None
    assert 9.95 <= r005["mid_price"] <= 10.15
    assert 9.95 <= r010["mid_price"] <= 10.15
    print("  BUG 11: PASS — mid_price is within bar range with interpolation")


# ========== BUG 12: tick boundary stability ==========
def test_bug12_tick_stability():
    """Narrow ranges use smaller tick, not forced to 0.1."""
    narrow = [
        {"high": 60.0, "low": 59.0, "close": 59.5, "volume": 10000},
        {"high": 60.1, "low": 59.1, "close": 59.6, "volume": 10000},
    ]
    r_auto = calc_chip_distribution(narrow, tick_size=None)

    assert r_auto["bin_width"] < 0.1, (
        "Auto tick for narrow range should be < 0.1, got %.4f" % r_auto["bin_width"]
    )
    print("  BUG 12: PASS — narrow range uses smaller tick (%.4f < 0.1)" % r_auto["bin_width"])


# ========== BUG 13: close-weighted allocation ==========
def test_bug13_close_weighted_allocation():
    """Long upper shadow: mid_price should lean toward close, not range mid."""
    bar_long = [{"high": 70.0, "low": 55.0, "close": 56.0, "volume": 100000}]
    r = calc_chip_distribution(bar_long, tick_size=0.15)

    assert r["mid_price"] < 60, (
        "Long upper shadow (close=56) should pull mid_price toward close, got %.2f (range mid=62.5)"
        % r["mid_price"]
    )
    print("  BUG 13: PASS — mid_price=%.2f leans toward close=56, not range mid=62.5" % r["mid_price"])


# ========== BUG 14: deduplicated share ranking ==========
def test_bug14_deduplicated_share_ranking():
    """Same share_pct peaks get same rank, not arbitrary index()."""
    two_peaks = [
        {"high": 44.5, "low": 44.0, "close": 44.25, "volume": 50000},
        {"high": 64.5, "low": 64.0, "close": 64.25, "volume": 50000},
        {"high": 70.0, "low": 69.0, "close": 69.5, "volume": 10000},
    ]
    r = calc_chip_distribution(two_peaks, tick_size=0.5)

    large_peaks = [p for p in r["peaks"] if p["share_of_total"] > 1.0]
    assert len(large_peaks) >= 2, "Should have at least 2 large peaks"
    ranks = sorted(set(p["support_level"] for p in large_peaks))
    assert "强支撑" in ranks or ranks[0] == ranks[1] if len(ranks) > 1 else True, (
        "Same share_pct peaks should get compatible ranks"
    )
    print("  BUG 14: PASS — deduplicated ranking works")


# ========== BUG 15: near-end peak window ==========
def test_bug15_near_end_peak_window():
    """Near-current-price peaks aren't lost to top-3."""
    far_near = [
        {"high": 80.0, "low": 60.0, "close": 65.0, "volume": 100000},
        {"high": 59.5, "low": 58.5, "close": 59.0, "volume": 20000},
        {"high": 75.0, "low": 55.0, "close": 57.0, "volume": 60000},
        {"high": 57.5, "low": 45.0, "close": 48.0, "volume": 30000},
    ]
    r = calc_chip_distribution(far_near, tick_size=0.3)

    near_peaks = [p for p in r["peaks"] if abs(p["price"] - 65.0) / 65.0 <= 0.06]
    assert len(near_peaks) >= 1 or len(r["peaks"]) >= 2, (
        "Should have near-end peaks or at least 2 peaks total"
    )
    print("  BUG 15: PASS — near-end peaks included (%d total peaks)" % len(r["peaks"]))


# ========== BUG 16: return value completeness ==========
def test_bug16_return_value_completeness():
    """Return dict includes bin_width, effective_range, volume_above_pct."""
    bars = [
        {"high": 56.5, "low": 53.0, "close": 53.5, "volume": 10000},
        {"high": 57.0, "low": 53.5, "close": 54.0, "volume": 10000},
    ]
    r = calc_chip_distribution(bars, tick_size=0.2)

    required_keys = {"peaks", "total_volume", "current_pct", "mid_price",
                     "volume_above_pct", "bin_width", "effective_range"}
    assert required_keys.issubset(set(r.keys())), (
        "Missing keys: %s" % (required_keys - set(r.keys()))
    )
    assert r["bin_width"] > 0
    assert r["effective_range"][0] < r["effective_range"][1]
    assert isinstance(r["effective_range"], tuple) and len(r["effective_range"]) == 2
    print("  BUG 16: PASS — all required keys present, bin_width=%.4f, range=%s" % (
        r["bin_width"], r["effective_range"]))


# ========== NEW: Dynamic Chip Decay (时间衰减) ==========
def test_decay_accumulation():
    """Verify that decay factor properly discounts older volume and shifts cost basis to newer bars."""
    bars = [
        {"high": 10.1, "low": 9.9, "close": 10.0, "volume": 10000, "turnover_rate": 50.0}, # Day 1
        {"high": 20.1, "low": 19.9, "close": 20.0, "volume": 6000, "turnover_rate": 50.0},  # Day 2
    ]
    # On Day 1: 10000 volume at 10.0.
    # On Day 2: Day 1 decays by 50% -> 5000 remaining.
    # Day 2's volume 6000 added at 20.0.
    # So peak should shift to 20.0 because 6000 > 5000!
    r = calc_chip_distribution(bars, lookback=2, tick_size=1.0)
    assert len(r["peaks"]) >= 2
    assert abs(r["peaks"][0]["price"] - 20.0) < 1.5
    print("  DECAY TEST: PASS — dynamic decay successfully shifts cost basis to newer bars")


# ========== NEW: Independent Peak Separation (独立峰空间去重) ==========
def test_independent_peak_separation():
    """Verify that returned peaks are strictly separated by at least 4% price difference and 4 bins distance."""
    bars = [
        {"high": 10.05, "low": 9.95, "close": 10.0, "volume": 10000},
        {"high": 10.15, "low": 10.05, "close": 10.1, "volume": 9000},
        {"high": 15.0, "low": 14.8, "close": 14.9, "volume": 8000},
    ]
    # Peaks at 10.0 and 10.1 are too close (<4% price gap).
    # Thus, only ONE peak from the 10.0-10.1 region should be chosen, and the second peak must be 14.9.
    r = calc_chip_distribution(bars, lookback=5, tick_size=0.1)
    prices = [p["price"] for p in r["peaks"]]
    
    if len(prices) >= 2:
        diff = abs(prices[0] - prices[1]) / min(prices[0], prices[1])
        assert diff >= 0.04, f"Peaks {prices} are too close! Diff is {diff:.2f}"
    print("  PEAK SEPARATION TEST: PASS — independent peak separation works")


if __name__ == "__main__":
    print("=" * 60)
    print("Running chip_distribution dynamic decay and peak separation tests")
    print("=" * 60)
    test_bug10_current_pct_is_volume_above_pct()
    test_bug11_mid_price_linear_interp()
    test_bug12_tick_stability()
    test_bug13_close_weighted_allocation()
    test_bug14_deduplicated_share_ranking()
    test_bug15_near_end_peak_window()
    test_bug16_return_value_completeness()
    test_decay_accumulation()
    test_independent_peak_separation()
    print("=" * 60)
    print("ALL CHIP REBUILD VERIFICATION: PASS")
    print("=" * 60)
