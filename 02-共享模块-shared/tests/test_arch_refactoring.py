"""Tests for DI interfaces, fetchers, plugin registry, and async utils."""

from __future__ import annotations

import pytest
from typing import Any


# ── interfaces.py tests ──

class TestInterfaces:
    """Test abstract interfaces are properly defined."""

    def test_data_fetcher_is_abc(self):
        """DataFetcher cannot be instantiated directly."""
        from trader_shared.interfaces import DataFetcher
        with pytest.raises(TypeError):
            DataFetcher()

    def test_indicator_plugin_is_abc(self):
        """IndicatorPlugin cannot be instantiated directly."""
        from trader_shared.interfaces import IndicatorPlugin
        with pytest.raises(TypeError):
            IndicatorPlugin()

    def test_data_fetcher_has_abstract_methods(self):
        """DataFetcher defines required abstract methods."""
        from trader_shared.interfaces import DataFetcher
        import inspect
        abstract_methods = {
            name for name, method in inspect.getmembers(DataFetcher)
            if getattr(method, '__isabstractmethod__', False)
        }
        assert "fetch_quote" in abstract_methods
        assert "fetch_qfq_daily" in abstract_methods
        assert "fetch_kline" in abstract_methods

    def test_indicator_plugin_has_abstract_methods(self):
        """IndicatorPlugin defines required abstract methods."""
        from trader_shared.interfaces import IndicatorPlugin
        import inspect
        abstract_methods = {
            name for name, method in inspect.getmembers(IndicatorPlugin)
            if getattr(method, '__isabstractmethod__', False)
        }
        assert "name" in abstract_methods
        assert "analyze" in abstract_methods

    def test_indicator_plugin_default_weight(self):
        """IndicatorPlugin.weight() defaults to 1.0."""
        from trader_shared.interfaces import IndicatorPlugin

        class TestPlugin(IndicatorPlugin):
            def name(self) -> str:
                return "test"
            def analyze(self, current, bars, change_pct, quote):
                return {}

        plugin = TestPlugin()
        assert plugin.weight() == 1.0


# ── fetchers.py tests ──

class TestMockFetcher:
    """Test MockFetcher for testing."""

    def test_mock_fetcher_returns_configured_data(self):
        """MockFetcher returns pre-configured data."""
        from trader_shared.fetchers import MockFetcher
        quote = {"current_price": 10.5, "name": "Test"}
        bars = [{"date": "2026-01-01", "close": 10.0}]
        fetcher = MockFetcher(quote=quote, daily_bars=bars)

        assert fetcher.fetch_quote("000001") == quote
        assert fetcher.fetch_qfq_daily("000001") == bars
        assert fetcher.fetch_kline("000001") == []
        assert fetcher.name == "mock"

    def test_mock_fetcher_returns_copies(self):
        """MockFetcher returns copies, not references."""
        from trader_shared.fetchers import MockFetcher
        quote = {"current_price": 10.5}
        fetcher = MockFetcher(quote=quote)

        q1 = fetcher.fetch_quote("000001")
        q2 = fetcher.fetch_quote("000001")
        assert q1 == q2
        assert q1 is not q2  # Different objects

    def test_tencent_fetcher_name(self):
        """TencentFetcher has correct name."""
        from trader_shared.fetchers import TencentFetcher
        fetcher = TencentFetcher()
        assert fetcher.name == "tencent"

    def test_sina_fetcher_name(self):
        """SinaFetcher has correct name."""
        from trader_shared.fetchers import SinaFetcher
        fetcher = SinaFetcher()
        assert fetcher.name == "sina"


class TestFetcherGlobalState:
    """Test global fetcher state management."""

    def test_get_fetcher_returns_default(self):
        """get_fetcher() returns TencentFetcher by default."""
        from trader_shared.fetchers import get_fetcher, TencentFetcher, set_fetcher
        # Reset to default
        set_fetcher(TencentFetcher())
        fetcher = get_fetcher()
        assert fetcher.name == "tencent"

    def test_set_fetcher_replaces_default(self):
        """set_fetcher() replaces the global default."""
        from trader_shared.fetchers import MockFetcher, get_fetcher, set_fetcher
        mock = MockFetcher(quote={"test": True})
        set_fetcher(mock)
        assert get_fetcher().name == "mock"
        # Reset
        from trader_shared.fetchers import TencentFetcher
        set_fetcher(TencentFetcher())


# ── plugin_registry.py tests ──

class TestPluginRegistry:
    """Test plugin registry functionality."""

    def test_register_and_get(self):
        """Register a plugin and retrieve it by name."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class TestPlugin(IndicatorPlugin):
            def name(self): return "test"
            def analyze(self, current, bars, change_pct, quote):
                return {"direction": 1, "confidence": 0.5, "reason": "test"}

        registry = PluginRegistry()
        plugin = TestPlugin()
        registry.register(plugin)

        assert registry.get("test") is plugin
        assert registry.get("nonexistent") is None

    def test_names(self):
        """names() returns all registered plugin names."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class PluginA(IndicatorPlugin):
            def name(self): return "a"
            def analyze(self, current, bars, change_pct, quote): return {}

        class PluginB(IndicatorPlugin):
            def name(self): return "b"
            def analyze(self, current, bars, change_pct, quote): return {}

        registry = PluginRegistry()
        registry.register(PluginA())
        registry.register(PluginB())

        assert set(registry.names()) == {"a", "b"}

    def test_unregister(self):
        """unregister() removes a plugin."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class TestPlugin(IndicatorPlugin):
            def name(self): return "test"
            def analyze(self, current, bars, change_pct, quote): return {}

        registry = PluginRegistry()
        registry.register(TestPlugin())
        assert registry.get("test") is not None

        registry.unregister("test")
        assert registry.get("test") is None

    def test_analyze_all(self):
        """analyze_all() runs all plugins and returns results."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class PluginA(IndicatorPlugin):
            def name(self): return "a"
            def analyze(self, current, bars, change_pct, quote):
                return {"direction": 1, "confidence": 0.7}

        class PluginB(IndicatorPlugin):
            def name(self): return "b"
            def analyze(self, current, bars, change_pct, quote):
                return {"direction": -1, "confidence": 0.3}

        registry = PluginRegistry()
        registry.register(PluginA())
        registry.register(PluginB())

        results = registry.analyze_all(10.0, [], 0.0, {})
        assert "a" in results
        assert "b" in results
        assert results["a"]["direction"] == 1
        assert results["b"]["direction"] == -1

    def test_analyze_all_handles_exceptions(self):
        """analyze_all() catches plugin exceptions gracefully."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class BadPlugin(IndicatorPlugin):
            def name(self): return "bad"
            def analyze(self, current, bars, change_pct, quote):
                raise ValueError("plugin error")

        registry = PluginRegistry()
        registry.register(BadPlugin())

        results = registry.analyze_all(10.0, [], 0.0, {})
        assert "bad" in results
        assert results["bad"]["direction"] == 0
        assert "异常" in results["bad"]["reason"]

    def test_get_weights(self):
        """get_weights() returns plugin weights."""
        from trader_shared.plugin_registry import PluginRegistry
        from trader_shared.interfaces import IndicatorPlugin

        class TestPlugin(IndicatorPlugin):
            def name(self): return "test"
            def analyze(self, current, bars, change_pct, quote): return {}
            def weight(self): return 0.5

        registry = PluginRegistry()
        registry.register(TestPlugin())

        weights = registry.get_weights()
        assert weights["test"] == 0.5


# ── async_utils.py tests ──

class TestAsyncUtils:
    """Test async utility functions."""

    def test_resolve_qq_symbol(self):
        """QQ symbol resolution works correctly."""
        from trader_shared.async_utils import _resolve_qq_symbol
        assert _resolve_qq_symbol("688248") == "sh688248"
        assert _resolve_qq_symbol("000001") == "sz000001"
        assert _resolve_qq_symbol("688248.SH") == "sh688248"
        assert _resolve_qq_symbol("000001.SZ") == "sz000001"

    def test_to_float(self):
        """Float conversion works correctly."""
        from trader_shared.async_utils import _to_float
        assert _to_float("10.5") == 10.5
        assert _to_float(None) is None
        assert _to_float("") is None
        assert _to_float("abc") is None

    def test_check_aiohttp(self):
        """aiohttp availability check works."""
        from trader_shared.async_utils import _check_aiohttp
        # Should return True or False, not raise
        result = _check_aiohttp()
        assert isinstance(result, bool)


# ── Plugin wrappers tests ──

class TestPluginWrappers:
    """Test that plugin wrappers import correctly."""

    def test_chanlun_plugin_import(self):
        """ChanlunPlugin can be imported."""
        from trader_shared.plugins.chan_plugin import ChanlunPlugin
        plugin = ChanlunPlugin()
        assert plugin.name() == "chanlun"
        assert plugin.weight() == 0.45

    def test_wyckoff_plugin_import(self):
        """WyckoffPlugin can be imported."""
        from trader_shared.plugins.wyckoff_plugin import WyckoffPlugin
        plugin = WyckoffPlugin()
        assert plugin.name() == "wyckoff"
        assert plugin.weight() == 0.35

    def test_momentum_plugin_import(self):
        """MomentumPlugin can be imported."""
        from trader_shared.plugins.momentum_plugin import MomentumPlugin
        plugin = MomentumPlugin()
        assert plugin.name() == "momentum"
        assert plugin.weight() == 0.30  # 与 MomentumPlugin.weight / 正常大势 mom 权重对齐


# ── Integration: fusion_core with plugins ──

class TestFusionPluginIntegration:
    """Test fusion_core merge_decisions_from_plugins."""

    def test_merge_decisions_from_plugins_exists(self):
        """merge_decisions_from_plugins function exists and is callable."""
        from trader_shared.fusion_core import merge_decisions_from_plugins
        assert callable(merge_decisions_from_plugins)
