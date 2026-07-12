"""测试 display_indicators.py 模块

验证以下内容：
1. display_only 标记为 True
2. calc_vwap 的空输入、正常输入、阈值分级
3. calc_supertrend 的空输入、正常输入
4. indicator_math 中的同名函数向后兼容（re-export 透明）
5. config 中展示类阈值可读
"""
from __future__ import annotations

import pytest
import sys
import os

# 确保能找到 trader_shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "02-共享模块-shared"))


# ── calc_vwap ─────────────────────────────────────────────────────────────────

class TestCalcVwap:
    def _make_bars(self, close=10.3, volume=1000, n=5):
        return [{"high": close * 1.02, "low": close * 0.98, "close": close, "volume": volume}] * n

    def test_empty_input(self):
        from trader_shared.display_indicators import calc_vwap
        r = calc_vwap([])
        assert r["vwap"] is None
        assert r["deviation_pct"] is None
        assert r["position"] is None
        assert r["level"] is None

    def test_normal_input_returns_vwap(self):
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        r = calc_vwap(bars, current_price=10.0)
        assert r["vwap"] is not None
        assert abs(r["vwap"] - 10.0) < 0.1  # 典型价 ≈ 收盘价

    def test_level_above_trapped(self):
        """现价低于 VWAP 超过阈值 → 机构被套"""
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        # 现价比 VWAP 低 3%（超过 1.5% 阈值）
        r = calc_vwap(bars, current_price=9.6)
        assert r["level"] == "机构被套"

    def test_level_near_cost(self):
        """现价略低于 VWAP → 成本附近"""
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        # 现价比 VWAP 低 0.5%
        r = calc_vwap(bars, current_price=9.95)
        assert r["level"] == "成本附近"

    def test_level_small_profit(self):
        """现价略高于 VWAP → 机构微盈"""
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        # 现价比 VWAP 高 0.5%（低于 1.5% 阈值）
        r = calc_vwap(bars, current_price=10.05)
        assert r["level"] == "机构微盈"

    def test_level_large_profit(self):
        """现价远高于 VWAP → 机构大幅盈利"""
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        # 现价比 VWAP 高 3%
        r = calc_vwap(bars, current_price=10.4)
        assert r["level"] == "机构大幅盈利"

    def test_no_volume_returns_none(self):
        """成交量为 0 时返回 None"""
        from trader_shared.display_indicators import calc_vwap
        bars = [{"high": 10.5, "low": 9.5, "close": 10.0, "volume": 0}] * 3
        r = calc_vwap(bars)
        assert r["vwap"] is None

    def test_position_above_below(self):
        """position 字段正确区分 above/below"""
        from trader_shared.display_indicators import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        r_above = calc_vwap(bars, current_price=10.5)
        assert r_above["position"] == "above"
        r_below = calc_vwap(bars, current_price=9.0)
        assert r_below["position"] == "below"

    def test_compat_from_indicator_math(self):
        """从 indicator_math 导入仍然能正常计算（re-export 兼容）"""
        from trader_shared.indicator_math import calc_vwap
        bars = self._make_bars(close=10.0, volume=1000)
        r = calc_vwap(bars, current_price=10.0)
        assert r["vwap"] is not None


# ── calc_supertrend ───────────────────────────────────────────────────────────

class TestCalcSupertrend:
    def _make_bars(self, n=30, start=10.0, trend="up"):
        """构造一段简单趋势 K 线"""
        bars = []
        price = start
        for i in range(n):
            if trend == "up":
                price = start * (1 + i * 0.005)
            else:
                price = start * (1 - i * 0.005)
            bars.append({
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
            })
        return bars

    def test_empty_input(self):
        from trader_shared.display_indicators import calc_supertrend
        r = calc_supertrend([])
        assert r["direction"] == "neutral"
        assert r["atr"] == 0.0
        assert r["stop_long"] is None
        assert r["stop_short"] is None

    def test_uptrend_returns_up(self):
        from trader_shared.display_indicators import calc_supertrend
        bars = self._make_bars(n=40, trend="up")
        r = calc_supertrend(bars)
        assert r["direction"] == "up"
        assert r["stop_long"] is not None
        assert r["atr"] > 0

    def test_downtrend_returns_down(self):
        from trader_shared.display_indicators import calc_supertrend
        bars = self._make_bars(n=40, start=20.0, trend="down")
        r = calc_supertrend(bars)
        assert r["direction"] == "down"
        assert r["stop_short"] is not None

    def test_vol_level_field_present(self):
        from trader_shared.display_indicators import calc_supertrend
        bars = self._make_bars(n=30, trend="up")
        r = calc_supertrend(bars)
        assert r["vol_level"] in ("波动较低", "波动正常", "波动偏大", "波幅偏高")

    def test_custom_atr_period_and_multiplier(self):
        from trader_shared.display_indicators import calc_supertrend
        bars = self._make_bars(n=40, trend="up")
        r = calc_supertrend(bars, atr_period=10, multiplier=2.0)
        assert r["direction"] in ("up", "down", "neutral")

    def test_compat_from_indicator_math(self):
        """从 indicator_math 导入仍然有效（re-export 兼容）"""
        from trader_shared.indicator_math import calc_supertrend
        bars = self._make_bars(n=40, trend="up")
        r = calc_supertrend(bars)
        assert r["direction"] in ("up", "down", "neutral")


# ── display_only 标记 ─────────────────────────────────────────────────────────

class TestDisplayOnly:
    def test_module_flag(self):
        import trader_shared.display_indicators as di
        assert di.display_only is True

    def test_vwap_plugin_flag(self):
        import trader_shared.plugins.vwap_plugin as vp
        assert vp.display_only is True

    def test_supertrend_plugin_flag(self):
        import trader_shared.plugins.supertrend_plugin as sp
        assert sp.display_only is True


# ── config 阈值 ───────────────────────────────────────────────────────────────

class TestConfigThresholds:
    def test_vwap_thresholds_present(self):
        from trader_shared.config import VWAP_DEVIATION_BELOW_TRAPPED, VWAP_DEVIATION_ABOVE_PROFIT
        assert VWAP_DEVIATION_BELOW_TRAPPED < 0
        assert VWAP_DEVIATION_ABOVE_PROFIT > 0

    def test_supertrend_multiplier_present(self):
        from trader_shared.config import SUPERTREND_MULTIPLIER
        assert SUPERTREND_MULTIPLIER > 0

    def test_atr_period_present(self):
        from trader_shared.config import ATR_PERIOD
        assert ATR_PERIOD > 0

    def test_env_override(self, monkeypatch):
        """验证 env 覆盖机制（重载模块后生效）"""
        import importlib
        monkeypatch.setenv("ATR_PERIOD", "20")
        import trader_shared.config as cfg
        importlib.reload(cfg)
        assert cfg.ATR_PERIOD == 20
        # 清理：还原
        importlib.reload(cfg)
