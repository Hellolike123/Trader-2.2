"""Phase A anchor persistence acceptance tests (S-P1...S-P4).

法源：docs/plans/wyckoff-structure-anchor-handoff.md §8。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from trader_shared.config import WYCKOFF_SC_COLD_START_BARS_DAILY
from trader_shared.trader_paths import load_json, path, rmw_json
from trader_shared.wyckoff_core import wyckoff_analysis


def _bar(o, h, l, c, v=100, *, d: str = ""):
    out = {"open": o, "high": h, "low": l, "close": c, "volume": v}
    if d:
        out["date"] = d
    return out


def _dated(bars: list[dict], *, start: date = date(2026, 1, 1)) -> list[dict]:
    out: list[dict] = []
    for idx, bar in enumerate(bars):
        item = dict(bar)
        item["date"] = (start + timedelta(days=idx)).isoformat()
        out.append(item)
    return out


def _neutral(price: float = 90.0, vol: int = 100) -> dict:
    return _bar(price, price + 1.0, price - 1.0, price, vol)


def _with_alive_sc(total: int = 50, sc_idx: int = 24) -> list[dict]:
    bars = [_neutral() for _ in range(total)]
    bars[sc_idx] = _bar(84.0, 85.0, 82.0, 83.0, 2500)
    bars[sc_idx + 1] = _bar(83.5, 87.0, 85.0, 86.0, 160)
    for i in range(sc_idx + 2, total):
        bars[i] = _bar(85.0, 86.0, 84.8, 85.2, 120)
    return _dated(bars)


def _extend_after(bars: list[dict], count: int, *, price: float = 85.2) -> list[dict]:
    out = [dict(b) for b in bars]
    start = date.fromisoformat(out[-1]["date"]) + timedelta(days=1)
    for idx in range(count):
        out.append(
            _bar(
                price,
                price + 0.8,
                price - 0.4,
                price,
                110,
                d=(start + timedelta(days=idx)).isoformat(),
            )
        )
    return out


def _with_breakdown_from_alive() -> list[dict]:
    bars = _with_alive_sc(total=32, sc_idx=18)
    bars[20] = {
        **bars[20],
        "open": 82.0,
        "high": 82.5,
        "low": 75.0,
        "close": 76.0,
        "volume": 100,
    }
    bars[21] = {
        **bars[21],
        "open": 76.5,
        "high": 86.5,
        "low": 81.5,
        "close": 86.0,
        "volume": 80,
    }
    return bars


def _daily_key(symbol: str = "600519.SH") -> str:
    return f"{symbol}::daily"


def test_s_p1_cold_start_alive_anchor_is_saved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    bars = _with_alive_sc()

    result = wyckoff_analysis(bars, symbol="600519.SH", use_persisted_phase=False)

    assert result["phase_a_status"] in {"forming", "established"}
    rec = load_json("wyckoff_phase_a_anchor")[_daily_key()]
    assert rec["sc_date"] == bars[result["phase_a_range"]["sc_bar_idx"]]["date"]
    assert rec["sc_low"] == result["phase_a_range"]["sc_low"]
    assert rec["status"] == result["phase_a_range"]["status"]
    assert rec["timeframe"] == "daily"
    phase_path = path("wyckoff_phase")
    assert (not phase_path.exists()) or _daily_key() not in load_json("wyckoff_phase")


def test_s_p2_persisted_anchor_pins_beyond_daily_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    seed_bars = _with_alive_sc()
    first = wyckoff_analysis(seed_bars, symbol="600519.SH", use_persisted_phase=False)
    sc_idx = first["phase_a_range"]["sc_bar_idx"]
    sc_date = seed_bars[sc_idx]["date"]
    sc_low = first["phase_a_range"]["sc_low"]

    long_bars = _extend_after(seed_bars, WYCKOFF_SC_COLD_START_BARS_DAILY + 5)
    assert sc_idx < len(long_bars) - WYCKOFF_SC_COLD_START_BARS_DAILY

    pinned = wyckoff_analysis(long_bars, symbol="600519.SH", use_persisted_phase=False)

    assert pinned["phase_a_range"]["search_mode"] == "pinned"
    assert long_bars[pinned["phase_a_range"]["sc_bar_idx"]]["date"] == sc_date
    assert pinned["phase_a_range"]["sc_low"] == sc_low
    assert pinned["phase_a_status"] in {"forming", "established"}

    cold = wyckoff_analysis(
        long_bars,
        symbol="600519.SH",
        use_persisted_phase=False,
        use_persisted_phase_a_anchor=False,
    )
    assert cold.get("sc_signal") is not True
    assert cold["phase_a_status"] == "none"


def test_s_p3_breakdown_deletes_anchor_and_stays_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    seed_bars = _with_alive_sc(total=32, sc_idx=18)
    first = wyckoff_analysis(seed_bars, symbol="600519.SH", use_persisted_phase=False)
    assert first["phase_a_status"] in {"forming", "established"}
    assert _daily_key() in load_json("wyckoff_phase_a_anchor")

    broken = _with_breakdown_from_alive()
    failed = wyckoff_analysis(broken, symbol="600519.SH", use_persisted_phase=False)

    assert failed["phase_a_status"] == "failed"
    assert failed["phase_a_range"]["status"] == "failed"
    assert failed["tr_maturity"] == "L0"
    assert failed["secondary_test_sc_signal"] is not True
    assert _daily_key() not in load_json("wyckoff_phase_a_anchor")

    again = wyckoff_analysis(broken, symbol="600519.SH", use_persisted_phase=False)
    assert again["phase_a_status"] == "failed"
    assert again["tr_maturity"] == "L0"
    assert again["box_display_mode"] == "none"


def test_s_p4_timeframe_isolated_and_bad_sc_date_discarded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    symbol = "600519.SH"
    daily_bars = _with_alive_sc()
    wyckoff_analysis(daily_bars, symbol=symbol, use_persisted_phase=False)
    daily_rec = load_json("wyckoff_phase_a_anchor")[_daily_key(symbol)]

    weekly_bars = _dated([_neutral(100.0, 100) for _ in range(45)], start=date(2025, 1, 3))
    weekly = wyckoff_analysis(
        weekly_bars,
        symbol=symbol,
        timeframe="weekly",
        use_persisted_phase=False,
    )
    assert weekly["phase_a_status"] == "none"
    anchors = load_json("wyckoff_phase_a_anchor")
    assert anchors[_daily_key(symbol)] == daily_rec
    assert f"{symbol}::weekly" not in anchors

    long_bars = _extend_after(daily_bars, WYCKOFF_SC_COLD_START_BARS_DAILY + 5)

    def _poison(data: dict) -> dict:
        data[_daily_key(symbol)] = {
            **daily_rec,
            "sc_date": "1999-01-01",
            "sc_bar_idx": 1,
        }
        return data

    rmw_json("wyckoff_phase_a_anchor", _poison)
    discarded = wyckoff_analysis(long_bars, symbol=symbol, use_persisted_phase=False)
    assert discarded.get("sc_signal") is not True
    assert discarded["phase_a_status"] == "none"
    assert _daily_key(symbol) not in load_json("wyckoff_phase_a_anchor")
