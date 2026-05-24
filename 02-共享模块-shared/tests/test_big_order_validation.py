from __future__ import annotations

from typing import Any
import sys
from pathlib import Path

# Add shared scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-行情数据-market-data"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trader_shared"))

from big_order import validate_big_orders


def _make_bar(time: str, close: float) -> dict[str, Any]:
    return {"time": f"2026-05-20 {time}:00", "close": close, "open": close}


def test_validation_active_buy_valid():
    # Buy order at 10:00, price is 10.00
    # Price rises and closes at 10.20 (Valid)
    bars = [
        _make_bar("09:30", 9.90),
        _make_bar("10:00", 10.00), # Key event
        _make_bar("10:30", 10.10),
        _make_bar("11:00", 10.15),
        _make_bar("15:00", 10.20),
    ]
    events = [
        {"time": "10:00", "side": "主动买入", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "有效"
    assert "站稳" in res["reason"]


def test_validation_active_buy_divergent():
    # Buy order at 10:00, price is 10.00
    # Price drops to 9.70 (Divergent)
    bars = [
        _make_bar("09:30", 9.90),
        _make_bar("10:00", 10.00), # Key event
        _make_bar("10:30", 9.80),
        _make_bar("15:00", 9.70),
    ]
    events = [
        {"time": "10:00", "side": "主动买入", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "背离"
    assert "跌破" in res["reason"]


def test_validation_active_buy_invalid():
    # Buy order at 10:00, price is 10.00
    # Price stays flat at 9.92 (Invalid)
    bars = [
        _make_bar("09:30", 9.90),
        _make_bar("10:00", 10.00), # Key event
        _make_bar("10:30", 9.95),
        _make_bar("15:00", 9.92),
    ]
    events = [
        {"time": "10:00", "side": "主动买入", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "无效"
    assert "窄幅震荡" in res["reason"]


def test_validation_active_sell_valid():
    # Sell order at 10:00, price is 10.00
    # Price drops to 9.80 (Valid)
    bars = [
        _make_bar("09:30", 10.10),
        _make_bar("10:00", 10.00), # Key event
        _make_bar("10:30", 9.90),
        _make_bar("15:00", 9.80),
    ]
    events = [
        {"time": "10:00", "side": "主动卖出", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "有效"
    assert "受制于" in res["reason"]


def test_validation_active_sell_divergent():
    # Sell order at 10:00, price is 10.00
    # Price rises to 10.30 (Divergent)
    bars = [
        _make_bar("09:30", 10.10),
        _make_bar("10:00", 10.00), # Key event
        _make_bar("10:30", 10.20),
        _make_bar("15:00", 10.30),
    ]
    events = [
        {"time": "10:00", "side": "主动卖出", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "背离"
    assert "逆势拉升" in res["reason"]


def test_validation_end_of_day():
    # Large order at the very end of day
    bars = [
        _make_bar("09:30", 10.00),
        _make_bar("15:00", 10.00), # Key event
    ]
    events = [
        {"time": "15:00", "side": "主动买入", "hands": 5000, "amount_wan": 500}
    ]
    res = validate_big_orders(bars, events)
    assert res is not None
    assert res["verdict"] == "观察"
    assert "临近尾盘" in res["reason"]
