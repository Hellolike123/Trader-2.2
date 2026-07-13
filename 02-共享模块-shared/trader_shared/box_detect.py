#!/usr/bin/env python3
"""箱体检测独立模块 (Box / Range Detection Engine).

严格按 A股 箱体震荡实务规则实现，作为独立原子模块供组合策略报告消费：

箱体有效性
  - 周期 ≥ 40 交易日
  - 振幅 ≤ 20%
  - 上下沿各 ≥ 3 次触及且基本平行（均线缠绕走平，即将变盘）
  - MA20 走平 / 向上（排除高位出货箱）

上下沿
  - 平行线间反复震荡；下沿=支撑、上沿=压力
  - 非单点，是「多次验证的轨道」

向上突破确认
  - 收盘站上沿 + 连续 2 日站稳 + 量 ≥ 1.5 倍近期均量（温和放量，非单日天量）
  - 突破当日只打底仓，回踩上沿缩量企稳再加仓

向下破位
  - 收盘跌破下沿 + 连续 2 日收不回
  - 放量 ≥ 1.5 倍（恐慌出逃），但缩量阴跌击穿也算有效破位
  - 破位不抄底

假突破识别
  - 单日巨量冲上沿、次日快速缩量跌回 = 诱多
  - 冲高收长上影
  - 3% 缓冲带：真突破持续远离、假突破快速回箱内
  - 高开 > 5% 脉冲 = 诱多

量能上下文
  - 堆量突破（持续 > 1.3 倍 20 日均量）
  - 缩量破位
  - 均衡不变盘（围绕 20 日均量小幅波动 → 箱体延续）

风控
  - 止损 = 箱体下沿下方（跌破即离场）
  - 突破后止损上移至原上沿
  - 单标的不超 3 成仓（由仓位模块处理，本模块只给价位）

输出结构化 dict，供组合报告「各自输出 + 价位矩阵合成」消费。
"""
from __future__ import annotations

from typing import Any, List, Optional

from trader_shared.light_data import to_float
from trader_shared.pattern_core import _find_local_extrema


# ── 阈值（A股 箱体实务通用值）──────────────────────────────────
WINDOW_DAYS = 120          # 回看窗口，找轨道
MIN_SPAN_DAYS = 40         # 箱体本身最小跨度
MAX_AMPLITUDE_PCT = 20.0   # 最大振幅（超过视为趋势而非箱体）
MIN_TOUCHES = 3            # 上下沿最少触及次数
TOUCH_TOL_PCT = 0.015      # 触及聚类容差（1.5%）
MAX_RAIL_SLOPE_PCT = 10.0  # 轨道斜率上限（平行校验，10% 内）
BUFFER_PCT = 0.03          # 3% 缓冲带（真假突破判定）
BREAKOUT_VOL_RATIO = 1.5   # 突破量能确认（≥1.5 倍 20 日均量）
ACCUM_VOL_RATIO = 1.3      # 堆量阈值（≥1.3 倍视为持续放量）
HOLD_DAYS_CONFIRM = 2      # 站稳 / 收不回 所需连续天数
STOP_BUFFER_PCT = 0.01     # 止损下沿下方缓冲（1%）


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def _extract_bars(bars: list[Any]) -> tuple[
    List[float], List[float], List[float], List[float]
]:
    """从 bars 提取 highs / lows / closes / volumes（过滤无效）。"""
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    vols: List[float] = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        h = to_float(bar.get("high"))
        lo = to_float(bar.get("low"))
        c = to_float(bar.get("close"))
        v = to_float(bar.get("volume"))
        if None in (h, lo, c) or h <= 0 or lo <= 0:
            continue
        highs.append(h)
        lows.append(lo)
        closes.append(c)
        vols.append(v if v is not None and v > 0 else 0.0)
    return highs, lows, closes, vols


def _cluster_rail(points: List[tuple[int, float]], tol_pct: float) -> Optional[
    tuple[float, int, List[tuple[int, float]]]
]:
    """把局部极值点 (idx, value) 按价格容差聚成轨道，返回 (均值价, 触及数, 点集)。

    取点数最多的簇为有效轨道。返回 None 表示无足够触点。
    """
    if not points:
        return None
    # 按价格排序后贪心聚类
    srt = sorted(points, key=lambda p: p[1])
    clusters: List[List[tuple[int, float]]] = []
    cur: List[tuple[int, float]] = [srt[0]]
    cur_mean = srt[0][1]
    for p in srt[1:]:
        if abs(p[1] - cur_mean) <= tol_pct * cur_mean:
            cur.append(p)
            cur_mean = sum(x[1] for x in cur) / len(cur)
        else:
            clusters.append(cur)
            cur = [p]
            cur_mean = p[1]
    clusters.append(cur)
    # 取点数最多的簇
    best = max(clusters, key=len)
    mean_price = sum(x[1] for x in best) / len(best)
    return _round2(mean_price), len(best), best


def _rail_slope_pct(rail_points: List[tuple[int, float]]) -> float:
    """轨道斜率百分比：回归 value ~ idx，斜率 × 跨度 / 均值 × 100。"""
    n = len(rail_points)
    if n < 2:
        return 0.0
    idxs = [p[0] for p in rail_points]
    vals = [p[1] for p in rail_points]
    mean_i = sum(idxs) / n
    mean_v = sum(vals) / n
    cov = sum((idxs[i] - mean_i) * (vals[i] - mean_v) for i in range(n))
    var = sum((idxs[i] - mean_i) ** 2 for i in range(n))
    if var == 0:
        return 0.0
    slope = cov / var
    span = max(idxs) - min(idxs)
    return slope * span / mean_v * 100.0


def _ma20(closes: List[float]) -> Optional[float]:
    if len(closes) < 20:
        return None
    return sum(closes[-20:]) / 20


def detect_box(
    bars: list[Any],
    current: Optional[float] = None,
    ma20_vol: Optional[float] = None,
    window_days: int = WINDOW_DAYS,
) -> dict:
    """箱体检测主函数。

    Args:
        bars: OHLCV dict 列表，含 high/low/close/volume（按时间升序）
        current: 最新收盘价（缺省取 bars 末根 close）
        ma20_vol: 20 日平均成交量（缺省由 bars 末 20 根自算）
        window_days: 回看窗口（默认 120 日）

    Returns:
        结构化箱体结果 dict（详见模块 docstring 输出字段）
    """
    highs, lows, closes, vols = _extract_bars(bars)
    if len(closes) < MIN_SPAN_DAYS:
        return _empty_box("数据不足，无法检测箱体")

    win = min(window_days, len(closes))
    h_win = highs[-win:]
    l_win = lows[-win:]
    c_win = closes[-win:]
    v_win = vols[-win:]

    if current is None:
        current = c_win[-1]
    if ma20_vol is None:
        ma20_vol = _ma20(v_win) if len(v_win) >= 20 else (sum(v_win) / len(v_win) if v_win else 0.0)

    # ── 1. 找局部高/低点（轨道候选）──
    # 顶轨 = highs 序列的局部极大；底轨 = lows 序列的局部极小
    # 顶轨 = 高序列的局部极大（返回第二项 highs）
    _, hi_maxima = _find_local_extrema(h_win, min_gap=3)
    # 底轨 = 低序列的局部极小（返回第一项 lows）
    lo_minima, _ = _find_local_extrema(l_win, min_gap=3)

    top_cluster = _cluster_rail(hi_maxima, TOUCH_TOL_PCT)
    bot_cluster = _cluster_rail(lo_minima, TOUCH_TOL_PCT)

    if top_cluster is None or bot_cluster is None:
        return _empty_box("未找到满足触及次数的上下沿轨道")
    top, top_touches, top_pts = top_cluster
    bottom, bot_touches, bot_pts = bot_cluster

    if top <= bottom:
        return _empty_box("上下沿交叉，不构成箱体")

    # ── 2. 有效性校验 ──
    valid_reasons: List[str] = []
    span_days = (max(top_pts[-1][0], bot_pts[-1][0])
                 - min(top_pts[0][0], bot_pts[0][0])) + 1
    amplitude_pct = (top - bottom) / bottom * 100.0

    ok_span = span_days >= MIN_SPAN_DAYS
    ok_amp = amplitude_pct <= MAX_AMPLITUDE_PCT
    ok_top_touch = top_touches >= MIN_TOUCHES
    ok_bot_touch = bot_touches >= MIN_TOUCHES
    top_slope = abs(_rail_slope_pct(top_pts))
    bot_slope = abs(_rail_slope_pct(bot_pts))
    ok_parallel = top_slope <= MAX_RAIL_SLOPE_PCT and bot_slope <= MAX_RAIL_SLOPE_PCT

    # MA20 走平/向上（排除高位出货箱）
    ma20_first = _ma20(c_win[:20]) if len(c_win) >= 40 else None
    ma20_last = _ma20(c_win[-20:]) if len(c_win) >= 20 else None
    ok_ma = True
    if ma20_first and ma20_last:
        ok_ma = (ma20_last / ma20_first - 1.0) >= -0.05  # 区间内跌幅不超 5%

    valid = ok_span and ok_amp and ok_top_touch and ok_bot_touch and ok_parallel and ok_ma
    if ok_span:
        valid_reasons.append(f"跨度 {span_days} 日≥{MIN_SPAN_DAYS}日")
    if ok_amp:
        valid_reasons.append(f"振幅 {amplitude_pct:.1f}%≤{MAX_AMPLITUDE_PCT:.0f}%")
    if ok_top_touch:
        valid_reasons.append(f"上沿触及 {top_touches} 次≥{MIN_TOUCHES}次")
    if ok_bot_touch:
        valid_reasons.append(f"下沿触及 {bot_touches} 次≥{MIN_TOUCHES}次")
    if ok_parallel:
        valid_reasons.append(f"上下沿基本平行(斜率{top_slope:.1f}%/{bot_slope:.1f}%)")
    if ok_ma:
        valid_reasons.append("MA20 走平/向上")

    # ── 3. 状态机 ──
    top_break = top * (1 + BUFFER_PCT)
    bot_break = bottom * (1 - BUFFER_PCT)

    state, breakout = _classify_state(
        c_win, v_win, top, bottom, top_break, bot_break, ma20_vol
    )

    # ── 4. 假突破识别 ──
    false_risk = _detect_false_breakout(
        h_win, c_win, v_win, top, top_break, ma20_vol
    )

    # ── 5. 量能上下文 ──
    vol_ctx = _volume_context(v_win, ma20_vol, breakout["direction"])

    # ── 6. 止损位（下沿下方缓冲）──
    stop_loss = _round2(bottom * (1 - STOP_BUFFER_PCT))

    # ── 7. 现价位置 ──
    if top > bottom:
        pos = (current - bottom) / (top - bottom) * 100.0
        position_pct = max(0.0, min(100.0, pos))
    else:
        position_pct = 0.0

    note = _build_note(
        top, bottom, amplitude_pct, span_days, state, breakout,
        false_risk, vol_ctx, position_pct, valid,
    )

    return {
        "found": True,
        "valid": valid,
        "valid_reasons": valid_reasons,
        "top": top,
        "bottom": bottom,
        "amplitude_pct": _round2(amplitude_pct),
        "span_days": span_days,
        "top_touches": top_touches,
        "bottom_touches": bot_touches,
        "position_pct": _round2(position_pct),
        "state": state,
        "breakout": breakout,
        "false_breakout_risk": false_risk,
        "volume_context": vol_ctx,
        "stop_loss": stop_loss,
        "note": note,
    }


def _classify_state(
    c_win: List[float],
    v_win: List[float],
    top: float,
    bottom: float,
    top_break: float,
    bot_break: float,
    ma20_vol: float,
) -> tuple[str, dict]:
    """从末根向前数连续站在突破带外的天数，判定状态 + 突破结构。"""
    n = len(c_win)
    # 向上连续天数（收盘 > top_break）
    up_run = 0
    for i in range(n - 1, -1, -1):
        if c_win[i] > top_break:
            up_run += 1
        else:
            break
    # 向下连续天数（收盘 < bot_break）
    dn_run = 0
    for i in range(n - 1, -1, -1):
        if c_win[i] < bot_break:
            dn_run += 1
        else:
            break

    breakout_vol = v_win[-1] / ma20_vol if ma20_vol and ma20_vol > 0 else 1.0

    # 优先判向上（A股 箱体向上突破是主要机会）
    if up_run >= 1:
        confirmed = up_run >= HOLD_DAYS_CONFIRM and breakout_vol >= BREAKOUT_VOL_RATIO
        direction = "up"
        state = "up_confirmed" if confirmed else "up_pending"
        return state, {
            "direction": direction,
            "hold_days": up_run,
            "vol_ratio": _round2(breakout_vol),
            "confirm": confirmed,
        }
    if dn_run >= 1:
        # 向下破位：缩量阴跌也算有效，仅要求连续 2 日
        confirmed = dn_run >= HOLD_DAYS_CONFIRM
        direction = "down"
        state = "down_confirmed" if confirmed else "down_pending"
        return state, {
            "direction": direction,
            "hold_days": dn_run,
            "vol_ratio": _round2(breakout_vol),
            "confirm": confirmed,
        }
    return "inside", {
        "direction": "none",
        "hold_days": 0,
        "vol_ratio": _round2(breakout_vol),
        "confirm": False,
    }


def _detect_false_breakout(
    h_win: List[float],
    c_win: List[float],
    v_win: List[float],
    top: float,
    top_break: float,
    ma20_vol: float,
) -> bool:
    """假突破识别：
    - 末根/近根冲高刺穿上沿(top_break)但收盘回落，且为单日量能脉冲（非堆量）
    - 长上影（上影 > 实体 2 倍且 > 区间 50%）
    - 高开 > 5% 脉冲（近似：当日振幅大且收阴）
    """
    n = len(c_win)
    if n < 2:
        return False

    # 看末根：是否刺穿上沿但收盘回落
    last_high = h_win[-1]
    last_close = c_win[-1]
    last_vol = v_win[-1]
    poked = last_high > top and last_close <= top  # 刺穿未站上
    spike = (last_vol / ma20_vol) >= 2.0 if ma20_vol and ma20_vol > 0 else False
    # 长上影：用 high-close 近似（无 open 时）
    upper_shadow = (last_high - last_close) / last_close if last_close > 0 else 0.0
    long_upper = upper_shadow >= 0.03  # 上影 ≥ 3% 视为长上影

    if poked and (spike or long_upper):
        return True

    # 往前找最近一次「站上 top 但次日跌回」的诱多
    for i in range(max(0, n - 10), n - 1):
        if c_win[i] > top and c_win[i + 1] < top:
            day_vol = v_win[i]
            is_spike = (day_vol / ma20_vol) >= 2.0 if ma20_vol and ma20_vol > 0 else False
            # 单日脉冲（非持续堆量）：前一日量能正常
            prev_vol = v_win[i - 1] if i > 0 else day_vol
            not_accum = is_spike and (
                (prev_vol / ma20_vol) < ACCUM_VOL_RATIO if ma20_vol and ma20_vol > 0 else True
            )
            if not_accum:
                return True
    return False


def _volume_context(
    v_win: List[float], ma20_vol: float, direction: str
) -> str:
    """量能上下文：堆量突破 / 缩量破位 / 均衡不变盘。"""
    if ma20_vol is None or ma20_vol <= 0:
        return "balanced"
    recent = v_win[-3:]
    avg_recent = sum(recent) / len(recent) if recent else 0.0
    ratio = avg_recent / ma20_vol
    if direction == "up":
        return "accumulate" if ratio >= ACCUM_VOL_RATIO else "balanced"
    if direction == "down":
        # 缩量阴跌也算有效破位 → 量能偏低即 shrink_break
        return "shrink_break" if ratio <= ACCUM_VOL_RATIO else "balanced"
    # inside
    if ratio >= ACCUM_VOL_RATIO:
        return "accumulate"
    if ratio <= 0.8:
        return "shrink_break"
    return "balanced"


def _build_note(
    top: float, bottom: float, amp: float, span: int, state: str,
    breakout: dict, false_risk: bool, vol_ctx: str,
    position_pct: float, valid: bool,
) -> str:
    parts = [
        f"箱体 {bottom:.2f}–{top:.2f}（振幅{amp:.1f}%，跨度{span}日）",
        f"状态：{state}",
    ]
    if breakout["direction"] != "none":
        parts.append(
            f"突破：{breakout['direction']} 站稳{breakout['hold_days']}日 "
            f"量比{breakout['vol_ratio']}x {'已确认' if breakout['confirm'] else '待确认'}"
        )
    if false_risk:
        parts.append("⚠ 假突破风险（刺穿回落/长上影/单日脉冲）")
    parts.append(f"量能：{vol_ctx}")
    parts.append(f"现价位于箱体 {position_pct:.0f}%")
    if not valid:
        parts.append("（有效性未全部满足，仅供参考）")
    return "；".join(parts)


def _empty_box(reason: str) -> dict:
    return {
        "found": False,
        "valid": False,
        "valid_reasons": [],
        "top": None,
        "bottom": None,
        "amplitude_pct": None,
        "span_days": 0,
        "top_touches": 0,
        "bottom_touches": 0,
        "position_pct": None,
        "state": "none",
        "breakout": {"direction": "none", "hold_days": 0, "vol_ratio": 0.0, "confirm": False},
        "false_breakout_risk": False,
        "volume_context": "balanced",
        "stop_loss": None,
        "note": reason,
    }
