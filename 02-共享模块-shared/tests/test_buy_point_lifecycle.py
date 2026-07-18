"""买点盖生命周期 L1。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.buy_point_lifecycle import (  # noqa: E402
    evaluate_buy_point_lifecycle,
    build_buy_point_lifecycle_for_report,
)


def test_close_below_lid_failed():
    out = evaluate_buy_point_lifecycle(
        current=9.5,
        last_close=9.5,
        lid_price=10.0,
        has_buy_signal=True,
        intraday=False,
    )
    assert out["status"] == "failed"
    assert "已失效" in out["display_line"]


def test_intraday_pierce_close_back_watching():
    out = evaluate_buy_point_lifecycle(
        current=9.8,
        last_close=10.2,
        lid_price=10.0,
        has_buy_signal=True,
        intraday=True,
    )
    assert out["status"] == "watching"


def test_active_above_lid():
    out = evaluate_buy_point_lifecycle(
        current=10.5,
        last_close=10.5,
        lid_price=10.0,
        has_buy_signal=True,
    )
    assert out["status"] == "active"
    assert "有效" in out["display_line"]


def test_report_builder_shape_failed():
    life = build_buy_point_lifecycle_for_report({
        "current": 9.0,
        "support": 10.0,
        "chan_buy_point_types": ["一类买"],
        "daily_bars": [{"close": 9.0}],
        "key_prices": {"buy_zone_low": 10.0},
    })
    assert life["status"] == "failed"
