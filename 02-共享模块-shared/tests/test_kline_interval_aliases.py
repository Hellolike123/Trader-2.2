"""C-01：分钟周期别名 — ``30`` 不得默默落到 5m。"""
from __future__ import annotations

from trader_shared.light_data import (
    _resolve_akshare_kline_period,
    _resolve_mootdx_category_key,
    _resolve_sina_kline_scale,
)


def test_c01_bare_30_resolves_to_30_not_5():
    assert _resolve_sina_kline_scale("30") == "30"
    assert _resolve_sina_kline_scale("30m") == "30"
    assert _resolve_akshare_kline_period("30") == "30"
    assert _resolve_akshare_kline_period("30m") == "30"
    assert _resolve_mootdx_category_key("30") == "30m"
    assert _resolve_mootdx_category_key("30m") == "30m"


def test_c01_common_minute_aliases():
    for bare, scale in (("1", "1"), ("5", "5"), ("15", "15"), ("60", "60")):
        assert _resolve_sina_kline_scale(bare) == scale
        assert _resolve_sina_kline_scale(f"{bare}m") == scale
        assert _resolve_akshare_kline_period(bare) == scale
        assert _resolve_mootdx_category_key(bare) == f"{bare}m"


def test_c01_weekly_monthly_specials():
    assert _resolve_sina_kline_scale("weekly") == "1200"
    assert _resolve_sina_kline_scale("monthly") == "7200"
    assert _resolve_akshare_kline_period("weekly") == "weekly"
    assert _resolve_mootdx_category_key("weekly") == "weekly"
