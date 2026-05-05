from __future__ import annotations

from datetime import datetime
from typing import Any

from candidate_core import atr_volatility_level
from light_data import to_float
from trader_shared.data_provider import get_provider


def pct_text(value: float | None) -> str:
    return "--" if value is None else f"{value:+.2f}%"


def price_text(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"


def volume_wan_hands(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value / 10000:.1f}万手"


def volume_wan_shares(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value / 10000:.1f}万股"


def bar_time(bar: dict[str, Any]) -> str:
    text = str(bar.get("time") or bar.get("date") or "")
    if " " in text:
        return text.split(" ", 1)[1][:5]
    if len(text) >= 16 and text[10] in {" ", "T"}:
        return text[11:16]
    return text[-8:-3] if ":" in text else ""


def bar_date(bar: dict[str, Any]) -> str:
    text = str(bar.get("time") or bar.get("date") or "")
    return text.split(" ", 1)[0] if " " in text else text[:10]


def filter_trade_date(bars: list[dict[str, Any]], trade_date: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    if not bars:
        return trade_date, []
    dates = [bar_date(bar) for bar in bars if bar_date(bar)]
    selected_date = trade_date or (dates[-1] if dates else None)
    if not selected_date:
        return None, bars
    filtered = [bar for bar in bars if bar_date(bar) == selected_date]
    return selected_date, filtered or bars


def in_range(time_text: str, start: str, end: str) -> bool:
    return bool(time_text) and start <= time_text <= end


def max_bar_time(bars: list[dict[str, Any]]) -> str:
    times = [bar_time(bar) for bar in bars if bar_time(bar)]
    return max(times) if times else ""


def numeric_values(items: list[dict[str, Any]], key: str) -> list[float]:
    return [value for value in (to_float(item.get(key)) for item in items) if value is not None]


def sum_volume(bars: list[dict[str, Any]]) -> float:
    return sum(numeric_values(bars, "volume"))


def average_volume(bars: list[dict[str, Any]]) -> float:
    volumes = numeric_values(bars, "volume")
    return sum(volumes) / len(volumes) if volumes else 0.0


def pct_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return (end / start - 1.0) * 100


def latest_or_quote_close(quote: dict[str, Any], daily: list[dict[str, Any]]) -> float:
    current = to_float(quote.get("current_price"))
    if current is not None:
        return current
    close = to_float(daily[-1].get("close")) if daily else None
    if close is None:
        raise RuntimeError("close price unavailable")
    return close


def moving_average(daily: list[dict[str, Any]], period: int) -> float | None:
    closes = [to_float(item.get("close")) for item in daily]
    values = [value for value in closes if value is not None]
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def dense_price_zone(daily: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    recent = daily[-20:] if len(daily) >= 20 else daily
    typical: list[tuple[float, float]] = []
    for item in recent:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        volume = to_float(item.get("volume")) or 0
        if high is None or low is None or close is None:
            continue
        typical.append(((high + low + close) / 3, volume))
    if not typical:
        return None, None
    weighted = [(price, volume) for price, volume in typical if volume > 0]
    if weighted:
        total_volume = sum(volume for _, volume in weighted)
        center = sum(price * volume for price, volume in weighted) / total_volume
    else:
        center = sum(price for price, _ in typical) / len(typical)
    prices = [price for price, _ in typical]
    spread = max((max(prices) - min(prices)) * 0.18, center * 0.01)
    return round(center - spread, 2), round(center + spread, 2)


def calc_chip_distribution(daily: list[dict[str, Any]], lookback: int = 60) -> dict[str, Any]:
    """粗算筹码分布：每日量按日K价格区间均匀摊到价格带上。"""
    bars = daily[-lookback:] if len(daily) >= lookback else daily
    valid = []
    for item in bars:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        volume = to_float(item.get("volume")) or 0
        if high is None or low is None or high == low or volume <= 0:
            continue
        valid.append((low, high, volume))
    if not valid:
        return {"peaks": [], "current_pct": None, "profit_pct": 0}

    min_price = min(lo for lo, _, _ in valid)
    max_price = max(hi for _, hi, _ in valid)
    price_range = max_price - min_price

    # Use a fixed step: ~50 bins across the price range, min 0.3 yuan step
    num_bins = max(int(price_range / 0.3) + 1, 50)
    tick = price_range / num_bins
    if tick < 0.1:
        tick = 0.1
        num_bins = int((max_price - min_price) / tick) + 2

    price_bins = [(min_price + (i + 0.5) * tick) for i in range(num_bins)]
    volume_map = [0.0] * num_bins

    for low, high, volume in valid:
        lo_idx = max(0, int((low - min_price) / tick))
        hi_idx = min(num_bins - 1, int((high - min_price) / tick))
        if hi_idx == lo_idx:
            volume_map[lo_idx] += volume
        else:
            segment = volume / (hi_idx - lo_idx + 1)
            for i in range(lo_idx, hi_idx + 1):
                volume_map[i] += segment

    total_chip = sum(volume_map)
    if total_chip == 0:
        return {"peaks": [], "current_pct": None, "profit_pct": 0, "mid_price": None}

    # Top 3 peaks by volume
    sorted_indices = sorted(range(num_bins), key=lambda i: volume_map[i], reverse=True)
    peaks = []
    peak_shares = []
    for idx in sorted_indices[:3]:
        price = price_bins[idx]
        volume = volume_map[idx]
        share_pct = volume / total_chip * 100
        if share_pct > 0.5:
            peak_shares.append(share_pct)

    peak_shares = sorted(peak_shares, reverse=True) if peak_shares else [1, 1, 1]

    for idx in sorted_indices[:3]:
        price = price_bins[idx]
        volume = volume_map[idx]
        share_pct = volume / total_chip * 100
        if share_pct > 0.5:
            half_range = tick * 2
            # Rank by relative share: strongest = 强支撑, next = 支撑
            share_rank = peak_shares.index(share_pct)
            if share_rank == 0 and share_pct > 3:
                level = "强支撑"
            elif share_rank <= 1 and share_pct > 2:
                level = "支撑"
            else:
                level = "弱支撑"
            peaks.append({
                "price": round(price, 2),
                "volume": round(volume),
                "share_of_total": round(share_pct, 2),
                "support_level": level,
            })
    peaks.sort(key=lambda p: p["price"])

    # Current cumulative position (where is today's close relative to chips)
    current_pct = None
    cumulative = 0.0
    for i, vol in enumerate(volume_map):
        cumulative += vol
        if cumulative / total_chip >= 0.5:
            current_pct = round((i / num_bins) * 100, 1)
            break

    # Median price (50th percentile of chip distribution)
    mid_price = None
    cumulative = 0.0
    for i, vol in enumerate(volume_map):
        cumulative += vol
        if cumulative / total_chip >= 0.5:
            mid_price = price_bins[i]
            break

    return {
        "peaks": peaks,
        "total_volume": round(total_chip),
        "current_pct": current_pct,
        "mid_price": mid_price,
    }


def analyze_intraday(bars_5m: list[dict[str, Any]], trade_date: str | None, session: str = "close") -> dict[str, Any]:
    selected_date, bars = filter_trade_date(bars_5m, trade_date)
    if session == "midday":
        bars = [bar for bar in bars if in_range(bar_time(bar), "09:30", "11:30")]
    if len(bars) < 8:
        return {
            "trade_date": selected_date,
            "session": session,
            "data_state": "partial",
            "lines": ["分时数据不足，走势结构只按日线和收盘位置降级判断。"],
            "volume_lines": ["5分钟量能不足，无法拆分上午/午后成交。"],
            "morning_volume": None,
            "afternoon_volume": None,
            "total_volume": sum_volume(bars) or None,
            "max_bar": None,
            "morning_ratio": None,
            "afternoon_ratio": None,
            "recent_avg_volume": None,
            "early_avg_volume": None,
            "volume_state": "分时证据不足",
            "coverage_end_time": max_bar_time(bars),
            "coverage_complete": False,
            "tail_has_data": False,
        }

    morning = [bar for bar in bars if in_range(bar_time(bar), "09:30", "11:30")]
    open_flush = [bar for bar in bars if in_range(bar_time(bar), "09:30", "10:00")]
    rebound = [bar for bar in bars if in_range(bar_time(bar), "10:00", "11:30")]
    late_morning = [bar for bar in bars if in_range(bar_time(bar), "10:45", "11:30")]
    afternoon = [bar for bar in bars if in_range(bar_time(bar), "13:00", "15:00")]
    digestion = [bar for bar in bars if in_range(bar_time(bar), "13:00", "14:30")]
    tail = [bar for bar in bars if in_range(bar_time(bar), "14:30", "15:00")]
    coverage_end_time = max_bar_time(bars)
    coverage_complete = session == "midday" or coverage_end_time >= "14:55"
    total = sum_volume(bars)
    morning_total = sum_volume(morning)
    afternoon_total = sum_volume(afternoon)
    max_bar = max(bars, key=lambda item: to_float(item.get("volume")) or 0)
    early_avg = average_volume(open_flush or morning[:6])
    recent_avg = average_volume(digestion or afternoon)
    max_ratio = ((to_float(max_bar.get("volume")) or 0) / early_avg) if early_avg else None
    rebound_tops = sorted(rebound, key=lambda item: to_float(item.get("volume")) or 0, reverse=True)[:2]

    def segment_line(name: str, segment: list[dict[str, Any]], fallback: str) -> str:
        if not segment:
            return fallback
        first_open = to_float(segment[0].get("open"))
        last_close = to_float(segment[-1].get("close"))
        lows = numeric_values(segment, "low")
        highs = numeric_values(segment, "high")
        low = min(lows) if lows else None
        high = max(highs) if highs else None
        return f"{name}：{price_text(first_open)}→{price_text(last_close)}，区间 {price_text(low)}-{price_text(high)}。"

    lines = [
        segment_line("09:30-10:00｜开盘试探", open_flush, "09:30-10:00｜开盘段数据不足。"),
        f"{bar_time(max_bar)} 放出最大量柱 {volume_wan_shares(to_float(max_bar.get('volume')))}。",
    ]
    if rebound_tops:
        parts = [f"{bar_time(bar)} {volume_wan_shares(to_float(bar.get('volume')))}" for bar in rebound_tops]
        lines.extend(["10:00-11:30｜早盘修复", "；".join(parts) + "，推动上午修复。"])
    if session == "midday":
        lines.extend(
            [
                segment_line("10:45-11:30｜临近午盘", late_morning, "10:45-11:30｜临近午盘数据不足。"),
                f"临近午盘均量约 {volume_wan_shares(average_volume(late_morning))}。",
            ]
        )
    else:
        lines.extend(
            [
                segment_line("13:05-14:30｜午后震荡", digestion, "13:05-14:30｜午后段数据不足。"),
                f"午后均量约 {volume_wan_shares(recent_avg)}，较早盘明显收敛。" if early_avg and recent_avg < early_avg * 0.75 else f"午后均量约 {volume_wan_shares(recent_avg)}。",
                segment_line("14:30-15:00｜尾盘横盘", tail, "14:30-15:00｜尾盘数据不足。"),
            ]
        )
        tail_last = tail[-1] if tail else bars[-1]
        lines.append(f"{bar_time(tail_last)} 量能约 {volume_wan_shares(to_float(tail_last.get('volume')))}。")

    volume_lines = [f"{bar_time(max_bar)} 最大量柱 {volume_wan_shares(to_float(max_bar.get('volume')))}" + (f"，约为开盘段均量 {max_ratio:.1f}倍" if max_ratio else "")]
    if session == "midday":
        volume_lines.insert(0, f"上午成交 {volume_wan_shares(morning_total)}")
    else:
        volume_lines.insert(0, f"午后 {volume_wan_shares(afternoon_total)}，占全天 {afternoon_total / total * 100:.0f}%" if total else "午后成交占比不足。")
        volume_lines.insert(0, f"上午 {volume_wan_shares(morning_total)}，占全天 {morning_total / total * 100:.0f}%" if total else "上午成交占比不足。")
    volume_state = "早盘放量、午后缩量" if early_avg and recent_avg and recent_avg < early_avg * 0.75 else "量能平稳"
    return {
        "trade_date": selected_date,
        "session": session,
        "data_state": "full" if coverage_complete else "partial_close",
        "lines": lines,
        "volume_lines": volume_lines,
        "morning_volume": morning_total,
        "afternoon_volume": afternoon_total,
        "total_volume": total,
        "max_bar": {"time": bar_time(max_bar), "volume": to_float(max_bar.get("volume"))},
        "morning_ratio": morning_total / total if total else None,
        "afternoon_ratio": afternoon_total / total if total else None,
        "recent_avg_volume": recent_avg,
        "early_avg_volume": early_avg,
        "volume_state": volume_state,
        "coverage_end_time": coverage_end_time,
        "coverage_complete": coverage_complete,
        "tail_has_data": bool(tail),
    }


def build_levels(current: float, quote: dict[str, Any], daily: list[dict[str, Any]], cost: float | None) -> dict[str, Any]:
    today_low = to_float(quote.get("low"))
    today_high = to_float(quote.get("high"))
    recent = daily[-20:] if len(daily) >= 20 else daily
    previous = daily[-2] if len(daily) >= 2 else None
    previous_low = to_float(previous.get("low")) if previous else None
    recent_high_values = numeric_values(recent, "high")
    recent_low_values = numeric_values(recent, "low")
    recent_high = max(recent_high_values) if recent_high_values else None
    recent_low = min(recent_low_values) if recent_low_values else None
    ma5 = moving_average(daily, 5)
    ma10 = moving_average(daily, 10)
    ma20 = moving_average(daily, 20)
    dense_low, dense_high = dense_price_zone(daily)
    first_support = round(max((today_low or current), current * 0.985), 2) if today_low and today_low < current else round(current * 0.985, 2)
    support = [
        {"price": round(current, 2), "label": "今日收盘价，守住偏强"},
        {"price": first_support, "label": "回撤第一防线"},
    ]
    if today_low:
        support.append({"price": round(today_low, 2), "label": "今日低点，跌破则止跌失败"})
    if previous_low and today_low and abs(previous_low - today_low) / current <= 0.01:
        support.append({"price": round(previous_low, 2), "label": "前一交易日低点，双低点参考"})
    pressure = []
    if today_high:
        pressure.append({"price": round(today_high, 2), "label": "今日高点，明日第一关"})
    if cost and cost > current:
        pressure.append({"price": round(cost * 0.998, 2), "label": "成本区前压力"})
        pressure.append({"price": round(cost, 2), "label": "你的成本，最关键"})
    elif dense_high and dense_high > current:
        pressure.append({"price": dense_high, "label": "近20日成交密集压力"})
    if recent_high and recent_high > current * 1.03:
        pressure.append({"price": round(recent_high, 2), "label": "中期趋势压力参考"})
    if not pressure:
        pressure.append({"price": round(current * 1.02, 2), "label": "短线确认压力"})
    key_pressure = pressure[1]["price"] if len(pressure) > 1 else pressure[0]["price"]
    return {
        "support": support,
        "pressure": pressure,
        "key_support": support[2]["price"] if len(support) > 2 else support[1]["price"],
        "first_support": support[1]["price"],
        "key_pressure": key_pressure,
        "today_high": today_high,
        "today_low": today_low,
        "previous_low": previous_low,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "ma": {"ma5": ma5, "ma10": ma10, "ma20": ma20},
        "chip_zone": {"low": dense_low, "high": dense_high},
    }


def theory_verdicts(current: float, quote: dict[str, Any], daily: list[dict[str, Any]], intraday: dict[str, Any], levels: dict[str, Any], cost: float | None, session: str = "close") -> dict[str, Any]:
    previous = daily[-2] if len(daily) >= 2 else {}
    prev_close = to_float(quote.get("pre_close")) or to_float(previous.get("close"))
    today_low = levels.get("today_low")
    previous_low = levels.get("previous_low")
    today_high = levels.get("today_high")
    recent_high = levels.get("recent_high")
    low_close_reclaim = today_low is not None and current > today_low * 1.025
    double_low = today_low is not None and previous_low is not None and abs(today_low - previous_low) / max(current, 1) <= 0.01
    lower_high = bool(recent_high and current < recent_high * 0.96)
    pressure = levels["key_pressure"]
    above_pressure = current >= pressure
    morning_ratio = intraday.get("morning_ratio") or 0
    early_avg = intraday.get("early_avg_volume") or 0
    recent_avg = intraday.get("recent_avg_volume") or 0
    intraday_usable = intraday.get("data_state") in {"full", "partial_close"}
    volume_repair = intraday_usable and morning_ratio >= 0.55 and low_close_reclaim
    afternoon_shrink = bool(early_avg and recent_avg and recent_avg < early_avg * 0.75)
    tail_has_data = bool(intraday.get("tail_has_data"))
    pnl_pct = pct_change(cost, current) if cost else None
    chip_pressure = bool(cost and current < cost and (cost - current) / current <= 0.05)

    macd_p = calc_macd_params(daily)
    macd_above = macd_p.get("above_zero")
    macd_below = macd_p.get("below_zero")
    macd_gcx = macd_p.get("golden_cross")
    macd_dcx = macd_p.get("death_cross")
    macd_hist = to_float(macd_p.get("histogram"))
    macd_line = to_float(macd_p.get("macd_line"))
    macd_hist_prev = to_float(daily[-2].get("macd_histogram")) if len(daily) >= 2 else None
    hist_expand = macd_hist is not None and macd_hist_prev is not None and ((macd_hist > macd_hist_prev > 0) or (macd_hist < macd_hist_prev < 0))
    macd_cross_3 = False
    chk = daily[-3:] if len(daily) >= 3 else daily
    for _i in range(1, len(chk)):
        _pm = to_float(chk[_i-1].get("macd_line"))
        _pd = to_float(chk[_i-1].get("dea"))
        _cm = to_float(chk[_i].get("macd_line"))
        _cd = to_float(chk[_i].get("dea"))
        if _pm is not None and _pd is not None and _cm is not None and _cd is not None and abs((_pm - _pd) - (_cm - _cd)) > 0:
            sig_prev = (_pm - _pd) * (_cm - _cd)
            if sig_prev <= 0:
                macd_cross_3 = True
                break
    macd_struc_b = 10 if (macd_gcx and not afternoon_shrink) else (5 if macd_below and not macd_dcx else 0)
    macd_mom_b = 15 if macd_cross_3 else (10 if macd_above and not macd_dcx else 0)
    if macd_dcx:
        macd_mom_b = -10
    elif macd_hist is not None and macd_hist > 0 and hist_expand:
        macd_mom_b = max(macd_mom_b, 12)

    from chan_core import chanlun_analysis
    from wyckoff_core import wyckoff_analysis
    chan_r = chanlun_analysis(bars=daily, current=current, macd_hist_current=macd_hist, macd_hist_prev=macd_hist_prev)
    wyck_r = wyckoff_analysis(daily)

    structure_score = 50
    if chan_r.get("trend_label") == "拉升段":
        structure_score += 15
    elif chan_r.get("trend_label") == "回调段":
        structure_score -= 10
    chan_bps = str(chan_r.get("buy_point_text", ""))
    if "一类买" in chan_bps: structure_score += 25
    elif "二类买" in chan_bps: structure_score += 15
    elif "三类买" in chan_bps: structure_score += 10
    chan_div = chan_r.get("divergence", {})
    if chan_div.get("bottom_divergence"): structure_score += 15
    elif chan_div.get("top_divergence"): structure_score -= 10
    if chan_r.get("strokes_count", 0) >= 3: structure_score += 5
    elif chan_r.get("strokes_count", 0) < 2: structure_score -= 5
    structure_score += (10 if double_low else 0) + (10 if low_close_reclaim else 0)
    structure_score += 5 if current > (prev_close or current) else 0
    structure_score -= 10 if lower_high else 0
    structure_score += 10 if above_pressure else 0
    structure_score += macd_struc_b

    volume_score = 50
    if wyck_r.get("spring_signal"): volume_score += 25
    if wyck_r.get("upthrust_signal"): volume_score += 15
    if wyck_r.get("bearish_volume_divergence"): volume_score -= 10
    if wyck_r.get("bullish_volume_divergence"): volume_score += 5
    volume_score += (15 if volume_repair else 0) - (5 if afternoon_shrink else 0)

    chip_score = 50 - (15 if chip_pressure else 0) + (10 if cost and pnl_pct is not None and pnl_pct >= 0 else 0)

    from momentum_core import assess_momentum
    momentum_result = assess_momentum(daily)
    momentum_score = momentum_result.get("score", 50)
    momentum_dir = momentum_result.get("direction", "neutral")
    momentum_signals = momentum_result.get("signals", [])
    momentum_rsi = momentum_result.get("rsi", {})
    momentum_adx = momentum_result.get("adx", {})
    momentum_macd = momentum_result.get("macd", {})

    total_score = round(structure_score * 0.32 + volume_score * 0.28 + chip_score * 0.18 + momentum_score * 0.22)

    close_word = "现价" if session == "midday" else "收盘"
    next_word = "午后" if session == "midday" else "明天"
    macd_str = "MACD金叉确认转强。" if macd_gcx else chan_r.get("trend_label", "") + "。"
    chanlun_text = macd_str
    if chan_div.get("bottom_divergence"): chanlun_text += " 有底背驰，止跌信号增强。"
    elif chan_div.get("top_divergence"): chanlun_text += " 有顶背驰，需警惕回调。"
    elif chan_bps and chan_bps != "无买卖点": chanlun_text += " " + chan_bps
    else: chanlun_text += " 结构未出现明确买卖点。"
    wyckoff_text = "供需平衡，无明显信号。"
    if wyck_r.get("spring_signal"):
        wyckoff_text = f"Spring 吸筹信号：{wyck_r.get('spring_reason', '')}"
    elif wyck_r.get("upthrust_signal"):
        wyckoff_text = f"Upthrust 派发信号：{wyck_r.get('upthrust_reason', '')}"
    elif wyck_r.get("bearish_volume_divergence"):
        wyckoff_text = "量价背离（顶背离）：高价创新高但量能萎缩。"
    elif wyck_r.get("bullish_volume_divergence"):
        wyckoff_text = "量价背离（底背离）：低价创新低但量能萎缩。"
    else:
        wyckoff_text = wyck_r.get("wyckoff_summary", "供需平衡，无明显信号。")

    return {
        "chanlun": chanlun_text,
        "wyckoff": wyckoff_text,
        "chip": (f"{cost:.2f} 是你的成本压力区；轻量估算不等同真实筹码分布。" if cost else "按近20日成交密集区做轻量估算，不等同真实筹码分布。"),
        "fund": "有吸筹/洗盘嫌疑，但证据不足以确认。" if volume_repair else "资金行为证据不足，只能按价格和量能观察。",
        "momentum": "；".join(momentum_signals) if momentum_signals else (f"{momentum_dir.title()}，动能评分{momentum_score}/100" if session not in {"midday"} else "上午改善，午后还需确认。"),
        "supports": [
            "结构：两次接近位置止跌" if double_low else "结构：下杀后收回，短线修复",
            "量价：开盘放量下杀后收回，不是一路放量下跌" if volume_repair else "量价：收盘修复，但分时确认不足",
            "威科夫：有 Spring 类修复特征" if volume_repair else "威科夫：供需修复仍在观察",
            "资金：外盘数据可用时只作辅助；尾盘无明显砸盘" if tail_has_data else "资金：外盘数据可用时只作辅助；尾盘数据不足，不做尾盘判断",
            f"动能：{close_word}高于前收" if current > (prev_close or current) else "动能：仍需重新放量确认",
        ],
        "blocks": [
            f"缠论：还没突破 {price_text(today_high)}-{price_text(pressure)}，结构没有向上离开" if not above_pressure else "缠论：突破后仍要看回踩是否守住",
            "量价：午后明显缩量，买盘没有持续放大" if afternoon_shrink else f"量价：持续性还要等{next_word}验证",
            f"筹码：{cost:.2f} 是你的成本，附近可能有解套压力" if cost and current < cost else "筹码：上方成交密集区仍需消化",
            f"趋势：近期高点 {recent_high:.2f} 以来，高点仍在降低" if recent_high and lower_high else "趋势：中期趋势仍需继续确认",
            f"动能：强点在上午，{next_word}需要重新放量确认",
        ],
        "scores": {
            "structure": max(0, min(100, round(structure_score))),
            "volume": max(0, min(100, round(volume_score))),
            "chip": max(0, min(100, round(chip_score))),
            "momentum": max(0, min(100, round(momentum_score))),
            "total": max(0, min(100, total_score)),
        },
        "state": "转强确认" if above_pressure and total_score >= 70 else "短线止跌修复" if total_score >= 55 else "弱修复观察",
        "double_low": double_low,
        "afternoon_shrink": afternoon_shrink,
    }


def build_review(target: str, cost: float | None = None, trade_date: str | None = None, session: str = "close") -> dict[str, Any]:
    if session not in {"close", "midday"}:
        raise RuntimeError("session must be close or midday")
    provider = get_provider()
    sec = provider.resolve_security(target)
    quote = provider.fetch_quote(sec)
    daily = provider.fetch_qfq_daily(sec, days=40)
    calc_macd(daily)
    daily_macd_params = calc_macd_params(daily)
    bars_5m = provider.fetch_5m(sec, datalen=80)
    current = latest_or_quote_close(quote, daily)
    last_bar = daily[-1] if daily else {}
    atr14 = to_float(last_bar.get("atr14")) or 0.0
    atr7 = to_float(last_bar.get("atr7")) or 0.0
    atr_ratio_val = to_float(last_bar.get("atr_ratio")) or 0.0
    atr_level_name, atr_suggested_cap = atr_volatility_level(atr_ratio_val) if atr14 > 0 else ("数据不足", 10)
    selected_date = trade_date or (daily[-1].get("date") if daily else None) or quote.get("trade_date")
    intraday = analyze_intraday(bars_5m, selected_date, session=session)
    levels = build_levels(current, quote, daily, cost)
    chip_dist = calc_chip_distribution(daily, lookback=60)
    theory = theory_verdicts(current, quote, daily, intraday, levels, cost, session=session)
    previous_close = to_float(quote.get("pre_close")) or (to_float(daily[-2].get("close")) if len(daily) >= 2 else None)
    change_pct = to_float(quote.get("current_change_pct"))
    if change_pct is None:
        change_pct = pct_change(previous_close, current)
    pnl_pct = pct_change(cost, current) if cost else None
    name = quote.get("name") or sec.name
    symbol = quote.get("symbol") or sec.ts_code
    review_date = intraday.get("trade_date") or selected_date or datetime.now().strftime("%Y-%m-%d")
    return {
        "contract": "review_trader_v1",
        "mode": "single",
        "session": session,
        "name": name,
        "symbol": symbol,
        "date": review_date,
        "target": target,
        "quote": {
            "open": to_float(quote.get("open")),
            "high": to_float(quote.get("high")),
            "low": to_float(quote.get("low")),
            "close": current,
            "pre_close": previous_close,
            "change_pct": change_pct,
            "volume": to_float(quote.get("volume")),
            "amount": to_float(quote.get("amount")),
            "turnover_rate": to_float(quote.get("turnover_rate")),
        },
        "cost": cost,
        "pnl_pct": pnl_pct,
        "intraday": intraday,
        "levels": levels,
        "theory": theory,
        "macd_params": {
            "macd_line": daily_macd_params.get("macd_line"),
            "dea": daily_macd_params.get("dea"),
            "histogram": daily_macd_params.get("histogram"),
            "golden_cross": daily_macd_params.get("golden_cross"),
            "death_cross": daily_macd_params.get("death_cross"),
        },
        "summary": {
            "state": theory["state"],
            "score": theory["scores"]["total"],
            "key_pressure": levels["key_pressure"],
            "key_support": levels["key_support"],
            "first_support": levels["first_support"],
            "action": "放量站稳关键压力才考虑加仓；否则继续观察。",
        },
        "atr": {
            "atr7": atr7,
            "atr14": atr14,
            "atr_ratio": atr_ratio_val,
            "level": atr_level_name,
            "suggested_cap_pct": atr_suggested_cap,
            "available": atr14 > 0,
        },
        "chip_distribution": chip_dist,
        "data_time": f"{quote.get('trade_date') or review_date} {quote.get('trade_time') or ''}".strip(),
    }


def enrich_with_signal_backtrack(review: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    symbol = str(review.get("symbol") or "")
    if not symbol:
        review.setdefault("historical_signals", [])
        review.setdefault("target_score", None)
        review.setdefault("pnl_pct", None)
        return review
    try:
        from signal_store import load_recent_signals
        signals = load_recent_signals(symbol, limit=limit)
        review_date = str(review.get("date") or "")
        same_day = [s for s in signals if str(s.get("trade_date") or "") == review_date]
        review["historical_signals"] = same_day if same_day else signals[-limit:]
    except ImportError:
        review.setdefault("historical_signals", [])
    try:
        from trader_shared import fill_by_target
        name = str(review.get("name") or "")
        pnl_pct = float(review.get("pnl_pct") or 0)
        fill_by_target(name, pnl_pct=pnl_pct, days_held=1, outcome="unknown")
        review.setdefault("tracker_filled", True)
    except ImportError:
        pass
    return review


def calc_macd(bars: list[dict[str, Any]]) -> None:
    if not bars or len(bars) < 26:
        return

    closes: list[float] = []
    for bar in bars:
        c = to_float(bar.get("close"))
        if c is not None:
            closes.append(c)

    if len(closes) < 26:
        return

    fast_alpha = 2.0 / 13.0
    slow_alpha = 2.0 / 27.0
    signal_alpha = 2.0 / 10.0

    ema12 = sum(closes[:12]) / 12.0
    ema26 = sum(closes[:26]) / 26.0

    dea_values: list[float] = []

    for i in range(12, len(bars)):
        c = closes[i]
        ema12 = ema12 * fast_alpha + c * (1.0 - fast_alpha)
        if i >= 26:
            ema26 = ema26 * slow_alpha + c * (1.0 - slow_alpha)
            macd_line = ema12 - ema26
            dea_values.append(macd_line)
            if len(dea_values) == 9:
                dea = sum(dea_values) / 9.0
            elif len(dea_values) > 9:
                dea = dea * signal_alpha + macd_line * (1.0 - signal_alpha)
            else:
                dea = macd_line
            bars[i]["macd_line"] = round(macd_line, 4)
            bars[i]["dea"] = round(dea, 4)
            bars[i]["macd_histogram"] = round(macd_line - dea, 4)


def calc_macd_params(bars: list[dict[str, Any]]) -> dict[str, Any]:
    calc_macd(bars)
    latest = bars[-1] if bars else None
    if latest is None:
        return {
            "macd_line": None,
            "dea": None,
            "histogram": None,
            "above_zero": None,
            "below_zero": None,
            "golden_cross": False,
            "death_cross": False,
            "cross_bar_index": -1,
        }

    m = to_float(latest.get("macd_line"))
    d = to_float(latest.get("dea"))
    h = to_float(latest.get("macd_histogram"))

    if m is not None:
        above_zero = m > 0
        below_zero = m < 0
    else:
        above_zero = None
        below_zero = None

    check = bars[-5:] if len(bars) >= 5 else bars
    golden_cross = False
    death_cross = False
    cross_idx = -1

    for i in range(1, len(check)):
        prev_m = to_float(bars[i - 1].get("macd_line"))
        prev_d = to_float(bars[i - 1].get("dea"))
        cur_m = to_float(bars[i].get("macd_line"))
        cur_d = to_float(bars[i].get("dea"))
        if prev_m is not None and prev_d is not None and cur_m is not None and cur_d is not None:
            prev_diff = prev_m - prev_d
            cur_diff = cur_m - cur_d
            if prev_diff <= 0 and cur_diff > 0:
                golden_cross = True
                cross_idx = i
            elif prev_diff >= 0 and cur_diff < 0:
                death_cross = True
                cross_idx = i

    return {
        "macd_line": m,
        "dea": d,
        "histogram": h,
        "above_zero": above_zero,
        "below_zero": below_zero,
        "golden_cross": golden_cross,
        "death_cross": death_cross,
        "cross_bar_index": cross_idx,
    }
