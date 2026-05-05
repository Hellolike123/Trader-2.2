"""Shared constants common to all trader skills.

Usage (in skill scripts):
    from trader_shared.config import LOOKBACK_DAYS, RECENT_WINDOW, ...
"""
from __future__ import annotations

LOOKBACK_DAYS: int = 30
RECENT_WINDOW: int = 5
CONFIRM_BUFFER: float = 0.02
STOP_BUFFER: float = 0.98
TAKE_PROFIT_BUFFER: float = 1.06
