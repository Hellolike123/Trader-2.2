"""Chanlun (缠论) indicator plugin.

Wraps chan_core.py chanlun_strategy() behind the IndicatorPlugin interface.
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin


class ChanlunPlugin(IndicatorPlugin):
    """Chanlun analysis plugin — detects buy points, divergences, and trend labels."""

    def name(self) -> str:
        return "chanlun"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
        weekly_bars: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from trader_shared.chan_core import chanlun_strategy
        # ADR-002：透传 weekly_bars，保证 analyze_all 路径与 build_report 直算等价
        return chanlun_strategy(current, bars, change_pct, quote, weekly_bars=weekly_bars)

    def weight(self) -> float:
        return 0.45  # Default weight in fusion (matches existing chan weight)
