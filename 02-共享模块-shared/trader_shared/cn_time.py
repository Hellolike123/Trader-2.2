"""A 股墙钟：统一 Asia/Shanghai，避免主机非东八区时盘中/日历错位。"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> datetime:
    """当前上海墙钟（naive），与行情 bar 的无时区时间戳可比。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)


def today_cn() -> date:
    """当前上海自然日。"""
    return now_cn().date()
