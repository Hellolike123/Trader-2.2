"""Chan structure classification + buy/sell points + divergence."""
from __future__ import annotations
import math
import os
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
        CHAN_DIVERGENCE_FALLBACK_WINDOW,
        CHAN_DIVERGENCE_BC,
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
    CHAN_DIVERGENCE_FALLBACK_WINDOW = 120
    CHAN_DIVERGENCE_BC = "legacy"

from .chan_geometry import (
    _aggregate_bars,
    _calc_macd,
    _detect_unilateral,
    _has_entry_exit_segments,
    _higher_level_trend,
    _merge_char_element,
    _merge_zones,
    _valid_strokes,
    build_segments,
    build_strokes,
    build_zones,
    find_fractions,
    handle_inclusion,
    unwrap_chan
)

_THIRD_POINT_MAX_LEAVE_PCT = 0.15

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

    拓扑规则（中枢合并版；formulas.md §4.3 / §9 / §11A）：
    - strokes < 3 → 无结构
    - 0 个合并中枢 → 单边 / 无结构（原典：0 中枢即无结构，不谎报盘整；§11A）
    - 1 个合并中枢 → 盘整
    - 2+ 同向不重叠中枢 + 连接段为反向 → 上涨趋势 / 下跌趋势（即使段数只有 4～6）
    - 2+ 同向不重叠但连接段非反向（夹同向小中枢）→ 盘整（假趋势，§9.2/§9.4；
      不发明 structure_type=假趋势）
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
            return _ok("无结构")  # 原典：0 中枢即无结构，不谎报盘整
        return _ok("无结构")

    # 判断中枢方向关系（拓扑：同向不重叠→趋势，重叠→盘整）
    # formulas.md §4.3 / §9.2：同向不重叠且连接段为反向 → 趋势；连接段非反向 → 假趋势降盘整
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

    # 2+ 同向不重叠中枢 → 趋势；但 §9.1/§9.2/§9.4：任一对连接段非反向 → 降为盘整（假趋势）
    # structure_type 仍只写「盘整」，不发明「假趋势」主状态
    if zones_trend in ("上涨趋势", "下跌趋势"):
        pair_dir = "up" if zones_trend == "上涨趋势" else "down"
        for i in range(1, len(valid_zones)):
            if _connector_is_non_reverse(
                valid_zones[i - 1],
                valid_zones[i],
                pair_dir,
                segments=segments,
                strokes=strokes,
            ):
                out = _ok("盘整")
                out["structure_evidence"] = (
                    f"{out['structure_evidence']},假趋势(连接段非反向·§9.2)"
                )
                return out
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

def _volume_shrink_between_strokes(bars: list[dict], stroke_prev: dict, stroke_curr: dict) -> bool:
    """检查两段笔之间成交量是否缩量（回踩量缩 = 抛压枯竭）。

    原典依据：二买的核心确认是回踩时量缩，代表卖方力量衰竭。
    计算：后一笔区间内均量 <= 前一笔区间内均量 × 0.8（允许 20% 误差）。
    数据不足时放行（不因缺数据误杀信号）。
    """
    if not bars:
        return True

    def _avg_vol(stroke: dict) -> float | None:
        start = stroke.get("start_index") or 0
        end = stroke.get("end_index") or 0
        if start >= end or end > len(bars):
            return None
        vols = []
        for i in range(start, min(end, len(bars))):
            v = to_float(bars[i].get("volume"))
            if v is not None and v > 0:
                vols.append(v)
        return sum(vols) / len(vols) if vols else None

    vol_prev = _avg_vol(stroke_prev)
    vol_curr = _avg_vol(stroke_curr)

    # 数据不足放行
    if vol_prev is None or vol_curr is None:
        return True
    if vol_prev <= 0:
        return True

    # 缩量条件：回踩均量 <= 前笔均量 × 0.8（必须明确缩量 20%+）
    return vol_curr <= vol_prev * 0.8

def _check_macd_for_2nd_buy(
    bars: list[dict],
    strokes: list[dict],
) -> bool:
    """二类买确认（原典三条件：MACD + 成交量缩量 + 趋势过滤）。

    Condition A: 笔级 MACD 负面积，后笔力度不显著强于前笔
    Condition B: 近端柱状恢复（绿柱回升）
    Condition C: 成交量缩量（回踩时量缩，代表抛压枯竭）
    工程风控：MA 空头排列硬过滤
    """
    if not bars or not strokes:
        return False

    down_strokes = [s for s in strokes if s["direction"] == "down"]
    if len(down_strokes) < 2:
        return False

    # Condition A: 笔级 MACD 负面积对比
    area_prev = _stroke_macd_area(bars, down_strokes[-2], "neg")
    area_curr = _stroke_macd_area(bars, down_strokes[-1], "neg")
    condition_a = _stroke_force_not_much_stronger(area_prev, area_curr, "down")

    # Condition B: 近端柱状恢复
    hist_values = [to_float(b.get("macd_histogram")) for b in bars]
    hist_values = [h for h in hist_values if h is not None]
    condition_b = False
    if len(hist_values) >= 3:
        last_3 = hist_values[-3:]
        condition_b = all(h < 0 for h in last_3) and last_3[-1] > last_3[0]
    if not condition_a and area_prev is None and area_curr is None and len(hist_values) >= 10:
        recent_hist = hist_values[-5:]
        earlier_hist = hist_values[-10:-5]
        if recent_hist and earlier_hist:
            recent_min = min(recent_hist)
            earlier_min = min(earlier_hist)
            condition_a = recent_min > earlier_min and recent_min < 0

    if not (condition_a or condition_b):
        return False

    # Condition C: 成交量缩量（原典核心：二买回踩时量缩 = 抛压枯竭）
    # 回踩笔（第二段 down）的均量 < 第一段 down 的均量
    condition_c = _volume_shrink_between_strokes(bars, down_strokes[-2], down_strokes[-1])

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

def _item_raw_index_span(item: dict) -> tuple[int, int] | None:
    """读取成员 start/end_index 原始跨度（尚未映到 bar）。"""
    si = item.get("start_index")
    ei = item.get("end_index")
    if si is None or ei is None:
        return None
    try:
        a, b = int(si), int(ei)
    except (TypeError, ValueError):
        return None
    if a < 0 or b < 0:
        return None
    return (a, b) if a <= b else (b, a)


def _zone_member_items(zone: dict) -> list[dict]:
    """合并中枢走 members；原始中枢顶层带 strokes。"""
    items: list[dict] = []
    members = zone.get("members") or [zone]
    for m in members:
        for s in m.get("strokes", []):
            if isinstance(s, dict):
                items.append(s)
    return items


def _zone_indices_are_stroke_ordinals(zone: dict, strokes: list[dict] | None) -> bool:
    """段级中枢成员索引为笔序；笔级中枢索引已是 bar（对齐 ``_last_pivot_anchor_bar``）。"""
    if not strokes:
        return False
    idxs: list[int] = []
    for item in _zone_member_items(zone):
        span = _item_raw_index_span(item)
        if span is None:
            continue
        idxs.extend(span)
    if not idxs:
        return False
    return max(idxs) < len(strokes)


def _map_stroke_ordinal_span_to_bar(
    lo: int,
    hi: int,
    strokes: list[dict],
) -> tuple[int, int] | None:
    """笔序 [lo, hi] → bar 起止（取覆盖笔的 start/end_index 极值）。"""
    if lo < 0 or hi < 0 or not strokes:
        return None
    hi = min(hi, len(strokes) - 1)
    lo = min(lo, hi)
    bars: list[int] = []
    for i in range(lo, hi + 1):
        s = strokes[i]
        for key in ("start_index", "end_index"):
            v = s.get(key)
            if v is None:
                continue
            try:
                bars.append(int(v))
            except (TypeError, ValueError):
                continue
    if not bars:
        return None
    return min(bars), max(bars)


def _item_bar_span(
    item: dict,
    strokes: list[dict] | None = None,
    *,
    as_segment: bool = False,
) -> tuple[int, int] | None:
    """笔/段索引 → bar 跨度。

    ``as_segment=True``（或段级中枢成员）时经 strokes 映到 bar；
    笔级则索引已是 bar，直接用。法源：formulas.md §9.1；range-diff C-DIFF-2。
    """
    span = _item_raw_index_span(item)
    if span is None:
        return None
    lo, hi = span
    if as_segment and strokes and hi < len(strokes):
        return _map_stroke_ordinal_span_to_bar(lo, hi, strokes)
    return lo, hi


def _zone_last_end_index(zone: dict, strokes: list[dict] | None = None) -> int:
    """取中枢末端在 **K 线（bar）** 坐标系下的 end 索引，用于离开段约束。

    兼容两种中枢结构：
    - 合并中枢（build_zones merge=True，默认）：顶层无 strokes，末端落在 members 的最后一笔；
    - 原始滑动窗口中枢（merge=False）：顶层直接带 strokes。
    段级中枢成员 ``start_index/end_index`` 为笔序，须经 ``strokes`` 映到 bar
    （范式对齐 ``_last_pivot_anchor_bar``）；笔级中枢索引已是 bar。
    无任何有效成员返回 -1。

    修复 D4：旧实现直接读 zone.get("strokes")，但默认 merge=True 产出的合并中枢
    顶层没有 strokes 字段，导致 _last_zone_end 恒为 -1，"背驰须发生在离开段"
    的约束被静默禁用，可能产出假一类买卖。
    """
    as_seg = _zone_indices_are_stroke_ordinals(zone, strokes)
    candidates: list[int] = []
    for item in _zone_member_items(zone):
        span = _item_bar_span(item, strokes, as_segment=as_seg)
        if span is not None:
            candidates.append(span[1])
    return max(candidates) if candidates else -1


def _zone_first_start_index(zone: dict, strokes: list[dict] | None = None) -> int:
    """取中枢首端在 **bar** 坐标系下的 start_index（与 `_zone_last_end_index` 对称）。

    合并中枢走 members；原始中枢顶层带 strokes。段级须映笔序→bar。
    无有效索引返回 -1。用于 formulas.md §9.1/§9.2 连接段时间窗：`(prev_end, curr_start)`。
    """
    as_seg = _zone_indices_are_stroke_ordinals(zone, strokes)
    candidates: list[int] = []
    for item in _zone_member_items(zone):
        span = _item_bar_span(item, strokes, as_segment=as_seg)
        if span is not None:
            candidates.append(span[0])
    return min(candidates) if candidates else -1


def _item_indices_in_open_interval(
    item: dict,
    prev_end: int,
    curr_start: int,
    strokes: list[dict] | None = None,
    *,
    as_segment: bool = False,
) -> bool:
    """笔/段在 bar 坐标系下是否整段落在开区间 (prev_end, curr_start) 内。"""
    span = _item_bar_span(item, strokes, as_segment=as_segment)
    if span is None:
        return False
    lo, hi = span
    return prev_end < lo and hi < curr_start


def _connector_is_non_reverse(
    prev_zone: dict,
    curr_zone: dict,
    pair_dir: str,
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> bool:
    """连接段是否「非反向走势」（假趋势拓扑，formulas.md §9.1 / §9.2 / §9.4）。

    操作化（仅由「即连接段自身不是反向走势」等价推出，不发明幅度阈值）：
      - 时间窗：`(_zone_last_end_index(prev), _zone_first_start_index(curr))` 开区间（**bar** 序）
      - 索引不可解析或窗口非法 → False（无法证明假趋势，不降级；兼容无 member 索引的裸区单测）
      - 优先收集窗内 segments（段索引映 bar），若无则 strokes；仍无 → False（保守）
      - reverse = down if pair_dir==up else up
      - 窗内无一笔/段 direction==reverse → True（连接段非反向 → 假趋势）
      - ≥1 反向项 → False（合格连接）
    """
    if pair_dir not in ("up", "down"):
        return False
    prev_end = _zone_last_end_index(prev_zone, strokes)
    curr_start = _zone_first_start_index(curr_zone, strokes)
    if prev_end < 0 or curr_start < 0 or prev_end >= curr_start:
        return False

    connector: list[dict] = []
    if segments:
        connector = [
            s for s in segments
            if isinstance(s, dict)
            and _item_indices_in_open_interval(
                s, prev_end, curr_start, strokes, as_segment=True
            )
        ]
    if not connector and strokes:
        connector = [
            s for s in strokes
            if isinstance(s, dict)
            and _item_indices_in_open_interval(
                s, prev_end, curr_start, strokes, as_segment=False
            )
        ]
    if not connector:
        return False

    reverse = "down" if pair_dir == "up" else "up"
    if any(s.get("direction") == reverse for s in connector):
        return False
    return True


def _strict_down_trend_zones(
    valid_zones: list[dict],
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> bool:
    """下跌趋势：≥2 中枢且整链严格下移不重叠（与 classify 拓扑一致）。

    formulas.md §6 / §9.1–§9.4：一类拓扑与 classify 一致——全部相邻同向不重叠，
    且任一对连接段须为反向；夹同向小中枢（连接段非反向）→ False。
    未传 segments/strokes 或索引缺失时跳过连接检查（保持旧裸区行为）。
    """
    if len(valid_zones) < 2:
        return False
    for i in range(1, len(valid_zones)):
        prev, curr = valid_zones[i - 1], valid_zones[i]
        try:
            if not (float(curr["zh_top"]) < float(prev["zh_bottom"])):
                return False
        except (TypeError, ValueError, KeyError):
            return False
        if _connector_is_non_reverse(
            prev, curr, "down", segments=segments, strokes=strokes
        ):
            return False
    return True


def _strict_up_trend_zones(
    valid_zones: list[dict],
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> bool:
    """上涨趋势：≥2 中枢且整链严格上移不重叠。

    同 `_strict_down_trend_zones`：§9 连接段须反向，否则非一类趋势拓扑。
    """
    if len(valid_zones) < 2:
        return False
    for i in range(1, len(valid_zones)):
        prev, curr = valid_zones[i - 1], valid_zones[i]
        try:
            if not (float(curr["zh_bottom"]) > float(prev["zh_top"])):
                return False
        except (TypeError, ValueError, KeyError):
            return False
        if _connector_is_non_reverse(
            prev, curr, "up", segments=segments, strokes=strokes
        ):
            return False
    return True


def _stroke_leaves_after_zone(
    stroke: dict,
    zone: dict,
    strokes: list[dict] | None = None,
) -> bool:
    """笔是否从中枢之后离开（无 index 时放行，兼容手工 stroke 单测）。

    比较在 **bar** 坐标系：段级中枢 zone_end 经 strokes 映到 bar 后再比。
    """
    z_end = _zone_last_end_index(zone, strokes)
    si = stroke.get("start_index")
    if si is None or z_end < 0:
        return True
    try:
        return int(si) > z_end
    except (TypeError, ValueError):
        return True


def _with_anchor(point: dict[str, Any], stroke: dict | None) -> dict[str, Any]:
    """给买卖点挂上结构锚点（定义笔 end_index），供粘滞去重 / 稳定 signal_id。"""
    if not isinstance(stroke, dict):
        return point
    ei = stroke.get("end_index")
    if ei is None:
        return point
    try:
        point["anchor_index"] = int(ei)
    except (TypeError, ValueError):
        return point
    return point


def _stroke_leaves_zone(
    stroke: dict,
    zone: dict,
    direction: str,
    strokes: list[dict] | None = None,
) -> bool:
    """离开段须同时满足：时间在中枢之后 + 价格穿出中枢。

    仅「start_index > zone_end」会把远高于/低于中枢的后续笔误判为离开段
    （例：中枢在 32，后续 down 在 51 仍被当成一类买离开段）。
    - down：end_price < zh_bottom（破 ZD）
    - up：end_price > zh_top（破 ZG）
    缺价位字段时回退为时间离开（兼容残缺单测）。
    段级中枢时间比较须 bar 序（见 ``_zone_last_end_index``）。
    """
    if not _stroke_leaves_after_zone(stroke, zone, strokes):
        return False
    try:
        end_price = float(stroke["end_price"])
        if direction == "down":
            return end_price < float(zone["zh_bottom"])
        if direction == "up":
            return end_price > float(zone["zh_top"])
    except (TypeError, ValueError, KeyError):
        return True
    return False


def _historical_type1_buy_ok(
    down_strokes: list[dict],
    valid_zones: list[dict],
    bars: list[dict] | None,
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> bool:
    """二类买时刻：末笔是抬高低点回抽，一类低点在 down_strokes[-2]。

    禁止「同帧 buy_points 里已有一类」——一类要创新低、二类要不破前低，
    同一末笔几何互斥，旧逻辑导致二类永假。
    """
    if len(down_strokes) < 2 or not _strict_down_trend_zones(
        valid_zones, segments=segments, strokes=strokes
    ):
        return False
    first = down_strokes[-2]
    if not _stroke_leaves_zone(first, valid_zones[-1], "down", strokes):
        return False
    if len(down_strokes) >= 3:
        prior = down_strokes[-3]
        try:
            if float(first["end_price"]) > float(prior["end_price"]):
                return False
        except (TypeError, ValueError, KeyError):
            return False
        area_prev = _stroke_macd_area(bars, prior, "neg")
        area_curr = _stroke_macd_area(bars, first, "neg")
        if area_prev is not None and area_curr is not None:
            if not _stroke_force_weaker(area_prev, area_curr, "down"):
                return False
    return True


def _historical_type1_sell_ok(
    up_strokes: list[dict],
    valid_zones: list[dict],
    bars: list[dict] | None,
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> bool:
    """二类卖时刻：末笔是降低高点反抽，一类高点在 up_strokes[-2]。"""
    if len(up_strokes) < 2 or not _strict_up_trend_zones(
        valid_zones, segments=segments, strokes=strokes
    ):
        return False
    first = up_strokes[-2]
    if not _stroke_leaves_zone(first, valid_zones[-1], "up", strokes):
        return False
    if len(up_strokes) >= 3:
        prior = up_strokes[-3]
        try:
            if float(first["end_price"]) < float(prior["end_price"]):
                return False
        except (TypeError, ValueError, KeyError):
            return False
        area_prev = _stroke_macd_area(bars, prior, "pos")
        area_curr = _stroke_macd_area(bars, first, "pos")
        if area_prev is not None and area_curr is not None:
            if not _stroke_force_weaker(area_prev, area_curr, "up"):
                return False
    return True


def resolve_divergence_bc_mode(bc_mode: str | None = None) -> str:
    """背驰比较模式：legacy（末两同向笔）| strict（中枢 b vs c）。默认 legacy。"""
    raw = (bc_mode if bc_mode is not None else os.environ.get("CHAN_DIVERGENCE_BC", CHAN_DIVERGENCE_BC))
    mode = str(raw or "legacy").strip().lower()
    return mode if mode in ("legacy", "strict") else "legacy"


def _bc_stroke_pair(
    strokes: list[dict],
    zone: dict,
    direction: str,
) -> tuple[dict | None, dict | None]:
    """最后中枢的进入段 b 与离开段 c（同方向笔）。

    规则（formulas.md §5.4）：
      - c：中枢之后（start_index > zone_end）同向笔的末笔
      - b：中枢结束前（end_index <= zone_end）同向笔的最近一笔
      - 缺 index / 缺 b 或 c → (None, None)
    zone_end 为 **bar** 索引（段级中枢成员笔序经 strokes 映射）。
    """
    if not strokes or not isinstance(zone, dict):
        return None, None
    z_end = _zone_last_end_index(zone, strokes)
    if z_end < 0:
        return None, None

    same = [s for s in strokes if isinstance(s, dict) and s.get("direction") == direction]
    after: list[dict] = []
    before: list[dict] = []
    for s in same:
        try:
            si = s.get("start_index")
            ei = s.get("end_index")
            if si is not None and int(si) > z_end:
                after.append(s)
            elif ei is not None and int(ei) <= z_end:
                before.append(s)
        except (TypeError, ValueError):
            continue
    if not after or not before:
        return None, None
    return before[-1], after[-1]


def _divergence_kind_for_zones(
    valid_zones: list[dict],
    direction: str,
    segments: list[dict] | None = None,
    strokes: list[dict] | None = None,
) -> str:
    """有 b/c 可比较时的 kind：严格趋势中枢 → trend，否则 range。"""
    if direction == "down" and _strict_down_trend_zones(
        valid_zones, segments=segments, strokes=strokes
    ):
        return "trend"
    if direction == "up" and _strict_up_trend_zones(
        valid_zones, segments=segments, strokes=strokes
    ):
        return "trend"
    if valid_zones:
        return "range"
    return "none"


def resolve_force_stroke_pair(
    strokes: list[dict],
    valid_zones: list[dict],
    direction: str,
    *,
    bc_mode: str | None = None,
    anchor_bar: int | None = None,
    segments: list[dict] | None = None,
) -> tuple[dict | None, dict | None, str]:
    """解析用于力度比较的 (prev/b, curr/c, kind)。

    legacy：锚定后（或全序列）末两同向笔；kind 由中枢拓扑标。
    strict：必须能解析最后中枢 b/c；否则返回 (None, None, "none")。
    """
    mode = resolve_divergence_bc_mode(bc_mode)
    same = [s for s in strokes if isinstance(s, dict) and s.get("direction") == direction]
    if mode == "strict":
        if not valid_zones:
            return None, None, "none"
        b, c = _bc_stroke_pair(strokes, valid_zones[-1], direction)
        if b is None or c is None:
            return None, None, "none"
        return b, c, _divergence_kind_for_zones(
            valid_zones, direction, segments=segments, strokes=strokes
        )

    # legacy：可选锚定过滤（与 detect_divergence 旧行为一致）
    if anchor_bar is not None:
        anchored = [s for s in same if to_float(s.get("end_index")) is not None
                    and float(s.get("end_index")) >= anchor_bar]
        if len(anchored) >= 2:
            same = anchored
    if len(same) < 2:
        return None, None, "none"
    kind = (
        _divergence_kind_for_zones(
            valid_zones, direction, segments=segments, strokes=strokes
        )
        if valid_zones
        else "none"
    )
    return same[-2], same[-1], kind


def detect_buy_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    macd_divergence_ok: bool = False,
    bars: list[dict] | None = None,
    bc_mode: str | None = None,
    segments: list[dict] | None = None,
) -> list[dict]:
    """检测缠论买点（P1 定义纠偏）。

    一类买: 下跌趋势（≥2 不重叠下移中枢）+ 离开段末 down 创新低 + 笔级底背驰
    二类买: down_a→up→down_b 且 low_b>low_a 且 low_b<up_high；
           且前置一类 = 时间轴上 down_a 满足历史一类结构（非同帧 buy_points）
    类二买: 同上结构几何，但历史一类不满足或力度/缩量未齐——买侧放宽试探档
           （fusion/C1 只认正式「二类买」，类二买不进强多/买点阶梯二档）
    三类买: 离开 ZG 之后出现回抽 down 且 end>=ZG；未回踩不报（上限 15%）；
           量能确认与三类卖对称（近20日均量 ×1.2，数据不足放行）
    bars 须为与 stroke index 对齐的序列（chanlun_analysis 传入 handle_inclusion 后的 cleaned）。
    """
    buy_points: list[dict[str, Any]] = []

    if not strokes:
        return buy_points

    # ── 辅助过滤器（增强项，不替代中枢+背驰主条件；与卖侧 _volume_spike 同口径）──
    def _volume_confirm(idx: int, threshold: float = 1.2) -> bool:
        """当日成交量 ≥ 近20日均量 × threshold；数据不足放行"""
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

    # ── 一类买：下跌背驰（两档：严格趋势 / 放宽结构）──
    # 严格档：≥2 个不重叠下移中枢（原典趋势级别）
    # 放宽档：≥1 个中枢 + 末段创新低 + MACD 背驰（结构级别，实盘更实用）
    # strict 模式：力度对用最后中枢 b/c；legacy：末两同向 down
    if last_stroke["direction"] == "down" and len(down_strokes) >= 2 and valid_zones:
        prev_down, curr_down, force_kind = resolve_force_stroke_pair(
            strokes, valid_zones, "down", bc_mode=bc_mode, segments=segments
        )
        if prev_down is not None and curr_down is not None:
            price_new_low = curr_down["end_price"] <= prev_down["end_price"]
            last_zone = valid_zones[-1]
            if price_new_low and _stroke_leaves_zone(curr_down, last_zone, "down", strokes):
                area_prev = _stroke_macd_area(bars, prev_down, "neg")
                area_curr = _stroke_macd_area(bars, curr_down, "neg")
                _is_strict_trend = force_kind == "trend"
                if area_prev is not None and area_curr is not None:
                    if _stroke_force_weaker(area_prev, area_curr, "down"):
                        bp_type = "一类买" if _is_strict_trend else "类一买"
                        bp_conf = 3 if _is_strict_trend else 2
                        buy_points.append(_with_anchor({
                            "type": bp_type,
                            "price": round(curr_down["end_price"], 4),
                            "confidence": bp_conf,
                            "divergence_kind": force_kind,
                        }, curr_down))
                else:
                    # 柱序列 fallback（strict 无 b/c 面积时仍可弱确认）
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
                        bar_ok = (
                            macd_hist_current < 0
                            and macd_hist_prev < 0
                            and macd_hist_current > macd_hist_prev
                        )
                    if bar_ok:
                        buy_points.append(_with_anchor({
                            "type": "类一买",
                            "price": round(curr_down["end_price"], 4),
                            "confidence": 1,
                            "force_source": "hist_bar_fallback",
                            "divergence_kind": "range",
                        }, curr_down))
        elif resolve_divergence_bc_mode(bc_mode) == "legacy":
            # legacy 且 resolve 失败时不应到此（有 ≥2 down）；strict 无 b/c 则静默
            pass

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
                # 正式二类买：历史一类 + 结构 + (面积/MACD) + 缩量
                # 类二买：仅结构 + (面积/MACD/缩量任一项)；无趋势中枢也可（买侧放宽）
                # 裸结构（无力度也无缩量）不报任何信号
                structure_ok = low_b > low_a and low_b < up_high
                if structure_ok:
                    hist_type1_ok = _historical_type1_buy_ok(
                        down_strokes, valid_zones, bars,
                        segments=segments, strokes=strokes,
                    )
                    area_prev = _stroke_macd_area(bars, down_strokes[-2], "neg")
                    area_curr = _stroke_macd_area(bars, down_strokes[-1], "neg")
                    area_ok = _stroke_force_not_much_stronger(area_prev, area_curr, "down")
                    vol_shrink = _volume_shrink_between_strokes(
                        bars, down_strokes[-2], down_strokes[-1]
                    )
                    force_ok = area_ok or macd_divergence_ok
                    if hist_type1_ok and force_ok and vol_shrink:
                        buy_points.append(_with_anchor({
                            "type": "二类买",
                            "price": round(low_b, 4),
                            "confidence": 2,
                        }, down_strokes[-1]))
                    elif force_ok or vol_shrink:
                        buy_points.append(_with_anchor({
                            "type": "类二买",
                            "price": round(low_b, 4),
                            "confidence": 1,
                        }, down_strokes[-1]))

    # ── 三类买：离开中枢后回踩不入 + 反弹确认（与三类卖对称：离开幅度 ≤15%）──
    if last_close > 0 and valid_zones:
        last_valid = valid_zones[-1]
        zh_top = last_valid["zh_top"]
        if last_close > zh_top:
            above_pct = (last_close - zh_top) / zh_top if zh_top else 999.0
            if above_pct <= _THIRD_POINT_MAX_LEAVE_PCT:
                # 找离开段：最近一根 up 笔 end > ZG，且后面有 down 笔（回踩）
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
                # 检查回踩：末 down 笔 end >= ZG，且在末 3 笔内
                pullback_ok = False
                pullback_low = None
                if leave_i is not None:
                    for i in range(len(strokes) - 1, leave_i, -1):
                        s = strokes[i]
                        if s.get("direction") == "down" and s.get("end_price") is not None:
                            pullback_low = s["end_price"]
                            if s["end_price"] >= zh_top and i >= len(strokes) - 3:
                                pullback_ok = True
                            break
                # 反弹确认：回踩后第一根 up 笔收盘 > 回踩低点（过滤假突破）
                bounce_ok = True
                if pullback_ok and pullback_low is not None and leave_i is not None:
                    bounce_ok = False
                    for i in range(leave_i, len(strokes)):
                        s = strokes[i]
                        if s.get("direction") == "up" and s.get("end_price") is not None:
                            if s["end_price"] > pullback_low:
                                bounce_ok = True
                            break
                if leave_i is not None and pullback_ok and bounce_ok:
                    vol_ok = not bars or _volume_confirm(len(bars) - 1, 1.2)
                    if vol_ok:
                        # 锚在回踩笔：现价日日变，但结构未变时应同一 anchor
                        pb_stroke = None
                        for i in range(len(strokes) - 1, leave_i, -1):
                            if strokes[i].get("direction") == "down":
                                pb_stroke = strokes[i]
                                break
                        # 信号价用回踩结构锚点，禁止现价冒充（C-01 / deep-card §2.3）
                        buy_points.append(_with_anchor({
                            "type": "三类买",
                            "price": round(float(pullback_low), 4),
                            "confidence": 1,
                        }, pb_stroke or strokes[leave_i]))

    return buy_points

def detect_sell_points(
    strokes: list[dict],
    zones: list[dict],
    last_close: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    macd_divergence_ok: bool = False,
    bars: list[dict] | None = None,
    bc_mode: str | None = None,
    segments: list[dict] | None = None,
) -> list[dict]:
    """检测缠论卖点（与 detect_buy_points 对称，P1 定义）。

    一类卖: 上涨趋势（≥2 不重叠上移中枢）+ 离开段末 up 创新高 + 笔级顶背驰
    类一卖: 单中枢盘整背驰（conf=2）或柱序列弱确认（conf=1）
    二类卖: up_a→down→up_b 且 high_b<high_a 且 high_b>down_low；
           且前置一类 = 时间轴上 up_a 满足历史一类结构（非同帧 sell_points）
    类二卖: 同上结构几何，但历史一类不满足或力度/缩量未齐——卖侧放宽试探档
           （fusion 不强空；正式「二类卖」才进强空路径）
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

    # ── 一类卖：上涨背驰（两档：严格趋势 / 放宽结构）──
    # strict：力度对用最后中枢 b/c；legacy：末两同向 up
    if last_stroke["direction"] == "up" and len(up_strokes) >= 2 and valid_zones:
        prev_up, curr_up, force_kind = resolve_force_stroke_pair(
            strokes, valid_zones, "up", bc_mode=bc_mode, segments=segments
        )
        if prev_up is not None and curr_up is not None:
            price_new_high = curr_up["end_price"] >= prev_up["end_price"]
            last_zone = valid_zones[-1]
            if price_new_high and _stroke_leaves_zone(curr_up, last_zone, "up", strokes):
                area_prev = _stroke_macd_area(bars, prev_up, "pos")
                area_curr = _stroke_macd_area(bars, curr_up, "pos")
                _is_strict_trend = force_kind == "trend"
                if area_prev is not None and area_curr is not None:
                    if _stroke_force_weaker(area_prev, area_curr, "up"):
                        sp_type = "一类卖" if _is_strict_trend else "类一卖"
                        sp_conf = 3 if _is_strict_trend else 2
                        sell_points.append(_with_anchor({
                            "type": sp_type,
                            "price": round(curr_up["end_price"], 4),
                            "confidence": sp_conf,
                            "divergence_kind": force_kind,
                        }, curr_up))
                else:
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
                        sell_points.append(_with_anchor({
                            "type": "类一卖",
                            "price": round(curr_up["end_price"], 4),
                            "confidence": 1,
                            "force_source": "hist_bar_fallback",
                            "divergence_kind": "range",
                        }, curr_up))

    # ── 二类卖：回抽不过前高；要求末笔即为该回抽 up（防粘滞）──
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
                # 正式二类卖：历史一类 + 结构 + (面积/MACD) + 缩量
                # 类二卖：仅结构 + (面积/MACD/缩量任一项)；无趋势中枢也可（卖侧放宽）
                structure_ok = high_b < high_a and high_b > down_low
                if structure_ok:
                    hist_type1_ok = _historical_type1_sell_ok(
                        up_strokes, valid_zones, bars,
                        segments=segments, strokes=strokes,
                    )
                    area_prev = _stroke_macd_area(bars, up_strokes[-2], "pos")
                    area_curr = _stroke_macd_area(bars, up_strokes[-1], "pos")
                    area_ok = _stroke_force_not_much_stronger(area_prev, area_curr, "up")
                    vol_shrink = _volume_shrink_between_strokes(
                        bars, up_strokes[-2], up_strokes[-1]
                    )
                    force_ok = area_ok or macd_divergence_ok
                    if hist_type1_ok and force_ok and vol_shrink:
                        sell_points.append(_with_anchor({
                            "type": "二类卖",
                            "price": round(high_b, 4),
                            "confidence": 2,
                        }, up_strokes[-1]))
                    elif force_ok or vol_shrink:
                        sell_points.append(_with_anchor({
                            "type": "类二卖",
                            "price": round(high_b, 4),
                            "confidence": 1,
                        }, up_strokes[-1]))

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
                        bounce_stroke = None
                        pullback_high = None
                        for i in range(len(strokes) - 1, leave_i, -1):
                            if strokes[i].get("direction") == "up":
                                bounce_stroke = strokes[i]
                                if bounce_stroke.get("end_price") is not None:
                                    pullback_high = bounce_stroke["end_price"]
                                break
                        # 信号价用反抽结构锚点，禁止现价冒充（C-01 / deep-card §2.3）
                        struct_price = (
                            float(pullback_high)
                            if pullback_high is not None
                            else float(last_close)
                        )
                        sell_points.append(_with_anchor({
                            "type": "三类卖",
                            "price": round(struct_price, 4),
                            "confidence": 1,
                        }, bounce_stroke or strokes[leave_i]))

    return sell_points

def detect_divergence(
    bars: list[dict],
    strokes: list[dict] | None = None,
    anchor_bar: int | None = None,
    zones: list[dict] | None = None,
    bc_mode: str | None = None,
    segments: list[dict] | None = None,
) -> dict:
    """背驰检测（P1：优先笔级 MACD 面积；仅无笔/无 index/面积不可算时 fallback 峰谷）。

    某一侧（顶/底）一旦笔级面积可算，该侧以笔级结论为准，不再被峰谷覆盖。
    两侧独立评估，一侧 True 不短路另一侧。

    P3（anchor_bar）：legacy 模式锚定最后中枢后的趋势 legs。
    strict 模式（CHAN_DIVERGENCE_BC=strict）：用最后中枢进入段 b vs 离开段 c；
    缺 b/c 不报该侧笔级背驰，且不做峰谷 fallback（对照更干净）。

    额外字段：bottom_kind / top_kind / kind ∈ {trend, range, none}
    """
    result: dict[str, Any] = {
        "top_divergence": False,
        "bottom_divergence": False,
        "bottom_kind": "none",
        "top_kind": "none",
        "kind": "none",
        "bc_mode": resolve_divergence_bc_mode(bc_mode),
    }
    bottom_evaluated = False
    top_evaluated = False
    mode = result["bc_mode"]

    n = len(bars)
    if n < 5:
        return result

    valid_zones = [z for z in (zones or []) if isinstance(z, dict) and z.get("valid")]

    if strokes:
        prev_d, curr_d, b_kind = resolve_force_stroke_pair(
            strokes, valid_zones, "down", bc_mode=mode, anchor_bar=anchor_bar,
            segments=segments,
        )
        if prev_d is not None and curr_d is not None:
            if curr_d["end_price"] <= prev_d["end_price"]:
                a_prev = _stroke_macd_area(bars, prev_d, "neg")
                a_curr = _stroke_macd_area(bars, curr_d, "neg")
                if a_prev is not None and a_curr is not None:
                    bottom_evaluated = True
                    if "power_price" in prev_d and "power_price" in curr_d:
                        weak = _stroke_force_weaker_multi(
                            prev_d, curr_d, a_prev, a_curr, "down")
                    else:
                        weak = _stroke_force_weaker(a_prev, a_curr, "down")
                    result["bottom_divergence"] = bool(weak)
                    if weak:
                        result["bottom_kind"] = b_kind if b_kind != "none" else "range"

        prev_u, curr_u, t_kind = resolve_force_stroke_pair(
            strokes, valid_zones, "up", bc_mode=mode, anchor_bar=anchor_bar,
            segments=segments,
        )
        if prev_u is not None and curr_u is not None:
            if curr_u["end_price"] >= prev_u["end_price"]:
                a_prev = _stroke_macd_area(bars, prev_u, "pos")
                a_curr = _stroke_macd_area(bars, curr_u, "pos")
                if a_prev is not None and a_curr is not None:
                    top_evaluated = True
                    if "power_price" in prev_u and "power_price" in curr_u:
                        weak = _stroke_force_weaker_multi(
                            prev_u, curr_u, a_prev, a_curr, "up")
                    else:
                        weak = _stroke_force_weaker(a_prev, a_curr, "up")
                    result["top_divergence"] = bool(weak)
                    if weak:
                        result["top_kind"] = t_kind if t_kind != "none" else "range"

    # strict：不做峰谷 fallback，避免与 b/c 口径混杂
    if mode != "strict":
        _fb_start = max(2, anchor_bar) if anchor_bar is not None else max(2, n - CHAN_DIVERGENCE_FALLBACK_WINDOW)
        if not top_evaluated:
            peaks: list[dict[str, Any]] = []
            for i in range(_fb_start, n - 2):
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
                    result["top_kind"] = "range"

        if not bottom_evaluated:
            troughs: list[dict[str, Any]] = []
            for i in range(_fb_start, n - 2):
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
                    result["bottom_kind"] = "range"

    if result["bottom_kind"] == "trend" or result["top_kind"] == "trend":
        result["kind"] = "trend"
    elif result["bottom_kind"] == "range" or result["top_kind"] == "range":
        result["kind"] = "range"
    else:
        result["kind"] = "none"

    return result
