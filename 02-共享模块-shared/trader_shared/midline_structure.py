"""中线关键价独立周线引擎（Weekly Structure Engine v1）。

规格真理：docs/midline-price-engine-plan.md（含 §9 全 A 冻结补丁）。
主路径仅消费 weekly_bars + chanlun_midline（timeframe==weekly 的 strokes/segments/zones）。
禁止成功路径用日线 key_levels / find_key_levels(daily) / stop / stage_based 填四价。
"""
from __future__ import annotations

import os
from typing import Any

from trader_shared.chan_core import unwrap_chan
from trader_shared.light_data import to_float

# ── §9.2 常量冻结 ──────────────────────────────────────────────
MIN_WEEKLY = 26
SWING_N_LIFE = 20
SWING_N_RESIST = 20
SWING_N_PULLBACK = 12
SWING_N_TARGET = 40
MA_WEEKLY = 20
TOUCH_TOL_PCT = 0.015
UNBROKEN_PCT = 0.03
SWING_HALF_WINDOW = 3

# components 闭枚举 §9.7
_STRUCTURE_COMPONENTS = frozenset({
    "seg_low",
    "last_down_stroke_end",
    "zone_zh_bottom",
    "last_up_stroke_end",
    "seg_high",
})


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
        if x != x or x <= 0:
            return None
        return x
    except (TypeError, ValueError):
        return None


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def _daily_fallback_enabled() -> bool:
    """MIDLINE_PRICE_DAILY_FALLBACK 默认 false（§9.2 / §9.8）。"""
    return os.environ.get("MIDLINE_PRICE_DAILY_FALLBACK", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def _extract_hl(bars: list[Any]) -> tuple[list[float], list[float], list[float]]:
    """从 bars 提取 highs / lows / closes（过滤无效）。"""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        h = to_float(bar.get("high"))
        lo = to_float(bar.get("low"))
        c = to_float(bar.get("close"))
        if h is not None and lo is not None and h > 0 and lo > 0:
            highs.append(h)
            lows.append(lo)
            closes.append(c if c is not None and c > 0 else (h + lo) / 2.0)
        elif c is not None and c > 0:
            highs.append(c)
            lows.append(c)
            closes.append(c)
    return highs, lows, closes


def _find_level_with_touches(
    window_highs: list[float],
    window_lows: list[float],
    *,
    find_support: bool,
    half_window: int = SWING_HALF_WINDOW,
    tol_pct: float = TOUCH_TOL_PCT,
    unbroken_pct: float = UNBROKEN_PCT,
) -> float | None:
    """窗口内 2-touch 摆动位（思想同 structure_core.find_key_levels，参数可配）。"""
    if len(window_highs) < 5:
        return None

    source = window_lows if find_support else window_highs
    extrema: list[tuple[int, float]] = []

    for i in range(half_window, len(source) - half_window):
        val = source[i]
        left_vals = source[i - half_window : i]
        right_vals = source[i + 1 : i + half_window + 1]
        if find_support:
            if val <= min(left_vals) and val <= min(right_vals):
                extrema.append((i, val))
        else:
            if val >= max(left_vals) and val >= max(right_vals):
                extrema.append((i, val))

    if not extrema:
        return None

    best_price: float | None = None
    best_count = 0
    for _idx, price in extrema:
        band_lo = price * (1 - tol_pct)
        band_hi = price * (1 + tol_pct)
        touch_count = sum(1 for j in range(len(source)) if band_lo <= source[j] <= band_hi)
        if touch_count < 2:
            continue
        cand_key = (-touch_count, abs(price - source[-1]))
        if find_support:
            if min(window_lows) >= price * (1.0 - unbroken_pct):
                if best_price is None or cand_key < (-best_count, abs(best_price - source[-1])):
                    best_price = price
                    best_count = touch_count
        else:
            if max(window_highs) <= price * (1.0 + unbroken_pct):
                if best_price is None or cand_key < (-best_count, abs(best_price - source[-1])):
                    best_price = price
                    best_count = touch_count

    return _round2(best_price) if best_price is not None else None


def find_swing_levels(
    bars: list[Any],
    *,
    n_life: int = SWING_N_LIFE,
    n_pullback: int = SWING_N_PULLBACK,
    n_target: int = SWING_N_TARGET,
    n_resist: int = SWING_N_RESIST,
) -> dict[str, float | None]:
    """周线摆动支撑/压力（bars 必须是 weekly）。

    返回：
      life_support, pullback_support, resist, target_resist
      以及 min_low_pullback（近 n_pullback 最低，无 2-touch 时用）
    """
    highs, lows, closes = _extract_hl(bars)
    empty = {
        "life_support": None,
        "pullback_support": None,
        "resist": None,
        "target_resist": None,
        "min_low_pullback": None,
    }
    if not highs:
        return empty

    # ATR 自适应容差：周线波动天然比日线大，用周线 ATR 计算
    _atr_pct = 0.02
    if len(highs) >= 5:
        tr_vals = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_vals.append(tr)
        if tr_vals and closes[-1] > 0:
            _atr_pct = (sum(tr_vals) / len(tr_vals)) / closes[-1]
    _adapt_tol = max(TOUCH_TOL_PCT, 0.8 * _atr_pct)
    _adapt_unbroken = max(UNBROKEN_PCT, 1.2 * _atr_pct)

    def _win(n: int) -> tuple[list[float], list[float]]:
        k = min(n, len(highs))
        return highs[-k:], lows[-k:]

    life_h, life_l = _win(n_life)
    pb_h, pb_l = _win(n_pullback)
    res_h, res_l = _win(n_resist)
    tgt_h, tgt_l = _win(n_target)

    life_sup = _find_level_with_touches(life_h, life_l, find_support=True, tol_pct=_adapt_tol, unbroken_pct=_adapt_unbroken)
    if life_sup is None and life_l:
        life_sup = _round2(min(life_l))

    pb_sup = _find_level_with_touches(pb_h, pb_l, find_support=True, tol_pct=_adapt_tol, unbroken_pct=_adapt_unbroken)
    min_low_pb = _round2(min(pb_l)) if pb_l else None
    if pb_sup is None:
        pb_sup = min_low_pb

    resist = _find_level_with_touches(res_h, res_l, find_support=False, tol_pct=_adapt_tol, unbroken_pct=_adapt_unbroken)
    if resist is None and res_h:
        resist = _round2(max(res_h))

    target = _find_level_with_touches(tgt_h, tgt_l, find_support=False, tol_pct=_adapt_tol, unbroken_pct=_adapt_unbroken)
    if target is None and tgt_h:
        target = _round2(max(tgt_h))

    return {
        "life_support": life_sup,
        "pullback_support": pb_sup,
        "resist": resist,
        "target_resist": target,
        "min_low_pullback": min_low_pb,
    }


_FIB_RETRACEMENTS = (0.382, 0.5, 0.618)
_FIB_EXTENSION = 1.382  # 138.2% 延伸位作为目标


def _calc_fibonacci_from_swings(
    highs: list[float],
    lows: list[float],
    *,
    lookback: int = 40,
) -> dict[str, Any]:
    """从周线摆动高低点计算 Fibonacci 回撤位和延伸位。

    找最近一段上升浪（swing_low → swing_high），计算：
    - 38.2%/50%/61.8% 回撤位（黄金购买点候选）
    - 138.2% 延伸位（波段目标）
    """
    n = min(lookback, len(highs))
    if n < 5:
        return {"retracements": {}, "extension": None, "swing_low": None, "swing_high": None}

    win_h = highs[-n:]
    win_l = lows[-n:]

    # 找最近一段上升浪：从最低点到最高点
    # 先找最低点位置，再找其后最高点
    min_idx = 0
    min_val = win_l[0]
    for i in range(len(win_l)):
        if win_l[i] < min_val:
            min_val = win_l[i]
            min_idx = i

    max_idx = min_idx
    max_val = win_h[min_idx]
    for i in range(min_idx, len(win_h)):
        if win_h[i] > max_val:
            max_val = win_h[i]
            max_idx = i

    if max_val <= min_val or max_idx <= min_idx:
        # 没找到有效上升浪，用绝对高低点
        min_val = min(win_l)
        max_val = max(win_h)
        if max_val <= min_val:
            return {"retracements": {}, "extension": None, "swing_low": None, "swing_high": None}

    swing_range = max_val - min_val

    # 回撤位：从 high 往下回撤
    retracements = {}
    for fib in _FIB_RETRACEMENTS:
        level = _round2(max_val - swing_range * fib)
        retracements[f"{fib:.1%}"] = level

    # 延伸位：从 low 往上延伸
    extension = _round2(min_val + swing_range * _FIB_EXTENSION)

    return {
        "retracements": retracements,
        "extension": extension,
        "swing_low": _round2(min_val),
        "swing_high": _round2(max_val),
    }


def _weekly_ma_or_mean5(
    closes: list[float],
) -> tuple[float | None, str]:
    """周 MA20；不足则 5 周收盘均（partial 语义由调用方记）。"""
    if len(closes) >= MA_WEEKLY:
        return _round2(sum(closes[-MA_WEEKLY:]) / MA_WEEKLY), "weekly_ma20"
    if len(closes) >= 5:
        return _round2(sum(closes[-5:]) / 5.0), "weekly_close_mean5"
    if closes:
        return _round2(sum(closes) / len(closes)), "weekly_close_mean5"
    return None, "none"


def _last_by_direction(items: list[dict], direction: str) -> dict | None:
    for it in reversed(items or []):
        if not isinstance(it, dict):
            continue
        if str(it.get("direction") or "") == direction:
            return it
    return None


def _last_valid_zone_zh_bottom(zones: list[Any]) -> float | None:
    """自尾向前第一个 valid zone 的 zh_bottom（禁止 last_valid_zone_* center）。"""
    for z in reversed(zones or []):
        if not isinstance(z, dict):
            continue
        if not z.get("valid"):
            continue
        bottom = _f(z.get("zh_bottom"))
        if bottom is not None:
            return _round2(bottom)
    return None


def build_midline_levels(
    *,
    current: float | None = None,
    weekly_bars: list[Any] | None = None,
    chanlun_midline: dict[str, Any] | None = None,
    wyckoff_midline: dict[str, Any] | None = None,  # P0 旁证，不改写价
    ma_weekly: dict[str, Any] | None = None,
    # 旧参：默认忽略；仅 MIDLINE_PRICE_DAILY_FALLBACK=true 时 degraded
    key_levels: dict[str, Any] | None = None,
    stop: float | None = None,
    stop_losses: dict[str, Any] | None = None,
    stage_stop_price: float | None = None,
    ma20: float | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """中线四价引擎。返回兼容 mid_key_prices 的字段 + engine/quality/components。"""
    del wyckoff_midline  # P0 不兜底改写 life/resist
    current = _f(current)
    bars = list(weekly_bars or [])

    empty_components = {
        "life_line": "none",
        "pullback_low": "none",
        "pullback_high": "none",
        "resist": "none",
        "target": "none",
        "golden_buy": "none",
    }

    def _pack(
        *,
        life_line: float | None,
        pullback_low: float | None,
        pullback_high: float | None,
        resist: float | None,
        target: float | None,
        golden_buy: float | None = None,
        components: dict[str, str],
        source: str,
        quality: str,
        notes_extra: list[str] | None = None,
    ) -> dict[str, Any]:
        if life_line is not None:
            life_line = _round2(life_line)
        if pullback_low is not None:
            pullback_low = _round2(pullback_low)
        if pullback_high is not None:
            pullback_high = _round2(pullback_high)
        if resist is not None:
            resist = _round2(resist)
        if target is not None:
            target = _round2(target)
        if golden_buy is not None:
            golden_buy = _round2(golden_buy)

        line_life = ""
        if life_line is not None and current is not None and current > 0:
            _dist_pct = abs(current - life_line) / current
            if _dist_pct > 0.30:
                # 生命线离现价超过30%，太远无实战意义，不显示
                line_life = ""
            else:
                line_life = f"生命线 {life_line:.2f}（破则中线转弱）"
        elif life_line is not None:
            line_life = f"生命线 {life_line:.2f}（破则中线转弱）"

        line_pullback = ""
        if pullback_low is not None and pullback_high is not None:
            if abs(pullback_high - pullback_low) < 1e-9:
                line_pullback = f"回踩区 {pullback_low:.2f}（到了才谈低吸）"
            else:
                line_pullback = (
                    f"回踩区 {pullback_low:.2f}-{pullback_high:.2f}（到了才谈低吸）"
                )

        # 黄金购买点：50% Fibonacci 回撤位，在回踩区内才显示
        line_golden_buy = ""
        if golden_buy is not None:
            in_zone = (
                pullback_low is not None and pullback_high is not None
                and pullback_low - 0.5 <= golden_buy <= pullback_high + 0.5
            )
            # 判断黄金买点是否和现价非常接近（<2%）
            _gb_near_current = (
                current is not None and current > 0
                and abs(golden_buy - current) / current < 0.02
            )
            if _gb_near_current:
                line_golden_buy = f"黄金买点 {golden_buy:.2f}（50%回撤·现价已到位，等触发信号）"
            elif in_zone:
                line_golden_buy = f"黄金买点 {golden_buy:.2f}（50%回撤·最佳低吸位）"
            else:
                # 不在回踩区内，仅作为参考
                line_golden_buy = f"黄金买点 {golden_buy:.2f}（50%回撤·参考）"

        line_resist = ""
        line_target = ""
        merge_resist_target = False
        if resist is not None and target is not None and abs(resist - target) < 1e-9:
            merge_resist_target = True
            line_resist = f"压力/目标 {resist:.2f}（靠近只减不加；波段上看）"
            line_target = ""
        else:
            if resist is not None:
                line_resist = f"压力 {resist:.2f}（靠近只减不加）"
            if target is not None:
                line_target = f"目标 {target:.2f}（波段上看）"

        notes_parts = [f"source={source}", f"engine=weekly_v1"]
        if notes_extra:
            notes_parts.extend(notes_extra)
        if current is not None and life_line is not None and current < life_line:
            notes_parts.append("already_below_life")

        return {
            "life_line": life_line,
            "pullback_low": pullback_low,
            "pullback_high": pullback_high,
            "resist": resist,
            "target": target,
            "golden_buy": golden_buy,
            "current": current,
            "merge_resist_target": merge_resist_target,
            "line_life": line_life,
            "line_pullback": line_pullback,
            "line_resist": line_resist,
            "line_target": line_target,
            "line_golden_buy": line_golden_buy,
            "notes": ";".join(notes_parts),
            "engine": "weekly_v1",
            "quality": quality,
            "components": components,
            "source": source,
        }

    # ── insufficient：周线缺失 / 过短 ──────────────────────────
    if not bars:
        return _pack(
            life_line=None,
            pullback_low=None,
            pullback_high=None,
            resist=None,
            target=None,
            components=dict(empty_components),
            source="weekly_missing",
            quality="insufficient",
            notes_extra=["weekly_missing"],
        )

    if len(bars) < MIN_WEEKLY:
        return _pack(
            life_line=None,
            pullback_low=None,
            pullback_high=None,
            resist=None,
            target=None,
            components=dict(empty_components),
            source="weekly_too_short",
            quality="insufficient",
            notes_extra=["weekly_too_short"],
        )

    # ── 周线摆动（主路径始终可算）────────────────────────────
    swings = find_swing_levels(bars)
    highs, lows, closes = _extract_hl(bars)

    # 周 MA
    ma_val: float | None = None
    ma_comp = "none"
    if isinstance(ma_weekly, dict):
        ma_val = _f(ma_weekly.get("ma20") or ma_weekly.get(MA_WEEKLY) or ma_weekly.get("MA20"))
        if ma_val is not None:
            ma_comp = "weekly_ma20"
    if ma_val is None:
        ma_val, ma_comp = _weekly_ma_or_mean5(closes)

    # ── chan 仅 timeframe==weekly 才用笔段 ────────────────────
    chan = unwrap_chan(chanlun_midline)
    tf = str(chan.get("timeframe") or "")
    use_structure = tf == "weekly"

    strokes: list[dict] = []
    segments: list[dict] = []
    zones: list[dict] = []
    if use_structure:
        raw_strokes = chan.get("strokes") or []
        raw_segments = chan.get("segments") or []
        raw_zones = chan.get("zones") or []
        strokes = [s for s in raw_strokes if isinstance(s, dict)]
        segments = [s for s in raw_segments if isinstance(s, dict)]
        zones = [z for z in raw_zones if isinstance(z, dict)]

    has_pen_duan = bool(strokes or segments or zones)
    # 无笔段 → weekly_swing_only（即使 timeframe 声称 weekly）
    if use_structure and not has_pen_duan:
        use_structure = False

    components = dict(empty_components)
    notes_extra: list[str] = []

    # ── A. 生命线（§9.3 命中即停；候选仅 price>0）────────────
    life_line: float | None = None
    life_comp = "none"

    if use_structure:
        up_seg = _last_by_direction(segments, "up")
        if up_seg is not None:
            cand = _f(up_seg.get("low"))
            if cand is not None:
                life_line = _round2(cand)
                life_comp = "seg_low"

        if life_line is None:
            down_stroke = _last_by_direction(strokes, "down")
            if down_stroke is not None:
                cand = _f(down_stroke.get("end_price"))
                if cand is not None:
                    life_line = _round2(cand)
                    life_comp = "last_down_stroke_end"

        if life_line is None:
            zb = _last_valid_zone_zh_bottom(zones)
            if zb is not None:
                life_line = zb
                life_comp = "zone_zh_bottom"

    if life_line is None:
        swing_life = swings.get("life_support")
        if swing_life is not None and swing_life > 0:
            life_line = _round2(float(swing_life))
            life_comp = "weekly_swing_n20"

    components["life_line"] = life_comp

    # ── B. 回踩区（§9.4 强制夹 life）─────────────────────────
    pb_lo: float | None = None
    pb_lo_comp = "none"

    if use_structure:
        down_stroke = _last_by_direction(strokes, "down")
        if down_stroke is not None:
            cand = _f(down_stroke.get("end_price"))
            if cand is not None:
                pb_lo = _round2(cand)
                pb_lo_comp = "last_down_stroke_end"

    if pb_lo is None:
        pb_swing = swings.get("pullback_support") or swings.get("min_low_pullback")
        if pb_swing is not None and pb_swing > 0:
            pb_lo = _round2(float(pb_swing))
            # §9.7 闭枚举无 n12；回踩周摆动归入 weekly_swing_n20 族
            pb_lo_comp = "weekly_swing_n20"

    if life_line is not None and pb_lo is not None:
        pb_lo = _round2(max(pb_lo, life_line))
    elif life_line is not None and pb_lo is None:
        pb_lo = life_line
        pb_lo_comp = life_comp

    pb_hi: float | None = None
    pb_hi_comp = "none"
    if pb_lo is not None:
        if ma_val is not None:
            pb_hi = _round2(max(pb_lo, ma_val))
            pb_hi_comp = ma_comp
        else:
            pb_hi = _round2(pb_lo)
            pb_hi_comp = pb_lo_comp
        if pb_hi < pb_lo:
            pb_hi = pb_lo

    components["pullback_low"] = pb_lo_comp
    components["pullback_high"] = pb_hi_comp

    # ── C/D. 压力 / 目标（P0 无 fib）§9.5 ────────────────────
    resist: float | None = None
    resist_comp = "none"
    target: float | None = None
    target_comp = "none"

    if use_structure:
        up_stroke = _last_by_direction(strokes, "up")
        if up_stroke is not None:
            cand = _f(up_stroke.get("end_price"))
            if cand is not None:
                resist = _round2(cand)
                resist_comp = "last_up_stroke_end"
        if resist is None:
            up_seg = _last_by_direction(segments, "up")
            if up_seg is not None:
                cand = _f(up_seg.get("high"))
                if cand is not None:
                    resist = _round2(cand)
                    resist_comp = "seg_high"

        up_seg_for_tgt = _last_by_direction(segments, "up")
        if up_seg_for_tgt is not None:
            cand = _f(up_seg_for_tgt.get("high"))
            if cand is not None:
                target = _round2(cand)
                target_comp = "seg_high"

    if resist is None:
        sw_r = swings.get("resist")
        if sw_r is not None and sw_r > 0:
            resist = _round2(float(sw_r))
            resist_comp = "weekly_swing_n20_high"

    if target is None:
        sw_t = swings.get("target_resist")
        if sw_t is not None and sw_t > 0:
            target = _round2(float(sw_t))
            target_comp = "weekly_swing_n40_high"

    components["resist"] = resist_comp
    components["target"] = target_comp

    # ── quality / source ────────────────────────────────────
    if use_structure and has_pen_duan:
        source = "weekly_structure"
        struct_hit = any(
            components.get(k) in _STRUCTURE_COMPONENTS
            for k in ("life_line", "resist", "target", "pullback_low")
        )
        # full：至少 life 或 resist 的 components 属于笔段/zone 源
        life_or_resist_struct = (
            components.get("life_line") in _STRUCTURE_COMPONENTS
            or components.get("resist") in _STRUCTURE_COMPONENTS
        )
        quality = "full" if life_or_resist_struct else "partial"
        if not struct_hit:
            quality = "partial"
    else:
        source = "weekly_swing_only"
        quality = "partial"
        if tf and tf != "weekly":
            notes_extra.append(f"chan_tf={tf}")

    if ma_comp == "weekly_close_mean5" and quality == "full":
        # MA 降级不单独把 full 打成 partial；仅结构决定
        pass

    # ── Fibonacci：黄金购买点 + 延伸目标 ────────────────────
    golden_buy: float | None = None
    golden_buy_comp = "none"
    fib_result = _calc_fibonacci_from_swings(highs, lows, lookback=40)
    fib_retrs = fib_result.get("retracements") or {}
    fib_ext = fib_result.get("extension")

    # 黄金购买点：50% 回撤位
    gb_50 = fib_retrs.get("50.0%")
    if gb_50 is not None and gb_50 > 0:
        golden_buy = gb_50
        golden_buy_comp = "fib_50_retracement"

    # 目标：优先 Fibonacci 138.2% 延伸位（有预测意义），高于原历史高点目标
    if fib_ext is not None and fib_ext > 0:
        if target is None or fib_ext > target:
            target = fib_ext
            target_comp = "fib_138_extension"

    components["golden_buy"] = golden_buy_comp

    return _pack(
        life_line=life_line,
        pullback_low=pb_lo,
        pullback_high=pb_hi,
        resist=resist,
        target=target,
        golden_buy=golden_buy,
        components=components,
        source=source,
        quality=quality,
        notes_extra=notes_extra or None,
    )


def build_degraded_daily_key_levels(
    *,
    current: float | None = None,
    key_levels: dict[str, Any] | None = None,
    ma20: float | None = None,
    stop: float | None = None,
    stop_losses: dict[str, Any] | None = None,
    stage_stop_price: float | None = None,
) -> dict[str, Any]:
    """显式日线降级（仅开关开启时调用）。source=degraded_daily_key_levels。"""
    current = _f(current)
    ma20 = _f(ma20)
    stop = _f(stop)
    kl = key_levels or {}

    life_line = _f(kl.get("mid_support"))
    life_source = "mid_support" if life_line else ""
    if life_line is None:
        stage_px = _f(stage_stop_price)
        if stage_px is None and isinstance(stop_losses, dict):
            sb = stop_losses.get("stage_based")
            if isinstance(sb, dict):
                stage_px = _f(sb.get("price"))
            else:
                stage_px = _f(sb)
        if stage_px is not None:
            life_line = stage_px
            life_source = "stage_based"
    if life_line is None and stop is not None:
        life_line = stop
        life_source = "stop"

    pb_lo = _f(kl.get("short_support"))
    pb_hi: float | None = None
    if pb_lo is not None:
        if ma20 is not None:
            pb_hi = _round2(max(pb_lo, ma20))
        else:
            pb_hi = _round2(pb_lo)
        pb_lo = _round2(pb_lo)
        if pb_hi < pb_lo:
            pb_lo, pb_hi = pb_hi, pb_lo

    resist = _f(kl.get("mid_resist"))
    target = _f(kl.get("long_resist"))
    if resist is not None:
        resist = _round2(resist)
    if target is not None:
        target = _round2(target)
    if life_line is not None:
        life_line = _round2(life_line)

    line_life = ""
    if life_line is not None:
        line_life = f"生命线 {life_line:.2f}（破则中线转弱）"

    line_pullback = ""
    if pb_lo is not None and pb_hi is not None:
        if abs(pb_hi - pb_lo) < 1e-9:
            line_pullback = f"回踩区 {pb_lo:.2f}（到了才谈低吸）"
        else:
            line_pullback = f"回踩区 {pb_lo:.2f}-{pb_hi:.2f}（到了才谈低吸）"

    line_resist = ""
    line_target = ""
    merge_resist_target = False
    if resist is not None and target is not None and abs(resist - target) < 1e-9:
        merge_resist_target = True
        line_resist = f"压力/目标 {resist:.2f}（靠近只减不加；波段上看）"
        line_target = ""
    else:
        if resist is not None:
            line_resist = f"压力 {resist:.2f}（靠近只减不加）"
        if target is not None:
            line_target = f"目标 {target:.2f}（波段上看）"

    notes_parts = ["source=degraded_daily_key_levels", "engine=weekly_v1"]
    if life_source:
        notes_parts.append(f"life={life_source}")
    if current is not None and life_line is not None and current < life_line:
        notes_parts.append("already_below_life")

    return {
        "life_line": life_line,
        "pullback_low": pb_lo,
        "pullback_high": pb_hi,
        "resist": resist,
        "target": target,
        "current": current,
        "merge_resist_target": merge_resist_target,
        "line_life": line_life,
        "line_pullback": line_pullback,
        "line_resist": line_resist,
        "line_target": line_target,
        "notes": ";".join(notes_parts),
        "engine": "weekly_v1",
        "quality": "partial",
        "source": "degraded_daily_key_levels",
        "components": {
            "life_line": life_source or "none",
            "pullback_low": "short_support" if pb_lo is not None else "none",
            "pullback_high": "ma20" if pb_hi is not None and ma20 is not None else "none",
            "resist": "mid_resist" if resist is not None else "none",
            "target": "long_resist" if target is not None else "none",
        },
    }
