"""Plugin registry for managing indicator plugins.

Central registry that discovers, registers, and orchestrates analysis plugins.
The fusion layer consumes plugin results from this registry.

Usage:
    from trader_shared.plugin_registry import get_registry
    registry = get_registry()
    results = registry.analyze_all(current, bars, change_pct, quote)
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin
from trader_shared._logging import get_logger

_logger = get_logger(__name__)


class PluginRegistry:
    """Registry for indicator plugins.

    Manages plugin lifecycle: register, discover, run all, get by name.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, IndicatorPlugin] = {}

    def register(self, plugin: IndicatorPlugin) -> None:
        """Register a plugin. Overwrites if name already exists."""
        name = plugin.name()
        self._plugins[name] = plugin
        _logger.debug("Plugin registered: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a plugin by name."""
        self._plugins.pop(name, None)

    def get(self, name: str) -> IndicatorPlugin | None:
        """Get a plugin by name, or None if not found."""
        return self._plugins.get(name)

    def names(self) -> list[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def analyze_all(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Run all registered plugins and return their results.

        Args:
            current: Current stock price
            bars: Daily K-line bars
            change_pct: Today's change percentage
            quote: Real-time quote dict

        Returns:
            Dict mapping plugin name → analysis result dict
        """
        results: dict[str, dict[str, Any]] = {}
        for name, plugin in self._plugins.items():
            try:
                result = plugin.analyze(current, bars, change_pct, quote)
                if isinstance(result, dict):
                    results[name] = result
                else:
                    _logger.warning("Plugin %s returned non-dict: %s", name, type(result))
            except Exception as exc:
                _logger.warning("Plugin %s failed: %s", name, exc)
                results[name] = {
                    "direction": 0,
                    "confidence": 0.0,
                    "reason": f"{name}分析异常: {exc}",
                }
        return results

    def get_weights(self) -> dict[str, float]:
        """Get weights for all registered plugins.

        Returns:
            Dict mapping plugin name → weight (default 1.0)
        """
        return {name: plugin.weight() for name, plugin in self._plugins.items()}


# ── Global registry (singleton) ──

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the global plugin registry (lazy init with auto-registration)."""
    global _registry
    if _registry is not None:
        return _registry
    _registry = PluginRegistry()
    _auto_register(_registry)
    return _registry


def set_registry(registry: PluginRegistry) -> None:
    """Replace the global plugin registry."""
    global _registry
    _registry = registry


def _auto_register(registry: PluginRegistry) -> None:
    """Auto-register built-in plugins if available."""
    # Chanlun plugin
    try:
        from trader_shared.plugins.chan_plugin import ChanlunPlugin
        registry.register(ChanlunPlugin())
    except ImportError:
        _logger.debug("ChanlunPlugin not available")

    # Wyckoff plugin
    try:
        from trader_shared.plugins.wyckoff_plugin import WyckoffPlugin
        registry.register(WyckoffPlugin())
    except ImportError:
        _logger.debug("WyckoffPlugin not available")

    # Momentum plugin
    try:
        from trader_shared.plugins.momentum_plugin import MomentumPlugin
        registry.register(MomentumPlugin())
    except ImportError:
        _logger.debug("MomentumPlugin not available")

    # Supertrend plugin (展示型，不进融合)
    try:
        from trader_shared.plugins.supertrend_plugin import SupertrendPlugin
        registry.register(SupertrendPlugin())
    except ImportError:
        _logger.debug("SupertrendPlugin not available")

    # VWAP plugin (展示型，不进融合)
    try:
        from trader_shared.plugins.vwap_plugin import VwapPlugin
        registry.register(VwapPlugin())
    except ImportError:
        _logger.debug("VwapPlugin not available")
