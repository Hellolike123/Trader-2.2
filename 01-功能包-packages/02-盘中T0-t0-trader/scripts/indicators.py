from __future__ import annotations

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


def calculate_ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0 or not values:
        return [None for _ in values]
    alpha = 2 / (period + 1)
    result: list[float | None] = []
    ema: float | None = None
    for value in values:
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
    dif_values = [value if value is not None else 0.0 for value in dif]
    dea_raw = calculate_ema(dif_values, signal)
    dea: list[float | None] = [None if item is None else item for item in dea_raw]
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
