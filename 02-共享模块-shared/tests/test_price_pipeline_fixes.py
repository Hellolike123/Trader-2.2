"""取价/算价修复回归：市场前缀、merge trade_date、sanitize、session VWAP、live_bar。"""
from __future__ import annotations

from datetime import datetime


def test_infer_a_share_market_etf_and_stock():
    from trader_shared.light_data import infer_a_share_market, resolve_security

    assert infer_a_share_market("510050") == "SH"
    assert infer_a_share_market("588000") == "SH"
    assert infer_a_share_market("159915") == "SZ"
    assert infer_a_share_market("688248") == "SH"
    assert infer_a_share_market("002050") == "SZ"
    assert infer_a_share_market("430047") == "BJ"

    sec = resolve_security("510050")
    assert sec.market == "SH"
    assert sec.qq_symbol == "sh510050"
    assert sec.ts_code == "510050.SH"

    sec2 = resolve_security("159915")
    assert sec2.market == "SZ"
    assert sec2.qq_symbol.startswith("sz")


def test_merge_uses_trade_date_not_wall_clock():
    from trader_shared.cache_utils import merge_daily_bars_with_quote

    bars = [
        {"date": "2026-07-25", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1},
        {"date": "2026-07-28", "open": 10.5, "high": 11, "low": 10, "close": 10.8, "volume": 1},
    ]
    quote = {
        "trade_date": "2026-07-28",
        "current_price": 11.2,
        "open": 10.9,
        "high": 11.5,
        "low": 10.7,
        "volume": 100,
    }
    out = merge_daily_bars_with_quote(bars, quote)
    assert len(out) == 2
    assert out[-1]["date"] == "2026-07-28"
    assert out[-1]["close"] == 11.2
    assert out[-1]["high"] == 11.5


def test_merge_normalizes_yyyymmdd_and_replaces():
    from trader_shared.cache_utils import merge_daily_bars_with_quote

    bars = [
        {"date": "20260725", "close": 10.0, "open": 10, "high": 10, "low": 10, "volume": 1},
        {"date": "2026-07-28", "close": 10.5, "open": 10, "high": 11, "low": 10, "volume": 1},
    ]
    quote = {
        "trade_date": "20260728",
        "current_price": 12.0,
        "open": 11.0,
        "high": 12.5,
        "low": 10.8,
    }
    out = merge_daily_bars_with_quote(bars, quote)
    assert len(out) == 2
    assert out[-1]["close"] == 12.0
    assert out[-1]["date"] == "2026-07-28"


def test_sanitize_keeps_limit_board_range():
    """±20% 宽幅日不得被误杀。"""
    from trader_shared.light_data import sanitize_quote

    q = {
        "current_price": 12.0,
        "pre_close": 10.0,
        "high": 12.0,  # +20% 涨停
        "low": 9.8,
    }
    out = sanitize_quote(dict(q))
    assert out["high"] == 12.0
    assert out["low"] == 9.8


def test_sanitize_clamps_overflow_glitch():
    from trader_shared.light_data import sanitize_quote

    q = {
        "current_price": 59.33,
        "pre_close": 57.5,
        "high": 6_556_720.0,
        "low": 3_195_758.0,
    }
    out = sanitize_quote(q)
    assert out["high"] == 59.33
    assert out["low"] == 59.33


def test_session_5m_bars_drops_undated_and_picks_latest():
    from trader_shared.display_indicators import session_5m_bars

    bars = [
        {"date": "2026-07-27", "time": "14:55", "close": 50, "high": 50, "low": 50, "volume": 1},
        {"date": "2026-07-28", "time": "10:00", "close": 40, "high": 41, "low": 39, "volume": 1},
        {"date": "2026-07-28", "time": "10:05", "close": 40.2, "high": 40.5, "low": 40, "volume": 1},
        {"close": 99, "volume": 1},  # 无日期 → 丢弃
    ]
    out = session_5m_bars(bars)
    assert len(out) == 2
    assert all(b["date"] == "2026-07-28" for b in out)
    assert all(b.get("close") != 99 for b in out)


def test_live_bar_uses_quote_ohlc():
    from trader_shared.report_pipeline import build_live_bar_anchor

    quote = {
        "trade_date": "2026-07-29",
        "current_price": 43.25,
        "pre_close": 41.67,
        "open": 41.68,
        "high": 43.98,
        "low": 40.30,
        "volume": 59758,
        "current_change_pct": 3.79,
    }
    bars = [{"date": "2026-07-28", "close": 41.67, "atr14": 1.2}]
    live, as_of = build_live_bar_anchor(quote, bars)
    assert live is not None
    assert live["open"] == 41.68
    assert live["high"] == 43.98
    assert live["low"] == 40.30
    assert live["close"] == 43.25
    assert live["volume"] == 59758
    assert as_of == "2026-07-28"


def test_t0_today_bars_aligns_with_session():
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2] / "01-功能包-packages" / "t0" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from price_point_engine import today_bars as tb

    bars = [
        {"date": "2026-07-27 14:55:00", "close": 50, "high": 50, "low": 50, "volume": 1},
        {"date": "2026-07-28 10:00:00", "close": 40, "high": 41, "low": 39, "volume": 1},
        {"close": 1, "volume": 1},
    ]
    out = tb(bars)
    assert len(out) == 1
    assert "2026-07-28" in str(out[0].get("date"))
