"""Chan geometry builders (leaf)."""
from __future__ import annotations
import math
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
        CHAN_SEGMENT_RELAX_OVERLAP,
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
    CHAN_SEGMENT_RELAX_OVERLAP = True
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

def _calc_macd(bars: list[dict]) -> list[dict]:
    """计算 MACD histogram 并写入 bars。使用 indicator_math.calc_macd_series 统一实现。

    预热不足时写 ``None``（禁止用 0.0 占位）：0 柱会被当成「零面积」掺进笔级
    MACD 面积，污染背驰力度；``_stroke_macd_area`` 已跳过 None。
    柱线刻度 = DIF−DEA（×1），与通达信常见 2×(DIF−DEA) 差一半，符号一致。
    """
    from trader_shared.indicator_math import calc_macd_series

    bars = [dict(b) for b in bars]
    closes = [to_float(b.get("close")) for b in bars]
    result = calc_macd_series(closes)

    for i, bar in enumerate(bars):
        h = result["histogram"][i] if i < len(result["histogram"]) else None
        bar["macd_histogram"] = h  # None = 预热未完成，勿填 0.0

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

        # 缠论笔定义：从起点出发，取【第一个】距离合格的反向分型成笔，
        # 不往前延伸至「最极端」分型。过度延伸会吞掉本应独立的笔，
        # 导致笔→线段→中枢→背驰→买卖点全链路失真（这是历史“胡算”根因之一）。
        best_end = None
        best_j = None
        while j < num:
            f = fractions[j]

            if f["type"] == start["type"]:
                # 同向分型 → 转折点，停止扫描
                break

            # 反向分型：第一个距离合格者即笔终点（缠论标准）
            if f["index"] - start["index"] >= min_bars_per_stroke - 1:
                best_end = f
                best_j = j
                break

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


def _drop_leading_dangling_strokes(strokes: list[dict]) -> list[dict]:
    """P2：丢弃左端悬空笔，从第一个完整支点起读。

    缠论笔由「第一个合格反向分型」成笔，故序列首笔必从数据起点
    （cleaned[0] 处第一个分型）起算——其左侧没有任何分型可确认起点，
    是悬空不可信笔。标准做法（czsc 等）视首笔/首段为「不确定」，
    不参与趋势判定与背驰比较。

    此处裁掉 strokes[0]（首笔永远无左支点），保留严格交替性；
    笔数 < 2 时不裁（无从裁剪）。
    """
    if len(strokes) < 2:
        return strokes
    return strokes[1:]

def _valid_strokes(strokes: list[dict]) -> list[dict]:
    """过滤掉 start_price/end_price 为非有限值的笔（None/NaN/Inf）。

    用于 build_segments 入口防御：坏数据（缺失价格、除零、来源异常）不应让
    线段构建崩溃，也不应输出含 NaN/Inf 的段。保留原始 dict 引用（不拷贝），
    仅做过滤。
    """
    cleaned: list[dict] = []
    for s in strokes:
        if not isinstance(s, dict):
            continue
        sp = s.get("start_price")
        ep = s.get("end_price")
        if sp is None or ep is None:
            continue
        if not (math.isfinite(sp) and math.isfinite(ep)):
            continue
        cleaned.append(s)
    return cleaned

def _merge_char_element(
    seq: list[dict[str, float]], new_h: float, new_l: float, char_direction: str | None
) -> tuple[list[dict[str, float]], str | None]:
    """对特征序列做包含处理：如果新元素与最后一个重叠，按方向合并。

    P-02：非合并分支原地 `seq.append`（O(1)），不再每次 O(n) 拷贝整条特征序列；
    合并分支直接替换 `seq[-1]`（本就原地）。char_direction 仅被读取，原样返回。
    """
    if not seq:
        return [{"high": new_h, "low": new_l}], char_direction

    last = seq[-1]
    # 检查是否包含（重叠）
    contains = (new_h >= last["high"] and new_l <= last["low"]) or \
               (new_h <= last["high"] and new_l >= last["low"])
    if not contains:
        seq.append({"high": new_h, "low": new_l})
        return seq, char_direction

    # 包含处理：按特征序列趋势方向合并
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
    return seq, char_direction

def build_segments(strokes: list[dict], min_strokes: int = 3, relax_overlap: bool | None = None) -> list[dict]:
    """将笔序列构建为线段序列。

    线段是最小可递归走势单元，由至少3笔构成。
    使用特征序列三分型（含包含处理）判断线段终结：
    - 向上线段：取所有向下笔构成特征序列；至少 3 个特征元素，
      且最后三根形成标准双侧底分型（mid.low 三者最低 且 mid.high 三者最低，
      即 middle 整体低于左右）时终结
    - 向下线段：取所有向上笔构成特征序列；至少 3 个特征元素，
      且最后三根形成标准双侧顶分型（mid.high 三者最高 且 mid.low 三者最高，
      即 middle 整体高于左右）时终结
    - A-2：双侧分型（缠论 1.2 合规，与 find_fractions 一致）——底/顶分型需同时满足
      low 与 high 两侧（middle 整体在单侧之外），单侧假分型（仅 low 达标而 high 不达标）
      不再终结线段，减少误判与包含处理导致的假终结

    包含处理规则（与 K 线包含一致）：
    - 两根特征序列元素重叠时，按方向合并
    - 趋势向上：取 max(high), max(low)
    - 趋势向下：取 min(high), min(low)

    B-01 健壮性：入口过滤掉 start_price/end_price 为非有限值（None/NaN/Inf）的笔，
    过滤后不足 min_strokes 直接返回 []，避免坏数据造成崩溃或输出 NaN/Inf 段。
    P-01 性能：段高/段低用增量 run_high/run_low 维护（随外循环推进），
    去掉每次终结时的 O(n) 重算；P-02：特征序列非合并分支改为原地 append（O(1)）。
    """
    if relax_overlap is None:
        relax_overlap = CHAN_SEGMENT_RELAX_OVERLAP
    min_strokes = max(min_strokes, 3)   # P0-2 加固：方向判定必访问 strokes[2]，防 config 配<3 时 IndexError
    if len(strokes) < min_strokes:
        return []

    # B-01 健壮性：过滤非有限价格笔，过滤后不足 min_strokes 直接返回
    strokes = _valid_strokes(strokes)
    if len(strokes) < min_strokes:
        return []

    # 线段起点：标准缠论从首笔起段，无需"连续3笔价格严格重叠"门槛。
    # 旧逻辑（首个三笔严格重叠才启动）仅保留作一键回退路径。
    if relax_overlap:
        seg_start = 0
    else:
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

    # P-01：增量维护当前未闭合段的 high/low（run_high/run_low），
    # 覆盖 strokes[seg_start .. i-1]（每轮迭代开始时）。段终结与尾部收尾直接使用，
    # 去掉每次终结时的 O(n) 重算；与原 O(n) 逻辑字节级一致（max/min 对集合顺序无关）。
    run_high = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
    run_low = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])

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
                char_seq, char_direction = _merge_char_element(char_seq, char_h, char_l, char_direction)

                # A-2 特征序列三分型终结：至少 3 个特征元素，最后三根标准双侧底分型
                # （mid.low 三者最低 且 mid.high 三者最低——middle 整体低于左右，与
                #   formulas.md 1.2 / find_fractions 一致；单侧假底分型不终结）
                if len(char_seq) >= 3:
                    left, mid, right = char_seq[-3], char_seq[-2], char_seq[-1]
                    if (mid["low"] < left["low"] and mid["low"] < right["low"]
                            and mid["high"] < left["high"] and mid["high"] < right["high"]):
                        end_idx = i - 1
                        start_p = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        end_p = max(strokes[end_idx]["start_price"], strokes[end_idx]["end_price"])
                        segments.append({
                            "direction": "up",
                            "start_price": start_p,
                            "end_price": end_p,
                            "high": run_high,
                            "low": run_low,
                            "start_index": seg_start,
                            "end_index": end_idx,
                            "strokes_count": end_idx - seg_start + 1,
                        })
                        seg_start = end_idx
                        current_direction = "down"
                        char_seq = []
                        char_direction = None
                        # 新段从 seg_start（=end_idx）起；当前触发笔 i 也属于新段，纳入 run
                        run_high = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        run_low = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        h_i = max(s["start_price"], s["end_price"])
                        l_i = min(s["start_price"], s["end_price"])
                        run_high = max(run_high, h_i)
                        run_low = min(run_low, l_i)
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
                char_seq, char_direction = _merge_char_element(char_seq, char_h, char_l, char_direction)

                # A-2 特征序列三分型终结：至少 3 个特征元素，最后三根标准双侧顶分型
                # （mid.high 三者最高 且 mid.low 三者最高——middle 整体高于左右，与
                #   formulas.md 1.2 / find_fractions 一致；单侧假顶分型不终结）
                if len(char_seq) >= 3:
                    left, mid, right = char_seq[-3], char_seq[-2], char_seq[-1]
                    if (mid["high"] > left["high"] and mid["high"] > right["high"]
                            and mid["low"] > left["low"] and mid["low"] > right["low"]):
                        end_idx = i - 1
                        start_p = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        end_p = min(strokes[end_idx]["start_price"], strokes[end_idx]["end_price"])
                        segments.append({
                            "direction": "down",
                            "start_price": start_p,
                            "end_price": end_p,
                            "high": run_high,
                            "low": run_low,
                            "start_index": seg_start,
                            "end_index": end_idx,
                            "strokes_count": end_idx - seg_start + 1,
                        })
                        seg_start = end_idx
                        current_direction = "up"
                        char_seq = []
                        char_direction = None
                        # 新段从 seg_start（=end_idx）起；当前触发笔 i 也属于新段，纳入 run
                        run_high = max(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        run_low = min(strokes[seg_start]["start_price"], strokes[seg_start]["end_price"])
                        h_i = max(s["start_price"], s["end_price"])
                        l_i = min(s["start_price"], s["end_price"])
                        run_high = max(run_high, h_i)
                        run_low = min(run_low, l_i)
                        continue

        # 当前笔 i 属于未闭合段（未触发终结），将其高低纳入 run（增量维护）
        h = max(s["start_price"], s["end_price"])
        l = min(s["start_price"], s["end_price"])
        run_high = max(run_high, h)
        run_low = min(run_low, l)

    # 收尾：如果最后一段至少有 min_strokes 笔，追加（run 已覆盖 strokes[seg_start:]）
    remaining = strokes[seg_start:]
    if len(remaining) >= min_strokes:
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
            "high": run_high,
            "low": run_low,
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


def _last_pivot_anchor_bar(
    segments: list[dict] | None,
    strokes: list[dict] | None,
    merged_zones: list[dict] | None,
) -> int | None:
    """P3：定位「最后中枢」结束处的 bar 索引，作为背驰检测的锚点。

    背驰只应比较最后中枢之后的趋势 legs（离开段 c 及其次级别同向段），
    而非整段历史。返回最后中枢右边界对应的 bar 索引；无法定位时返回 None，
    调用方回退到原行为（不锚定）。

    映射逻辑：
    - merged_zones 由 segments 或 strokes 构成。段级中枢的成员元素（segment）
      其 start_index/end_index 是「笔索引」，需经 strokes 映射到 bar 索引；
    - 笔级中枢（segments 不足时用 strokes 建区）的成员元素 start/end_index
      已是 bar 索引，直接使用。
    """
    if not merged_zones or not strokes:
        return None
    valid = [z for z in merged_zones if z.get("valid")]
    if not valid:
        return None
    last = valid[-1]
    members = last.get("members") or [last]
    if not members:
        return None
    last_raw = members[-1]
    items = last_raw.get("strokes") or []
    if not items:
        return None
    last_item = items[-1]
    si = last_item.get("start_index")
    ei = last_item.get("end_index")
    if si is None or ei is None:
        return None

    anchor = None
    if max(si, ei) < len(strokes):
        # 线段索引 → 经 strokes 映射到 bar 端点（取区间最大 end_index）
        lo, hi = min(si, ei), max(si, ei)
        hi = min(hi, len(strokes) - 1)
        a = to_float(strokes[hi].get("end_index"))
        b = to_float(strokes[lo].get("end_index"))
        if a is not None or b is not None:
            anchor = max(v for v in (a, b) if v is not None)
    else:
        # 已是 bar 索引
        anchor = max(si, ei)

    return int(anchor) if anchor is not None else None

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
