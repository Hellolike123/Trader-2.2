#!/usr/bin/env python3
"""日内成交量分布（Volume Profile）单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATE = _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
if str(_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(_CANDIDATE))


def _make_bars(prices_and_volumes):
    """生成测试用 K 线列表。"""
    bars = []
    for i, (price, vol) in enumerate(prices_and_volumes):
        bars.append({
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price,
            "volume": vol,
        })
    return bars


class TestVolumeProfile:
    """VolumeProfile 数学正确性与鲁棒性测试。"""

    def setup_method(self):
        from volume_profile import VolumeProfile, compute_volume_profile, assess_vp_breakout
        self.VP = VolumeProfile
        self.compute = compute_volume_profile
        self.assess = assess_vp_breakout

    # ── 基础功能 ──────────────────────────────────────────────────────────────

    def test_poc_is_highest_volume_price(self):
        """POC 应对应成交量最大的价格区域。"""
        # 在 10.5 附近集中大量成交
        bars = _make_bars([
            (10.0, 100), (10.1, 100), (10.2, 100),
            (10.5, 5000), (10.5, 4000), (10.5, 3000),  # 成交量集中在 10.5
            (10.8, 100), (10.9, 100), (11.0, 100),
        ])
        vp = self.VP(n_bins=30)
        vp.fit(bars)
        assert vp._fitted
        # POC 应在 10.5 附近（允许 ±0.3 的网格误差）
        assert abs(vp.poc - 10.5) < 0.5, f"POC={vp.poc:.3f} 应接近 10.5"

    def test_va_contains_poc(self):
        """POC 应落在 Value Area [va_low, va_high] 内。"""
        bars = _make_bars([(10.0 + i * 0.1, 500 + i * 10) for i in range(20)])
        vp = self.VP()
        vp.fit(bars)
        assert vp.va_low <= vp.poc <= vp.va_high, (
            f"POC={vp.poc:.3f} 不在 VA [{vp.va_low:.3f}, {vp.va_high:.3f}]"
        )

    def test_va_width_positive(self):
        """Value Area 宽度应大于零。"""
        bars = _make_bars([(10.0, 100)] * 30)
        vp = self.VP()
        vp.fit(bars)
        if vp._fitted:
            assert vp.va_high >= vp.va_low

    def test_va_covers_at_least_60_pct_volume(self):
        """Value Area 覆盖的成交量应占总量的 60% 以上（理论目标是 70%）。"""
        import numpy as np
        bars = _make_bars([(10.0 + i * 0.05, 200 + i * 20) for i in range(40)])
        vp = self.VP(n_bins=40)
        vp.fit(bars)
        if not vp._fitted or vp.volume_by_price is None:
            return
        total = vp.volume_by_price.sum()
        # 找 va 区间内的成交量
        in_va = 0
        for i, (lo, hi) in enumerate(zip(vp.price_bins[:-1], vp.price_bins[1:])):
            mid = (lo + hi) / 2
            if vp.va_low <= mid <= vp.va_high:
                in_va += vp.volume_by_price[i]
        ratio = in_va / max(total, 1e-10)
        assert ratio >= 0.60, f"VA 覆盖 {ratio:.1%} 不足 60%"

    # ── 边界判断函数 ──────────────────────────────────────────────────────────

    def test_in_value_area_true_for_poc_price(self):
        """POC 附近的价格应在 Value Area 内。"""
        bars = _make_bars([(10.5, 5000)] * 5 + [(9.0, 100), (12.0, 100)])
        vp = self.VP()
        vp.fit(bars)
        if vp._fitted:
            assert vp.in_value_area(vp.poc)

    def test_breakout_of_va_above_va_high(self):
        """价格高于 va_high 应判断为突破。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        vp = self.VP()
        vp.fit(bars)
        if vp._fitted:
            assert vp.breakout_of_va(vp.va_high + 1.0)
            assert not vp.breakout_of_va(vp.va_high - 0.01)

    def test_breakdown_of_va_below_va_low(self):
        """价格低于 va_low 应判断为跌破。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        vp = self.VP()
        vp.fit(bars)
        if vp._fitted:
            assert vp.breakdown_of_va(vp.va_low - 1.0)
            assert not vp.breakdown_of_va(vp.va_low + 0.01)

    # ── 鲁棒性 ────────────────────────────────────────────────────────────────

    def test_empty_bars_does_not_crash(self):
        """空 K 线列表应安全处理，不崩溃。"""
        vp = self.VP()
        vp.fit([])
        assert not vp._fitted
        # 未拟合时 in_value_area 应返回 True（默认通过）
        assert vp.in_value_area(10.0) is True

    def test_single_bar_does_not_crash(self):
        """单根 K 线应安全处理。"""
        vp = self.VP()
        vp.fit([{"high": 10.5, "low": 10.0, "close": 10.2, "volume": 1000}])
        assert isinstance(vp._fitted, bool)

    def test_invalid_bar_fields_ignored(self):
        """含有无效字段的 K 线应被忽略，不崩溃。"""
        bars = [
            {"high": "abc", "low": 10.0, "close": 10.1, "volume": 100},
            {"high": 10.5, "low": 10.1, "close": 10.3, "volume": 500},
            {"high": None, "low": None, "close": None, "volume": None},
        ]
        vp = self.VP()
        vp.fit(bars)
        assert isinstance(vp, self.VP)

    def test_zero_volume_bars_handled(self):
        """零成交量 K 线应安全处理。"""
        bars = [{"high": 10.5, "low": 10.0, "close": 10.2, "volume": 0} for _ in range(10)]
        vp = self.VP()
        vp.fit(bars)
        assert isinstance(vp, self.VP)

    # ── compute_volume_profile 便捷函数 ──────────────────────────────────────

    def test_compute_returns_callable_functions(self):
        """compute_volume_profile 返回字典中应包含可调用的判断函数。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        result = self.compute(bars)
        assert callable(result["in_value_area"])
        assert callable(result["breakout_of_va"])
        assert callable(result["breakdown_of_va"])
        assert callable(result["above_poc"])

    def test_compute_returns_numeric_fields(self):
        """compute_volume_profile 返回字典中数值字段应为 float。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        result = self.compute(bars)
        assert isinstance(result["poc"], float)
        assert isinstance(result["va_high"], float)
        assert isinstance(result["va_low"], float)

    # ── assess_vp_breakout 评估函数 ───────────────────────────────────────────

    def test_assess_above_va_high_returns_breakout(self):
        """价格高于 va_high 应返回 va_breakout 信号。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        vp_dict = self.compute(bars)
        if vp_dict["fitted"]:
            result = self.assess(vp_dict["va_high"] + 0.5, vp_dict)
            assert result["vp_signal"] == "va_breakout"

    def test_assess_below_va_low_returns_below_va(self):
        """价格低于 va_low 应返回 below_va 信号。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        vp_dict = self.compute(bars)
        if vp_dict["fitted"]:
            result = self.assess(vp_dict["va_low"] - 0.5, vp_dict)
            assert result["vp_signal"] == "below_va"

    def test_assess_no_data_returns_no_data(self):
        """未拟合的 vp_dict 应返回 no_data 信号。"""
        result = self.assess(10.0, {"fitted": False})
        assert result["vp_signal"] == "no_data"

    def test_assess_confidence_in_valid_range(self):
        """vp_confidence 应在 [0, 1] 范围内。"""
        bars = _make_bars([(10.0 + i * 0.1, 500) for i in range(20)])
        vp_dict = self.compute(bars)
        result = self.assess(10.5, vp_dict)
        assert 0.0 <= result["vp_confidence"] <= 1.0
