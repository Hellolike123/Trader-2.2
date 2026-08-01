"""中线量度目标：必须在真周线上出 TR/P&F，不得抄日线。"""

from __future__ import annotations

from datetime import date, timedelta

from trader_shared.wyckoff_core import wyckoff_analysis


def _wk(o: float, h: float, l: float, c: float, v: float, d: date) -> dict:
    return {
        "date": d.isoformat(),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


def test_weekly_phase_a_seed_yields_cause_effect_targets() -> None:
    """构造周线 SC→AR：weekly 路径须亮量度目标。"""
    bars: list[dict] = []
    d0 = date(2025, 11, 7)
    for i in range(20):
        d = d0 + timedelta(weeks=i)
        bars.append(_wk(60.0, 63.0, 57.0, 60.0, 120_000.0, d))
    sc_d = d0 + timedelta(weeks=20)
    bars.append(_wk(58.0, 59.0, 38.0, 39.0, 220_000.0, sc_d))
    ar_d = sc_d + timedelta(weeks=1)
    bars.append(_wk(39.5, 45.0, 39.0, 43.0, 140_000.0, ar_d))
    bars.append(_wk(42.0, 44.0, 40.0, 41.5, 110_000.0, ar_d + timedelta(weeks=1)))
    bars.append(_wk(41.0, 43.5, 40.2, 42.0, 105_000.0, ar_d + timedelta(weeks=2)))

    weekly = wyckoff_analysis(
        bars, symbol="688248", timeframe="weekly", use_persisted_phase=False
    )

    assert weekly.get("sc_signal") is True
    assert weekly.get("ar_signal") is True
    assert weekly.get("tr_lower") is not None
    assert weekly.get("tr_upper") is not None
    assert weekly.get("cause_effect_up_target") is not None
    assert weekly.get("cause_effect_down_target") is not None
    assert weekly.get("pnf_method") in (
        "horizontal",
        "vertical",
        "height_1to1_fallback",
    )
    # 上目标应高于箱体上沿
    assert float(weekly["cause_effect_up_target"]) > float(weekly["tr_upper"])
