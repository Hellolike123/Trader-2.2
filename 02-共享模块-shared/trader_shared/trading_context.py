"""集中式交易时间感知层 — 统一节假日日历、交易时段、数据新鲜度判断。

用法:
    from trader_shared.trading_context import is_trading_day, is_trading_time, current_session, data_freshness
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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


def _last_trading_day(as_of: date) -> date:
    """返回 as_of 当天或之前最近的交易日。"""
    d = as_of
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def compute_data_freshness(last_data_date: date | str | None, as_of: date | datetime | None = None) -> str:
    """数据是否最新可用：最后数据日期覆盖到「应有数据的交易日」→ live，否则 stale。

    应有数据的交易日判定：
    - 交易日盘中/盘后：当天
    - 交易日盘前（< 9:25）：昨天（今天尚未开盘，最新可用 = 昨收盘）
    - 非交易日：最近交易日
    只有数据停留在更早（停牌、断更多日）才标 stale。
    """
    if last_data_date is None:
        return "stale"
    if isinstance(last_data_date, str):
        try:
            last_data_date = datetime.strptime(last_data_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return "stale"
    as_of = as_of or datetime.now()
    as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
    # 盘前：今天尚未开盘，允许数据停留在昨天
    if isinstance(as_of, datetime) and is_trading_day(as_of_date):
        if as_of.hour < 9 or (as_of.hour == 9 and as_of.minute < 25):
            as_of_date = _last_trading_day(as_of_date - timedelta(days=1))
    expected = _last_trading_day(as_of_date)
    return "live" if last_data_date >= expected else "stale"
