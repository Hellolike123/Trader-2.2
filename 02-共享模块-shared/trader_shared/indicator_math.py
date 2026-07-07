"""技术指标数学计算共享模块。

提供统一的技术指标计算实现，避免各模块各自实现导致的不一致问题。

主要函数：
  - calc_expma: 计算EXPMA值（SMA初始化 + 指数递推）
  - calc_expma_series: 计算完整的EXPMA序列
"""

from __future__ import annotations


def calc_expma(closes: list[float], period: int) -> float | None:
    """计算单个EXPMA值（使用SMA初始化）。

    必须传入完整历史数据（而非切片），否则会退化为SMA。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        最后一个EXPMA值，数据不足时返回None
    """
    if not closes or period <= 0 or len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
    return round(expma_val, 4)


def calc_expma_series(closes: list[float], period: int) -> list[float | None]:
    """计算完整的EXPMA序列。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        EXPMA值序列，长度与closes相同，前period-1个值为None
    """
    if not closes or period <= 0:
        return [None] * len(closes)
    if len(closes) < period:
        return [None] * len(closes)
    k = 2.0 / (period + 1)
    result: list[float | None] = []
    # 前period-1个值为None
    for _ in range(period - 1):
        result.append(None)
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    result.append(round(expma_val, 4))
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
        result.append(round(expma_val, 4))
    return result


def aggregate_5m_to_60m(bars_5m: list[dict]) -> list[dict]:
    """将5分钟K线聚合为60分钟K线。

    Args:
        bars_5m: 5分钟K线数据列表

    Returns:
        60分钟K线数据列表
    """
    if not bars_5m:
        return []

    from datetime import datetime

    groups: dict[str, list[dict]] = {}
    for bar in bars_5m:
        dt_str = str(bar.get("date") or bar.get("datetime") or "")
        if not dt_str:
            continue
        try:
            if len(dt_str) > 16:
                dt = datetime.fromisoformat(dt_str)
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            # 向下取整到60分钟边界
            hour_bucket = dt.replace(minute=0, second=0, microsecond=0)
            key = hour_bucket.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        groups.setdefault(key, []).append(bar)

    result = []
    for key in sorted(groups.keys()):
        group = groups[key]
        if not group:
            continue
        result.append({
            "date": key,
            "open": float(group[0].get("open", 0)),
            "high": max(float(b.get("high", 0)) for b in group),
            "low": min(float(b.get("low", float("inf"))) for b in group),
            "close": float(group[-1].get("close", 0)),
            "volume": sum(float(b.get("volume", 0)) for b in group),
        })
    return result


def _bar_values(bar: dict) -> tuple[float, float, float]:
    """兼容 dict / 对象两种 bar 形态，提取 (high, low, close)。"""
    if not isinstance(bar, dict):
        return float(getattr(bar, "high", 0)), float(getattr(bar, "low", 0)), float(getattr(bar, "close", 0))
    return float(bar.get("high", 0) or 0), float(bar.get("low", 0) or 0), float(bar.get("close", 0) or 0)


def calc_atr_series(bars: list, period: int = 14) -> list[float | None]:
    """计算 ATR（真实波幅）序列（简单移动平均法）。

    Args:
        bars: K线序列，每根含 high/low/close
        period: ATR 周期

    Returns:
        与 bars 等长的序列，前 period-1 个为 None
    """
    if not bars or len(bars) < 2:
        return [None] * len(bars)

    tr_list: list[float] = []
    for i, bar in enumerate(bars):
        h, l, c = _bar_values(bar)
        if i == 0:
            tr = h - l
        else:
            hp, _, cp = _bar_values(bars[i - 1])
            tr = max(h - l, abs(h - cp), abs(l - cp))
        tr_list.append(tr)

    atr_list: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(tr_list)):
        window = tr_list[i - period + 1 : i + 1]
        atr_list.append(sum(window) / period)
    return atr_list


def calc_supertrend(bars: list, atr_period: int = 14, multiplier: float = 3.0) -> dict:
    """计算 Supertrend 趋势带（ATR 通道）。

    输出趋势方向、多头/空头止损轨道、ATR、ATR 占收盘比、波动率分级。

    Args:
        bars: 日 K 线序列（含 high/low/close）
        atr_period: ATR 周期
        multiplier: ATR 倍数（轨道宽度）

    Returns:
        {
            "direction": "up" | "down" | "neutral",
            "stop_long": float | None,   # 多头轨道（下轨）
            "stop_short": float | None,  # 空头轨道（上轨）
            "atr": float,
            "atr_pct": float,            # atr / 收盘价
            "vol_level": str,            # 波动较低/正常/偏大/偏高
        }
    """
    if not bars:
        # 空输入早返回：避免 atr_list[-1] 索引越界，保持下游契约完整
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
        # 标准 Supertrend 以 (H+L)/2 为中心构造上下轨，首根方向比较才有意义；
        # 若以 close 为中心，basic_lower = close - mult*ATR 恒成立，首根永远为 up。
        h, l, c = _bar_values(bar)
        hl2 = (h + l) / 2.0
        basic_upper.append(hl2 + multiplier * atr_list[i])
        basic_lower.append(hl2 - multiplier * atr_list[i])

    # 标准 Supertrend：正向序列状态机，随收盘是否跌破/突破轨道翻转方向
    final_upper: list[float | None] = [None] * n
    final_lower: list[float | None] = [None] * n
    direction_list: list[str | None] = [None] * n
    for i in range(n):
        if basic_upper[i] is None:
            continue
        _, _, c = _bar_values(bars[i])
        if i == atr_period - 1 or direction_list[i - 1] is None:
            # 首个有效 ATR 索引：以「收盘是否在支撑线上方」初始化
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
        else:  # down
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
            "level": str | None,            # 机构被套/成本附近/机构微盈/机构大幅盈利
        }
    """
    if not bars_5m:
        return {"vwap": None, "deviation_pct": None, "position": None, "level": None}

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
    if deviation_pct < -0.015:
        level = "机构被套"
    elif deviation_pct < 0:
        level = "成本附近"
    elif deviation_pct < 0.015:
        level = "机构微盈"
    else:
        level = "机构大幅盈利"

    return {
        "vwap": vwap,
        "deviation_pct": deviation_pct,
        "position": position,
        "level": level,
    }
