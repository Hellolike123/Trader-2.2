from __future__ import annotations

from typing import Any

from trader_shared.light_data import to_float
from trader_shared.signal_utils import normalize_signal_id


def unwrap_chan(chan_result: Any) -> dict:
    """剥开 chanlun_strategy 包装层，兼容嵌套与扁平两种形态。

    - 嵌套: {"chanlun": {...分析字段...}}  → 内层 dict
    - 扁平: {"strokes": ..., "buy_points": ...} → 原样返回
    - 非法/空 → {}
    """
    if not isinstance(chan_result, dict):
        return {}
    inner = chan_result.get("chanlun")
    if isinstance(inner, dict):
        return inner
    return chan_result

try:
    from trader_shared.config import (
        CHANLUN_MIN_BARS,
        CHANLUN_MIN_BARS_PER_STROKE,
        CHANLUN_MIN_STROKES_PER_SEGMENT,
        CHAN_MULTILEVEL_ENABLED,
        CHAN_MULTILEVEL_CHUNK,
        CHAN_MULTILEVEL_MIN_BARS,
        CHAN_ZONE_MERGE_ENABLED,
        CHAN_ZONE_MERGE_GAP_PCT,
        CHAN_SIGNAL_ID_ENABLED,
        CHAN_DAILY_TREND_SEGS_HIGH,
        CHAN_DAILY_TREND_SEGS_MID,
        CHAN_DAILY_CONSOL_SEGS_HIGH,
        CHAN_DAILY_CONSOL_SEGS_MID,
        CHAN_WEEKLY_TREND_SEGS_HIGH,
        CHAN_WEEKLY_TREND_SEGS_MID,
        CHAN_WEEKLY_CONSOL_SEGS_HIGH,
        CHAN_WEEKLY_CONSOL_SEGS_MID,
    )
except ImportError:
    CHANLUN_MIN_BARS = 20
    CHANLUN_MIN_BARS_PER_STROKE = 5
    CHANLUN_MIN_STROKES_PER_SEGMENT = 3
    CHAN_MULTILEVEL_ENABLED = True
    CHAN_MULTILEVEL_CHUNK = 5
    CHAN_MULTILEVEL_MIN_BARS = 15
    CHAN_ZONE_MERGE_ENABLED = True
    CHAN_ZONE_MERGE_GAP_PCT = 0.015
    CHAN_SIGNAL_ID_ENABLED = True
    CHAN_DAILY_TREND_SEGS_HIGH = 8
    CHAN_DAILY_TREND_SEGS_MID = 5
    CHAN_DAILY_CONSOL_SEGS_HIGH = 5
    CHAN_DAILY_CONSOL_SEGS_MID = 3
    CHAN_WEEKLY_TREND_SEGS_HIGH = 5
    CHAN_WEEKLY_TREND_SEGS_MID = 3
    CHAN_WEEKLY_CONSOL_SEGS_HIGH = 3
    CHAN_WEEKLY_CONSOL_SEGS_MID = 2


def _calc_macd(bars: list[dict]) -> list[dict]:
    """计算 MACD histogram 并写入 bars。使用 indicator_math.calc_macd_series 统一实现。"""
    from trader_shared.indicator_math import calc_macd_series

    bars = [dict(b) for b in bars]
    closes = [to_float(b.get("close")) for b in bars]
    result = calc_macd_series(closes)

    for i, bar in enumerate(bars):
        bar["macd_histogram"] = result["histogram"][i] if result["histogram"][i] is not None else 0.0

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
                new_high = round(max(h_curr, h_prev), 4)
                new_low = round(max(l_curr, l_prev), 4)
            elif direction == "down":
                new_high = round(min(h_curr, h_prev), 4)
                new_low = round(min(l_curr, l_prev), 4)
            else:
                new_high = round(max(h_curr, h_prev), 4)
                new_low = round(min(l_curr, l_prev), 4)

            curr["high"] = new_high
            curr["low"] = new_low

            # 重算 open/close（与 czsc 对齐）：涨 → close=high, open=low；跌 → open=high, close=low
            o = to_float(curr.get("open"))
            c = to_float(curr.get("close"))
            if o is not None and c is not None:
                if c > o:
                    curr["close"] = new_high
                    curr["open"] = new_low
                else:
                    curr["open"] = new_high
                    curr["close"] = new_low

            # 累加 volume/amount（与 czsc 对齐）
            pv = to_float(prev.get("volume")) or to_float(prev.get("vol")) or 0
            cv = to_float(curr.get("volume")) or to_float(curr.get("vol")) or 0
            if pv or cv:
                if "volume" in curr:
                    curr["volume"] = round(pv + cv, 4)
                if "vol" in curr:
                    curr["vol"] = round(pv + cv, 4)
            pa = to_float(prev.get("amount")) or 0
            ca = to_float(curr.get("amount")) or 0
            if pa or ca:
                curr["amount"] = round(pa + ca, 4)

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

        # 双侧验证（与 czsc check_fx 一致）：
        # 顶分型：high 和 low 都高于左右两侧
        # 底分型：high 和 low 都低于左右两侧
        is_top = (h_mid > h_left and h_mid > h_right
                  and l_mid > l_left and l_mid > l_right)
        is_bottom = (l_mid < l_left and l_mid < l_right
                     and h_mid < h_left and h_mid < h_right)

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


def _aggregate_bars(bars: list[dict], chunk: int = 5) -> list[dict]:
    """将 bars 按 chunk 聚合为粗粒度 K 线（用于模拟上级别走势，区间套思想）。

    每 chunk 根合成 1 根：open=首根开(缺省用首根收), high=最高, low=最低, close=末根收。
    仅保留分析所需的 OHLC / date / macd_histogram（取末根）。
    """
    if chunk <= 1 or len(bars) < chunk:
        return [dict(b) for b in bars]
    coarse: list[dict[str, Any]] = []
    i = 0
    n = len(bars)
    while i + chunk <= n:
        group = bars[i:i + chunk]
        open_p = to_float(group[0].get("open"))
        if open_p is None:
            open_p = to_float(group[0].get("close"))
        highs = [to_float(b.get("high")) for b in group]
        lows = [to_float(b.get("low")) for b in group]
        close_p = to_float(group[-1].get("close"))
        highs = [h for h in highs if h is not None]
        lows = [l for l in lows if l is not None]
        if open_p is None or not highs or not lows or close_p is None:
            i += chunk
            continue
        coarse.append({
            "open": round(open_p, 4),
            "high": round(max(highs), 4),
            "low": round(min(lows), 4),
            "close": round(close_p, 4),
            "date": group[-1].get("date"),
            "macd_histogram": group[-1].get("macd_histogram"),
        })
        i += chunk
    return coarse


def _higher_level_trend(bars: list[dict], chunk: int = 5, weekly_bars: list[dict] | None = None) -> dict:
    """基于粗粒度 K 线估计上级别趋势方向（区间套，轻量自包含实现）。

    优先使用真实周线（weekly_bars），不可用时回退到日线 chunk 聚合。
    返回 {"trend": "up"|"down"|"sideways"|None, "confidence": float, "segments_count": int}。
    - 数据不足 CHAN_MULTILEVEL_MIN_BARS 或无足够线段 → trend=None, confidence=0
    - 取末 3 段多数决；confidence = 同向段数 / 3（需 >=3 段才置信）
    """
    result: dict[str, Any] = {"trend": None, "confidence": 0.0, "segments_count": 0}

    # 优先用真实周线（比 chunk 聚合准）
    if weekly_bars and len(weekly_bars) >= CHAN_MULTILEVEL_MIN_BARS:
        cleaned = handle_inclusion(weekly_bars)
        fractions = find_fractions(cleaned)
        strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE)
        segments = build_segments(strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)
        if len(segments) >= 3:
            recent3 = [seg["direction"] for seg in segments[-3:]]
            up = recent3.count("up")
            down = recent3.count("down")
            result["segments_count"] = len(segments)
            if up >= 2:
                result["trend"] = "up"
                result["confidence"] = up / 3.0
            elif down >= 2:
                result["trend"] = "down"
                result["confidence"] = down / 3.0
            else:
                result["trend"] = "sideways"
                result["confidence"] = 0.5
            return result

    # 回退到 chunk 聚合
    if not bars or len(bars) < CHAN_MULTILEVEL_MIN_BARS:
        return result
    coarse = _aggregate_bars(bars, chunk=chunk)
    if len(coarse) < CHAN_MULTILEVEL_MIN_BARS:
        return result
    cleaned = handle_inclusion(coarse)
    fractions = find_fractions(cleaned)
    strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE)
    segments = build_segments(strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)
    if len(segments) < 3:
        result["segments_count"] = len(segments)
        return result
    recent3 = [seg["direction"] for seg in segments[-3:]]
    up = recent3.count("up")
    down = recent3.count("down")
    result["segments_count"] = len(segments)
    if up >= 2:
        result["trend"] = "up"
        result["confidence"] = up / 3.0
    elif down >= 2:
        result["trend"] = "down"
        result["confidence"] = down / 3.0
    else:
        result["trend"] = "sideways"
        result["confidence"] = 0.5
    return result


def build_strokes(fractions: list[dict], min_bars_per_stroke: int = 5, bars: list[dict] | None = None) -> list[dict]:
    """由分型序列构建笔。

    成笔条件：`end.index - start.index >= min_bars_per_stroke - 1`，且方向与上一笔交替。
    连续同向分型取极值（顶取更高 high，底取更低 low）。

    P0：反向分型距离不够时跳过，保留 start 继续找。
    P1：扫描所有合格反向分型，选最极端的（顶取 high 最大，底取 low 最小）作为笔端点。
    P4：返回 power_price（绝对价差）和 length（K 线根数）；传入 bars 时额外计算 power_volume。
    """
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

        # P1: 在转折点（同向不更极端的分型）之前的范围内，
        # 扫描所有合格反向分型，选最极端的作为笔端点
        best_end = None
        best_j = None
        while j < num:
            f = fractions[j]

            if f["type"] == start["type"]:
                # 同向分型 → 转折点，停止扫描
                break

            # 反向分型：距离合格则跟踪最极端候选
            if f["index"] - start["index"] >= min_bars_per_stroke - 1:
                if best_end is None:
                    best_end = f
                    best_j = j
                elif start["type"] == "bottom" and f["high"] > best_end["high"]:
                    best_end = f
                    best_j = j
                elif start["type"] == "top" and f["low"] < best_end["low"]:
                    best_end = f
                    best_j = j

            j += 1

        # 扫描结束，用最极端候选成笔
        if best_end is not None:
            direction = "up" if start["type"] == "bottom" else "down"

            # 强制交替：新笔方向必须与上一笔相反
            if last_direction is not None and direction == last_direction:
                i = best_j
                continue

            sp = start["low"] if start["type"] == "bottom" else start["high"]
            ep = best_end["high"] if best_end["type"] == "top" else best_end["low"]
            si = start["index"]
            ei = best_end["index"]
            stroke = {
                "start_type": start["type"],
                "start_price": sp,
                "end_type": best_end["type"],
                "end_price": ep,
                "direction": direction,
                "start_index": si,
                "end_index": ei,
                "power_price": round(abs(ep - sp), 4),
                "length": ei - si,
            }
            # P4: 传入 bars 时计算笔内成交量之和（中间 K 线）
            if bars and ei > si + 1 and ei <= len(bars):
                pv = 0.0
                for bi in range(si + 1, ei):
                    v = to_float(bars[bi].get("volume")) or to_float(bars[bi].get("vol")) or 0
                    pv += v
                stroke["power_volume"] = round(pv, 4)
            strokes.append(stroke)
            last_direction = direction
            i = best_j
        else:
            # 从当前 start 无法成笔（后续无合格反向分型），推进起点防死循环
            i += 1

    return strokes


def build_segments(strokes: list[dict], min_strokes: int = 3) -> list[dict]:
    """将笔序列构建为线段序列。

    线段是最小可递归走势单元，由至少3笔构成。
    使用特征序列三分型（含包含处理）判断线段终结：
    - 向上线段：取所有向下笔构成特征序列；至少 3 个特征元素，
      且最后三根形成底分型（mid.low < left.low and mid.low < right.low）时终结
    - 向下线段：取所有向上笔构成特征序列；至少 3 个特征元素，
      且最后三根形成顶分型（mid.high > left.high and mid.high > right.high）时终结
    - 默认只比 low（底分型）/ high（顶分型），与 K 线分型侧重点一致

    包含处理规则（与 K 线包含一致）：
    - 两根特征序列元素重叠时，按方向合并
    - 趋势向上：取 max(high), max(low)
    - 趋势向下：取 min(high), min(low)
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
        # P6: 第 3 笔未确认方向，根据首尾笔端点推断；若仍不明确则推迟
        first_end = strokes[seg_start]["end_price"]
        third_end = strokes[seg_start + 2]["end_price"]
        if third_end > first_end:
            current_direction = "up"
        elif third_end < first_end:
            current_direction = "down"
        else:
            current_direction = strokes[seg_start]["direction"]

    segments: list[dict[str, Any]] = []
    # 特征序列缓存：包含处理后的元素列表，每个元素有 high/low
    char_seq: list[dict[str, float]] = []
    char_direction: str | None = None  # 特征序列当前趋势方向

    def _merge_char_element(
        seq: list[dict[str, float]], new_h: float, new_l: float
    ) -> list[dict[str, float]]:
        """对特征序列做包含处理：如果新元素与最后一个重叠，按方向合并。"""
        if not seq:
            return [{"high": new_h, "low": new_l}]

        last = seq[-1]
        # 检查是否包含（重叠）
        contains = (new_h >= last["high"] and new_l <= last["low"]) or \
                   (new_h <= last["high"] and new_l >= last["low"])
        if not contains:
            return seq + [{"high": new_h, "low": new_l}]

        # 包含处理：按特征序列趋势方向合并
        nonlocal char_direction
        if char_direction == "up":
            # 趋势向上：取 max(high), max(low)
            merged = {"high": max(new_h, last["high"]), "low": max(new_l, last["low"])}
        elif char_direction == "down":
            # 趋势向下：取 min(high), min(low)
            merged = {"high": min(new_h, last["high"]), "low": min(new_l, last["low"])}
        else:
            # 方向未定：取 max(high), min(low)
            merged = {"high": max(new_h, last["high"]), "low": min(new_l, last["low"])}
        seq[-1] = merged
        return seq

    for i in range(seg_start + 1, len(strokes)):
        s = strokes[i]

        if current_direction == "up":
            # 向上线段：只看向下笔作为特征序列
            if s["direction"] == "down":
                char_h = max(s["start_price"], s["end_price"])
                char_l = min(s["start_price"], s["end_price"])

                # 确定特征序列趋势方向
                if char_seq:
                    last_h = char_seq[-1]["high"]
                    last_l = char_seq[-1]["low"]
                    if char_h > last_h and char_l > last_l:
                        char_direction = "up"
                    elif char_h < last_h and char_l < last_l:
                        char_direction = "down"

                # 包含处理
                char_seq = _merge_char_element(char_seq, char_h, char_l)

                # 特征序列三分型终结：至少 3 个特征元素，最后三根底分型
                # （默认只比 low，与 K 线底分型侧重点一致）
                if len(char_seq) >= 3:
                    left, mid, right = char_seq[-3], char_seq[-2], char_seq[-1]
                    if mid["low"] < left["low"] and mid["low"] < right["low"]:
                        end_idx = i - 1
                        seg_strokes = strokes[seg_start:end_idx + 1]
                        seg_high = max(max(ss["start_price"], ss["end_price"]) for ss in seg_strokes)
                        seg_low = min(min(ss["start_price"], ss["end_price"]) for ss in seg_strokes)
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
                        seg_start = end_idx
                        current_direction = "down"
                        char_seq = []
                        char_direction = None
                        continue

        else:  # current_direction == "down"
            # 向下线段：只看向上笔作为特征序列
            if s["direction"] == "up":
                char_h = max(s["start_price"], s["end_price"])
                char_l = min(s["start_price"], s["end_price"])

                # 确定特征序列趋势方向
                if char_seq:
                    last_h = char_seq[-1]["high"]
                    last_l = char_seq[-1]["low"]
                    if char_h > last_h and char_l > last_l:
                        char_direction = "up"
                    elif char_h < last_h and char_l < last_l:
                        char_direction = "down"

                # 包含处理
                char_seq = _merge_char_element(char_seq, char_h, char_l)

                # 特征序列三分型终结：至少 3 个特征元素，最后三根顶分型
                # （默认只比 high，与 K 线顶分型侧重点一致）
                if len(char_seq) >= 3:
                    left, mid, right = char_seq[-3], char_seq[-2], char_seq[-1]
                    if mid["high"] > left["high"] and mid["high"] > right["high"]:
                        end_idx = i - 1
                        seg_strokes = strokes[seg_start:end_idx + 1]
                        seg_high = max(max(ss["start_price"], ss["end_price"]) for ss in seg_strokes)
                        seg_low = min(min(ss["start_price"], ss["end_price"]) for ss in seg_strokes)
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
                        seg_start = end_idx
                        current_direction = "up"
                        char_seq = []
                        char_direction = None
                        continue

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


def _merge_zones(raw_zones: list[dict], gap_pct: float) -> list[dict]:
    """将重叠的滑动窗口中枢合并为 consolidated pivot。

    合并条件（P0 安全修复）：**仅当两中枢价格区间真正重叠**时才合并
    （`z.top > last.bottom and z.bottom < last.top`）。

    纯 gap（不重叠）不再合并——即使间距 < gap_pct。旧逻辑用交集合并
    近邻非重叠中枢时会出现 `zh_top < zh_bottom` 的非法中枢。

    gap_pct 参数保留以兼容调用方（CHAN_ZONE_MERGE_GAP_PCT），当前已禁用 gap 合并，
    仅作未来扩展预留，本函数内不消费。

    合并后取交集：zh_top = min(tops), zh_bottom = max(bottoms)，并保证 top > bottom；
    成员原始中枢记录到 members。
    """
    # gap_pct 暂不使用（禁用 gap 合并，避免非法中枢）
    _ = gap_pct

    merged: list[dict[str, Any]] = []
    for z in raw_zones:
        if not merged:
            merged.append({
                "zh_top": z["zh_top"], "zh_bottom": z["zh_bottom"],
                "zh_center": z["zh_center"], "members": [z], "valid": True,
            })
            continue
        last = merged[-1]
        # 仅真正价格重叠才合并
        overlap = z["zh_top"] > last["zh_bottom"] and z["zh_bottom"] < last["zh_top"]
        if overlap:
            new_top = min(last["zh_top"], z["zh_top"])
            new_bottom = max(last["zh_bottom"], z["zh_bottom"])
            # 交集须仍为合法区间；否则保持独立，避免 top <= bottom
            if new_top > new_bottom:
                last["zh_top"] = new_top
                last["zh_bottom"] = new_bottom
                last["zh_center"] = round((last["zh_top"] + last["zh_bottom"]) / 2, 4)
                last["members"].append(z)
            else:
                merged.append({
                    "zh_top": z["zh_top"], "zh_bottom": z["zh_bottom"],
                    "zh_center": z["zh_center"], "members": [z], "valid": True,
                })
        else:
            merged.append({
                "zh_top": z["zh_top"], "zh_bottom": z["zh_bottom"],
                "zh_center": z["zh_center"], "members": [z], "valid": True,
            })
    return merged


def build_zones(items: list[dict], level: str = "segment", merge: bool = True) -> list[dict]:
    """构建中枢序列。

    当 level=="segment" 且 items 含 start_index/end_index 字段时，用 3 段线段构建中枢；
    否则用旧逻辑（3 笔构建中枢）。
    merge=True（且 CHAN_ZONE_MERGE_ENABLED）时，将**价格重叠**的滑动窗口中枢
    合并为 consolidated pivot（P0：纯 gap 不再合并），减少中枢数量膨胀。
    """
    if len(items) < 3:
        return []

    raw: list[dict[str, Any]] = []
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
            raw.append({
                "zh_top": round(zh_top, 4),
                "zh_bottom": round(zh_bottom, 4),
                "zh_center": round((zh_top + zh_bottom) / 2, 4),
                "strokes": group,
                "valid": valid,
            })

    if merge and CHAN_ZONE_MERGE_ENABLED:
        return _merge_zones(raw, CHAN_ZONE_MERGE_GAP_PCT)
    return raw


def _has_entry_exit_segments(pivot: dict, segments: list[dict] | None) -> bool:
    """验证中枢存在「进入段 + 离开段」结构（盘整成立的拓扑条件）。

    从合并中枢的成员原始中枢中提取笔/线段索引区间，判断是否有线段在中枢之前结束、
    且有线段在中枢之后开始。成员无索引信息（如手工构造测试数据）时返回 False，
    调用方应回退到线段数量门槛。
    """
    if not segments:
        return False
    members = pivot.get("members") or [pivot]
    item_indices: list[tuple[int, int]] = []
    for m in members:
        for s in m.get("strokes", []):
            if isinstance(s, dict) and "start_index" in s and "end_index" in s:
                item_indices.append((s["start_index"], s["end_index"]))
    if not item_indices:
        return False
    min_idx = min(i for i, _ in item_indices)
    max_idx = max(j for _, j in item_indices)
    has_before = any(isinstance(s, dict) and s.get("end_index", -1) < min_idx for s in segments)
    has_after = any(isinstance(s, dict) and s.get("start_index", 1 << 30) > max_idx for s in segments)
    return has_before and has_after


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


def _structure_conf_thresholds(timeframe: str) -> dict[str, int]:
    """日线 / 周线 structure_confidence 段数门槛（禁止共用 11 硬失败）。"""
    tf = (timeframe or "daily").lower()
    if tf in ("weekly", "week", "w"):
        return {
            "trend_high": CHAN_WEEKLY_TREND_SEGS_HIGH,
            "trend_mid": CHAN_WEEKLY_TREND_SEGS_MID,
            "consol_high": CHAN_WEEKLY_CONSOL_SEGS_HIGH,
            "consol_mid": CHAN_WEEKLY_CONSOL_SEGS_MID,
        }
    return {
        "trend_high": CHAN_DAILY_TREND_SEGS_HIGH,
        "trend_mid": CHAN_DAILY_TREND_SEGS_MID,
        "consol_high": CHAN_DAILY_CONSOL_SEGS_HIGH,
        "consol_mid": CHAN_DAILY_CONSOL_SEGS_MID,
    }


def _structure_confidence(
    structure_type: str,
    seg_count: int,
    timeframe: str = "daily",
) -> str:
    """段数只影响证据强弱 high|mid|low，不改主状态名。"""
    if structure_type == "无结构":
        return "low"
    th = _structure_conf_thresholds(timeframe)
    if structure_type in ("上涨趋势", "下跌趋势", "单边上涨", "单边下跌"):
        high, mid = th["trend_high"], th["trend_mid"]
    else:
        # 盘整（含 0 中枢弱盘整）
        high, mid = th["consol_high"], th["consol_mid"]
    if seg_count >= high:
        return "high"
    if seg_count >= mid:
        return "mid"
    return "low"


def classify_structure(
    zones: list[dict],
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
    timeframe: str = "daily",
) -> dict:
    """走势分类：主状态由中枢拓扑决定；段数只影响 structure_confidence。

    拓扑规则（中枢合并版）：
    - strokes < 3 → 无结构
    - 0 个合并中枢 → 单边 / 有线段则盘整 / 无结构
    - 1 个合并中枢 → 盘整
    - 2+ 同向不重叠中枢 → 上涨趋势 / 下跌趋势（即使段数只有 4～6）
    - 2+ 重叠/方向混乱 → 盘整

    主状态 structure_type 仅允许：
    无结构 / 单边上涨 / 单边下跌 / 盘整 / 上涨趋势 / 下跌趋势
    禁止返回「线段不足n/m」。

    新增字段：structure_confidence (high|mid|low), structure_evidence
    兼容字段：structure_type, structure_segments_count, structure_zones_count,
              merged_zones, pivot_count
    """
    valid_zones = [z for z in zones if z.get("valid")]
    seg_count = len(segments) if segments else 0
    strokes_count = len(strokes) if strokes else 0
    pivot_count = len(valid_zones)

    base: dict[str, Any] = {
        "structure_segments_count": seg_count,
        "structure_zones_count": len(zones),
        "merged_zones": valid_zones,
        "pivot_count": pivot_count,
        "structure_evidence": f"segments={seg_count},pivots={pivot_count}",
    }

    def _ok(st: str) -> dict:
        conf = _structure_confidence(st, seg_count, timeframe=timeframe)
        return {**base, "structure_type": st, "structure_confidence": conf}

    if strokes_count < 3:
        return _ok("无结构")

    if not valid_zones:
        unilateral = _detect_unilateral(strokes or [])
        if unilateral:
            return _ok(unilateral)
        if seg_count > 0:
            return _ok("盘整")
        return _ok("无结构")

    # 判断中枢方向关系（拓扑：同向不重叠→趋势，重叠→盘整）
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

    # 1 个中枢：有中枢即盘整
    if len(valid_zones) == 1:
        return _ok("盘整")

    # 2+ 同向不重叠中枢 → 直接趋势（段数只调 conf）
    if zones_trend in ("上涨趋势", "下跌趋势"):
        return _ok(zones_trend)

    # 2+ 重叠/混乱 → 盘整
    return _ok("盘整")


def _stroke_macd_area(bars: list[dict] | None, stroke: dict, side: str) -> float | None:
    """对 stroke 的 [start_index, end_index] 区间求 MACD histogram 面积。

    P1 定义：笔级力度用柱面积，而非全图最后 N 根。
    side='neg': 只累加负柱（底背驰用，返回负值或 0）
    side='pos': 只累加正柱（顶背驰用）
    无 index / 无数据 → None（手工 stroke 可能无 index，调用方须容错）

    契约：bars 必须与 start_index/end_index 同一坐标系。
    chanlun_analysis 传入的是 inclusion 后并已 _calc_macd 重算的 cleaned
    （禁止用 raw 日线 + 笔 index，否则面积会错位）。
    """
    if not bars or not stroke:
        return None
    start_idx = stroke.get("start_index")
    end_idx = stroke.get("end_index")
    if start_idx is None or end_idx is None:
        return None
    lo = min(int(start_idx), int(end_idx))
    hi = max(int(start_idx), int(end_idx))
    lo = max(0, lo)
    hi = min(len(bars) - 1, hi)
    if lo > hi:
        return None

    area = 0.0
    signed_count = 0  # 必须有同侧真实柱；预热 0.0 / 反号柱不算有效力度
    for i in range(lo, hi + 1):
        h = to_float(bars[i].get("macd_histogram"))
        if h is None:
            continue
        if side == "neg" and h < 0:
            area += h
            signed_count += 1
        elif side == "pos" and h > 0:
            area += h
            signed_count += 1
    if signed_count == 0:
        return None
    return area


def _stroke_force_weaker(
    area_prev: float | None,
    area_curr: float | None,
    direction: str,
) -> bool:
    """笔级力度更弱判定（真·背驰）。

    向下背驰：|area_curr| < |area_prev|（负面积绝对值更小=力度更弱）
    向上背驰：area_curr < area_prev（正面积更小）
    """
    if area_prev is None or area_curr is None:
        return False
    if direction == "down":
        return abs(area_curr) < abs(area_prev)
    if direction == "up":
        return area_curr < area_prev
    return False


def _stroke_force_weaker_multi(
    prev: dict,
    curr: dict,
    area_prev: float | None,
    area_curr: float | None,
    direction: str,
) -> bool:
    """多维力度衰减判定（P5）。

    综合三个维度判断后笔是否弱于前笔：
    1. MACD 面积（area）
    2. 价格力度（power_price）
    3. 持续时间（length）

    至少 2 个维度显示衰减 → 判定为更弱。
    """
    votes = 0
    total = 0

    # 维度 1：MACD 面积
    if area_prev is not None and area_curr is not None:
        total += 1
        if direction == "down":
            if abs(area_curr) < abs(area_prev):
                votes += 1
        elif direction == "up":
            if area_curr < area_prev:
                votes += 1

    # 维度 2：价格力度
    pp_prev = prev.get("power_price")
    pp_curr = curr.get("power_price")
    if pp_prev is not None and pp_curr is not None and pp_prev > 0:
        total += 1
        if pp_curr < pp_prev:
            votes += 1

    # 维度 3：持续时间（length）
    ln_prev = prev.get("length")
    ln_curr = curr.get("length")
    if ln_prev is not None and ln_curr is not None:
        total += 1
        if ln_curr < ln_prev:
            votes += 1

    # 至少 2 个维度衰减（或仅 1 个维度但 MACD 面积明确衰减）
    if total == 0:
        return False
    if votes >= 2:
        return True
    # 单维度但 MACD 面积明确衰减时也算（保持向后兼容）
    if votes == 1 and total == 1 and area_prev is not None and area_curr is not None:
        return _stroke_force_weaker(area_prev, area_curr, direction)
    return False


def _stroke_force_not_much_stronger(
    area_prev: float | None,
    area_curr: float | None,
    direction: str,
    tol: float = 1.05,
) -> bool:
    """二类确认：后笔力度不显著强于前笔（允许约 5% 容差）。

    向下：|area_curr| <= |area_prev| * tol
    向上：area_curr <= area_prev * tol
    """
    if area_prev is None or area_curr is None:
        return False
    if direction == "down":
        return abs(area_curr) <= abs(area_prev) * tol
    if direction == "up":
        return area_curr <= area_prev * tol
    return False


def _check_macd_for_2nd_buy(
    bars: list[dict],
    strokes: list[dict],
) -> bool:
    """二类买 MACD 确认（P1：优先笔级负面积对比）。

    Condition A: 最后两段 down 笔负面积，后笔力度不显著强于前笔
                 （|area_curr| <= |area_prev| * 1.05）
    Condition B: 近端柱状恢复（全序列末几根绿柱回升，无 index 时的补充）
    工程风控：MA 空头排列硬过滤
    """
    if not bars or not strokes:
        return False

    down_strokes = [s for s in strokes if s["direction"] == "down"]
    if len(down_strokes) < 2:
        return False

    # Condition A: 笔级 MACD 负面积对比（必须使用 down_strokes）
    area_prev = _stroke_macd_area(bars, down_strokes[-2], "neg")
    area_curr = _stroke_macd_area(bars, down_strokes[-1], "neg")
    condition_a = _stroke_force_not_much_stronger(area_prev, area_curr, "down")

    # Condition B: 近端柱状恢复（无笔 index / 面积时的补充条件）
    hist_values = [to_float(b.get("macd_histogram")) for b in bars]
    hist_values = [h for h in hist_values if h is not None]
    condition_b = False
    if len(hist_values) >= 3:
        last_3 = hist_values[-3:]
        condition_b = all(h < 0 for h in last_3) and last_3[-1] > last_3[0]
    # 无 index 时也可用全图近端 min 对比作为 area 的粗替代
    if not condition_a and area_prev is None and area_curr is None and len(hist_values) >= 10:
        recent_hist = hist_values[-5:]
        earlier_hist = hist_values[-10:-5]
        if recent_hist and earlier_hist:
            recent_min = min(recent_hist)
            earlier_min = min(earlier_hist)
            condition_a = recent_min > earlier_min and recent_min < 0

    if not (condition_a or condition_b):
        return False

    # Trend filter: reject 2nd buy in strong bearish alignment
    closes = [to_float(b.get("close")) for b in bars]
    closes = [c for c in closes if c is not None]
    if len(closes) >= 25:
        ma5 = sum(closes[-10:-5]) / 5
        ma10 = sum(closes[-15:-5]) / 10
        ma20 = sum(closes[-25:-5]) / 20
        last_5_closes = closes[-5:]
        if all(c < ma5 and c < ma10 and c < ma20 for c in last_5_closes):
            return False

    return True


def _check_macd_for_2nd_sell(
    bars: list[dict],
    strokes: list[dict],
) -> bool:
    """二类卖 MACD 确认（P1：优先笔级正面积对比；P0 已修正为顶背驰侧）。

    Condition A: 最后两段 up 笔正面积，后笔力度不显著强于前笔
    Condition B: 近端红柱回落
    工程风控：MA 多头排列硬过滤
    """
    if not bars or not strokes:
        return False

    up_strokes = [s for s in strokes if s["direction"] == "up"]
    if len(up_strokes) < 2:
        return False

    area_prev = _stroke_macd_area(bars, up_strokes[-2], "pos")
    area_curr = _stroke_macd_area(bars, up_strokes[-1], "pos")
    condition_a = _stroke_force_not_much_stronger(area_prev, area_curr, "up")

    hist_values = [to_float(b.get("macd_histogram")) for b in bars]
    hist_values = [h for h in hist_values if h is not None]
    condition_b = False
    if len(hist_values) >= 3:
        last_3 = hist_values[-3:]
        condition_b = all(h > 0 for h in last_3) and last_3[-1] < last_3[0]
    if not condition_a and area_prev is None and area_curr is None and len(hist_values) >= 10:
        recent_hist = hist_values[-5:]
        earlier_hist = hist_values[-10:-5]
        if recent_hist and earlier_hist:
            recent_max = max(recent_hist)
            earlier_max = max(earlier_hist)
            condition_a = recent_max < earlier_max and recent_max > 0

    if not (condition_a or condition_b):
        return False

    closes = [to_float(b.get("close")) for b in bars]
    closes = [c for c in closes if c is not None]
    if len(closes) >= 25:
        ma5 = sum(closes[-10:-5]) / 5
        ma10 = sum(closes[-15:-5]) / 10
        ma20 = sum(closes[-25:-5]) / 20
        last_5_closes = closes[-5:]
        if all(c > ma5 and c > ma10 and c > ma20 for c in last_5_closes):
            return False

    return True


# 三类买卖点：离开中枢后允许的最大偏离（防止远离中枢仍叫三买/三卖）
_THIRD_POINT_MAX_LEAVE_PCT = 0.15


def detect_buy_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    macd_divergence_ok: bool = False,
    bars: list[dict] | None = None,
) -> list[dict]:
    """检测缠论买点（P1 定义纠偏）。

    一类买: 最后一笔 down + valid 中枢 + 至少两段 down + 笔级底背驰
    二类买: down_a→up→down_b 且 low_b>low_a 且 low_b<up_high + 笔级力度/MACD 确认
    三类买: 离开 ZG 之后出现回抽 down 且 end>=ZG；未回踩不报（取消 0~2% 窄窗，上限 15%）
    bars 须为与 stroke index 对齐的序列（chanlun_analysis 传入 handle_inclusion 后的 cleaned）。
    """
    buy_points: list[dict[str, Any]] = []

    if not strokes:
        return buy_points

    # ── 辅助过滤器（增强项，不替代中枢+背驰主条件）──
    def _volume_confirm(idx: int, threshold: float = 1.5) -> bool:
        """当日成交量 > 近20日均量 × threshold；数据不足放行"""
        if not bars or idx < 20:
            return True
        recent = bars[max(0, idx - 20):idx]
        avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / len(recent)
        curr_vol = to_float(bars[idx].get("volume")) or 0
        return avg_vol > 0 and curr_vol >= avg_vol * threshold

    valid_zones = [z for z in zones if z.get("valid")]
    last_stroke = strokes[-1]
    down_strokes = [s for s in strokes if s["direction"] == "down"]
    up_strokes = [s for s in strokes if s["direction"] == "up"]

    # ── P1 一类买：结构（中枢 + 两 down）+ 笔级底背驰 ──
    # 删除旧「仅 MACD 为负 + 放量 + MA20」无中枢假一类
    if last_stroke["direction"] == "down" and valid_zones and len(down_strokes) >= 2:
        prev_down = down_strokes[-2]
        curr_down = down_strokes[-1]
        price_new_low = curr_down["end_price"] <= prev_down["end_price"]
        if price_new_low:
            area_prev = _stroke_macd_area(bars, prev_down, "neg")
            area_curr = _stroke_macd_area(bars, curr_down, "neg")
            if area_prev is not None and area_curr is not None:
                # 完整笔级背驰 → confidence 3
                if _stroke_force_weaker(area_prev, area_curr, "down"):
                    buy_points.append({
                        "type": "一类买",
                        "price": round(curr_down["end_price"], 4),
                        "confidence": 3,
                    })
            else:
                # P7: 无 index / 无法算面积：fallback 要求至少 3 根连续负柱回升
                bar_ok = False
                if bars and len(bars) >= 3:
                    h_vals = [to_float(b.get("macd_histogram")) for b in bars[-3:]]
                    h_vals = [h for h in h_vals if h is not None]
                    bar_ok = (
                        len(h_vals) == 3
                        and all(h < 0 for h in h_vals)
                        and h_vals[2] > h_vals[1] > h_vals[0]
                    )
                elif macd_hist_current is not None and macd_hist_prev is not None:
                    # 无 bars 时回退到 2 柱检查（兼容旧调用）
                    bar_ok = (
                        macd_hist_current < 0
                        and macd_hist_prev < 0
                        and macd_hist_current > macd_hist_prev
                    )
                if bar_ok:
                    buy_points.append({
                        "type": "一类买",
                        "price": round(curr_down["end_price"], 4),
                        "confidence": 1,
                    })

    # ── P1 二类买：回抽不破前低；要求末笔即为该回抽 down（防粘滞）──
    if (
        len(strokes) >= 3
        and len(down_strokes) >= 2
        and len(up_strokes) >= 1
        and last_stroke["direction"] == "down"
    ):
        low_a = down_strokes[-2]["end_price"]
        low_b = down_strokes[-1]["end_price"]
        idx_a = -1
        idx_b = -1
        for i, s in enumerate(strokes):
            if s is down_strokes[-2]:
                idx_a = i
            if s is down_strokes[-1]:
                idx_b = i
        # 末笔必须是最后一根 down
        if idx_b == len(strokes) - 1:
            up_high = None
            if idx_a >= 0 and idx_b > idx_a:
                for s in strokes[idx_a + 1:idx_b]:
                    if s["direction"] == "up" and s.get("end_price") is not None:
                        if up_high is None or s["end_price"] > up_high:
                            up_high = s["end_price"]
            if up_high is None:
                # P8: 两笔之间无同向笔 → 结构不成立，跳过二类买
                pass
            else:
                structure_ok = low_b > low_a and low_b < up_high
                if structure_ok:
                    area_prev = _stroke_macd_area(bars, down_strokes[-2], "neg")
                    area_curr = _stroke_macd_area(bars, down_strokes[-1], "neg")
                    area_ok = _stroke_force_not_much_stronger(area_prev, area_curr, "down")
                    if area_ok or macd_divergence_ok:
                        buy_points.append({
                            "type": "二类买",
                            "price": round(low_b, 4),
                            "confidence": 2,
                        })

    # ── P1/P2 三类买：离开中枢后回踩不入；回抽须为近端（末 2 笔内）──
    if last_close > 0 and valid_zones:
        last_valid = valid_zones[-1]
        zh_top = last_valid["zh_top"]
        if last_close > zh_top:
            above_pct = (last_close - zh_top) / zh_top
            if above_pct <= _THIRD_POINT_MAX_LEAVE_PCT:
                leave_i = None
                for i, s in enumerate(strokes):
                    if (
                        s.get("direction") == "up"
                        and s.get("end_price") is not None
                        and s["end_price"] > zh_top
                    ):
                        if any(
                            strokes[k].get("direction") == "down"
                            for k in range(i + 1, len(strokes))
                        ):
                            leave_i = i
                pullback_ok = False
                last_down_i = None
                if leave_i is not None:
                    for i in range(len(strokes) - 1, leave_i, -1):
                        s = strokes[i]
                        if s.get("direction") == "down" and s.get("end_price") is not None:
                            last_down_i = i
                            if s["end_price"] >= zh_top:
                                # 回抽在末 3 笔内才算当前三买（防粘滞）
                                if last_down_i >= len(strokes) - 3:
                                    pullback_ok = True
                            break
                if leave_i is not None and pullback_ok:
                    vol_ok = not bars or _volume_confirm(len(bars) - 1, 1.2)
                    if vol_ok:
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
    bars: list[dict] | None = None,
) -> list[dict]:
    """检测缠论卖点（与 detect_buy_points 对称，P1 定义）。

    一类卖: 最后一笔 up + valid 中枢 + 两 up + 笔级顶背驰
    二类卖: up_a→down→up_b 且 high_b<high_a 且 high_b>down_low + 力度/MACD 确认
    三类卖: 离开 ZD 之后出现反弹 up 且 end<=ZD；未反弹不报（上限 15%）
    bars 须为与 stroke index 对齐的序列（chanlun_analysis 传入 cleaned）。
    """
    sell_points: list[dict[str, Any]] = []

    if not strokes:
        return sell_points

    def _volume_spike(idx: int, threshold: float = 1.5) -> bool:
        if not bars or idx < 20:
            return True
        recent = bars[max(0, idx - 20):idx]
        avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / len(recent)
        curr_vol = to_float(bars[idx].get("volume")) or 0
        return avg_vol > 0 and curr_vol >= avg_vol * threshold

    valid_zones = [z for z in zones if z.get("valid")]
    last_stroke = strokes[-1]
    up_strokes = [s for s in strokes if s["direction"] == "up"]
    down_strokes = [s for s in strokes if s["direction"] == "down"]

    # ── P1 一类卖：结构 + 笔级顶背驰；删除无中枢降级一类卖 ──
    if last_stroke["direction"] == "up" and valid_zones and len(up_strokes) >= 2:
        prev_up = up_strokes[-2]
        curr_up = up_strokes[-1]
        price_new_high = curr_up["end_price"] >= prev_up["end_price"]
        if price_new_high:
            area_prev = _stroke_macd_area(bars, prev_up, "pos")
            area_curr = _stroke_macd_area(bars, curr_up, "pos")
            if area_prev is not None and area_curr is not None:
                if _stroke_force_weaker(area_prev, area_curr, "up"):
                    sell_points.append({
                        "type": "一类卖",
                        "price": round(curr_up["end_price"], 4),
                        "confidence": 3,
                    })
            else:
                # P7: 无 index / 无法算面积：fallback 要求至少 3 根连续正柱回落
                bar_ok = False
                if bars and len(bars) >= 3:
                    h_vals = [to_float(b.get("macd_histogram")) for b in bars[-3:]]
                    h_vals = [h for h in h_vals if h is not None]
                    bar_ok = (
                        len(h_vals) == 3
                        and all(h > 0 for h in h_vals)
                        and h_vals[2] < h_vals[1] < h_vals[0]
                    )
                elif macd_hist_current is not None and macd_hist_prev is not None:
                    bar_ok = (
                        macd_hist_current > 0
                        and macd_hist_prev > 0
                        and macd_hist_current < macd_hist_prev
                    )
                if bar_ok:
                    sell_points.append({
                        "type": "一类卖",
                        "price": round(curr_up["end_price"], 4),
                        "confidence": 1,
                    })

    # ── P1 二类卖：回抽不过前高；要求末笔即为该回抽 up（防粘滞）──
    if (
        len(strokes) >= 3
        and len(up_strokes) >= 2
        and len(down_strokes) >= 1
        and last_stroke["direction"] == "up"
    ):
        high_a = up_strokes[-2]["end_price"]
        high_b = up_strokes[-1]["end_price"]
        idx_a = -1
        idx_b = -1
        for i, s in enumerate(strokes):
            if s is up_strokes[-2]:
                idx_a = i
            if s is up_strokes[-1]:
                idx_b = i
        if idx_b == len(strokes) - 1:
            down_low = None
            if idx_a >= 0 and idx_b > idx_a:
                for s in strokes[idx_a + 1:idx_b]:
                    if s["direction"] == "down" and s.get("end_price") is not None:
                        if down_low is None or s["end_price"] < down_low:
                            down_low = s["end_price"]
            if down_low is None:
                # P8: 两笔之间无同向笔 → 结构不成立，跳过二类卖
                pass
            else:
                structure_ok = high_b < high_a and high_b > down_low
                if structure_ok:
                    area_prev = _stroke_macd_area(bars, up_strokes[-2], "pos")
                    area_curr = _stroke_macd_area(bars, up_strokes[-1], "pos")
                    area_ok = _stroke_force_not_much_stronger(area_prev, area_curr, "up")
                    if area_ok or macd_divergence_ok:
                        sell_points.append({
                            "type": "二类卖",
                            "price": round(high_b, 4),
                            "confidence": 2,
                        })

    # ── P1/P2 三类卖：离开后反弹不回；反弹须为近端（末 2 笔内）──
    if last_close > 0 and valid_zones:
        last_valid = valid_zones[-1]
        zh_bottom = last_valid["zh_bottom"]
        if last_close < zh_bottom:
            below_pct = (zh_bottom - last_close) / zh_bottom
            if below_pct <= _THIRD_POINT_MAX_LEAVE_PCT:
                leave_i = None
                for i, s in enumerate(strokes):
                    if (
                        s.get("direction") == "down"
                        and s.get("end_price") is not None
                        and s["end_price"] < zh_bottom
                    ):
                        if any(
                            strokes[k].get("direction") == "up"
                            for k in range(i + 1, len(strokes))
                        ):
                            leave_i = i
                bounce_ok = False
                if leave_i is not None:
                    for i in range(len(strokes) - 1, leave_i, -1):
                        s = strokes[i]
                        if s.get("direction") == "up" and s.get("end_price") is not None:
                            if s["end_price"] <= zh_bottom and i >= len(strokes) - 3:
                                bounce_ok = True
                            break
                if leave_i is not None and bounce_ok:
                    vol_ok = not bars or _volume_spike(len(bars) - 1, 1.2)
                    if vol_ok:
                        sell_points.append({
                            "type": "三类卖",
                            "price": round(last_close, 4),
                            "confidence": 1,
                        })

    return sell_points


def detect_divergence(bars: list[dict], strokes: list[dict] | None = None) -> dict:
    """背驰检测（P1：优先笔级 MACD 面积；仅无笔/无 index/面积不可算时 fallback 峰谷）。

    某一侧（顶/底）一旦笔级面积可算，该侧以笔级结论为准，不再被峰谷覆盖。
    两侧独立评估，一侧 True 不短路另一侧。
    """
    result: dict[str, bool] = {"top_divergence": False, "bottom_divergence": False}
    # 笔级是否已对该侧给出最终结论（True/False 都算已评估）
    bottom_evaluated = False
    top_evaluated = False

    n = len(bars)
    if n < 5:
        return result

    # ── P1 优先：最后两段同向笔的面积背驰 ──
    if strokes:
        down_strokes = [s for s in strokes if s["direction"] == "down"]
        up_strokes = [s for s in strokes if s["direction"] == "up"]

        if len(down_strokes) >= 2:
            prev_d, curr_d = down_strokes[-2], down_strokes[-1]
            if curr_d["end_price"] <= prev_d["end_price"]:
                a_prev = _stroke_macd_area(bars, prev_d, "neg")
                a_curr = _stroke_macd_area(bars, curr_d, "neg")
                if a_prev is not None and a_curr is not None:
                    bottom_evaluated = True
                    # P5: 有 power 数据时用多维比较，否则回退到单维
                    if "power_price" in prev_d and "power_price" in curr_d:
                        result["bottom_divergence"] = _stroke_force_weaker_multi(
                            prev_d, curr_d, a_prev, a_curr, "down")
                    else:
                        result["bottom_divergence"] = _stroke_force_weaker(a_prev, a_curr, "down")

        if len(up_strokes) >= 2:
            prev_u, curr_u = up_strokes[-2], up_strokes[-1]
            if curr_u["end_price"] >= prev_u["end_price"]:
                a_prev = _stroke_macd_area(bars, prev_u, "pos")
                a_curr = _stroke_macd_area(bars, curr_u, "pos")
                if a_prev is not None and a_curr is not None:
                    top_evaluated = True
                    if "power_price" in prev_u and "power_price" in curr_u:
                        result["top_divergence"] = _stroke_force_weaker_multi(
                            prev_u, curr_u, a_prev, a_curr, "up")
                    else:
                        result["top_divergence"] = _stroke_force_weaker(a_prev, a_curr, "up")

    # ── fallback：仅对「笔级未评估」的一侧使用全图峰谷 ──
    if not top_evaluated:
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

    if not bottom_evaluated:
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


def _chanlun_compute(
    cleaned: list[dict],
    current: float,
    higher_trend: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
    timeframe: str = "daily",
    raw_bars: list[dict] | None = None,
) -> dict:
    """缠论分析共享内核（批量接口与增量引擎共用）。

    `cleaned` 为「已包含处理 + 已带 MACD」的 K 线序列。本函数只跑结构层与后处理，
    不触碰包含/MACD 计算，确保批量（chanlun_analysis）与增量（ChanlunEngine）两条路径
    由同一份代码驱动、字节级一致。

    注意：`cleaned` 必带 `macd_histogram`（由 _calc_macd 写入），故买卖点力度一律取自
    cleaned，不再回退 raw 入参（raw 入参不再传入本内核）。
    """
    fractions = find_fractions(cleaned)
    strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE, bars=cleaned)
    segments = build_segments(strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)

    # --- E2: build raw zones for zones_count (兼容)，merged zones for 分类 ---
    if len(segments) >= 3:
        items, lvl = segments, "segment"
    else:
        items, lvl = strokes, "stroke"
    raw_zones = build_zones(items, level=lvl, merge=False)
    zones = build_zones(items, level=lvl, merge=True)  # merged if CHAN_ZONE_MERGE_ENABLED
    zones_count = len(raw_zones)  # 保留原始滑动窗口数量，向后兼容

    # timeframe: daily 用日线 conf 门槛；weekly 用周线门槛（段数只调 conf）
    structure = classify_structure(zones, segments, strokes, timeframe=timeframe)
    merged_zones = structure.get("merged_zones", [])
    pivot_count = structure.get("pivot_count", 0)

    # 一类 conf=1 等 bar 级 fallback：优先用 cleaned 末两根，与笔级力度同坐标系
    # cleaned 必带 macd_histogram（由 _calc_macd 写入），故一律用 cleaned，不回退 raw 入参
    cleaned_macd_curr = to_float(cleaned[-1].get("macd_histogram")) if cleaned else None
    cleaned_macd_prev = to_float(cleaned[-2].get("macd_histogram")) if len(cleaned) >= 2 else None
    macd_for_buy_sell_curr = cleaned_macd_curr
    macd_for_buy_sell_prev = cleaned_macd_prev

    # 笔 start_index/end_index 相对 cleaned；背驰/二类确认/买卖点一律吃 cleaned
    divergence = detect_divergence(cleaned, strokes)
    macd_divergence_buy = _check_macd_for_2nd_buy(cleaned, strokes)
    macd_divergence_sell = _check_macd_for_2nd_sell(cleaned, strokes)

    buy_points = detect_buy_points(
        strokes, zones, current, macd_for_buy_sell_curr, macd_for_buy_sell_prev,
        macd_divergence_buy, bars=cleaned,
    )
    sell_points = detect_sell_points(
        strokes, zones, current, macd_for_buy_sell_curr, macd_for_buy_sell_prev,
        macd_divergence_sell, bars=cleaned,
    )

    # --- E1: 多级别区间套确认 ---
    # N1 加固：还原预重构行为——higher_trend 源在 chunk 回退路径（weekly_bars=None）下
    # 必须是「原始 raw bars」而非「包含处理后的 cleaned」，否则聚合分组边界可能偏移。
    # weekly_bars 优先路径忽略首个入参，故此处选择不影响其输出。
    if higher_trend is None and CHAN_MULTILEVEL_ENABLED:
        _ht_src = raw_bars if raw_bars is not None else cleaned
        higher_trend = _higher_level_trend(_ht_src, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=weekly_bars)
    ht: str | None = None
    hc: float = 0.0
    if isinstance(higher_trend, dict):
        ht = higher_trend.get("trend")
        hc = to_float(higher_trend.get("confidence")) or 0.0
    confident = hc >= 0.66

    # 多级别过滤（P1 裁定）：上级明确反向时保留「一类」背驰点，去掉二/三类粘滞点；
    # 同步清理无对应一类时的 divergence，避免过滤买点却仍报底/顶背驰。
    if isinstance(divergence, dict):
        divergence = dict(divergence)
    else:
        divergence = {"top_divergence": False, "bottom_divergence": False}

    if confident and ht == "down":
        buy_points = [bp for bp in buy_points if bp["type"] == "一类买"]
        if not buy_points:
            divergence["bottom_divergence"] = False
    if confident and ht == "up":
        sell_points = [sp for sp in sell_points if sp["type"] == "一类卖"]
        if not sell_points:
            divergence["top_divergence"] = False

    # 顺向增强：买点与上级 up 同向 → confidence +1（cap 3）
    if confident and ht == "up":
        for bp in buy_points:
            bp["confidence"] = min(3, bp["confidence"] + 1)
            bp["multi_level_confirm"] = True
    if confident and ht == "down":
        for sp in sell_points:
            sp["confidence"] = min(3, sp["confidence"] + 1)
            sp["multi_level_confirm"] = True

    # --- E4: 买卖点信号标准化（Signal Contract v2 signal_id）---
    if CHAN_SIGNAL_ID_ENABLED and symbol and analysis_date:
        for bp in buy_points:
            bp["signal_id"] = normalize_signal_id(
                symbol, analysis_date, _chan_type_canonical(bp["type"]), bp["price"],
                source_skill="chanlun",
            )
        for sp in sell_points:
            sp["signal_id"] = normalize_signal_id(
                symbol, analysis_date, _chan_type_canonical(sp["type"]), sp["price"],
                source_skill="chanlun",
            )

    strokes_count = len(strokes)

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
        "structure_confidence": structure.get("structure_confidence", "mid"),
        "structure_evidence": structure.get("structure_evidence", ""),
        # E1 新增字段
        "higher_trend": ht,
        # 真冲突：上级趋势明确，且本级仍留有对立方向买卖点/背驰时为 True
        "higher_trend_conflict": bool(
            confident
            and (
                (ht == "down" and (buy_points or divergence.get("bottom_divergence")))
                or (ht == "up" and (sell_points or divergence.get("top_divergence")))
            )
        ),
        # E3 新增字段：fractions（修复 time_window_detector 死代码 bug）
        "fractions": fractions,
        # E2 新增字段：合并中枢信息
        "merged_zones": merged_zones,
        "pivot_count": pivot_count,
    }


def chanlun_analysis(
    bars: list[dict],
    current: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    higher_trend: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
    timeframe: str = "daily",
) -> dict:
    """缠论批量分析（无状态接口，向后兼容）。

    委托共享内核 `_chanlun_compute`：先算「包含处理 + MACD」，再交给内核。
    输出与重构前字节级一致（仅把结构层/后处理抽取为共享函数，算法行为未改）。
    """
    if len(bars) < CHANLUN_MIN_BARS:
        return {}

    # 结构层：包含处理（拷贝 OHLC，不修改入参 bars）
    cleaned = handle_inclusion(bars)
    # 力度层：在 inclusion 后序列上重算 MACD，使笔 index 与 histogram 同坐标系。
    # _calc_macd 内部 dict 拷贝，只写 cleaned，绝不写回调用方 raw bars。
    cleaned = _calc_macd(cleaned)

    return _chanlun_compute(
        cleaned, current,
        higher_trend=higher_trend, symbol=symbol,
        analysis_date=analysis_date, weekly_bars=weekly_bars, timeframe=timeframe,
        raw_bars=bars,
    )


class ChanlunEngine:
    """缠论增量分析引擎（有状态）。

    Phase 1 范围：批量初始化 + 增量 ``update_bar``（append / 当前 bar replace）+
    状态持久化（save/load）。下游结构算法（find_fractions / build_strokes /
    build_segments / detect_*）全部复用既有纯函数，增量结果与批量重算由构造保证一致
    （共享内核 ``_chanlun_compute``）。

    设计取舍（对照评审第七节）：
      - 以 ``self._raw`` 为权威源，``update_bar`` 后通过 ``_calc_macd(handle_inclusion(raw))``
        重算 ``self.cleaned``。纯尾部增量回溯（7.3 inclusion run / 7.4 增量 MACD）为 optional
        性能项；此处以「全量复用纯函数」换取零漂移正确性（300 根 < 1ms，见 7.5/7.9）。
      - 持久化含 MACD EMA 末值（_ema12/_ema26/_dea）、inclusion run 起点、higher_trend
        缓存与最后 bar 身份（7.6）。save 前用 ``to_float`` 归一 numpy 类型，避免 JSON 序列化失败。
    """

    def __init__(self, bars: list[dict] | None = None):
        self._raw: list[dict] = []
        self.cleaned: list[dict] = []
        self.fractions: list[dict] = []
        self.strokes: list[dict] = []
        self.segments: list[dict] = []
        self.zones: list[dict] = []
        # MACD EMA 末值（持久化用；本实现每 tick 全量重算 cleaned，故为派生状态）
        self._ema12: float | None = None
        self._ema26: float | None = None
        self._dea: float | None = None
        # inclusion run 起点（纳入持久化，供后续尾部增量优化使用）
        self._incl_run_start: int = 0
        # higher_trend 缓存（7.7）
        self._higher_trend: dict | None = None
        self._higher_trend_weekly_id: object | None = None
        # 最后 bar 身份（append / replace 判定，7.6）
        self._last_bar_id: object | None = None
        if bars:
            for bar in bars:
                self.update_bar(bar)

    # ---- bar 身份 ----
    @staticmethod
    def _bar_id(bar: dict) -> object:
        if isinstance(bar, dict) and bar.get("date") is not None:
            return ("date", bar["date"])
        # 无 date 时退化为对象 id（同进程内稳定）；跨进程由 save/load 的 last_bar_id 兜底
        return ("idx", id(bar))

    # ---- 核心重算（一致性由纯函数保证）----
    def _recompute(self) -> None:
        if not self._raw:
            self.cleaned = []
            self.fractions = []
            self.strokes = []
            self.segments = []
            self.zones = []
            self._ema12 = self._ema26 = self._dea = None
            return
        self.cleaned = _calc_macd(handle_inclusion(self._raw))
        self.fractions = find_fractions(self.cleaned)
        self.strokes = build_strokes(
            self.fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE, bars=self.cleaned
        )
        self.segments = build_segments(self.strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)
        # 派生 MACD EMA 末值（用于 save/load 保真）
        from trader_shared.indicator_math import calc_macd_series

        closes = [to_float(b.get("close")) for b in self.cleaned]
        macd = calc_macd_series(closes)
        for k in range(len(macd["ema12"]) - 1, -1, -1):
            if (
                macd["ema12"][k] is not None
                and macd["ema26"][k] is not None
                and macd["dea"][k] is not None
            ):
                self._ema12 = to_float(macd["ema12"][k])
                self._ema26 = to_float(macd["ema26"][k])
                self._dea = to_float(macd["dea"][k])
                break

    def update_bar(self, bar: dict) -> None:
        """增量更新。

        - bar 与最后 bar 同 id（同一交易日/同一对象）→ **replace** 当前（进行中）bar；
        - 否则 → **append** 新 bar。
        """
        bar = dict(bar)
        bar_id = self._bar_id(bar)
        if self._last_bar_id is not None and bar_id == self._last_bar_id and self._raw:
            # replace 当前（进行中）bar：覆盖最后一根 raw，再整段重算
            self._raw[-1] = bar
        else:
            self._raw.append(bar)
            self._last_bar_id = bar_id
        self._recompute()

    def get_analysis(
        self,
        current: float,
        symbol: str | None = None,
        analysis_date: str | None = None,
        weekly_bars: list[dict] | None = None,
        timeframe: str = "daily",
        higher_trend: dict | None = None,
    ) -> dict:
        """基于缓存状态计算（不重算历史）。

        全参数透传至 ``_chanlun_compute``；higher_trend 走缓存（7.7）：
        显式传入优先；否则用首次计算并缓存的值（weekly_bars 对象不变则复用，
        避免盘中每次实时调用都重跑 ``_higher_level_trend``）。
        """
        if len(self._raw) < CHANLUN_MIN_BARS:
            return {}
        if higher_trend is not None:
            ht = higher_trend
        elif self._higher_trend is not None and self._higher_trend_weekly_id == id(weekly_bars):
            ht = self._higher_trend
        else:
            ht = _higher_level_trend(
                self._raw, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=weekly_bars
            )
            self._higher_trend = ht
            self._higher_trend_weekly_id = id(weekly_bars)
        return _chanlun_compute(
            self.cleaned, current, higher_trend=ht, symbol=symbol,
            analysis_date=analysis_date, weekly_bars=weekly_bars, timeframe=timeframe,
        )

    # ---- 状态持久化 ----
    def save(self, path) -> None:
        import json
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "raw_bars": self._raw,
            "ema12": self._ema12,
            "ema26": self._ema26,
            "dea": self._dea,
            "incl_run_start": self._incl_run_start,
            "higher_trend": self._higher_trend,
            "last_bar_id": self._last_bar_id,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, default=_chan_json_default)

    @classmethod
    def load(cls, path) -> "ChanlunEngine":
        import json

        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        eng = cls()
        eng._raw = state.get("raw_bars", [])
        eng._ema12 = state.get("ema12")
        eng._ema26 = state.get("ema26")
        eng._dea = state.get("dea")
        eng._incl_run_start = state.get("incl_run_start", 0)
        eng._higher_trend = state.get("higher_trend")
        eng._last_bar_id = state.get("last_bar_id")
        eng._recompute()
        return eng


def _chan_json_default(o):
    """JSON 序列化兜底：numpy 标量 → 原生 float/int（cleaned 不入库，raw 可能含 numpy）。"""
    try:
        import numpy as np
    except ImportError:
        return str(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


_CHAN_TYPE_CANONICAL: dict[str, str] = {
    "一类买": "chan_buy_1",
    "二类买": "chan_buy_2",
    "三类买": "chan_buy_3",
    "一类卖": "chan_sell_1",
    "二类卖": "chan_sell_2",
    "三类卖": "chan_sell_3",
}


def _chan_type_canonical(cn_type: str) -> str:
    """将中文买卖点类型映射为 Signal Contract v2 规范类型名。"""
    return _CHAN_TYPE_CANONICAL.get(cn_type, cn_type)


def chanlun_strategy(
    current: float,
    bars: list[dict],
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
) -> dict:
    """日线缠论（短线 / fusion）。周线仅作 higher_trend 过滤，不是中线主分析。"""
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    # 从 quote 派生 symbol/date，供 signal_id 使用（向后兼容：无 quote 时不加 id）
    if symbol is None and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if analysis_date is None and isinstance(quote, dict):
        analysis_date = quote.get("trade_date") or (bars[-1].get("date") if bars else None)
    result = chanlun_analysis(
        bars, current, macd_h_curr, macd_h_prev,
        symbol=symbol, analysis_date=analysis_date,
        weekly_bars=weekly_bars,
        timeframe="daily",
    )
    if isinstance(result, dict):
        result = {**result, "timeframe": "daily"}
    return {"chanlun": result}


def chanlun_strategy_midline(
    current: float,
    weekly_bars: list[dict] | None = None,
    daily_bars: list[dict] | None = None,
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
) -> dict:
    """中线缠论独立判断：优先在周 K 上完整跑笔段/结构，不足则回退日 K。

    与日线 chanlun_strategy 分离：
    - 中线：本函数 → 报告「理论：缠论 …」
    - 短线：chanlun_strategy(日线) → fusion / 短线专家
    """
    weekly_bars = weekly_bars or []
    daily_bars = daily_bars or []
    if symbol is None and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if analysis_date is None and isinstance(quote, dict):
        analysis_date = quote.get("trade_date")

    if len(weekly_bars) >= CHANLUN_MIN_BARS:
        bars = weekly_bars
        tf = "weekly"
        conf_tf = "weekly"
        # 周线主分析不再叠 higher_trend 周线（避免双重周线）
        extra_weekly = None
    elif len(daily_bars) >= CHANLUN_MIN_BARS:
        bars = daily_bars
        tf = "daily_fallback"
        conf_tf = "daily"
        extra_weekly = weekly_bars if weekly_bars else None
    else:
        return {
            "chanlun": {
                "timeframe": "insufficient",
                "structure_type": "",
                "structure_confidence": "low",
                "trend_label": "数据不足",
                "divergence": {},
                "buy_points": [],
                "sell_points": [],
            }
        }

    if analysis_date is None and bars:
        analysis_date = bars[-1].get("date")
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    # 现价：周线分析用当前价更贴现价位置
    cur = float(current) if current and current > 0 else float(to_float(bars[-1].get("close")) or 0)
    result = chanlun_analysis(
        bars, cur, macd_h_curr, macd_h_prev,
        symbol=symbol, analysis_date=analysis_date,
        weekly_bars=extra_weekly,
        timeframe=conf_tf,
    )
    if not isinstance(result, dict):
        result = {}
    result = {**result, "timeframe": tf}
    return {"chanlun": result}


def format_chanlun_theory_line(chan_result: Any) -> str:
    """中线理论区用：结构 · 方向（不写「缠论：」前缀，由外层拼接）。

    conf=low 时主名旁注「段偏少」；禁止用线段不足当主显示。
    """
    chan = unwrap_chan(chan_result) if isinstance(chan_result, dict) else {}
    if not isinstance(chan, dict) or not chan:
        return "结构未成型·中性"

    st = str(chan.get("structure_type") or "").strip()
    # 兼容历史缓存中的「线段不足*」主状态；正常路径不再产出该值
    if st.startswith("线段不足"):
        main = "结构未成型"
    elif st and st != "无结构":
        main = st
        conf = str(chan.get("structure_confidence") or "").lower()
        if conf == "low":
            main = f"{st}(段偏少)"
    else:
        main = "暂无明确结构"

    # 方向：买卖点/背驰/trend_label（与 fusion 优先级类似，但只出多空标签）
    buy_points = chan.get("buy_points") if isinstance(chan.get("buy_points"), list) else []
    sell_points = chan.get("sell_points") if isinstance(chan.get("sell_points"), list) else []
    divergence = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    trend_label = str(chan.get("trend_label") or "")

    direction = 0
    if any(isinstance(p, dict) and p.get("type") in ("一类卖", "二类卖", "三类卖") for p in sell_points):
        direction = -1
    elif divergence.get("top_divergence"):
        direction = -1
    elif any(isinstance(p, dict) and p.get("type") in ("一类买", "二类买", "三类买") for p in buy_points):
        direction = 1
    elif divergence.get("bottom_divergence"):
        direction = 1
    elif "上涨" in trend_label or "多" in trend_label:
        direction = 1
    elif "下跌" in trend_label or "空" in trend_label:
        direction = -1

    dir_label = "看涨" if direction > 0 else ("看跌" if direction < 0 else "中性")
    return f"{main}·{dir_label}"
