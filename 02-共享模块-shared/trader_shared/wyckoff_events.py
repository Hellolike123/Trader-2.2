"""Wyckoff event detectors (leaf)."""
from __future__ import annotations

import json
import os
from typing import Any

from trader_shared.light_data import to_float

# ── Wyckoff 打分权重常量（均衡型） ----
# 优雅动态导入配置，提供强兼容性的 fallback 默认值
try:
    from trader_shared.config import (
        WYCKOFF_MIN_BARS,
        WYCKOFF_BC_VOL_RATIO_THRESHOLD,
        WYCKOFF_BC_CHANGE_THRESHOLD,
        WYCKOFF_BC_UPPER_SHADOW_RATIO,
        WYCKOFF_BC_MIN_POS_PCT,
        WYCKOFF_SOW_SUPPORT_LOOKBACK,
        WYCKOFF_SOW_VOL_RATIO_THRESHOLD,
        WYCKOFF_SOW_CONSECUTIVE_DAYS,
        WYCKOFF_SPRING_SUPPORT_LOOKBACK,
        WYCKOFF_SPRING_RECLAIM_RATIO,
        WYCKOFF_SPRING_ATR_MULTIPLE,
        WYCKOFF_SPRING_BULLISH_VOL_RATIO,
        WYCKOFF_SPRING_LOW_VOL_RATIO,
        WYCKOFF_UTAD_BREAKOUT_RATIO,
        WYCKOFF_UTAD_RECLAIM_RATIO,
        WYCKOFF_UT_VOL_RATIO,
        WYCKOFF_DIVERGENCE_BARS,
        WYCKOFF_DIVERGENCE_RATIO,
        WYCKOFF_PHASE_LOOKBACK,
        WYCKOFF_VSA_AVG_SPREAD_PERIOD,
        # Wyckoff Score 权重
        WYCKOFF_SCORE_SPRING,
        WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS,
        WYCKOFF_SCORE_BULLISH_DIV,
        WYCKOFF_SCORE_UT,
        WYCKOFF_SCORE_BEARISH_DIV,
        WYCKOFF_SCORE_BC,
        WYCKOFF_SCORE_SOW,
        WYCKOFF_SCORE_MAX_ABS,
        # 新增经典信号权重
        WYCKOFF_SCORE_AR,
        WYCKOFF_SCORE_SOS,
        WYCKOFF_SCORE_ST,
        WYCKOFF_SCORE_LPS,
        WYCKOFF_SCORE_LPSY,
        # P2/P3 新增
        WYCKOFF_SCORE_COMPRESSION,
        WYCKOFF_SCORE_TREND_PB,
        WYCKOFF_COMPRESSION_LOOKBACK,
        WYCKOFF_COMPRESSION_ATR_QUANTILE,
        WYCKOFF_COMPRESSION_VOL_RATIO,
        WYCKOFF_COMPRESSION_VOL_REF_WINDOW,
        WYCKOFF_TREND_PB_LOOKBACK,
        WYCKOFF_TREND_PB_MIN_PULLBACK,
        WYCKOFF_TREND_PB_MAX_PULLBACK,
        WYCKOFF_TREND_PB_VOL_SHRINK,
        WYCKOFF_TREND_PB_MA_WINDOW,
        # P0-3 Trading Range 识别层常量
        WYCKOFF_TR_LOOKBACK,
        WYCKOFF_TR_MIN_WIDTH,
        WYCKOFF_TR_AMPLITUDE_MAX,
        WYCKOFF_TR_AMPLITUDE_MIN,
        WYCKOFF_TR_QUALITY_WIDTH_REF,
        WYCKOFF_TR_FLOOR_PCT,
        WYCKOFF_TR_CEIL_PCT,
        # P0-4 Spring/Upthrust 真假分级常量
        WYCKOFF_SPRING_STRONG_DEPTH_PCT,
        WYCKOFF_SPRING_WEAK_DEPTH_PCT,
        WYCKOFF_SPRING_STRONG_RECLAIM,
        WYCKOFF_UT_STRONG_DEPTH_PCT,
        WYCKOFF_UT_WEAK_DEPTH_PCT,
        WYCKOFF_UT_STRONG_RECLAIM,
        # P0-5 事件簇确认常量
        WYCKOFF_CLUSTER_LOOKBACK,
        WYCKOFF_CLUSTER_MIN_GAP,
    )
except ImportError:
    WYCKOFF_MIN_BARS = 15
    WYCKOFF_BC_VOL_RATIO_THRESHOLD = 1.8  # must match config.py
    WYCKOFF_BC_CHANGE_THRESHOLD = 1.0
    WYCKOFF_BC_UPPER_SHADOW_RATIO = 0.02
    WYCKOFF_BC_MIN_POS_PCT = 0.65
    WYCKOFF_SOW_SUPPORT_LOOKBACK = 10
    WYCKOFF_SOW_VOL_RATIO_THRESHOLD = 1.0
    WYCKOFF_SOW_CONSECUTIVE_DAYS = 1
    WYCKOFF_SPRING_SUPPORT_LOOKBACK = 10
    WYCKOFF_SPRING_RECLAIM_RATIO = 0.985
    WYCKOFF_SPRING_ATR_MULTIPLE = 0.5
    WYCKOFF_SPRING_BULLISH_VOL_RATIO = 1.3
    WYCKOFF_SPRING_LOW_VOL_RATIO = 0.8
    WYCKOFF_UTAD_BREAKOUT_RATIO = 1.005
    WYCKOFF_UTAD_RECLAIM_RATIO = 0.995
    WYCKOFF_UT_VOL_RATIO = 1.2
    WYCKOFF_DIVERGENCE_BARS = 5
    WYCKOFF_DIVERGENCE_RATIO = 0.85
    WYCKOFF_PHASE_LOOKBACK = 60
    WYCKOFF_VSA_AVG_SPREAD_PERIOD = 20
    # Wyckoff Score 权重 fallback
    WYCKOFF_SCORE_SPRING = 25
    WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS = 5
    WYCKOFF_SCORE_BULLISH_DIV = 10
    WYCKOFF_SCORE_UT = -20
    WYCKOFF_SCORE_BEARISH_DIV = -10
    WYCKOFF_SCORE_BC = -15
    WYCKOFF_SCORE_SOW = -10
    WYCKOFF_SCORE_MAX_ABS = 95
    # 新增经典信号权重 fallback
    WYCKOFF_SCORE_AR = 10
    WYCKOFF_SCORE_SOS = 15
    WYCKOFF_SCORE_ST = 8
    WYCKOFF_SCORE_LPS = 12
    # LPSY 最后供应点（负向，对称于 LPS）
    WYCKOFF_SCORE_LPSY = -12
    # P2/P3 fallback
    WYCKOFF_SCORE_COMPRESSION = 10
    WYCKOFF_SCORE_TREND_PB = 8
    WYCKOFF_COMPRESSION_LOOKBACK = 20
    WYCKOFF_COMPRESSION_ATR_QUANTILE = 0.20
    WYCKOFF_COMPRESSION_VOL_RATIO = 0.60
    WYCKOFF_COMPRESSION_VOL_REF_WINDOW = 60
    WYCKOFF_TREND_PB_LOOKBACK = 10
    WYCKOFF_TREND_PB_MIN_PULLBACK = 5.0
    WYCKOFF_TREND_PB_MAX_PULLBACK = 20.0
    WYCKOFF_TREND_PB_VOL_SHRINK = 0.60
    WYCKOFF_TREND_PB_MA_WINDOW = 20
    # P0-3 Trading Range 识别层 fallback
    WYCKOFF_TR_LOOKBACK = 120
    WYCKOFF_TR_MIN_WIDTH = 20
    WYCKOFF_TR_AMPLITUDE_MAX = 30.0
    WYCKOFF_TR_AMPLITUDE_MIN = 6.0
    WYCKOFF_TR_QUALITY_WIDTH_REF = 60
    WYCKOFF_TR_FLOOR_PCT = 0.15
    WYCKOFF_TR_CEIL_PCT = 0.85
    # P0-4 Spring/Upthrust 真假分级常量 fallback
    WYCKOFF_SPRING_STRONG_DEPTH_PCT = 1.5
    WYCKOFF_SPRING_WEAK_DEPTH_PCT = 0.5
    WYCKOFF_SPRING_STRONG_RECLAIM = 1.0
    WYCKOFF_UT_STRONG_DEPTH_PCT = 0.5
    WYCKOFF_UT_WEAK_DEPTH_PCT = 0.1
    WYCKOFF_UT_STRONG_RECLAIM = 1.0
    # P0-5 事件簇确认常量 fallback
    WYCKOFF_CLUSTER_LOOKBACK = 60
    WYCKOFF_CLUSTER_MIN_GAP = 5


# ── 共享工具：Spring 刺穿深度 / BC 高位过滤 ─────────────────────────


def _spring_breach_level(support: float, bar: dict | None = None) -> float:
    """Spring 刺穿深度线：优先 ATR，fallback 固定比例。

    与 _detect_spring / _detect_st 共用，避免 ST 回扫用固定 1.5% 而 Spring 用 ATR。
    """
    atr14 = to_float(bar.get("atr14")) if bar else None
    if atr14 is not None and atr14 > 0:
        return support - atr14 * WYCKOFF_SPRING_ATR_MULTIPLE
    return support * WYCKOFF_SPRING_RECLAIM_RATIO

def _price_pos_pct(bars: list[dict], idx: int, lookback: int | None = None) -> float | None:
    """计算 bars[idx] 收盘价在近窗高低区间中的位置 (0=底, 1=顶)。"""
    if idx < 0 or idx >= len(bars):
        return None
    lb = lookback or WYCKOFF_SPRING_SUPPORT_LOOKBACK
    start = max(0, idx - lb)
    window = bars[start:idx + 1]
    highs = [to_float(b.get("high")) for b in window]
    lows = [to_float(b.get("low")) for b in window]
    valid_h = [h for h in highs if h is not None]
    valid_l = [lo for lo in lows if lo is not None]
    close = to_float(bars[idx].get("close"))
    high = to_float(bars[idx].get("high"))
    if not valid_h or not valid_l or close is None:
        return None
    range_hi = max(valid_h)
    range_lo = min(valid_l)
    span = range_hi - range_lo
    if span <= 0:
        return 1.0  # 无波动时视为中性高位
    # 用 high/close 较高者判定是否在高位区
    ref = max(close, high if high is not None else close)
    return (ref - range_lo) / span

def _is_bc_high_position(bars: list[dict], idx: int) -> bool:
    """BC 高位过滤：须处于近窗价格区间上沿。"""
    pos = _price_pos_pct(bars, idx)
    if pos is None:
        return False
    return pos >= WYCKOFF_BC_MIN_POS_PCT

def _is_frozen_board(bar: dict) -> bool:
    """检测一字板（开=高=低=收，全天几乎无波动）。A股涨跌停制度下无效换手。"""
    o = to_float(bar.get("open"))
    h = to_float(bar.get("high"))
    l = to_float(bar.get("low"))
    c = to_float(bar.get("close"))
    if any(v is None for v in [o, h, l, c]) or c is None or c <= 0:
        return False
    day_range_pct = (h - l) / c * 100
    return day_range_pct <= 1.0 and abs(o - c) / c * 100 <= 1.0

def _board_vol_scale(symbol: str) -> float:
    """按涨跌停幅度返回量能阈值缩放系数。20% 板块（创业板/科创板）放大 1.41x。"""
    code = symbol.split(".")[0] if "." in symbol else symbol
    if code.startswith(("300", "301", "688", "689")):
        return 1.41  # sqrt(20/10)
    return 1.0

def _is_trading_range(bars: list[dict], lookback: int = 20) -> bool:
    """检查近 N 日是否处于合理交易区间（ATR 振幅不超过 4x ATR%）。"""
    if len(bars) < lookback + 1:
        return True
    recent = bars[-(lookback + 1):-1]
    highs = [to_float(b.get("high")) for b in recent]
    lows = [to_float(b.get("low")) for b in recent]
    closes = [to_float(b.get("close")) for b in recent]
    valid = [h for h in highs if h is not None] + [l for l in lows if l is not None]
    if len(valid) < lookback:
        return True
    h_max = max(valid)
    l_min = min(valid)
    if l_min <= 0:
        return False
    range_pct = (h_max - l_min) / l_min * 100
    # 计算 ATR
    trs = []
    for i in range(1, len(recent)):
        h = to_float(recent[i].get("high"))
        l = to_float(recent[i].get("low"))
        pc = to_float(recent[i - 1].get("close"))
        if h is None or l is None or pc is None:
            continue
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return True
    avg_tr = sum(trs) / len(trs)
    last_c = to_float(recent[-1].get("close"))
    if last_c is None or last_c <= 0:
        return True
    atr_pct = avg_tr / last_c * 100
    max_allowed = max(atr_pct * 4, 30.0)  # 最低 30%
    return range_pct <= max_allowed

def _detect_trading_range(
    bars: list[dict],
    lookback: int | None = None,
    min_width: int = WYCKOFF_TR_MIN_WIDTH,
    max_amplitude_pct: float = WYCKOFF_TR_AMPLITUDE_MAX,
    min_amplitude_pct: float = WYCKOFF_TR_AMPLITUDE_MIN,
) -> dict | None:
    """识别当前最近的交易区间（Trading Range / TR）。

    原典依据：TR 是吸筹或派发的「容器」，价格在区间内反复测试清晰的上下沿、
    持续足够时长。因果律要求 TR 宽度决定后续行情幅度。

    算法：从当前 bar 向后回溯（最多 lookback 根），逐步纳入更早 K 线，
    维护区间 high_max / low_min。一旦区间振幅 (high_max-low_min)/low_min
    超过 max_amplitude_pct（说明已滑入趋势段），停止回溯。
    候选 TR 须满足：宽度 >= min_width 且振幅落入 [min_amplitude_pct, max_amplitude_pct]。

    Args:
        bars: K 线列表
        lookback: 最大回溯根数（默认 WYCKOFF_TR_LOOKBACK）
        min_width / max_amplitude_pct / min_amplitude_pct: 可调阈值

    Returns:
        dict | None：
        {
            "tr_upper": float,            # 区间上沿（反复被拒的高点）
            "tr_lower": float,            # 区间下沿（反复被撑的地点）
            "tr_baseline_volume": float,  # 区间内平均成交量（量能基线）
            "tr_start": int,              # 区间起点索引（含）
            "tr_end": int,                # 区间终点索引（= len(bars)-1）
            "tr_width": int,              # 区间宽度（根数）
            "tr_amplitude_pct": float,    # 区间振幅 %
            "tr_quality": float,          # 质量评分 0~1（越宽越清晰越高）
            "in_tr": bool,                # 当前收盘价是否在区间内
        }
        无有效 TR 返回 None（调用方 fallback 局部极值逻辑）。
    """
    n = len(bars)
    if n < min_width:
        return None
    _lookback = min(lookback if lookback is not None else WYCKOFF_TR_LOOKBACK, n)
    start_search = max(0, n - _lookback)

    # 从末端向前扩展，维护区间内 high_max / low_min / 均量
    last = bars[-1]
    hi_max = to_float(last.get("high"))
    lo_min = to_float(last.get("low"))
    last_vol = to_float(last.get("volume"))
    if hi_max is None or lo_min is None or last_vol is None or lo_min <= 0:
        return None

    vol_sum = last_vol
    count = 1
    best_start = n - 1

    for i in range(n - 2, start_search - 1, -1):
        h = to_float(bars[i].get("high"))
        l = to_float(bars[i].get("low"))
        v = to_float(bars[i].get("volume"))
        if h is None or l is None or v is None or l <= 0:
            continue
        new_hi = max(hi_max, h)
        new_lo = min(lo_min, l)
        amp = (new_hi - new_lo) / new_lo * 100
        # 纳入该根会让振幅超阈值 → 已进入趋势段，TR 停在此前
        if amp > max_amplitude_pct:
            break
        hi_max, lo_min = new_hi, new_lo
        vol_sum += v
        count += 1
        if count >= min_width:
            best_start = i  # 持续刷新为满足条件的最早起点

    width = n - best_start
    if width < min_width:
        return None
    amplitude = (hi_max - lo_min) / lo_min * 100
    if amplitude < min_amplitude_pct or amplitude > max_amplitude_pct:
        return None

    # 方向交替测试（原典核心）：TR 内价格应频繁改变方向（在区间内来回震荡、
    # 反复测试上下沿），区别于单向趋势段（即便相对振幅落入区间也不算 TR）。
    # 统计候选区间内 close 涨跌方向的变化次数，震荡段远多于趋势段。
    # 注：用相邻方向交替而非全局三分位折返，避免突破段高点拉伸上界、
    # 压低横盘段正常震荡的折返计数（T4 场景）。
    dir_changes = 0
    prev_dir = 0
    for j in range(best_start + 1, n):
        cj = to_float(bars[j].get("close"))
        cj1 = to_float(bars[j - 1].get("close"))
        if cj is None or cj1 is None:
            continue
        d = 1 if cj > cj1 else (-1 if cj < cj1 else 0)
        if d != 0 and prev_dir != 0 and d != prev_dir:
            dir_changes += 1
        if d != 0:
            prev_dir = d
    if dir_changes < 2:
        return None

    # ── 边界用「反复测试的清晰上下沿」而非绝对极值 ──────────────────────
    # 原典：TR 是价格反复测试清晰上下沿的容器；Spring（刺穿下沿）/Upthrust
    # （刺穿上沿）是事件而非边界本身。若直接取区间 low/high 的极值作边界，
    # 会把刺穿毛刺当成支撑/阻力，导致 Spring 无法「跌破」自身最低点而漏检。
    # 故对区间内的 low/high 取分位带（默认 15/85 分位），过滤最深/最高的刺穿，
    # 得到价格真正反复测试的水平。无效时回退绝对极值。
    _lows = []
    _highs = []
    for j in range(best_start, n):
        l = to_float(bars[j].get("low"))
        h = to_float(bars[j].get("high"))
        if l is not None and l > 0:
            _lows.append(l)
        if h is not None and h > 0:
            _highs.append(h)
    if _lows and _highs:
        _lows.sort()
        _highs.sort()
        fl = max(0.0, min(1.0, WYCKOFF_TR_FLOOR_PCT))
        cl = max(0.0, min(1.0, WYCKOFF_TR_CEIL_PCT))
        _fi = min(len(_lows) - 1, int(round(fl * (len(_lows) - 1))))
        _ci = min(len(_highs) - 1, int(round(cl * (len(_highs) - 1))))
        _pctl_lower = _lows[_fi]
        _pctl_upper = _highs[_ci]
        if _pctl_upper > _pctl_lower:
            hi_max, lo_min = _pctl_upper, _pctl_lower

    tr_baseline_volume = vol_sum / count if count > 0 else 0.0
    close_last = to_float(last.get("close"))
    in_tr = (close_last is not None) and (lo_min <= close_last <= hi_max)
    # 质量：宽度越大越高（封顶 1.0）；振幅越居中（远离上下限）略加权
    width_score = min(1.0, width / max(1, WYCKOFF_TR_QUALITY_WIDTH_REF))
    amp_mid = (min_amplitude_pct + max_amplitude_pct) / 2.0
    amp_score = 1.0 - abs(amplitude - amp_mid) / max(amp_mid, 1e-6) * 0.5
    amp_score = max(0.3, min(1.0, amp_score))
    tr_quality = round(width_score * 0.7 + amp_score * 0.3, 3)

    return {
        "tr_upper": round(hi_max, 4),
        "tr_lower": round(lo_min, 4),
        "tr_baseline_volume": round(tr_baseline_volume, 2),
        "tr_start": best_start,
        "tr_end": n - 1,
        "tr_width": width,
        "tr_amplitude_pct": round(amplitude, 2),
        "tr_quality": tr_quality,
        "in_tr": bool(in_tr),
    }

def _compute_dynamic_support(
    bars: list[dict],
    lookback: int = 10,
    chan_zones: list[dict] | None = None,
    chip_peaks: list[dict] | None = None,
) -> float | None:
    """从多个来源计算最佳支撑位。

    优先级：
    1. 缠论中枢下沿（zh_bottom）— 最可靠的结构性支撑
    2. 筹码密集峰价格 — 量价支撑
    3. 最近 N 日最低价 — 简单 fallback

    Returns:
        支撑位价格，或 None（数据不足）
    """
    current_price = to_float(bars[-1].get("close")) if bars else None
    if current_price is None:
        return None

    candidates: list[float] = []

    # 来源1：缠论中枢下沿
    if chan_zones:
        for z in chan_zones:
            if isinstance(z, dict) and z.get("valid"):
                zh_bottom = to_float(z.get("zh_bottom"))
                if zh_bottom is not None and zh_bottom < current_price:
                    candidates.append(zh_bottom)

    # 来源2：筹码密集峰
    if chip_peaks:
        for p in chip_peaks:
            if isinstance(p, dict):
                price = to_float(p.get("price"))
                if price is not None and price < current_price:
                    candidates.append(price)

    # 来源3：最近 N 日最低价（排除当前 bar）
    recent = bars[-(lookback + 1):-1] if len(bars) > lookback else bars[:-1]
    lows = [to_float(b.get("low")) for b in recent]
    valid_lows = [l for l in lows if l is not None]
    if valid_lows:
        candidates.append(min(valid_lows))

    if not candidates:
        return None

    # 选择最接近当前价的支撑位（但不能太近，至少低于当前价 0.5%）
    min_gap = current_price * 0.005
    valid_candidates = [c for c in candidates if current_price - c >= min_gap]
    if not valid_candidates:
        return min(candidates)  # 所有候选都太近，取最低的

    # 取最接近当前价的（最高支撑）
    return max(valid_candidates)

def _detect_buying_climax(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Buying Climax (BC) — 天量滞涨，高位放量阴线。

    P1 Fix: 扫描 bars[-5:] 而非仅 bars[-1]，任一满足 BC 条件即触发。
    返回最近一次 BC 的信息。

    Returns:
        dict with keys: bc_signal (bool), bc_reason (str), bc_price (float)
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"bc_signal": False, "bc_reason": "数据不足", "bc_price": 0.0}

    # P1 Fix: 扫描最近 5 根 K 线，任一满足 BC 条件即触发
    scan_start = max(1, len(bars) - 5)
    for scan_idx in range(len(bars) - 1, scan_start - 1, -1):
        current = bars[scan_idx]
        recent = bars[max(0, scan_idx - WYCKOFF_SPRING_SUPPORT_LOOKBACK):scan_idx]

        cur_open = to_float(current.get("open"))
        cur_high = to_float(current.get("high"))
        cur_low = to_float(current.get("low"))
        cur_close = to_float(current.get("close"))
        cur_volume = to_float(current.get("volume"))

        if any(v is None for v in [cur_open, cur_high, cur_low, cur_close, cur_volume]):
            continue

        # 量比计算
        avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
        if avg_volume <= 0:
            continue

        vol_ratio = cur_volume / avg_volume

        # 涨幅计算（相对前收盘）
        price_range = cur_high - cur_low if cur_high != cur_low else 1.0
        prev_close = to_float(bars[scan_idx - 1].get("close")) if scan_idx >= 1 else cur_open
        change_pct = (cur_close - prev_close) / max(prev_close, 0.01) * 100

        # 上影线比例
        real_body_top = max(cur_open, cur_close)
        upper_shadow = cur_high - real_body_top
        upper_shadow_ratio = upper_shadow / max(price_range, 0.01)

        # BC 条件判断使用外置参数
        if vol_ratio < WYCKOFF_BC_VOL_RATIO_THRESHOLD:
            continue

        # P1: 高位过滤 — 低位天量不标 BC（派发 Phase A 须在区间上沿）
        if not _is_bc_high_position(bars, scan_idx):
            continue

        # 天量 + 滞涨（收盘接近开盘或阴线）
        is_stagnant = change_pct < WYCKOFF_BC_CHANGE_THRESHOLD
        has_upper_shadow = upper_shadow_ratio > WYCKOFF_BC_UPPER_SHADOW_RATIO

        if not (is_stagnant or (cur_close < cur_open)):
            continue

        parts = []
        parts.append(f"量比 {vol_ratio:.1f}")
        pos = _price_pos_pct(bars, scan_idx)
        if pos is not None:
            parts.append(f"高位区{pos*100:.0f}%")
        if is_stagnant:
            parts.append(f"涨幅仅 {change_pct:.1f}%")
        if has_upper_shadow:
            parts.append("上影线明显")
        if cur_close < cur_open:
            parts.append("收阴")

        return {
            "bc_signal": True,
            "bc_reason": "天量滞涨，购买高潮信号：" + "，".join(parts),
            "bc_price": round(cur_high, 2),
        }

    return {"bc_signal": False, "bc_reason": "未检测到购买高潮", "bc_price": 0.0}

def _detect_selling_climax(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Selling Climax (SC) — 天量宽幅下跌，低位抛售宣泄。

    对称于 BC（Buying Climax），但方向相反：
      - 巨量（量比 >= BC 阈值）
      - 低位（在近窗价格区间下沿）
      - 阴线（close < open）且跌幅显著
      - 下影线比例低（实体占比大）

    Returns:
        dict with keys: sc_signal (bool), sc_reason (str), sc_price (float)
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"sc_signal": False, "sc_reason": "数据不足", "sc_price": 0.0}

    scan_start = max(1, len(bars) - 5)
    for scan_idx in range(len(bars) - 1, scan_start - 1, -1):
        current = bars[scan_idx]
        recent = bars[max(0, scan_idx - WYCKOFF_SPRING_SUPPORT_LOOKBACK):scan_idx]

        cur_open = to_float(current.get("open"))
        cur_high = to_float(current.get("high"))
        cur_low = to_float(current.get("low"))
        cur_close = to_float(current.get("close"))
        cur_volume = to_float(current.get("volume"))

        if any(v is None for v in [cur_open, cur_high, cur_low, cur_close, cur_volume]):
            continue

        avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
        if avg_volume <= 0:
            continue

        vol_ratio = cur_volume / avg_volume

        # 量比门槛（与 BC 共用阈值）
        if vol_ratio < WYCKOFF_BC_VOL_RATIO_THRESHOLD:
            continue

        # 低位过滤：须在近窗价格区间下沿
        pos = _price_pos_pct(bars, scan_idx)
        if pos is None or pos > 1 - WYCKOFF_BC_MIN_POS_PCT:
            continue

        # 必须是阴线（close < open），且跌幅明显（相对前收盘）
        if cur_close >= cur_open:
            continue
        prev_close = to_float(bars[scan_idx - 1].get("close")) if scan_idx >= 1 else cur_open
        change_pct = (cur_close - prev_close) / max(prev_close, 0.01) * 100
        if change_pct > -2.0:  # 跌幅至少 -2%
            continue

        # 下影线比例低（实体占比大，不是探底回升）
        price_range = cur_high - cur_low if cur_high != cur_low else 1.0
        real_body_bottom = min(cur_open, cur_close)
        lower_shadow = real_body_bottom - cur_low
        lower_shadow_ratio = lower_shadow / max(price_range, 0.01)

        parts = [f"量比 {vol_ratio:.1f}", f"跌幅 {change_pct:.1f}%"]
        if lower_shadow_ratio < 0.3:
            parts.append("下影线短（实体大）")
        else:
            parts.append("带下影线")
        pos_label = f"低位区{pos*100:.0f}%"
        parts.append(pos_label)

        return {
            "sc_signal": True,
            "sc_reason": "天量宽幅下跌，卖力高潮：" + "，".join(parts),
            "sc_price": round(cur_low, 2),
        }

    return {"sc_signal": False, "sc_reason": "未检测到卖力高潮", "sc_price": 0.0}

def _detect_sign_of_weakness(bars: list[dict], _support: float | None = None, tr_ctx: dict | None = None) -> dict:
    """Detect Sign of Weakness (SOW) — 收盘有效跌破支撑且放量。

    产品 ⑤B：
      - sow_signal：收盘仍在支撑下方（计分 / 阶段 / fusion）
      - sow_intraday_warn：放量刺穿后收盘收回（仅展示，不计分；字段名故意不含 _signal，避免阶段滑窗误吸）

    关键修复：当 WYCKOFF_SOW_CONSECUTIVE_DAYS > 1 时，支撑位从「不含连续确认窗口」
    的 K 线中计算，避免前一日 low 被纳入 support 导致 prev_low >= support 恒成立。
    支持 _support 覆盖：提供外部计算的动态支撑位时优先使用。
    """
    _empty = {
        "sow_signal": False,
        "sow_intraday_warn": False,
        "sow_reason": "",
        "sow_price": 0.0,
    }
    consecutive = WYCKOFF_SOW_CONSECUTIVE_DAYS
    min_bars = WYCKOFF_SOW_SUPPORT_LOOKBACK + consecutive
    if len(bars) < min_bars:
        return {**_empty, "sow_reason": "数据不足"}

    # 支撑位计算：TR 内用 TR 下沿（原典 SOW = 跌破 TR 下沿），否则动态支撑或局部最低
    if tr_ctx is not None and tr_ctx.get("in_tr") and tr_ctx.get("tr_lower") is not None:
        support = tr_ctx["tr_lower"]
    elif _support is not None:
        support = _support
    else:
        # 排除最后 consecutive 根（它们参与跌破确认，不应纳入 support）
        support_end = -(consecutive) if consecutive > 0 else None
        support_start = -(WYCKOFF_SOW_SUPPORT_LOOKBACK + consecutive)
        support_window = bars[support_start:support_end]
        low_values = [to_float(b.get("low")) for b in support_window]
        valid_lows = [v for v in low_values if v is not None]

        if not valid_lows:
            return {**_empty, "sow_reason": "数据异常"}
        support = min(valid_lows)

    # 当前 bar（最后一根）
    current = bars[-1]
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))
    cur_volume = to_float(current.get("volume"))

    if cur_low is None or cur_close is None or cur_volume is None:
        return {**_empty, "sow_reason": "数据异常"}

    # 跌破支撑判定逻辑
    if consecutive > 1:
        # 需要连续 N 天最低价刺穿才进入量能确认
        if cur_low >= support:
            return {**_empty, "sow_reason": "未跌破支撑"}

        # 检查前 consecutive-1 天是否也跌破
        for i in range(2, consecutive + 1):
            check_bar = bars[-i]
            check_low = to_float(check_bar.get("low"))
            if check_low is None or check_low >= support:
                return {
                    **_empty,
                    "sow_reason": f"仅 {i-1}/{consecutive} 日跌破，需连续{consecutive}天确认",
                }
    else:
        # 单日判定，最低价或收盘价跌破即可进入量能确认
        if cur_low >= support and cur_close >= support:
            return {**_empty, "sow_reason": "未跌破支撑"}

    # 放量确认
    vol_window = bars[-(WYCKOFF_SOW_SUPPORT_LOOKBACK + 1):-1]
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in vol_window) / max(len(vol_window), 1)
    is_high_volume = avg_volume > 0 and cur_volume >= avg_volume * WYCKOFF_SOW_VOL_RATIO_THRESHOLD

    if not is_high_volume:
        return {**_empty, "sow_reason": "缩量跌破，非强弱势信号"}

    # ⑤B：收盘站上支撑 → 仅日内警告；收盘仍破 → 正式 SOW
    if cur_close >= support:
        return {
            "sow_signal": False,
            "sow_intraday_warn": True,
            "sow_reason": f"日内跌破支撑 {support:.2f} 后收回，弱势警告（未确认）",
            "sow_price": round(support, 2),
        }

    return {
        "sow_signal": True,
        "sow_intraday_warn": False,
        "sow_reason": f"放量跌破支撑 {support:.2f}，弱势信号",
        "sow_price": round(support, 2),
    }

def _detect_spring(bars: list[dict], _support: float | None = None, symbol: str = "", tr_ctx: dict | None = None) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    # P1-3: 一字板过滤
    if _is_frozen_board(current):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "一字板无效换手"}
    if len(recent) > 0 and _is_frozen_board(recent[-1]):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "前日一字板无效换手"}

    # TR 语境优先：在 TR 内时，TR 下沿即吸筹区支撑，无需 ATR 振幅过滤（TR 本身就是横盘容器）
    in_tr = bool(tr_ctx.get("in_tr")) if tr_ctx else False
    if not in_tr and not _is_trading_range(bars):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "非交易区间（振幅过大）"}

    low_values = [to_float(b.get("low")) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    current_low = to_float(current.get("low"))
    current_close = to_float(current.get("close"))
    current_volume = to_float(current.get("volume"))

    # 支撑位：TR 内用 TR 下沿（原典 Spring = 跌破 TR 下沿后收回），否则动态支撑或局部最低
    if in_tr and tr_ctx.get("tr_lower") is not None:
        support = tr_ctx["tr_lower"]
    else:
        support = _support if _support is not None else (min(valid_lows) if valid_lows else None)
    if current_low is None or current_close is None or support is None or current_volume is None:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据异常"}

    # P0-1 / P1: ATR 动态刺穿深度（与 ST 共用 _spring_breach_level）
    breach_level = _spring_breach_level(support, current)

    # 刺穿深度判定：最低价刺穿深度线
    if current_low >= breach_level:
        return {"spring_signal": False, "spring_price": 0.0,
                "spring_reason": "未刺穿支撑", "spring_strength": None}
    # 刺穿了支撑却未收回 → 弹簧失败（派发信号），区别于普通无信号
    if current_close < support:
        return {
            "spring_signal": False, "spring_price": 0.0,
            "spring_reason": "刺穿支撑后未能收回，弹簧失败(派发信号)",
            "spring_strength": "failure",
        }

    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)

    # P1-2: 涨跌停板量能缩放
    vol_scale = _board_vol_scale(symbol)

    # ── 收回速度检查：Spring 必须在 1-2 根内收回支撑上方 ──
    # 回溯 recent 找跌破点，检查是否在 1-2 根内收回
    breach_bar_i = None
    for j in range(len(recent)):
        b_low = to_float(recent[j].get("low"))
        b_close = to_float(recent[j].get("close"))
        if b_low is not None and b_low < support:
            breach_bar_i = j
            break
    if breach_bar_i is not None:
        # 检查跌破后 1-2 根内是否收回
        recharged = False
        for k in range(breach_bar_i + 1, min(breach_bar_i + 3, len(recent))):
            if to_float(recent[k].get("close")) is not None and to_float(recent[k].get("close")) >= support:
                recharged = True
                break
        if not recharged:
            return {"spring_signal": False, "spring_price": 0.0,
                    "spring_reason": "跌破支撑后未在2根内收回，非Spring"}
    # 当前价也必须在支撑上方
    if current_close < support:
        return {"spring_signal": False, "spring_price": 0.0,
                "spring_reason": "刺穿支撑后未能收回，弹簧失败(派发信号)", "spring_strength": "failure"}

    # ── 量能分级 + 过滤 ──
    if avg_volume > 0 and current_volume < avg_volume * WYCKOFF_SPRING_LOW_VOL_RATIO:
        vol_class = "low_vol_confirm"
        volume_note = "缩量洗盘（供应耗尽，可靠）"
    elif avg_volume > 0 and current_volume >= avg_volume * WYCKOFF_SPRING_BULLISH_VOL_RATIO * vol_scale:
        # 放量弹簧：直接过滤，不报信号；仍透传 vol_class 供展示/审计（打分只在 signal=True 时消费降权分支）
        return {
            "spring_signal": False,
            "spring_price": 0.0,
            "spring_reason": "放量跌破支撑，可能是真破位",
            "spring_strength": "failure",
            "spring_vol_class": "high_vol_warning",
        }
    else:
        vol_class = "normal"
        volume_note = "正常量能"

    # ── 收回力度检查：必须收回跌幅的 50%+ ──
    baseline_vol = tr_ctx.get("tr_baseline_volume") if (in_tr and tr_ctx) else avg_volume
    vol_ratio = (current_volume / baseline_vol) if baseline_vol and baseline_vol > 0 else 1.0
    depth_pct = ((support - current_low) / support * 100.0) if support > 0 else 0.0
    recent_highs = [to_float(b.get("high")) for b in recent]
    valid_recent_highs = [v for v in recent_highs if v is not None]
    local_high = max(valid_recent_highs) if valid_recent_highs else support
    tr_upper = tr_ctx.get("tr_upper") if (in_tr and tr_ctx) else None
    tr_mid = ((tr_upper + support) / 2.0) if tr_upper is not None else ((support + local_high) / 2.0)
    range_mid = (tr_mid - support)
    reclaim_ratio = ((current_close - support) / range_mid) if range_mid > 0 else 0.0

    # ── 收回力度 < 50% → 弱弹簧，不可靠 ──
    if reclaim_ratio < 0.5:
        return {"spring_signal": False, "spring_price": 0.0,
                "spring_reason": f"收回力度不足（{reclaim_ratio*100:.0f}% < 50%），弱弹簧", "spring_strength": "weak"}

    # ── 分级：强 = 量价齐振；弱 = 缩量无确认；其他 = 标准 ──
    # high_vol_warning 已在上方硬过滤；此处不再标 strong（避免与放量真破位语义冲突）
    if (
        vol_class != "high_vol_warning"
        and depth_pct >= WYCKOFF_SPRING_STRONG_DEPTH_PCT
        and vol_ratio >= 1.0
        and reclaim_ratio >= WYCKOFF_SPRING_STRONG_RECLAIM
    ):
        strength = "strong"
        strength_note = "深度震仓+放量承接+坚决收回中轴，吸筹最强确认"
    elif vol_ratio < WYCKOFF_SPRING_LOW_VOL_RATIO:
        strength = "weak"
        strength_note = f"缩量（量比{vol_ratio:.1f}），无主动承接确认，可靠性低"
    else:
        strength = "ordinary"
        strength_note = "标准弹簧"

    return {
        "spring_signal": True,
        "spring_price": round(breach_level, 2),
        "spring_reason": f"跌破支撑后收回 {volume_note}，收回{reclaim_ratio*100:.0f}%",
        "spring_vol_class": vol_class,
        "spring_strength": strength,
        "spring_strength_note": strength_note,
        "spring_depth_pct": round(depth_pct, 3),
        "spring_vol_ratio": round(vol_ratio, 3),
        "spring_reclaim_ratio": round(reclaim_ratio, 3),
    }

def _detect_upthrust(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    high_values = [to_float(b.get("high")) for b in recent]
    valid_highs = [v for v in high_values if v is not None]
    current_high = to_float(current.get("high"))
    current_close = to_float(current.get("close"))

    # 阻力位：TR 内用 TR 上沿（原典 UT = 突破 TR 上沿后回落），否则局部最高
    if tr_ctx is not None and tr_ctx.get("in_tr") and tr_ctx.get("tr_upper") is not None:
        resistance = tr_ctx["tr_upper"]
    else:
        resistance = max(valid_highs) if valid_highs else None
    if current_high is None or current_close is None or resistance is None:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据异常"}

    breakout_level = resistance * WYCKOFF_UTAD_BREAKOUT_RATIO
    reclaim_level = resistance * WYCKOFF_UTAD_RECLAIM_RATIO

    # 未突破阻力 → 普通无信号
    if current_high <= breakout_level:
        return {"upthrust_signal": False, "upthrust_price": 0.0,
                "upthrust_reason": "未突破阻力", "upthrust_strength": None}
    # 突破后站住未回落 → 上冲失败（可能是真突破 SOS），反向吸筹信号
    if current_close >= reclaim_level:
        return {
            "upthrust_signal": False, "upthrust_price": 0.0,
            "upthrust_reason": "突破阻力后站住未回落，上冲失败(可能是真突破)",
            "upthrust_strength": "failure",
        }

    # P0-2: UT 需放量确认（派发需要成交量配合）
    current_volume = to_float(current.get("volume"))
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    if current_volume is not None and avg_volume > 0 and current_volume < avg_volume * WYCKOFF_UT_VOL_RATIO:
        return {"upthrust_signal": False, "upthrust_price": 0.0,
                "upthrust_reason": "上冲未放量，非主力派发", "upthrust_strength": None}

    # ── P0-4 真假分级：突破深度 + 量能比(vs TR基线量) + 跌回位置(相对TR中轴) ──
    baseline_vol = tr_ctx.get("tr_baseline_volume") if (tr_ctx and tr_ctx.get("in_tr")) else avg_volume
    vol_ratio = (current_volume / baseline_vol) if baseline_vol and baseline_vol > 0 else 1.0
    depth_pct = ((current_high - resistance) / resistance * 100.0) if resistance > 0 else 0.0
    # TR 中轴：TR 语境用 (上沿+下沿)/2，否则用 (阻力+局部最低)/2
    tr_lower = tr_ctx.get("tr_lower") if (tr_ctx and tr_ctx.get("in_tr")) else None
    recent_low_values = [to_float(b.get("low")) for b in recent]
    valid_recent_lows = [v for v in recent_low_values if v is not None]
    local_low = min(valid_recent_lows) if valid_recent_lows else resistance
    tr_mid = ((resistance + tr_lower) / 2.0) if tr_lower is not None else ((resistance + local_low) / 2.0)
    range_mid = (resistance - tr_mid)
    reclaim_ratio = ((resistance - current_close) / range_mid) if range_mid > 0 else 0.0

    if depth_pct >= WYCKOFF_UT_STRONG_DEPTH_PCT and vol_ratio >= WYCKOFF_UT_VOL_RATIO and reclaim_ratio >= WYCKOFF_UT_STRONG_RECLAIM:
        strength = "strong"
        strength_note = "深度假突破+放量派发+跌回中轴下，派发最强确认"
    elif depth_pct < WYCKOFF_UT_WEAK_DEPTH_PCT or (vol_ratio < 1.0 and reclaim_ratio < 0.5):
        strength = "weak"
        strength_note = "突破过浅或量不足，噪音风险"
    else:
        strength = "ordinary"
        strength_note = "标准上冲回落"

    return {
        "upthrust_signal": True,
        "upthrust_price": round(resistance, 2),
        "upthrust_reason": "突破阻力后回落，上冲回落信号",
        "upthrust_strength": strength,
        "upthrust_strength_note": strength_note,
        "upthrust_depth_pct": round(depth_pct, 3),
        "upthrust_vol_ratio": round(vol_ratio, 3),
        "upthrust_reclaim_ratio": round(reclaim_ratio, 3),
    }

def _detect_volume_divergence(bars: list[dict]) -> tuple[bool, bool]:
    if len(bars) < WYCKOFF_DIVERGENCE_BARS:
        return False, False

    recent = bars[-WYCKOFF_DIVERGENCE_BARS:]

    prices: list[float] = []
    volumes: list[float] = []
    for b in recent:
        close_val = to_float(b.get("close"))
        vol_val = to_float(b.get("volume"))
        if close_val is None or vol_val is None:
            return False, False
        prices.append(close_val)
        volumes.append(vol_val)

    # 拆分两部分计算成交量平均值
    mid = len(prices) // 2
    first_half_avg_vol = sum(volumes[:mid]) / max(mid, 1)
    second_half_avg_vol = sum(volumes[mid:]) / max(len(volumes) - mid, 1)

    max_price_idx = max(range(len(prices)), key=lambda i: prices[i])
    min_price_idx = min(range(len(prices)), key=lambda i: prices[i])

    # 看空背离：价格在上升趋势中创新高（峰值高于起点），但后半段平均量萎缩至前半段比例内
    bearish = (prices[max_price_idx] > prices[0]) and (second_half_avg_vol < first_half_avg_vol * WYCKOFF_DIVERGENCE_RATIO)
    # 看多背离：价格在下降趋势中创新低（谷值低于起点），但后半段平均量释放或萎缩度满足抛压出清
    bullish = (prices[min_price_idx] < prices[0]) and (second_half_avg_vol < first_half_avg_vol * WYCKOFF_DIVERGENCE_RATIO)

    return bearish, bullish

def _detect_ar(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Automatic Rally (AR) — SC 之后抛售枯竭的快速反弹（原典）。

    产品 ⑥B：AR 只绑 SC；BC 后不再产 AR（派发侧 Automatic Reaction 未单独建模）。

    触发条件:
      1. 最近 N 根 K 线内检测到 SC（卖力高潮）
      2. SC 后 1-3 根 K 线内，存在至少 1 根满足:
         - close > sc_close * 1.02 (上涨 >= 2%)
         - volume > sc 前均量 * 1.2 (放量)
    """
    if len(bars) < WYCKOFF_MIN_BARS + 3:
        return {"ar_signal": False, "ar_reason": "数据不足", "ar_price": None}

    # 扫描最近 15 根寻找 SC 锚点（原 5 根过短，A 股高潮后 1 周才反弹会漏 AR）
    scan_start = max(1, len(bars) - 15)
    sc_bar_idx = None
    sc_close = None
    sc_avg_vol = None

    for scan_idx in range(len(bars) - 1, scan_start - 1, -1):
        current = bars[scan_idx]
        recent = bars[max(0, scan_idx - WYCKOFF_SPRING_SUPPORT_LOOKBACK):scan_idx]

        cur_open = to_float(current.get("open"))
        cur_close = to_float(current.get("close"))
        cur_volume = to_float(current.get("volume"))

        if any(v is None for v in [cur_open, cur_close, cur_volume]):
            continue

        avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
        if avg_volume <= 0:
            continue

        prev_close = to_float(bars[scan_idx - 1].get("close")) if scan_idx >= 1 else cur_open
        change_pct = (cur_close - prev_close) / max(prev_close, 0.01) * 100
        vol_ratio = cur_volume / avg_volume
        is_candle = cur_close < cur_open

        # 仅 SC：低位 + 阴线 + 跌幅显著 + 天量（与 _detect_selling_climax 对齐）
        sc_pos = _price_pos_pct(bars, scan_idx)
        if (
            vol_ratio >= WYCKOFF_BC_VOL_RATIO_THRESHOLD
            and is_candle
            and sc_pos is not None
            and sc_pos <= 1 - WYCKOFF_BC_MIN_POS_PCT
            and change_pct <= -2.0
        ):
            sc_bar_idx = scan_idx
            sc_close = cur_close
            sc_avg_vol = avg_volume
            break

    if sc_bar_idx is None:
        return {"ar_signal": False, "ar_reason": "未检测到 SC，无法触发 AR", "ar_price": None}

    # 检查 SC 后 1-3 根 K 线
    for i in range(1, min(4, len(bars) - sc_bar_idx)):
        rally_bar = bars[sc_bar_idx + i]
        r_close = to_float(rally_bar.get("close"))
        r_volume = to_float(rally_bar.get("volume"))
        if r_close is None or r_volume is None:
            continue

        if r_close > sc_close * 1.02 and r_volume > sc_avg_vol * 1.2:
            pct = (r_close / sc_close - 1) * 100
            return {
                "ar_signal": True,
                "ar_reason": f"SC 后自动反弹，放量 +{pct:.1f}%",
                "ar_price": round(r_close, 2),
            }

    return {"ar_signal": False, "ar_reason": "SC 后未检测到有效反弹", "ar_price": None}

def _detect_sos(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Sign of Strength (SOS) — 连续放量突破。

    触发条件（最近 5 根 K 线窗口）:
      - ≥4/5 阳线 (close > open)（A 股极少 5 连阳，与 LPS 对齐）
      - close[4] >= open[0] (总体抬高)
      - 平均量比 > 1.2（相对前窗基线均量）
      - 累计涨幅 >= 2%
    """
    if len(bars) < WYCKOFF_DIVERGENCE_BARS + WYCKOFF_SPRING_SUPPORT_LOOKBACK:
        return {"sos_signal": False, "sos_reason": "数据不足", "sos_price": None}

    recent = bars[-(WYCKOFF_DIVERGENCE_BARS + WYCKOFF_SPRING_SUPPORT_LOOKBACK):-1]
    current_window = bars[-WYCKOFF_DIVERGENCE_BARS:]

    # 基线均量：TR 内用 TR 量能基线（区间内均量，避免含趋势段失真），否则前10根均量
    if tr_ctx is not None and tr_ctx.get("in_tr") and tr_ctx.get("tr_baseline_volume"):
        baseline_avg_vol = tr_ctx["tr_baseline_volume"]
    else:
        baseline_start = max(0, len(recent) - 10)
        baseline = recent[baseline_start:]
        baseline_avg_vol = sum(to_float(b.get("volume")) or 0 for b in baseline) / max(len(baseline), 1)
    if baseline_avg_vol <= 0:
        return {"sos_signal": False, "sos_reason": "量能数据不足", "sos_price": None}

    # 检查 5 根 K 线
    closes = []
    opens = []
    volumes = []
    for b in current_window:
        o = to_float(b.get("open"))
        c = to_float(b.get("close"))
        v = to_float(b.get("volume"))
        if o is None or c is None or v is None:
            return {"sos_signal": False, "sos_reason": "数据异常", "sos_price": None}
        closes.append(c)
        opens.append(o)
        volumes.append(v)

    # P1-2: 放宽为 ≥4/5 阳线（A 股连续 5 阳极罕见，4/5 + 强涨幅更实际）
    bullish_count = sum(1 for c, o in zip(closes, opens) if c > o)
    if bullish_count < WYCKOFF_DIVERGENCE_BARS - 1:
        return {"sos_signal": False, "sos_reason": f"仅 {bullish_count}/{WYCKOFF_DIVERGENCE_BARS} 阳线，不足 {WYCKOFF_DIVERGENCE_BARS - 1} 根", "sos_price": None}

    # 总体抬高
    if closes[-1] < opens[0]:
        return {"sos_signal": False, "sos_reason": "未总体抬高", "sos_price": None}

    # 平均量比
    sos_avg_vol = sum(volumes) / len(current_window)
    if sos_avg_vol < baseline_avg_vol * 1.2:
        return {"sos_signal": False, "sos_reason": "量能不足", "sos_price": None}

    # 累计涨幅
    gain = (closes[-1] - opens[0]) / max(opens[0], 0.01)
    if gain < 0.02:
        return {"sos_signal": False, "sos_reason": f"涨幅 {gain*100:.1f}% 不足 2%", "sos_price": None}

    return {
        "sos_signal": True,
        "sos_reason": f"强势突破，{bullish_count}/5 阳线累计涨{gain*100:.1f}%，量能放大",
        "sos_price": round(closes[-1], 2),
    }

def _detect_st(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Secondary Test (ST) — 二次测试 Spring 支撑，缩量确认。

    触发条件:
      1. 最近 N 根 K 线内检测到 Spring 信号
      2. Spring 后 3-15 根 K 线内:
         - 价格回到支撑区域（±1%）
         - 成交量 < 均量 * 0.8
         - 最低价未破支撑
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 15 + 1:
        return {"st_signal": False, "st_reason": "数据不足", "st_price": None}

    # 扫描 Spring 事件
    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    low_values = [to_float(b.get("low")) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    # 支撑位：TR 内用 TR 下沿，否则局部最低
    if tr_ctx is not None and tr_ctx.get("in_tr") and tr_ctx.get("tr_lower") is not None:
        support = tr_ctx["tr_lower"]
    else:
        support = min(valid_lows) if valid_lows else None

    if support is None:
        return {"st_signal": False, "st_reason": "支撑位数据异常", "st_price": None}

    # P1: 与 Spring 共用 ATR/固定比例刺穿深度
    breach_level = _spring_breach_level(support, current)
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))

    # 检查最近是否有 Spring
    spring_detected = (cur_low is not None and cur_close is not None and
                       cur_low < breach_level and cur_close >= support)

    if not spring_detected:
        # 也可能 Spring 发生在更早的 bar
        scan_range = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 15):-1]
        for i in range(len(scan_range) - 1, 0, -1):
            sl = to_float(scan_range[i].get("low"))
            sc = to_float(scan_range[i].get("close"))
            if sl is None or sc is None:
                continue
            # 找 support
            pre = scan_range[max(0, i - WYCKOFF_SPRING_SUPPORT_LOOKBACK):i]
            pls = [to_float(b.get("low")) for b in pre]
            vs = [v for v in pls if v is not None]
            if not vs:
                continue
            sup = min(vs)
            br = _spring_breach_level(sup, scan_range[i])
            if sl < br and sc >= sup:
                support = sup
                spring_detected = True
                break

    if not spring_detected:
        return {"st_signal": False, "st_reason": "未检测到 Spring，无法触发 ST", "st_price": None}

    # 在 Spring 后 3-15 根 K 线内寻找回测
    # 当前 bar 就是最后一个，用它检查
    # 需要回溯查找 Spring 发生位置
    spring_idx = None
    for i in range(len(bars) - 2, max(0, len(bars) - WYCKOFF_SPRING_SUPPORT_LOOKBACK - 15 - 1), -1):
        sl = to_float(bars[i].get("low"))
        sc = to_float(bars[i].get("close"))
        if sl is None or sc is None:
            continue
        pre = bars[max(0, i - WYCKOFF_SPRING_SUPPORT_LOOKBACK):i]
        pls = [to_float(b.get("low")) for b in pre]
        vs = [v for v in pls if v is not None]
        if not vs:
            continue
        sup = min(vs)
        br = _spring_breach_level(sup, bars[i])
        if sl < br and sc >= sup:
            spring_idx = i
            support = sup
            break

    if spring_idx is None:
        return {"st_signal": False, "st_reason": "Spring 锚点未找到", "st_price": None}

    # 检查 Spring 后 3-15 根 K 线
    _spring_vol_slice = bars[max(0, spring_idx - WYCKOFF_SPRING_SUPPORT_LOOKBACK):spring_idx]
    spring_avg_vol = (
        sum(to_float(b.get("volume")) or 0 for b in _spring_vol_slice)
        / max(len(_spring_vol_slice), 1)
    )

    for i in range(spring_idx + 3, min(spring_idx + 16, len(bars))):
        test_bar = bars[i]
        t_low = to_float(test_bar.get("low"))
        t_close = to_float(test_bar.get("close"))
        t_volume = to_float(test_bar.get("volume"))
        if t_low is None or t_close is None or t_volume is None:
            continue

        # 价格回到支撑区域（±1%）
        if t_low > support * 1.01:
            continue
        # 未破支撑
        if t_low < support * 0.99:
            continue
        # 成交量萎缩
        if spring_avg_vol > 0 and t_volume < spring_avg_vol * 0.8:
            return {
                "st_signal": True,
                "st_reason": f"Spring 支撑二次测试，缩量确认",
                "st_price": round(support, 2),
            }

    return {"st_signal": False, "st_reason": "Spring 后未检测到有效二次测试", "st_price": None}

def _detect_lps(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect LPS (Last Point of Support) — SOS 突破后回调不破前低。

    威科夫阶段: ... → SOS → 回调 → LPS → 主升
    检测逻辑:
      1. 从近到远找「最近一次」有效 SOS 锚点（SOS 结束后的 bar 索引）
      2. 只评估该 SOS 之后到当前的完整回调（2–10 根），不回退到更早伪 SOS
      3. 回调不破 SOS 前低（允许约 1% 容差）
      4. 回调末端缩量（相对基线均量 * 0.7）
      5. SOS 阳线标准与 _detect_sos 对齐：≥4/5 阳线
    """
    sos_len = WYCKOFF_DIVERGENCE_BARS  # 5
    min_pb = 2
    max_pb = 10
    baseline_len = 10
    min_bars = sos_len + min_pb + baseline_len + WYCKOFF_SPRING_SUPPORT_LOOKBACK  # ≈27
    if len(bars) < min_bars:
        return {"lps_signal": False, "lps_reason": "数据不足", "lps_price": None}

    n = len(bars)
    tr_baseline = (
        tr_ctx.get("tr_baseline_volume")
        if (tr_ctx and tr_ctx.get("in_tr") and tr_ctx.get("tr_baseline_volume"))
        else None
    )

    def _valid_sos(sos_start: int, sos_end: int, tr_baseline: float | None = None) -> tuple[bool, float, float]:
        """返回 (是否有效 SOS, 前低, 基线均量)。"""
        if sos_start < baseline_len or sos_end - sos_start != sos_len:
            return False, 0.0, 0.0
        sos_window = bars[sos_start:sos_end]
        sos_opens: list[float] = []
        sos_closes: list[float] = []
        sos_vols: list[float] = []
        for b in sos_window:
            o = to_float(b.get("open"))
            c = to_float(b.get("close"))
            v = to_float(b.get("volume"))
            if o is None or c is None or v is None:
                return False, 0.0, 0.0
            sos_opens.append(o)
            sos_closes.append(c)
            sos_vols.append(v)
        bullish_count = sum(1 for c, o in zip(sos_closes, sos_opens) if c > o)
        if bullish_count < 4:
            return False, 0.0, 0.0
        if sos_closes[-1] < sos_opens[0]:
            return False, 0.0, 0.0
        gain = (sos_closes[-1] - sos_opens[0]) / max(sos_opens[0], 0.01)
        if gain < 0.02:
            return False, 0.0, 0.0
        if tr_baseline:
            baseline_avg_vol = tr_baseline
        else:
            baseline = bars[sos_start - baseline_len:sos_start]
            baseline_avg_vol = sum(to_float(b.get("volume")) or 0 for b in baseline) / max(len(baseline), 1)
            if baseline_avg_vol <= 0:
                return False, 0.0, 0.0
        if sum(sos_vols) / sos_len < baseline_avg_vol * 1.2:
            return False, 0.0, 0.0
        pre_start = max(0, sos_start - 5)
        pre_lows = [to_float(bars[i].get("low")) for i in range(pre_start, sos_start)]
        pre_lows = [v for v in pre_lows if v is not None]
        if not pre_lows:
            return False, 0.0, 0.0
        return True, min(pre_lows), baseline_avg_vol

    # 从近到远：sos_end = n-2, n-3, ... n-10 → 取最近一次有效 SOS 后只评估一次
    for pb_len in range(min_pb, max_pb + 1):
        sos_end = n - pb_len
        sos_start = sos_end - sos_len
        ok, pre_low, baseline_avg_vol = _valid_sos(sos_start, sos_end, tr_baseline)
        if not ok:
            continue

        pullback = bars[sos_end:n]
        pb_closes: list[float] = []
        pb_lows: list[float] = []
        pb_vols: list[float] = []
        for b in pullback:
            c = to_float(b.get("close"))
            lo = to_float(b.get("low"))
            v = to_float(b.get("volume"))
            if c is None or lo is None or v is None:
                continue
            pb_closes.append(c)
            pb_lows.append(lo)
            pb_vols.append(v)
        if len(pb_closes) < 2:
            # 最近有效 SOS 已找到但回调数据不足 → 结束，不回退更早 SOS
            return {"lps_signal": False, "lps_reason": "SOS 后回调数据不足", "lps_price": None}

        # 回调：价格下行或横盘（末收 ≤ 起始 * 1.01）
        if pb_closes[-1] > pb_closes[0] * 1.01:
            return {"lps_signal": False, "lps_reason": "SOS 后未形成有效回调", "lps_price": None}

        pb_low = min(pb_lows)
        # 不破 SOS 前低（允许 1% 容差）
        if pb_low < pre_low * 0.99:
            return {"lps_signal": False, "lps_reason": "回调跌破 SOS 前低", "lps_price": None}

        # 回调末端缩量
        if pb_vols[-1] >= baseline_avg_vol * 0.7:
            return {"lps_signal": False, "lps_reason": "回调量能不萎缩", "lps_price": None}

        return {
            "lps_signal": True,
            "lps_reason": f"SOS 后缩量回调，低点 {pb_low:.2f} 未破前低 {pre_low:.2f}",
            "lps_price": round(pb_low, 2),
        }

    return {"lps_signal": False, "lps_reason": "未检测到有效 LPS（需 SOS→缩量回调）", "lps_price": None}

def _detect_lpsy(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect LPSY (Last Point of Supply) — 派发末期反弹不过前高。

    对称于 LPS（最后支撑点），但方向相反：
      - 检测到 UT/SOW 事件后（派发背景）
      - 反弹 up 走势接近前高但未突破
      - 成交量萎缩（无需求跟进）
      - 是 Markdown 前最后一次做多机会/最后逃命波

    Returns:
        dict with keys: lpsy_signal (bool), lpsy_reason (str), lpsy_price (float)
    """
    if len(bars) < 15:
        return {"lpsy_signal": False, "lpsy_reason": "数据不足", "lpsy_price": None}

    # 阻力位：TR 内用 TR 上沿（原典 LPSY = 反弹不过 TR 上沿），否则近15根最高
    if tr_ctx is not None and tr_ctx.get("in_tr") and tr_ctx.get("tr_upper") is not None:
        resistance = tr_ctx["tr_upper"]
        res_idx = 0  # TR 上沿天然是更早的高点，跳过距离检查
    else:
        # 从近到远扫描找最近一次明显的高点（阻力位）
        # 取近 15 根 K 线中的最高价作为阻力锚点
        scan = bars[-15:]
        highs = [to_float(b.get("high")) for b in scan if to_float(b.get("high")) is not None]
        if not highs:
            return {"lpsy_signal": False, "lpsy_reason": "无有效高点数据", "lpsy_price": None}

        resistance = max(highs)
        res_idx = highs.index(resistance)
        # 阻力位必须距离当前至少 3 根 K 线（确保不是当前最高）
        if len(highs) - res_idx < 3:
            return {"lpsy_signal": False, "lpsy_reason": "阻力位在近期，未形成有效反弹结构", "lpsy_price": None}

    # 当前价格从下方接近阻力位但未突破
    last_close = to_float(bars[-1].get("close"))
    last_high = to_float(bars[-1].get("high"))
    if last_close is None or last_high is None:
        return {"lpsy_signal": False, "lpsy_reason": "数据异常", "lpsy_price": None}

    # 条件：当前在阻力位附近（95%-99.5%）但未突破
    near_resistance = last_close > resistance * 0.95 and last_high < resistance * 1.005
    if not near_resistance:
        return {"lpsy_signal": False, "lpsy_reason": f"价格 {last_close:.2f} 不在阻力 {resistance:.2f} 附近", "lpsy_price": None}

    # 缩量确认（相对于前 10 日均量）
    recent = bars[-11:-1] if len(bars) >= 11 else bars[:-1]
    avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    cur_vol = to_float(bars[-1].get("volume")) or 0
    if avg_vol > 0 and cur_vol > avg_vol * 0.8:
        return {"lpsy_signal": False, "lpsy_reason": "量能未萎缩，供应未枯竭", "lpsy_price": None}

    return {
        "lpsy_signal": True,
        "lpsy_reason": f"反弹至 {resistance:.2f} 受阻回落，缩量最后供应点",
        "lpsy_price": round(resistance, 2),
    }

def _scan_last_event(
    scan_bars: list[dict],
    detector_fn: Any,
    tr_ctx: dict | None,
    window: int,
    step: int = 1,
) -> tuple[int, dict | None]:
    """在 scan_bars 上滑窗扫描 detector_fn，返回 (最后触发 bar 的索引, 该次检测器完整输出)。

    所有事件检测器都检查子窗口最后一根 bar（bars[-1]）是否为信号，因此
    start+window-1 即为事件触发位置。用于事件簇确认时的先后顺序判断。

    Returns:
        (index, result) —— 未找到时 (-1, None)
    """
    n = len(scan_bars)
    if n < window:
        return -1, None
    last_idx = -1
    last_res: dict | None = None
    for start in range(0, n - window + 1, step):
        sub = scan_bars[start:start + window]
        try:
            # 统一用关键字传 tr_ctx：各 detector 第二位置参数不同
            # (_detect_spring / _detect_sign_of_weakness 第二参是 _support，
            #  位置传参会把 tr_ctx 错塞进 _support 导致 tr_ctx 实际为 None 而失效)
            res = detector_fn(sub, tr_ctx=tr_ctx)
        except Exception:
            continue
        if any(k.endswith("_signal") and res.get(k) is True for k in res):
            last_idx = start + window - 1
            last_res = res
    return last_idx, last_res

def _detect_event_cluster(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """事件簇确认 (Event Cluster Confirmation) — 将孤立信号升级为可信的积累/派发事件簇。

    原典逻辑：
      - 积累确认 (accumulation_confirmed)：支撑测试（Spring 或 ST）在先，随后 SOS 突破
        → 主力吸筹完成，Markup 将启动
      - 派发确认 (distribution_confirmed)：上冲 (Upthrust) 在先，随后 SOW 跌破
        → 主力派发完成，Markdown 将启动
      - 失败簇（反向信号）：
          · accumulation_failed：Spring 后接 SOW（非 SOS）→ 假突破，实为派发
          · distribution_failed：Upthrust 后接 SOS（非 SOW）→ 假派发，实为吸筹

    与阶段机的区别：本检测器显式校验事件先后顺序（trigger bar index），
    并用 P0-4 的 strength 字段给簇定级，输出干净的 confirmed/failed 布尔供 fusion 消费。

    Args:
        tr_ctx=None 时各检测器走原逻辑（向后兼容）。

    Returns:
        dict with keys:
          accumulation_confirmed, distribution_confirmed,
          accumulation_failed, distribution_failed,
          cluster_quality ("high"/"medium"/"low"/None),
          cluster_confidence (float 0-1),
          cluster_reason (str)
    """
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "accumulation_confirmed": False,
            "distribution_confirmed": False,
            "accumulation_failed": False,
            "distribution_failed": False,
            "cluster_quality": None,
            "cluster_confidence": 0.0,
            "cluster_reason": "数据不足",
        }

    lookback = WYCKOFF_CLUSTER_LOOKBACK
    scan = bars[-lookback:] if len(bars) > lookback else bars
    gap = WYCKOFF_CLUSTER_MIN_GAP

    # 在 scan 内找各事件最后触发位置 + 完整输出（用于读 strength）
    spring_idx, spring_res = _scan_last_event(scan, _detect_spring, tr_ctx, window=15, step=1)
    st_idx, _ = _scan_last_event(scan, _detect_st, tr_ctx, window=26, step=1)
    ut_idx, ut_res = _scan_last_event(scan, _detect_upthrust, tr_ctx, window=15, step=1)
    sos_idx, _ = _scan_last_event(scan, _detect_sos, tr_ctx, window=15, step=1)
    sow_idx, _ = _scan_last_event(scan, _detect_sign_of_weakness, tr_ctx, window=16, step=1)

    support_idx = max(spring_idx, st_idx)  # 支撑测试 = Spring 或 ST

    # 顺序确认：支撑测试必须先于 SOS（间隔 >= gap）；上冲必须先于 SOW
    accumulation_confirmed = support_idx >= 0 and sos_idx > support_idx + gap
    distribution_confirmed = ut_idx >= 0 and sow_idx > ut_idx + gap

    # 失败簇：支撑测试后接 SOW（且 SOS 不存在或在 SOW 之前）→ 假突破实为派发
    accumulation_failed = (
        support_idx >= 0
        and sow_idx > support_idx + gap
        and (sos_idx < 0 or sow_idx > sos_idx)
    )
    # 失败簇：上冲后接 SOS（且 SOW 不存在或在 SOS 之前）→ 假派发实为吸筹
    distribution_failed = (
        ut_idx >= 0
        and sos_idx > ut_idx + gap
        and (sow_idx < 0 or sos_idx > sow_idx)
    )

    # 质量分级（用 P0-4 strength 字段）
    quality = None
    confidence = 0.0
    reason_parts: list[str] = []

    if accumulation_confirmed:
        sp_strength = (spring_res or {}).get("spring_strength") if spring_idx >= st_idx else "ordinary"
        if sp_strength == "strong":
            quality, confidence = "high", 0.9
        elif sp_strength == "ordinary":
            quality, confidence = "medium", 0.65
        else:  # weak / failure / None
            quality, confidence = "low", 0.45
        reason_parts.append(f"积累确认：支撑测试({sp_strength})→SOS 突破")
    elif distribution_confirmed:
        ut_strength = (ut_res or {}).get("upthrust_strength")
        if ut_strength == "strong":
            quality, confidence = "high", 0.9
        elif ut_strength == "ordinary":
            quality, confidence = "medium", 0.65
        else:
            quality, confidence = "low", 0.45
        reason_parts.append(f"派发确认：上冲({ut_strength})→SOW 跌破")
    elif accumulation_failed:
        reason_parts.append("积累失败：Spring 后接 SOW（假突破，实为派发）")
        confidence = 0.8
    elif distribution_failed:
        reason_parts.append("派发失败：上冲后接 SOS（假派发，实为吸筹）")
        confidence = 0.8

    if not reason_parts:
        reason_parts.append("无确认事件簇")

    return {
        "accumulation_confirmed": accumulation_confirmed,
        "distribution_confirmed": distribution_confirmed,
        "accumulation_failed": accumulation_failed,
        "distribution_failed": distribution_failed,
        "cluster_quality": quality,
        "cluster_confidence": confidence,
        "cluster_reason": "；".join(reason_parts),
    }

def _detect_effort_vs_result(bars: list[dict]) -> dict[str, bool]:
    """基础量价幅度分析（Effort vs Result）。

    检测最近 3 根 K 线的 spread（high-low）与 volume 的关系：
    - 高量窄幅（Effort No Result）：vol > 1.5x avg 且 spread < 0.7x avg_spread
      → 努力无结果，供应仍在
    - 低量窄幅（No Supply）：vol < 0.7x avg 且 spread < 0.7x avg_spread
      → 供应耗尽，可靠信号

    Returns:
        {"effort_no_result": bool, "no_supply": bool}
    """
    period = WYCKOFF_VSA_AVG_SPREAD_PERIOD
    if len(bars) < period + 3:
        return {"effort_no_result": False, "no_supply": False}

    # 计算基线均量和平均波幅
    baseline = bars[-(period + 3):-3]
    volumes_b = [to_float(b.get("volume")) or 0 for b in baseline]
    spreads_b = []
    for b in baseline:
        h = to_float(b.get("high"))
        l = to_float(b.get("low"))
        if h is not None and l is not None:
            spreads_b.append(h - l)
    avg_vol = sum(volumes_b) / max(len(volumes_b), 1)
    avg_spread = sum(spreads_b) / max(len(spreads_b), 1) if spreads_b else 0

    if avg_vol <= 0 or avg_spread <= 0:
        return {"effort_no_result": False, "no_supply": False}

    # 检查最近 3 根 K 线
    recent3 = bars[-3:]
    for b in recent3:
        vol = to_float(b.get("volume")) or 0
        high = to_float(b.get("high"))
        low = to_float(b.get("low"))
        if high is None or low is None:
            continue
        spread = high - low
        if vol > avg_vol * 1.5 and spread < avg_spread * 0.7:
            return {"effort_no_result": True, "no_supply": False}
        if vol < avg_vol * 0.7 and spread < avg_spread * 0.7:
            return {"effort_no_result": False, "no_supply": True}

    return {"effort_no_result": False, "no_supply": False}

def _detect_compression(bars: list[dict]) -> dict:
    """检测压缩蓄势：振幅收窄 + 量能枯竭 = 蓄势待发。

    触发条件:
      1. 近 N 日 ATR 分位数 < 20%（振幅压缩）
      2. 近 N 日均量 / 参考均量 < 0.6（量能枯竭）
      3. 非下降结构（防止阴跌缩量误判）
    """
    lookback = WYCKOFF_COMPRESSION_LOOKBACK
    ref_window = WYCKOFF_COMPRESSION_VOL_REF_WINDOW
    if len(bars) < max(lookback, ref_window) + 5:
        return {"compression_signal": False, "compression_reason": "数据不足", "compression_price": None}

    recent = bars[-lookback:]
    ref = bars[-(ref_window + lookback):-lookback] if len(bars) >= ref_window + lookback else bars[:max(1, len(bars) - lookback)]

    # 计算近 N 日 ATR
    trs = []
    for i in range(1, len(recent)):
        h = to_float(recent[i].get("high"))
        l = to_float(recent[i].get("low"))
        pc = to_float(recent[i - 1].get("close"))
        if h is None or l is None or pc is None:
            continue
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return {"compression_signal": False, "compression_reason": "ATR 计算失败", "compression_price": None}

    current_atr = trs[-1]
    avg_atr = sum(trs) / len(trs)
    if avg_atr <= 0:
        return {"compression_signal": False, "compression_reason": "ATR 为零", "compression_price": None}

    # ATR 分位数检查：当前 ATR 是否处于历史低位
    atr_values = sorted(trs)
    atr_rank = sum(1 for t in atr_values if t <= current_atr) / len(atr_values)
    if atr_rank > WYCKOFF_COMPRESSION_ATR_QUANTILE:
        return {"compression_signal": False, "compression_reason": f"振幅未压缩（ATR分位 {atr_rank:.0%}）", "compression_price": None}

    # 量能萎缩检查
    recent_vols = [to_float(b.get("volume")) for b in recent if to_float(b.get("volume")) is not None]
    ref_vols = [to_float(b.get("volume")) for b in ref if to_float(b.get("volume")) is not None]
    if not recent_vols or not ref_vols:
        return {"compression_signal": False, "compression_reason": "成交量数据不足", "compression_price": None}

    avg_recent_vol = sum(recent_vols) / len(recent_vols)
    avg_ref_vol = sum(ref_vols) / len(ref_vols)
    if avg_ref_vol <= 0:
        return {"compression_signal": False, "compression_reason": "参考量为零", "compression_price": None}

    vol_ratio = avg_recent_vol / avg_ref_vol
    if vol_ratio >= WYCKOFF_COMPRESSION_VOL_RATIO:
        return {"compression_signal": False, "compression_reason": f"量能未萎缩（量比 {vol_ratio:.2f}）", "compression_price": None}

    # 非下降结构检查：近 5 根收盘价不能持续下跌
    recent_closes = [to_float(b.get("close")) for b in recent[-5:]]
    recent_closes = [c for c in recent_closes if c is not None]
    if len(recent_closes) >= 3:
        declines = sum(1 for i in range(1, len(recent_closes)) if recent_closes[i] < recent_closes[i - 1])
        if declines >= len(recent_closes) - 1:
            return {"compression_signal": False, "compression_reason": "下降结构中，非蓄势", "compression_price": None}

    # 找到当前价格区间
    recent_highs = [to_float(b.get("high")) for b in recent if to_float(b.get("high")) is not None]
    recent_lows = [to_float(b.get("low")) for b in recent if to_float(b.get("low")) is not None]
    if recent_highs and recent_lows:
        current_price = to_float(recent[-1].get("close"))
        return {
            "compression_signal": True,
            "compression_reason": f"振幅压缩（ATR分位 {atr_rank:.0%}）+ 量能枯竭（量比 {vol_ratio:.2f}）",
            "compression_price": round(current_price, 2) if current_price else None,
        }

    return {"compression_signal": False, "compression_reason": "数据异常", "compression_price": None}

def _detect_trend_pullback(bars: list[dict]) -> dict:
    """检测趋势回踩：上升趋势中回踩不破关键均线 = 买点。

    触发条件:
      1. 近 N 日有回撤（5-20%）
      2. 回落段缩量（量比 < 0.6）
      3. 收盘站稳 MA20 附近（±2%）
      4. MA20 仍在上升
    """
    lookback = WYCKOFF_TREND_PB_LOOKBACK
    ma_window = WYCKOFF_TREND_PB_MA_WINDOW
    if len(bars) < max(lookback, ma_window) + 5:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "数据不足", "trend_pullback_price": None}

    recent = bars[-lookback:]
    recent_closes = [to_float(b.get("close")) for b in recent]
    recent_closes = [c for c in recent_closes if c is not None]
    if len(recent_closes) < lookback:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "收盘价数据不足", "trend_pullback_price": None}

    # 计算回撤幅度
    high_close = max(recent_closes)
    low_close = min(recent_closes)
    current_close = recent_closes[-1]
    if high_close <= 0:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "价格异常", "trend_pullback_price": None}

    pullback_pct = (high_close - current_close) / high_close * 100
    if pullback_pct < WYCKOFF_TREND_PB_MIN_PULLBACK:
        return {"trend_pullback_signal": False, "trend_pullback_reason": f"回撤不足（{pullback_pct:.1f}% < {WYCKOFF_TREND_PB_MIN_PULLBACK}%）", "trend_pullback_price": None}
    if pullback_pct > WYCKOFF_TREND_PB_MAX_PULLBACK:
        return {"trend_pullback_signal": False, "trend_pullback_reason": f"回撤过大（{pullback_pct:.1f}% > {WYCKOFF_TREND_PB_MAX_PULLBACK}%），趋势可能已破坏", "trend_pullback_price": None}

    # 计算 MA20
    all_closes = [to_float(b.get("close")) for b in bars]
    all_closes = [c for c in all_closes if c is not None]
    if len(all_closes) < ma_window:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "MA 数据不足", "trend_pullback_price": None}

    ma_vals = []
    for i in range(ma_window - 1, len(all_closes)):
        ma_vals.append(sum(all_closes[i - ma_window + 1:i + 1]) / ma_window)
    if len(ma_vals) < 3:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "MA 序列不足", "trend_pullback_price": None}

    ma_current = ma_vals[-1]
    ma_prev = ma_vals[-3]

    # MA20 必须在上升
    if ma_current <= ma_prev:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "MA20 未上升，趋势不明确", "trend_pullback_price": None}

    # 收盘价在 MA20 附近（±2%）
    if ma_current <= 0:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "MA20 异常", "trend_pullback_price": None}
    ma_deviation = abs(current_close - ma_current) / ma_current
    if ma_deviation > 0.02:
        return {"trend_pullback_signal": False, "trend_pullback_reason": f"收盘偏离 MA20 过远（{ma_deviation:.1%} > 2%）", "trend_pullback_price": None}

    # 回落段缩量检查
    recent_vols = [to_float(b.get("volume")) for b in recent if to_float(b.get("volume")) is not None]
    all_vols = [to_float(b.get("volume")) for b in bars if to_float(b.get("volume")) is not None]
    if len(recent_vols) < 3 or len(all_vols) < ma_window:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "成交量数据不足", "trend_pullback_price": None}

    avg_recent_vol = sum(recent_vols) / len(recent_vols)
    avg_ref_vol = sum(all_vols[-ma_window:]) / ma_window
    if avg_ref_vol <= 0:
        return {"trend_pullback_signal": False, "trend_pullback_reason": "参考量为零", "trend_pullback_price": None}

    vol_ratio = avg_recent_vol / avg_ref_vol
    if vol_ratio >= WYCKOFF_TREND_PB_VOL_SHRINK:
        return {"trend_pullback_signal": False, "trend_pullback_reason": f"回踩未缩量（量比 {vol_ratio:.2f}）", "trend_pullback_price": None}

    return {
        "trend_pullback_signal": True,
        "trend_pullback_reason": f"趋势回踩（回撤 {pullback_pct:.1f}%）+ 缩量（量比 {vol_ratio:.2f}）+ 站稳 MA20",
        "trend_pullback_price": round(current_close, 2),
    }


# ── 原典补齐：PS / PSY / BU / UTAD / 因果目标 ──────────────────────────────


def _detect_preliminary_support(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """PS (Preliminary Support) — SC 之前的初步止跌：低位放量阴/十字，跌幅弱于 SC。

    与 SC 区分：不要求「高潮级」宽幅暴跌，只要求低位 + 量能放大 + 收盘未创新低塌陷。
    若当日已是 SC 则不重复报 PS。
    """
    if len(bars) < 12:
        return {"ps_signal": False, "ps_reason": "数据不足", "ps_price": None}
    sc = _detect_selling_climax(bars, tr_ctx=tr_ctx)
    if sc.get("sc_signal"):
        return {"ps_signal": False, "ps_reason": "当日已是 SC，PS 让位", "ps_price": None}

    cur = bars[-1]
    recent = bars[-11:-1]
    avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    cur_vol = to_float(cur.get("volume")) or 0
    cur_open = to_float(cur.get("open"))
    cur_close = to_float(cur.get("close"))
    cur_low = to_float(cur.get("low"))
    prev_close = to_float(bars[-2].get("close")) if len(bars) >= 2 else cur_open
    if not avg_vol or cur_close is None or prev_close is None or cur_open is None:
        return {"ps_signal": False, "ps_reason": "数据异常", "ps_price": None}

    pos = _price_pos_pct(bars, len(bars) - 1)
    if pos is None or pos > 0.45:
        return {"ps_signal": False, "ps_reason": "非低位，非 PS", "ps_price": None}
    if cur_vol < avg_vol * 1.4:
        return {"ps_signal": False, "ps_reason": "量能不足", "ps_price": None}
    chg = (cur_close - prev_close) / max(abs(prev_close), 0.01) * 100
    # 下跌但非崩盘（崩盘归 SC）：-0.5% ~ -6%，或阴线收在区间中上部
    if chg > -0.3:
        return {"ps_signal": False, "ps_reason": "未体现止跌抛压", "ps_price": None}
    if chg < -7.0:
        return {"ps_signal": False, "ps_reason": "跌幅过大，更接近 SC", "ps_price": None}
    body_ok = cur_close >= cur_open or (cur_low is not None and cur_close > cur_low * 1.005)
    if not body_ok:
        return {"ps_signal": False, "ps_reason": "收盘过弱", "ps_price": None}
    return {
        "ps_signal": True,
        "ps_reason": f"低位放量初步止跌（量比 {cur_vol / avg_vol:.1f}，{chg:.1f}%）",
        "ps_price": round(cur_close, 2),
    }


def _detect_preliminary_supply(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """PSY (Preliminary Supply) — BC 之前的初步供应：高位放量滞涨/上影。"""
    if len(bars) < 12:
        return {"psy_signal": False, "psy_reason": "数据不足", "psy_price": None}
    bc = _detect_buying_climax(bars, tr_ctx=tr_ctx)
    if bc.get("bc_signal"):
        return {"psy_signal": False, "psy_reason": "当日已是 BC，PSY 让位", "psy_price": None}

    cur = bars[-1]
    recent = bars[-11:-1]
    avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    cur_vol = to_float(cur.get("volume")) or 0
    cur_open = to_float(cur.get("open"))
    cur_close = to_float(cur.get("close"))
    cur_high = to_float(cur.get("high"))
    cur_low = to_float(cur.get("low"))
    prev_close = to_float(bars[-2].get("close")) if len(bars) >= 2 else cur_open
    if not avg_vol or cur_close is None or prev_close is None or cur_open is None:
        return {"psy_signal": False, "psy_reason": "数据异常", "psy_price": None}

    pos = _price_pos_pct(bars, len(bars) - 1)
    if pos is None or pos < 0.55:
        return {"psy_signal": False, "psy_reason": "非高位，非 PSY", "psy_price": None}
    if cur_vol < avg_vol * 1.4:
        return {"psy_signal": False, "psy_reason": "量能不足", "psy_price": None}
    chg = (cur_close - prev_close) / max(abs(prev_close), 0.01) * 100
    rng = (cur_high - cur_low) if cur_high is not None and cur_low is not None else 0
    upper = (cur_high - max(cur_open, cur_close)) if cur_high is not None else 0
    has_upper = rng > 0 and upper / rng > 0.35
    stagnant = chg < 1.5
    if not (stagnant or has_upper or cur_close < cur_open):
        return {"psy_signal": False, "psy_reason": "无滞涨/上影特征", "psy_price": None}
    return {
        "psy_signal": True,
        "psy_reason": f"高位放量初步供应（量比 {cur_vol / avg_vol:.1f}）",
        "psy_price": round(cur_close, 2),
    }


def _detect_backup(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """BU (Backup) — SOS 突破后缩量回踩不破突破位/TR 上沿（Markup 初期买点）。"""
    if len(bars) < 20:
        return {"bu_signal": False, "bu_reason": "数据不足", "bu_price": None}

    # 在近 12 根内找 SOS 锚点
    sos_idx = -1
    sos_low = None
    for i in range(len(bars) - 2, max(0, len(bars) - 13), -1):
        sub = bars[: i + 1]
        if len(sub) < 15:
            continue
        try:
            r = _detect_sos(sub, tr_ctx=tr_ctx)
        except Exception:
            continue
        if r.get("sos_signal"):
            sos_idx = i
            lows = [to_float(b.get("low")) for b in sub[-5:] if to_float(b.get("low")) is not None]
            sos_low = min(lows) if lows else to_float(bars[i].get("close"))
            break
    if sos_idx < 0 or sos_low is None:
        return {"bu_signal": False, "bu_reason": "近端无 SOS，无 Backup", "bu_price": None}

    # 当前须在 SOS 之后至少 2 根，且为回踩（close < 近高）
    if len(bars) - 1 - sos_idx < 2:
        return {"bu_signal": False, "bu_reason": "SOS 过新，尚未回踩", "bu_price": None}

    cur = bars[-1]
    cur_close = to_float(cur.get("close"))
    cur_low = to_float(cur.get("low"))
    if cur_close is None or cur_low is None:
        return {"bu_signal": False, "bu_reason": "数据异常", "bu_price": None}

    # 支撑：TR 上沿优先，否则 SOS 窗口低点
    floor = sos_low
    if tr_ctx and tr_ctx.get("tr_upper") is not None:
        floor = max(floor, float(tr_ctx["tr_upper"]) * 0.995)

    if cur_low < floor * 0.985:
        return {"bu_signal": False, "bu_reason": "回踩跌破突破位", "bu_price": None}
    if cur_close < floor * 0.99:
        return {"bu_signal": False, "bu_reason": "收盘未守住突破区", "bu_price": None}

    recent = bars[sos_idx:len(bars) - 1] or bars[-6:-1]
    avg_vol = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    cur_vol = to_float(cur.get("volume")) or 0
    if avg_vol > 0 and cur_vol > avg_vol * 0.85:
        return {"bu_signal": False, "bu_reason": "回踩未缩量", "bu_price": None}

    return {
        "bu_signal": True,
        "bu_reason": f"SOS 后缩量回踩不破 {floor:.2f}（Backup）",
        "bu_price": round(cur_close, 2),
    }


def _detect_utad(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    bc_signal: bool = False,
    sow_signal: bool = False,
    upthrust_signal: bool = False,
    upthrust_result: dict | None = None,
) -> dict:
    """UTAD — 派发区末端上冲：须有派发背景（BC 或 SOW）且当日 UT 成立。"""
    has_dist = bool(bc_signal or sow_signal)
    if not has_dist:
        # 滑窗弱扫描：近端是否有 BC
        if len(bars) >= 15:
            try:
                has_dist = bool(_detect_buying_climax(bars).get("bc_signal"))
            except Exception:
                has_dist = False
    if not has_dist:
        return {"utad_signal": False, "utad_reason": "无派发背景（需 BC/SOW）", "utad_price": None}

    ut = upthrust_result if upthrust_result is not None else _detect_upthrust(bars, tr_ctx=tr_ctx)
    if not (upthrust_signal or ut.get("upthrust_signal")):
        return {"utad_signal": False, "utad_reason": "无上冲回落，非 UTAD", "utad_price": None}
    if ut.get("upthrust_strength") == "failure":
        return {"utad_signal": False, "utad_reason": "上冲未收回，非 UTAD", "utad_price": None}

    price = ut.get("upthrust_price") or to_float(bars[-1].get("close"))
    return {
        "utad_signal": True,
        "utad_reason": "派发背景上的上冲回落（UTAD）",
        "utad_price": round(price, 2) if price else None,
    }


def _cause_effect_targets(tr_ctx: dict | None, bars: list[dict] | None = None) -> dict:
    """因果律简化执行：用 TR 高度 1:1 投射目标（水平计数近似，非完整 P&F）。

    上升目标 ≈ tr_upper + (tr_upper - tr_lower)
    下降目标 ≈ tr_lower - (tr_upper - tr_lower)
    """
    empty = {
        "cause_effect_up_target": None,
        "cause_effect_down_target": None,
        "cause_effect_range": None,
        "cause_effect_note": "无有效 TR，无法做因果目标",
    }
    if not tr_ctx:
        return empty
    try:
        upper = float(tr_ctx["tr_upper"])
        lower = float(tr_ctx["tr_lower"])
    except (TypeError, ValueError, KeyError):
        return empty
    if upper <= lower:
        return empty
    height = upper - lower
    return {
        "cause_effect_up_target": round(upper + height, 2),
        "cause_effect_down_target": round(lower - height, 2),
        "cause_effect_range": round(height, 2),
        "cause_effect_note": (
            f"TR 高度 {height:.2f} 作 1:1 投射（简化因果/水平计数近似，非点数图）"
        ),
    }
