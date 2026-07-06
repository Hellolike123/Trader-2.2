"""展示增强 (v2.4.1) 单元测试：Supertrend / VWAP / 动量微调。

这些指标均为「纯展示 + 方案B轻量确认」，不进融合加权、不替换止损。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts")

from trader_shared.indicator_math import calc_supertrend, calc_vwap, calc_atr_series
from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge


def _bars_up(n=30):
    return [{"high": 10 + i, "low": 9 + i, "close": 9.5 + i} for i in range(n)]


def _bars_down(n=30):
    return [{"high": 20 - i * 0.3, "low": 19 - i * 0.3, "close": 19.5 - i * 0.3} for i in range(n)]


def test_supertrend_up():
    st = calc_supertrend(_bars_up())
    assert st["direction"] == "up"
    assert st["stop_long"] is not None
    assert st["stop_long"] < _bars_up()[-1]["close"]
    assert st["vol_level"] in ("波动较低", "波动正常", "波动偏大", "波幅偏高")


def test_supertrend_down():
    st = calc_supertrend(_bars_down())
    assert st["direction"] == "down"
    assert st["stop_short"] is not None
    assert st["stop_short"] > _bars_down()[-1]["close"]


def test_supertrend_flips_in_choppy_market():
    bars = (
        [{"high": 10 + i * 0.2, "low": 9 + i * 0.2, "close": 9.5 + i * 0.2} for i in range(15)]
        + [{"high": 13 - i * 0.4, "low": 12 - i * 0.4, "close": 12.5 - i * 0.4} for i in range(15, 30)]
    )
    st = calc_supertrend(bars)
    assert st["direction"] in ("up", "down")
    if st["direction"] == "up":
        assert st["stop_long"] is not None
    else:
        assert st["stop_short"] is not None


def test_vwap_basic():
    bars5 = [
        {"high": 10.2, "low": 9.8, "close": 10.0, "volume": 1000},
        {"high": 10.3, "low": 10.0, "close": 10.1, "volume": 1200},
        {"high": 10.4, "low": 10.1, "close": 10.3, "volume": 1500},
    ]
    v = calc_vwap(bars5, current_price=10.3)
    assert v["vwap"] is not None
    assert abs(v["vwap"] - 10.151) < 0.01
    assert v["position"] in ("above", "below")
    assert v["deviation_pct"] is not None


def test_vwap_empty():
    v = calc_vwap([])
    assert v["vwap"] is None
    assert v["position"] is None
    assert v["level"] is None


def test_nudge_same_direction_confirms():
    mom = {"momentum": {"direction": "bullish", "score": 60}}
    out = apply_supertrend_nudge(mom, "up")
    # 同向确认增强 +8（封顶 100）
    assert out["momentum"]["score"] == 68


def test_nudge_opposite_direction_no_punish():
    mom = {"momentum": {"direction": "bearish", "score": 40}}
    out = apply_supertrend_nudge(mom, "up")
    # 反向不惩罚，分数不变
    assert out["momentum"]["score"] == 40


def test_nudge_neutral_no_flip():
    mom = {"momentum": {"direction": "neutral", "score": 50}}
    out = apply_supertrend_nudge(mom, "up")
    assert out["momentum"]["score"] == 50


def test_nudge_none_is_noop():
    mom = {"momentum": {"direction": "bullish", "score": 60}}
    out = apply_supertrend_nudge(mom, None)
    assert out["momentum"]["score"] == 60


if __name__ == "__main__":
    test_supertrend_up()
    test_supertrend_down()
    test_supertrend_flips_in_choppy_market()
    test_vwap_basic()
    test_vwap_empty()
    test_nudge_same_direction_confirms()
    test_nudge_opposite_direction_no_punish()
    test_nudge_neutral_no_flip()
    test_nudge_none_is_noop()
    print("ALL INDICATOR ENHANCEMENT TESTS PASSED")
