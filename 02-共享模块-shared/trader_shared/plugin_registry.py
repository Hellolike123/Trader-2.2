"""Plugin registry for managing indicator plugins.

Central registry that discovers, registers, and orchestrates analysis plugins.
The fusion layer consumes plugin results from this registry.

Usage:
    from trader_shared.plugin_registry import get_registry
    registry = get_registry()
    results = registry.analyze_all(current, bars, change_pct, quote)
"""
from __future__ import annotations

import inspect
from typing import Any

from trader_shared.interfaces import IndicatorPlugin
from trader_shared._logging import get_logger

_logger = get_logger(__name__)


def _plugin_accepts_supertrend_direction(fn) -> bool:
    """检测插件 analyze 是否接受 supertrend_direction 关键字参数。

    旧插件（如 chan/wyckoff 展示插件）签名不含该参数，不能透传，否则 TypeError。
    含 **kwargs 的插件视为兼容。
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return True
    return "supertrend_direction" in sig.parameters


def _plugin_accepts_weekly_bars(fn) -> bool:
    """检测插件 analyze 是否接受 weekly_bars 关键字参数（ADR-002 透传）。

    含 **kwargs 的插件视为兼容；否则仅当签名显式声明 weekly_bars 才透传，
    避免对未升级插件造成 TypeError。
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return True
    return "weekly_bars" in sig.parameters


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
        supertrend_direction: str | None = None,
        weekly_bars: list[dict[str, Any]] | None = None,
        midline: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Run all registered plugins and return their results.

        Args:
            current: Current stock price
            bars: Daily K-line bars
            change_pct: Today's change percentage
            quote: Real-time quote dict
            supertrend_direction: Supertrend 趋势带方向（"up"/"down"/None）。
                用于方案 B「只确认不否决」微调：若未传入，则内部基于 bars 自动计算
                （与 build_report 直算路径一致）。仅透传给显式声明接受该参数的插件
                （当前为 momentum），避免破坏其他插件签名。
            weekly_bars: 周 K 线（中线主分析 / 日线 chan 的 higher_trend 过滤）。
                透传给所有声明接受该参数的插件（当前为 chan），保证 analyze_all 路径
                与 build_report 直算路径日线 chan 结果等价（ADR-002 等价性闸门关键）。
            midline: 是否额外产出中线结果（chanlun_midline / wyckoff_midline）。
                仅 build_report 路由时传 True；fusion_core / final_pool / review 的
                analyze_all 调用不传，故中线计算不波及这些调用方（最小爆炸半径）。

        Returns:
            Dict mapping plugin name → analysis result dict。midline=True 时额外含
            "chanlun_midline" / "wyckoff_midline" 键。
        """
        # 方案 B（P1-1）：registry 路径也应触发动量「只确认不否决」微调。
        # build_report 现在也走 analyze_all（ADR-002），动量 nudge 由 MomentumPlugin
        # 统一完成，避免 build_report 二次 nudge 导致 weighted_score 漂移。
        if supertrend_direction is None:
            try:
                from trader_shared.indicator_math import calc_supertrend
                supertrend_direction = calc_supertrend(bars).get("direction")
            except Exception:
                supertrend_direction = None

        results: dict[str, dict[str, Any]] = {}
        for name, plugin in self._plugins.items():
            try:
                extra = {}
                if _plugin_accepts_supertrend_direction(plugin.analyze):
                    extra["supertrend_direction"] = supertrend_direction
                if _plugin_accepts_weekly_bars(plugin.analyze):
                    extra["weekly_bars"] = weekly_bars
                result = plugin.analyze(current, bars, change_pct, quote, **extra)
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

        # ── ADR-002 中线分支：仅 midline=True 时产出，避免波及 fusion_core 等调用方 ──
        if midline:
            try:
                from trader_shared.chan_core import chanlun_strategy_midline
                results["chanlun_midline"] = chanlun_strategy_midline(
                    current, weekly_bars, bars, change_pct, quote
                ) or {}
            except Exception as exc:
                _logger.warning("midline chanlun failed: %s", exc)
                results["chanlun_midline"] = {
                    "direction": 0, "confidence": 0.0,
                    "reason": f"中线缠论异常: {exc}",
                }
            try:
                from trader_shared.wyckoff_core import wyckoff_strategy_midline
                results["wyckoff_midline"] = wyckoff_strategy_midline(
                    current, weekly_bars, bars, change_pct, quote
                ) or {}
            except Exception as exc:
                _logger.warning("midline wyckoff failed: %s", exc)
                results["wyckoff_midline"] = {
                    "direction": 0, "confidence": 0.0,
                    "reason": f"中线威科夫异常: {exc}",
                }

        return results

    def get_weights(self) -> dict[str, float]:
        """Get weights for all registered plugins.

        Returns:
            Dict mapping plugin name → weight (default 1.0)
        """
        return {name: plugin.weight() for name, plugin in self._plugins.items()}

    # ---- 分层查询接口 ---------------------------------------------------

    def is_display_only(self, name: str) -> bool:
        """Return True if the named plugin is marked display_only.

        判断方式（优先级从高到低）:
        1. 插件实例 attribute `display_only` （如果实例自带）
        2. 插件模块级 `display_only` 变量（即 vwap_plugin.display_only）
        3. weight() == 0.0 且实例内部属性 display_only 设为 True。4.默认返回 False
        """
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        # 1. 实例自带属性
        if getattr(plugin, "display_only", None) is True:
            return True
        # 2. 模块级属性
        import sys
        mod = sys.modules.get(type(plugin).__module__)
        if mod is not None and getattr(mod, "display_only", None) is True:
            return True
        # 3. weight==0 且实例 dict内 display_only=True
        try:
            if plugin.weight() == 0.0:
                # 尝试调用空数据查看返回结果中是否含 display_only
                pass
        except Exception:
            pass
        return False

    def get_decision_plugin_names(self) -> list[str]:
        """Return names of decision plugins (display_only=False, participate in fusion)."""
        return [name for name in self._plugins if not self.is_display_only(name)]

    def get_display_plugin_names(self) -> list[str]:
        """Return names of display-only plugins (do not affect fusion score)."""
        return [name for name in self._plugins if self.is_display_only(name)]



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
