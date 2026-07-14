"""P2 插件自动发现回归测试。

验证 _auto_register 用 importlib 扫描 trader_shared/plugins/ 自动发现所有
IndicatorPlugin 子类，注册集合与原硬编码白名单完全等价（零行为漂移）。
"""
from __future__ import annotations

from trader_shared.interfaces import IndicatorPlugin
from trader_shared.plugin_registry import PluginRegistry, _auto_register
from trader_shared.plugins.chan_plugin import ChanlunPlugin
from trader_shared.plugins.wyckoff_plugin import WyckoffPlugin
from trader_shared.plugins.momentum_plugin import MomentumPlugin
from trader_shared.plugins.supertrend_plugin import SupertrendPlugin
from trader_shared.plugins.vwap_plugin import VwapPlugin

# 当前 plugins/ 目录下全部 IndicatorPlugin 非抽象子类。
# 未来新增插件须在此同步扩充（这就是"加指标零改核心"的契约证明点）。
EXPECTED_PLUGIN_TYPES = {
    ChanlunPlugin,
    WyckoffPlugin,
    MomentumPlugin,
    SupertrendPlugin,
    VwapPlugin,
}


def _registered_types() -> set[type]:
    reg = PluginRegistry()
    _auto_register(reg)
    return {type(p) for p in reg._plugins.values()}


def test_autodiscovery_registers_exactly_the_builtin_plugins():
    """自动发现注册的插件集合 == 原白名单（不多不少，等价性闸门）。"""
    registered = _registered_types()
    assert registered == EXPECTED_PLUGIN_TYPES, (
        f"自动发现集合 {registered} 与原白名单 {EXPECTED_PLUGIN_TYPES} 不一致"
    )


def test_autodiscovery_excludes_abstract_base_and_reexports():
    """抽象基类自身、以及从别处 import 进来的类不应被注册。"""
    reg = PluginRegistry()
    _auto_register(reg)
    for plugin in reg._plugins.values():
        # 注册的都应是具体 IndicatorPlugin 实例（非抽象）
        assert isinstance(plugin, IndicatorPlugin)
        assert not __import__("inspect").isabstract(type(plugin))
    # IndicatorPlugin 基类本身绝不应出现在注册表里
    assert "IndicatorPlugin" not in reg.names()


def test_autodiscovery_idempotent():
    """重复注册不报错、不产生重复项（register 按 name 覆盖）。"""
    reg = PluginRegistry()
    _auto_register(reg)
    first_count = len(reg.names())
    _auto_register(reg)  # 再跑一次
    assert len(reg.names()) == first_count
