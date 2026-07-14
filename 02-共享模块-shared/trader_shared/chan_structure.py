"""Chan structure classification + buy/sell points + divergence."""
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
        CHAN_DIVERGENCE_FALLBACK_WINDOW,
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

    拓扑规则（中枢合并版）：
    - strokes < 3 → 无结构
    - 0 个合并中枢 → 单边 / 无结构（原典：0 中枢即无结构，不谎报盘整）
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
            return _ok("无结构")  # 原典：0 中枢即无结构，不谎报盘整
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

def _zone_last_end_index(zone: dict) -> int:
    """取中枢末端笔的 end_index，用于「离开段」约束判断。

    兼容两种中枢结构：
    - 合并中枢（build_zones merge=True，默认）：顶层无 strokes，末端落在 members 的最后一笔；
    - 原始滑动窗口中枢（merge=False）：顶层直接带 strokes。
    返回所有成员笔中最大的 end_index；无任何有效笔返回 -1。

    修复 D4：旧实现直接读 zone.get("strokes")，但默认 merge=True 产出的合并中枢
    顶层没有 strokes 字段，导致 _last_zone_end 恒为 -1，"背驰须发生在离开段"
    的约束被静默禁用，可能产出假一类买卖。
    """
    candidates: list[int] = []
    members = zone.get("members") or [zone]
    for m in members:
        for s in m.get("strokes", []):
            if isinstance(s, dict):
                e = s.get("end_index", -1)
                if e >= 0:
                    candidates.append(e)
    return max(candidates) if candidates else -1

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

    # ── P1 一类买：下跌趋势背驰（严格缠论）──
    # 删除旧「仅 MACD 为负 + 放量 + MA20」无中枢假一类
    # 严格化：一类买 = 下跌趋势背驰转折点，须趋势（≥2 个下移中枢），盘整背驰不算；
    #          且最后一段 down 必须在最后一个中枢之后（背驰发生在离开段）。
    _is_down_trend = len(valid_zones) >= 2 and valid_zones[-1]["zh_top"] < valid_zones[-2]["zh_top"]
    if (
        last_stroke["direction"] == "down"
        and _is_down_trend
        and len(down_strokes) >= 2
    ):
        _last_zone_end = _zone_last_end_index(valid_zones[-1]) if valid_zones else -1
        if down_strokes[-1].get("start_index", 0) > _last_zone_end:
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
                # 严格缠论二类买：必须前置一类买（无一类买则无二类买），且回抽不破一类买低点
                _first_buy = next((bp for bp in buy_points if bp["type"] == "一类买"), None)
                if _first_buy is not None:
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
                        else:
                            # 类二买：结构同二买（down→up→down + low抬升 + 有一买前置），
                            # 但面积对比不满足减弱条件（area_ok=False）或 MACD 未确认，
                            # 视为二买的弱化版。
                            buy_points.append({
                                "type": "类二买",
                                "price": round(low_b, 4),
                                "confidence": 1,
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

    # ── P1 一类卖：上涨趋势背驰（严格缠论）──
    # 删除无中枢降级一类卖
    # 严格化：一类卖 = 上涨趋势背驰，须趋势（≥2 个上移中枢）；最后 up 在最后中枢之后
    _is_up_trend = len(valid_zones) >= 2 and valid_zones[-1]["zh_bottom"] > valid_zones[-2]["zh_bottom"]
    if (
        last_stroke["direction"] == "up"
        and _is_up_trend
        and len(up_strokes) >= 2
    ):
        _last_zone_end_s = _zone_last_end_index(valid_zones[-1]) if valid_zones else -1
        if up_strokes[-1].get("start_index", 0) > _last_zone_end_s:
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
                # 严格缠论二类卖：必须前置一类卖（无一类卖则无二类卖），且反弹不过一类卖高点
                _first_sell = next((bp for bp in sell_points if bp["type"] == "一类卖"), None)
                if _first_sell is not None:
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

def detect_divergence(
    bars: list[dict],
    strokes: list[dict] | None = None,
    anchor_bar: int | None = None,
) -> dict:
    """背驰检测（P1：优先笔级 MACD 面积；仅无笔/无 index/面积不可算时 fallback 峰谷）。

    某一侧（顶/底）一旦笔级面积可算，该侧以笔级结论为准，不再被峰谷覆盖。
    两侧独立评估，一侧 True 不短路另一侧。

    P3（anchor_bar）：背驰锚定「最后中枢」而非固定窗口。传入最后中枢右边界的
    bar 索引后，笔级比较只取 end_index >= anchor_bar 的趋势 legs（离开段 c 与其
    次级别同向段），fallback 峰谷窗口也从 anchor_bar 起算，杜绝陈旧历史污染现状。
    anchor_bar 为 None 时回退到 P0b 的近期窗口逻辑（向后兼容）。
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

        # P3：只保留最后中枢之后的趋势 legs；锚定后不足两段则回退全序列，避免漏判
        if anchor_bar is not None:
            down_anchored = [s for s in down_strokes if to_float(s.get("end_index")) >= anchor_bar]
            up_anchored = [s for s in up_strokes if to_float(s.get("end_index")) >= anchor_bar]
            if len(down_anchored) >= 2:
                down_strokes = down_anchored
            if len(up_anchored) >= 2:
                up_strokes = up_anchored

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

    # ── fallback：仅对「笔级未评估」的一侧使用【近期】峰谷（不扫全图历史）──
    # P3：若已锚定最后中枢，从 anchor_bar 起算；否则扫最近 CHAN_DIVERGENCE_FALLBACK_WINDOW 根，
    # 避免把几年前的旧背离当现状。
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

    return result
