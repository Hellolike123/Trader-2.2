"""Plugin base classes for indicator analysis.

Defines the IndicatorPlugin ABC that all analysis plugins must implement.
Plugins are self-contained analysis units that can be registered and composed.
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin

# Re-export for convenience
__all__ = ["IndicatorPlugin"]
