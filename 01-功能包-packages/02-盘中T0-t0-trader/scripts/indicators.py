from __future__ import annotations

import math
from typing import Any


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def calculate_sma(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        return [None for _ in values]
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
        else:
            window = values[index + 1 - period : index + 1]
            result.append(sum(window) / period)
    return result


def calculate_ema(values: list[float | None], period: int) -> list[float | None]:
    if period <= 0 or not values:
        return [None for _ in values]
    alpha = 2 / (period + 1)
    result: list[float | None] = []
    ema: float | None = None
    for value in values:
        if value is None:
            result.append(ema)
            continue
        ema = value if ema is None else value * alpha + ema * (1 - alpha)
        result.append(ema)
    return result


def calculate_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float | None]]:
    if not closes:
        return {"dif": [], "dea": [], "hist": []}
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    dif: list[float | None] = []
    for left, right in zip(ema_fast, ema_slow):
        dif.append(None if left is None or right is None else left - right)
    dea = calculate_ema(dif, signal)
    hist: list[float | None] = []
    for d, e in zip(dif, dea):
        hist.append(None if d is None or e is None else (d - e) * 2)
    return {"dif": dif, "dea": dea, "hist": hist}


def calculate_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if period <= 0 or len(closes) < 2:
        return [None for _ in closes]
    result: list[float | None] = [None for _ in closes]
    gains: list[float] = []
    losses: list[float] = []
    avg_gain: float | None = None
    avg_loss: float | None = None
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
        if len(gains) < period:
            continue
        if len(gains) == period:
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
        else:
            avg_gain = ((avg_gain or 0.0) * (period - 1) + gains[-1]) / period
            avg_loss = ((avg_loss or 0.0) * (period - 1) + losses[-1]) / period
        if avg_loss == 0 and (avg_gain or 0.0) == 0:
            result[index] = 50.0
        elif avg_loss == 0:
            result[index] = 100.0
        else:
            rs = (avg_gain or 0.0) / avg_loss
            result[index] = 100 - (100 / (1 + rs))
    return result


def calculate_vwap_from_bars(bars: list[dict[str, Any]]) -> float | None:
    total_value = 0.0
    total_volume = 0.0
    for bar in bars:
        high = _num(bar.get("high"))
        low = _num(bar.get("low"))
        close = _num(bar.get("close"))
        volume = _num(bar.get("volume"))
        if high is None or low is None or close is None or volume is None or volume <= 0:
            continue
        typical = (high + low + close) / 3
        total_value += typical * volume
        total_volume += volume
    return total_value / total_volume if total_volume > 0 else None


def calculate_volume_ratio(bars: list[dict[str, Any]], recent: int = 6, prior: int = 12) -> float | None:
    if len(bars) < recent + prior:
        return None
    recent_values = [_num(bar.get("volume")) or 0.0 for bar in bars[-recent:]]
    prior_values = [_num(bar.get("volume")) or 0.0 for bar in bars[-(recent + prior) : -recent]]
    recent_avg = sum(recent_values) / recent if recent else 0
    prior_avg = sum(prior_values) / prior if prior else 0
    return recent_avg / prior_avg if prior_avg > 0 else None


def detect_upper_shadow(bar: dict[str, Any]) -> bool:
    open_ = _num(bar.get("open"))
    high = _num(bar.get("high"))
    low = _num(bar.get("low"))
    close = _num(bar.get("close"))
    if None in (open_, high, low, close) or high == low:
        return False
    upper = high - max(open_, close)
    body = abs(close - open_)
    return upper >= max(body * 1.2, (high - low) * 0.25)


def detect_lower_shadow(bar: dict[str, Any]) -> bool:
    open_ = _num(bar.get("open"))
    high = _num(bar.get("high"))
    low = _num(bar.get("low"))
    close = _num(bar.get("close"))
    if None in (open_, high, low, close) or high == low:
        return False
    lower = min(open_, close) - low
    body = abs(close - open_)
    return lower >= max(body * 1.2, (high - low) * 0.25)


def is_new_low_recent(bars: list[dict[str, Any]], lookback: int = 6) -> bool:
    if len(bars) < lookback:
        return False
    lows = [_num(bar.get("low")) for bar in bars[-lookback:]]
    lows = [value for value in lows if value is not None]
    return len(lows) >= 3 and lows[-1] <= min(lows[:-1])


def is_new_high_recent(bars: list[dict[str, Any]], lookback: int = 6) -> bool:
    if len(bars) < lookback:
        return False
    highs = [_num(bar.get("high")) for bar in bars[-lookback:]]
    highs = [value for value in highs if value is not None]
    return len(highs) >= 3 and highs[-1] >= max(highs[:-1])


def calculate_bollinger_bands(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[int, dict[str, float | None]]:
    result: dict[int, dict[str, float | None]] = {}
    for i in range(len(closes)):
        if i + 1 < period:
            continue
        window = closes[i + 1 - period : i + 1]
        middle = sum(window) / period
        variance = sum((x - middle) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper = middle + num_std * std
        lower = middle - num_std * std
        bandwidth = (upper - lower) / middle if middle > 0 else None
        pct_b = (closes[i] - lower) / (upper - lower) if (upper - lower) > 0 else None
        result[i] = {
            "middle": round(middle, 4),
            "upper": round(upper, 4),
            "lower": round(lower, 4),
            "bandwidth": round(bandwidth, 6) if bandwidth is not None else None,
            "pct_b": round(pct_b, 4) if pct_b is not None else None,
        }
    return result


def _find_local_extrema(values: list[float | None], mode: str = "min") -> list[int]:
    """找到序列中的局部极值点索引。

    Args:
        values: 指标序列（可能含 None）
        mode: "min" 找极小值，"max" 找极大值
    """
    extrema: list[int] = []
    for i in range(1, len(values) - 1):
        v = values[i]
        if v is None:
            continue
        v_prev = values[i - 1]
        v_next = values[i + 1]
        if v_prev is None or v_next is None:
            continue
        if mode == "min" and v < v_prev and v < v_next:
            extrema.append(i)
        elif mode == "max" and v > v_prev and v > v_next:
            extrema.append(i)
    return extrema


def detect_bullish_divergence(bars: list[dict[str, Any]], rsi_series: list[float | None], lookback: int = 12) -> bool:
    """看多背离：价格创新低但 RSI 未创新低。

    标准背离检测：
    1. 找 RSI 的局部极小值点（谷底）
    2. 取最近的两个谷底
    3. 判断价格创新低但 RSI 未创新低
    """
    if not bars or not rsi_series or len(bars) < lookback or len(rsi_series) < lookback:
        return False
    window_start = len(bars) - lookback
    closes: list[float | None] = []
    rsi_window: list[float | None] = []
    for i in range(window_start, len(bars)):
        closes.append(_num(bars[i].get("close")))
        rsi_window.append(rsi_series[i] if i < len(rsi_series) else None)

    # 找 RSI 局部极小值点
    troughs = _find_local_extrema(rsi_window, mode="min")
    if len(troughs) < 2:
        # 如果没有两个极小值点，检查窗口首尾
        # 简化：只要 RSI 和价格在窗口两端的趋势相反就算
        first_valid_rsi = None
        last_valid_rsi = None
        first_valid_close = None
        last_valid_close = None
        for i in range(len(rsi_window)):
            if rsi_window[i] is not None and first_valid_rsi is None:
                first_valid_rsi = rsi_window[i]
                first_valid_close = closes[i]
            if rsi_window[len(rsi_window) - 1 - i] is not None and last_valid_rsi is None:
                last_valid_rsi = rsi_window[len(rsi_window) - 1 - i]
                last_valid_close = closes[len(rsi_window) - 1 - i]
        if all(v is not None for v in [first_valid_rsi, last_valid_rsi, first_valid_close, last_valid_close]):
            # 价格创新低 but RSI 未创新低
            if last_valid_close < first_valid_close and last_valid_rsi > first_valid_rsi:
                return True
        return False

    # 取最近两个谷底
    t1, t2 = troughs[-2], troughs[-1]
    price1, price2 = closes[t1], closes[t2]
    rsi1, rsi2 = rsi_window[t1], rsi_window[t2]
    if any(v is None for v in [price1, price2, rsi1, rsi2]):
        return False
    # 价格创新低 but RSI 未创新低 = 看多背离
    return price2 < price1 and rsi2 > rsi1


def detect_bearish_divergence(bars: list[dict[str, Any]], rsi_series: list[float | None], lookback: int = 12) -> bool:
    """看空背离：价格创新高但 RSI 未创新高。

    标准背离检测：
    1. 找 RSI 的局部极大值点（峰顶）
    2. 取最近的两个峰顶
    3. 判断价格创新高但 RSI 未创新高
    """
    if not bars or not rsi_series or len(bars) < lookback or len(rsi_series) < lookback:
        return False
    window_start = len(bars) - lookback
    closes: list[float | None] = []
    rsi_window: list[float | None] = []
    for i in range(window_start, len(bars)):
        closes.append(_num(bars[i].get("close")))
        rsi_window.append(rsi_series[i] if i < len(rsi_series) else None)

    # 找 RSI 局部极大值点
    peaks = _find_local_extrema(rsi_window, mode="max")
    if len(peaks) < 2:
        # 简化：检查窗口首尾
        first_valid_rsi = None
        last_valid_rsi = None
        first_valid_close = None
        last_valid_close = None
        for i in range(len(rsi_window)):
            if rsi_window[i] is not None and first_valid_rsi is None:
                first_valid_rsi = rsi_window[i]
                first_valid_close = closes[i]
            if rsi_window[len(rsi_window) - 1 - i] is not None and last_valid_rsi is None:
                last_valid_rsi = rsi_window[len(rsi_window) - 1 - i]
                last_valid_close = closes[len(rsi_window) - 1 - i]
        if all(v is not None for v in [first_valid_rsi, last_valid_rsi, first_valid_close, last_valid_close]):
            # 价格创新高 but RSI 未创新高
            if last_valid_close > first_valid_close and last_valid_rsi < first_valid_rsi:
                return True
        return False

    # 取最近两个峰顶
    p1, p2 = peaks[-2], peaks[-1]
    price1, price2 = closes[p1], closes[p2]
    rsi1, rsi2 = rsi_window[p1], rsi_window[p2]
    if any(v is None for v in [price1, price2, rsi1, rsi2]):
        return False
    # 价格创新高 but RSI 未创新高 = 看空背离
    return price2 > price1 and rsi2 < rsi1


def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> dict[str, list[float | None]]:
    n = len(closes)
    if n < period * 2:
        return {"adx": [None] * n, "plus_di": [None] * n, "minus_di": [None] * n}
    tr_list: list[float] = [0.0]
    plus_dm_list: list[float] = [0.0]
    minus_dm_list: list[float] = [0.0]
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)
        up_move = max(h - highs[i - 1], 0)
        down_move = max(lows[i - 1] - l, 0)
        if up_move > down_move:
            plus_dm_list.append(up_move)
            minus_dm_list.append(0.0)
        elif down_move > up_move:
            plus_dm_list.append(0.0)
            minus_dm_list.append(down_move)
        else:
            plus_dm_list.append(0.0)
            minus_dm_list.append(0.0)
    tr_smooth = sum(tr_list[:period]) / period
    plus_smooth = sum(plus_dm_list[:period]) / period
    minus_smooth = sum(minus_dm_list[:period]) / period
    di_plus: list[float | None] = [None] * period
    di_minus: list[float | None] = [None] * period
    dx_list: list[float] = []
    for i in range(period, n):
        tr_smooth = (tr_smooth * (period - 1) + tr_list[i]) / period
        plus_smooth = (plus_smooth * (period - 1) + plus_dm_list[i]) / period
        minus_smooth = (minus_smooth * (period - 1) + minus_dm_list[i]) / period
        pdi = (plus_smooth / tr_smooth * 100) if tr_smooth > 0 else 0
        mdi = (minus_smooth / tr_smooth * 100) if tr_smooth > 0 else 0
        di_plus.append(pdi)
        di_minus.append(mdi)
        denom = pdi + mdi
        dx_list.append(abs(pdi - mdi) / denom * 100 if denom > 0 else 0)
    adx_values: list[float | None] = [None] * (period * 2)
    if len(dx_list) >= period:
        adx_smooth = sum(dx_list[:period]) / period
        for idx, dx in enumerate(dx_list[period:], start=period):
            adx_smooth = (adx_smooth * (period - 1) + dx) / period
            adx_values.append(adx_smooth)
        pad = period * 2 - len(adx_values)
        adx_values = [None] * max(pad, 0) + adx_values[max(pad, 0):]
        while len(adx_values) < n:
            adx_values.append(None)
    adx_values = adx_values[:n]
    return {"adx": adx_values, "plus_di": di_plus, "minus_di": di_minus}

