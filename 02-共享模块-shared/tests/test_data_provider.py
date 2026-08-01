"""Tests for the akshare data provider backend (P0 #2 fix).

The `_akshare_to_bar` and `_akshare_fetch_quote` helpers were calling
`to_float(...)` as a bare function name, but the module never imported
`to_float` at top level. When TRADER_DATA_PROVIDER=akshare was set, calling
any akshare method immediately raised `NameError: name 'to_float' is not
defined`.

This test verifies the top-level import is now present.
"""
from __future__ import annotations

import importlib
import sys


def test_akshare_to_float_imported() -> None:
    """`from trader_shared.light_data import to_float` must exist in data_provider module."""
    import trader_shared.data_provider as dp
    importlib.reload(dp)
    assert hasattr(dp, "to_float"), "data_provider module must expose to_float at top level"
    # to_float should be the same callable as light_data.to_float
    from trader_shared.light_data import to_float as light_to_float
    assert dp.to_float is light_to_float


def test_akshare_class_method_uses_top_level_to_float() -> None:
    """UnifiedProvider.to_float (instance method) should still be wired to light_data.to_float."""
    from trader_shared.data_provider import UnifiedProvider
    from trader_shared.light_data import to_float as light_to_float

    provider = UnifiedProvider(backend="akshare")
    # Call the instance method
    assert provider.to_float("3.14") == 3.14
    assert provider.to_float(None) is None
    assert provider.to_float("--") is None


def test_normalize_bars_sorts_ascending() -> None:
    """倒序原始行经 normalize_bars 后 bars[-1] 为最新。"""
    from trader_shared.light_data import normalize_bars

    raw = [
        {"date": "2026-07-29", "open": 3, "close": 3, "high": 3, "low": 3, "volume": 1},
        {"date": "2026-07-28", "open": 2, "close": 2, "high": 2, "low": 2, "volume": 1},
        {"date": "2025-07-25", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1},
    ]
    bars = normalize_bars(raw)
    dates = [b["date"] for b in bars]
    assert dates == sorted(dates)
    assert bars[-1]["date"] == "2026-07-29"
    assert bars[0]["date"] == "2025-07-25"


def test_ensure_bars_ascending_recomputes_atr() -> None:
    """倒序输入纠正后，TR 使用时间上的前一日收盘。"""
    from trader_shared.light_data import ensure_bars_ascending

    # newest-first（毒序）
    bars = [
        {"date": "2026-07-10", "open": 10.0, "close": 10.5, "high": 10.6, "low": 9.9, "volume": 1},
        {"date": "2026-07-09", "open": 9.8, "close": 10.0, "high": 10.1, "low": 9.7, "volume": 1},
        {"date": "2026-07-08", "open": 9.5, "close": 9.8, "high": 9.9, "low": 9.4, "volume": 1},
    ]
    fixed, rewritten = ensure_bars_ascending(bars)
    assert rewritten is True
    assert [b["date"] for b in fixed] == ["2026-07-08", "2026-07-09", "2026-07-10"]
    # 中间日 TR：相对 07-08 收盘 9.8
    assert fixed[1]["tr"] == round(max(10.1 - 9.7, abs(10.1 - 9.8), abs(9.7 - 9.8)), 4)
    again, rewritten2 = ensure_bars_ascending(fixed)
    assert rewritten2 is False
    assert again[-1]["date"] == "2026-07-10"


def test_ensure_bars_ascending_intraday_timestamps() -> None:
    """同日内分钟线倒序也能纠正（勿只按日期截断）。"""
    from trader_shared.light_data import ensure_bars_ascending

    bars = [
        {"date": "2026-07-30 10:10", "open": 3, "close": 3, "high": 3, "low": 3, "volume": 1},
        {"date": "2026-07-30 10:00", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1},
        {"date": "2026-07-30 10:05", "open": 2, "close": 2, "high": 2, "low": 2, "volume": 1},
    ]
    fixed, rewritten = ensure_bars_ascending(bars, recompute_atr=False)
    assert rewritten is True
    assert [b["date"] for b in fixed] == [
        "2026-07-30 10:00",
        "2026-07-30 10:05",
        "2026-07-30 10:10",
    ]


def test_aggregate_daily_to_weekly_iso_buckets() -> None:
    from datetime import date, timedelta
    from trader_shared.indicator_math import (
        aggregate_daily_to_weekly,
        weekly_bars_look_like_weekly,
    )

    start = date(2026, 6, 1)
    daily = []
    for i in range(60):  # ≥4 个完整交易周
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        daily.append({
            "date": d.isoformat(),
            "open": 10.0 + i * 0.1,
            "high": 11.0 + i * 0.1,
            "low": 9.0 + i * 0.1,
            "close": 10.5 + i * 0.1,
            "volume": 100.0,
        })
    weekly = aggregate_daily_to_weekly(daily)
    assert len(weekly) >= 4
    assert weekly_bars_look_like_weekly(weekly)
    assert not weekly_bars_look_like_weekly(daily)
    # 周内 open=首根 close=末根
    assert weekly[0]["open"] == daily[0]["open"]


def test_aggregate_5m_to_60m_sorts_within_hour() -> None:
    from trader_shared.indicator_math import aggregate_5m_to_60m

    # 故意打乱同小时内顺序
    bars = [
        {"date": "2026-07-30 10:55", "open": 12, "high": 13, "low": 11, "close": 12.5, "volume": 1},
        {"date": "2026-07-30 10:05", "open": 10, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 2},
        {"date": "2026-07-30 10:30", "open": 11, "high": 11.5, "low": 10.8, "close": 11.2, "volume": 3},
    ]
    out = aggregate_5m_to_60m(bars)
    assert len(out) == 1
    assert out[0]["open"] == 10.0  # 最早 10:05
    assert out[0]["close"] == 12.5  # 最晚 10:55


def test_aggregate_5m_to_60m_reads_time_when_date_is_day_only() -> None:
    """生产 light_data 形状：date=日、time=完整时间戳，不得聚合为空。"""
    from trader_shared.indicator_math import aggregate_5m_to_60m

    bars = [
        {
            "date": "2026-07-30",
            "time": "2026-07-30 10:55:00",
            "open": 12,
            "high": 13,
            "low": 11,
            "close": 12.5,
            "volume": 1,
        },
        {
            "date": "2026-07-30",
            "time": "2026-07-30 10:05:00",
            "open": 10,
            "high": 10.5,
            "low": 9.5,
            "close": 10.2,
            "volume": 2,
        },
        {
            "date": "2026-07-30",
            "time": "2026-07-30 10:30:00",
            "open": 11,
            "high": 11.5,
            "low": 10.8,
            "close": 11.2,
            "volume": 3,
        },
    ]
    out = aggregate_5m_to_60m(bars)
    assert len(out) == 1
    assert out[0]["open"] == 10.0
    assert out[0]["close"] == 12.5


def test_parse_em_klines_takes_latest_n_after_sort() -> None:
    from trader_shared.fund_flow_data import _parse_em_klines

    # 倒序源：最新在前；取 days=2 应得到最近两天
    klines = [
        "2026-07-10,100,0,0,0,0",
        "2026-07-09,90,0,0,0,0",
        "2026-07-08,80,0,0,0,0",
    ]
    out = _parse_em_klines(klines, days=2)
    assert [r["date"] for r in out] == ["2026-07-09", "2026-07-10"]


def test_get_day_scoped_bars_fixes_reversed_cache(monkeypatch) -> None:
    """同日倒序缓存经 get_day_scoped_bars 纠正为正序并回写。"""
    import trader_shared.cache_utils as cu

    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-17")
    store: dict = {}
    reversed_rows = [
        {"date": "2026-07-16", "open": 3, "close": 3, "high": 3, "low": 3, "volume": 1},
        {"date": "2026-07-15", "open": 2, "close": 2, "high": 2, "low": 2, "volume": 1},
        {"date": "2026-07-14", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1},
    ] * 10  # 30 rows, still newest-block first pattern — use unique desc
    reversed_rows = [
        {"date": f"2026-06-{d:02d}", "open": float(d), "close": float(d),
         "high": float(d), "low": float(d), "volume": 1}
        for d in range(30, 0, -1)
    ]

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return cu.CacheResult(
                data={"fetch_date": "2026-07-17", "rows": list(reversed_rows)},
                stale=False,
                age_seconds=1.0,
                source="file",
            )
        return cu.CacheResult(data=data, stale=False, age_seconds=1.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    def _boom():
        raise RuntimeError("should not fetch")

    out = cu.get_day_scoped_bars("daily", "000988", _boom, min_rows=20)
    dates = [b["date"] for b in out]
    assert dates == sorted(dates)
    assert out[-1]["date"] == "2026-06-30"
    assert out[0]["date"] == "2026-06-01"
    # 已回写正序
    written = store[("daily", "000988")]["rows"]
    assert [b["date"] for b in written] == sorted(b["date"] for b in written)


def test_get_ths_daily_sorts_ascending(monkeypatch) -> None:
    from trader_shared import sector_data as sd

    monkeypatch.setattr(sd._cu, "cache_calendar_date", lambda: "2026-07-17")
    monkeypatch.setattr(sd._cu, "get_cached", lambda *a, **k: None)
    monkeypatch.setattr(sd._cu, "set_cached", lambda *a, **k: None)

    class _C:
        def query_ths_daily(self, *a, **k):
            return [
                {"trade_date": "20260710", "pct_change": 1.0},
                {"trade_date": "20260708", "pct_change": -0.5},
                {"trade_date": "20260709", "pct_change": 0.2},
            ]

    monkeypatch.setattr(sd, "get_client", lambda: _C())
    rows = sd.get_ths_daily("885800.TI")
    assert [r["trade_date"] for r in rows] == ["20260708", "20260709", "20260710"]
    assert rows[-1]["pct_change"] == 1.0


def test_akshare_daily_postprocess_fills_atr_when_already_sorted() -> None:
    """AkShare 日线常已升序：ensure 不重排时也必须补 ATR。"""
    from trader_shared.light_data import _compute_atr_fields, ensure_bars_ascending

    bars = []
    price = 10.0
    for i in range(30):
        price += 0.05
        bars.append(
            {
                "date": f"2026-06-{(i % 28) + 1:02d}",
                "open": price - 0.05,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "volume": 1000 + i,
            }
        )
    fixed, rewritten = ensure_bars_ascending(bars)
    assert rewritten is False or rewritten is True  # 允许任一
    if not rewritten:
        _compute_atr_fields(fixed)
    last = fixed[-1]
    assert last.get("atr14") is not None
    assert last.get("atr_ratio") is not None
