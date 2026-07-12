"""展示指标计算模块（display_indicators.py）

本模块承载"面向展示"的技术指标计算，即那些最终目的是
渲染到报告/UI 的指标（VWAP、Supertrend、Volume Profile）。

纯数学内核（ATR、MACD、EXPMA 等）仍保留在 indicator_math.py。
上层调用方可以从本模块或 indicator_math 任意引入，两者均保持兼容。

display_only = True  <- 标记：插件注册时识别此模块为纯展示类，不参与 fusion 决策
"""
from __future__ import annotations

# display_only 标记，供 plugin_registry 分层加载时识别
display_only: bool = True

# 重新导出纯数学内核（避免下游需要同时 import 两个模块）
from trader_shared.indicator_math import (  # noqa: F401
    calc_atr_series,
    calc_expma,
    calc_expma_series,
    calc_macd_series,
    aggregate_5m_to_60m,
    _bar_values,
)


def calc_vwap(bars_5m: list, current_price: float | None = None) -> dict:
    """计算当日 VWAP（成交量加权均价）及偏离度。

    Args:
        bars_5m: 当日 5 分钟 K 线（含 high/low/close/volume）
        current_price: 最新价（算偏离度，可选）

    Returns:
        {
            "vwap": float | None,
            "deviation_pct": float | None,  # (现价 - vwap) / vwap
            "position": "above" | "below" | None,
            "level": str | None,  # 机构被套/成本附近/机构微盈/机构大幅盈利
        }
    """
    if not bars_5m:
        return {"vwap": None, "deviation_pct": None, "position": None, "level": None}

    try:
        from trader_shared.config import VWAP_DEVIATION_BELOW_TRAPPED, VWAP_DEVIATION_ABOVE_PROFIT
    except ImportError:
        VWAP_DEVIATION_BELOW_TRAPPED = -0.015
        VWAP_DEVIATION_ABOVE_PROFIT = 0.015

    cum_pv = 0.0
    cum_vol = 0.0
    for bar in bars_5m:
        vol = 0.0
        if isinstance(bar, dict):
            vol = float(bar.get("volume", 0) or bar.get("vol", 0) or 0)
        else:
            vol = float(getattr(bar, "volume", 0) or 0)
        if vol <= 0:
            continue
        h, l, c = _bar_values(bar)
        if h <= 0 or l <= 0 or c <= 0:
            continue
        typical = (h + l + c) / 3
        cum_pv += typical * vol
        cum_vol += vol

    if cum_vol <= 0:
        return {"vwap": None, "deviation_pct": None, "position": None, "level": None}

    vwap = cum_pv / cum_vol
    if current_price is None:
        _, _, current_price = _bar_values(bars_5m[-1])
    if current_price is None or current_price <= 0:
        return {"vwap": vwap, "deviation_pct": None, "position": None, "level": None}

    deviation_pct = (current_price - vwap) / vwap
    position = "above" if current_price >= vwap else "below"
    if deviation_pct < VWAP_DEVIATION_BELOW_TRAPPED:
        level = "机构被套"
    elif deviation_pct < 0:
        level = "成本附近"
    elif deviation_pct < VWAP_DEVIATION_ABOVE_PROFIT:
        level = "机构微盈"
    else:
        level = "机构大幅盈利"

    return {
        "vwap": vwap,
        "deviation_pct": deviation_pct,
        "position": position,
        "level": level,
    }


def calc_supertrend(bars: list, atr_period: int | None = None, multiplier: float | None = None) -> dict:
    """计算 Supertrend 趋势带（ATR 通道）。

    输出趋势方向、多头/空头止损轨道、ATR、ATR 占收盘比、波动率分级。

    Args:
        bars: 日 K 线序列（含 high/low/close）
        atr_period: ATR 周期（默认读 config.ATR_PERIOD，14）
        multiplier: ATR 倍数（默认读 config.SUPERTREND_MULTIPLIER，3.0）

    Returns:
        {
            "direction": "up" | "down" | "neutral",
            "stop_long": float | None,   # 多头轨道（下轨）
            "stop_short": float | None,  # 空头轨道（上轨）
            "atr": float,
            "atr_pct": float,
            "vol_level": str,
        }
    """
    try:
        from trader_shared.config import ATR_PERIOD, SUPERTREND_MULTIPLIER
    except ImportError:
        ATR_PERIOD, SUPERTREND_MULTIPLIER = 14, 3.0

    if atr_period is None:
        atr_period = ATR_PERIOD
    if multiplier is None:
        multiplier = SUPERTREND_MULTIPLIER

    if not bars:
        return {
            "direction": "neutral",
            "stop_long": None,
            "stop_short": None,
            "atr": 0.0,
            "atr_pct": 0.0,
            "vol_level": "波动正常",
        }

    atr_list = calc_atr_series(bars, atr_period)
    n = len(bars)
    basic_upper: list[float | None] = []
    basic_lower: list[float | None] = []
    for i, bar in enumerate(bars):
        if atr_list[i] is None:
            basic_upper.append(None)
            basic_lower.append(None)
            continue
        h, l, c = _bar_values(bar)
        hl2 = (h + l) / 2.0
        basic_upper.append(hl2 + multiplier * atr_list[i])
        basic_lower.append(hl2 - multiplier * atr_list[i])

    final_upper: list[float | None] = [None] * n
    final_lower: list[float | None] = [None] * n
    direction_list: list[str | None] = [None] * n
    for i in range(n):
        if basic_upper[i] is None:
            continue
        _, _, c = _bar_values(bars[i])
        if i == atr_period - 1 or direction_list[i - 1] is None:
            final_lower[i] = basic_lower[i]
            final_upper[i] = basic_upper[i]
            direction_list[i] = "up" if c >= basic_lower[i] else "down"
            continue
        prev_dir = direction_list[i - 1]
        if prev_dir == "up":
            final_lower[i] = max(final_lower[i - 1] or basic_lower[i], basic_lower[i])
            final_upper[i] = basic_upper[i]
            if c <= final_lower[i]:
                direction_list[i] = "down"
                final_upper[i] = basic_upper[i]
            else:
                direction_list[i] = "up"
        else:
            final_upper[i] = min(final_upper[i - 1] or basic_upper[i], basic_upper[i])
            final_lower[i] = basic_lower[i]
            if c >= final_upper[i]:
                direction_list[i] = "up"
                final_lower[i] = basic_lower[i]
            else:
                direction_list[i] = "down"

    direction = "neutral"
    last_valid = -1
    for i in range(n - 1, -1, -1):
        if direction_list[i] is not None:
            direction = direction_list[i]
            last_valid = i
            break

    last_atr = atr_list[-1] or 0.0
    _, _, last_close = _bar_values(bars[-1]) if bars else (0.0, 0.0, 0.0)
    atr_pct = (last_atr / last_close) if last_close > 0 else 0.0
    if atr_pct < 0.03:
        vol_level = "波动较低"
    elif atr_pct < 0.05:
        vol_level = "波动正常"
    elif atr_pct < 0.08:
        vol_level = "波动偏大"
    else:
        vol_level = "波幅偏高"

    return {
        "direction": direction,
        "stop_long": final_lower[last_valid] if direction == "up" and last_valid >= 0 else None,
        "stop_short": final_upper[last_valid] if direction == "down" and last_valid >= 0 else None,
        "atr": last_atr,
        "atr_pct": atr_pct,
        "vol_level": vol_level,
    }


def calc_volume_profile(bars: list, n_bins: int = 50, value_area_ratio: float = 0.70) -> dict:
    """计算日内成交量分布（Volume Profile）便捷包装。

    从 volume_profile 模块导入核心逻辑，对外提供统一接口。

    Args:
        bars: K 线列表（含 high/low/close/volume）
        n_bins: 价格网格数
        value_area_ratio: 价值区覆盖比例（默认 70%）

    Returns:
        {
            "poc": float,         # Point of Control（最大成交量价格）
            "va_high": float,     # 价值区上沿
            "va_low": float,      # 价值区下沿
            "in_value_area": Callable[[float], bool],
        }
    """
    try:
        from trader_shared.volume_profile import compute_volume_profile
        return compute_volume_profile(bars, n_bins=n_bins, value_area_ratio=value_area_ratio)
    except Exception:
        return {"poc": 0.0, "va_high": 0.0, "va_low": 0.0, "in_value_area": lambda _: False}
