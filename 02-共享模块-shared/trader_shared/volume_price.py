#!/usr/bin/env python3
"""量价背离检测模块 (Volume-Price Divergence Detection)

检测放量滞涨、天量天价等量价背离信号。

用法:
    from volume_price import detect_volume_divergence, VolumeWarning

    warning = detect_volume_divergence(bars)
    print(warning.warning_type)  # "stagnation" | "climactic" | "none"
    print(warning.signal)        # -1=看空, 0=无信号
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class VolumeWarning:
    """量价背离警告。"""
    warning_type: str = "none"      # "stagnation" | "climactic" | "none"
    signal: int = 0                 # -1=看空, 0=无信号
    confidence: float = 0.0         # 0-1
    volume_ratio: float = 0.0       # 当前量比
    price_change: float = 0.0       # 价格涨幅%
    reason: str = ""                # 人类可读描述


def _calc_volume_ratio(bars: List[Dict[str, Any]], window: int = 5) -> float:
    """计算量比（近N日均量 / 前N日均量）。"""
    if len(bars) < 2 * window:
        return 1.0

    recent_vols = []
    prev_vols = []
    for b in bars[-window:]:
        try:
            v = float(str(b.get("volume", 0)).replace(",", ""))
            recent_vols.append(v)
        except (ValueError, TypeError):
            pass

    for b in bars[-2 * window:-window]:
        try:
            v = float(str(b.get("volume", 0)).replace(",", ""))
            prev_vols.append(v)
        except (ValueError, TypeError):
            pass

    if not recent_vols or not prev_vols:
        return 1.0

    avg_recent = sum(recent_vols) / len(recent_vols)
    avg_prev = sum(prev_vols) / len(prev_vols)

    return avg_recent / avg_prev if avg_prev > 0 else 1.0


def _calc_price_change(bars: List[Dict[str, Any]], days: int = 3) -> float:
    """计算近N日涨跌幅。"""
    if len(bars) < days + 1:
        return 0.0

    try:
        current = float(str(bars[-1].get("close", 0)).replace(",", ""))
        prev = float(str(bars[-1 - days].get("close", 0)).replace(",", ""))
        if prev > 0:
            return (current - prev) / prev
    except (ValueError, TypeError):
        pass

    return 0.0


def _has_upper_shadow(bar: Dict[str, Any], threshold: float = 0.3) -> bool:
    """检查是否有长上影线（上影线占实体比例 > threshold）。"""
    try:
        high = float(str(bar.get("high", 0)).replace(",", ""))
        low = float(str(bar.get("low", 0)).replace(",", ""))
        close = float(str(bar.get("close", 0)).replace(",", ""))
        open_ = float(str(bar.get("open", 0)).replace(",", ""))

        if high == low:
            return False

        body_top = max(open_, close)
        upper_shadow = high - body_top
        body = abs(close - open_)

        if body < 1e-10:
            return upper_shadow / (high - low) > threshold

        return upper_shadow / body > threshold
    except (ValueError, TypeError):
        return False


def detect_volume_divergence(
    bars: List[Dict[str, Any]],
    vol_ratio_threshold: float = 1.5,
    price_change_threshold: float = 0.01,
    climactic_threshold: float = 3.0,
) -> VolumeWarning:
    """检测量价背离信号。

    检测条件:
    1. 放量滞涨: 量比 > 1.5 但价格涨幅 < 1%
    2. 天量天价: 量比 > 3.0 且股价创新高

    Args:
        bars: K线数据列表 (至少10根)
        vol_ratio_threshold: 放量判定阈值 (默认1.5)
        price_change_threshold: 涨幅判定阈值 (默认1%)
        climactic_threshold: 天量判定阈值 (默认3.0)

    Returns:
        VolumeWarning 包含警告类型、信号方向、置信度
    """
    if len(bars) < 10:
        return VolumeWarning(reason="数据不足，需要至少10根K线")

    vol_ratio = _calc_volume_ratio(bars)
    price_change = _calc_price_change(bars, days=3)

    # 检查近3天是否有上影线
    recent_upper_shadow = any(
        _has_upper_shadow(bars[i]) for i in range(-3, 0)
    )

    # 检查是否创新高（近20日）
    recent_highs = []
    for b in bars[-20:]:
        try:
            h = float(str(b.get("high", 0)).replace(",", ""))
            recent_highs.append(h)
        except (ValueError, TypeError):
            pass
    current_high = recent_highs[-1] if recent_highs else 0
    max_recent_high = max(recent_highs[:-1]) if len(recent_highs) > 1 else 0
    is_new_high = current_high > max_recent_high and max_recent_high > 0

    # 天量天价检测
    if vol_ratio >= climactic_threshold and is_new_high and price_change > 0:
        return VolumeWarning(
            warning_type="climactic",
            signal=-1,
            confidence=0.7,
            volume_ratio=round(vol_ratio, 2),
            price_change=round(price_change * 100, 2),
            reason=f"天量天价（量比{vol_ratio:.1f}，创新高），注意见顶风险",
        )

    # 放量滞涨检测
    if vol_ratio >= vol_ratio_threshold:
        # 涨幅微弱 或 有上影线
        if abs(price_change) < price_change_threshold or recent_upper_shadow:
            # 如果是上涨中的放量滞涨，信号更强
            if price_change >= 0:
                return VolumeWarning(
                    warning_type="stagnation",
                    signal=-1,
                    confidence=0.5,
                    volume_ratio=round(vol_ratio, 2),
                    price_change=round(price_change * 100, 2),
                    reason=f"放量滞涨（量比{vol_ratio:.1f}，涨幅{price_change*100:+.1f}%），上涨乏力",
                )
            # 下跌中的放量滞涨
            else:
                return VolumeWarning(
                    warning_type="stagnation",
                    signal=-1,
                    confidence=0.4,
                    volume_ratio=round(vol_ratio, 2),
                    price_change=round(price_change * 100, 2),
                    reason=f"放量下跌（量比{vol_ratio:.1f}，跌幅{price_change*100:+.1f}%），注意风险",
                )

    return VolumeWarning(
        volume_ratio=round(vol_ratio, 2),
        price_change=round(price_change * 100, 2),
        reason="量价关系正常",
    )


def volume_warning_to_signal(warning: VolumeWarning) -> dict:
    """将 VolumeWarning 转换为融合层信号格式。"""
    return {
        "direction": warning.signal,
        "confidence": warning.confidence,
        "reason": warning.reason,
        "raw_key": "volume_price",
        "warning_type": warning.warning_type,
    }
