from __future__ import annotations

from typing import Any

from trader_shared.light_data import to_float

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
    WYCKOFF_SPRING_RECLAIM_RATIO = 0.97

try:
    from trader_shared.config import WYCKOFF_DIVERGENCE_BARS
except ImportError:
    WYCKOFF_DIVERGENCE_BARS = 5

# 量比阈值说明：
# - _VOL_SPIKE_THRESHOLD = 1.2 用于 SOW/洗盘等一般放量判断（宽松）
# - _BC_VOL_RATIO_THRESHOLD = 2.0 用于 BC 购买高潮（严格，天量才触发）
_VOL_SPIKE_THRESHOLD = 1.2

# ── BC (Buying Climax) 购买高潮检测 ──
# 量化条件：量比 > 2.0 且 涨幅 < 1% 且 上影线 > 2%
_BC_VOL_RATIO_THRESHOLD = 2.0
_BC_CHANGE_THRESHOLD = 1.0
_BC_UPPER_SHADOW_RATIO = 0.02


def _detect_buying_climax(bars: list[dict]) -> dict:
    """Detect Buying Climax (BC) — 天量滞涨，高位放量阴线。

    Returns:
        dict with keys: bc_signal (bool), bc_reason (str), bc_price (float)
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"bc_signal": False, "bc_reason": "数据不足", "bc_price": 0.0}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    cur_open = to_float(current.get("open"))
    cur_high = to_float(current.get("high"))
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))
    cur_volume = to_float(current.get("volume"))

    if any(v is None for v in [cur_open, cur_high, cur_low, cur_close, cur_volume]):
        return {"bc_signal": False, "bc_reason": "数据异常", "bc_price": 0.0}

    # 量比计算
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    if avg_volume <= 0:
        return {"bc_signal": False, "bc_reason": "历史成交量异常", "bc_price": 0.0}

    vol_ratio = cur_volume / avg_volume

    # 涨幅计算（相对前收盘）
    price_range = cur_high - cur_low if cur_high != cur_low else 1.0
    prev_close = to_float(bars[-2].get("close")) if len(bars) >= 2 else cur_open
    change_pct = (cur_close - prev_close) / max(prev_close, 0.01) * 100

    # 上影线比例
    real_body_top = max(cur_open, cur_close)
    upper_shadow = cur_high - real_body_top
    upper_shadow_ratio = upper_shadow / max(price_range, 0.01)

    # BC 条件
    if vol_ratio < _BC_VOL_RATIO_THRESHOLD:
        return {"bc_signal": False, "bc_reason": "量比不足", "bc_price": 0.0}

    # 天量 + 滞涨（收盘接近开盘或阴线）
    is_stagnant = change_pct < _BC_CHANGE_THRESHOLD
    has_upper_shadow = upper_shadow_ratio > _BC_UPPER_SHADOW_RATIO

    if not (is_stagnant or (cur_close < cur_open)):
        return {"bc_signal": False, "bc_reason": "未出现滞涨", "bc_price": 0.0}

    parts = []
    parts.append(f"量比 {vol_ratio:.1f}")
    if is_stagnant:
        parts.append(f"涨幅仅 {change_pct:.1f}%")
    if has_upper_shadow:
        parts.append("上影线明显")
    if cur_close < cur_open:
        parts.append("收阴")

    return {
        "bc_signal": True,
        "bc_reason": "天量滞涨，购买高潮信号：" + "，".join(parts),
        "bc_price": round(cur_high, 2),
    }


# ── SOW (Sign of Weakness) 弱势信号检测 ──
_SOW_SUPPORT_LOOKBACK = 10


def _detect_sign_of_weakness(bars: list[dict]) -> dict:
    """Detect Sign of Weakness (SOW) — 价格跌破支撑且放量。

    Returns:
        dict with keys: sow_signal (bool), sow_reason (str), sow_price (float)
    """
    if len(bars) < _SOW_SUPPORT_LOOKBACK + 1:
        return {"sow_signal": False, "sow_reason": "数据不足", "sow_price": 0.0}

    recent = bars[-(_SOW_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    low_values = [to_float(b["low"]) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))
    cur_volume = to_float(current.get("volume"))

    if cur_low is None or cur_close is None or cur_volume is None or not valid_lows:
        return {"sow_signal": False, "sow_reason": "数据异常", "sow_price": 0.0}

    support = min(valid_lows)

    # 跌破支撑（需要连续2天跌破才算）
    if cur_low >= support:
        return {"sow_signal": False, "sow_reason": "未跌破支撑", "sow_price": 0.0}
    
    # 检查前一天是否也跌破（连续2天跌破才触发）
    prev_low = to_float(bars[-2].get("low")) if len(bars) >= 2 else None
    if prev_low is None or prev_low >= support:
        return {"sow_signal": False, "sow_reason": "仅单日跌破，需连续2天确认", "sow_price": 0.0}

    # 放量确认
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    is_high_volume = avg_volume > 0 and cur_volume > avg_volume * _VOL_SPIKE_THRESHOLD

    if not is_high_volume:
        return {"sow_signal": False, "sow_reason": "缩量跌破，非弱势信号", "sow_price": 0.0}

    # 收盘在支撑下方（真跌破）
    if cur_close >= support:
        return {
            "sow_signal": True,
            "sow_reason": f"放量跌破支撑 {support:.2f} 后收回，弱势警告",
            "sow_price": round(support, 2),
        }

    return {
        "sow_signal": True,
        "sow_reason": f"放量跌破支撑 {support:.2f}，弱势信号",
        "sow_price": round(support, 2),
    }


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

    if current_low >= breach_level or current_close < support:
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
    reclaim_level = resistance * 0.995

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

    # Split into two halves and compare average volume
    mid = len(prices) // 2
    first_half_avg_vol = sum(volumes[:mid]) / max(mid, 1)
    second_half_avg_vol = sum(volumes[mid:]) / max(len(volumes) - mid, 1)

    max_price_idx = max(range(len(prices)), key=lambda i: prices[i])
    min_price_idx = min(range(len(prices)), key=lambda i: prices[i])

    # 看空背离：价格在上升趋势中创新高（峰值高于起点），但后半段平均量低于前半段（量能萎缩）
    bearish = (prices[max_price_idx] > prices[0]) and (second_half_avg_vol < first_half_avg_vol * 0.8)
    # 看多背离：价格在下降趋势中创新低（谷值低于起点），但后半段平均量低于前半段（抛压释放）
    bullish = (prices[min_price_idx] < prices[0]) and (second_half_avg_vol < first_half_avg_vol * 0.8)

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
            "bc_signal": False,
            "bc_reason": "数据不足",
            "bc_price": None,
            "sow_signal": False,
            "sow_reason": "数据不足",
            "sow_price": None,
            "bearish_volume_divergence": False,
            "bullish_volume_divergence": False,
            "wyckoff_summary": "K线数据不足，无法进行威科夫分析",
        }

    spring = _detect_spring(bars)
    upthrust = _detect_upthrust(bars)
    bc = _detect_buying_climax(bars)
    sow = _detect_sign_of_weakness(bars)
    bearish_div, bullish_div = _detect_volume_divergence(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bc["bc_signal"]:
        parts.append(f"购买高潮: {bc['bc_reason']}")
    if sow["sow_signal"]:
        parts.append(f"弱势信号: {sow['sow_reason']}")
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
        "bc_signal": bc["bc_signal"],
        "bc_reason": bc["bc_reason"],
        "bc_price": round(bc["bc_price"], 2) if bc["bc_signal"] else None,
        "sow_signal": sow["sow_signal"],
        "sow_reason": sow["sow_reason"],
        "sow_price": round(sow["sow_price"], 2) if sow["sow_signal"] else None,
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        "wyckoff_summary": "；".join(parts),
    }


def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    return {"wyckoff": wyckoff_analysis(bars)}
