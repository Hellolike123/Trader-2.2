"""Sanity check: qfqday fallback to day logic works as intended.

The real fetch_qfq_daily uses a closure around extract_jsonp, making
it hard to mock in unit tests. Instead, we inline the fallback logic
here (mirrors lines 300-316 of light_data.py) and test it directly.
"""
from __future__ import annotations


def to_float(value) -> float | None:
    """Lightweight copy from light_data.to_float for test isolation."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("-", "None", ""):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def build_bars_from(sec_data: dict, sec_key: str) -> list[dict]:
    """Copy of the core fallback logic from fetch_qfq_daily.do_fetch
    (lines 300-316 of light_data.py), tested in isolation.
    """
    rows = (sec_data.get("data") or {}).get(sec_key) or {}
    qfqday = rows.get("qfqday") or []
    bars: list[dict] = []
    for row in qfqday:
        if isinstance(row, list) and len(row) >= 6:
            bars.append({"date": row[0], "close": to_float(row[2])})
    # 新股/qfqday 为空时回退到原始 day
    if not bars:
        day_rows = rows.get("day") or []
        for row in day_rows:
            if isinstance(row, list) and len(row) >= 6:
                bars.append({"date": row[0], "close": to_float(row[2])})
    if not bars:
        raise RuntimeError("Tencent qfq daily bars unavailable")
    return bars


def test_qfqday_produces_bars():
    sec_data = {
        "data": {
            "688248.SZ": {
                "qfqday": [
                    ["2026-05-07", 20.00, 20.50, 21.00, 19.80, 50000],
                    ["2026-05-08", 20.50, 21.00, 21.50, 20.30, 60000],
                ],
            }
        }
    }
    bars = build_bars_from(sec_data, "688248.SZ")
    assert len(bars) == 2
    assert bars[0]["date"] == "2026-05-07"
    assert bars[0]["close"] == 20.50


def test_qfqday_empty_fallbacks_to_day():
    sec_data = {
        "data": {
            "688248.SZ": {
                "qfqday": [],
                "day": [
                    ["2026-02-01", 30.00, 30.50, 31.00, 29.50, 10000],
                    ["2026-02-02", 30.50, 31.00, 31.50, 30.00, 12000],
                    ["2026-02-03", 31.00, 31.50, 32.00, 30.80, 15000],
                ],
            }
        }
    }
    bars = build_bars_from(sec_data, "688248.SZ")
    assert len(bars) == 3
    assert bars[0]["close"] == 30.50
    assert bars[2]["close"] == 31.50


def test_qfqday_empty_and_day_empty_raises():
    sec_data = {"data": {"688248.SZ": {"qfqday": [], "day": []}}}
    try:
        build_bars_from(sec_data, "688248.SZ")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "unavailable" in str(e)


def test_qfqday_nonempty_does_not_fallback():
    sec_data = {
        "data": {
            "688248.SZ": {
                "qfqday": [["2026-05-08", 40.00, 40.50, 41.00, 39.50, 20000]],
                "day": [
                    ["2026-02-01", 30.00, 30.50, 31.00, 29.50, 10000],
                    ["2026-02-02", 30.50, 31.00, 31.50, 30.00, 12000],
                ],
            }
        }
    }
    bars = build_bars_from(sec_data, "688248.SZ")
    assert len(bars) == 1
    assert bars[0]["close"] == 40.50
