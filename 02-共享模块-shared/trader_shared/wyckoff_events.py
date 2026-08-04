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
        WYCKOFF_CLIMAX_ANCHOR_BARS,
        WYCKOFF_SC_COLD_START_BARS_DAILY,
        WYCKOFF_SC_COLD_START_BARS_WEEKLY,
        WYCKOFF_AR_MAX_BARS,
        WYCKOFF_AR_PREFER_WEAK_VS_SC,
        WYCKOFF_AR_REQUIRE_WEAK_VS_SC,
        WYCKOFF_AR_WEAK_VS_SC_RATIO,
        WYCKOFF_ST_SC_VOL_RATIO,
        WYCKOFF_ST_SC_MAX_BARS,
        WYCKOFF_ST_SC_PROXIMITY,
        WYCKOFF_ST_SC_MAX_PIERCE,
        WYCKOFF_ST_SC_SPREAD_RATIO,
        WYCKOFF_BC_VOL_RATIO_THRESHOLD,
        WYCKOFF_BC_CHANGE_THRESHOLD,
        WYCKOFF_BC_UPPER_SHADOW_RATIO,
        WYCKOFF_BC_SCAN_BARS,
        WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO,
        WYCKOFF_BC_MIN_POS_PCT,
        WYCKOFF_SC_MAX_POS_PCT,
        WYCKOFF_SC_CHANGE_PCT_MAX_DAILY,
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
        WYCKOFF_SOS_THRUST_MIN_GAIN,
        WYCKOFF_SOS_THRUST_VOL_RATIO,
        WYCKOFF_SOS_RECENT_LOOKBACK,
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
        WYCKOFF_SCORE_ARE,
        WYCKOFF_SCORE_SOS,
        WYCKOFF_SCORE_ST,
        WYCKOFF_SCORE_LPS,
        WYCKOFF_SCORE_LPSY,
        # P2/P3 新增
        WYCKOFF_SCORE_COMPRESSION,
        WYCKOFF_SCORE_TREND_PB,
        WYCKOFF_SCORE_TREND_RALLY,
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
        WYCKOFF_TR_FALLBACK_MIN_WIDTH,
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
        WYCKOFF_CLUSTER_EVENT_FRESH_BARS,
    )
except ImportError:
    WYCKOFF_MIN_BARS = 15
    WYCKOFF_CLIMAX_ANCHOR_BARS = 15
    WYCKOFF_SC_COLD_START_BARS_DAILY = 90
    WYCKOFF_SC_COLD_START_BARS_WEEKLY = 39
    WYCKOFF_AR_MAX_BARS = 15
    WYCKOFF_AR_PREFER_WEAK_VS_SC = True
    WYCKOFF_AR_REQUIRE_WEAK_VS_SC = False
    WYCKOFF_AR_WEAK_VS_SC_RATIO = 1.0
    # 广义 ST 默认须与 config.py 同步（A 股放宽后）
    WYCKOFF_ST_SC_VOL_RATIO = 0.80
    WYCKOFF_ST_SC_MAX_BARS = 22
    WYCKOFF_ST_SC_PROXIMITY = 0.045
    WYCKOFF_ST_SC_MAX_PIERCE = 0.012
    WYCKOFF_ST_SC_SPREAD_RATIO = 0.85
    WYCKOFF_BC_VOL_RATIO_THRESHOLD = 1.5  # must match config.py
    WYCKOFF_BC_CHANGE_THRESHOLD = 1.0
    WYCKOFF_BC_UPPER_SHADOW_RATIO = 0.02
    WYCKOFF_BC_MIN_POS_PCT = 0.65
    WYCKOFF_SC_MAX_POS_PCT = 0.50
    WYCKOFF_SC_CHANGE_PCT_MAX_DAILY = -1.5
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
    WYCKOFF_SOS_THRUST_MIN_GAIN = 0.05
    WYCKOFF_SOS_THRUST_VOL_RATIO = 1.8
    WYCKOFF_SOS_RECENT_LOOKBACK = 30
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
    WYCKOFF_SCORE_ARE = -10
    WYCKOFF_SCORE_SOS = 15
    WYCKOFF_SCORE_ST = 8
    WYCKOFF_SCORE_LPS = 12
    # LPSY 最后供应点（负向，对称于 LPS）
    WYCKOFF_SCORE_LPSY = -12
    # P2/P3 fallback
    WYCKOFF_SCORE_COMPRESSION = 10
    WYCKOFF_SCORE_TREND_PB = 8
    WYCKOFF_SCORE_TREND_RALLY = -8
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
    WYCKOFF_TR_FALLBACK_MIN_WIDTH = 10
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
    WYCKOFF_CLUSTER_EVENT_FRESH_BARS = 10


# ── 共享工具：Spring 刺穿深度 / BC 高位过滤 ─────────────────────────


def _spring_breach_level(support: float, bar: dict | None = None) -> float:
    """Spring 刺穿深度线：优先 ATR，fallback 固定比例。

    与 _detect_spring / _detect_st 共用，避免 ST 回扫用固定 1.5% 而 Spring 用 ATR。
    """
    atr14 = to_float(bar.get("atr14")) if bar else None
    if atr14 is not None and atr14 > 0:
        return support - atr14 * WYCKOFF_SPRING_ATR_MULTIPLE
    return support * WYCKOFF_SPRING_RECLAIM_RATIO

def _price_pos_pct(
    bars: list[dict],
    idx: int,
    lookback: int | None = None,
    *,
    ref: str = "high",
) -> float | None:
    """计算 bars[idx] 在近窗高低区间中的位置 (0=底, 1=顶)。

    ref:
      - ``high``（默认）：max(close, high)，偏高位过滤（BC）
      - ``close``：收盘价，适合 SC 低位（周线高潮周高低跨度大时勿用 high）
      - ``low``：min(close, low)
    """
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
    low = to_float(bars[idx].get("low"))
    if not valid_h or not valid_l or close is None:
        return None
    range_hi = max(valid_h)
    range_lo = min(valid_l)
    span = range_hi - range_lo
    if span <= 0:
        return 1.0  # 无波动时视为中性高位
    if ref == "close":
        px = close
    elif ref == "low":
        px = min(close, low if low is not None else close)
    else:
        # 用 high/close 较高者判定是否在高位区
        px = max(close, high if high is not None else close)
    return (px - range_lo) / span


# 常见 A 股指数 ts_code（须带后缀时区分 000001.SH 上证 vs 000001.SZ 个股）
_WYCKOFF_INDEX_TS_CODES = frozenset({
    "000001.SH",  # 上证综指
    "399001.SZ",  # 深成指
    "399006.SZ",  # 创业板指
    "000688.SH",  # 科创50
    "000852.SH",  # 中证1000
    "000300.SH",  # 沪深300
    "000016.SH",  # 上证50
    "399005.SZ",  # 中小100
})
# 无歧义裸码（不含 000001）
_WYCKOFF_INDEX_BARE_CODES = frozenset({
    "000852", "000688", "399001", "399006", "000300", "000016", "399005",
})


def resolve_wyckoff_is_index(symbol: Any = "") -> bool:
    """识别威科夫分析标的是否为指数（用于放宽 SC 量阈，禁止软 ST 绕过）。

    带 ``.SH/.SZ/.BJ`` 后缀时**只**认完整 ``ts_code`` 白名单，禁止去后缀走裸码
    （避免 ``000300.SZ`` 维维股份、``000016.SZ`` 深康佳 误判为沪深300/上证50）。
    """
    if symbol is None:
        return False
    if hasattr(symbol, "ts_code"):
        ts = str(getattr(symbol, "ts_code", "") or "").strip().upper()
        if ts in _WYCKOFF_INDEX_TS_CODES:
            return True
        code = str(getattr(symbol, "code", "") or "").strip()
        market = str(getattr(symbol, "market", "") or "").strip().upper()
        if code and market:
            digits = "".join(ch for ch in code if ch.isdigit())[-6:]
            return f"{digits}.{market}" in _WYCKOFF_INDEX_TS_CODES
        symbol = code or ts
    raw = str(symbol or "").strip().upper().replace("_", ".")
    if not raw:
        return False
    if raw in _WYCKOFF_INDEX_TS_CODES:
        return True
    # sh000001 / sz399001
    if raw.startswith(("SH", "SZ")) and len(raw) >= 8 and "." not in raw:
        mkt, digits = raw[:2], raw[2:]
        if digits.isdigit():
            return f"{digits}.{mkt}" in _WYCKOFF_INDEX_TS_CODES
        return False
    # 带交易所后缀：只匹配完整 ts_code，禁止 strip 后撞裸码白名单
    if ".SH" in raw or ".SZ" in raw or ".BJ" in raw:
        parts = raw.split(".")
        if len(parts) >= 2:
            digits = "".join(ch for ch in parts[0] if ch.isdigit())[-6:]
            mkt = parts[1][:2]
            if digits and mkt:
                return f"{digits}.{mkt}" in _WYCKOFF_INDEX_TS_CODES
        return False
    # 无后缀：仅无无歧义裸码（不含 000001；000001 须带 .SH）
    bare = "".join(ch for ch in raw if ch.isdigit())[-6:] if raw else ""
    return bare in _WYCKOFF_INDEX_BARE_CODES


def _sc_detector_params(timeframe: str = "daily", *, is_index: bool = False) -> dict:
    """日/周线 SC 锚点参数。

    ``anchor_bars`` 是无 alive 锚时的冷启动 CAP（日 90 / 周 39），
    不是旧 ``WYCKOFF_CLIMAX_ANCHOR_BARS`` 的 15 根短窗。

    指数/大盘：量比难达个股阈值 → 略放宽 SC 量阈；ST 仍强制回测 SC 区，禁止软确认绕过。
    """
    if str(timeframe or "").lower() == "weekly":
        params = {
            "anchor_bars": int(WYCKOFF_SC_COLD_START_BARS_WEEKLY),
            "support_lookback": max(4, int(WYCKOFF_SPRING_SUPPORT_LOOKBACK * 0.5)),
            "vol_ratio_threshold": min(WYCKOFF_BC_VOL_RATIO_THRESHOLD, 1.25),
            "change_pct_max": -1.0,  # 周线跌幅门槛略宽（仍须明显下跌）
            "pos_ref": "close",
        }
    else:
        params = {
            "anchor_bars": int(WYCKOFF_SC_COLD_START_BARS_DAILY),
            "support_lookback": WYCKOFF_SPRING_SUPPORT_LOOKBACK,
            "vol_ratio_threshold": WYCKOFF_BC_VOL_RATIO_THRESHOLD,
            "change_pct_max": float(WYCKOFF_SC_CHANGE_PCT_MAX_DAILY),
            "pos_ref": "high",  # 与历史日线 SC 行为一致（低位仍用 pos 上界过滤）
        }
    if is_index:
        # 指数量比偏平滑：SC 量阈略降；广义 ST 不得用「站在 SC 上方」软确认替代回测
        params["vol_ratio_threshold"] = min(float(params["vol_ratio_threshold"]), 1.35)
    return params

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

def _tr_dir_changes(bars: list[dict], start: int, end: int) -> int:
    """候选窗内相邻收盘方向交替次数（end 为开区间终点索引）。"""
    dir_changes = 0
    prev_dir = 0
    for j in range(start + 1, end):
        cj = to_float(bars[j].get("close"))
        cj1 = to_float(bars[j - 1].get("close"))
        if cj is None or cj1 is None:
            continue
        d = 1 if cj > cj1 else (-1 if cj < cj1 else 0)
        if d != 0 and prev_dir != 0 and d != prev_dir:
            dir_changes += 1
        if d != 0:
            prev_dir = d
    return dir_changes


def _tr_build_from_slice(
    bars: list[dict],
    start: int,
    end: int,
    *,
    min_amplitude_pct: float,
    max_amplitude_pct: float,
    min_dir_changes: int = 2,
) -> dict | None:
    """由 [start, end) 切片构建 TR；不合格返回 None。振幅用绝对 hi/lo；边界用分位带。"""
    if end <= start:
        return None
    width = end - start
    hi_max: float | None = None
    lo_min: float | None = None
    vol_sum = 0.0
    count = 0
    _lows: list[float] = []
    _highs: list[float] = []
    for j in range(start, end):
        h = to_float(bars[j].get("high"))
        l = to_float(bars[j].get("low"))
        v = to_float(bars[j].get("volume"))
        if h is None or l is None or v is None or l <= 0:
            continue
        hi_max = h if hi_max is None else max(hi_max, h)
        lo_min = l if lo_min is None else min(lo_min, l)
        vol_sum += v
        count += 1
        _lows.append(l)
        _highs.append(h)
    if hi_max is None or lo_min is None or lo_min <= 0 or count <= 0:
        return None
    amplitude = (hi_max - lo_min) / lo_min * 100
    if amplitude < min_amplitude_pct or amplitude > max_amplitude_pct:
        return None
    if _tr_dir_changes(bars, start, end) < min_dir_changes:
        return None

    bound_hi, bound_lo = hi_max, lo_min
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
            bound_hi, bound_lo = _pctl_upper, _pctl_lower

    last = bars[end - 1]
    close_last = to_float(last.get("close"))
    in_tr = (close_last is not None) and (bound_lo <= close_last <= bound_hi)
    width_score = min(1.0, width / max(1, WYCKOFF_TR_QUALITY_WIDTH_REF))
    amp_mid = (min_amplitude_pct + max_amplitude_pct) / 2.0
    amp_score = 1.0 - abs(amplitude - amp_mid) / max(amp_mid, 1e-6) * 0.5
    amp_score = max(0.3, min(1.0, amp_score))
    tr_quality = round(width_score * 0.7 + amp_score * 0.3, 3)

    return {
        "tr_upper": round(bound_hi, 4),
        "tr_lower": round(bound_lo, 4),
        "tr_baseline_volume": round(vol_sum / count, 2),
        "tr_start": start,
        "tr_end": end - 1,
        "tr_width": width,
        "tr_amplitude_pct": round(amplitude, 2),
        "tr_quality": tr_quality,
        "in_tr": bool(in_tr),
    }


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

    主路径：从当前 bar 向后回溯 grow，振幅超限则停（兼容旧行为）。
    Fallback（Bug B / wyckoff-sos-epic-bcg-handoff）：主路径失败时，末端对齐滑窗
    [FALLBACK_MIN_WIDTH .. lookback] 取质量最高合格候选（SC 前高打断 / 崩盘后短横盘）。

    Returns:
        dict | None（tr_upper/lower/baseline/start/end/width/amp/quality/in_tr；fallback 时 tr_fallback=True）
    """
    n = len(bars)
    fb_min = max(4, int(WYCKOFF_TR_FALLBACK_MIN_WIDTH))
    if n < min(min_width, fb_min):
        return None
    _lookback = min(lookback if lookback is not None else WYCKOFF_TR_LOOKBACK, n)
    start_search = max(0, n - _lookback)

    # ── 主路径 grow ──────────────────────────────────────────────
    primary: dict | None = None
    if n >= min_width:
        last = bars[-1]
        hi_max = to_float(last.get("high"))
        lo_min = to_float(last.get("low"))
        last_vol = to_float(last.get("volume"))
        if hi_max is not None and lo_min is not None and last_vol is not None and lo_min > 0:
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
                if amp > max_amplitude_pct:
                    break
                hi_max, lo_min = new_hi, new_lo
                count += 1
                if count >= min_width:
                    best_start = i
            if n - best_start >= min_width:
                primary = _tr_build_from_slice(
                    bars,
                    best_start,
                    n,
                    min_amplitude_pct=min_amplitude_pct,
                    max_amplitude_pct=max_amplitude_pct,
                )
    if primary is not None:
        return primary

    # ── Fallback：末端对齐滑窗（不降低全局 MIN_WIDTH）────────────────
    best_fb: dict | None = None
    best_q = -1.0
    max_w = min(_lookback, n)
    for width in range(fb_min, max_w + 1):
        start = n - width
        cand = _tr_build_from_slice(
            bars,
            start,
            n,
            min_amplitude_pct=min_amplitude_pct,
            max_amplitude_pct=max_amplitude_pct,
        )
        if cand is None:
            continue
        q = float(cand.get("tr_quality") or 0.0)
        prev_w = int((best_fb or {}).get("tr_width") or 0)
        if q > best_q or (q == best_q and width > prev_w):
            best_q = q
            best_fb = {**cand, "tr_fallback": True}
    return best_fb

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

    Bug H 重构（wyckoff-sos-修复交接说明 §8 / wyckoff-epic-context-refactor-handoff H-M1~M4）：
      - 回溯窗口 5 → WYCKOFF_BC_SCAN_BARS=90（对齐 SC 冷启动日 90），从新到旧找**最近一次** BC
      - 滞涨阈值 1.0 → 5.0（容忍 A 股单日波动）
      - 新增「显著长上影」OR 分支（upper_shadow / price_range ≥ 0.25，06-25 +6.8% 型）
    触发 = 量比≥1.5 ∧ 高位 pos≥0.65 ∧（滞涨 ∨ 显著长上影 ∨ 收阴）。

    Returns:
        dict with keys: bc_signal (bool), bc_reason (str), bc_price (float),
        bc_bar_idx (int|None，最近一次 BC 位置), bc_close (float|None, BC 棒收盘),
        bc_avg_vol (float|None, BC 前均量) —— 供 ARE 复用（H-M5）
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"bc_signal": False, "bc_reason": "数据不足", "bc_price": 0.0}

    # H-M1: 回溯扫描最近 WYCKOFF_BC_SCAN_BARS 根，任一满足 BC 条件即触发
    scan_start = max(1, len(bars) - WYCKOFF_BC_SCAN_BARS)
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

        # H-M2/M4: 滞涨（<5.0%）∨ 显著长上影（≥0.25）∨ 收阴
        is_stagnant = change_pct < WYCKOFF_BC_CHANGE_THRESHOLD
        strong_upper_shadow = upper_shadow_ratio >= WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO
        has_upper_shadow = upper_shadow_ratio > WYCKOFF_BC_UPPER_SHADOW_RATIO

        if not (is_stagnant or strong_upper_shadow or (cur_close < cur_open)):
            continue

        parts = []
        parts.append(f"量比 {vol_ratio:.1f}")
        pos = _price_pos_pct(bars, scan_idx)
        if pos is not None:
            parts.append(f"高位区{pos*100:.0f}%")
        if is_stagnant:
            parts.append(f"涨幅仅 {change_pct:.1f}%")
        if strong_upper_shadow:
            parts.append("显著长上影")
        elif has_upper_shadow:
            parts.append("上影线明显")
        if cur_close < cur_open:
            parts.append("收阴")

        return {
            "bc_signal": True,
            "bc_reason": "天量滞涨，购买高潮信号：" + "，".join(parts),
            "bc_price": round(cur_high, 2),
            "bc_bar_idx": scan_idx,
            "bc_close": cur_close,
            "bc_avg_vol": avg_volume,
        }

    return {"bc_signal": False, "bc_reason": "未检测到购买高潮", "bc_price": 0.0}


def _phase_a_breakdown(
    bars: list[dict],
    sc_bar_idx: int,
    sc_low: float,
    *,
    end_idx: int | None = None,
) -> dict | None:
    """有效破 SC low 未收回 → Phase A failed（与广义 ST 刺穿语义一致）。"""
    if sc_low is None:
        return None
    try:
        low_anchor = float(sc_low)
    except (TypeError, ValueError):
        return None
    if low_anchor <= 0:
        return None

    stop = len(bars) if end_idx is None else min(len(bars), int(end_idx))
    floor = low_anchor * (1.0 - WYCKOFF_ST_SC_MAX_PIERCE)
    for i in range(int(sc_bar_idx) + 1, stop):
        bar = bars[i]
        t_low = to_float(bar.get("low"))
        t_close = to_float(bar.get("close"))
        # 法源 structure-anchor §3.1 / known-gaps G-K1：须 close；缺失则跳过该棒
        if t_low is None or t_close is None:
            continue
        if t_low < floor and t_close < low_anchor:
            return {
                "phase_a_failed": True,
                "fail_bar_idx": i,
                "fail_reason": "SC 后有效跌破未收回（Phase A 失败）",
            }
    return None


def _phase_a_from_ctx(tr_ctx: dict | None) -> dict:
    if not isinstance(tr_ctx, dict):
        return {}
    pa = tr_ctx.get("phase_a_range")
    if isinstance(pa, dict):
        return pa
    return tr_ctx


def _pinned_sc_bar_idx_from_ctx(
    bars: list[dict],
    tr_ctx: dict | None,
    *,
    include_failed: bool = False,
) -> int | None:
    pa = _phase_a_from_ctx(tr_ctx)
    status = str(pa.get("status") or pa.get("phase_a_status") or "").strip()
    if status not in {"forming", "established"}:
        return None
    try:
        sc_idx = int(pa.get("sc_bar_idx"))
    except (TypeError, ValueError):
        return None
    if sc_idx < 1 or sc_idx >= len(bars):
        return None

    sc_low = pa.get("sc_low")
    if sc_low is None:
        bar_low = to_float(bars[sc_idx].get("low"))
        sc_low = bar_low
    if sc_low is None:
        return None
    if not include_failed and _phase_a_breakdown(bars, sc_idx, float(sc_low)) is not None:
        return None
    return sc_idx


def _fail_bar_cutoff_from_ctx(tr_ctx: dict | None) -> int | None:
    """从 tr_ctx / phase_a_range 读取 fail_bar_idx（破位棒），供冷启动排除旧锚。"""
    if not isinstance(tr_ctx, dict):
        return None
    pa = _phase_a_from_ctx(tr_ctx)
    for src in (pa, tr_ctx):
        if not isinstance(src, dict):
            continue
        v = src.get("fail_bar_idx")
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _find_sc_anchor(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
    include_failed: bool = False,
) -> dict | None:
    """找最近一次 SC（SSOT）。

    Path A：调用方持有未失效 Phase A 锚时，搜索宇宙钉住
    ``[sc_bar_idx, 今]``，可越过冷启动 CAP。
    Path B：无 alive 锚时，日线仅最近 90 根、周线仅最近 39 根冷启动。

    ``include_failed=False``（Path B / AR 等）且 ctx 带 ``fail_bar_idx`` 时，
    **跳过** ``scan_idx <= fail_bar_idx`` 的候选（S-A5 / range-diff W-DIFF-2），
    避免已破 SC 被冷启动再次钉成健康 forming/established。
    ``include_failed=True``（汇报已失败 SC / 广义 ST）**不**套此排除。

    ``sc_low`` 必须是 SC 棒最低价（bar.low），禁止用 close / 局部偏高点当谷底。

    Returns:
        dict | None: sc_bar_idx, sc_low, sc_close, sc_avg_vol, vol_ratio, change_pct, pos
    """
    p = _sc_detector_params(timeframe, is_index=is_index)
    support_lb = int(p["support_lookback"])
    anchor_bars = int(p["anchor_bars"])
    vol_th = float(p["vol_ratio_threshold"])
    change_max = float(p["change_pct_max"])
    pos_ref = str(p["pos_ref"])

    # I-M1（统一结构上下文）：tr_ctx.sc_anchor 为完整序列算好的 SC 锚 → 直接返回，
    # 不重算、不冷启动。簇确认（_detect_event_cluster）与后续阶段机以此保证
    # 簇的重置锚与主流程 sc.sc_bar_idx 同源；无该字段走下方原逻辑（I-M2 向后兼容）。
    if isinstance(tr_ctx, dict):
        _ctx_anchor = tr_ctx.get("sc_anchor")
        if isinstance(_ctx_anchor, dict):
            return _ctx_anchor

    if len(bars) < support_lb + 1:
        return None
    pinned_idx = _pinned_sc_bar_idx_from_ctx(bars, tr_ctx, include_failed=include_failed)
    if pinned_idx is not None:
        scan_start = max(1, pinned_idx)
        search_mode = "pinned"
    else:
        scan_start = max(1, len(bars) - anchor_bars)
        search_mode = "cold_start"
    # W-DIFF-2 / S-A5：冷启动排除 fail_bar 及更早；include_failed 不排除
    fail_cutoff = None if include_failed else _fail_bar_cutoff_from_ctx(tr_ctx)
    for scan_idx in range(len(bars) - 1, scan_start - 1, -1):
        if fail_cutoff is not None and scan_idx <= fail_cutoff:
            continue
        current = bars[scan_idx]
        recent = bars[max(0, scan_idx - support_lb):scan_idx]

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
        if vol_ratio < vol_th:
            continue

        # 低位过滤可用 close/high 作 pos_ref；谷底价本身始终取棒最低价
        # SC 位置上限用 WYCKOFF_SC_MAX_POS_PCT（试验默认 0.50；旧约 1-BC_MIN=0.35）
        pos = _price_pos_pct(bars, scan_idx, lookback=support_lb, ref=pos_ref)
        if pos is None or pos > float(WYCKOFF_SC_MAX_POS_PCT):
            continue

        if cur_close >= cur_open:
            continue
        prev_close = to_float(bars[scan_idx - 1].get("close")) if scan_idx >= 1 else cur_open
        change_pct = (cur_close - prev_close) / max(prev_close, 0.01) * 100
        if change_pct > change_max:
            continue

        failed = _phase_a_breakdown(bars, scan_idx, float(cur_low))
        if failed is not None and not include_failed:
            continue

        out = {
            "sc_bar_idx": scan_idx,
            # SC low SSOT：棒最低价（非 close / 非局部偏高点）
            "sc_low": round(float(cur_low), 2),
            "sc_close": cur_close,
            "sc_avg_vol": avg_volume,
            "vol_ratio": vol_ratio,
            "change_pct": change_pct,
            "pos": pos,
            "cur_high": cur_high,
            "cur_open": cur_open,
            "anchor_bars": anchor_bars,
            "search_mode": search_mode,
        }
        if failed is not None:
            out.update(failed)
        return {
            **out,
        }
    return None


def _sc_empty() -> dict:
    return {
        "sc_signal": False,
        "sc_reason": "未检测到卖力高潮",
        "sc_price": 0.0,
        "sc_low": None,
        "sc_bar_idx": None,
    }


def _detect_selling_climax(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> dict:
    """Detect Selling Climax (SC) — 天量宽幅下跌，低位抛售宣泄。

    对称于 BC（Buying Climax），但方向相反：
      - 巨量（量比 >= BC 阈值）
      - 低位（在近窗价格区间下沿）
      - 阴线（close < open）且跌幅显著
      - 下影线比例低（实体占比大）

    Returns:
        dict with keys: sc_signal (bool), sc_reason (str), sc_price (float),
        sc_low (float|None), sc_bar_idx (int|None)
        sc_low / sc_price 均为 SC 棒最低价（SSOT，非 close）
    """
    p = _sc_detector_params(timeframe, is_index=is_index)
    if len(bars) < int(p["support_lookback"]) + 1:
        return {**_sc_empty(), "sc_reason": "数据不足"}

    anchor = _find_sc_anchor(
        bars,
        tr_ctx=tr_ctx,
        timeframe=timeframe,
        is_index=is_index,
        include_failed=True,
    )
    if anchor is None:
        return _sc_empty()

    price_range = (anchor["cur_high"] - anchor["sc_low"]) if anchor["cur_high"] is not None else 1.0
    if price_range <= 0:
        price_range = 1.0
    real_body_bottom = min(anchor["cur_open"], anchor["sc_close"])
    lower_shadow = real_body_bottom - anchor["sc_low"]
    lower_shadow_ratio = lower_shadow / max(price_range, 0.01)

    parts = [f"量比 {anchor['vol_ratio']:.1f}", f"跌幅 {anchor['change_pct']:.1f}%"]
    if lower_shadow_ratio < 0.3:
        parts.append("下影线短（实体大）")
    else:
        parts.append("带下影线")
    parts.append(f"低位区{anchor['pos']*100:.0f}%")

    # SC low SSOT：再从棒读取 low，避免任何路径用 close 冒充谷底
    sc_bar_idx = int(anchor["sc_bar_idx"])
    bar_low = to_float(bars[sc_bar_idx].get("low"))
    sc_low = round(float(bar_low), 2) if bar_low is not None else anchor["sc_low"]
    return {
        "sc_signal": True,
        "sc_reason": "天量宽幅下跌，卖力高潮：" + "，".join(parts),
        "sc_price": sc_low,
        "sc_low": sc_low,
        "sc_bar_idx": sc_bar_idx,
        "anchor_bars": anchor.get("anchor_bars"),
        "search_mode": anchor.get("search_mode"),
        "phase_a_failed": bool(anchor.get("phase_a_failed")),
        "fail_bar_idx": anchor.get("fail_bar_idx"),
        "fail_reason": anchor.get("fail_reason"),
    }


def _ar_empty(reason: str = "未检测到 SC，无法触发 AR") -> dict:
    return {
        "ar_signal": False,
        "ar_reason": reason,
        "ar_price": None,
        "ar_high": None,
        "ar_bar_idx": None,
        "ar_volume_soft": False,
        "sc_low": None,
        "sc_bar_idx": None,
    }

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

    # 支撑位：有 TR 下沿则始终用它（原典 SOW = 跌破 TR 下沿）。
    # 勿绑 in_tr：收盘已破下沿时 in_tr=False，仍须按 tr_lower 判定正式 SOW。
    if tr_ctx is not None and tr_ctx.get("tr_lower") is not None:
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

    # TR 语境：有正式 tr_lower 即视为区间事件容器（不强制当日 in_tr）
    has_tr_lower = bool(tr_ctx and tr_ctx.get("tr_lower") is not None)
    in_tr = bool(tr_ctx.get("in_tr")) if tr_ctx else False
    if not has_tr_lower and not in_tr and not _is_trading_range(bars):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "非交易区间（振幅过大）"}

    low_values = [to_float(b.get("low")) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    current_low = to_float(current.get("low"))
    current_close = to_float(current.get("close"))
    current_volume = to_float(current.get("volume"))

    # 支撑位：有 TR 下沿则用它（原典 Spring = 跌破 TR 下沿后收回）
    if has_tr_lower:
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
    # 取 recent 内首次跌破起算；当前棒也计入窗口（昨破今收是常见 Spring）
    breach_bar_i = None
    for j in range(len(recent)):
        b_low = to_float(recent[j].get("low"))
        if b_low is not None and b_low < support:
            breach_bar_i = j
            break
    if breach_bar_i is not None:
        recharged = False
        for k in range(breach_bar_i + 1, min(breach_bar_i + 3, len(recent))):
            if to_float(recent[k].get("close")) is not None and to_float(recent[k].get("close")) >= support:
                recharged = True
                break
        bars_after_breach = (len(recent) - breach_bar_i)
        if (
            not recharged
            and bars_after_breach <= 2
            and current_close is not None
            and current_close >= support
        ):
            recharged = True
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
    baseline_vol = (
        tr_ctx.get("tr_baseline_volume")
        if (has_tr_lower and tr_ctx and tr_ctx.get("tr_baseline_volume"))
        else avg_volume
    )
    vol_ratio = (current_volume / baseline_vol) if baseline_vol and baseline_vol > 0 else 1.0
    depth_pct = ((support - current_low) / support * 100.0) if support > 0 else 0.0
    recent_highs = [to_float(b.get("high")) for b in recent]
    valid_recent_highs = [v for v in recent_highs if v is not None]
    local_high = max(valid_recent_highs) if valid_recent_highs else support
    tr_upper = tr_ctx.get("tr_upper") if (has_tr_lower and tr_ctx) else None
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
    """Detect Upthrust — 对称于 Spring：突破阻力后快速回落。

    与 Spring 对齐的闸门：一字板过滤、无 TR 时交易区间约束、突破后 1–2 根内回落。
    """
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    # 与 Spring 对称：一字板无效换手
    if _is_frozen_board(current):
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "一字板无效换手"}
    if len(recent) > 0 and _is_frozen_board(recent[-1]):
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "前日一字板无效换手"}

    high_values = [to_float(b.get("high")) for b in recent]
    valid_highs = [v for v in high_values if v is not None]
    current_high = to_float(current.get("high"))
    current_close = to_float(current.get("close"))

    # 阻力位：有 TR 上沿则始终用它（原典 UT = 突破 TR 上沿后回落；勿绑 in_tr）
    has_tr_upper = bool(tr_ctx and tr_ctx.get("tr_upper") is not None)
    in_tr = bool(tr_ctx.get("in_tr")) if tr_ctx else False
    if not has_tr_upper and not in_tr and not _is_trading_range(bars):
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "非交易区间（振幅过大）"}

    if has_tr_upper:
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

    # 与 Spring「2 根内收回」对称：取 recent 内首次突破起算 1–2 根内回落；
    # 当前棒也计入窗口（昨突今落是常见 UT；不可改成「最近突破」否则慢回落会被误放行）
    breakout_bar_i = None
    for j in range(len(recent)):
        b_high = to_float(recent[j].get("high"))
        if b_high is not None and b_high > breakout_level:
            breakout_bar_i = j
            break
    if breakout_bar_i is not None:
        fell_back = False
        for k in range(breakout_bar_i + 1, min(breakout_bar_i + 3, len(recent))):
            k_close = to_float(recent[k].get("close"))
            if k_close is not None and k_close < reclaim_level:
                fell_back = True
                break
        bars_after_breakout = (len(recent) - breakout_bar_i)
        if (
            not fell_back
            and bars_after_breakout <= 2
            and current_close is not None
            and current_close < reclaim_level
        ):
            fell_back = True
        if not fell_back:
            return {
                "upthrust_signal": False,
                "upthrust_price": 0.0,
                "upthrust_reason": "突破阻力后未在2根内回落，非Upthrust",
            }

    # P0-2: UT 需放量确认（派发需要成交量配合）
    current_volume = to_float(current.get("volume"))
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    if current_volume is not None and avg_volume > 0 and current_volume < avg_volume * WYCKOFF_UT_VOL_RATIO:
        return {"upthrust_signal": False, "upthrust_price": 0.0,
                "upthrust_reason": "上冲未放量，非主力派发", "upthrust_strength": None}

    # ── P0-4 真假分级：突破深度 + 量能比(vs TR基线量) + 跌回位置(相对TR中轴) ──
    baseline_vol = (
        tr_ctx.get("tr_baseline_volume")
        if (has_tr_upper and tr_ctx and tr_ctx.get("tr_baseline_volume"))
        else avg_volume
    )
    vol_ratio = (current_volume / baseline_vol) if baseline_vol and baseline_vol > 0 else 1.0
    depth_pct = ((current_high - resistance) / resistance * 100.0) if resistance > 0 else 0.0
    # TR 中轴：有正式下沿时用 (上沿+下沿)/2
    tr_lower = tr_ctx.get("tr_lower") if (has_tr_upper and tr_ctx) else None
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

def _ar_volume_flags() -> tuple[bool, bool, float]:
    """运行时读 AR 量能 flag（便于测例 monkeypatch config）。"""
    try:
        from trader_shared import config as cfg

        prefer = bool(getattr(cfg, "WYCKOFF_AR_PREFER_WEAK_VS_SC", WYCKOFF_AR_PREFER_WEAK_VS_SC))
        require = bool(getattr(cfg, "WYCKOFF_AR_REQUIRE_WEAK_VS_SC", WYCKOFF_AR_REQUIRE_WEAK_VS_SC))
        ratio = float(getattr(cfg, "WYCKOFF_AR_WEAK_VS_SC_RATIO", WYCKOFF_AR_WEAK_VS_SC_RATIO))
        return prefer, require, ratio
    except Exception:
        return (
            bool(WYCKOFF_AR_PREFER_WEAK_VS_SC),
            bool(WYCKOFF_AR_REQUIRE_WEAK_VS_SC),
            float(WYCKOFF_AR_WEAK_VS_SC_RATIO),
        )


def _detect_ar(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> dict:
    """Detect Automatic Rally (AR) — SC 之后抛售枯竭的快速反弹（原典）。

    只绑 SC。与 `_detect_selling_climax` 共用 `_find_sc_anchor`。
    边界价用 ar_high（反弹棒最高价）；ar_price 保留 close 供旧消费。

    P2-C 量能：相对 SC 棒量 prefer 弱量（``WYCKOFF_AR_PREFER_WEAK_VS_SC``）；
    ``ar_volume_soft=True`` = 量能偏强/非原典弱量（结构仍可亮）；
    ``WYCKOFF_AR_REQUIRE_WEAK_VS_SC`` 时放量 AR 硬否决（默认关）。
    """
    if len(bars) < WYCKOFF_MIN_BARS + 3:
        return {**_ar_empty(), "ar_reason": "数据不足"}

    anchor = _find_sc_anchor(bars, tr_ctx=tr_ctx, timeframe=timeframe, is_index=is_index)
    if anchor is None:
        # F-M1/F-M2：SC 失效链——常规锚（include_failed=False）缺失时，
        # 再探测「存在但失效」的 SC（与 _detect_selling_climax 的 include_failed=True
        # 口径一致），输出失效态文案而非「未检测到 SC」；禁止软确认（ar_signal 恒 False）。
        failed_anchor = _find_sc_anchor(
            bars,
            tr_ctx=tr_ctx,
            timeframe=timeframe,
            is_index=is_index,
            include_failed=True,
        )
        if (
            failed_anchor is not None
            and failed_anchor.get("phase_a_failed")
            and failed_anchor.get("fail_reason")
        ):
            # F-M5：失效态仍透出 SC 位置（SC low SSOT：棒最低价）
            f_sc_bar_idx = int(failed_anchor["sc_bar_idx"])
            f_bar_low = to_float(bars[f_sc_bar_idx].get("low"))
            f_sc_low = (
                round(float(f_bar_low), 2)
                if f_bar_low is not None
                else failed_anchor["sc_low"]
            )
            return {
                **_ar_empty("SC 已失效（Phase A 失败），链终止，须重新寻底"),
                "sc_low": f_sc_low,
                "sc_bar_idx": f_sc_bar_idx,
            }
        return _ar_empty()

    sc_bar_idx = anchor["sc_bar_idx"]
    sc_close = anchor["sc_close"]
    # SC low SSOT：与 _find_sc_anchor / SC 检测器同一谷底（棒最低价）
    bar_low = to_float(bars[sc_bar_idx].get("low"))
    sc_low = round(float(bar_low), 2) if bar_low is not None else anchor["sc_low"]
    sc_vol = to_float(bars[sc_bar_idx].get("volume")) or float(anchor.get("sc_avg_vol") or 0)

    _prefer_weak, require_weak, weak_ratio = _ar_volume_flags()
    del _prefer_weak  # 兼容开关；选棒始终取首段结构 AR

    # AR 搜索上沿：WYCKOFF_AR_MAX_BARS（默认=climax 锚点）；周线半幅缩放
    ar_limit = int(WYCKOFF_AR_MAX_BARS)
    if str(timeframe or "").lower() == "weekly":
        ar_limit = max(2, int(ar_limit * 0.5))
    rally_max = min(max(2, ar_limit), len(bars) - sc_bar_idx - 1)

    candidates: list[dict] = []
    for i in range(1, rally_max + 1):
        rally_bar = bars[sc_bar_idx + i]
        r_close = to_float(rally_bar.get("close"))
        r_high = to_float(rally_bar.get("high"))
        r_volume = to_float(rally_bar.get("volume"))
        if r_close is None or r_high is None or r_volume is None:
            continue
        if r_close <= sc_close * 1.02:
            continue

        weak_vs_sc = bool(sc_vol > 0 and r_volume <= sc_vol * weak_ratio)
        if require_weak and not weak_vs_sc:
            continue
        pct = (r_close / sc_close - 1) * 100
        candidates.append(
            {
                "i": i,
                "r_close": r_close,
                "r_high": r_high,
                "r_volume": r_volume,
                "weak_vs_sc": weak_vs_sc,
                "pct": pct,
            }
        )

    if not candidates:
        reason = "SC 后未检测到有效反弹"
        if require_weak:
            # 区分：结构有反弹但全被量能硬否决
            for i in range(1, rally_max + 1):
                rally_bar = bars[sc_bar_idx + i]
                r_close = to_float(rally_bar.get("close"))
                r_volume = to_float(rally_bar.get("volume"))
                if r_close is None or r_volume is None:
                    continue
                if r_close > sc_close * 1.02 and sc_vol > 0 and r_volume > sc_vol * weak_ratio:
                    reason = "AR 放量相对 SC，REQUIRE 弱量否决"
                    break
        return {
            **_ar_empty(reason),
            "sc_low": sc_low,
            "sc_bar_idx": sc_bar_idx,
        }

    # Phase A 上沿钉「SC 后首段自动反弹」：始终取最早结构候选。
    # 禁止因弱量 prefer 跳到更晚棒抬高 ar_high；弱/强只影响 soft / REQUIRE。
    chosen = candidates[0]
    soft = not bool(chosen["weak_vs_sc"])
    if soft:
        vol_note = "量能偏强/非原典弱量(soft)"
    else:
        vol_note = "弱于SC量"
    return {
        "ar_signal": True,
        "ar_reason": f"SC 后自动反弹，{vol_note} +{chosen['pct']:.1f}%",
        "ar_price": round(chosen["r_close"], 2),
        "ar_high": round(chosen["r_high"], 2),
        "ar_bar_idx": sc_bar_idx + int(chosen["i"]),
        "ar_volume_soft": soft,
        "sc_low": sc_low,
        "sc_bar_idx": sc_bar_idx,
    }


def _st_sc_empty(reason: str = "未检测到 SC 锚点") -> dict:
    return {
        "secondary_test_sc_signal": False,
        "secondary_test_sc_reason": reason,
        "st_sc_low": None,
        "secondary_test_sc_low": None,
        "secondary_test_sc_price": None,
        "secondary_test_sc_bar_idx": None,
    }


def _st_sc_max_bars_for_tf(timeframe: str = "daily") -> int:
    """广义 ST 扫描根数：日线 = config；周线半幅（``wyckoff-weekly-scan-windows-handoff`` §1.2）。

    默认 22 → 周线 ``max(8, ceil(22/2))=11``，避免周线 ST 窗≈5 个月过松。
    """
    n = int(WYCKOFF_ST_SC_MAX_BARS)
    if str(timeframe or "").lower() == "weekly":
        return max(8, (n + 1) // 2)
    return n


def _detect_secondary_test_sc(
    bars: list[dict],
    tr_ctx: dict | None = None,
    phase_a_range: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> dict:
    """广义 Secondary Test — SC 后二次回测 SC 区（非 Spring Test / st_*）。

    前提：已有 SC 锚点；SC/AR 后若干根内 **low 进入 SC 区**（proximity / 允许刺穿+收回）、
    量与波幅较 SC 明显缩小、未有效破新低。字段独立，不覆盖 spring_test_* / st_*。

    测试窗（phase-a §4.4.1）：有 ``ar_bar_idx`` 则从 AR+3 起扫，无 AR 从 SC+3；
    破位扫描仍从 SC+1。回测锚 ``sc_low`` 以 ``_find_sc_anchor`` 为准（SSOT），
    不用外部偏高种子价。

    禁止软确认（handoff §1.3）：价格一直站在 sc_low 上方、从未回测 SC 区 →
    不得返回 ``secondary_test_sc_signal=True``。

    有效跌破（handoff §1.3）：超允许刺穿且收盘不收回 → **Phase A 失败**，
    整段不得再认后续 ST（禁止 ``continue`` 跳过破位棒后另找假 ST）。
    """
    p = _sc_detector_params(timeframe, is_index=is_index)
    if len(bars) < int(p["support_lookback"]) + 2:
        return _st_sc_empty("数据不足")

    anchor = _find_sc_anchor(
        bars,
        tr_ctx=tr_ctx,
        timeframe=timeframe,
        is_index=is_index,
        include_failed=True,
    )
    if anchor is None:
        return _st_sc_empty()

    sc_bar_idx = int(anchor["sc_bar_idx"])
    # SC low SSOT：回测锚 = SC 棒最低价（与 _find_sc_anchor 同源；禁止 close / 外部偏高种子）
    bar_low = to_float(bars[sc_bar_idx].get("low"))
    sc_low = round(float(bar_low), 2) if bar_low is not None else anchor.get("sc_low")
    sc_vol = to_float(bars[sc_bar_idx].get("volume")) or anchor.get("sc_avg_vol") or 0
    sc_high = to_float(bars[sc_bar_idx].get("high"))
    if sc_vol <= 0 or sc_low is None:
        return _st_sc_empty("SC 量能数据异常")
    sc_spread = None
    if sc_high is not None and sc_high > sc_low:
        sc_spread = float(sc_high) - float(sc_low)

    failed = _phase_a_breakdown(bars, sc_bar_idx, float(sc_low))
    if failed is not None:
        return {
            **_st_sc_empty(str(failed.get("fail_reason") or "SC 后有效跌破未收回（Phase A 失败）")),
            "phase_a_failed": True,
            "fail_bar_idx": failed.get("fail_bar_idx"),
            "fail_reason": failed.get("fail_reason"),
        }

    # ST 候选窗：phase-a §4.4.1「SC/AR 后 3…LOOKBACK」；有 AR 以 AR 为锚，否则 SC
    # 破位扫描仍从 SC+1（整段 Phase A，含 AR 前跌破）
    st_anchor = sc_bar_idx
    pa = phase_a_range if isinstance(phase_a_range, dict) else None
    if pa is not None and pa.get("ar_bar_idx") is not None:
        try:
            ar_i = int(pa["ar_bar_idx"])
            if ar_i >= sc_bar_idx:
                st_anchor = ar_i
        except (TypeError, ValueError):
            pass
    st_scan_start = int(st_anchor) + 3

    st_max = _st_sc_max_bars_for_tf(timeframe)
    st_scan_end = min(len(bars), st_scan_start + st_max)
    # 破位扫描须覆盖 SC→AR 前 + ST 窗，避免漏掉 AR 前有效跌破
    fail_scan_end = min(
        len(bars),
        max(st_scan_end, sc_bar_idx + 1 + st_max),
    )
    if fail_scan_end <= sc_bar_idx + 1:
        return _st_sc_empty("SC 后无足够 K 线")

    zone_upper = sc_low * (1.0 + WYCKOFF_ST_SC_PROXIMITY)
    spread_cap = (
        sc_spread * float(WYCKOFF_ST_SC_SPREAD_RATIO)
        if sc_spread is not None and sc_spread > 0
        else None
    )

    best_low: float | None = None
    best_vol: float | None = None
    best_close: float | None = None
    best_idx: int | None = None
    saw_soft_above = False  # 曾有棒站在 SC 区上方（软确认候选，一律否决）
    saw_wide_spread = False
    for i in range(sc_bar_idx + 1, fail_scan_end):
        bar = bars[i]
        t_low = to_float(bar.get("low"))
        t_high = to_float(bar.get("high"))
        t_close = to_float(bar.get("close"))
        t_vol = to_float(bar.get("volume"))
        if t_low is None or t_vol is None:
            continue

        # AR 前的棒只做破位扫描，不认 ST
        if i < st_scan_start or i >= st_scan_end:
            continue

        # 禁止软确认：low 必须进入 SC 区；一直站在上方不算 ST
        if t_low > zone_upper:
            saw_soft_above = True
            continue

        if t_vol >= sc_vol * WYCKOFF_ST_SC_VOL_RATIO:
            continue

        # L2：ST 波幅须明显弱于 SC；过宽不算 ST
        if spread_cap is not None and t_high is not None:
            t_spread = float(t_high) - float(t_low)
            if t_spread > spread_cap:
                saw_wide_spread = True
                continue

        if best_low is None or t_low < best_low:
            best_low = t_low
            best_vol = t_vol
            best_close = t_close
            best_idx = i

    if best_low is None:
        if saw_wide_spread:
            return _st_sc_empty(
                f"SC 后回测波幅未弱于 SC（须≤{float(WYCKOFF_ST_SC_SPREAD_RATIO):.0%} SC 波幅）"
            )
        if saw_soft_above:
            return _st_sc_empty("SC 后价格未回测 SC 区（禁止软确认）")
        return _st_sc_empty("SC 后未检测到有效二次测试（须回测 SC 区且量/波幅弱于 SC）")

    vol_pct = (best_vol / sc_vol * 100) if best_vol and sc_vol else 0
    return {
        "secondary_test_sc_signal": True,
        "secondary_test_sc_reason": f"SC 区二次测试，量 {vol_pct:.0f}% SC",
        "st_sc_low": round(best_low, 2),
        "secondary_test_sc_low": round(best_low, 2),
        "secondary_test_sc_price": round(best_close, 2) if best_close is not None else round(best_low, 2),
        "secondary_test_sc_bar_idx": best_idx,
    }


def _detect_are(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Automatic Reaction (ARE) — BC 之后买力枯竭的快速回落（对称 AR）。

    触发条件:
      1. 检测到 BC（购买高潮）——H-M5：复用 ``_detect_buying_climax``（同常量同分支，
         消漂移；ARE 的 BC 锚 = 最近一次 BC 触发位置，窗口跟随 WYCKOFF_BC_SCAN_BARS）
      2. BC 后 1-3 根内，存在至少 1 根满足:
         - close < bc_close * 0.98（下跌 >= 2%）
         - volume > bc 前均量 * 1.2（放量）

    注：回落棒本身也可能像 BC（高位放量阴线）。若最近一次 BC 恰在末根（无回落空间），
    返回「BC 后未检测到有效回落」（与原「从近到远尝试 BC 候选」的兜底语义对齐）。
    """
    if len(bars) < WYCKOFF_MIN_BARS + 3:
        return {"are_signal": False, "are_reason": "数据不足", "are_price": None}

    bc = _detect_buying_climax(bars, tr_ctx=tr_ctx)
    if not bc.get("bc_signal"):
        return {"are_signal": False, "are_reason": "未检测到 BC，无法触发 ARE", "are_price": None}

    try:
        bc_idx = int(bc.get("bc_bar_idx") or -1)
    except (TypeError, ValueError):
        bc_idx = -1
    bc_close = bc.get("bc_close")
    avg_volume = bc.get("bc_avg_vol")
    if bc_idx < 0 or bc_idx >= len(bars) - 1:
        return {"are_signal": False, "are_reason": "BC 后未检测到有效回落", "are_price": None}
    if bc_close is None or avg_volume is None or bc_close <= 0:
        return {"are_signal": False, "are_reason": "BC 数据异常，无法触发 ARE", "are_price": None}

    react_max = min(max(3, WYCKOFF_CLIMAX_ANCHOR_BARS // 2), len(bars) - bc_idx - 1)
    for i in range(1, react_max + 1):
        react_bar = bars[bc_idx + i]
        r_close = to_float(react_bar.get("close"))
        r_volume = to_float(react_bar.get("volume"))
        if r_close is None or r_volume is None:
            continue
        if r_close >= bc_close * 0.98:
            continue
        vol_ok = avg_volume > 0 and r_volume > avg_volume * 1.2
        pct = (r_close / bc_close - 1) * 100
        vol_note = "放量" if vol_ok else "量能偏弱(soft)"
        return {
            "are_signal": True,
            "are_reason": f"BC 后自动回落，{vol_note} {pct:.1f}%",
            "are_price": round(r_close, 2),
            "are_volume_soft": not vol_ok,
        }

    return {"are_signal": False, "are_reason": "BC 后未检测到有效回落", "are_price": None}

def _sos_empty(reason: str) -> dict:
    return {"sos_signal": False, "sos_reason": reason, "sos_price": None, "sos_kind": None}


def _sos_baseline_avg_vol(
    bars: list[dict],
    tr_ctx: dict | None,
    *,
    robust: bool = False,
) -> float:
    """基线量：有 TR 基线量则用它（勿绑 in_tr），否则前10根。

    robust=True（thrust）：无 TR 基线时用**中位数**，避免 AR/天量单日拉高均值导致
    真突破量比被压死（南网 08-03 vs 07-20 AR）。
    """
    recent = bars[-(WYCKOFF_DIVERGENCE_BARS + WYCKOFF_SPRING_SUPPORT_LOOKBACK):-1]
    if tr_ctx is not None and tr_ctx.get("tr_baseline_volume"):
        try:
            bv = float(tr_ctx["tr_baseline_volume"])
            if bv > 0:
                return bv
        except (TypeError, ValueError):
            pass
    baseline_start = max(0, len(recent) - 10)
    baseline = recent[baseline_start:]
    vols = [to_float(b.get("volume")) or 0 for b in baseline]
    vols = [v for v in vols if v > 0]
    if not vols:
        return 0.0
    if robust:
        vs = sorted(vols)
        mid = len(vs) // 2
        if len(vs) % 2:
            return float(vs[mid])
        return float(vs[mid - 1] + vs[mid]) / 2.0
    return sum(vols) / len(vols)


def _try_sos_climb(bars: list[dict], baseline_avg_vol: float) -> dict:
    """连续爬坡型 SOS（近 5 根 ≥4 阳）。"""
    current_window = bars[-WYCKOFF_DIVERGENCE_BARS:]
    closes: list[float] = []
    opens: list[float] = []
    volumes: list[float] = []
    for b in current_window:
        o = to_float(b.get("open"))
        c = to_float(b.get("close"))
        v = to_float(b.get("volume"))
        if o is None or c is None or v is None:
            return _sos_empty("数据异常")
        closes.append(c)
        opens.append(o)
        volumes.append(v)

    # P1-2: 放宽为 ≥4/5 阳线（A 股连续 5 阳极罕见，4/5 + 强涨幅更实际）
    bullish_count = sum(1 for c, o in zip(closes, opens) if c > o)
    if bullish_count < WYCKOFF_DIVERGENCE_BARS - 1:
        return _sos_empty(
            f"仅 {bullish_count}/{WYCKOFF_DIVERGENCE_BARS} 阳线，不足 {WYCKOFF_DIVERGENCE_BARS - 1} 根"
        )

    if closes[-1] < opens[0]:
        return _sos_empty("未总体抬高")

    sos_avg_vol = sum(volumes) / len(current_window)
    if sos_avg_vol < baseline_avg_vol * 1.2:
        return _sos_empty("量能不足")

    gain = (closes[-1] - opens[0]) / max(opens[0], 0.01)
    if gain < 0.02:
        return _sos_empty(f"涨幅 {gain*100:.1f}% 不足 2%")

    return {
        "sos_signal": True,
        "sos_reason": f"强势突破，{bullish_count}/5 阳线累计涨{gain*100:.1f}%，量能放大",
        "sos_price": round(closes[-1], 2),
        "sos_kind": "climb",
    }


def _sos_thrust_creek(tr_ctx: dict | None) -> float | None:
    """Thrust 突破锚（溪/箱顶）。

    优先 phase_a ``ar_high``（吸筹离开 AR 钉的上沿），其次 ``tr_upper``。
    避免：突破后分位 TR 上沿被抬高，回扫历史 tip 时 close>tr_upper 反而不成立。
    """
    if not isinstance(tr_ctx, dict):
        return None
    candidates: list[float] = []
    pa = tr_ctx.get("phase_a_range")
    if isinstance(pa, dict) and pa.get("ar_high") is not None:
        try:
            candidates.append(float(pa["ar_high"]))
        except (TypeError, ValueError):
            pass
    for k in ("ar_high", "tr_upper"):
        if tr_ctx.get(k) is None:
            continue
        try:
            candidates.append(float(tr_ctx[k]))
        except (TypeError, ValueError):
            continue
    if not candidates:
        return None
    # 取有效正数中的「结构上沿」：优先 AR（列表中先出现），否则 tr_upper
    for c in candidates:
        if c > 0:
            return c
    return None


def _sos_thrust_baseline_vol(
    bars: list[dict],
    tr_ctx: dict | None,
    creek: float,
    fallback: float,
) -> float:
    """Thrust 量比分母：TR 内、tip 之前、收盘仍 ≤ 溪 的 bar 中位数。

    南网实证：整段 tr_baseline 含突破日 → 5.75M，08-03 量比仅 1.47；
    溪内中位 ≈ 横盘均量，才能还原 handoff「相对 TR 内均量 ≥1.8」。
    """
    vols: list[float] = []
    start = 0
    if isinstance(tr_ctx, dict) and tr_ctx.get("tr_start") is not None:
        try:
            start = max(0, int(tr_ctx["tr_start"]))
        except (TypeError, ValueError):
            start = 0
    # tip = bars[-1]；只取之前的 bar
    end = max(start, len(bars) - 1)
    for b in bars[start:end]:
        c = to_float(b.get("close"))
        v = to_float(b.get("volume"))
        if v is None or v <= 0:
            continue
        if c is not None and c > creek:
            continue  # 已离开溪上的 bar 不进基线
        vols.append(float(v))
    if len(vols) >= 3:
        vs = sorted(vols)
        mid = len(vs) // 2
        if len(vs) % 2:
            return float(vs[mid])
        return float(vs[mid - 1] + vs[mid]) / 2.0
    if fallback > 0:
        return float(fallback)
    return _sos_baseline_avg_vol(bars, tr_ctx, robust=True)


def _try_sos_thrust(bars: list[dict], tr_ctx: dict | None, baseline_avg_vol: float) -> dict:
    """单日爆发型 SOS：阳线 + 收盘站上溪/TR 上沿 + 放量 + 大涨。

    法源：docs/plans/wyckoff-sos-single-day-handoff.md
    v1：无 creek（ar_high/tr_upper）不做 thrust（禁止无箱大阳兜底）。
    """
    tr_upper = _sos_thrust_creek(tr_ctx)
    if tr_upper is None:
        return _sos_empty("无TR上沿，不判单日爆发型SOS")

    last = bars[-1]
    o = to_float(last.get("open"))
    c = to_float(last.get("close"))
    v = to_float(last.get("volume"))
    if o is None or c is None or v is None or o <= 0:
        return _sos_empty("数据异常")

    baseline_avg_vol = _sos_thrust_baseline_vol(
        bars, tr_ctx, tr_upper, baseline_avg_vol
    )
    if baseline_avg_vol <= 0:
        return _sos_empty("量能数据不足")

    if c <= o:
        return _sos_empty("单日非阳线，非爆发型SOS")
    if c <= tr_upper:
        return _sos_empty(f"收盘未站上TR上沿{tr_upper:.2f}")

    # 开→收 与 昨收→收 取大（跳空高开实体偏小但仍强势离开箱）
    prev_c = to_float(bars[-2].get("close")) if len(bars) >= 2 else None
    gain_oc = (c - o) / max(o, 0.01)
    gain_pc = (c - prev_c) / max(abs(prev_c), 0.01) if prev_c else gain_oc
    single_gain = max(gain_oc, gain_pc)
    if single_gain < WYCKOFF_SOS_THRUST_MIN_GAIN:
        return _sos_empty(
            f"单日涨幅{single_gain*100:.1f}%不足{WYCKOFF_SOS_THRUST_MIN_GAIN*100:.0f}%"
        )

    # 两位小数对齐人读「量比 1.8」（84498/47000≈1.7978 不应因浮点被卡）
    vol_ratio = v / baseline_avg_vol
    vol_ratio_r = round(vol_ratio, 2)
    if vol_ratio_r < WYCKOFF_SOS_THRUST_VOL_RATIO:
        return _sos_empty(
            f"单日量比{vol_ratio_r:.2f}不足{WYCKOFF_SOS_THRUST_VOL_RATIO:.1f}"
        )

    return {
        "sos_signal": True,
        "sos_reason": (
            f"单日爆发型突破：+{single_gain*100:.1f}%，量比{vol_ratio_r:.1f}，"
            f"收盘站上溪/上沿{tr_upper:.2f}"
        ),
        "sos_price": round(c, 2),
        "sos_kind": "thrust",
    }


def _detect_sos_at_tip(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """仅判断序列末日是否 SOS（climb OR thrust）。供滑窗/回扫复用。"""
    if len(bars) < WYCKOFF_DIVERGENCE_BARS + WYCKOFF_SPRING_SUPPORT_LOOKBACK:
        return _sos_empty("数据不足")

    baseline_climb = _sos_baseline_avg_vol(bars, tr_ctx, robust=False)
    if baseline_climb <= 0:
        return _sos_empty("量能数据不足")

    climb = _try_sos_climb(bars, baseline_climb)
    if climb.get("sos_signal"):
        return climb

    baseline_thrust = _sos_baseline_avg_vol(bars, tr_ctx, robust=True)
    thrust = _try_sos_thrust(bars, tr_ctx, baseline_thrust if baseline_thrust > 0 else baseline_climb)
    if thrust.get("sos_signal"):
        return thrust

    return climb if climb.get("sos_reason") else thrust


def _detect_sos(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    lookback_tips: int = 1,
    min_tip_idx: int | None = None,
) -> dict:
    """Detect Sign of Strength (SOS) — climb 连续放量 OR thrust 单日爆发。

    Climb（最近 5 根）:
      - ≥4/5 阳线 (close > open)（A 股极少 5 连阳，与 LPS 对齐）
      - close[-1] >= open[0] (总体抬高)
      - 平均量比 > 1.2（相对前窗基线均量）
      - 累计涨幅 >= 2%

    Thrust（法源 wyckoff-sos-single-day-handoff）:
      - 须 tr_upper；阳线；close > tr_upper；开收涨幅与量比过阈

    lookback_tips:
      - 1（默认）→ 仅末日 tip（簇滑窗 / BU 回扫必须，避免索引漂移）
      - N>1 → 从末日往回最多 N 根 tip，取最近一次命中（主分析用 RECENT_LOOKBACK）

    min_tip_idx:
      - 若给出（通常 = 最后 SC 的 bar 索引），仅接受 tip 索引 **严格大于** 该值的 SOS，
        防止回扫到 SC 之前派发段的假强势（南网周线 sos_price=63 类污染）。
    """
    lb = max(1, int(lookback_tips))
    floor_i = int(min_tip_idx) if min_tip_idx is not None else -1

    def _ok_idx(i: int) -> bool:
        return i > floor_i

    tip = _detect_sos_at_tip(bars, tr_ctx)
    tip_i = len(bars) - 1
    if tip.get("sos_signal") and _ok_idx(tip_i):
        return tip
    if tip.get("sos_signal") and not _ok_idx(tip_i):
        tip = _sos_empty("SOS 不晚于 SC，忽略旧强势")
    if lb <= 1 or len(bars) < 2:
        return tip

    min_len = WYCKOFF_DIVERGENCE_BARS + WYCKOFF_SPRING_SUPPORT_LOOKBACK
    # i = tip 索引；从次末日往回找最近一次命中（且须晚于 SC）
    # 有 SC 地板：扫 SC→今（突破可能早于固定 30 窗），硬顶 120
    # 无 SC：仅 lookback_tips 近窗
    if floor_i >= 0:
        oldest = max(min_len - 1, floor_i + 1, len(bars) - 120)
    else:
        oldest = max(min_len - 1, len(bars) - lb)
    for i in range(len(bars) - 2, oldest - 1, -1):
        if not _ok_idx(i):
            continue
        sub = bars[: i + 1]
        if len(sub) < min_len:
            continue
        hit = _detect_sos_at_tip(sub, tr_ctx)
        if hit.get("sos_signal"):
            age = len(bars) - 1 - i
            reason = hit.get("sos_reason") or ""
            if age > 0 and "近端" not in reason:
                hit = {**hit, "sos_reason": f"{reason}（近端{age}根前）"}
            return hit
    return tip

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
    # 支撑位：有 TR 下沿则固定用它（ST 与 Spring 同锚），否则局部最低
    has_tr_lower = bool(tr_ctx and tr_ctx.get("tr_lower") is not None)
    if has_tr_lower:
        support = tr_ctx["tr_lower"]
    else:
        support = min(valid_lows) if valid_lows else None

    if support is None:
        return {"st_signal": False, "st_reason": "支撑位数据异常", "st_price": None}

    # P1: 与 Spring 共用 ATR/固定比例刺穿深度
    breach_level = _spring_breach_level(support, current)
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))

    def _st_support_for_bar(bar: dict, pre_bars: list[dict]) -> float | None:
        if has_tr_lower:
            return float(tr_ctx["tr_lower"])
        pls = [to_float(b.get("low")) for b in pre_bars]
        vs = [v for v in pls if v is not None]
        return min(vs) if vs else None

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
            pre = scan_range[max(0, i - WYCKOFF_SPRING_SUPPORT_LOOKBACK):i]
            sup = _st_support_for_bar(scan_range[i], pre)
            if sup is None:
                continue
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
        sup = _st_support_for_bar(bars[i], pre)
        if sup is None:
            continue
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


def _spring_test_fields_from_st(st: dict) -> dict:
    """将 `_detect_st` 结果双写为 Test of Spring 显式字段（与 st_* 同源，避免双计分）。"""
    on = bool(st.get("st_signal"))
    raw_reason = str(st.get("st_reason") or "")
    if on:
        reason = "Spring确认：缩量回测未破支撑"
    elif "未检测到 Spring" in raw_reason:
        reason = "未检测到 Spring，无法触发 Spring确认"
    elif "数据不足" in raw_reason:
        reason = "数据不足"
    elif "锚点" in raw_reason:
        reason = "Spring 锚点未找到"
    else:
        reason = "Spring 后未检测到有效确认测试" if raw_reason else "未检测到 Spring确认"
    return {
        "spring_test_signal": on,
        "spring_test_reason": reason,
        "spring_test_price": st.get("st_price"),
    }


def _detect_spring_test(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Detect Test of Spring — Spring 后缩量确认回测（薄封装 `_detect_st`）。

    与 `st_*` 双写兼容一版；语义上本字段才是「Spring确认」，广义 SC 后 ST 本 PR 不做。
    """
    st = _detect_st(bars, tr_ctx=tr_ctx)
    out = _spring_test_fields_from_st(st)
    # 兼容：同步带回 st_*，调用方可只跑一次
    out["st_signal"] = bool(st.get("st_signal"))
    out["st_reason"] = st.get("st_reason")
    out["st_price"] = st.get("st_price")
    return out


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
        if (tr_ctx and tr_ctx.get("tr_baseline_volume"))
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

    # 阻力位：有 TR 上沿则用它（原典 LPSY = 反弹不过 TR 上沿；勿绑 in_tr）
    if tr_ctx is not None and tr_ctx.get("tr_upper") is not None:
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
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> tuple[int, dict | None]:
    """在 scan_bars 上滑窗扫描 detector_fn，返回 (最后触发 bar 的索引, 该次检测器完整输出)。

    所有事件检测器都检查子窗口最后一根 bar（bars[-1]）是否为信号，因此
    start+window-1 即为事件触发位置。用于事件簇确认时的先后顺序判断。

    timeframe / is_index：透传给 SC/AR 等认周期检测器（W-01）。

    短序列（n < window）：与 ``_scan_for_signal`` 对齐，整段试探一次（S1；
    周线叙事窗约 12 根时常小于日线 window=15）。命中则索引 = n-1。

    Returns:
        (index, result) —— 未找到时 (-1, None)
    """
    n = len(scan_bars)
    if n <= 0:
        return -1, None

    def _call(sub: list[dict]) -> dict:
        try:
            if tr_ctx is None:
                return detector_fn(sub, timeframe=timeframe, is_index=is_index)
            return detector_fn(
                sub, tr_ctx=tr_ctx, timeframe=timeframe, is_index=is_index
            )
        except TypeError:
            pass
        if tr_ctx is None:
            return detector_fn(sub)
        try:
            return detector_fn(sub, tr_ctx=tr_ctx)
        except TypeError:
            return detector_fn(sub)

    if n < window:
        try:
            res = _call(scan_bars)
            if any(k.endswith("_signal") and res.get(k) is True for k in res):
                return n - 1, res
        except Exception:
            pass
        return -1, None

    last_idx = -1
    last_res: dict | None = None
    for start in range(0, n - window + 1, step):
        sub = scan_bars[start:start + window]
        try:
            res = _call(sub)
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
    n_scan = len(scan)
    fresh = max(3, int(WYCKOFF_CLUSTER_EVENT_FRESH_BARS))
    fresh_floor = max(0, n_scan - fresh)

    # 在 scan 内找各事件最后触发位置 + 完整输出（用于读 strength）
    spring_idx, spring_res = _scan_last_event(scan, _detect_spring, tr_ctx, window=15, step=1)
    st_idx, _ = _scan_last_event(scan, _detect_st, tr_ctx, window=26, step=1)
    ut_idx, ut_res = _scan_last_event(scan, _detect_upthrust, tr_ctx, window=15, step=1)
    sos_idx, _ = _scan_last_event(scan, _detect_sos, tr_ctx, window=15, step=1)
    sow_idx, _ = _scan_last_event(scan, _detect_sign_of_weakness, tr_ctx, window=16, step=1)
    # I-M3（统一结构上下文，Bug I 机制根）：SC 重置锚用**完整序列**算一次
    # （与主流程 _detect_selling_climax 的 _find_sc_anchor 同源），再换算成 scan 内偏移；
    # 不再对截断子序列滑窗重算 SC（旧 _scan_last_event(scan, _detect_selling_climax, ...) 行已删）。
    # 锚不在 scan 内 → -1（与原「scan 内未检出 SC」一致：全部事件可认，见 I-M4）。
    _sc_anchor = _find_sc_anchor(bars, tr_ctx, include_failed=True)
    sc_idx = -1
    if _sc_anchor is not None:
        try:
            _sc_full = int(_sc_anchor["sc_bar_idx"])
        except (KeyError, TypeError, ValueError):
            _sc_full = -1
        if _sc_full >= 0:
            sc_idx = _sc_full - (len(bars) - len(scan))
            if not (0 <= sc_idx < n_scan):
                sc_idx = -1

    def _after_sc(idx: int) -> bool:
        return idx >= 0 and (sc_idx < 0 or idx > sc_idx)

    if sc_idx >= 0:
        if not _after_sc(spring_idx):
            spring_idx, spring_res = -1, None
        if not _after_sc(st_idx):
            st_idx = -1
        if not _after_sc(ut_idx):
            ut_idx, ut_res = -1, None
        if not _after_sc(sos_idx):
            sos_idx = -1
        if not _after_sc(sow_idx):
            sow_idx = -1

    support_idx = max(spring_idx, st_idx)  # 支撑测试 = Spring 或 ST

    # 顺序确认：支撑测试必须先于 SOS（间隔 >= gap）；上冲必须先于 SOW
    # 确认事件须落在近端 fresh 窗（防 60 日旧簇污染）
    accumulation_confirmed = (
        support_idx >= 0
        and sos_idx > support_idx + gap
        and sos_idx >= fresh_floor
    )
    distribution_confirmed = (
        ut_idx >= 0
        and sow_idx > ut_idx + gap
        and sow_idx >= fresh_floor
    )

    # 失败簇：支撑测试后接 SOW（且 SOS 不存在或在 SOW 之前）→ 假突破实为派发
    accumulation_failed = (
        support_idx >= 0
        and sow_idx > support_idx + gap
        and sow_idx >= fresh_floor
        and (sos_idx < 0 or sow_idx > sos_idx)
    )
    # 失败簇：上冲后接 SOS（且 SOW 不存在或在 SOS 之前）→ 假派发实为吸筹
    distribution_failed = (
        ut_idx >= 0
        and sos_idx > ut_idx + gap
        and sos_idx >= fresh_floor
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


def _detect_trend_rally(bars: list[dict]) -> dict:
    """检测趋势反抽：下降趋势中反抽不过关键均线 = 空点（对称 Trend Pullback）。

    触发条件:
      1. 近 N 日有反抽（相对低点反弹 5-20%）
      2. 反抽段缩量（量比 < 0.6）
      3. 收盘压在 MA20 附近（±2%）
      4. MA20 仍在下降
    """
    lookback = WYCKOFF_TREND_PB_LOOKBACK
    ma_window = WYCKOFF_TREND_PB_MA_WINDOW
    if len(bars) < max(lookback, ma_window) + 5:
        return {"trend_rally_signal": False, "trend_rally_reason": "数据不足", "trend_rally_price": None}

    recent = bars[-lookback:]
    recent_closes = [to_float(b.get("close")) for b in recent]
    recent_closes = [c for c in recent_closes if c is not None]
    if len(recent_closes) < lookback:
        return {"trend_rally_signal": False, "trend_rally_reason": "收盘价数据不足", "trend_rally_price": None}

    high_close = max(recent_closes)
    low_close = min(recent_closes)
    current_close = recent_closes[-1]
    if low_close <= 0:
        return {"trend_rally_signal": False, "trend_rally_reason": "价格异常", "trend_rally_price": None}

    rally_pct = (current_close - low_close) / low_close * 100
    if rally_pct < WYCKOFF_TREND_PB_MIN_PULLBACK:
        return {
            "trend_rally_signal": False,
            "trend_rally_reason": f"反抽不足（{rally_pct:.1f}% < {WYCKOFF_TREND_PB_MIN_PULLBACK}%）",
            "trend_rally_price": None,
        }
    if rally_pct > WYCKOFF_TREND_PB_MAX_PULLBACK:
        return {
            "trend_rally_signal": False,
            "trend_rally_reason": f"反抽过大（{rally_pct:.1f}% > {WYCKOFF_TREND_PB_MAX_PULLBACK}%），跌势可能已破坏",
            "trend_rally_price": None,
        }

    all_closes = [to_float(b.get("close")) for b in bars]
    all_closes = [c for c in all_closes if c is not None]
    if len(all_closes) < ma_window:
        return {"trend_rally_signal": False, "trend_rally_reason": "MA 数据不足", "trend_rally_price": None}

    ma_vals = []
    for i in range(ma_window - 1, len(all_closes)):
        ma_vals.append(sum(all_closes[i - ma_window + 1:i + 1]) / ma_window)
    if len(ma_vals) < 3:
        return {"trend_rally_signal": False, "trend_rally_reason": "MA 序列不足", "trend_rally_price": None}

    ma_current = ma_vals[-1]
    ma_prev = ma_vals[-3]

    # MA20 必须在下降
    if ma_current >= ma_prev:
        return {"trend_rally_signal": False, "trend_rally_reason": "MA20 未下降，跌势不明确", "trend_rally_price": None}

    if ma_current <= 0:
        return {"trend_rally_signal": False, "trend_rally_reason": "MA20 异常", "trend_rally_price": None}
    ma_deviation = abs(current_close - ma_current) / ma_current
    if ma_deviation > 0.02:
        return {
            "trend_rally_signal": False,
            "trend_rally_reason": f"收盘偏离 MA20 过远（{ma_deviation:.1%} > 2%）",
            "trend_rally_price": None,
        }

    recent_vols = [to_float(b.get("volume")) for b in recent if to_float(b.get("volume")) is not None]
    all_vols = [to_float(b.get("volume")) for b in bars if to_float(b.get("volume")) is not None]
    if len(recent_vols) < 3 or len(all_vols) < ma_window:
        return {"trend_rally_signal": False, "trend_rally_reason": "成交量数据不足", "trend_rally_price": None}

    avg_recent_vol = sum(recent_vols) / len(recent_vols)
    avg_ref_vol = sum(all_vols[-ma_window:]) / ma_window
    if avg_ref_vol <= 0:
        return {"trend_rally_signal": False, "trend_rally_reason": "参考量为零", "trend_rally_price": None}

    vol_ratio = avg_recent_vol / avg_ref_vol
    if vol_ratio >= WYCKOFF_TREND_PB_VOL_SHRINK:
        return {
            "trend_rally_signal": False,
            "trend_rally_reason": f"反抽未缩量（量比 {vol_ratio:.2f}）",
            "trend_rally_price": None,
        }

    return {
        "trend_rally_signal": True,
        "trend_rally_reason": f"趋势反抽（反弹 {rally_pct:.1f}%）+ 缩量（量比 {vol_ratio:.2f}）+ 压在 MA20",
        "trend_rally_price": round(current_close, 2),
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


def _jac_empty(reason: str = "无有效溪上沿") -> dict:
    return {
        "jac_signal": False,
        "jac_reason": reason,
        "jac_price": None,
        "jac_bar_idx": None,
    }


def _detect_jump_across_creek(
    bars: list[dict],
    tr_ctx: dict | None = None,
    *,
    ar_high: float | None = None,
    sos_signal: bool = False,
    bu_signal: bool = False,
    phase: str | None = None,
) -> dict:
    """Jump Across the Creek（跳溪）— 强势越过溪并站稳的专名灯。

    非新阶段机；不进 fusion。溪优先 ``tr_upper`` / ``ar_high``。
    薄检测：近窗阳线 close > creek×(1+eps)，后续 1–2 根不跌回溪下，量能不明显萎缩。
    仅在 SOS / markup / BU 附近亮（避免无背景假跳溪）。
    """
    if len(bars) < WYCKOFF_MIN_BARS + 3:
        return _jac_empty("数据不足")

    phase_s = str(phase or "")
    near_ctx = bool(sos_signal or bu_signal or phase_s == "markup")
    if not near_ctx:
        return _jac_empty("非 SOS/Markup/BU 附近，跳溪不亮")

    creek: float | None = None
    if tr_ctx is not None and tr_ctx.get("tr_upper") is not None:
        try:
            creek = float(tr_ctx["tr_upper"])
        except (TypeError, ValueError):
            creek = None
    if creek is None and ar_high is not None:
        try:
            creek = float(ar_high)
        except (TypeError, ValueError):
            creek = None
    if creek is None or creek <= 0:
        return _jac_empty()

    eps = 0.005
    threshold = creek * (1.0 + eps)
    # 近窗找越过溪的阳线；须留 1–2 根后续确认站稳
    scan_start = max(0, len(bars) - 10)
    avg_start = max(0, len(bars) - 20)
    avg_vols = [to_float(b.get("volume")) or 0 for b in bars[avg_start:]]
    avg_vol = sum(avg_vols) / max(len(avg_vols), 1)

    for i in range(scan_start, len(bars) - 1):
        bar = bars[i]
        o = to_float(bar.get("open"))
        c = to_float(bar.get("close"))
        v = to_float(bar.get("volume"))
        if o is None or c is None or v is None:
            continue
        if c <= o:
            continue
        if c <= threshold:
            continue
        # 量能不明显萎缩（相对近均量）
        if avg_vol > 0 and v < avg_vol * 0.7:
            continue
        # 后续 1–2 根不跌回 creek 下
        hold_end = min(len(bars), i + 3)
        hold_bars = bars[i + 1 : hold_end]
        if not hold_bars:
            continue
        held = True
        for hb in hold_bars:
            hc = to_float(hb.get("close"))
            if hc is None or hc < creek:
                held = False
                break
        if not held:
            continue
        return {
            "jac_signal": True,
            "jac_reason": f"越过溪 {creek:.2f} 并站稳（跳溪/JAC）",
            "jac_price": round(c, 2),
            "jac_bar_idx": i,
        }

    return _jac_empty("未见越过溪并站稳")


def _stopping_volume_empty(reason: str = "未检测到止跌量") -> dict:
    return {
        "stopping_volume_signal": False,
        "stopping_volume_reason": reason,
        "stopping_volume_price": None,
        "stopping_volume_bar_idx": None,
    }


def _detect_stopping_volume(bars: list[dict], tr_ctx: dict | None = None) -> dict:
    """Stopping Volume（止跌量）— 下跌末段放量宽幅、收盘收回棒体上半。

    可与 SC 同亮但独立命名；打分层由 core 防双计。
    """
    del tr_ctx  # 预留：TR 下沿附近优先
    if len(bars) < WYCKOFF_MIN_BARS + 2:
        return _stopping_volume_empty("数据不足")

    # 近窗均量 / 均波幅（不含末棒）
    look = bars[-(WYCKOFF_MIN_BARS + 1) : -1]
    vols = [to_float(b.get("volume")) or 0 for b in look]
    spreads: list[float] = []
    for b in look:
        h = to_float(b.get("high"))
        lo = to_float(b.get("low"))
        if h is not None and lo is not None and h > lo:
            spreads.append(h - lo)
    avg_vol = sum(vols) / max(len(vols), 1)
    avg_spread = sum(spreads) / max(len(spreads), 1) if spreads else 0.0
    if avg_vol <= 0:
        return _stopping_volume_empty("量能数据异常")

    # 下跌末段：近 5 根总体下行
    recent = bars[-6:-1]
    if len(recent) < 3:
        return _stopping_volume_empty("下跌背景不足")
    first_c = to_float(recent[0].get("close"))
    last_c = to_float(recent[-1].get("close"))
    if first_c is None or last_c is None or last_c > first_c * 0.995:
        return _stopping_volume_empty("非下跌末段")

    # 在近 3 根内找止跌量棒（含当前）
    for idx in range(len(bars) - 3, len(bars)):
        if idx < 1:
            continue
        bar = bars[idx]
        o = to_float(bar.get("open"))
        h = to_float(bar.get("high"))
        lo = to_float(bar.get("low"))
        c = to_float(bar.get("close"))
        v = to_float(bar.get("volume"))
        if any(x is None for x in (o, h, lo, c, v)):
            continue
        spread = float(h) - float(lo)
        if spread <= 0:
            continue
        # 放量
        if float(v) < avg_vol * 1.5:
            continue
        # 波幅大
        if avg_spread > 0 and spread < avg_spread * 1.2:
            continue
        # 收盘收回棒体上半（卖压被吸收）
        mid = float(lo) + 0.5 * spread
        if float(c) < mid:
            continue
        # 否决：普通阴线贴地收（虽已过 mid 检查，再防极窄上影）
        upper_half_ratio = (float(c) - float(lo)) / spread
        if upper_half_ratio < 0.5:
            continue
        return {
            "stopping_volume_signal": True,
            "stopping_volume_reason": (
                f"下跌末段放量宽幅止跌（量比 {float(v) / avg_vol:.1f}，收盘上半）"
            ),
            "stopping_volume_price": round(float(c), 2),
            "stopping_volume_bar_idx": idx,
        }

    return _stopping_volume_empty()


_CM_MODE_NOTES: dict[str, str] = {
    "markdown_absorption": "打压吸筹",
    "rally_absorption": "拉高吸筹",
    "range_absorption": "横盘吸筹",
    "rally_distribution": "拉高派发",
    "range_distribution": "横盘派发",
    "shakeout_distribution": "震仓派发",
    "none": "",
}


def _classify_cm_mode(
    *,
    phase: str | None = None,
    signals: dict | None = None,
) -> dict:
    """复合人行为模式 — 只读 phase + 事件灯的轻量映射（非新引擎）。

    禁止改 phase / tr_maturity / measure_allowed / fusion。
    """
    sig = signals if isinstance(signals, dict) else {}
    phase_s = str(phase or sig.get("phase") or "none")

    sc = bool(sig.get("sc_signal"))
    spring = bool(sig.get("spring_signal"))
    sos = bool(sig.get("sos_signal"))
    bu = bool(sig.get("bu_signal"))
    jac = bool(sig.get("jac_signal"))
    ar = bool(sig.get("ar_signal"))
    st = bool(sig.get("st_signal") or sig.get("spring_test_signal") or sig.get("secondary_test_sc_signal"))
    compression = bool(sig.get("compression_signal"))
    bc = bool(sig.get("bc_signal"))
    ut = bool(sig.get("upthrust_signal")) and not bool(sig.get("upthrust_premature"))
    utad = bool(sig.get("utad_signal"))
    sow = bool(sig.get("sow_signal"))
    are = bool(sig.get("are_signal"))
    lpsy = bool(sig.get("lpsy_signal"))

    is_acc = phase_s.startswith("accumulation") or phase_s == "markup"
    is_dist = phase_s.startswith("distribution") or phase_s == "markdown"

    mode = "none"
    # 派发优先（UTAD/BC 背景明确时）
    if utad or is_dist or (bc and (ut or sow or are or lpsy)):
        if utad:
            mode = "shakeout_distribution"
        elif bc or ut:
            mode = "rally_distribution"
        elif sow or are or lpsy or is_dist:
            mode = "range_distribution"
    elif is_acc or sc or spring or sos or bu or jac or ar:
        if phase_s == "markup" or bu or sos or jac:
            mode = "rally_absorption"
        elif spring or sc:
            mode = "markdown_absorption"
        elif compression or st or phase_s in (
            "accumulation_b",
            "accumulation_c",
            "accumulation_d",
            "accumulation_e",
        ):
            mode = "range_absorption"
        elif ar or phase_s.startswith("accumulation"):
            mode = "range_absorption"

    note = _CM_MODE_NOTES.get(mode, "")
    return {"cm_mode": mode, "cm_note": note}


def _cause_effect_targets(tr_ctx: dict | None, bars: list[dict] | None = None) -> dict:
    """因果律目标：委托 P&F 水平计数（见 wyckoff_pnf / docs/plans/wyckoff-pnf-handoff.md）。

    无 TR / 关开关 / 计数失败时回退 TR 高度 1:1，note 写明原因。
    """
    from trader_shared.wyckoff_pnf import compute_cause_effect_targets

    return compute_cause_effect_targets(tr_ctx, bars)
