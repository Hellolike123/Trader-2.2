from __future__ import annotations

from typing import Any

from trader_shared.light_data import to_float
from trader_shared.signal_utils import normalize_signal_id

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


def build_strokes(fractions: list[dict], min_bars_per_stroke: int = 5) -> list[dict]:
    """由分型序列构建笔。

    成笔条件：`end.index - start.index >= min_bars_per_stroke - 1`，且方向与上一笔交替。
    连续同向分型取极值（顶取更高 high，底取更低 low）。

    P0 修复：反向分型距离不够时，不再把起点永久丢弃（旧逻辑 `i = j`），
    而是跳过该近距反向分型，继续在后续分型中寻找：
    - 同向更极端 → 更新 start
    - 反向且距离够 → 成笔
    - 反向仍不够 → 继续跳过
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

        # 在后续分型中寻找合格终点；近距反向分型不丢弃 start
        formed = False
        while j < num:
            f = fractions[j]

            if f["type"] == start["type"]:
                # 同向更极端则更新起点
                if start["type"] == "top" and f["high"] > start["high"]:
                    start = f
                elif start["type"] == "bottom" and f["low"] < start["low"]:
                    start = f
                j += 1
                continue

            # 反向分型
            direction = "up" if start["type"] == "bottom" else "down"

            # 强制交替：新笔方向必须与上一笔相反
            if last_direction is not None and direction == last_direction:
                # 方向冲突：从该反向分型重新起笔（与旧语义一致）
                i = j
                formed = True  # 借标记跳出内层，外层 continue
                break

            if f["index"] - start["index"] >= min_bars_per_stroke - 1:
                strokes.append({
                    "start_type": start["type"],
                    "start_price": start["low"] if start["type"] == "bottom" else start["high"],
                    "end_type": f["type"],
                    "end_price": f["high"] if f["type"] == "top" else f["low"],
                    "direction": direction,
                    # P1: 分型 mid 的 bar index（handle_inclusion 后序列），供笔级 MACD 力度
                    "start_index": start["index"],
                    "end_index": f["index"],
                })
                last_direction = direction
                i = j  # 下一笔从本笔终点起
                formed = True
                break

            # 距离不够：跳过该反向分型，保留 start 继续找
            j += 1

        if not formed:
            # 从当前 start 无法成笔（后续无合格反向分型），推进起点防死循环
            i += 1

    return strokes


def build_segments(strokes: list[dict], min_strokes: int = 3) -> list[dict]:
    """将笔序列构建为线段序列。

    线段是最小可递归走势单元，由至少3笔构成。
    使用特征序列法（含包含处理）判断线段终结：
    - 向上线段中，取所有向下笔构成特征序列
    - 对特征序列做包含处理（合并重叠元素）
    - 如果处理后的特征序列出现「跌破前一根」，线段终结
    - 向下线段对称处理

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

                # 检查线段终结：处理后的特征序列当前元素 low < 前一个元素 low
                if len(char_seq) >= 2 and char_seq[-1]["low"] < char_seq[-2]["low"]:
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

                # 检查线段终结：处理后的特征序列当前元素 high > 前一个元素 high
                if len(char_seq) >= 2 and char_seq[-1]["high"] > char_seq[-2]["high"]:
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


def classify_structure(zones: list[dict], segments: list[dict] | None = None, strokes: list[dict] | None = None) -> dict:
    """走势分类：根据中枢拓扑关系和线段数量判断盘整或趋势。

    拓扑规则（中枢合并版）：
    - 0 个合并中枢 → 单边/线段不足
    - 1 个合并中枢 → 验证「进入段+离开段」结构 → 盘整，否则回退到线段数量门槛
    - 2+ 同向不重叠中枢 → 上涨/下跌趋势
    - 重叠中枢 → 盘整

    输出结构类型：
    - "盘整" / "上涨趋势" / "下跌趋势" / "单边上涨" / "单边下跌"
    - "线段不足X/Y" — 有线段但不够判定
    - "无结构" — 连笔都没有

    兼容字段（不变）：structure_type, structure_segments_count, structure_zones_count
    新增字段：merged_zones, pivot_count
    """
    MIN_SEGMENTS_CONSOLIDATION = 5
    MIN_SEGMENTS_TREND = 11

    valid_zones = [z for z in zones if z.get("valid")]
    seg_count = len(segments) if segments else 0
    strokes_count = len(strokes) if strokes else 0

    base: dict[str, Any] = {
        "structure_segments_count": seg_count,
        "structure_zones_count": len(zones),
        "merged_zones": valid_zones,
        "pivot_count": len(valid_zones),
    }

    def _ok(st: str) -> dict:
        return {**base, "structure_type": st}

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

    # 1 个中枢：优先用拓扑结构（进/离段）判定盘整，否则回退到线段数量门槛
    if len(valid_zones) == 1:
        pivot = valid_zones[0]
        if _has_entry_exit_segments(pivot, segments):
            return _ok("盘整")
        # 有中枢本身就是结构证据，线段不足时降级为盘整而非报错
        if seg_count >= MIN_SEGMENTS_CONSOLIDATION:
            return _ok("盘整")
        return _ok("盘整")

    # 2+ 个中枢
    if zones_trend in ("上涨趋势", "下跌趋势"):
        if seg_count < MIN_SEGMENTS_TREND:
            # 有多个中枢本身就是趋势证据，降级为趋势类型而非报错
            return _ok(zones_trend)
        return _ok(zones_trend)

    # 中枢重叠 → 盘整
    if seg_count < MIN_SEGMENTS_CONSOLIDATION:
        return _ok("盘整")
    return _ok("盘整")


def _stroke_macd_area(bars: list[dict] | None, stroke: dict, side: str) -> float | None:
    """对 stroke 的 [start_index, end_index] 区间求 MACD histogram 面积。

    P1 定义：笔级力度用柱面积，而非全图最后 N 根。
    side='neg': 只累加负柱（底背驰用，返回负值或 0）
    side='pos': 只累加正柱（顶背驰用）
    无 index / 无数据 → None（手工 stroke 可能无 index，调用方须容错）

    契约：bars 必须与 start_index/end_index 同一坐标系
    （通常为 handle_inclusion 后的 cleaned，与 build_strokes 一致）。
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
    has_data = False
    for i in range(lo, hi + 1):
        h = to_float(bars[i].get("macd_histogram"))
        if h is None:
            continue
        has_data = True
        if side == "neg" and h < 0:
            area += h
        elif side == "pos" and h > 0:
            area += h
    if not has_data:
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
                # 无 index / 无法算面积：fallback bar 级绿柱缩短，confidence 降为 1
                bar_ok = (
                    macd_hist_current is not None
                    and macd_hist_prev is not None
                    and macd_hist_current < 0
                    and macd_hist_prev < 0
                    and macd_hist_current > macd_hist_prev
                )
                if bar_ok:
                    buy_points.append({
                        "type": "一类买",
                        "price": round(curr_down["end_price"], 4),
                        "confidence": 1,
                    })

    # ── P1 二类买：回抽不破前低（low_a 扮演一类低点，不要求列表里已有一类）──
    if len(strokes) >= 3 and len(down_strokes) >= 2 and len(up_strokes) >= 1:
        low_a = down_strokes[-2]["end_price"]
        low_b = down_strokes[-1]["end_price"]
        idx_a = -1
        idx_b = -1
        for i, s in enumerate(strokes):
            if s is down_strokes[-2]:
                idx_a = i
            if s is down_strokes[-1]:
                idx_b = i
        up_high = None
        if idx_a >= 0 and idx_b > idx_a:
            for s in strokes[idx_a + 1:idx_b]:
                if s["direction"] == "up" and s.get("end_price") is not None:
                    if up_high is None or s["end_price"] > up_high:
                        up_high = s["end_price"]
        if up_high is None:
            up_high = max(s["end_price"] for s in up_strokes)

        structure_ok = low_b > low_a and low_b < up_high
        if structure_ok:
            # 确认：笔级负面积不显著更强，或上游 macd_divergence_ok
            area_prev = _stroke_macd_area(bars, down_strokes[-2], "neg")
            area_curr = _stroke_macd_area(bars, down_strokes[-1], "neg")
            area_ok = _stroke_force_not_much_stronger(area_prev, area_curr, "down")
            if area_ok or macd_divergence_ok:
                buy_points.append({
                    "type": "二类买",
                    "price": round(low_b, 4),
                    "confidence": 2,
                })

    # ── P1 三类买：离开中枢后回踩不入（取消 0~2% 窄窗）──
    # 时间序：先找到「离开 ZG」的 up 笔，只考察其后的回抽 down；未回踩不报三买。
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
                        leave_i = i
                        break
                pullback_ok = False
                if leave_i is not None:
                    downs_after = [
                        s for s in strokes[leave_i + 1 :]
                        if s.get("direction") == "down" and s.get("end_price") is not None
                    ]
                    # 必须有离开后的回抽；最近一次回抽 end >= ZG（不破中枢上沿）
                    if downs_after and downs_after[-1]["end_price"] >= zh_top:
                        pullback_ok = True
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
                bar_ok = (
                    macd_hist_current is not None
                    and macd_hist_prev is not None
                    and macd_hist_current > 0
                    and macd_hist_prev > 0
                    and macd_hist_current < macd_hist_prev
                )
                if bar_ok:
                    sell_points.append({
                        "type": "一类卖",
                        "price": round(curr_up["end_price"], 4),
                        "confidence": 1,
                    })

    # ── P1 二类卖：回抽不过前高 ──
    if len(strokes) >= 3 and len(up_strokes) >= 2 and len(down_strokes) >= 1:
        high_a = up_strokes[-2]["end_price"]
        high_b = up_strokes[-1]["end_price"]
        idx_a = -1
        idx_b = -1
        for i, s in enumerate(strokes):
            if s is up_strokes[-2]:
                idx_a = i
            if s is up_strokes[-1]:
                idx_b = i
        down_low = None
        if idx_a >= 0 and idx_b > idx_a:
            for s in strokes[idx_a + 1:idx_b]:
                if s["direction"] == "down" and s.get("end_price") is not None:
                    if down_low is None or s["end_price"] < down_low:
                        down_low = s["end_price"]
        if down_low is None:
            down_low = min(s["end_price"] for s in down_strokes)

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

    # ── P1 三类卖：离开中枢后反弹不回 ZD（取消过窄窗口）──
    # 时间序：先找到「离开 ZD」的 down 笔，只考察其后的反弹 up；未反弹不报三卖。
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
                        leave_i = i
                        break
                bounce_ok = False
                if leave_i is not None:
                    ups_after = [
                        s for s in strokes[leave_i + 1 :]
                        if s.get("direction") == "up" and s.get("end_price") is not None
                    ]
                    if ups_after and ups_after[-1]["end_price"] <= zh_bottom:
                        bounce_ok = True
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
                    result["bottom_divergence"] = _stroke_force_weaker(a_prev, a_curr, "down")

        if len(up_strokes) >= 2:
            prev_u, curr_u = up_strokes[-2], up_strokes[-1]
            if curr_u["end_price"] >= prev_u["end_price"]:
                a_prev = _stroke_macd_area(bars, prev_u, "pos")
                a_curr = _stroke_macd_area(bars, curr_u, "pos")
                if a_prev is not None and a_curr is not None:
                    top_evaluated = True
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


def chanlun_analysis(
    bars: list[dict],
    current: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    higher_trend: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
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

    # --- E2: build raw zones for zones_count (兼容)，merged zones for 分类 ---
    if len(segments) >= 3:
        items, lvl = segments, "segment"
    else:
        items, lvl = strokes, "stroke"
    raw_zones = build_zones(items, level=lvl, merge=False)
    zones = build_zones(items, level=lvl, merge=True)  # merged if CHAN_ZONE_MERGE_ENABLED
    zones_count = len(raw_zones)  # 保留原始滑动窗口数量，向后兼容

    structure = classify_structure(zones, segments, strokes)
    merged_zones = structure.get("merged_zones", [])
    pivot_count = structure.get("pivot_count", 0)

    # P1: 笔 start_index/end_index 相对 handle_inclusion 后序列，笔级 MACD 必须用 cleaned
    divergence = detect_divergence(cleaned, strokes)

    # Check MACD divergence for 2nd buy point (bottom divergence)
    macd_divergence_buy = _check_macd_for_2nd_buy(cleaned, strokes)
    # Check MACD divergence for 2nd sell point (top divergence) — P0 fix
    macd_divergence_sell = _check_macd_for_2nd_sell(cleaned, strokes)

    buy_points = detect_buy_points(
        strokes, zones, current, macd_hist_current, macd_hist_prev,
        macd_divergence_buy, bars=cleaned,
    )
    sell_points = detect_sell_points(
        strokes, zones, current, macd_hist_current, macd_hist_prev,
        macd_divergence_sell, bars=cleaned,
    )

    # --- E1: 多级别区间套确认 ---
    if higher_trend is None and CHAN_MULTILEVEL_ENABLED:
        higher_trend = _higher_level_trend(bars, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=weekly_bars)
    ht: str | None = None
    hc: float = 0.0
    if isinstance(higher_trend, dict):
        ht = higher_trend.get("trend")
        hc = to_float(higher_trend.get("confidence")) or 0.0
    confident = hc >= 0.66

    # 冲突过滤：上级趋势 down 且置信 → 仅保留 二类买（已由 MACD 门控）
    if confident and ht == "down":
        buy_points = [bp for bp in buy_points if bp["type"] == "二类买"]
    # 冲突过滤：上级趋势 up 且置信 → 仅保留 二类卖（已由 MACD 门控）
    if confident and ht == "up":
        sell_points = [sp for sp in sell_points if sp["type"] == "二类卖"]

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
        # E1 新增字段
        "higher_trend": ht,
        "higher_trend_conflict": bool(confident and ht in ("up", "down")),
        # E3 新增字段：fractions（修复 time_window_detector 死代码 bug）
        "fractions": fractions,
        # E2 新增字段：合并中枢信息
        "merged_zones": merged_zones,
        "pivot_count": pivot_count,
    }


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
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    # 从 quote 派生 symbol/date，供 signal_id 使用（向后兼容：无 quote 时不加 id）
    if symbol is None and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if analysis_date is None and isinstance(quote, dict):
        analysis_date = quote.get("trade_date") or (bars[-1].get("date") if bars else None)
    return {
        "chanlun": chanlun_analysis(
            bars, current, macd_h_curr, macd_h_prev,
            symbol=symbol, analysis_date=analysis_date,
            weekly_bars=weekly_bars,
        )
    }
