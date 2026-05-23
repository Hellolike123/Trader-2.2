#!/usr/bin/env python3
"""日内成交量分布分析器 (Intraday Volume Profile)

基于分钟 K 线数据计算日内价格成交量分布，
识别控制节点 POC（Point of Control）与成交量密集区 Value Area（VA）。

用法:
    from volume_profile import VolumeProfile, compute_volume_profile

    bars = [{"high": 10.5, "low": 10.1, "close": 10.3, "volume": 1200}, ...]
    vp = compute_volume_profile(bars)
    print(vp["poc"])          # 成交量最高的价格节点
    print(vp["va_high"])      # 价值区上沿
    print(vp["va_low"])       # 价值区下沿
    print(vp["in_value_area"](10.25))  # True/False
"""

from __future__ import annotations

import numpy as np
from typing import List, Dict, Any, Optional, Callable


class VolumeProfile:
    """日内成交量分布分析器。

    将每根 K 线的成交量按照其价格范围均匀分配到价格网格上，
    然后计算 POC 和 Value Area（70% 总成交量的价格区间）。
    """

    def __init__(self, n_bins: int = 50):
        """
        Args:
            n_bins: 价格网格分辨率（默认 50 档）
        """
        self.n_bins = n_bins
        self.poc: float = 0.0
        self.va_high: float = 0.0
        self.va_low: float = 0.0
        self.value_area_ratio: float = 0.70
        self.price_bins: Optional[np.ndarray] = None
        self.volume_by_price: Optional[np.ndarray] = None
        self._fitted = False

    def fit(self, bars: List[Dict[str, Any]]) -> "VolumeProfile":
        """拟合成交量分布。

        Args:
            bars: K 线列表，每根包含 high / low / close / volume 字段

        Returns:
            self（链式调用）
        """
        if not bars:
            return self

        # 提取有效 K 线
        valid_bars = []
        for b in bars:
            try:
                h = float(str(b.get("high", 0)).replace(",", ""))
                l = float(str(b.get("low", 0)).replace(",", ""))
                v = float(str(b.get("volume", 0)).replace(",", ""))
                if h > l > 0 and v >= 0:
                    valid_bars.append((h, l, v))
            except (TypeError, ValueError):
                continue

        if not valid_bars:
            return self

        # 确定价格范围
        all_highs = [b[0] for b in valid_bars]
        all_lows = [b[1] for b in valid_bars]
        price_min = min(all_lows)
        price_max = max(all_highs)

        if price_max <= price_min:
            return self

        # 构建价格网格
        self.price_bins = np.linspace(price_min, price_max, self.n_bins + 1)
        bin_centers = (self.price_bins[:-1] + self.price_bins[1:]) / 2
        self.volume_by_price = np.zeros(self.n_bins)

        # 将每根 K 线成交量均匀分配到价格区间内
        for h, l, v in valid_bars:
            # 找出与 [l, h] 重叠的所有 bin
            mask = (self.price_bins[1:] >= l) & (self.price_bins[:-1] <= h)
            n_overlap = mask.sum()
            if n_overlap > 0:
                self.volume_by_price[mask] += v / n_overlap

        # 计算 POC（成交量最多的价格节点）
        poc_idx = int(np.argmax(self.volume_by_price))
        self.poc = float(bin_centers[poc_idx])

        # 计算 Value Area（70% 总成交量区间）
        total_vol = self.volume_by_price.sum()
        target_vol = total_vol * self.value_area_ratio

        # 从 POC 向两侧扩展，直到覆盖 70% 成交量
        lo_idx = poc_idx
        hi_idx = poc_idx
        accumulated = float(self.volume_by_price[poc_idx])

        while accumulated < target_vol:
            can_expand_lo = lo_idx > 0
            can_expand_hi = hi_idx < self.n_bins - 1

            if not can_expand_lo and not can_expand_hi:
                break

            vol_lo = float(self.volume_by_price[lo_idx - 1]) if can_expand_lo else -1.0
            vol_hi = float(self.volume_by_price[hi_idx + 1]) if can_expand_hi else -1.0

            if vol_lo >= vol_hi:
                lo_idx -= 1
                accumulated += vol_lo
            else:
                hi_idx += 1
                accumulated += vol_hi

        self.va_low = float(self.price_bins[lo_idx])
        self.va_high = float(self.price_bins[hi_idx + 1])
        self._fitted = True

        return self

    def in_value_area(self, price: float) -> bool:
        """判断价格是否处于成交量价值区内。"""
        if not self._fitted:
            return True  # 未拟合时默认通过
        return self.va_low <= price <= self.va_high

    def above_poc(self, price: float) -> bool:
        """判断价格是否高于控制节点。"""
        if not self._fitted:
            return True
        return price > self.poc

    def breakout_of_va(self, price: float) -> bool:
        """判断价格是否突破价值区上沿（有效向上突破信号）。"""
        if not self._fitted:
            return False
        return price > self.va_high

    def breakdown_of_va(self, price: float) -> bool:
        """判断价格是否跌破价值区下沿（有效向下跌破信号）。"""
        if not self._fitted:
            return False
        return price < self.va_low

    def to_dict(self) -> Dict[str, Any]:
        """返回可序列化的结果字典。"""
        return {
            "poc": round(self.poc, 3),
            "va_high": round(self.va_high, 3),
            "va_low": round(self.va_low, 3),
            "fitted": self._fitted,
        }


def compute_volume_profile(bars: List[Dict[str, Any]], n_bins: int = 50) -> Dict[str, Any]:
    """一站式日内成交量分布计算函数。

    Args:
        bars:   分钟 K 线列表（5m / 15m / 30m 均可）
        n_bins: 价格网格分辨率

    Returns:
        {
            "poc": float,            # 控制节点价格
            "va_high": float,        # 价值区上沿
            "va_low": float,         # 价值区下沿
            "fitted": bool,          # 是否成功拟合
            "in_value_area": Callable,
            "breakout_of_va": Callable,
            "breakdown_of_va": Callable,
            "above_poc": Callable,
        }
    """
    vp = VolumeProfile(n_bins=n_bins)
    vp.fit(bars)

    result = vp.to_dict()
    result["in_value_area"] = vp.in_value_area
    result["breakout_of_va"] = vp.breakout_of_va
    result["breakdown_of_va"] = vp.breakdown_of_va
    result["above_poc"] = vp.above_poc

    return result


def assess_vp_breakout(
    current_price: float,
    vp: Dict[str, Any],
    is_buy_context: bool = True,
) -> Dict[str, Any]:
    """评估当前价格与成交量分布的相对位置，为买卖决策提供微观支撑。

    Args:
        current_price:  当前价格
        vp:             compute_volume_profile() 的输出
        is_buy_context: 是否是买入语境（True=验证低吸/突破，False=验证减仓/防守）

    Returns:
        {
            "vp_signal": str,    # "va_breakout" / "va_support" / "poc_hold" / "below_va"
            "vp_confidence": float,
            "vp_note": str,
        }
    """
    if not vp.get("fitted"):
        return {"vp_signal": "no_data", "vp_confidence": 0.5, "vp_note": "无量价分布数据"}

    poc = vp["poc"]
    va_high = vp["va_high"]
    va_low = vp["va_low"]

    if current_price > va_high:
        return {
            "vp_signal": "va_breakout",
            "vp_confidence": 0.75,
            "vp_note": f"价格 {current_price:.2f} 突破价值区上沿 {va_high:.2f}，强势信号",
        }
    elif va_low <= current_price <= va_high:
        if current_price >= poc:
            return {
                "vp_signal": "above_poc",
                "vp_confidence": 0.60,
                "vp_note": f"价格 {current_price:.2f} 处于 POC {poc:.2f} 上方价值区内，偏多",
            }
        else:
            return {
                "vp_signal": "va_support",
                "vp_confidence": 0.55,
                "vp_note": f"价格 {current_price:.2f} 在价值区内 POC {poc:.2f} 下方，关注 POC 确认",
            }
    else:
        return {
            "vp_signal": "below_va",
            "vp_confidence": 0.35,
            "vp_note": f"价格 {current_price:.2f} 跌破价值区下沿 {va_low:.2f}，偏空",
        }
