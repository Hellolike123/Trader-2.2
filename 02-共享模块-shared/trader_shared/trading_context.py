"""集中式交易时间感知层 — 统一节假日日历、交易时段、数据新鲜度判断。

用法:
    from trader_shared.trading_context import is_trading_day, is_trading_time, current_session, data_freshness
"""

from __future__ import annotations

from datetime import date, datetime

# 复用 trading_calendar 的节假日数据和基础判断
from trader_shared.trading_calendar import (
    CHINA_HOLIDAYS_2025_2027,
    is_trading_day,
    next_trading_open,
)


def is_trading_time() -> bool:
    """判断当前是否是交易时间（9:25-11:30, 13:00-15:00，非交易日返回 False）。"""
    now = datetime.now()
    if not is_trading_day(now.date()):
        return False
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1130) or (1300 <= t <= 1500)


def current_session() -> str:
    """返回当前所处的交易时段。

    Returns:
        "pre_market"   — 盘前（交易日 0:00-9:24）
        "trading"      — 盘中（9:25-11:30, 13:00-15:00）
        "lunch_break"  — 午休（11:31-12:59）
        "post_market"  — 盘后（15:01-23:59）
        "non_trading"  — 非交易日
    """
    now = datetime.now()
    if not is_trading_day(now.date()):
        return "non_trading"
    t = now.hour * 100 + now.minute
    if t < 925:
        return "pre_market"
    if 925 <= t <= 1130:
        return "trading"
    if 1131 <= t <= 1259:
        return "lunch_break"
    if 1300 <= t <= 1500:
        return "trading"
    return "post_market"


def data_freshness() -> str:
    """返回当前数据的新鲜度标签。

    Returns:
        "live"  — 盘中，数据实时
        "stale" — 非交易时段，数据可能过期
    """
    return "live" if is_trading_time() else "stale"
