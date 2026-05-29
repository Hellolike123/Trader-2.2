from __future__ import annotations

from typing import Any

from light_data import to_float

try:
    from trader_shared.config import WYCKOFF_MIN_BARS
except ImportError:
    WYCKOFF_MIN_BARS = 15

try:
    from trader_shared.config import WYCKOFF_SPRING_SUPPORT_LOOKBACK
except ImportError:
    WYCKOFF_SPRING_SUPPORT_LOOKBACK = 10

try:
    from trader_shared.config import WYCKOFF_SPRING_RECLAIM_RATIO
except ImportError:
    WYCKOFF_SPRING_RECLAIM_RATIO = 0.92

try:
    from trader_shared.config import WYCKOFF_DIVERGENCE_BARS
except ImportError:
    WYCKOFF_DIVERGENCE_BARS = 5

_VOL_SPIKE_THRESHOLD = 1.2


def _detect_spring(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    low_values = [to_float(b["low"]) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    current_low = to_float(current.get("low"))
    current_close = to_float(current.get("close"))
    current_volume = to_float(current.get("volume"))

    support = min(valid_lows) if valid_lows else None
    if current_low is None or current_close is None or support is None or current_volume is None:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据异常"}

    breach_level = support * WYCKOFF_SPRING_RECLAIM_RATIO

    if current_low >= breach_level or current_close < breach_level:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "未满足弹簧条件"}

    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)

    volume_note = "放量恐慌" if (avg_volume > 0 and current_volume > avg_volume * _VOL_SPIKE_THRESHOLD) else "缩量洗盘"

    return {
        "spring_signal": True,
        "spring_price": round(breach_level, 2),
        "spring_reason": f"跌破支撑后收回 {volume_note}",
    }


def _detect_upthrust(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    high_values = [to_float(b["high"]) for b in recent]
    valid_highs = [v for v in high_values if v is not None]
    current_high = to_float(current.get("high"))
    current_close = to_float(current.get("close"))

    resistance = max(valid_highs) if valid_highs else None
    if current_high is None or current_close is None or resistance is None:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据异常"}

    breakout_level = resistance * 1.02
    reclaim_level = resistance * 0.98

    if current_high <= breakout_level or current_close >= reclaim_level:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "未满足上冲回落条件"}

    return {
        "upthrust_signal": True,
        "upthrust_price": round(resistance, 2),
        "upthrust_reason": "突破阻力后回落，上冲回落信号",
    }


def _detect_volume_divergence(bars: list[dict]) -> tuple[bool, bool]:
    if len(bars) < WYCKOFF_DIVERGENCE_BARS:
        return False, False

    recent = bars[-WYCKOFF_DIVERGENCE_BARS:]

    prices: list[float] = []
    volumes: list[float] = []
    for b in recent:
        close_val = to_float(b.get("close"))
        vol_val = to_float(b.get("volume"))
        if close_val is None or vol_val is None:
            return False, False
        prices.append(close_val)
        volumes.append(vol_val)

    max_price_idx = max(range(len(prices)), key=lambda i: prices[i])
    min_price_idx = min(range(len(prices)), key=lambda i: prices[i])
    max_vol_idx = max(range(len(volumes)), key=lambda i: volumes[i])

    # 看空背离：价格在上升趋势中创新高（峰值高于起点），但量能峰值出现在价格峰值之前（量能萎缩）
    bearish = (prices[max_price_idx] > prices[0]) and (max_price_idx > max_vol_idx)
    # 看多背离：价格在下降趋势中创新低（谷值低于起点），但量能峰值出现在价格谷值之前（抛压释放）
    bullish = (prices[min_price_idx] < prices[0]) and (min_price_idx > max_vol_idx)

    return bearish, bullish


def wyckoff_analysis(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "spring_signal": False,
            "spring_reason": "数据不足",
            "spring_price": None,
            "upthrust_signal": False,
            "upthrust_reason": "数据不足",
            "upthrust_price": None,
            "bearish_volume_divergence": False,
            "bullish_volume_divergence": False,
            "wyckoff_summary": "K线数据不足，无法进行威科夫分析",
        }

    spring = _detect_spring(bars)
    upthrust = _detect_upthrust(bars)
    bearish_div, bullish_div = _detect_volume_divergence(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bearish_div and bullish_div:
        parts.append("量价信号冲突，无法确定方向")
    elif bearish_div:
        parts.append("看空量价背离")
    elif bullish_div:
        parts.append("看多量价背离")
    if not parts:
        parts.append("无明显威科夫信号")

    return {
        "spring_signal": spring["spring_signal"],
        "spring_reason": spring["spring_reason"],
        "spring_price": round(spring["spring_price"], 2) if spring["spring_signal"] else None,
        "upthrust_signal": upthrust["upthrust_signal"],
        "upthrust_reason": upthrust["upthrust_reason"],
        "upthrust_price": round(upthrust["upthrust_price"], 2) if upthrust["upthrust_signal"] else None,
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        "wyckoff_summary": "；".join(parts),
    }


def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    return {"wyckoff": wyckoff_analysis(bars)}
