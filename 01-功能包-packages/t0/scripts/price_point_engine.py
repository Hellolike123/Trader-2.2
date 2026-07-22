from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from trader_shared.safe_cast import safe_max
from t0_config import (
    BUY_ACCEPT_FACTOR,
    BUY_ACCEPT_FACTOR_AGGRESSIVE,
    BUY_ACCEPT_FACTOR_CONSERVATIVE,
    BUY_CONFIRM_FACTOR,
    DEFAULT_ZONE_WIDTH_PCT,
    INVALID_ABOVE_RESISTANCE,
    INVALID_BELOW_SUPPORT,
    GOOD_T_AMPLITUDE_PCT,
    MIN_5M_BARS,
    MACD_WARMUP_BARS,
    MIN_T_AMPLITUDE_PCT,
    MIN_TRIGGER_MATCHES,
    MIN_T_NET_SPACE_PCT,
    MIN_SELL_NET_SPACE_PCT,
    PRICE_TICK,
    SELL_ACCEPT_FACTOR,
    SELL_ACCEPT_FACTOR_AGGRESSIVE,
    SELL_ACCEPT_FACTOR_CONSERVATIVE,
    SLIPPAGE_HIGH_VOLUME_RATIO,
    SLIPPAGE_LOW_VOLUME_RATIO,
    STRONG_TRIGGER_MATCHES,
    STRUCTURE_WINDOW,
    TREND_FILTER_DAYS,
    TREND_FILTER_ENABLED,
    TREND_FILTER_EXTREME_DROP_PCT,
    TREND_FILTER_EXTREME_ONLY,
    VOLUME_EXPAND_RATIO,
    VOLUME_SHRINK_RATIO,
    ZONE_AMPLITUDE_FACTOR,
    ZONE_MAX_WIDTH_PCT,
    ZONE_MIN_WIDTH_PCT,
    ENABLE_ICT_EXECUTION,
    ICT_RECENT_WINDOW,
    ICT_MIN_STRENGTH,
    ICT_STRUCTURE_LOOKBACK,
    ICT_SWEEP_LOOKBACK,
    ADX_STRONG_THRESHOLD,
    ADX_WEAK_THRESHOLD,
    ATR_STOP_FACTOR,
    ATR_STOP_MAX_PCT,
    ATR_STOP_MIN_PCT,
    LEFT_TRIGGER_CORE,
    LEFT_TRIGGER_AUX,
    LEFT_NO_SUPPORT_BLOCK,
)
from ict_execution import build_ict_signal
from indicators import (
    calculate_adx,
    calculate_bollinger_bands,
    detect_bearish_divergence,
    detect_bullish_divergence,
    calculate_macd,
    calculate_rsi,
    calculate_volume_ratio,
    calculate_vwap_from_bars,
    detect_lower_shadow,
    detect_upper_shadow,
    is_new_high_recent,
    is_new_low_recent,
)


STATUSES = {"已触发", "观察中", "未进入候选区", "被阻断", "数据不足", "触发过期", "熔断中"}
MIN_OBSERVE_SPREAD_ABS = 0.05
MIN_OBSERVE_SPREAD_PCT = 0.005


def num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(round(value / PRICE_TICK) * PRICE_TICK, 2)


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def price_or_pending(value: float | None) -> str:
    return f"{value:.2f}元" if value is not None else "未触发，暂不生成"


def min_observe_spread(current: float) -> float:
    return max(MIN_OBSERVE_SPREAD_ABS, current * MIN_OBSERVE_SPREAD_PCT)


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def is_trade_time(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    current = now.time()
    return (time(9, 30) <= current <= time(11, 30)) or (time(13, 0) <= current <= time(15, 0))


def completed_5m_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    if not bars:
        return []
    now = now or datetime.now()
    completed: list[dict[str, Any]] = []
    for bar in bars:
        if bar is None:
            continue
        dt = parse_dt(bar.get("time") or bar.get("date"))
        if dt is None:
            completed.append(bar)
            continue
        if dt.date() < now.date():
            completed.append(bar)
        elif dt + timedelta(minutes=5) <= now.replace(second=0, microsecond=0):
            completed.append(bar)
    return completed


def today_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """只保留今日的 bar（VWAP 是日内指标，不能跨日计算）。"""
    if not bars:
        return []
    now = now or datetime.now()
    result: list[dict[str, Any]] = []
    for bar in bars:
        if bar is None:
            continue
        dt = parse_dt(bar.get("time") or bar.get("date"))
        if dt is None or dt.date() == now.date():
            result.append(bar)
    return result


def data_status(quote: dict[str, Any], daily: list[dict[str, Any]], bars_5m: list[dict[str, Any]], now: datetime | None = None) -> str:
    now = now or datetime.now()
    if not quote or not daily or len(bars_5m) < MIN_5M_BARS:
        return "degraded"
    last_dt = parse_dt((bars_5m[-1] or {}).get("time") or (bars_5m[-1] or {}).get("date"))
    if not is_trade_time(now):
        return "partial"
    if last_dt is None or last_dt.date() != now.date():
        return "degraded"
    delay_minutes = (now - last_dt).total_seconds() / 60
    return "full" if delay_minutes <= 12 else "degraded"


def values(bars: list[dict[str, Any]], key: str) -> list[float]:
    return [float(item[key]) for item in bars if num(item.get(key)) is not None]


def add_level(levels: list[dict[str, Any]], name: str, price_value: float | None, weight: float) -> None:
    rounded = round_price(price_value)
    if rounded is not None and rounded > 0:
        # 累积「触碰次数」：近价(1.5%)已存在则合并计数+1，用于 choose_level 优先选被多周期共同指向的价位
        for lv in levels:
            if abs(float(lv.get("price") or 0) - rounded) / max(rounded, 1) < 0.015:
                lv["touches"] = int(lv.get("touches") or 1) + 1
                break
        else:
            levels.append({"name": name, "price": rounded, "weight": weight, "touches": 1})


def find_key_levels(report_data: dict[str, Any], structure_result: dict[str, Any] | None = None) -> dict[str, Any]:
    quote = report_data["quote"]
    daily = report_data["daily_bars"]
    bars_5m = report_data["kline_5m_completed"]
    bars_15m = report_data.get("kline_15m") or []
    bars_30m = report_data.get("kline_30m") or []
    current = float(report_data["current_price"])
    vwap = calculate_vwap_from_bars(today_bars(bars_5m))
    recent5 = daily[-5:] if len(daily) >= 5 else daily
    recent20 = daily[-STRUCTURE_WINDOW:] if len(daily) >= STRUCTURE_WINDOW else daily
    support: list[dict[str, Any]] = []
    resistance: list[dict[str, Any]] = []
    # 优先注入trader结构分析的结果，weight=1.1确保被choose_level优先选中
    if structure_result is not None:
        ts = float(structure_result.get("support") or 0)
        tr = float(structure_result.get("resistance") or 0)
        if ts > 0:
            add_level(support, "结构支撑(trader)", ts, 1.1)
        if tr > 0:
            add_level(resistance, "结构阻力(trader)", tr, 1.1)
    min5 = min(values(recent5, "low"), default=None)
    max5 = max(values(recent5, "high"), default=None)
    if min5 is not None:
        add_level(support, "5日低点", min5, 1.0)
    if max5 is not None:
        add_level(resistance, "5日高点", max5, 1.0)
    add_level(support, "今日低点", num(quote.get("low")), 0.9)
    add_level(resistance, "今日高点", num(quote.get("high")), 0.9)
    min20 = min(values(recent20, "low"), default=None)
    max20 = max(values(recent20, "high"), default=None)
    if min20 is not None:
        add_level(support, "20日低点", min20, 0.8)
    if max20 is not None:
        add_level(resistance, "20日高点", max20, 0.8)
    min5m = min(values(bars_5m[-12:], "low"), default=None)
    max5m = max(values(bars_5m[-12:], "high"), default=None)
    if min5m is not None:
        add_level(support, "5m低点", min5m, 0.7)
    if max5m is not None:
        add_level(resistance, "5m高点", max5m, 0.7)
    min15m = min(values(bars_15m[-8:], "low"), default=None)
    max15m = max(values(bars_15m[-8:], "high"), default=None)
    if min15m is not None:
        add_level(support, "15m低点", min15m, 0.7)
    if max15m is not None:
        add_level(resistance, "15m高点", max15m, 0.7)
    min30m = min(values(bars_30m[-8:], "low"), default=None)
    max30m = max(values(bars_30m[-8:], "high"), default=None)
    if min30m is not None:
        add_level(support, "30m低点", min30m, 0.8)
    if max30m is not None:
        add_level(resistance, "30m高点", max30m, 0.8)
    add_level(support, "VWAP", vwap, 0.6)
    add_level(resistance, "VWAP上方偏离", vwap * 1.01 if vwap else None, 0.6)
    bb = calculate_bollinger_bands(values(bars_5m, "close"), period=20, num_std=2.0)
    bb_last = bb.get(max(bb.keys()), {}) if bb else {}
    bb_lower = bb_last.get("lower")
    bb_upper = bb_last.get("upper")
    if bb_lower:
        add_level(support, "布林下轨(20,2σ)", round_price(bb_lower), 0.4)
    if bb_upper:
        add_level(resistance, "布林上轨(20,2σ)", round_price(bb_upper), 0.4)
    if bb_last.get("middle"):
        add_level(support, "布林中轨", round_price(bb_last["middle"]), 0.3)
        add_level(resistance, "布林中轨", round_price(bb_last["middle"]), 0.3)
    # 破位过滤：剔除已有效跌破的支撑 / 已有效突破的阻力，避免把失效价位当有效位
    BREAK_TOL = 0.015

    def _filter_broken(levels: list[dict[str, Any]], below: bool) -> list[dict[str, Any]]:
        if not (current and current > 0):
            return list(levels)
        kept: list[dict[str, Any]] = []
        for lv in levels:
            p = float(lv.get("price") or 0)
            if p <= 0:
                kept.append(lv)
                continue
            if below and p < current * (1 - BREAK_TOL):
                continue  # 已有效跌破 → 失效支撑，剔除
            if (not below) and p > current * (1 + BREAK_TOL):
                continue  # 已有效突破 → 失效阻力，剔除
            kept.append(lv)
        return kept

    support = _filter_broken(support, below=True)
    resistance = _filter_broken(resistance, below=False)
    main_support = choose_level(support, current, below=True)
    main_resistance = choose_level(resistance, current, below=False)
    return {"support_levels": support, "resistance_levels": resistance, "main_support": main_support, "main_resistance": main_resistance, "vwap": round_price(vwap)}


def choose_level(levels: list[dict[str, Any]], current: float, *, below: bool) -> dict[str, Any]:
    candidates = [item for item in levels if (item["price"] <= current if below else item["price"] >= current)]
    if not candidates:
        candidates = sorted(levels, key=lambda item: abs(item["price"] - current))

    if not candidates:
        return {"name": "现价兜底", "price": round_price(current), "weight": 0.1}

    def distance(item: dict[str, Any]) -> float:
        return abs(float(item["price"]) - current) / max(current, 1)

    primary = [item for item in candidates if float(item.get("weight") or 0) >= 0.7 and not str(item.get("name") or "").startswith("VWAP")]
    if not primary:
        return sorted(candidates, key=lambda item: (-int(item.get("touches") or 0), distance(item), -float(item.get("weight") or 0)))[0]

    best_primary = sorted(primary, key=lambda item: (-int(item.get("touches") or 0), distance(item), -float(item.get("weight") or 0)))[0]
    vwap_items = [item for item in candidates if str(item.get("name") or "").startswith("VWAP")]
    if vwap_items:
        best_vwap = sorted(vwap_items, key=distance)[0]
        if distance(best_vwap) <= 0.008 and distance(best_primary) >= 0.08:
            return best_vwap
    return best_primary


def intraday_amplitude_pct(quote: dict[str, Any]) -> float | None:
    pre_close = num(quote.get("pre_close"))
    high = num(quote.get("high"))
    low = num(quote.get("low"))
    if pre_close and high is not None and low is not None and high >= low:
        return (high - low) / pre_close
    return None


def space_state(amplitude_pct: float | None) -> str:
    if amplitude_pct is None:
        return "unknown"
    if amplitude_pct < MIN_T_AMPLITUDE_PCT:
        return "too_small"
    if amplitude_pct < GOOD_T_AMPLITUDE_PCT:
        return "normal"
    return "good"


def build_candidate_zones(report_data: dict[str, Any], key_levels: dict[str, Any]) -> dict[str, Any]:
    amplitude_pct = intraday_amplitude_pct(report_data["quote"])
    if amplitude_pct is not None:
        width_pct = min(ZONE_MAX_WIDTH_PCT, max(ZONE_MIN_WIDTH_PCT, amplitude_pct * ZONE_AMPLITUDE_FACTOR))
    else:
        width_pct = DEFAULT_ZONE_WIDTH_PCT
    support = key_levels["main_support"]["price"]
    resistance = key_levels["main_resistance"]["price"]
    return {
        "amplitude_pct": amplitude_pct,
        "space_state": space_state(amplitude_pct),
        "buy_zone": {
            "main_support": support,
            "lower": round_price(support * (1 - width_pct)),
            "upper": round_price(support * (1 + width_pct)),
            "width_pct": width_pct,
            "source": key_levels["main_support"]["name"],
        },
        "sell_zone": {
            "main_resistance": resistance,
            "lower": round_price(resistance * (1 - width_pct)),
            "upper": round_price(resistance * (1 + width_pct)),
            "width_pct": width_pct,
            "source": key_levels["main_resistance"]["name"],
        },
    }


def latest_indicator_state(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = values(bars, "close")
    macd = calculate_macd(closes)
    rsi = calculate_rsi(closes)
    hist = macd.get("hist") or []
    vwap = calculate_vwap_from_bars(today_bars(bars))
    prev_vwap = calculate_vwap_from_bars(today_bars(bars[:-1])) if len(bars) >= 2 else None
    bb = calculate_bollinger_bands(closes, period=20, num_std=2.0)
    bb_last = bb.get(safe_max(bb.keys())) if bb else {}
    bb_pct_b = bb_last.get("pct_b")
    bb_squeeze = (bb_last.get("bandwidth") or 999) < 0.03
    highs = values(bars, "high")
    lows = values(bars, "low")
    adx = calculate_adx(highs, lows, closes, period=14)
    adx_last = adx["adx"][-1] if adx["adx"] else None
    pdi_last = adx["plus_di"][-1] if adx["plus_di"] else None
    mdi_last = adx["minus_di"][-1] if adx["minus_di"] else None
    return {
        "closes": closes,
        "vwap": vwap,
        "prev_vwap": prev_vwap,
        "volume_ratio": calculate_volume_ratio(bars),
        "macd_ready": len(closes) >= MACD_WARMUP_BARS,
        "hist": hist,
        "rsi": rsi,
        "last_hist": hist[-1] if hist else None,
        "prev_hist": hist[-2] if len(hist) >= 2 else None,
        "last_rsi": rsi[-1] if rsi else None,
        "prev_rsi": rsi[-2] if len(rsi) >= 2 else None,
        "bb": bb_last,
        "pct_b": bb_pct_b,
        "bb_squeeze": bb_squeeze,
        "adx": adx_last,
        "plus_di": pdi_last,
        "minus_di": mdi_last,
        "strong_trend": adx_last is not None and adx_last > ADX_STRONG_THRESHOLD,
        "weak_trend": adx_last is not None and adx_last < ADX_WEAK_THRESHOLD,
        "di_uptrend": pdi_last is not None and mdi_last is not None and pdi_last > mdi_last,
        "di_downtrend": pdi_last is not None and mdi_last is not None and mdi_last > pdi_last,
    }


def macd_green_shrinking(state: dict[str, Any]) -> bool:
    if not state.get("macd_ready"):
        return False
    last = state.get("last_hist")
    prev = state.get("prev_hist")
    return last is not None and prev is not None and last < 0 and abs(last) < abs(prev)


def macd_red_shrinking(state: dict[str, Any]) -> bool:
    if not state.get("macd_ready"):
        return False
    last = state.get("last_hist")
    prev = state.get("prev_hist")
    return last is not None and prev is not None and last > 0 and last < prev


def rsi_turning_up(state: dict[str, Any]) -> bool:
    last = state.get("last_rsi")
    prev = state.get("prev_rsi")
    return last is not None and prev is not None and last > prev and prev <= 45


def rsi_turning_down(state: dict[str, Any]) -> bool:
    last = state.get("last_rsi")
    prev = state.get("prev_rsi")
    return last is not None and prev is not None and last < prev and prev >= 55


def t0_net_space_pct(zones: dict[str, Any]) -> float | None:
    buy_upper = zones["buy_zone"].get("upper")
    sell_lower = zones["sell_zone"].get("lower")
    if buy_upper is None or sell_lower is None or buy_upper <= 0:
        return None
    return (sell_lower - buy_upper) / buy_upper


def sell_net_space_pct(current: float, zones: dict[str, Any]) -> float | None:
    sell_lower = zones["sell_zone"].get("lower")
    if sell_lower is None or current <= 0:
        return None
    return (sell_lower - current) / current


def observation_validity(report_data: dict[str, Any], zones: dict[str, Any]) -> dict[str, Any]:
    current = float(report_data["current_price"])
    data_status_value = str(report_data.get("data_status") or "")
    if data_status_value in ("degraded", "failed"):
        reason = "盘中数据不足，暂不生成T0观察价"
        return {"buy_valid": False, "sell_valid": False, "buy_reason": reason, "sell_reason": reason}
    if data_status_value == "partial":
        reason = "非交易时段或数据部分，暂不生成T0观察价"
        return {"buy_valid": False, "sell_valid": False, "buy_reason": reason, "sell_reason": reason}

    net_space = report_data.get("t0_net_space_pct")
    if net_space is not None and net_space < MIN_T_NET_SPACE_PCT:
        reason = "低吸和高抛观察位距离太近，扣掉滑点后没有有效差价"
        return {"buy_valid": False, "sell_valid": False, "buy_reason": reason, "sell_reason": reason}

    buy_valid = True
    sell_valid = True
    buy_reason = ""
    sell_reason = ""
    sell_space = report_data.get("sell_net_space_pct")
    sell_zone = zones.get("sell_zone") or {}
    sell_observe = num(sell_zone.get("lower"))
    sell_source = str(sell_zone.get("source") or "")
    if sell_space is not None and sell_space < MIN_SELL_NET_SPACE_PCT:
        sell_valid = False
        sell_reason = "高抛观察位距离现价太近，等待更有效压力位形成"
    elif sell_source == "5m高点" and sell_observe is not None and abs(sell_observe - current) < min_observe_spread(current):
        sell_valid = False
        sell_reason = "5m高点太贴近现价，暂不作为高抛观察位"

    return {"buy_valid": buy_valid, "sell_valid": sell_valid, "buy_reason": buy_reason, "sell_reason": sell_reason}


def _close_vals(bars: list[dict[str, Any]]) -> list[float]:
    vals: list[float] = []
    for b in bars:
        try:
            vals.append(float(b.get("close")))
        except (TypeError, ValueError):
            pass
    return vals


def _trend_filter(daily_bars: list[dict[str, Any]]) -> bool:
    """趋势过滤器：T0专用，比日线级别更宽松。

    TREND_FILTER_EXTREME_ONLY=True 时，仅在极端下行（N日累计跌幅超阈值）才阻断，
    避免普通日线趋势下行时完全无法触发5分钟级别的做T信号。
    """
    if not TREND_FILTER_ENABLED:
        return True
    closes = _close_vals(daily_bars)
    n = TREND_FILTER_DAYS
    if len(closes) < n + 1:
        return True
    if TREND_FILTER_EXTREME_ONLY:
        # 极端下行模式：只看最近N日累计跌幅
        recent_start = closes[-(n + 1)]
        recent_end = closes[-1]
        if recent_start <= 0:
            return True
        drop_pct = (recent_end - recent_start) / recent_start
        return drop_pct > TREND_FILTER_EXTREME_DROP_PCT
    else:
        # 传统模式：短期均线 vs 长期均线
        if len(closes) < 30:
            return True
        ma_short = sum(closes[-n:]) / n
        long_avg = sum(closes[:-n]) / max(len(closes) - n, 1)
        if long_avg <= 0:
            return True
        return ma_short > long_avg


def vwap_uptrend(state: dict[str, Any]) -> bool:
    vwap = state.get("vwap")
    prev = state.get("prev_vwap")
    return vwap is not None and prev is not None and float(vwap) > float(prev)


def _ict_strength_meets_minimum(ict: dict[str, Any]) -> bool:
    """检查ICT信号强度是否达到最低门槛。"""
    strength_order = {"weak": 0, "medium": 1, "strong": 2}
    actual = strength_order.get(str(ict.get("confirmation_strength") or "weak"), 0)
    threshold = strength_order.get(ICT_MIN_STRENGTH, 1)
    return actual >= threshold


# ── 5m 威科夫形态检测（T0 专用，轻量级）──────────────────────────────────

def detect_spring_5m(bars: list[dict], support: float) -> dict[str, Any]:
    """Spring 检测（5m 级别）：假跌破后快速有力收回。

    条件：
    1. 最近 5 根 bar 中有跌破支撑
    2. 1-2 根内收回支撑上方
    3. 收回幅度 ≥ 跌幅 × 50%
    4. 跌破时量缩（< 均量 × 0.8）
    5. 排除放量弹簧（量 > 均量 × 1.5）
    """
    if len(bars) < 10 or support <= 0:
        return {"detected": False}

    avg_vol = sum(num(x.get("volume")) or 0 for x in bars[-12:]) / max(len(bars[-12:]), 1)
    if avg_vol <= 0:
        return {"detected": False}

    recent = bars[-5:]
    for i, b in enumerate(recent):
        low = num(b.get("low"))
        close = num(b.get("close"))
        vol = num(b.get("volume")) or 0
        if low is None or close is None:
            continue
        # 条件1：跌破支撑
        if low >= support:
            continue
        # 条件5：放量弹簧 → 直接排除
        if avg_vol > 0 and vol > avg_vol * 1.5:
            continue
        # 条件2：1-2 根内收回
        recharged = False
        for j in range(i + 1, min(i + 3, len(recent))):
            c = num(recent[j].get("close"))
            if c is not None and c >= support:
                recharged = True
                break
        if not recharged:
            # 检查当前 bar 本身是否收回
            if close < support:
                continue
            recharged = True
        if not recharged:
            continue
        # 条件3：收回幅度 ≥ 50%
        drop_depth = support - low
        if drop_depth <= 0:
            continue
        reclaim = close - support
        if reclaim / drop_depth < 0.5:
            continue
        # 条件4：量缩确认
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
        strength = "strong" if vol_ratio < 0.6 and close > support * 1.002 else "ordinary"
        return {
            "detected": True,
            "strength": strength,
            "reason": f"5m刺穿{support:.2f}后收回{reclaim/drop_depth*100:.0f}%，量比{vol_ratio:.1f}",
            "vol_ratio": round(vol_ratio, 2),
        }
    return {"detected": False}


def detect_no_supply_pullback_5m(bars: list[dict], support: float) -> dict[str, Any]:
    """无供给回调（5m 级别）：价格回踩支撑区但成交量明显萎缩，抛压枯竭。

    条件：
    1. 最近 3 根 bar 中有 1 根最低价接近支撑（±1%）
    2. 该根 bar 成交量 < 均量的 0.6 倍（缩量）
    3. 收盘价未跌破支撑
    """
    if len(bars) < 10 or support <= 0:
        return {"detected": False}

    avg_vol = sum(num(x.get("volume")) or 0 for x in bars[-12:]) / max(len(bars[-12:]), 1)
    if avg_vol <= 0:
        return {"detected": False}

    for b in bars[-3:]:
        low = num(b.get("low"))
        close = num(b.get("close"))
        vol = num(b.get("volume"))
        if low is None or close is None or vol is None:
            continue
        near_support = abs(low - support) / support < 0.01
        shrinking = vol < avg_vol * 0.6
        held = close >= support
        if near_support and shrinking and held:
            return {
                "detected": True,
                "reason": f"回踩{support:.2f}附近缩量（量比{vol/avg_vol:.2f}），抛压枯竭",
                "vol_ratio": round(vol / avg_vol, 2),
            }
    return {"detected": False}


def detect_upthrust_5m(bars: list[dict], resistance: float) -> dict[str, Any]:
    """UT 诱多（5m 级别）：价格突破阻力后快速回落，假突破。

    条件：
    1. 最近 3 根 bar 中有 1 根最高价 > resistance（突破）
    2. 该根 bar 收盘价 < resistance（跌回）
    3. 当前价 < resistance（确认回落）
    """
    if len(bars) < 5 or resistance <= 0:
        return {"detected": False}

    for b in bars[-3:]:
        high = num(b.get("high"))
        close = num(b.get("close"))
        vol = num(b.get("volume"))
        if high is None or close is None:
            continue
        if high > resistance and close < resistance:
            avg_vol = sum(num(x.get("volume")) or 0 for x in bars[-12:]) / max(len(bars[-12:]), 1)
            vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
            strength = "strong" if vol_ratio >= 1.3 else "ordinary"
            return {
                "detected": True,
                "strength": strength,
                "reason": f"5m突破{resistance:.2f}后跌回，假突破，量比{vol_ratio:.1f}",
                "vol_ratio": round(vol_ratio, 2),
            }
    return {"detected": False}


def detect_volume_stop_5m(bars: list[dict]) -> dict[str, Any]:
    """放量滞涨（5m 级别）：成交量创新高但价格未创新高。

    条件：
    1. 当前 bar 成交量 > 近 12 根均量的 1.5 倍
    2. 当前 bar 收盘价 <= 前一根收盘价（价格未涨）
    3. 最近 3 根 bar 出现上影线或实体缩小
    """
    if len(bars) < 12:
        return {"detected": False}

    last = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else {}
    vol = num(last.get("volume")) or 0
    avg_vol = sum(num(x.get("volume")) or 0 for x in bars[-12:]) / 12

    if avg_vol <= 0 or vol < avg_vol * 1.5:
        return {"detected": False}

    last_close = num(last.get("close"))
    last_high = num(last.get("high"))
    prev_close = num(prev.get("close"))
    if last_close is None or prev_close is None or last_high is None:
        return {"detected": False}

    price_stagnant = last_close <= prev_close
    has_upper_shadow = last_high is not None and last_close is not None and (last_high - last_close) > (last_close - (num(last.get("open")) or last_close)) * 0.5

    if price_stagnant and has_upper_shadow:
        return {
            "detected": True,
            "reason": f"放量（量比{vol/avg_vol:.1f}）但价格滞涨+上影线",
            "vol_ratio": round(vol / avg_vol, 2),
        }
    return {"detected": False}


def detect_buy_trigger(report_data: dict[str, Any], zones: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bars = report_data["kline_5m_completed"]
    current = float(report_data["current_price"])
    zone = zones["buy_zone"]
    if report_data["data_status"] in ("degraded", "failed", "partial") or len(bars) < MIN_5M_BARS:
        return trigger_result("数据不足", None, [], ["5m数据不足或非交易时段"])
    if report_data.get("space_state") == "too_small":
        return trigger_result("被阻断", None, [], ["日内振幅不足"])
    net_space = report_data.get("t0_net_space_pct")
    if net_space is not None and net_space < MIN_T_NET_SPACE_PCT:
        return trigger_result("被阻断", None, [], ["T0净空间不足"])
    if current > zone["upper"]:
        return trigger_result("未进入候选区", None, [], [])
    if not _trend_filter(report_data.get("daily_bars") or []):
        return trigger_result("趋势下行暂不低吸", None, [], ["30日均线下破长期均线"])
    last = bars[-1]
    blocked = []
    # 放量跌破：永远阻断
    if (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO and current < zone["main_support"]:
        blocked.append("放量跌破主支撑")
    # 非放量跌破：左侧模式不阻断，仅记录为辅助条件
    elif LEFT_NO_SUPPORT_BLOCK and current < zone["main_support"] and current < (num(last.get("close")) or current):
        pass  # 不阻断，继续等条件
    else:
        # 非左侧模式：保留原阻断逻辑
        if current < zone["main_support"] and current < (num(last.get("close")) or current):
            blocked.append("跌破主支撑后未收回")
    ict = report_data.get("ict_signal") or {}
    ict_buy_valid = ict.get("buy_confirmed") and _ict_strength_meets_minimum(ict)
    ict_sell_valid = ict.get("sell_confirmed") and _ict_strength_meets_minimum(ict)
    if ict_sell_valid:
        blocked.append("ICT反向高抛确认")
    if blocked:
        return trigger_result("被阻断", None, [], blocked)
    matched = []
    core_count = 0
    aux_count = 0
    if not is_new_low_recent(bars):
        matched.append("5m不再创新低")
    if (state.get("volume_ratio") or 1) < VOLUME_SHRINK_RATIO:
        matched.append("量能收缩")
    if macd_green_shrinking(state):
        matched.append("MACD绿柱缩短")
        core_count += 1
    rsi_series = state.get("rsi") or []
    if detect_bullish_divergence(bars, rsi_series, lookback=12):
        matched.append("RSI底背离（价格新低RSI未新低）")
        core_count += 1
    if rsi_turning_up(state):
        matched.append("RSI低位拐头")
        core_count += 1
    if state.get("vwap") is not None and current >= float(state["vwap"]):
        matched.append("站回VWAP")
        core_count += 1
    pct_b = state.get("pct_b")
    last_rsi = state.get("last_rsi")
    if pct_b is not None and pct_b < 0 and last_rsi is not None and last_rsi < 30:
        matched.append("布林下轨+RSI超卖共振")
        core_count += 1
    if detect_lower_shadow(last):
        matched.append("出现下影线")
        aux_count += 1
    if current >= zone["main_support"]:
        matched.append("支撑位收回")
        aux_count += 1
    if ict_buy_valid:
        matched.append("ICT下扫后转强")
        aux_count += 1
    # 威科夫 5m 形态：Spring（刺穿后收回）
    spring = detect_spring_5m(bars, zone["main_support"])
    if spring.get("detected"):
        matched.append(f"威科夫Spring({spring['reason']})")
        core_count += 1
    # 威科夫 5m 形态：无供给回调（缩量回踩支撑）
    no_supply = detect_no_supply_pullback_5m(bars, zone["main_support"])
    if no_supply.get("detected"):
        matched.append(f"威科夫无供给({no_supply['reason']})")
        core_count += 1
    # Left-side: 1 core + 1 aux → 已触发
    if LEFT_NO_SUPPORT_BLOCK:
        if core_count >= LEFT_TRIGGER_CORE and aux_count >= LEFT_TRIGGER_AUX:
            status = "已触发"
        else:
            status = "观察中"
    elif state.get("weak_trend"):
        base_count = len(matched) - core_count - aux_count
        effective_aux = 0 if (state.get("strong_trend") and state.get("di_downtrend")) else aux_count
        effective_total = core_count + base_count + effective_aux
        status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
    else:
        base_count = len(matched) - core_count - aux_count
        effective_aux = 0 if (state.get("strong_trend") and state.get("di_downtrend")) else aux_count
        effective_total = core_count + base_count + effective_aux
        status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"
    trigger_time = (last.get("time") or last.get("date")) if status == "已触发" else None
    return trigger_result(status, num(last.get("close")) if status == "已触发" else None, matched, [], trigger_time=trigger_time)



def detect_sell_trigger(report_data: dict[str, Any], zones: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bars = report_data["kline_5m_completed"]
    current = float(report_data["current_price"])
    zone = zones["sell_zone"]
    if report_data["data_status"] in ("degraded", "failed", "partial") or len(bars) < MIN_5M_BARS:
        return trigger_result("数据不足", None, [], ["5m数据不足或非交易时段"])
    if report_data.get("space_state") == "too_small":
        return trigger_result("被阻断", None, [], ["日内振幅不足"])
    net_space = report_data.get("t0_net_space_pct")
    if net_space is not None and net_space < MIN_T_NET_SPACE_PCT:
        return trigger_result("被阻断", None, [], ["T0净空间不足"])
    sell_space = report_data.get("sell_net_space_pct")
    if sell_space is not None and sell_space < MIN_SELL_NET_SPACE_PCT:
        return trigger_result("被阻断", None, [], ["卖出空间不足"])
    if current < zone["lower"]:
        return trigger_result("未进入候选区", None, [], [])
    if not _trend_filter(report_data.get("daily_bars") or []):
        return trigger_result("趋势下行暂不高抛", None, [], ["30日均线下破长期均线"])
    last = bars[-1]
    blocked = []
    if is_new_high_recent(bars):
        blocked.append("最近5m持续创新高")
    if (
        state.get("vwap") is not None
        and current > float(state["vwap"])
        and vwap_uptrend(state)
        and (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO
        and current > zone["main_resistance"]
    ):
        blocked.append("VWAP上行且放量突破主压力")
    ict = report_data.get("ict_signal") or {}
    ict_buy_valid = ict.get("buy_confirmed") and _ict_strength_meets_minimum(ict)
    ict_sell_valid = ict.get("sell_confirmed") and _ict_strength_meets_minimum(ict)
    if ict_buy_valid:
        blocked.append("ICT反向低吸确认")
    if blocked:
        return trigger_result("被阻断", None, [], blocked)
    matched = []
    core_count = 0
    aux_count = 0
    if (state.get("volume_ratio") or 1) <= 1.0:
        matched.append("冲高没有继续放量")
    if (state.get("volume_ratio") or 1) < VOLUME_SHRINK_RATIO or detect_upper_shadow(last):
        matched.append("放量滞涨或缩量上攻")
    if macd_red_shrinking(state):
        matched.append("MACD红柱缩短")
        core_count += 1
    rsi_series = state.get("rsi") or []
    if detect_bearish_divergence(bars, rsi_series, lookback=12):
        matched.append("RSI顶背离（价格新高RSI未新高）")
        core_count += 1
    if rsi_turning_down(state):
        matched.append("RSI高位拐头")
        core_count += 1
    if state.get("vwap") is not None and current <= float(state["vwap"]):
        matched.append("跌回VWAP")
        core_count += 1
    pct_b = state.get("pct_b")
    last_rsi = state.get("last_rsi")
    if pct_b is not None and pct_b > 1 and last_rsi is not None and last_rsi > 70:
        matched.append("布林上轨+RSI超买共振")
        core_count += 1
    if detect_upper_shadow(last):
        matched.append("出现上影线")
        aux_count += 1
    if current <= zone["main_resistance"]:
        matched.append("压力位回落")
        aux_count += 1
    if ict_sell_valid:
        matched.append("ICT上扫后转弱")
        aux_count += 1
    # 威科夫 5m 形态：UT 诱多（突破后跌回）
    ut = detect_upthrust_5m(bars, zone["main_resistance"])
    if ut.get("detected"):
        matched.append(f"威科夫UT({ut['reason']})")
        core_count += 1
    # 威科夫 5m 形态：放量滞涨（量创新高但价未新高）
    vstop = detect_volume_stop_5m(bars)
    if vstop.get("detected"):
        matched.append(f"威科夫放量滞涨({vstop['reason']})")
        core_count += 1
    # Left-side: 1 core + 1 aux → 已触发
    if LEFT_NO_SUPPORT_BLOCK:
        if core_count >= LEFT_TRIGGER_CORE and aux_count >= LEFT_TRIGGER_AUX:
            status = "已触发"
        else:
            status = "观察中"
    elif state.get("weak_trend"):
        base_count = len(matched) - core_count - aux_count
        effective_aux = 0 if (state.get("strong_trend") and state.get("di_uptrend")) else aux_count
        effective_total = core_count + base_count + effective_aux
        status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
    else:
        base_count = len(matched) - core_count - aux_count
        effective_aux = 0 if (state.get("strong_trend") and state.get("di_uptrend")) else aux_count
        effective_total = core_count + base_count + effective_aux
        status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"
    trigger_time = (last.get("time") or last.get("date")) if status == "已触发" else None
    return trigger_result(status, num(last.get("close")) if status == "已触发" else None, matched, [], trigger_time=trigger_time)



def trigger_result(status: str, trigger_price: float | None, matched: list[str], blocked: list[str], trigger_time: Any = None) -> dict[str, Any]:
    total = len(matched) + len(blocked)
    return {
        "status": status if status in STATUSES or status.startswith("买") else "观察中",
        "trigger_price": round_price(trigger_price),
        "trigger_time": str(trigger_time) if trigger_time else "",
        "matched_conditions": matched,
        "blocked_reasons": blocked,
        "matched_count": len(matched),
        "total_conditions": total,
        "confidence": round(len(matched) / total, 2) if total > 0 else 0.0,
    }


def calculate_buy_price_model(report_data: dict[str, Any], zones: dict[str, Any], trigger: dict[str, Any], atr14: float = 0) -> dict[str, Any]:
    zone = zones["buy_zone"]
    observation = zone["upper"]
    invalid = round_price(zone["main_support"] * INVALID_BELOW_SUPPORT)
    if atr14 > 0:
        atr_distance = atr14 * ATR_STOP_FACTOR
        pct_min = float(report_data.get("current_price", 0)) * ATR_STOP_MIN_PCT
        atr_distance = max(atr_distance, pct_min)
        pct_max = float(report_data.get("current_price", 0)) * ATR_STOP_MAX_PCT
        if atr_distance > pct_max:
            atr_distance = pct_max
        atr_invalid = round_price(float(report_data["current_price"]) - atr_distance)
        if atr_invalid is not None and atr_invalid > 0:
            invalid = max(invalid, atr_invalid)
    execution = None
    acceptable = None
    status = trigger["status"]
    trigger_price = trigger.get("trigger_price")
    # 动态滑点：根据量比调整可接受价范围
    volume_ratio = float(report_data.get("volume_ratio") or 1.0)
    if volume_ratio < SLIPPAGE_LOW_VOLUME_RATIO:
        accept_factor = BUY_ACCEPT_FACTOR_CONSERVATIVE  # 低量比→流动性差→放宽滑点
    elif volume_ratio > SLIPPAGE_HIGH_VOLUME_RATIO:
        accept_factor = BUY_ACCEPT_FACTOR_AGGRESSIVE    # 高量比→流动性好→收紧滑点
    else:
        accept_factor = BUY_ACCEPT_FACTOR
    if status == "已触发" and trigger_price is not None:
        execution = round_price(trigger_price * BUY_CONFIRM_FACTOR)
        acceptable = round_price(execution * accept_factor if execution else None)
        if acceptable is not None and float(report_data["current_price"]) > acceptable:
            status = "触发过期"
            execution = None
    return {
        "status": status,
        "zone": zone,
        "observation_price": observation,
        "trigger_price": trigger_price if status != "触发过期" else trigger_price,
        "trigger_time": trigger.get("trigger_time") or "",
        "execution_price": execution,
        "acceptable_price": acceptable,
        "invalid_price": invalid,
        "matched_count": trigger["matched_count"],
        "total_conditions": trigger["total_conditions"],
        "confidence": trigger["confidence"],
        "reasons": trigger["matched_conditions"],
        "blocked_reasons": trigger["blocked_reasons"],
    }


def calculate_sell_price_model(report_data: dict[str, Any], zones: dict[str, Any], trigger: dict[str, Any], atr14: float = 0) -> dict[str, Any]:
    zone = zones["sell_zone"]
    observation = zone["lower"]
    invalid = round_price(zone["main_resistance"] * INVALID_ABOVE_RESISTANCE)
    if atr14 > 0:
        atr_distance = atr14 * ATR_STOP_FACTOR
        pct_min = float(report_data.get("current_price", 0)) * ATR_STOP_MIN_PCT
        atr_distance = max(atr_distance, pct_min)
        pct_max = float(report_data.get("current_price", 0)) * ATR_STOP_MAX_PCT
        if atr_distance > pct_max:
            atr_distance = pct_max
        atr_invalid = round_price(float(report_data["current_price"]) + atr_distance)
        if atr_invalid is not None and atr_invalid > 0:
            invalid = max(invalid, atr_invalid)
    execution = None
    acceptable = None
    status = trigger["status"]
    trigger_price = trigger.get("trigger_price")
    # 动态滑点：根据量比调整可接受价范围
    volume_ratio = float(report_data.get("volume_ratio") or 1.0)
    if volume_ratio < SLIPPAGE_LOW_VOLUME_RATIO:
        accept_factor = SELL_ACCEPT_FACTOR_CONSERVATIVE  # 低量比→流动性差→放宽滑点
    elif volume_ratio > SLIPPAGE_HIGH_VOLUME_RATIO:
        accept_factor = SELL_ACCEPT_FACTOR_AGGRESSIVE    # 高量比→流动性好→收紧滑点
    else:
        accept_factor = SELL_ACCEPT_FACTOR
    if status == "已触发" and trigger_price is not None:
        execution = round_price(trigger_price * SELL_CONFIRM_FACTOR)
        acceptable = round_price(execution * accept_factor if execution else None)
        if acceptable is not None and float(report_data["current_price"]) < acceptable:
            status = "触发过期"
            execution = None
    return {
        "status": status,
        "zone": zone,
        "observation_price": observation,
        "trigger_price": trigger_price,
        "trigger_time": trigger.get("trigger_time") or "",
        "execution_price": execution,
        "acceptable_price": acceptable,
        "invalid_price": invalid,
        "matched_count": trigger["matched_count"],
        "total_conditions": trigger["total_conditions"],
        "confidence": trigger["confidence"],
        "reasons": trigger["matched_conditions"],
        "blocked_reasons": trigger["blocked_reasons"],
    }


def action_for_buy(status: str) -> str:
    return {
        "未进入候选区": "等回落，不急接",
        "观察中": "只观察，不执行",
        "已触发": "可以低吸",
        "触发过期": "错过了，不追",
        "被阻断": "被阻断，不接",
        "数据不足": "只观察，不执行",
    }.get(status, "只观察，不执行")


def action_for_sell(status: str) -> str:
    return {
        "未进入候选区": "等冲高失败，不提前卖",
        "观察中": "只观察，不执行",
        "已触发": "可以高抛",
        "触发过期": "错过了，不砸",
        "被阻断": "被阻断，不卖",
        "数据不足": "只观察，不执行",
    }.get(status, "只观察，不执行")


def choose_today_action(report_data: dict[str, Any], buy: dict[str, Any], sell: dict[str, Any]) -> str:
    if report_data["data_status"] in ("partial", "degraded", "failed"):
        return "等待，不主动操作"
    if "触发过期" in {buy["status"], sell["status"]}:
        return "等待下一次触发"

    # 三重共振灯色：绿灯才给操作建议，黄灯/红灯只观察
    resonance = report_data.get("resonance") or {}
    buy_green = resonance.get("buy_green", False)
    sell_red = resonance.get("sell_red", False)

    # cost_cut 模式：优先高抛（先卖后买降本）
    t_mode = (report_data.get("t0_account") or {}).get("mode", "")
    is_cost_cut = t_mode == "cost_cut"

    if buy["status"] == "已触发" and sell["status"] != "已触发":
        if buy_green:
            return "低吸优先"
        return "等共振确认再低吸"
    if sell["status"] == "已触发" and buy["status"] != "已触发":
        if sell_red:
            return "高抛优先"
        return "等共振确认再高抛"
    if buy["status"] == "已触发" and sell["status"] == "已触发":
        # 双触发：cost_cut 优先高抛，否则按距离选
        if is_cost_cut:
            return "高抛优先（降本模式）"
        current = float(report_data["current_price"])
        buy_mid = (buy["zone"]["lower"] + buy["zone"]["upper"]) / 2
        sell_mid = (sell["zone"]["lower"] + sell["zone"]["upper"]) / 2
        if buy_green and sell_red:
            return "低吸优先" if abs(current - buy_mid) <= abs(current - sell_mid) else "高抛优先"
        return "等共振确认"
    return "等待，不主动操作"


def _atr_volatility_label(atr_ratio: float) -> tuple[str, str]:
    if atr_ratio <= 0:
        return ("数据不足", "")
    if atr_ratio >= 0.03:
        return ("波幅偏高", "波幅偏高→日内仓位压缩到10%上限")
    if atr_ratio >= 0.02:
        return ("波动偏大", "波动偏大→日内仓位从20%压到10%")
    if atr_ratio >= 0.01:
        return ("波动正常", "波动正常→可用20%上限")
    return ("波动较低", "波动较低→可用20%上限")


def position_size(data_status_value: str, action: str, buy: dict[str, Any], sell: dict[str, Any], space_state_value: str, atr_ratio: float = 0.0) -> str:
    if action not in {"低吸优先", "高抛优先"}:
        return "不动"
    model = buy if action == "低吸优先" else sell
    if model["status"] != "已触发":
        return "不动"
    if space_state_value == "too_small":
        return "不动"
    if atr_ratio >= 0.02:
        return "底仓的 10%-20%"
    if data_status_value == "full" and space_state_value == "good" and model["matched_count"] >= STRONG_TRIGGER_MATCHES:
        return "底仓的 20%-30%"
    return "底仓的 10%-20%"


def score_position(report_data: dict[str, Any], key_levels: dict[str, Any]) -> int:
    current = float(report_data["current_price"])
    support = key_levels["main_support"]["price"]
    resistance = key_levels["main_resistance"]["price"]
    span = max(resistance - support, current * 0.01)
    position_score = 10 - min(10, int(abs((current - support) / span - 0.5) * 10))
    return max(1, min(10, position_score))


def score_volume(state: dict[str, Any]) -> int:
    score = 5
    ratio = state.get("volume_ratio")
    if ratio is not None:
        if ratio < VOLUME_SHRINK_RATIO:
            score += 2
        elif ratio > VOLUME_EXPAND_RATIO:
            score -= 1
    if macd_green_shrinking(state) or macd_red_shrinking(state):
        score += 1
    if rsi_turning_up(state) or rsi_turning_down(state):
        score += 1
    return max(1, min(10, score))


# ── 三重硬共振（T0 核心判定）─────────────────────────────────────────────

def check_resonance(report_data: dict[str, Any], zones: dict[str, Any],
                    state: dict[str, Any], ab_result: dict | None = None) -> dict[str, Any]:
    """三重硬共振检查：Al Brooks(5m) + 威科夫(5m) + 动量(5m)，三个同时亮灯才可操作。

    Al Brooks 价格行为替换缠论作为第一席位。
    """
    bars = report_data["kline_5m_completed"]
    current = float(report_data["current_price"])

    # ── 1. Al Brooks 价格行为 ──
    ab_buy = False
    ab_sell = False
    ab_reason = ""
    ab_buy_price = None
    ab_sell_price = None
    if ab_result:
        ab_buy = ab_result.get("buy_signal", False)
        ab_sell = ab_result.get("sell_signal", False)
        ab_reason = ab_result.get("buy_reason", "") if ab_buy else ab_result.get("sell_reason", "")
        ab_buy_price = ab_result.get("buy_price")
        ab_sell_price = ab_result.get("sell_price")

    # ── 2. 威科夫：Spring(买) / UT(卖) / 无供给(买) / 放量滞涨(卖) + 关键价位 ──
    wyckoff_buy = False
    wyckoff_sell = False
    wyckoff_reason = ""
    wyckoff_buy_price = None
    wyckoff_sell_price = None
    buy_zone = zones.get("buy_zone") or {}
    sell_zone = zones.get("sell_zone") or {}
    buy_support = float(buy_zone.get("main_support") or 0)
    sell_resistance = float(sell_zone.get("main_resistance") or 0)

    if buy_support > 0:
        spring = detect_spring_5m(bars, buy_support)
        if spring.get("detected"):
            wyckoff_buy = True
            wyckoff_reason = spring.get("reason", "Spring")
            wyckoff_buy_price = buy_support  # Spring 价位 = 支撑位
        if not wyckoff_buy:
            no_supply = detect_no_supply_pullback_5m(bars, buy_support)
            if no_supply.get("detected"):
                wyckoff_buy = True
                wyckoff_reason = no_supply.get("reason", "无供给")
                wyckoff_buy_price = buy_support

    if sell_resistance > 0:
        ut = detect_upthrust_5m(bars, sell_resistance)
        if ut.get("detected"):
            wyckoff_sell = True
            wyckoff_reason = ut.get("reason", "UT")
            wyckoff_sell_price = sell_resistance  # UT 价位 = 压力位
        if not wyckoff_sell:
            vstop = detect_volume_stop_5m(bars)
            if vstop.get("detected"):
                wyckoff_sell = True
                wyckoff_reason = vstop.get("reason", "放量滞涨")

    # ── 3. 动量：RSI 背离检测 + 入场/出场价 ──
    momentum_buy = False
    momentum_sell = False
    momentum_reason = ""
    momentum_buy_price = None
    momentum_sell_price = None
    momentum_exit_price = None
    rsi_series = state.get("rsi") or []
    rsi_last = rsi_series[-1] if rsi_series else None
    if detect_bullish_divergence(bars, rsi_series, lookback=12):
        momentum_buy = True
        momentum_reason = "RSI底背离"
        # 入场价 = 最近低点（背离确认的支撑位）
        momentum_buy_price = float(bars[-1].get("low", 0)) if bars else None
        # 出场价 = RSI 回到 50 中轴时对应的价格区域（用近期高点估算）
        if len(bars) >= 12:
            recent_highs = [float(b.get("high", 0)) for b in bars[-12:]]
            momentum_exit_price = round(min(recent_highs[-3:]), 2) if recent_highs else None
    if detect_bearish_divergence(bars, rsi_series, lookback=12):
        momentum_sell = True
        momentum_reason = "RSI顶背离"
        momentum_sell_price = float(bars[-1].get("high", 0)) if bars else None
        if len(bars) >= 12:
            recent_lows = [float(b.get("low", 0)) for b in bars[-12:]]
            momentum_exit_price = round(max(recent_lows[-3:]), 2) if recent_lows else None

    # ── 共振判定 ──
    buy_green = ab_buy and wyckoff_buy and momentum_buy
    sell_red = ab_sell and wyckoff_sell and momentum_sell

    # Al Brooks 出场价：信号棒反向极端 或 H2/L2 回调位
    ab_exit_price = None
    if ab_result:
        hl = ab_result.get("hl_count") or {}
        hl_price = hl.get("last_pullback_price")
        if ab_buy and hl_price:
            ab_exit_price = hl_price  # L2 回调低点作为加仓位
        elif ab_sell and hl_price:
            ab_exit_price = hl_price  # H2 回调高点作为减仓位

    # 威科夫出场价：Spring→下一压力位，UT→下一支撑位
    wyckoff_exit_price = None
    if wyckoff_buy and sell_resistance > 0:
        wyckoff_exit_price = sell_resistance  # Spring 目标 = 压力位
    elif wyckoff_sell and buy_support > 0:
        wyckoff_exit_price = buy_support  # UT 目标 = 支撑位

    # 亮灯状态（用于显示，不用于判定）
    lights = {
        "ab": {"buy": ab_buy, "sell": ab_sell, "reason": ab_reason, "ok": bool(ab_result),
               "buy_price": ab_buy_price, "sell_price": ab_sell_price,
               "exit_price": ab_exit_price,
               "quality": ab_result.get("signal_bar_quality", "none") if ab_result else "none",
               "always_in": ab_result.get("always_in", "neutral") if ab_result else "neutral"},
        "wyckoff": {"buy": wyckoff_buy, "sell": wyckoff_sell, "reason": wyckoff_reason, "ok": True,
                    "buy_price": wyckoff_buy_price, "sell_price": wyckoff_sell_price,
                    "exit_price": wyckoff_exit_price},
        "momentum": {"buy": momentum_buy, "sell": momentum_sell, "reason": momentum_reason, "ok": True,
                     "buy_price": momentum_buy_price, "sell_price": momentum_sell_price,
                     "exit_price": momentum_exit_price},
    }

    # 三套理论的参考价位汇总
    buy_prices = [p for p in [ab_buy_price, wyckoff_buy_price, momentum_buy_price] if p and p > 0]
    sell_prices = [p for p in [ab_sell_price, wyckoff_sell_price, momentum_sell_price] if p and p > 0]

    return {
        "buy_green": buy_green,
        "sell_red": sell_red,
        "lights": lights,
        "summary": _resonance_summary(lights, buy_green, sell_red),
        "ref_buy_price": round(min(buy_prices), 2) if buy_prices else None,
        "ref_sell_price": round(max(sell_prices), 2) if sell_prices else None,
    }


def _resonance_summary(lights: dict, buy_green: bool, sell_red: bool) -> str:
    """生成共振状态一行摘要（红黄绿灯）。"""
    if buy_green:
        return "🟢 三重共振买"
    if sell_red:
        return "🟢 三重共振卖"
    buy_count = sum(1 for v in lights.values() if v.get("buy"))
    sell_count = sum(1 for v in lights.values() if v.get("sell"))
    max_count = max(buy_count, sell_count)
    if max_count >= 2:
        return "🟡 部分共振"
    off = []
    for name, info in lights.items():
        label = {"ab": "价格行为", "wyckoff": "威科夫", "momentum": "动量"}[name]
        if not info["buy"] and not info["sell"]:
            off.append(label)
    return f"🔴 未共振（缺：{'、'.join(off)}）"


def build_price_point_model(report_data: dict[str, Any], structure_result: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(report_data)  # copy 防止副作用
    now = data.get("now") or datetime.now()
    completed = completed_5m_bars(data.get("kline_5m") or [], now)
    data["kline_5m_completed"] = completed
    status_value = data_status(data.get("quote") or {}, data.get("daily_bars") or [], completed, now)
    data["data_status"] = status_value
    key_levels = find_key_levels(data, structure_result=structure_result)
    zones = build_candidate_zones(data, key_levels)
    data["amplitude_pct"] = zones.get("amplitude_pct")
    data["space_state"] = zones.get("space_state")
    data["t0_net_space_pct"] = t0_net_space_pct(zones)
    data["sell_net_space_pct"] = sell_net_space_pct(float(data["current_price"]), zones)
    indicator_state = latest_indicator_state(completed)
    ict_signal = (
        build_ict_signal(
            completed,
            sweep_lookback=ICT_SWEEP_LOOKBACK,
            recent_window=ICT_RECENT_WINDOW,
            structure_lookback=ICT_STRUCTURE_LOOKBACK,
        )
        if ENABLE_ICT_EXECUTION
        else {"summary": "ICT执行辅助未启用。", "buy_confirmed": False, "sell_confirmed": False, "signal_grade": "无效"}
    )
    data["ict_signal"] = ict_signal
    daily_bars = data.get("daily_bars") or []
    last_daily = daily_bars[-1] if daily_bars else {}
    atr14_val = float(last_daily.get("atr14") or 0)
    atr_ratio_val = float(last_daily.get("atr_ratio") or 0)
    buy_trigger = detect_buy_trigger(data, zones, indicator_state)
    sell_trigger = detect_sell_trigger(data, zones, indicator_state)
    buy_model = calculate_buy_price_model(data, zones, buy_trigger, atr14_val)
    sell_model = calculate_sell_price_model(data, zones, sell_trigger, atr14_val)
    observation_flags = observation_validity(data, zones)
    buy_model["observation_valid"] = observation_flags["buy_valid"]
    buy_model["observation_reason"] = observation_flags["buy_reason"]
    sell_model["observation_valid"] = observation_flags["sell_valid"]
    sell_model["observation_reason"] = observation_flags["sell_reason"]
    action = choose_today_action(data, buy_model, sell_model)
    max_move = position_size(status_value, action, buy_model, sell_model, str(zones.get("space_state") or "unknown"), atr_ratio_val)
    atr_info: dict[str, Any] = {}
    if atr14_val > 0 and atr_ratio_val > 0:
        level_name, level_advice = _atr_volatility_label(atr_ratio_val)
        atr_info = {"atr14": atr14_val, "atr_ratio": atr_ratio_val, "level": level_name, "level_advice": level_advice}

    # 三重硬共振检查（Al Brooks + 威科夫 + 动量，三亮灯才可操作）
    from trader_shared.ab_price_action import analyze_ab
    ab_result = analyze_ab(
        bars_5m=completed,
        bars_15m=report_data.get("kline_15m") or [],
        current_price=float(data["current_price"]),
    )
    resonance = check_resonance(data, zones, indicator_state, ab_result=ab_result)

    return {
        "data_status": status_value,
        "amplitude_pct": zones.get("amplitude_pct"),
        "space_state": zones.get("space_state"),
        "key_levels": key_levels,
        "zones": zones,
        "buy": buy_model,
        "sell": sell_model,
        "today_action": action,
        "max_move": max_move,
        "position_score": score_position(data, key_levels),
        "volume_score": score_volume(indicator_state),
        "volume_ratio": indicator_state.get("volume_ratio"),
        "vwap": round_price(indicator_state.get("vwap")),
        "ict_signal": ict_signal,
        "atr_info": atr_info,
        "resonance": resonance,
        "ab_result": ab_result,
    }
