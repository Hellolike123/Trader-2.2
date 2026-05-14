from __future__ import annotations

from typing import Any

from light_data import to_float

try:
    from trader_shared.config import CHANLUN_MIN_BARS, CHANLUN_MIN_BARS_PER_STROKE
except ImportError:
    CHANLUN_MIN_BARS = 20
    CHANLUN_MIN_BARS_PER_STROKE = 5


def _calc_macd(bars: list[dict]) -> list[dict]:
    bars = [dict(b) for b in bars]
    n = len(bars)
    closes = [to_float(b.get("close")) for b in bars]

    ema12_val = None
    ema26_val = None
    dif_vals: list[float | None] = [None] * n

    for i in range(n):
        c = closes[i]
        if c is None:
            continue

        if i == 11:
            vals_12 = [x for x in closes[:12] if x is not None]
            if len(vals_12) == 12:
                ema12_val = sum(vals_12) / 12
        elif i > 11 and ema12_val is not None:
            ema12_val = ema12_val * 11 / 13 + c * 2 / 13

        if i == 25:
            vals_26 = [x for x in closes[:26] if x is not None]
            if len(vals_26) == 26:
                ema26_val = sum(vals_26) / 26
        elif i > 25 and ema26_val is not None:
            ema26_val = ema26_val * 25 / 27 + c * 2 / 27

        if ema12_val is not None and ema26_val is not None:
            dif_vals[i] = ema12_val - ema26_val

    dea_val = None
    dea_buffer: list[float] = []
    for i in range(n):
        d = dif_vals[i]
        if d is None:
            bars[i]["macd_histogram"] = 0.0
            continue

        dea_buffer.append(d)

        if len(dea_buffer) < 9:
            bars[i]["macd_histogram"] = 0.0
            continue

        if dea_val is None:
            dea_val = sum(dea_buffer) / 9
        else:
            dea_val = dea_val * 8 / 10 + d * 2 / 10

        # Keep histogram definition consistent with momentum_core: DIF - DEA (1x scale)
        bars[i]["macd_histogram"] = round(d - dea_val, 4)

    return bars


def handle_inclusion(bars: list[dict]) -> list[dict]:
    if not bars:
        return []
    if len(bars) == 1:
        return [dict(bars[0])]

    result: list[dict[str, Any]] = [dict(bars[0])]

    for i in range(1, len(bars)):
        curr = dict(bars[i])

        while True:
            if not result:
                result.append(curr)
                break

            prev = result[-1]
            h_prev = to_float(prev.get("high"))
            l_prev = to_float(prev.get("low"))
            h_curr = to_float(curr.get("high"))
            l_curr = to_float(curr.get("low"))

            if h_prev is None or l_prev is None or h_curr is None or l_curr is None:
                result.append(curr)
                break

            contains = (h_curr >= h_prev and l_curr <= l_prev) or (h_curr <= h_prev and l_curr >= l_prev)
            if not contains:
                result.append(curr)
                break

            direction: str | None = None
            if len(result) >= 2:
                b2 = result[-2]
                h2 = to_float(b2.get("high"))
                l2 = to_float(b2.get("low"))
                if h2 is not None and l2 is not None:
                    if h2 < h_prev and l2 < l_prev:
                        direction = "up"
                    elif h2 > h_prev and l2 > l_prev:
                        direction = "down"

            if direction == "up":
                curr["high"] = round(max(h_curr, h_prev), 4)
                curr["low"] = round(max(l_curr, l_prev), 4)
            elif direction == "down":
                curr["high"] = round(min(h_curr, h_prev), 4)
                curr["low"] = round(min(l_curr, l_prev), 4)
            else:
                curr["high"] = round(max(h_curr, h_prev), 4)
                curr["low"] = round(min(l_curr, l_prev), 4)

            result.pop()

    return result


def find_fractions(bars: list[dict]) -> list[dict]:
    if len(bars) < 3:
        return []

    fractions: list[dict[str, Any]] = []
    for i in range(1, len(bars) - 1):
        left = bars[i - 1]
        mid = bars[i]
        right = bars[i + 1]

        h_left = to_float(left.get("high"))
        l_left = to_float(left.get("low"))
        h_mid = to_float(mid.get("high"))
        l_mid = to_float(mid.get("low"))
        h_right = to_float(right.get("high"))
        l_right = to_float(right.get("low"))
        c_mid = to_float(mid.get("close"))

        if any(v is None for v in [h_left, l_left, h_mid, l_mid, h_right, l_right, c_mid]):
            continue

        is_top = h_mid > h_left and h_mid > h_right
        is_bottom = l_mid < l_left and l_mid < l_right

        if is_top and is_bottom:
            # 十字星同时满足顶底条件，按极值倾向决定
            top_margin = min(h_mid - h_left, h_mid - h_right)
            bottom_margin = min(l_left - l_mid, l_right - l_mid)
            if top_margin >= bottom_margin:
                is_bottom = False
            else:
                is_top = False

        if is_top:
            fractions.append({
                "type": "top",
                "high": h_mid,
                "low": l_mid,
                "index": i,
                "close": c_mid,
            })
        elif is_bottom:
            fractions.append({
                "type": "bottom",
                "high": h_mid,
                "low": l_mid,
                "index": i,
                "close": c_mid,
            })

    return fractions


def build_strokes(fractions: list[dict], min_bars_per_stroke: int = 5) -> list[dict]:
    if len(fractions) < 2:
        return []

    strokes: list[dict[str, Any]] = []
    num = len(fractions)
    i = 0

    while i < num - 1:
        start = fractions[i]
        j = i + 1

        # 连续同类分型取极值：顶取最高的，底取最低的
        best_same = start
        while j < num and fractions[j]["type"] == start["type"]:
            f = fractions[j]
            if start["type"] == "top" and f["high"] > best_same["high"]:
                best_same = f
            elif start["type"] == "bottom" and f["low"] < best_same["low"]:
                best_same = f
            j += 1

        start = best_same

        if j >= num:
            break

        end = fractions[j]
        # end 也可能是连续同类分型的第一个，需要在下一轮迭代中取极值
        # 但这里先检查距离
        if end["index"] - start["index"] >= min_bars_per_stroke - 1:
            direction = "up" if start["type"] == "bottom" else "down"
            strokes.append({
                "start_type": start["type"],
                "start_price": start["low"] if start["type"] == "bottom" else start["high"],
                "end_type": end["type"],
                "end_price": end["high"] if end["type"] == "top" else end["low"],
                "direction": direction,
            })

        i = j

    return strokes


def build_zones(strokes: list[dict]) -> list[dict]:
    if len(strokes) < 3:
        return []

    zones: list[dict[str, Any]] = []
    for i in range(0, len(strokes) - 2, 1):
        group = strokes[i:i + 3]

        highs: list[float] = []
        lows: list[float] = []
        for s in group:
            highs.append(max(s["start_price"], s["end_price"]))
            lows.append(min(s["start_price"], s["end_price"]))

        zh_top = min(highs)
        zh_bottom = max(lows)
        valid = zh_top > zh_bottom

        if valid:
            zones.append({
                "zh_top": round(zh_top, 4),
                "zh_bottom": round(zh_bottom, 4),
                "zh_center": round((zh_top + zh_bottom) / 2, 4),
                "strokes": group,
                "valid": valid,
            })

    return zones


def detect_buy_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
) -> list[dict]:
    buy_points: list[dict[str, Any]] = []

    if not strokes:
        return buy_points

    # 一类买: 向下笔 + MACD 绿柱缩短 (底背驰信号)
    last_stroke = strokes[-1]
    if last_stroke["direction"] == "down":
        if macd_hist_current is not None and macd_hist_prev is not None and macd_hist_current < 0 and macd_hist_prev < 0:
            if macd_hist_current > macd_hist_prev:
                buy_points.append({
                    "type": "一类买",
                    "price": round(last_stroke["end_price"], 4),
                    "confidence": 3,
                })
        elif macd_hist_current is not None and macd_hist_current < 0:
            buy_points.append({
                "type": "一类买",
                "price": round(last_stroke["end_price"], 4),
                "confidence": 2,
            })

    # 二类买: down_1(low_a) -> up -> down_2(low_b) 且 low_b > low_a
    if len(strokes) >= 3:
        down_strokes = [s for s in strokes if s["direction"] == "down"]
        up_strokes = [s for s in strokes if s["direction"] == "up"]
        if len(down_strokes) >= 2 and up_strokes:
            low_a = down_strokes[-2]["end_price"]
            low_b = down_strokes[-1]["end_price"]
            up_high = max(s["end_price"] for s in up_strokes)
            if low_b > low_a and low_b < up_high:
                buy_points.append({
                    "type": "二类买",
                    "price": round(low_b, 4),
                    "confidence": 2,
                })

    # 三类买 confirmed
    if last_close > 0 and zones:
        last_valid: dict | None = None
        for z in reversed(zones):
            if z["valid"]:
                last_valid = z
                break

        if last_valid is not None:
            zh_top = last_valid["zh_top"]
            above_pct = (last_close - zh_top) / zh_top
            if 0 < above_pct <= 0.02:
                buy_points.append({
                    "type": "三类买",
                    "price": round(last_close, 4),
                    "confidence": 1,
                })

    return buy_points


def detect_divergence(bars: list[dict]) -> dict:
    result: dict[str, bool] = {"top_divergence": False, "bottom_divergence": False}

    n = len(bars)
    if n < 5:
        return result

    peaks: list[dict[str, Any]] = []
    for i in range(2, n - 2):
        high = to_float(bars[i].get("high"))
        h_prev = to_float(bars[i - 1].get("high"))
        h_next = to_float(bars[i + 1].get("high"))
        macd = to_float(bars[i].get("macd_histogram"))

        if high is not None and h_prev is not None and h_next is not None and macd is not None:
            if high > h_prev and high > h_next:
                peaks.append({"index": i, "price": high, "macd": macd})

    if len(peaks) >= 2:
        p1 = peaks[-2]
        p2 = peaks[-1]
        if p2["price"] > p1["price"] and p2["macd"] < p1["macd"]:
            result["top_divergence"] = True

    troughs: list[dict[str, Any]] = []
    for i in range(2, n - 2):
        low = to_float(bars[i].get("low"))
        l_prev = to_float(bars[i - 1].get("low"))
        l_next = to_float(bars[i + 1].get("low"))
        macd = to_float(bars[i].get("macd_histogram"))

        if low is not None and l_prev is not None and l_next is not None and macd is not None:
            if low < l_prev and low < l_next:
                troughs.append({"index": i, "price": low, "macd": macd})

    if len(troughs) >= 2:
        t1 = troughs[-2]
        t2 = troughs[-1]
        if t2["price"] < t1["price"] and t2["macd"] > t1["macd"]:
            result["bottom_divergence"] = True

    return result


def chanlun_analysis(
    bars: list[dict],
    current: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
) -> dict:
    if len(bars) < CHANLUN_MIN_BARS:
        return {}

    has_macd = any(b.get("macd_histogram") is not None for b in bars[:5]) if len(bars) >= 5 else False
    if not has_macd:
        _calc_macd(bars)

    cleaned = handle_inclusion(bars)
    fractions = find_fractions(cleaned)
    strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE)
    zones = build_zones(strokes)
    divergence = detect_divergence(bars)

    buy_points = detect_buy_points(strokes, zones, current, macd_hist_current, macd_hist_prev)

    strokes_count = len(strokes)
    zones_count = len(zones)

    if strokes_count >= 3:
        trend_label = "回调段" if strokes[-1]["direction"] == "down" else "拉升段"
    else:
        trend_label = "数据不足"

    buy_point_text = "、".join([bp["type"] for bp in buy_points]) if buy_points else "无"

    last_valid_zone_last_price = None
    last_valid_zone_first_price = None
    for z in reversed(zones):
        if z["valid"]:
            last_valid_zone_last_price = z["zh_center"]
            break
    for z in zones:
        if z["valid"]:
            last_valid_zone_first_price = z["zh_center"]
            break

    return {
        "strokes": strokes,
        "zones": zones,
        "buy_points": buy_points,
        "trend_label": trend_label,
        "buy_point_text": buy_point_text,
        "strokes_count": strokes_count,
        "zones_count": zones_count,
        "divergence": divergence,
        "last_valid_zone_last_price": last_valid_zone_last_price,
        "last_valid_zone_first_price": last_valid_zone_first_price,
    }


def chanlun_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    return {"chanlun": chanlun_analysis(bars, current, macd_h_curr, macd_h_prev)}
