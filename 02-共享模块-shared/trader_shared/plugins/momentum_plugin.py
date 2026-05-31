"""Momentum (动量) indicator plugin.

Wraps momentum_core.py momentum_strategy() behind the IndicatorPlugin interface.
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin


class MomentumPlugin(IndicatorPlugin):
    """Momentum analysis plugin — RSI, MACD, ADX, Bollinger Bands."""

    def name(self) -> str:
        return "momentum"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
    ) -> dict[str, Any]:
        from trader_shared.momentum_core import momentum_strategy
        return momentum_strategy(current, bars, change_pct, quote)

    def weight(self) -> float:
        return 0.20  # Default weight in fusion (matches existing momentum weight)
