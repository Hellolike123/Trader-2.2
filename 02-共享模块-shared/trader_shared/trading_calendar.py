"""中国股市交易日历 — 节假日判断与交易时段检查。

硬编码 2025-2027 年已知法定节假日（不含周末）。
每年年底需更新下一年节假日集合。

用法:
    from trader_shared.trading_calendar import is_trading_day, is_trading_time
"""

from __future__ import annotations

from datetime import date, datetime

# ── 中国股市法定节假日（不含周末）───────────────────────────────────────────
# 每年年底由证监会公布下一年节假日安排后更新此集合。
# ⚠️ 请在每年 12 月底前更新下一年节假日！
CHINA_HOLIDAYS_2025_2027: set[date] = {
    # ── 2025 ──
    date(2025, 1, 1),   # 元旦
    date(2025, 1, 28),  # 春节
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 1, 31),
    date(2025, 2, 1),
    date(2025, 2, 2),
    date(2025, 2, 3),
    date(2025, 2, 4),
    date(2025, 4, 4),   # 清明节
    date(2025, 4, 5),
    date(2025, 4, 6),
    date(2025, 5, 1),   # 劳动节
    date(2025, 5, 2),
    date(2025, 5, 3),
    date(2025, 5, 4),
    date(2025, 5, 5),
    date(2025, 5, 31),  # 端午节
    date(2025, 6, 1),
    date(2025, 6, 2),
    date(2025, 10, 1),  # 国庆节
    date(2025, 10, 2),
    date(2025, 10, 3),
    date(2025, 10, 4),
    date(2025, 10, 5),
    date(2025, 10, 6),
    date(2025, 10, 7),
    # ── 2026 ──
    date(2026, 1, 1),   # 元旦
    date(2026, 1, 2),
    date(2026, 1, 3),
    date(2026, 2, 17),  # 春节
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 21),
    date(2026, 2, 22),
    date(2026, 2, 23),
    date(2026, 4, 5),   # 清明节
    date(2026, 4, 6),
    date(2026, 4, 7),
    date(2026, 5, 1),   # 劳动节
    date(2026, 5, 2),
    date(2026, 5, 3),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 6, 19),  # 端午节
    date(2026, 6, 20),
    date(2026, 6, 21),
    date(2026, 10, 1),  # 国庆节
    date(2026, 10, 2),
    date(2026, 10, 3),
    date(2026, 10, 4),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 7),
    date(2026, 10, 8),
    # ── 2027 ──（待证监会公布后更新，此处为预估）
    date(2027, 1, 1),   # 元旦
    date(2027, 1, 2),
    date(2027, 1, 3),
    date(2027, 2, 6),   # 春节（预估）
    date(2027, 2, 7),
    date(2027, 2, 8),
    date(2027, 2, 9),
    date(2027, 2, 10),
    date(2027, 2, 11),
    date(2027, 2, 12),
    date(2027, 4, 5),   # 清明节
    date(2027, 4, 6),
    date(2027, 4, 7),
    date(2027, 5, 1),   # 劳动节
    date(2027, 5, 2),
    date(2027, 5, 3),
    date(2027, 5, 4),
    date(2027, 5, 5),
    date(2027, 6, 9),   # 端午节（预估）
    date(2027, 6, 10),
    date(2027, 6, 11),
    date(2027, 10, 1),  # 国庆节
    date(2027, 10, 2),
    date(2027, 10, 3),
    date(2027, 10, 4),
    date(2027, 10, 5),
    date(2027, 10, 6),
    date(2027, 10, 7),
}


def is_trading_day(d: date | None = None) -> bool:
    """判断指定日期是否是交易日（非周末且非节假日）。

    Args:
        d: 要检查的日期，默认今天

    Returns:
        True 如果是交易日
    """
    d = d or date.today()
    if d.weekday() >= 5:
        return False
    return d not in CHINA_HOLIDAYS_2025_2027


def is_trading_time() -> bool:
    """判断当前是否是交易时间（9:25-11:30, 13:00-15:00，非交易日返回 False）。

    与 light_data.is_trading_time() 语义一致，但增加了节假日检查。
    """
    now = datetime.now()
    if not is_trading_day(now.date()):
        return False
    current_time = now.hour * 100 + now.minute
    return (925 <= current_time <= 1130) or (1300 <= current_time <= 1500)


def next_trading_open(from_dt: datetime | None = None) -> datetime:
    """计算下一个交易日开盘时间（9:25）。

    Args:
        from_dt: 起始时间，默认当前时间

    Returns:
        下一个交易日 9:25 的 datetime
    """
    from datetime import timedelta
    now = from_dt or datetime.now()
    # 如果今天是交易日且还没到 9:25，返回今天 9:25
    if is_trading_day(now.date()) and now.hour * 100 + now.minute < 925:
        return now.replace(hour=9, minute=25, second=0, microsecond=0)
    # 否则找下一个交易日
    d = now.date() + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 9, 25, 0)
