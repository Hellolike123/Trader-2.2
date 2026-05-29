"""江恩时间窗口检测器 (P4)。

从关键转折点（缠论笔的终点、中枢突破点）开始计数 K 线，
检测常见的江恩/费波纳契时间周期。

时间窗口类型：
  短周期（费波纳契天数）: 21 / 34 / 55
  中周期（江恩重要循环）: 90 / 144
  长周期（天文年）: 360

使用方式：
    from time_window_detector import check_time_windows

    result = check_time_windows(bars, chan_result)
    # result = {"window_active": True, "window_type": "144", "bars_since_pivot": 143, "tolerance": 3}
"""
from __future__ import annotations

from typing import Any


# 时间窗口定义：周期 → 容忍天数（窗口前后允许的偏差）
TIME_WINDOWS: dict[int, int] = {
    21: 2,   # 费波纳契短周期
    34: 2,   # 费波纳契短周期
    55: 3,   # 费波纳契中周期
    90: 3,   # 江恩1/4年
    144: 4,  # 江恩重要循环（费波纳契数）
    360: 5,  # 天文年
}


def _find_pivot_index(bars: list[dict[str, Any]], chan_result: dict[str, Any] | None = None) -> int | None:
    """找到最近的转折点在 bars 中的索引。

    优先从缠论笔数据中提取最后一个转折点，
    否则用简单的高低点检测作为降级方案。
    """
    # 尝试从缠论笔数据中获取转折点
    if chan_result is not None:
        chan = chan_result.get("chanlun", {}) if isinstance(chan_result, dict) else {}
        if isinstance(chan, dict):
            fractions = chan.get("fractions", [])
            # chan_core 不直接暴露 fractions 在 strategy 返回值中
            # 降级：用 strokes 的最后一笔起止推算
            strokes = chan.get("strokes", [])
            if isinstance(strokes, list) and len(strokes) >= 2:
                # 倒数第二笔的终点作为最近转折点
                second_last = strokes[-2]
                if isinstance(second_last, dict):
                    # 我们只有价格没有索引，用价格在 bars 中查找
                    target_price = float(second_last.get("end_price") or 0)
                    if target_price > 0:
                        # 在 bars 中找最近的匹配价
                        for i in range(len(bars) - 1, -1, -1):
                            bar = bars[i]
                            high = _to_f(bar.get("high"))
                            low = _to_f(bar.get("low"))
                            if high is not None and low is not None:
                                if low <= target_price <= high:
                                    return i

    # 降级方案：用最近的高点/低点作为转折点
    if len(bars) < 5:
        return None

    # 找最近20根K线内的极值点
    recent = bars[-20:] if len(bars) >= 20 else bars
    n = len(recent)
    max_high = -1.0
    max_idx = n - 1
    for i, bar in enumerate(recent):
        h = _to_f(bar.get("high"))
        if h is not None and h > max_high:
            max_high = h
            max_idx = i

    # 转换为在原始 bars 中的索引
    return len(bars) - n + max_idx


def _to_f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check_time_windows(
    bars: list[dict[str, Any]],
    chan_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """检测当前是否处于江恩时间窗口。

    Args:
        bars: K线数据列表（按时间升序）
        chan_result: chanlun_strategy() 的返回值（可选）

    Returns:
        {
            "window_active": bool,        # 是否处于时间窗口
            "window_type": str,           # 窗口周期名（如 "144"），空字符串表示无
            "bars_since_pivot": int,      # 距转折点的 K 线数
            "tolerance": int,             # 窗口容忍天数
            "all_active": [...],          # 所有激活的窗口列表
        }
    """
    result: dict[str, Any] = {
        "window_active": False,
        "window_type": "",
        "bars_since_pivot": 0,
        "tolerance": 0,
        "all_active": [],
    }

    if not bars:
        return result

    pivot_idx = _find_pivot_index(bars, chan_result)
    if pivot_idx is None:
        return result

    bars_since = len(bars) - 1 - pivot_idx
    result["bars_since_pivot"] = bars_since

    active_windows: list[dict[str, Any]] = []
    for period, tolerance in TIME_WINDOWS.items():
        if abs(bars_since - period) <= tolerance:
            active_windows.append({
                "period": period,
                "tolerance": tolerance,
                "distance": bars_since - period,
            })

    if active_windows:
        # 优先报告最接近的窗口
        best = min(active_windows, key=lambda w: abs(w["distance"]))
        result["window_active"] = True
        result["window_type"] = str(best["period"])
        result["tolerance"] = best["tolerance"]
        result["all_active"] = active_windows

    return result
