"""Wyckoff (威科夫) indicator plugin.

Wraps wyckoff_core.py wyckoff_strategy() behind the IndicatorPlugin interface.
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin


class WyckoffPlugin(IndicatorPlugin):
    """Wyckoff analysis plugin — detects Spring, Upthrust, and volume divergences."""

    def name(self) -> str:
        return "wyckoff"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
        weekly_bars: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from trader_shared.wyckoff_core import wyckoff_strategy

        symbol = ""
        if isinstance(quote, dict):
            symbol = str(
                quote.get("symbol") or quote.get("ts_code") or quote.get("code") or ""
            ).strip()
        return wyckoff_strategy(current, bars, change_pct, quote, symbol=symbol)

    def weight(self) -> float:
        return 0.35  # Default weight in fusion (matches existing wyckoff weight)
