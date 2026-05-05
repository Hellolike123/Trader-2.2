from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from config import (
    BUY_ACCEPT_FACTOR,
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
    SELL_CONFIRM_FACTOR,
    STRONG_TRIGGER_MATCHES,
    STRUCTURE_WINDOW,
    VOLUME_EXPAND_RATIO,
    VOLUME_SHRINK_RATIO,
    ZONE_AMPLITUDE_FACTOR,
    ZONE_MAX_WIDTH_PCT,
    ENABLE_ICT_EXECUTION,
    ICT_RECENT_WINDOW,
    ICT_STRUCTURE_LOOKBACK,
    ICT_SWEEP_LOOKBACK,
    ADX_STRONG_THRESHOLD,
    ADX_WEAK_THRESHOLD,
    ATR_STOP_FACTOR,
    ATR_STOP_MAX_PCT,
    ATR_STOP_MIN_PCT,
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


STATUSES = {"已触发", "观察中", "未进入候选区", "被阻断", "数据不足", "触发过期"}
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
        dt = parse_dt(bar.get("time") or bar.get("date"))
        if dt is None:
            completed.append(bar)
            continue
        if dt.date() < now.date():
            completed.append(bar)
        elif dt + timedelta(minutes=5) <= now.replace(second=0, microsecond=0):
            completed.append(bar)
    return completed


def data_status(quote: dict[str, Any], daily: list[dict[str, Any]], bars_5m: list[dict[str, Any]], now: datetime | None = None) -> str:
    now = now or datetime.now()
    if not quote or not daily or len(bars_5m) < MIN_5M_BARS:
        return "insufficient"
    last_dt = parse_dt((bars_5m[-1] or {}).get("time") or (bars_5m[-1] or {}).get("date"))
    if not is_trade_time(now):
        return "non_trading"
    if last_dt is None or last_dt.date() != now.date():
        return "delayed"
    delay_minutes = (now - last_dt).total_seconds() / 60
    return "fresh" if delay_minutes <= 12 else "delayed"


def values(bars: list[dict[str, Any]], key: str) -> list[float]:
    return [float(item[key]) for item in bars if num(item.get(key)) is not None]


def add_level(levels: list[dict[str, Any]], name: str, price_value: float | None, weight: float) -> None:
    rounded = round_price(price_value)
    if rounded is not None and rounded > 0:
        levels.append({"name": name, "price": rounded, "weight": weight})


def find_key_levels(report_data: dict[str, Any]) -> dict[str, Any]:
    quote = report_data["quote"]
    daily = report_data["daily_bars"]
    bars_5m = report_data["kline_5m_completed"]
    bars_15m = report_data.get("kline_15m") or []
    bars_30m = report_data.get("kline_30m") or []
    current = float(report_data["current_price"])
    vwap = calculate_vwap_from_bars(bars_5m)
    recent5 = daily[-5:] if len(daily) >= 5 else daily
    recent20 = daily[-STRUCTURE_WINDOW:] if len(daily) >= STRUCTURE_WINDOW else daily
    support: list[dict[str, Any]] = []
    resistance: list[dict[str, Any]] = []
    add_level(support, "5日低点", min(values(recent5, "low"), default=None), 1.0)
    add_level(resistance, "5日高点", max(values(recent5, "high"), default=None), 1.0)
    add_level(support, "今日低点", num(quote.get("low")), 0.9)
    add_level(resistance, "今日高点", num(quote.get("high")), 0.9)
    add_level(support, "20日低点", min(values(recent20, "low"), default=None), 0.8)
    add_level(resistance, "20日高点", max(values(recent20, "high"), default=None), 0.8)
    add_level(support, "5m低点", min(values(bars_5m[-12:], "low"), default=None), 0.7)
    add_level(resistance, "5m高点", max(values(bars_5m[-12:], "high"), default=None), 0.7)
    add_level(support, "15m低点", min(values(bars_15m[-8:], "low"), default=None), 0.7)
    add_level(resistance, "15m高点", max(values(bars_15m[-8:], "high"), default=None), 0.7)
    add_level(support, "30m低点", min(values(bars_30m[-8:], "low"), default=None), 0.8)
    add_level(resistance, "30m高点", max(values(bars_30m[-8:], "high"), default=None), 0.8)
    add_level(support, "VWAP", vwap, 0.6)
    add_level(resistance, "VWAP上方偏离", vwap * 1.01 if vwap else None, 0.6)
    bb = calculate_bollinger_bands(values(bars_5m, "close"), period=20, num_std=2.0)
    bb_last = bb.get(max(bb.keys(), default=-1), {})
    bb_lower = bb_last.get("lower")
    bb_upper = bb_last.get("upper")
    if bb_lower:
        add_level(support, "布林下轨(20,2σ)", round_price(bb_lower), 0.4)
    if bb_upper:
        add_level(resistance, "布林上轨(20,2σ)", round_price(bb_upper), 0.4)
    if bb_last.get("middle"):
        add_level(support, "布林中轨", round_price(bb_last["middle"]), 0.3)
        add_level(resistance, "布林中轨", round_price(bb_last["middle"]), 0.3)
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
        return sorted(candidates, key=lambda item: (distance(item), -float(item.get("weight") or 0)))[0]

    best_primary = sorted(primary, key=lambda item: (distance(item), -float(item.get("weight") or 0)))[0]
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
        width_pct = min(ZONE_MAX_WIDTH_PCT, amplitude_pct * ZONE_AMPLITUDE_FACTOR)
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
    vwap = calculate_vwap_from_bars(bars)
    prev_vwap = calculate_vwap_from_bars(bars[:-1]) if len(bars) >= 2 else None
    bb = calculate_bollinger_bands(closes, period=20, num_std=2.0)
    bb_last = bb.get(max(bb.keys(), default=-1), {})
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


def macd_green_expanding(state: dict[str, Any]) -> bool:
    if not state.get("macd_ready"):
        return False
    last = state.get("last_hist")
    prev = state.get("prev_hist")
    return last is not None and prev is not None and last < 0 and abs(last) > abs(prev)


def macd_red_shrinking(state: dict[str, Any]) -> bool:
    if not state.get("macd_ready"):
        return False
    last = state.get("last_hist")
    prev = state.get("prev_hist")
    return last is not None and prev is not None and last > 0 and last < prev


def macd_red_expanding(state: dict[str, Any]) -> bool:
    if not state.get("macd_ready"):
        return False
    last = state.get("last_hist")
    prev = state.get("prev_hist")
    return last is not None and prev is not None and last > 0 and last > prev


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
    if data_status_value == "insufficient":
        reason = "盘中数据不足，暂不生成T0观察价"
        return {"buy_valid": False, "sell_valid": False, "buy_reason": reason, "sell_reason": reason}
    if data_status_value == "non_trading":
        reason = "非交易时段，暂不生成T0观察价"
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


def vwap_uptrend(state: dict[str, Any]) -> bool:
    vwap = state.get("vwap")
    prev = state.get("prev_vwap")
    return vwap is not None and prev is not None and float(vwap) > float(prev)


def detect_buy_trigger(report_data: dict[str, Any], zones: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bars = report_data["kline_5m_completed"]
    current = float(report_data["current_price"])
    zone = zones["buy_zone"]
    if report_data["data_status"] in {"insufficient", "non_trading"} or len(bars) < MIN_5M_BARS:
        return trigger_result("数据不足", None, [], ["5m数据不足或非交易时段"])
    if report_data.get("space_state") == "too_small":
        return trigger_result("被阻断", None, [], ["日内振幅不足"])
    net_space = report_data.get("t0_net_space_pct")
    if net_space is not None and net_space < MIN_T_NET_SPACE_PCT:
        return trigger_result("被阻断", None, [], ["T0净空间不足"])
    if current > zone["upper"]:
        return trigger_result("未进入候选区", None, [], [])
    last = bars[-1]
    blocked = []
    if is_new_low_recent(bars):
        blocked.append("最近5m持续创新低")
    if macd_green_expanding(state):
        blocked.append("MACD绿柱继续放大")
    if current < zone["main_support"] and current < (num(last.get("close")) or current):
        blocked.append("跌破主支撑后未收回")
    if (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO and current < zone["main_support"]:
        blocked.append("放量跌破主支撑")
    ict = report_data.get("ict_signal") or {}
    if ict.get("sell_confirmed"):
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
    if ict.get("buy_confirmed"):
        matched.append("ICT下扫后转强")
        aux_count += 1
    base_count = len(matched) - core_count - aux_count
    effective_aux = 0 if (state.get("strong_trend") and state.get("di_downtrend")) else aux_count
    effective_total = core_count + base_count + effective_aux
    if state.get("weak_trend"):
        status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
    else:
        status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"
    trigger_time = (last.get("time") or last.get("date")) if status == "已触发" else None
    return trigger_result(status, num(last.get("close")) if status == "已触发" else None, matched, [], trigger_time=trigger_time)


def detect_sell_trigger(report_data: dict[str, Any], zones: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    bars = report_data["kline_5m_completed"]
    current = float(report_data["current_price"])
    zone = zones["sell_zone"]
    if report_data["data_status"] in {"insufficient", "non_trading"} or len(bars) < MIN_5M_BARS:
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
    last = bars[-1]
    blocked = []
    if is_new_high_recent(bars):
        blocked.append("最近5m持续创新高")
    if macd_red_expanding(state):
        blocked.append("MACD红柱继续放大")
    if (
        state.get("vwap") is not None
        and current > float(state["vwap"])
        and vwap_uptrend(state)
        and (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO
        and current > zone["main_resistance"]
    ):
        blocked.append("VWAP上行且放量突破主压力")
    ict = report_data.get("ict_signal") or {}
    if ict.get("buy_confirmed"):
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
    if ict.get("sell_confirmed"):
        matched.append("ICT上扫后转弱")
        aux_count += 1
    base_count = len(matched) - core_count - aux_count
    effective_aux = 0 if (state.get("strong_trend") and state.get("di_uptrend")) else aux_count
    effective_total = core_count + base_count + effective_aux
    if state.get("weak_trend"):
        status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
    else:
        status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"
    trigger_time = (last.get("time") or last.get("date")) if status == "已触发" else None
    return trigger_result(status, num(last.get("close")) if status == "已触发" else None, matched, [], trigger_time=trigger_time)


def trigger_result(status: str, trigger_price: float | None, matched: list[str], blocked: list[str], trigger_time: Any = None) -> dict[str, Any]:
    return {
        "status": status if status in STATUSES else "观察中",
        "trigger_price": round_price(trigger_price),
        "trigger_time": str(trigger_time) if trigger_time else "",
        "matched_conditions": matched,
        "blocked_reasons": blocked,
        "matched_count": len(matched),
        "total_conditions": 8,
        "confidence": round(len(matched) / 8, 2),
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
    if status == "已触发" and trigger_price is not None:
        execution = round_price(trigger_price * BUY_CONFIRM_FACTOR)
        acceptable = round_price(execution * BUY_ACCEPT_FACTOR if execution else None)
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


def calculate_sell_price_model(report_data: dict[str, Any], zones: dict[str, Any], trigger: dict[str, Any]) -> dict[str, Any]:
    zone = zones["sell_zone"]
    observation = zone["lower"]
    invalid = round_price(zone["main_resistance"] * INVALID_ABOVE_RESISTANCE)
    execution = None
    acceptable = None
    status = trigger["status"]
    trigger_price = trigger.get("trigger_price")
    if status == "已触发" and trigger_price is not None:
        execution = round_price(trigger_price * SELL_CONFIRM_FACTOR)
        acceptable = round_price(execution * SELL_ACCEPT_FACTOR if execution else None)
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
    if report_data["data_status"] in {"non_trading", "insufficient"}:
        return "等待，不主动操作"
    if "触发过期" in {buy["status"], sell["status"]}:
        return "等待下一次触发"
    if buy["status"] == "已触发" and sell["status"] != "已触发":
        return "低吸优先"
    if sell["status"] == "已触发" and buy["status"] != "已触发":
        return "高抛优先"
    if buy["status"] == "已触发" and sell["status"] == "已触发":
        current = float(report_data["current_price"])
        buy_mid = (buy["zone"]["lower"] + buy["zone"]["upper"]) / 2
        sell_mid = (sell["zone"]["lower"] + sell["zone"]["upper"]) / 2
        return "低吸优先" if abs(current - buy_mid) <= abs(current - sell_mid) else "高抛优先"
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
    if data_status_value == "fresh" and space_state_value == "good" and model["matched_count"] >= STRONG_TRIGGER_MATCHES:
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


def build_price_point_model(report_data: dict[str, Any]) -> dict[str, Any]:
    now = report_data.get("now") or datetime.now()
    completed = completed_5m_bars(report_data.get("kline_5m") or [], now)
    report_data["kline_5m_completed"] = completed
    status_value = data_status(report_data.get("quote") or {}, report_data.get("daily_bars") or [], completed, now)
    report_data["data_status"] = status_value
    key_levels = find_key_levels(report_data)
    zones = build_candidate_zones(report_data, key_levels)
    report_data["amplitude_pct"] = zones.get("amplitude_pct")
    report_data["space_state"] = zones.get("space_state")
    report_data["t0_net_space_pct"] = t0_net_space_pct(zones)
    report_data["sell_net_space_pct"] = sell_net_space_pct(float(report_data["current_price"]), zones)
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
    report_data["ict_signal"] = ict_signal
    daily_bars = report_data.get("daily_bars") or []
    last_daily = daily_bars[-1] if daily_bars else {}
    atr14_val = float(last_daily.get("atr14") or 0)
    atr_ratio_val = float(last_daily.get("atr_ratio") or 0)
    buy_trigger = detect_buy_trigger(report_data, zones, indicator_state)
    sell_trigger = detect_sell_trigger(report_data, zones, indicator_state)
    buy_model = calculate_buy_price_model(report_data, zones, buy_trigger, atr14_val)
    sell_model = calculate_sell_price_model(report_data, zones, sell_trigger)
    observation_flags = observation_validity(report_data, zones)
    buy_model["observation_valid"] = observation_flags["buy_valid"]
    buy_model["observation_reason"] = observation_flags["buy_reason"]
    sell_model["observation_valid"] = observation_flags["sell_valid"]
    sell_model["observation_reason"] = observation_flags["sell_reason"]
    action = choose_today_action(report_data, buy_model, sell_model)
    max_move = position_size(status_value, action, buy_model, sell_model, str(zones.get("space_state") or "unknown"), atr_ratio_val)
    atr_info: dict[str, Any] = {}
    if atr14_val > 0 and atr_ratio_val > 0:
        level_name, level_advice = _atr_volatility_label(atr_ratio_val)
        atr_info = {"atr14": atr14_val, "atr_ratio": atr_ratio_val, "level": level_name, "level_advice": level_advice}
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
        "position_score": score_position(report_data, key_levels),
        "volume_score": score_volume(indicator_state),
        "volume_ratio": indicator_state.get("volume_ratio"),
        "vwap": round_price(indicator_state.get("vwap")),
        "ict_signal": ict_signal,
        "atr_info": atr_info,
    }
