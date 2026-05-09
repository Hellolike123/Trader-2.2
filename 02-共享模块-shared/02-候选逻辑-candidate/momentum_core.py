from __future__ import annotations

import math
from typing import Any

from light_data import to_float


def _ema(values: list[float], period: int) -> list[float | None]:
    if not values or period <= 0:
        return [None] * len(values)
    alpha = 2 / (period + 1)
    result: list[float | None] = []
    ema: float | None = None
    for v in values:
        ema = v if ema is None else v * alpha + ema * (1 - alpha)
        result.append(ema)
    return result


def calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    diffs: list[float] = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains: list[float] = [max(d, 0.0) for d in diffs]
    losses: list[float] = [abs(min(d, 0.0)) for d in diffs]
    result: list[float | None] = [None] * len(closes)
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(closes)):
        if i > period:
            avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
            avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        result[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return result


def calc_macd(closes: list[float]) -> dict[str, Any]:
    if len(closes) < 26:
        return {"macd_line": None, "dea": None, "histogram": None, "hist_prev": None, "golden_cross": False, "death_cross": False}
    ema12 = sum(closes[:12]) / 12.0
    ema26 = sum(closes[:26]) / 26.0
    macd_line: float | None = None
    macd_prev: float | None = None
    dea: float | None = None
    dea_prev: float | None = None
    hist: float | None = None
    dea_buffer: list[float] = []
    for i in range(12, len(closes)):
        c = closes[i]
        ema12 = ema12 * 11 / 13 + c * 2 / 13
        if i >= 26:
            ema26 = ema26 * 25 / 27 + c * 2 / 27
            curr_macd = ema12 - ema26
            dea_buffer.append(curr_macd)
            if len(dea_buffer) == 9:
                dea = sum(dea_buffer) / 9.0
                macd_line = curr_macd
            elif len(dea_buffer) > 9 and dea is not None:
                macd_prev = macd_line
                dea_prev = dea
                dea = dea * 8 / 10 + curr_macd * 2 / 10
                macd_line = curr_macd
    hist = macd_line - dea if (macd_line is not None and dea is not None) else None
    gc = (
        macd_prev is not None
        and dea_prev is not None
        and macd_line is not None
        and dea is not None
        and macd_prev <= dea_prev
        and macd_line > dea
    )
    dc = (
        macd_prev is not None
        and dea_prev is not None
        and macd_line is not None
        and dea is not None
        and macd_prev >= dea_prev
        and macd_line < dea
    )
    return {"macd_line": macd_line, "dea": dea, "histogram": hist, "golden_cross": gc, "death_cross": dc}


def calc_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> dict[str, Any]:
    n = len(closes)
    if n < period * 2:
        return {"adx": None, "plus_di": None, "minus_di": None, "strong_trend": False, "di_uptrend": False}
    tr: list[float] = [0.0]
    pdi: list[float] = [0.0]
    mdi: list[float] = [0.0]
    for i in range(1, n):
        h, l_, pc = highs[i], lows[i], closes[i - 1]
        tr.append(max(h - l_, abs(h - pc), abs(l_ - pc)))
        up = max(h - highs[i - 1], 0)
        dn = max(lows[i - 1] - l_, 0)
        if up > dn:
            pdi.append(up)
            mdi.append(0.0)
        elif dn > up:
            pdi.append(0.0)
            mdi.append(dn)
        else:
            pdi.append(0.0)
            mdi.append(0.0)
    tr_s = sum(tr[:period]) / period
    pdi_s = sum(pdi[:period]) / period
    mdi_s = sum(mdi[:period]) / period
    dx_list: list[float] = []
    for i in range(period, n):
        tr_s = (tr_s * (period - 1) + tr[i]) / period
        pdi_s = (pdi_s * (period - 1) + pdi[i]) / period
        mdi_s = (mdi_s * (period - 1) + mdi[i]) / period
        p = (pdi_s / tr_s * 100) if tr_s > 0 else 0
        m = (mdi_s / tr_s * 100) if tr_s > 0 else 0
        denom = p + m
        dx_list.append(abs(p - m) / denom * 100 if denom > 0 else 0)
    if len(dx_list) < period:
        return {"adx": None, "plus_di": None, "minus_di": None, "strong_trend": False, "di_uptrend": False}
    adx_s = sum(dx_list[:period]) / period
    for dx in dx_list[period:]:
        adx_s = (adx_s * (period - 1) + dx) / period
    return {"adx": adx_s, "plus_di": p, "minus_di": m, "strong_trend": adx_s > 25, "di_uptrend": p > m}


def calc_bollinger(closes: list[float], period: int = 20, num_std: float = 2.0) -> dict[str, Any]:
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None, "pct_b": None, "squeeze": False}
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((x - middle) ** 2 for x in window) / period
    std = max(math.sqrt(variance), 1e-10)
    upper = middle + num_std * std
    lower = middle - num_std * std
    pct_b = (closes[-1] - lower) / (upper - lower)
    bandwidth = (upper - lower) / middle if middle > 0 else 0
    return {"upper": round(upper, 4), "middle": round(middle, 4), "lower": round(lower, 4), "pct_b": round(pct_b, 4), "squeeze": bandwidth < 0.03}


def assess_momentum(bars: list[dict]) -> dict[str, Any]:
    if len(bars) < 30:
        return {"direction": "neutral", "score": 50, "signals": [], "rsi": None, "macd": None, "adx": None, "bollinger": None, "strength": "insufficient"}
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for b in bars:
        c = to_float(b.get("close"))
        h = to_float(b.get("high"))
        l_ = to_float(b.get("low"))
        if c is None or h is None or l_ is None:
            continue
        closes.append(c)
        highs.append(h)
        lows.append(l_)
    if len(closes) < 30:
        return {"direction": "neutral", "score": 50, "signals": [], "strength": "insufficient"}
    rsi = calc_rsi(closes, 14)
    macd = calc_macd(closes)
    adx = calc_adx(highs, lows, closes, 14)
    bb = calc_bollinger(closes, 20, 2.0)
    last_rsi = rsi[-1] if rsi else None
    prev_rsi = rsi[-2] if rsi and len(rsi) >= 2 else None
    rsi_rising = prev_rsi is not None and last_rsi is not None and last_rsi > prev_rsi
    rsi_falling = prev_rsi is not None and last_rsi is not None and last_rsi < prev_rsi
    rsi_oversold = last_rsi is not None and last_rsi < 30
    rsi_overbought = last_rsi is not None and last_rsi > 70
    macd_golden = macd.get("golden_cross", False)
    macd_death = macd.get("death_cross", False)
    macd_hist = macd.get("histogram")
    macd_positive = macd_hist is not None and macd_hist > 0
    bb_lower = bb.get("lower")
    bb_upper = bb.get("upper")
    bb_pct_b = bb.get("pct_b")
    bb_below = bb_pct_b is not None and bb_pct_b < 0
    bb_above = bb_pct_b is not None and bb_pct_b > 1
    bb_squeeze = bb.get("squeeze", False)
    strong_trend = adx.get("strong_trend", False)
    di_up = adx.get("di_uptrend", False)
    last_close = closes[-1]
    current = last_close
    signals: list[str] = []
    score = 50
    if rsi_oversold or bb_below:
        if rsi_rising or macd_golden:
            signals.append("RSI超卖+回升(看多)")
            score += 15
        elif not rsi_falling:
            signals.append("RSI超卖区(潜在反弹)")
            score += 5
    if rsi_overbought or bb_above:
        if rsi_falling or macd_death:
            signals.append("RSI超买+回落(看空)")
            score -= 15
        elif not rsi_rising:
            signals.append("RSI超买区(潜在回调)")
            score -= 5
    if macd_golden and rsi_rising:
        signals.append("MACD金叉+RSI上升(偏多)")
        score += 12
    if macd_death and rsi_falling:
        signals.append("MACD死叉+RSI下降(偏空)")
        score -= 12
    if macd_positive and not rsi_falling:
        signals.append("MACD柱为正(偏多)")
        score += 8
    if strong_trend:
        if di_up:
            signals.append("ADX强趋势(上涨)")
            score += 10
        else:
            signals.append("ADX强趋势(下跌)")
            score -= 10
    if bb_squeeze:
        signals.append("布林收口(变盘前兆)")
        score += 0
    if macd_golden and macd_positive and rsi_rising and di_up:
        signals.append("多指标共振(强烈看多)")
        score += 10
    if macd_death and not macd_positive and rsi_falling and not di_up:
        signals.append("多指标共振(强烈看空)")
        score -= 10
    score = max(0, min(100, round(score)))
    if score >= 65:
        direction = "bullish"
    elif score <= 35:
        direction = "bearish"
    else:
        direction = "neutral"
    return {
        "direction": direction,
        "score": score,
        "signals": signals,
        "rsi": {"last": last_rsi, "prev": prev_rsi, "rising": rsi_rising, "oversold": rsi_oversold, "overbought": rsi_overbought},
        "macd": {"golden_cross": macd_golden, "death_cross": macd_death, "histogram": macd_hist, "positive": macd_positive},
        "adx": {"value": adx.get("adx"), "strong_trend": strong_trend, "di_uptrend": di_up},
        "bollinger": {"pct_b": bb_pct_b, "squeeze": bb_squeeze, "lower": bb_lower, "upper": bb_upper},
    }


def momentum_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    return {"momentum": assess_momentum(bars)}
