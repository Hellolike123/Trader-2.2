from __future__ import annotations

from typing import Any

from trader_shared.light_data import to_float

try:
    from trader_shared.config import CHANLUN_MIN_BARS, CHANLUN_MIN_BARS_PER_STROKE, CHANLUN_MIN_STROKES_PER_SEGMENT
except ImportError:
    CHANLUN_MIN_BARS = 20
    CHANLUN_MIN_BARS_PER_STROKE = 5
    CHANLUN_MIN_STROKES_PER_SEGMENT = 3


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
    last_direction: str | None = None

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
        direction = "up" if start["type"] == "bottom" else "down"

        # 强制交替：新笔方向必须与上一笔相反
        if last_direction is not None and direction == last_direction:
            i = j
            continue

        if end["index"] - start["index"] >= min_bars_per_stroke - 1:
            strokes.append({
                "start_type": start["type"],
                "start_price": start["low"] if start["type"] == "bottom" else start["high"],
                "end_type": end["type"],
                "end_price": end["high"] if end["type"] == "top" else end["low"],
                "direction": direction,
            })
            last_direction = direction

        i = j

    return strokes


def build_segments(strokes: list[dict], min_strokes: int = 3) -> list[dict]:
    """将笔序列构建为线段序列。

    线段是最小可递归走势单元，由至少3笔构成。
    使用简化版特征序列法判断线段终结：
    - 向上线段中，取所有向下笔构成特征序列
    - 如果某根向下笔的低点跌破前一根向下笔的低点，线段终结
    - 向下线段中，取所有向上笔构成特征序列
    - 如果某根向上笔的高点升破前一根向上笔的高点，线段终结
    """
    if len(strokes) < min_strokes:
        return []

    # 寻找第一个有价格重叠的3笔组合作为线段起点
    seg_start = -1
    for k in range(len(strokes) - 2):
        h0 = max(strokes[k]["start_price"], strokes[k]["end_price"])
        l0 = min(strokes[k]["start_price"], strokes[k]["end_price"])
        h1 = max(strokes[k + 1]["start_price"], strokes[k + 1]["end_price"])
        l1 = min(strokes[k + 1]["start_price"], strokes[k + 1]["end_price"])
        h2 = max(strokes[k + 2]["start_price"], strokes[k + 2]["end_price"])
        l2 = min(strokes[k + 2]["start_price"], strokes[k + 2]["end_price"])
        overlap_top = min(h0, h1, h2)
        overlap_bottom = max(l0, l1, l2)
        if overlap_top > overlap_bottom:
            seg_start = k
            break

    if seg_start < 0:
        # 所有3笔组合都没有价格重叠
        return []

    # 确定第一段线段方向
    first_high = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
    first_low = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
    third_high = max(strokes[seg_start + 2]["start_price"], strokes[seg_start + 2]["end_price"])
    third_low = min(strokes[seg_start + 2]["start_price"], strokes[seg_start + 2]["end_price"])

    if strokes[seg_start]["direction"] == "up" and third_high > first_high:
        current_direction = "up"
    elif strokes[seg_start]["direction"] == "down" and third_low < first_low:
        current_direction = "down"
    else:
        current_direction = strokes[seg_start]["direction"]

    segments: list[dict[str, Any]] = []
    # seg_start 已在上面确定，不再重置为0
    # 特征序列：记录与线段方向相反的笔
    # 向上线段 → 取向下笔（用低点）；向下线段 → 取向上笔（用高点）
    last_char_val: float | None = None  # 上一根特征序列的极值

    for i in range(seg_start + 1, len(strokes)):
        s = strokes[i]

        if current_direction == "up":
            # 向上线段：只看向下笔作为特征序列
            if s["direction"] == "down":
                char_val = min(s["start_price"], s["end_price"])  # 向下笔低点
                if last_char_val is not None and char_val < last_char_val:
                    # 线段终结：当前向下笔低点 < 前一根向下笔低点
                    # 线段终结于前一根笔（向上笔，即 i-1）
                    end_idx = i - 1
                    seg_strokes = strokes[seg_start:end_idx + 1]
                    seg_high = max(
                        max(ss["start_price"], ss["end_price"]) for ss in seg_strokes
                    )
                    seg_low = min(
                        min(ss["start_price"], ss["end_price"]) for ss in seg_strokes
                    )
                    start_p = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                    end_p = max(strokes[end_idx]["start_price"], strokes[end_idx]["end_price"])
                    segments.append({
                        "direction": "up",
                        "start_price": start_p,
                        "end_price": end_p,
                        "high": seg_high,
                        "low": seg_low,
                        "start_index": seg_start,
                        "end_index": end_idx,
                        "strokes_count": len(seg_strokes),
                    })
                    # 新线段从终结点开始，方向反转
                    seg_start = end_idx
                    current_direction = "down"
                    last_char_val = None
                    continue
                last_char_val = char_val

        else:  # current_direction == "down"
            # 向下线段：只看向上笔作为特征序列
            if s["direction"] == "up":
                char_val = max(s["start_price"], s["end_price"])  # 向上笔高点
                if last_char_val is not None and char_val > last_char_val:
                    # 线段终结：当前向上笔高点 > 前一根向上笔高点
                    # 线段终结于前一根笔（向下笔，即 i-1）
                    end_idx = i - 1
                    seg_strokes = strokes[seg_start:end_idx + 1]
                    seg_high = max(
                        max(ss["start_price"], ss["end_price"]) for ss in seg_strokes
                    )
                    seg_low = min(
                        min(ss["start_price"], ss["end_price"]) for ss in seg_strokes
                    )
                    start_p = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                    end_p = min(strokes[end_idx]["start_price"], strokes[end_idx]["end_price"])
                    segments.append({
                        "direction": "down",
                        "start_price": start_p,
                        "end_price": end_p,
                        "high": seg_high,
                        "low": seg_low,
                        "start_index": seg_start,
                        "end_index": end_idx,
                        "strokes_count": len(seg_strokes),
                    })
                    # 新线段从终结点开始，方向反转
                    seg_start = end_idx
                    current_direction = "up"
                    last_char_val = None
                    continue
                last_char_val = char_val

    # 收尾：如果最后一段至少有 min_strokes 笔，追加
    remaining = strokes[seg_start:]
    if len(remaining) >= min_strokes:
        seg_high = max(max(ss["start_price"], ss["end_price"]) for ss in remaining)
        seg_low = min(min(ss["start_price"], ss["end_price"]) for ss in remaining)
        if current_direction == "up":
            start_p = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
            end_p = max(strokes[-1]["start_price"], strokes[-1]["end_price"])
        else:
            start_p = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
            end_p = min(strokes[-1]["start_price"], strokes[-1]["end_price"])
        segments.append({
            "direction": current_direction,
            "start_price": start_p,
            "end_price": end_p,
            "high": seg_high,
            "low": seg_low,
            "start_index": seg_start,
            "end_index": len(strokes) - 1,
            "strokes_count": len(remaining),
        })

    return segments


def build_zones(items: list[dict], level: str = "segment") -> list[dict]:
    """构建中枢序列。

    当 level=="segment" 且 items 含 start_index/end_index 字段时，用 3 段线段构建中枢；
    否则用旧逻辑（3 笔构建中枢）。
    """
    if len(items) < 3:
        return []

    zones: list[dict[str, Any]] = []
    for i in range(0, len(items) - 2, 1):
        group = items[i:i + 3]

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


def _detect_unilateral(strokes: list[dict]) -> str | None:
    """检测单边走势：大部分笔之间无价格重叠，整体方向明确。

    返回 "单边上涨" / "单边下跌" / None
    """
    if len(strokes) < 6:
        return None

    # 统计相邻笔重叠比例
    total_pairs = len(strokes) - 1
    overlap_count = 0
    for i in range(total_pairs):
        h1 = max(strokes[i]["start_price"], strokes[i]["end_price"])
        l1 = min(strokes[i]["start_price"], strokes[i]["end_price"])
        h2 = max(strokes[i + 1]["start_price"], strokes[i + 1]["end_price"])
        l2 = min(strokes[i + 1]["start_price"], strokes[i + 1]["end_price"])
        if min(h1, h2) > max(l1, l2):
            overlap_count += 1

    # 超过60%的笔对无重叠 → 视为单边
    if overlap_count / total_pairs > 0.4:
        return None  # 重叠太多，不是单边

    # 判断方向：取每笔中点，看首尾差异
    mids = [(max(s["start_price"], s["end_price"]) + min(s["start_price"], s["end_price"])) / 2 for s in strokes]
    if len(mids) < 2:
        return None

    if mids[-1] > mids[0] * 1.05:
        return "单边上涨"
    elif mids[-1] < mids[0] * 0.95:
        return "单边下跌"
    return None


def classify_structure(zones: list[dict], segments: list[dict] | None = None, strokes: list[dict] | None = None) -> dict:
    """走势分类：根据中枢关系和线段数量判断盘整或趋势。

    线段数量要求（标准缠论）：
    - 盘整走势 = 进入段 + 中枢(3段) + 离开段 = 最少 5 段线段
    - 趋势走势 = 进1 + 中枢1(3段) + 离1 + 进2 + 中枢2(3段) + 离2 = 最少 11 段线段

    单边走势：
    - 线段不足但笔之间无重叠 → 单边上涨/单边下跌

    输出结构类型：
    - "盘整" / "上涨趋势" / "下跌趋势" / "单边上涨" / "单边下跌"
    - "线段不足X/Y" — 有线段但不够判定（X=当前线段数，Y=需要数）
    - "无结构" — 连笔都没有
    """
    MIN_SEGMENTS_CONSOLIDATION = 5   # 盘整最少线段数
    MIN_SEGMENTS_TREND = 11          # 趋势最少线段数

    valid_zones = [z for z in zones if z.get("valid")]
    seg_count = len(segments) if segments else 0
    strokes_count = len(strokes) if strokes else 0

    # 笔都没有 → 无结构
    if strokes_count < 3:
        return {
            "structure_type": "无结构",
            "structure_segments_count": seg_count,
            "structure_zones_count": 0,
        }

    # 没有中枢 → 尝试检测单边走势，否则显示线段不足
    if not valid_zones:
        unilateral = _detect_unilateral(strokes or [])
        if unilateral:
            return {
                "structure_type": unilateral,
                "structure_segments_count": seg_count,
                "structure_zones_count": 0,
            }
        if seg_count > 0:
            return {
                "structure_type": f"线段不足{seg_count}/{MIN_SEGMENTS_CONSOLIDATION}",
                "structure_segments_count": seg_count,
                "structure_zones_count": 0,
            }
        return {
            "structure_type": f"线段不足0/{MIN_SEGMENTS_CONSOLIDATION}",
            "structure_segments_count": 0,
            "structure_zones_count": 0,
        }

    # 先判断中枢方向关系
    pair_direction: str | None = None
    zones_trend = "盘整"
    for i in range(1, len(valid_zones)):
        prev = valid_zones[i - 1]
        curr = valid_zones[i]
        if curr["zh_bottom"] > prev["zh_top"]:
            this_dir = "up"
        elif curr["zh_top"] < prev["zh_bottom"]:
            this_dir = "down"
        else:
            zones_trend = "盘整"
            break
        if pair_direction is not None and this_dir != pair_direction:
            zones_trend = "盘整"
            break
        pair_direction = this_dir
        zones_trend = "上涨趋势" if this_dir == "up" else "下跌趋势"

    # 1 个中枢 → 盘整（需 ≥5 段线段）
    if len(valid_zones) == 1:
        if seg_count < MIN_SEGMENTS_CONSOLIDATION:
            return {
                "structure_type": f"线段不足{seg_count}/{MIN_SEGMENTS_CONSOLIDATION}",
                "structure_segments_count": seg_count,
                "structure_zones_count": 1,
            }
        return {
            "structure_type": "盘整",
            "structure_segments_count": seg_count,
            "structure_zones_count": 1,
        }

    # 2+ 个中枢
    if zones_trend in ("上涨趋势", "下跌趋势"):
        if seg_count < MIN_SEGMENTS_TREND:
            return {
                "structure_type": f"线段不足{seg_count}/{MIN_SEGMENTS_TREND}",
                "structure_segments_count": seg_count,
                "structure_zones_count": len(valid_zones),
            }
        return {
            "structure_type": zones_trend,
            "structure_segments_count": seg_count,
            "structure_zones_count": len(valid_zones),
        }

    # 中枢重叠 → 盘整
    if seg_count < MIN_SEGMENTS_CONSOLIDATION:
        return {
            "structure_type": f"线段不足{seg_count}/{MIN_SEGMENTS_CONSOLIDATION}",
            "structure_segments_count": seg_count,
            "structure_zones_count": len(valid_zones),
        }

    return {
        "structure_type": "盘整",
        "structure_segments_count": seg_count,
        "structure_zones_count": len(valid_zones),
    }


def _check_macd_for_2nd_buy(
    bars: list[dict],
    strokes: list[dict],
) -> bool:
    """Check MACD conditions for 2nd buy point.
    
    Condition A: MACD divergence - previous down stroke's MACD histogram is deeper (more negative)
                 than the earlier down stroke, but current is recovering.
    Condition B: MACD trend reversal - recent MACD histogram shows recovery (less negative).
    
    Returns True if either condition is met.
    """
    if not bars or not strokes:
        return False
    
    down_strokes = [s for s in strokes if s["direction"] == "down"]
    if len(down_strokes) < 2:
        return False
    
    # Get MACD histogram values for the bars
    hist_values = [to_float(b.get("macd_histogram")) for b in bars]
    hist_values = [h for h in hist_values if h is not None]
    
    if len(hist_values) < 10:
        return False
    
    # Condition A: Check for MACD divergence between two down strokes
    # Compare the MACD at the end of previous down stroke vs earlier down stroke
    # If previous down stroke has less negative MACD (divergence), it's a buy signal
    recent_hist = hist_values[-5:]  # Last 5 bars
    earlier_hist = hist_values[-10:-5]  # 5 bars before that
    
    if recent_hist and earlier_hist:
        recent_min = min(recent_hist)
        earlier_min = min(earlier_hist)
        # Condition A: MACD divergence - recent minimum is less negative than earlier
        condition_a = recent_min > earlier_min and recent_min < 0
        
        # Condition B: MACD recovery - recent histogram is recovering from negative
        # Check if the last 3 bars show recovery (less negative)
        if len(hist_values) >= 3:
            last_3 = hist_values[-3:]
            condition_b = all(h < 0 for h in last_3) and last_3[-1] > last_3[0]
        else:
            condition_b = False
        
        # Trend filter: reject 2nd buy in bearish alignment
        # Calculate MAs from data BEFORE the last 5 closes, then check if
        # the last 5 closes are all below those MAs (strong downtrend).
        closes = [to_float(b.get("close")) for b in bars]
        closes = [c for c in closes if c is not None]
        if len(closes) >= 25:
            # Use closes before the last 5 to calculate MAs
            ma5 = sum(closes[-10:-5]) / 5
            ma10 = sum(closes[-15:-5]) / 10
            ma20 = sum(closes[-25:-5]) / 20
            last_5_closes = closes[-5:]
            if all(c < ma5 and c < ma10 and c < ma20 for c in last_5_closes):
                return False

        return condition_a or condition_b
    
    return False


def _check_macd_for_2nd_sell(
    bars: list[dict],
    strokes: list[dict],
) -> bool:
    """Check MACD conditions for 2nd sell point (top divergence).

    P0 Fix: 二类卖点需要顶部背离检测，此前误用底部背离标志导致二类卖几乎永不触发。

    Condition A: MACD top divergence - previous up stroke's MACD histogram is weaker (less positive)
                 than the earlier up stroke's peak.
    Condition B: MACD decline - recent MACD histogram shows decline from positive territory.

    Returns True if either condition is met.
    """
    if not bars or not strokes:
        return False

    up_strokes = [s for s in strokes if s["direction"] == "up"]
    if len(up_strokes) < 2:
        return False

    hist_values = [to_float(b.get("macd_histogram")) for b in bars]
    hist_values = [h for h in hist_values if h is not None]

    if len(hist_values) < 10:
        return False

    recent_hist = hist_values[-5:]
    earlier_hist = hist_values[-10:-5]

    if recent_hist and earlier_hist:
        recent_max = max(recent_hist)
        earlier_max = max(earlier_hist)
        # Condition A: MACD top divergence - recent peak is lower (weakening momentum)
        condition_a = recent_max < earlier_max and recent_max > 0

        # Condition B: MACD decline from positive - last 3 bars show weakening
        if len(hist_values) >= 3:
            last_3 = hist_values[-3:]
            condition_b = all(h > 0 for h in last_3) and last_3[-1] < last_3[0]
        else:
            condition_b = False

        # Trend filter: reject 2nd sell in bullish alignment
        closes = [to_float(b.get("close")) for b in bars]
        closes = [c for c in closes if c is not None]
        if len(closes) >= 25:
            ma5 = sum(closes[-10:-5]) / 5
            ma10 = sum(closes[-15:-5]) / 10
            ma20 = sum(closes[-25:-5]) / 20
            last_5_closes = closes[-5:]
            if all(c > ma5 and c > ma10 and c > ma20 for c in last_5_closes):
                return False

        return condition_a or condition_b

    return False


def detect_buy_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    macd_divergence_ok: bool = False,
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
    # Requires MACD divergence/trend confirmation to avoid false positives in downtrends
    if len(strokes) >= 3:
        down_strokes = [s for s in strokes if s["direction"] == "down"]
        up_strokes = [s for s in strokes if s["direction"] == "up"]
        if len(down_strokes) >= 2 and len(up_strokes) >= 1:
            low_a = down_strokes[-2]["end_price"]
            low_b = down_strokes[-1]["end_price"]
            # Find the up stroke between the two down strokes (local up-stroke high)
            up_high = None
            for s in strokes:
                if s["direction"] == "up" and s.get("start_price") is not None and s["start_price"] <= low_a:
                    up_high = s["end_price"]
            if up_high is None:
                up_high = max(s["end_price"] for s in up_strokes)
            if low_b > low_a and low_b < up_high and macd_divergence_ok:
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


def detect_sell_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    macd_divergence_ok: bool = False,
) -> list[dict]:
    """检测缠论卖点（与detect_buy_points对称）。

    一类卖: 向上笔 + MACD 红柱缩短（顶背驰）
    二类卖: 高点降低（up_1 -> down -> up_2 且 high_b < high_a）
    三类卖: 跌破中枢下沿后反弹不回
    """
    sell_points: list[dict[str, Any]] = []

    if not strokes:
        return sell_points

    # 一类卖: 向上笔 + MACD 红柱缩短 (顶背驰信号)
    last_stroke = strokes[-1]
    if last_stroke["direction"] == "up":
        if macd_hist_current is not None and macd_hist_prev is not None and macd_hist_current > 0 and macd_hist_prev > 0:
            if macd_hist_current < macd_hist_prev:
                sell_points.append({
                    "type": "一类卖",
                    "price": round(last_stroke["end_price"], 4),
                    "confidence": 3,
                })
        elif macd_hist_current is not None and macd_hist_current > 0:
            sell_points.append({
                "type": "一类卖",
                "price": round(last_stroke["end_price"], 4),
                "confidence": 2,
            })

    # 二类卖: up_1(high_a) -> down -> up_2(high_b) 且 high_b < high_a
    if len(strokes) >= 3:
        up_strokes = [s for s in strokes if s["direction"] == "up"]
        down_strokes = [s for s in strokes if s["direction"] == "down"]
        if len(up_strokes) >= 2 and len(down_strokes) >= 1:
            high_a = up_strokes[-2]["end_price"]
            high_b = up_strokes[-1]["end_price"]
            # 找两根向上笔之间的向下笔低点
            down_low = None
            for s in strokes:
                if s["direction"] == "down" and s.get("start_price") is not None and s["start_price"] >= high_a:
                    down_low = s["end_price"]
            if down_low is None:
                down_low = min(s["end_price"] for s in down_strokes)
            if high_b < high_a and high_b > down_low and macd_divergence_ok:
                sell_points.append({
                    "type": "二类卖",
                    "price": round(high_b, 4),
                    "confidence": 2,
                })

    # 三类卖: 跌破中枢下沿后反弹不回
    if last_close > 0 and zones:
        last_valid: dict | None = None
        for z in reversed(zones):
            if z["valid"]:
                last_valid = z
                break

        if last_valid is not None:
            zh_bottom = last_valid["zh_bottom"]
            below_pct = (zh_bottom - last_close) / zh_bottom
            if 0 < below_pct <= 0.05:
                sell_points.append({
                    "type": "三类卖",
                    "price": round(last_close, 4),
                    "confidence": 1,
                })

    return sell_points


def detect_divergence(bars: list[dict], strokes: list[dict] | None = None) -> dict:
    result: dict[str, bool] = {"top_divergence": False, "bottom_divergence": False}

    n = len(bars)
    if n < 5:
        return result

    # 全局扫描检测背离（笔不携带MACD数据，跳过笔级别检测）
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
        bars = _calc_macd(bars)

    cleaned = handle_inclusion(bars)
    fractions = find_fractions(cleaned)
    strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE)
    segments = build_segments(strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)
    zones = build_zones(segments if len(segments) >= 3 else strokes,
                         level="segment" if len(segments) >= 3 else "stroke")
    structure = classify_structure(zones, segments, strokes)
    divergence = detect_divergence(bars, strokes)

    # Check MACD divergence for 2nd buy point (bottom divergence)
    macd_divergence_buy = _check_macd_for_2nd_buy(bars, strokes)
    # Check MACD divergence for 2nd sell point (top divergence) — P0 fix
    macd_divergence_sell = _check_macd_for_2nd_sell(bars, strokes)

    buy_points = detect_buy_points(strokes, zones, current, macd_hist_current, macd_hist_prev, macd_divergence_buy)
    sell_points = detect_sell_points(strokes, zones, current, macd_hist_current, macd_hist_prev, macd_divergence_sell)

    strokes_count = len(strokes)
    zones_count = len(zones)

    # 优先用线段投票，不足时 fallback 到笔级别
    if len(segments) >= 3:
        recent3 = [seg["direction"] for seg in segments[-3:]]
        up_count = recent3.count("up")
        down_count = recent3.count("down")
        if up_count >= 2:
            trend_label = "拉升段"
        elif down_count >= 2:
            trend_label = "回调段"
        else:
            trend_label = "震荡段"
    elif strokes_count >= 3:
        # 最近3笔方向多数决：过滤单笔噪音，避免最后一笔小回调误判整段趋势
        recent3 = [s["direction"] for s in strokes[-3:]]
        up_count = recent3.count("up")
        down_count = recent3.count("down")
        if up_count >= 2:
            trend_label = "拉升段"
        elif down_count >= 2:
            trend_label = "回调段"
        else:
            trend_label = "震荡段"
    else:
        trend_label = "数据不足"

    buy_point_text = "、".join([bp["type"] for bp in buy_points]) if buy_points else "无"
    sell_point_text = "、".join([sp["type"] for sp in sell_points]) if sell_points else "无"

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
        "sell_points": sell_points,
        "trend_label": trend_label,
        "buy_point_text": buy_point_text,
        "sell_point_text": sell_point_text,
        "strokes_count": strokes_count,
        "zones_count": zones_count,
        "divergence": divergence,
        "last_valid_zone_last_price": last_valid_zone_last_price,
        "last_valid_zone_first_price": last_valid_zone_first_price,
        "segments": segments,
        "segments_count": len(segments),
        "structure_type": structure["structure_type"],
        "structure_segments_count": structure["structure_segments_count"],
    }


def chanlun_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    return {"chanlun": chanlun_analysis(bars, current, macd_h_curr, macd_h_prev)}
