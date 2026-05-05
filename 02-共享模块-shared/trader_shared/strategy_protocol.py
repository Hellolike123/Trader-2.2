"""Minimal strategy protocol for pluggable analysis strategies.

A strategy is a callable with signature:

    def strategy(current: float, bars: list[dict], change_pct: Any, quote: dict) -> dict:
        '''Return {levels, verdict, signals, ...}'''

Strategies are composed by calling them in sequence and merging their results.
The contract is intentionally minimal — no classes, no registries, no framework.
"""

from __future__ import annotations

from typing import Any


def run_all(
    current: float,
    bars: list[dict[str, Any]],
    change_pct: Any,
    quote: dict[str, Any],
    *strategies: Any,
) -> dict[str, Any]:
    """Run strategies in order and merge results. Later strategies override earlier keys."""
    result: dict[str, Any] = {}
    for fn in strategies:
        try:
            chunk = fn(current, bars, change_pct, quote)
            if isinstance(chunk, dict):
                result.update(chunk)
        except Exception:
            continue
    return result
