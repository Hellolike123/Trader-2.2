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
    ) -> dict[str, Any]:
        from trader_shared.chan_core import chanlun_strategy
        return chanlun_strategy(current, bars, change_pct, quote)

    def weight(self) -> float:
        return 0.45  # Default weight in fusion (matches existing chan weight)
