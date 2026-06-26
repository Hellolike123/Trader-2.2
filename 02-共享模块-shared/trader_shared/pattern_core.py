#!/usr/bin/env python3
"""形态识别模块 (Pattern Detection)

检测经典价格形态：W底(双底)、M头(双顶)、三角形突破。

用法:
    from pattern_core import detect_pattern, PatternResult

    result = detect_pattern(closes, highs, lows)
    print(result.pattern)   # "double_bottom" | "double_top" | "triangle" | "none"
    print(result.signal)    # 1=看多, -1=看空, 0=无信号
    print(result.neckline)  # 颈线位
    print(result.target)    # 目标位
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PatternResult:
    """形态识别结果。"""
    pattern: str = "none"       # "double_bottom" | "double_top" | "triangle" | "none"
    signal: int = 0             # 1=看多, -1=看空, 0=无信号
    confidence: float = 0.0     # 0-1
    neckline: float = 0.0       # 颈线位
    target: float = 0.0         # 目标位
    reason: str = ""            # 人类可读描述


def _find_local_extrema(
    values: List[float],
    min_gap: int = 3,
) -> tuple[List[tuple[int, float]], List[tuple[int, float]]]:
    """找局部极值点。

    Args:
        values: 价格序列
        min_gap: 极值点之间最小间距

    Returns:
        (lows, highs) - 低点列表和高点列表，每项为 (index, value)
    """
    if len(values) < 2 * min_gap + 1:
        return [], []

    lows: List[tuple[int, float]] = []
    highs: List[tuple[int, float]] = []

    for i in range(min_gap, len(values) - min_gap):
        window = values[i - min_gap: i + min_gap + 1]
        val = values[i]

        # 平盘数据跳过 (min == max 表示无波动)
        if min(window) == max(window):
            continue

        # 局部低点
        if val == min(window):
            if not lows or (i - lows[-1][0]) >= min_gap:
                lows.append((i, val))

        # 局部高点
        if val == max(window):
            if not highs or (i - highs[-1][0]) >= min_gap:
                highs.append((i, val))

    return lows, highs


def _detect_double_bottom(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    min_gap: int = 5,
) -> Optional[PatternResult]:
    """检测W底(双底)形态。

    条件:
    1. 两个显著低点，间距 >= min_gap
    2. 第二低点 > 第一低点 (不破前低，允许微破2%)
    3. 两低点之间有反弹 (涨幅 >= 3%)
    4. 当前价格突破颈线 (两低点间最高点)
    """
    if len(closes) < 20:
        return None

    price_lows, _ = _find_local_extrema(lows, min_gap=3)
    if len(price_lows) < 2:
        return None

    # 检查最近的两个低点
    for i in range(len(price_lows) - 1):
        idx1, low1 = price_lows[i]
        idx2, low2 = price_lows[i + 1]

        # 间距检查
        if (idx2 - idx1) < min_gap:
            continue

        # 第二低点不破前低 (允许微破2%)
        if low2 < low1 * 0.98:
            continue

        # 两低点之间找最高点作为颈线
        between_highs = highs[idx1:idx2 + 1]
        if not between_highs:
            continue
        neckline = max(between_highs)

        # 反弹幅度检查 (从第一低点到颈线)
        if neckline <= 0 or low1 <= 0:
            continue
        bounce_pct = (neckline - low1) / low1
        if bounce_pct < 0.03:
            continue

        # 当前价格突破颈线
        current = closes[-1]
        if current > neckline:
            # 目标位: 颈线 + 形态高度 (使用两个低点中的最低点)
            pattern_height = neckline - min(low1, low2)
            target = neckline + pattern_height

            return PatternResult(
                pattern="double_bottom",
                signal=1,
                confidence=0.6,
                neckline=round(neckline, 2),
                target=round(target, 2),
                reason=f"W底确认，突破颈线{neckline:.2f}，目标{target:.2f}",
            )

    return None


def _detect_double_top(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    min_gap: int = 5,
) -> Optional[PatternResult]:
    """检测M头(双顶)形态。

    条件:
    1. 两个显著高点，间距 >= min_gap
    2. 第二高点 < 第一高点 (不创新高，允许微破2%)
    3. 两高点之间有回调 (跌幅 >= 3%)
    4. 当前价格跌破颈线 (两高点间最低点)
    """
    if len(closes) < 20:
        return None

    price_highs, _ = _find_local_extrema(highs, min_gap=3)
    if len(price_highs) < 2:
        return None

    for i in range(len(price_highs) - 1):
        idx1, high1 = price_highs[i]
        idx2, high2 = price_highs[i + 1]

        if (idx2 - idx1) < min_gap:
            continue

        # 第二高点不创新高 (允许微破2%)
        if high2 > high1 * 1.02:
            continue

        # 两高点之间找最低点作为颈线
        between_lows = lows[idx1:idx2 + 1]
        if not between_lows:
            continue
        neckline = min(between_lows)

        # 回调幅度检查
        if high1 <= 0:
            continue
        drop_pct = (high1 - neckline) / high1
        if drop_pct < 0.03:
            continue

        # 当前价格跌破颈线
        current = closes[-1]
        if current < neckline:
            # 目标位: 颈线 - 形态高度 (使用两个高点中的最高点)
            pattern_height = max(high1, high2) - neckline
            target = neckline - pattern_height

            return PatternResult(
                pattern="double_top",
                signal=-1,
                confidence=0.6,
                neckline=round(neckline, 2),
                target=round(target, 2),
                reason=f"M头确认，跌破颈线{neckline:.2f}，目标{target:.2f}",
            )

    return None


def _detect_triangle(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    min_points: int = 4,
) -> Optional[PatternResult]:
    """检测三角形收敛突破。

    条件:
    1. 高点逐步降低 (至少2个递降高点)
    2. 低点逐步抬高 (至少2个递升高点)
    3. 收敛区间 >= 5根K线
    4. 突破上轨 = 买入, 跌破下轨 = 卖出
    """
    if len(closes) < 20:
        return None

    price_highs, _ = _find_local_extrema(highs, min_gap=3)
    price_lows, _ = _find_local_extrema(lows, min_gap=3)

    # 需要至少2个高点和2个低点
    if len(price_highs) < 2 or len(price_lows) < 2:
        return None

    # 至少需要3个高点和3个低点才能形成有效三角形
    if len(price_highs) < 3 or len(price_lows) < 3:
        return None

    # 检查最近的高点是否递降
    recent_highs = price_highs[-min_points:]
    highs_declining = all(
        recent_highs[j][1] > recent_highs[j + 1][1]
        for j in range(len(recent_highs) - 1)
    )

    # 检查最近的低点是否递升
    recent_lows = price_lows[-min_points:]
    lows_rising = all(
        recent_lows[j][1] < recent_lows[j + 1][1]
        for j in range(len(recent_lows) - 1)
    )

    if not (highs_declining and lows_rising):
        return None

    # 收敛区间
    start_idx = min(recent_highs[0][0], recent_lows[0][0])
    end_idx = max(recent_highs[-1][0], recent_lows[-1][0])
    if (end_idx - start_idx) < 5:
        return None

    # 上轨和下轨
    upper_track = recent_highs[-1][1]
    lower_track = recent_lows[-1][1]

    # 当前价格判断突破方向
    current = closes[-1]
    prev = closes[-2] if len(closes) > 1 else current

    # 最小形态高度检查 (至少1%波动，避免退化信号)
    pattern_height = upper_track - lower_track
    if current > 0 and pattern_height < current * 0.01:
        return None

    if current > upper_track and prev <= upper_track:
        # 向上突破
        target = upper_track + pattern_height
        return PatternResult(
            pattern="triangle_breakout",
            signal=1,
            confidence=0.5,
            neckline=round(upper_track, 2),
            target=round(target, 2),
            reason=f"三角形向上突破{upper_track:.2f}，目标{target:.2f}",
        )
    elif current < lower_track and prev >= lower_track:
        # 向下突破
        target = lower_track - pattern_height
        return PatternResult(
            pattern="triangle_breakdown",
            signal=-1,
            confidence=0.5,
            neckline=round(lower_track, 2),
            target=round(target, 2),
            reason=f"三角形向下破位{lower_track:.2f}，目标{target:.2f}",
        )

    return None


def detect_pattern(
    closes: List[float],
    highs: List[float],
    lows: List[float],
) -> PatternResult:
    """检测价格形态。

    按优先级检测: W底 > M头 > 三角形

    Args:
        closes: 收盘价序列 (至少20根)
        highs: 最高价序列
        lows: 最低价序列

    Returns:
        PatternResult 包含形态类型、信号方向、置信度、颈线位、目标位
    """
    if len(closes) < 20 or len(highs) < 20 or len(lows) < 20:
        return PatternResult(reason="数据不足，需要至少20根K线")

    # 按优先级检测
    result = _detect_double_bottom(closes, highs, lows)
    if result:
        return result

    result = _detect_double_top(closes, highs, lows)
    if result:
        return result

    result = _detect_triangle(closes, highs, lows)
    if result:
        return result

    return PatternResult(reason="未检测到明确形态")
