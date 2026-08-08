from __future__ import annotations
"""T0 价位/触发引擎（自 t0/scripts/price_point_engine 迁入）。"""

from datetime import datetime, time, timedelta
from typing import Any

from trader_shared.safe_cast import safe_max
from trader_shared.t0_config import (
    ACCUM_PHASES,
    BREAKOUT_VOL_RATIO,
    BUY_ACCEPT_FACTOR,
    BUY_ACCEPT_FACTOR_AGGRESSIVE,
    BUY_ACCEPT_FACTOR_CONSERVATIVE,
    BUY_CONFIRM_FACTOR,
    DEFAULT_ZONE_WIDTH_PCT,
    DIST_PHASES,
    FAKE_BREAK_NEAR_PCT,
    INVALID_ABOVE_RESISTANCE,
    INVALID_BELOW_SUPPORT,
    GOOD_T_AMPLITUDE_PCT,
    KEY_SIGNAL_STRONG_QUALITY,
    AB_SIGNAL_SCORE_MIN,
    MIN_5M_BARS,
    MACD_WARMUP_BARS,
    MIN_T_AMPLITUDE_PCT,
    MIN_TRIGGER_MATCHES,
    MIN_T_NET_SPACE_PCT,
    MIN_SELL_NET_SPACE_PCT,
    OPEN_RECLAIM_EPS_PCT,
    OPEN_RECLAIM_MIN_BARS,
    PRICE_TICK,
    SELL_ACCEPT_FACTOR,
    SELL_ACCEPT_FACTOR_AGGRESSIVE,
    SELL_ACCEPT_FACTOR_CONSERVATIVE,
    SELL_CONFIRM_FACTOR,
    SLIPPAGE_HIGH_VOLUME_RATIO,
    SLIPPAGE_LOW_VOLUME_RATIO,
    STRONG_TRIGGER_MATCHES,
    STRUCTURE_WINDOW,
    TREND_FILTER_DAYS,
    TREND_FILTER_ENABLED,
    TREND_FILTER_EXTREME_DROP_PCT,
    TREND_FILTER_EXTREME_ONLY,
    VWAP_REGRESSION_DEV_PCT,
    VWAP_REGRESSION_VOL_RATIO,
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
from trader_shared.t0_ict_execution import build_ict_signal
from trader_shared.t0_indicators import (
    calculate_adx,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_rsi,
    calculate_volume_ratio,
    calculate_vwap_from_bars,
    detect_lower_shadow,
    detect_upper_shadow,
    is_new_high_recent,
    is_new_low_recent,
)


STATUSES = {
    "已触发",
    "观察中",
    "未进入候选区",
    "被阻断",
    "数据不足",
    "触发过期",
    "熔断中",
    "数据异常",
    "趋势下行暂不低吸",
    "趋势下行暂不高抛",
}
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


def completed_bars(
    bars: list[dict[str, Any]],
    bar_minutes: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """只保留已收盘完成的分钟棒（防未收盘 OHLC 污染结构/区间套）。

    bar 时间戳视为该棒起点；起点 + bar_minutes <= now 才算完成。
    """
    if not bars:
        return []
    minutes = max(int(bar_minutes or 0), 1)
    if now is None:
        try:
            from trader_shared.cn_time import now_cn
            now = now_cn()
        except Exception:
            now = datetime.now()
    cutoff = now.replace(second=0, microsecond=0)
    completed: list[dict[str, Any]] = []
    for bar in bars:
        if bar is None:
            continue
        dt = parse_dt(bar.get("time") or bar.get("date"))
        if dt is None:
            # 无时间戳的棒不可判定是否收盘完成，丢弃（与 today_bars 一致，防前视）
            continue
        if dt.date() < now.date():
            completed.append(bar)
        elif dt + timedelta(minutes=minutes) <= cutoff:
            completed.append(bar)
    return completed


def completed_5m_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    return completed_bars(bars, 5, now)


def completed_15m_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    return completed_bars(bars, 15, now)


def completed_30m_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    return completed_bars(bars, 30, now)


def today_bars(bars: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """只保留最新 session 的 5m bar（与 trader display_indicators.session_5m_bars 同源）。

    - 用 bars 内可解析交易日的 max，而非墙钟日历（避免盘后/周一脏混）
    - 无日期 bar 丢弃（禁止误入「今日」）
    """
    if not bars:
        return []
    try:
        from trader_shared.display_indicators import session_5m_bars
        return session_5m_bars([b for b in bars if b is not None])
    except ImportError:
        # 降级：可解析日期中的最新日
        days: list[str] = []
        parsed: list[tuple[str, dict]] = []
        for bar in bars:
            if bar is None:
                continue
            dt = parse_dt(bar.get("time") or bar.get("date"))
            if dt is None:
                continue
            d = dt.strftime("%Y-%m-%d")
            days.append(d)
            parsed.append((d, bar))
        if not days:
            return []
        latest = max(days)
        return [b for d, b in parsed if d == latest]


def data_status(quote: dict[str, Any], daily: list[dict[str, Any]], bars_5m: list[dict[str, Any]], now: datetime | None = None) -> str:
    if now is None:
        try:
            from trader_shared.cn_time import now_cn
            now = now_cn()
        except Exception:
            now = datetime.now()
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
    # 15m/30m 与 5m 同口径：只用已收盘棒，避免未完成 OHLC 抬拉 S/R
    if "kline_15m_completed" in report_data:
        bars_15m = report_data.get("kline_15m_completed") or []
    else:
        bars_15m = completed_15m_bars(report_data.get("kline_15m") or [])
    if "kline_30m_completed" in report_data:
        bars_30m = report_data.get("kline_30m_completed") or []
    else:
        bars_30m = completed_30m_bars(report_data.get("kline_30m") or [])
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


# ── 关键位信号（handoff §2：关键位 + 量价，单信号即出手）──────────────────

def daily_direction_from_phase(phase: str | None) -> str | None:
    """日线威科夫 phase → T0 方向：bullish / bearish / None（无明确阶段）。

    词表与 t0_config.ACCUM_PHASES / DIST_PHASES 对齐（handoff §1）。
    """
    p = str(phase or "").strip().lower()
    if not p or p in {"none", "unknown", "无明确阶段"}:
        return None
    if p in ACCUM_PHASES:
        return "bullish"
    if p in DIST_PHASES:
        return "bearish"
    return None


def vwap_regression_signal(
    bars: list[dict[str, Any]], state: dict[str, Any], current: float, side: str, direction: str | None
) -> dict[str, Any] | None:
    """VWAP 回归（handoff §2.1）：价格偏离均价线 >1.5% + 缩量 → 做回归。

    - side=buy：价格在 VWAP 下方深偏离 → 低吸回归；要求非日线派发
    - side=sell：价格在 VWAP 上方深偏离 → 高抛回归；要求非日线积累
    - 只认「首次进入偏离区」：前一棒收盘未深偏离，本棒才触发，
      避免持续偏离时每根 5m 都重复触发（单信号即出手，非每棒追）。
    """
    vwap = state.get("vwap")
    if vwap is None or current is None or current <= 0:
        return None
    vwap = float(vwap)
    if vwap <= 0:
        return None
    dev = (current - vwap) / vwap
    vol_ratio = state.get("volume_ratio") or 1.0
    today = today_bars(bars)
    prev_close = num(today[-2].get("close")) if len(today) >= 2 else None
    if side == "buy":
        if direction == "bearish":
            return None
        if dev <= -VWAP_REGRESSION_DEV_PCT and vol_ratio < VWAP_REGRESSION_VOL_RATIO:
            # 首次进入：前一棒收盘未深偏离（或数据不足时放行）
            if prev_close is None or (prev_close - vwap) / vwap > -VWAP_REGRESSION_DEV_PCT:
                return {"reason": f"VWAP回归：价低于均价线{vwap:.2f}达{abs(dev)*100:.1f}%且缩量(量比{vol_ratio:.1f})"}
    else:
        if direction == "bullish":
            return None
        if dev >= VWAP_REGRESSION_DEV_PCT and vol_ratio < VWAP_REGRESSION_VOL_RATIO:
            if prev_close is None or (prev_close - vwap) / vwap < VWAP_REGRESSION_DEV_PCT:
                return {"reason": f"VWAP回归：价高于均价线{vwap:.2f}达{dev*100:.1f}%且缩量(量比{vol_ratio:.1f})"}
    return None


def intraday_breakout_signal(
    bars: list[dict[str, Any]], state: dict[str, Any], current: float, side: str, direction: str | None
) -> dict[str, Any] | None:
    """前高/前低突破（handoff §2.2）。

    - 放量突破日内前高 + 顺日线 → 跟突破（buy）；对称：放量跌破前低 + 顺日线 → 跟跌破（sell）
    - 缩量到前高 + 逆日线（日线派发）→ 假突破反向高抛；对称：缩量到前低 + 逆日线（日线积累）→ 假突破反向低吸
    """
    today = today_bars(bars)
    if len(today) < 3:
        return None
    prev = today[:-1]
    highs = [num(b.get("high")) for b in prev if num(b.get("high")) is not None]
    lows = [num(b.get("low")) for b in prev if num(b.get("low")) is not None]
    if not highs or not lows:
        return None
    prev_high = max(highs)
    prev_low = min(lows)
    vol_ratio = state.get("volume_ratio") or 1.0
    expanding = vol_ratio >= BREAKOUT_VOL_RATIO
    shrinking = vol_ratio < VOLUME_SHRINK_RATIO
    if side == "buy":
        # 放量突破前高 + 非派发日线 → 跟突破
        if expanding and current > prev_high and direction != "bearish":
            return {"reason": f"放量突破日内前高{prev_high:.2f}(量比{vol_ratio:.1f})"}
        # 缩量到前低 + 日线积累 → 假突破反向低吸
        if shrinking and current <= prev_low * (1 + FAKE_BREAK_NEAR_PCT) and direction == "bullish":
            return {"reason": f"缩量回探前低{prev_low:.2f}(量比{vol_ratio:.1f})·日线积累假突破低吸"}
    else:
        # 放量跌破前低 + 非积累日线 → 跟跌破
        if expanding and current < prev_low and direction != "bullish":
            return {"reason": f"放量跌破日内前低{prev_low:.2f}(量比{vol_ratio:.1f})"}
        # 缩量到前高 + 日线派发 → 假突破反向高抛
        if shrinking and current >= prev_high * (1 - FAKE_BREAK_NEAR_PCT) and direction == "bearish":
            return {"reason": f"缩量冲前高{prev_high:.2f}(量比{vol_ratio:.1f})·日线派发假突破高抛"}
    return None


def open_price_reclaim_signal(
    bars: list[dict[str, Any]], state: dict[str, Any], current: float, side: str, direction: str | None
) -> dict[str, Any] | None:
    """开盘价失守/收复（handoff §2.3）：开盘 30 分钟后，
    站稳开盘价上方(顺多)→低吸；下方(顺空)→高抛。

    只认「刚穿越」：当前棒站稳开盘价同侧、且前一棒收盘还在另一侧
    （或紧贴开盘价），避免整日持续高于/低于开盘价造成每根都触发。
    """
    today = today_bars(bars)
    if len(today) < OPEN_RECLAIM_MIN_BARS + 1:
        return None
    open_px = num(today[0].get("open"))
    if open_px is None or open_px <= 0:
        return None
    eps = open_px * OPEN_RECLAIM_EPS_PCT
    prev_close = num(today[-2].get("close"))
    if prev_close is None:
        return None
    if side == "buy":
        if direction == "bearish":
            return None
        # 刚收复：前一棒收盘 ≤ 开盘价，本棒站稳开盘价上方
        if prev_close <= open_px and current > open_px + eps:
            return {"reason": f"开盘价{open_px:.2f}刚收复并站稳(顺日线低吸)"}
    else:
        if direction == "bullish":
            return None
        # 刚失守：前一棒收盘 ≥ 开盘价，本棒跌破开盘价下方
        if prev_close >= open_px and current < open_px - eps:
            return {"reason": f"开盘价{open_px:.2f}刚失守(顺日线高抛)"}
    return None


def ab_signal_bar_signal(
    ab_result: dict[str, Any] | None, side: str, direction: str | None
) -> dict[str, Any] | None:
    """Al Brooks 信号棒（handoff §2.4）：高质量信号棒 + 顺日线即出手。

    只认「信号棒驱动」的信号（analyze_ab 里 buy_reason 以“信号棒”开头）；
    Always-In 回调计数补充信号不算高质量信号棒，不进入关键位快速通道。
    另要求信号棒 score>=0.8（strong 里更强的一档），避免 5m 单根 strong 棒过密。
    """
    if not ab_result:
        return None
    quality = str(ab_result.get("signal_bar_quality") or "none")
    if KEY_SIGNAL_STRONG_QUALITY and quality != "strong":
        return None
    details = ab_result.get("details") or {}
    sig = details.get("signal_bar") or {}
    try:
        score = float(sig.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score < AB_SIGNAL_SCORE_MIN:
        return None
    if side == "buy":
        reason = str(ab_result.get("buy_reason") or "")
        if ab_result.get("buy_signal") and reason.startswith("信号棒") and direction != "bearish":
            return {"reason": f"AB信号棒({quality}·score{score:.1f})·{reason}"}
    else:
        reason = str(ab_result.get("sell_reason") or "")
        if ab_result.get("sell_signal") and reason.startswith("信号棒") and direction != "bullish":
            return {"reason": f"AB信号棒({quality}·score{score:.1f})·{reason}"}
    return None


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
    # 数据合法性守卫：买区主支撑高于卖区主压力（区间倒置），说明 VWAP/区间被跨日旧数据污染，
    # 应报"数据异常"而非伪装成"净空间不足"
    _buy_ms = (zones.get("buy_zone") or {}).get("main_support")
    _sell_mr = (zones.get("sell_zone") or {}).get("main_resistance")
    if _buy_ms is not None and _sell_mr is not None and _buy_ms >= _sell_mr:
        return trigger_result("数据异常", None, [], ["买区高于卖区，VWAP/区间疑似跨日污染"])
    # handoff §2：关键位信号（VWAP回归/前低突破/开盘价收复/AB信号棒），
    # 任一命中 + 顺日线方向（非派发）即出手——单信号不要求多条件共振，
    # 不受净空间/候选区/趋势/blocked 等旧闸限制（数据/振幅硬闸在上方已守）。
    direction = daily_direction_from_phase(report_data.get("daily_phase"))
    key_hits = [
        vwap_regression_signal(bars, state, current, "buy", direction),
        intraday_breakout_signal(bars, state, current, "buy", direction),
        open_price_reclaim_signal(bars, state, current, "buy", direction),
        ab_signal_bar_signal(report_data.get("ab_result"), "buy", direction),
    ]
    key_hits = [hit for hit in key_hits if hit]
    if key_hits:
        last = bars[-1]
        reasons = [hit["reason"] for hit in key_hits]
        trigger_time = last.get("time") or last.get("date")
        return trigger_result("已触发", num(last.get("close")), reasons, [], trigger_time=trigger_time)
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
    # handoff §2：扔掉 RSI 12 棒背离（错位信号）——不再检测
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
    # 数据合法性守卫：买区主支撑高于卖区主压力（区间倒置），说明 VWAP/区间被跨日旧数据污染，
    # 应报"数据异常"而非伪装成"净空间不足"
    _buy_ms = (zones.get("buy_zone") or {}).get("main_support")
    _sell_mr = (zones.get("sell_zone") or {}).get("main_resistance")
    if _buy_ms is not None and _sell_mr is not None and _buy_ms >= _sell_mr:
        return trigger_result("数据异常", None, [], ["买区高于卖区，VWAP/区间疑似跨日污染"])
    # handoff §2：关键位信号（VWAP回归/前高假突破/开盘价失守/AB信号棒），
    # 任一命中 + 顺日线方向（非积累）即出手——单信号不要求多条件共振，
    # 不受净空间/候选区/趋势/blocked 等旧闸限制（数据/振幅硬闸在上方已守）。
    direction = daily_direction_from_phase(report_data.get("daily_phase"))
    key_hits = [
        vwap_regression_signal(bars, state, current, "sell", direction),
        intraday_breakout_signal(bars, state, current, "sell", direction),
        open_price_reclaim_signal(bars, state, current, "sell", direction),
        ab_signal_bar_signal(report_data.get("ab_result"), "sell", direction),
    ]
    key_hits = [hit for hit in key_hits if hit]
    if key_hits:
        last = bars[-1]
        reasons = [hit["reason"] for hit in key_hits]
        trigger_time = last.get("time") or last.get("date")
        return trigger_result("已触发", num(last.get("close")), reasons, [], trigger_time=trigger_time)
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
    # handoff §2：扔掉 RSI 12 棒背离（错位信号）——不再检测
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
        # 高抛失效是天花板：取「阻力失效位」与「现价+ATR」的更紧（更低）一侧
        atr_invalid = round_price(float(report_data["current_price"]) + atr_distance)
        if atr_invalid is not None and atr_invalid > 0:
            if invalid is not None and invalid > 0:
                invalid = min(invalid, atr_invalid)
            else:
                invalid = atr_invalid
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

    # v2：today_action 只描述结构，不因 buy_green 下达交易指令
    if buy["status"] == "已触发" and sell["status"] != "已触发":
        return "价近低吸关注区 · 人决策"
    if sell["status"] == "已触发" and buy["status"] != "已触发":
        return "价近高抛关注区 · 人决策"
    if buy["status"] == "已触发" and sell["status"] == "已触发":
        return "双侧关注区皆近 · 人决策"
    return "等待，结构观察 · 人决策"


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
    # v2 today_action 为人读结构文案；同时兼容旧枚举
    _buy_actions = {"低吸优先", "价近低吸关注区 · 人决策"}
    _sell_actions = {"高抛优先", "价近高抛关注区 · 人决策"}
    if action in _buy_actions:
        model = buy
    elif action in _sell_actions:
        model = sell
    else:
        return "不动"
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

def check_resonance(report_data, zones, state, ab_result=None):
    """T0 评分系统（V1.0）：五条件各20分，总分100。

    条件1: EMA5 > EMA10 > EMA20         20分 多头趋势
    条件2: Close > VWAP                  20分 高于主力成本
    条件3: Close near Box Low            20分 靠近箱体底部
    条件4: Volume > MA5 * 1.5            20分 放量确认
    条件5: ATR / Close > 2%              20分 波动足够

    买入: >= 60分
    卖出: EMA5死叉EMA10 或 Close<VWAP 或 接近箱体顶
    """
    from trader_shared.t0_indicators import calculate_vwap_from_bars, calculate_ema

    bars = report_data.get("kline_5m_completed") or report_data.get("kline_5m") or []
    current = float(report_data["current_price"])
    closes = [float(b.get("close", 0)) for b in bars if b.get("close")]
    volumes = [float(b.get("volume", 0)) for b in bars if b.get("volume")]
    n = len(closes)

    # 条件1: EMA 排列
    score_ema = 0
    ema_reason = "EMA数据不足"
    e5 = e10 = e20 = 0.0
    if n >= 20:
        ema5 = calculate_ema(closes, 5)
        ema10 = calculate_ema(closes, 10)
        ema20 = calculate_ema(closes, 20)
        e5 = ema5[-1] if ema5 else 0
        e10 = ema10[-1] if ema10 else 0
        e20 = ema20[-1] if ema20 else 0
        e5_p = ema5[-2] if len(ema5) >= 2 else e5
        e10_p = ema10[-2] if len(ema10) >= 2 else e10
        if e5 > e10 > e20:
            score_ema = 20
            ema_reason = f"EMA5>{e5:.2f}>EMA10>{e10:.2f}>EMA20 多头"
        elif e5 < e10 < e20:
            ema_reason = f"EMA5<EMA10<EMA20 空头"
        else:
            ema_reason = "EMA排列不整"
        # 死叉检测（用于卖出）
        ema_death_cross = e5_p > e10_p and e5 <= e10
    else:
        ema_death_cross = False

    # 条件2: VWAP — 必须与结构区同源：仅今日 session（禁止跨日把 VWAP 拉飞）
    session = today_bars(bars)
    vwap = calculate_vwap_from_bars(session) if session else calculate_vwap_from_bars(bars)
    score_vwap = 20 if vwap and current > vwap else 0
    if vwap:
        side = "上方" if current > vwap else ("下方" if current < vwap else "附近")
        vwap_reason = f"今日VWAP{vwap:.2f}{side}"
    else:
        vwap_reason = "VWAP无数据"

    # 条件3: 箱体（最近20根5m的高低）
    box_reason = "箱体数据不足"
    score_box = 0
    box_high = box_low = 0
    if n >= 20:
        recent = bars[-20:]
        box_high = max(float(b.get("high", 0)) for b in recent if b.get("high"))
        box_low = min(float(b.get("low", 0)) for b in recent if b.get("low"))
        # ATR：真 TR 序列（indicator_math），用完整 5m bars，不用收盘差近似
        atr = _latest_atr(bars, period=14)
        dist_to_low = (current - box_low) / box_low if box_low > 0 else 1
        dist_to_high = (box_high - current) / box_high if box_high > 0 else 1
        if dist_to_low <= (atr / box_low * 0.8) if atr and box_low else False:
            score_box = 20
            box_reason = f"箱底{box_low:.2f} 距{dist_to_low*100:.1f}%"
        elif dist_to_high <= (atr / box_high * 0.8) if atr and box_high else False:
            box_reason = f"箱顶{box_high:.2f} 距{dist_to_high*100:.1f}%"
        else:
            box_reason = f"箱体{box_low:.2f}-{box_high:.2f}"
    else:
        atr = 0.0

    # 条件4: 成交量
    score_vol = 0
    vol_reason = "量数据不足"
    if len(volumes) >= 5:
        vol_ma5 = sum(volumes[-5:]) / 5
        last_vol = volumes[-1] if volumes else 0
        vol_ratio = last_vol / vol_ma5 if vol_ma5 > 0 else 1
        if last_vol > vol_ma5 * 1.5:
            score_vol = 20
            vol_reason = f"放量{vol_ratio:.1f}x"
        else:
            vol_reason = f"量{vol_ratio:.1f}x"

    # 条件5: ATR 波动（5m 上 >2% 很严，常不达标，文案标明门槛）
    score_atr = 0
    atr_reason = "ATR数据不足"
    if atr > 0 and current > 0:
        atr_pct = atr / current * 100
        if atr_pct > 2:
            score_atr = 20
            atr_reason = f"ATR{atr_pct:.1f}%够"
        else:
            atr_reason = f"ATR{atr_pct:.1f}%<2%门槛(5m常不达标)"

    # 总分（偏多五条件）
    buy_score = score_ema + score_vwap + score_box + score_vol + score_atr
    buy_green = buy_score >= 40

    # 偏空检查分（内部统计用；展示层不当「卖出指令」）
    sell_ema = 20 if (n >= 20 and e5 < e10) else 0
    sell_vwap = 20 if vwap and current < vwap else 0
    if n >= 20 and atr and box_high > 0:
        dist_to_high_s = (box_high - current) / box_high
        sell_box = 20 if dist_to_high_s <= (atr / box_high * 0.8) else 0
    else:
        sell_box = 0
    # 量/ATR 不重复计入偏空分（避免与偏多分混读）；只计方向性三项
    sell_score = sell_ema + sell_vwap + sell_box
    sell_red = sell_score >= 40

    # handoff §2：日内出手 = 关键位单信号（任一命中 + 顺日线方向）。
    # buy_green/sell_red 直接复用 detect_buy/sell_trigger 状态机（含数据/空间硬闸），
    # 保证回测撮合与盯盘/报告单一事实源；五条件评分降为仪表
    # （法源 v2 §4.3 / handoff §9：威科夫/动量降为背景参考，不驱动出手）。
    if str(report_data.get("space_state") or "") != "too_small":
        buy_green = detect_buy_trigger(report_data, zones, state).get("status") == "已触发"
        sell_red = detect_sell_trigger(report_data, zones, state).get("status") == "已触发"
    else:
        buy_green = sell_red = False

    lights = {
        "ema": {
            "buy": score_ema >= 20, "sell": sell_ema >= 20,
            "reason": ema_reason, "ok": n >= 20,
        },
        "vwap": {
            "buy": score_vwap >= 20, "sell": sell_vwap >= 20,
            "reason": vwap_reason, "ok": vwap is not None,
            "buy_price": round(vwap, 2) if vwap else None,
            "sell_price": round(vwap, 2) if vwap else None,
        },
        "box": {
            "buy": score_box >= 20, "sell": sell_box >= 20,
            "reason": box_reason, "ok": n >= 20,
        },
        "volume": {
            "buy": score_vol >= 20, "sell": False,  # 量能只作偏多确认，不标「空」
            "reason": vol_reason, "ok": len(volumes) >= 5,
        },
        "atr": {
            "buy": score_atr >= 20, "sell": False,
            "reason": atr_reason, "ok": atr > 0,
        },
    }
    # buy_green/sell_red 仅供结构偏强偏弱标签，不驱动「可交易」叙事（v2）
    if buy_score >= 60:
        summary = f"评分{buy_score}/100 · 结构偏强（参考）"
    elif buy_score >= 40:
        summary = f"评分{buy_score}/100 · 结构中性偏上（参考）"
    else:
        summary = f"评分{buy_score}/100 · 结构偏弱（参考）"
    return {
        "buy_green": buy_green, "sell_red": sell_red,
        "score": buy_score, "sell_score": sell_score,
        "lights": lights, "summary": summary,
        "ref_buy_price": round(box_low, 2) if box_low > 0 else None,
        "ref_sell_price": round(box_high, 2) if box_high > 0 else None,
    }


def _latest_atr(bars: list[dict], period: int = 14) -> float:
    """取 bars 上 calc_atr_series 最后一个有效 ATR；不足则 0。

    SMA(TR, period) 在恰好 period 根时已有首值（index=period-1）；勿误卡 period+1。
    """
    if not bars or period <= 0 or len(bars) < period:
        return 0.0
    from trader_shared.indicator_math import calc_atr_series

    series = calc_atr_series(bars, period=period)
    for value in reversed(series):
        if value is not None and value > 0:
            return float(value)
    return 0.0


def _resonance_summary(lights, buy_green, sell_red):
    if buy_green:
        return "结构偏强（参考）"
    if sell_red:
        return "结构偏弱/卖侧偏强（参考）"
    return "结构中性（参考）"
def build_price_point_model(report_data: dict[str, Any], structure_result: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(report_data)  # copy 防止副作用
    if data.get("now") is not None:
        now = data["now"]
    else:
        try:
            from trader_shared.cn_time import now_cn
            now = now_cn()
        except Exception:
            now = datetime.now()
    completed = completed_5m_bars(data.get("kline_5m") or [], now)
    data["kline_5m_completed"] = completed
    data["kline_15m_completed"] = completed_15m_bars(data.get("kline_15m") or [], now)
    data["kline_30m_completed"] = completed_30m_bars(data.get("kline_30m") or [], now)
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
    # 展示/仓位用日线 ATR14；单笔止损用日内 5m ATR（handoff §5）
    atr14_val = float(last_daily.get("atr14") or 0)
    atr_ratio_val = float(last_daily.get("atr_ratio") or 0)
    intraday_atr = _latest_atr(completed, period=14)
    # handoff §2：AB 信号棒提前算（信号引擎用 ab_result 做单一结构信号）
    from trader_shared.ab_price_action import analyze_ab
    ab_result = analyze_ab(
        bars_5m=completed,
        bars_15m=report_data.get("kline_15m") or [],
        current_price=float(data["current_price"]),
    )
    data["ab_result"] = ab_result
    buy_trigger = detect_buy_trigger(data, zones, indicator_state)
    sell_trigger = detect_sell_trigger(data, zones, indicator_state)
    buy_model = calculate_buy_price_model(data, zones, buy_trigger, intraday_atr)
    sell_model = calculate_sell_price_model(data, zones, sell_trigger, intraday_atr)
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
