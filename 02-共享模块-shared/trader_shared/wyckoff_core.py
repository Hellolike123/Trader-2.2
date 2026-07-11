from __future__ import annotations

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


# ── 威科夫辅助函数（P1: 板块/一字板/TR 检测）────────────────────────

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


# ── 动态支撑位计算（多源集成）────────────────────────────────────────

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


# ── BC (Buying Climax) 购买高潮检测 ──
def _detect_buying_climax(bars: list[dict]) -> dict:
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


# ── SOW (Sign of Weakness) 弱势信号检测 ──
def _detect_sign_of_weakness(bars: list[dict], _support: float | None = None) -> dict:
    """Detect Sign of Weakness (SOW) — 价格跌破支撑且放量。

    关键修复：当 WYCKOFF_SOW_CONSECUTIVE_DAYS > 1 时，支撑位从「不含连续确认窗口」
    的 K 线中计算，避免前一日 low 被纳入 support 导致 prev_low >= support 恒成立。
    支持 _support 覆盖：提供外部计算的动态支撑位时优先使用。

    Returns:
        dict with keys: sow_signal (bool), sow_reason (str), sow_price (float)
    """
    consecutive = WYCKOFF_SOW_CONSECUTIVE_DAYS
    min_bars = WYCKOFF_SOW_SUPPORT_LOOKBACK + consecutive
    if len(bars) < min_bars:
        return {"sow_signal": False, "sow_reason": "数据不足", "sow_price": 0.0}

    # 支撑位计算：优先使用外部动态支撑位
    if _support is not None:
        support = _support
    else:
        # 排除最后 consecutive 根（它们参与跌破确认，不应纳入 support）
        support_end = -(consecutive) if consecutive > 0 else None
        support_start = -(WYCKOFF_SOW_SUPPORT_LOOKBACK + consecutive)
        support_window = bars[support_start:support_end]
        low_values = [to_float(b.get("low")) for b in support_window]
        valid_lows = [v for v in low_values if v is not None]

        if not valid_lows:
            return {"sow_signal": False, "sow_reason": "数据异常", "sow_price": 0.0}
        support = min(valid_lows)

    # 当前 bar（最后一根）
    current = bars[-1]
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))
    cur_volume = to_float(current.get("volume"))

    if cur_low is None or cur_close is None or cur_volume is None:
        return {"sow_signal": False, "sow_reason": "数据异常", "sow_price": 0.0}

    # 跌破支撑判定逻辑
    if consecutive > 1:
        # 需要连续 N 天跌破才算
        if cur_low >= support:
            return {"sow_signal": False, "sow_reason": "未跌破支撑", "sow_price": 0.0}

        # 检查前 consecutive-1 天是否也跌破
        for i in range(2, consecutive + 1):
            check_bar = bars[-i]
            check_low = to_float(check_bar.get("low"))
            if check_low is None or check_low >= support:
                return {
                    "sow_signal": False,
                    "sow_reason": f"仅 {i-1}/{consecutive} 日跌破，需连续{consecutive}天确认",
                    "sow_price": 0.0,
                }
    else:
        # 单日判定，最低价或收盘价跌破即可触发
        if cur_low >= support and cur_close >= support:
            return {"sow_signal": False, "sow_reason": "未跌破支撑", "sow_price": 0.0}

    # 放量确认
    vol_window = bars[-(WYCKOFF_SOW_SUPPORT_LOOKBACK + 1):-1]
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in vol_window) / max(len(vol_window), 1)
    is_high_volume = avg_volume > 0 and cur_volume >= avg_volume * WYCKOFF_SOW_VOL_RATIO_THRESHOLD

    if not is_high_volume:
        return {"sow_signal": False, "sow_reason": "缩量跌破，非强弱势信号", "sow_price": 0.0}

    # 收盘在支撑下方（真跌破）
    if cur_close >= support:
        return {
            "sow_signal": True,
            "sow_reason": f"日内跌破支撑 {support:.2f} 后收回，弱势警告",
            "sow_price": round(support, 2),
        }

    return {
        "sow_signal": True,
        "sow_reason": f"放量跌破支撑 {support:.2f}，弱势信号",
        "sow_price": round(support, 2),
    }


# ── Spring 弹簧洗盘检测 ──
def _detect_spring(bars: list[dict], _support: float | None = None, symbol: str = "") -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    # P1-3: 一字板过滤
    if _is_frozen_board(current):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "一字板无效换手"}
    if len(recent) > 0 and _is_frozen_board(recent[-1]):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "前日一字板无效换手"}

    # P1-1: 交易区间检查（ATR 振幅不超过 4x）
    if not _is_trading_range(bars):
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "非交易区间（振幅过大）"}

    low_values = [to_float(b.get("low")) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    current_low = to_float(current.get("low"))
    current_close = to_float(current.get("close"))
    current_volume = to_float(current.get("volume"))

    # 使用动态支撑位（如果提供），否则从 bars 计算
    support = _support if _support is not None else (min(valid_lows) if valid_lows else None)
    if current_low is None or current_close is None or support is None or current_volume is None:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据异常"}

    # P0-1 / P1: ATR 动态刺穿深度（与 ST 共用 _spring_breach_level）
    breach_level = _spring_breach_level(support, current)

    # 刺穿深度判定：最低价刺穿深度线，且收盘价收回到支撑上方
    if current_low >= breach_level or current_close < support:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "未满足弹簧条件"}

    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)

    # P1-2: 涨跌停板量能缩放
    vol_scale = _board_vol_scale(symbol)

    # 量能分级：低量弹簧（供应耗尽）最可靠，高量弹簧可能是真破位
    if avg_volume > 0 and current_volume < avg_volume * WYCKOFF_SPRING_LOW_VOL_RATIO:
        vol_class = "low_vol_confirm"
        volume_note = "缩量洗盘（供应耗尽，可靠）"
    elif avg_volume > 0 and current_volume >= avg_volume * WYCKOFF_SPRING_BULLISH_VOL_RATIO * vol_scale:
        vol_class = "high_vol_warning"
        volume_note = "⚠️ 放量弹簧（可能是真破位）"
    else:
        vol_class = "normal"
        volume_note = "正常量能"

    return {
        "spring_signal": True,
        "spring_price": round(breach_level, 2),
        "spring_reason": f"跌破支撑后收回 {volume_note}",
        "spring_vol_class": vol_class,
    }


# ── Upthrust (UT / UTAD) 上冲回落检测 ──
def _detect_upthrust(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    high_values = [to_float(b.get("high")) for b in recent]
    valid_highs = [v for v in high_values if v is not None]
    current_high = to_float(current.get("high"))
    current_close = to_float(current.get("close"))

    resistance = max(valid_highs) if valid_highs else None
    if current_high is None or current_close is None or resistance is None:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据异常"}

    breakout_level = resistance * WYCKOFF_UTAD_BREAKOUT_RATIO
    reclaim_level = resistance * WYCKOFF_UTAD_RECLAIM_RATIO

    # 最高价高过突破界限，且收盘价跌回回落界限之下
    if current_high <= breakout_level or current_close >= reclaim_level:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "未满足上冲回落条件"}

    # P0-2: UT 需放量确认（派发需要成交量配合）
    current_volume = to_float(current.get("volume"))
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    if current_volume is not None and avg_volume > 0 and current_volume < avg_volume * WYCKOFF_UT_VOL_RATIO:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "上冲未放量，非主力派发"}

    return {
        "upthrust_signal": True,
        "upthrust_price": round(resistance, 2),
        "upthrust_reason": "突破阻力后回落，上冲回落信号",
    }


# ── Volume Divergence 量价背离检测 ──
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


# ── AR (Automatic Rally 自动反弹) 检测 ──
def _detect_ar(bars: list[dict]) -> dict:
    """Detect Automatic Rally (AR) — BC 之后抛售枯竭的快速反弹。

    触发条件:
      1. 最近 N 根 K 线内检测到 BC 信号
      2. BC 后 1-3 根 K 线内，存在至少 1 根满足:
         - close > bc_close * 1.02 (上涨 >= 2%)
         - volume > bc 前均量 * 1.2 (放量)
    """
    if len(bars) < WYCKOFF_MIN_BARS + 3:
        return {"ar_signal": False, "ar_reason": "数据不足", "ar_price": None}

    # 扫描最近 5 根 K 线寻找 BC
    scan_start = max(1, len(bars) - 5)
    bc_bar_idx = None
    bc_close = None
    bc_avg_vol = None

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
        is_stagnant = change_pct < WYCKOFF_BC_CHANGE_THRESHOLD
        cur_high = to_float(current.get("high"))
        cur_low = to_float(current.get("low"))
        real_body_top = max(cur_open, cur_close)
        upper_shadow = cur_high - real_body_top if cur_high is not None and real_body_top is not None else 0
        price_range = cur_high - cur_low if cur_high is not None and cur_low is not None else 1.0
        has_upper_shadow = (upper_shadow / max(price_range, 0.01)) > WYCKOFF_BC_UPPER_SHADOW_RATIO if price_range > 0 else False
        is_candle = cur_close < cur_open

        # 与 _detect_buying_climax 对齐：量能 + 滞涨/阴线 + 高位过滤
        if (
            vol_ratio >= WYCKOFF_BC_VOL_RATIO_THRESHOLD
            and (is_stagnant or is_candle)
            and _is_bc_high_position(bars, scan_idx)
        ):
            bc_bar_idx = scan_idx
            bc_close = cur_close
            bc_avg_vol = avg_volume
            break

    if bc_bar_idx is None:
        return {"ar_signal": False, "ar_reason": "未检测到 BC，无法触发 AR", "ar_price": None}

    # 检查 BC 后 1-3 根 K 线
    for i in range(1, min(4, len(bars) - bc_bar_idx)):
        rally_bar = bars[bc_bar_idx + i]
        r_close = to_float(rally_bar.get("close"))
        r_volume = to_float(rally_bar.get("volume"))
        if r_close is None or r_volume is None:
            continue

        if r_close > bc_close * 1.02 and r_volume > bc_avg_vol * 1.2:
            pct = (r_close / bc_close - 1) * 100
            return {
                "ar_signal": True,
                "ar_reason": f"BC 后自动反弹，放量 +{pct:.1f}%",
                "ar_price": round(r_close, 2),
            }

    return {"ar_signal": False, "ar_reason": "BC 后未检测到有效反弹", "ar_price": None}


# ── SOS (Sign of Strength 强势信号) 检测 ──
def _detect_sos(bars: list[dict]) -> dict:
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

    # 需要前 10 根用于均量计算
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
    if bullish_count < 4:
        return {"sos_signal": False, "sos_reason": f"仅 {bullish_count}/5 阳线，不足 4 根", "sos_price": None}

    # 总体抬高
    if closes[4] < opens[0]:
        return {"sos_signal": False, "sos_reason": "未总体抬高", "sos_price": None}

    # 平均量比
    sos_avg_vol = sum(volumes) / 5
    if sos_avg_vol < baseline_avg_vol * 1.2:
        return {"sos_signal": False, "sos_reason": "量能不足", "sos_price": None}

    # 累计涨幅
    gain = (closes[4] - opens[0]) / max(opens[0], 0.01)
    if gain < 0.02:
        return {"sos_signal": False, "sos_reason": f"涨幅 {gain*100:.1f}% 不足 2%", "sos_price": None}

    return {
        "sos_signal": True,
        "sos_reason": f"强势突破，{bullish_count}/5 阳线累计涨{gain*100:.1f}%，量能放大",
        "sos_price": round(closes[4], 2),
    }


# ── ST (Secondary Test 二次测试) 检测 ──
def _detect_st(bars: list[dict]) -> dict:
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


# ── LPS (Last Point of Support 最后支撑点) 检测 ──
def _detect_lps(bars: list[dict]) -> dict:
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

    def _valid_sos(sos_start: int, sos_end: int) -> tuple[bool, float, float]:
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
        ok, pre_low, baseline_avg_vol = _valid_sos(sos_start, sos_end)
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


# ── VSA (Volume Spread Analysis) 努力 vs 结果检测 ───────────────────

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


# ── P2: Compression 压缩蓄势检测 ──────────────────────────────────

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


# ── P3: Trend Pullback 趋势回踩检测 ──────────────────────────────

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


# ── 积累/派发阶段状态机 ──────────────────────────────────────────────

def _scan_for_signal(
    bars: list[dict],
    detector_fn: Any,
    window: int = 15,
    step: int = 5,
) -> bool:
    """在 bars 上滑动窗口运行检测器，找到任意窗口触发即返回 True。

    解决单次调用只能检测最近几根 K 线的问题——通过滑动窗口扫描历史。
    始终额外检查末尾窗口，避免 step>1 时漏掉最新信号。
    """
    n = len(bars)
    if n < window:
        # 数据不足整窗时，仍尝试整段 bars（兼容短序列末尾信号）
        try:
            result = detector_fn(bars)
            for key in result:
                if key.endswith("_signal") and result[key] is True:
                    return True
        except Exception:
            pass
        return False

    starts = list(range(0, n - window + 1, step))
    last_start = n - window
    if last_start not in starts:
        starts.append(last_start)

    for start in starts:
        sub = bars[start:start + window]
        try:
            result = detector_fn(sub)
            for key in result:
                if key.endswith("_signal") and result[key] is True:
                    return True
        except Exception:
            continue
    return False


def _detect_phase(bars: list[dict], signals: dict[str, Any]) -> dict[str, Any]:
    """基于信号序列推断威科夫阶段（积累 Phase A-E / 派发 Phase A'-E'）。

    真正扫描 WYCKOFF_PHASE_LOOKBACK 根 K 线的历史窗口，检测早期信号（BC/UT/AR）
    是否在较宽时间窗内出现过，再结合当前窗口的后期信号（Spring/SOS/LPS）推断阶段。

    Returns:
        {"phase": str, "phase_label": str, "phase_confidence_delta": float}
        phase_confidence_delta: 阶段上下文对当前信号置信度的修正
    """
    lookback = min(WYCKOFF_PHASE_LOOKBACK, len(bars))
    wide_bars = bars[-lookback:]

    # 当前 bar 信号优先（避免 scan step 漏检末尾），再滑动扫描历史窗口
    bc_found = bool(signals.get("bc_signal")) or _scan_for_signal(
        wide_bars, _detect_buying_climax, window=15, step=5
    )
    ar_found = bool(signals.get("ar_signal")) or _scan_for_signal(
        wide_bars, _detect_ar, window=18, step=5
    )
    ut_found = bool(signals.get("upthrust_signal")) or _scan_for_signal(
        wide_bars, _detect_upthrust, window=15, step=5
    )
    sow_found = bool(signals.get("sow_signal")) or _scan_for_signal(
        wide_bars, _detect_sign_of_weakness, window=16, step=5
    )

    # 后期信号直接用当前检测结果（通常在近期窗口内触发）
    spring = signals.get("spring_signal", False)
    sos = signals.get("sos_signal", False)
    lps = signals.get("lps_signal", False)
    compression = signals.get("compression_signal", False)
    trend_pullback = signals.get("trend_pullback_signal", False)

    # ── 积累序列：Spring 为起点（Phase C），SOS/LPS 升级到 D ──
    # 注意：BC 是派发 Phase A 事件，绝不能标成 accumulation_a
    if spring and (sos or lps):
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+SOS/LPS）",
            "phase_confidence_delta": 0.10,
        }
    if spring and trend_pullback:
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+趋势回踩）",
            "phase_confidence_delta": 0.12,
        }
    if spring:
        return {
            "phase": "accumulation_c",
            "phase_label": "积累期 C（测试：Spring）",
            "phase_confidence_delta": 0.10,
        }
    # P2: Compression = 积累期 B 末期（压缩蓄力）
    if compression:
        return {
            "phase": "accumulation_b",
            "phase_label": "积累期 B（压缩蓄力）",
            "phase_confidence_delta": 0.08,
        }
    # P3: Trend Pullback = 积累期 D 趋势确认
    if trend_pullback:
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（趋势回踩确认）",
            "phase_confidence_delta": 0.08,
        }
    # AR 且无 BC：可能是吸筹自动反弹（尚无完整 SC 检测器，作积累辅助）
    if ar_found and not bc_found:
        return {
            "phase": "accumulation_b",
            "phase_label": "积累期 B（辅助：AR无BC）",
            "phase_confidence_delta": 0.05,
        }

    # ── 派发序列：BC（Buying Climax）= 派发 Phase A ──
    if ut_found and sow_found:
        return {
            "phase": "distribution_c",
            "phase_label": "派发期 C（确认：UT+SOW）",
            "phase_confidence_delta": -0.10,
        }
    # BC 或 BC+AR（无 Spring）→ 派发期 A；BC+AR 负向更强
    if bc_found and ar_found:
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（停止：BC+AR）",
            "phase_confidence_delta": -0.10,
        }
    if bc_found:
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（购买高潮：BC）",
            "phase_confidence_delta": -0.05,
        }
    if ut_found:
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（上冲回落：UT）",
            "phase_confidence_delta": -0.05,
        }

    return {"phase": "none", "phase_label": "无明确阶段", "phase_confidence_delta": 0.0}


# ── 威科夫综合分析入口 ──
def wyckoff_analysis(bars: list[dict], symbol: str = "") -> dict:
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "spring_signal": False, "spring_reason": "数据不足", "spring_price": None,
            "upthrust_signal": False, "upthrust_reason": "数据不足", "upthrust_price": None,
            "bc_signal": False, "bc_reason": "数据不足", "bc_price": None,
            "sow_signal": False, "sow_reason": "数据不足", "sow_price": None,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            # 新增信号
            "ar_signal": False, "ar_reason": "数据不足", "ar_price": None,
            "sos_signal": False, "sos_reason": "数据不足", "sos_price": None,
            "st_signal": False, "st_reason": "数据不足", "st_price": None,
            "lps_signal": False, "lps_reason": "数据不足", "lps_price": None,
            "wyckoff_summary": "K线数据不足，无法进行威科夫分析",
        }

    # P2-2: 动态支撑位计算（多源集成）— 仅用于 Spring 检测
    dynamic_support = _compute_dynamic_support(bars, lookback=10)

    spring = _detect_spring(bars, _support=dynamic_support, symbol=symbol)
    upthrust = _detect_upthrust(bars)
    bc = _detect_buying_climax(bars)
    sow = _detect_sign_of_weakness(bars)  # SOW 使用自己的支撑位计算（处理 consecutive 逻辑）
    bearish_div, bullish_div = _detect_volume_divergence(bars)
    ar = _detect_ar(bars)
    sos = _detect_sos(bars)
    st = _detect_st(bars)
    lps = _detect_lps(bars)
    # P2/P3: 新增信号
    compression = _detect_compression(bars)
    trend_pullback = _detect_trend_pullback(bars)

    # P1-1: 阶段状态机 — 基于信号序列推断积累/派发阶段
    signals_dict = {
        "spring_signal": spring["spring_signal"],
        "upthrust_signal": upthrust["upthrust_signal"],
        "bc_signal": bc["bc_signal"],
        "sow_signal": sow["sow_signal"],
        "ar_signal": ar["ar_signal"],
        "sos_signal": sos["sos_signal"],
        "st_signal": st["st_signal"],
        "lps_signal": lps["lps_signal"],
        "compression_signal": compression["compression_signal"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
    }
    phase = _detect_phase(bars, signals_dict)

    # P3-1: VSA 量价幅度分析
    vsa = _detect_effort_vs_result(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bc["bc_signal"]:
        parts.append(f"购买高潮: {bc['bc_reason']}")
    if sow["sow_signal"]:
        parts.append(f"弱势信号: {sow['sow_reason']}")
    if ar["ar_signal"]:
        parts.append(f"自动反弹: {ar['ar_reason']}")
    if sos["sos_signal"]:
        parts.append(f"强势信号: {sos['sos_reason']}")
    if st["st_signal"]:
        parts.append(f"二次测试: {st['st_reason']}")
    if lps["lps_signal"]:
        parts.append(f"最后支撑: {lps['lps_reason']}")
    if bearish_div and bullish_div:
        parts.append("量价信号冲突，无法确定方向")
    elif bearish_div:
        parts.append("看空量价背离")
    elif bullish_div:
        parts.append("看多量价背离")
    if vsa["effort_no_result"]:
        parts.append("高量窄幅（努力无结果）")
    if vsa["no_supply"]:
        parts.append("低量窄幅（供应耗尽）")
    if compression["compression_signal"]:
        parts.append(f"压缩蓄势: {compression['compression_reason']}")
    if trend_pullback["trend_pullback_signal"]:
        parts.append(f"趋势回踩: {trend_pullback['trend_pullback_reason']}")
    if not parts:
        parts.append("无明显威科夫信号")

    return {
        "spring_signal": spring["spring_signal"],
        "spring_reason": spring["spring_reason"],
        "spring_price": round(spring["spring_price"], 2) if spring["spring_signal"] else None,
        "upthrust_signal": upthrust["upthrust_signal"],
        "upthrust_reason": upthrust["upthrust_reason"],
        "upthrust_price": round(upthrust["upthrust_price"], 2) if upthrust["upthrust_signal"] else None,
        "bc_signal": bc["bc_signal"],
        "bc_reason": bc["bc_reason"],
        "bc_price": round(bc["bc_price"], 2) if bc["bc_signal"] else None,
        "sow_signal": sow["sow_signal"],
        "sow_reason": sow["sow_reason"],
        "sow_price": round(sow["sow_price"], 2) if sow["sow_signal"] else None,
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        # 新增信号
        "ar_signal": ar["ar_signal"],
        "ar_reason": ar["ar_reason"],
        "ar_price": round(ar["ar_price"], 2) if ar["ar_signal"] else None,
        "sos_signal": sos["sos_signal"],
        "sos_reason": sos["sos_reason"],
        "sos_price": round(sos["sos_price"], 2) if sos["sos_signal"] else None,
        "st_signal": st["st_signal"],
        "st_reason": st["st_reason"],
        "st_price": round(st["st_price"], 2) if st["st_signal"] else None,
        "lps_signal": lps["lps_signal"],
        "lps_reason": lps["lps_reason"],
        "lps_price": round(lps["lps_price"], 2) if lps["lps_signal"] else None,
        # P0-1: 弹簧量能分级
        "spring_vol_class": spring.get("spring_vol_class", "normal") if spring["spring_signal"] else None,
        # P1-1: 阶段状态机
        "phase": phase["phase"],
        "phase_label": phase["phase_label"],
        "phase_confidence_delta": phase.get("phase_confidence_delta", 0.0),
        # P3-1: VSA 量价幅度分析
        "effort_no_result": vsa["effort_no_result"],
        "no_supply": vsa["no_supply"],
        # P2/P3: 新增信号
        "compression_signal": compression["compression_signal"],
        "compression_reason": compression["compression_reason"],
        "compression_price": compression["compression_price"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
        "trend_pullback_reason": trend_pullback["trend_pullback_reason"],
        "trend_pullback_price": trend_pullback["trend_pullback_price"],
        "wyckoff_summary": "；".join(parts),
    }


def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None, symbol: str = "") -> dict:
    """日线威科夫（供 fusion / 短线侧兼容）。"""
    result = wyckoff_analysis(bars, symbol=symbol)
    if isinstance(result, dict):
        result = {**result, "timeframe": "daily"}
    return {"wyckoff": result}


def wyckoff_strategy_midline(
    current: float,
    weekly_bars: list[dict] | None = None,
    daily_bars: list[dict] | None = None,
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str = "",
) -> dict:
    """中线威科夫独立判断：优先周 K，不足时回退日 K。

    与日线 fusion 路径分离：报告「威科夫：…」定性用本结果。
    """
    weekly_bars = weekly_bars or []
    daily_bars = daily_bars or []
    if len(weekly_bars) >= WYCKOFF_MIN_BARS:
        bars = weekly_bars
        tf = "weekly"
    elif len(daily_bars) >= WYCKOFF_MIN_BARS:
        bars = daily_bars
        tf = "daily_fallback"
    else:
        return {
            "wyckoff": {
                "timeframe": "insufficient",
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "wyckoff_summary": "K线不足，无法做中线威科夫",
            }
        }
    result = wyckoff_analysis(bars, symbol=symbol)
    if isinstance(result, dict):
        result = {**result, "timeframe": tf}
    return {"wyckoff": result}


# ── Wyckoff 独立打分 ──────────────────────────────────────────────

def calculate_wyckoff_score(bars: list[dict], symbol: str = "") -> dict:
    """基于 Wyckoff 信号规则的独立打分函数。

    先调用 wyckoff_analysis() 获取 5 路信号，按权重累加 raw_score，
    再线性映射到 0-100 分数（50 为中性）。

    Args:
        bars: 日线 K 线数据列表，最少 WYCKOFF_MIN_BARS 根。

    Returns:
        {
            "score": int,          # 0-100 分数
            "raw": int,            # 加权累加原始分（范围约 -80 ~ +80）
            "signals": list[str],  # 参与打分的信号明细
            "summary": str,        # 一句话总结
        }
    """
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "score": 50,
            "raw": 0,
            "signals": [],
            "summary": "K线数据不足，无法打分",
        }

    analysis = wyckoff_analysis(bars, symbol=symbol)

    raw = 0
    signals: list[str] = []

    spring = analysis.get("spring_signal")
    bullish_div = analysis.get("bullish_volume_divergence")
    bearish_div = analysis.get("bearish_volume_divergence")
    upthrust = analysis.get("upthrust_signal")
    bc = analysis.get("bc_signal")
    sow = analysis.get("sow_signal")
    spring_vol_class = analysis.get("spring_vol_class")

    # 1. Spring — 最强看多信号；高量弹簧减半（可能是真破位，非供应耗尽）
    if spring:
        spring_pts = WYCKOFF_SCORE_SPRING
        if spring_vol_class == "high_vol_warning":
            spring_pts = spring_pts // 2  # 高量 Spring 分数减半
            signals.append(f"Spring(高量降权) +{spring_pts}")
        else:
            signals.append(f"Spring +{spring_pts}")
        raw += spring_pts

    # 2. Spring + 看多背离额外加分；高量 Spring 同步降权（与主分一致）
    if spring and bullish_div:
        bonus = WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS
        if spring_vol_class == "high_vol_warning":
            bonus = bonus // 2  # 高量时背离加成减半（0 当 1 时 floor 为 0）
            if bonus > 0:
                signals.append(f"Spring×看多背离(高量降权) +{bonus}")
            else:
                signals.append("Spring×看多背离(高量降权) +0")
        else:
            signals.append(f"Spring×看多背离 +{bonus}")
        raw += bonus

    # 3. 独立看多背离
    if bullish_div and not spring:
        raw += WYCKOFF_SCORE_BULLISH_DIV
        signals.append(f"看多背离 +{WYCKOFF_SCORE_BULLISH_DIV}")

    # 4. Upthrust — 假突破派发
    if upthrust:
        raw += WYCKOFF_SCORE_UT
        signals.append(f"Upthrust {WYCKOFF_SCORE_UT}")

    # 5. 看空背离
    if bearish_div and not bullish_div:
        raw += WYCKOFF_SCORE_BEARISH_DIV
        signals.append(f"看空背离 {WYCKOFF_SCORE_BEARISH_DIV}")

    # 6. Buying Climax — 天量滞涨
    if bc:
        raw += WYCKOFF_SCORE_BC
        signals.append(f"购买高潮 {WYCKOFF_SCORE_BC}")

    # 7. Sign of Weakness — 放量跌破
    if sow:
        raw += WYCKOFF_SCORE_SOW
        signals.append(f"弱势信号 {WYCKOFF_SCORE_SOW}")

    # ── 新增经典信号 ──

    # 8. AR (Automatic Rally) — BC 后自动反弹
    if analysis.get("ar_signal"):
        raw += WYCKOFF_SCORE_AR
        signals.append(f"AR 反弹 +{WYCKOFF_SCORE_AR}")

    # 9. SOS (Sign of Strength) — 强势突破
    if analysis.get("sos_signal"):
        raw += WYCKOFF_SCORE_SOS
        signals.append(f"SOS +{WYCKOFF_SCORE_SOS}")

    # 10. ST (Secondary Test) — 二次测试支撑
    if analysis.get("st_signal"):
        raw += WYCKOFF_SCORE_ST
        signals.append(f"ST +{WYCKOFF_SCORE_ST}")

    # 11. LPS (Last Point of Support) — 最后支撑点
    if analysis.get("lps_signal"):
        raw += WYCKOFF_SCORE_LPS
        signals.append(f"LPS +{WYCKOFF_SCORE_LPS}")

    # 12. P2: Compression — 压缩蓄势
    if analysis.get("compression_signal"):
        raw += WYCKOFF_SCORE_COMPRESSION
        signals.append(f"压缩蓄势 +{WYCKOFF_SCORE_COMPRESSION}")

    # 13. P3: Trend Pullback — 趋势回踩
    if analysis.get("trend_pullback_signal"):
        raw += WYCKOFF_SCORE_TREND_PB
        signals.append(f"趋势回踩 +{WYCKOFF_SCORE_TREND_PB}")

    # ── P3-1: VSA 量价幅度修正 ──
    effort_no_result = analysis.get("effort_no_result", False)
    no_supply = analysis.get("no_supply", False)

    # Spring + 低量窄幅（供应耗尽）→ 额外加分
    if spring and no_supply:
        raw += 5
        signals.append("Spring×供应耗尽 +5")

    # UT + 高量窄幅（努力无结果）→ 额外扣分（派发确认）
    if upthrust and effort_no_result:
        raw -= 5
        signals.append("UT×努力无结果 -5")

    # SOS + 高量窄幅 → SOS 不可靠，取消加分
    if analysis.get("sos_signal") and effort_no_result:
        raw -= WYCKOFF_SCORE_SOS
        signals.append(f"SOS×努力无结果 撤销 +{WYCKOFF_SCORE_SOS}")

    # ── 阶段置信度修正：phase_confidence_delta * 20 取整后微调 raw ──
    phase_delta = analysis.get("phase_confidence_delta") or 0.0
    try:
        phase_adj = int(round(float(phase_delta) * 20))
    except (TypeError, ValueError):
        phase_adj = 0
    if phase_adj:
        raw += phase_adj
        signals.append(f"阶段修正 {phase_adj:+d}")

    # 线性映射: raw ∈ [-MAX_ABS, +MAX_ABS] → score ∈ [0, 100]
    score = max(0, min(100, 50 + raw * 50 // WYCKOFF_SCORE_MAX_ABS))

    if score >= 70:
        summary = f"威科夫看多（{score}/100）"
    elif score >= 60:
        summary = f"威科夫偏多（{score}/100）"
    elif score <= 30:
        summary = f"威科夫看空（{score}/100）"
    elif score <= 40:
        summary = f"威科夫偏空（{score}/100）"
    else:
        summary = f"威科夫中性（{score}/100）"

    return {
        "score": score,
        "raw": raw,
        "signals": signals,
        "summary": summary,
    }


def format_wyckoff_oneline(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
) -> str:
    """报告用威科夫一行人话（结论 + 白话，不拆第二行）。

    优先级与 fusion 主信号大致对齐：
      Spring > SOS > UT > BC > SOW > AR > ST > LPS > Compression > TrendPullback > 背离 > 无信号

    Returns:
        如「威科夫：低位假跌破后收回，偏多（更像洗盘，缩量较可信）」
    """
    wyk = wyckoff if isinstance(wyckoff, dict) else {}
    # 兼容 strategy 包装
    if "wyckoff" in wyk and isinstance(wyk.get("wyckoff"), dict):
        wyk = wyk["wyckoff"]

    def _dir_label(d: int) -> str:
        if d > 0:
            return "偏多"
        if d < 0:
            return "偏空"
        return "中性"

    # 按 fusion 优先级选主信号
    if wyk.get("spring_signal"):
        vol = wyk.get("spring_vol_class") or "normal"
        if vol == "high_vol_warning":
            main = "低位跌破后收回"
            note = "放量跌破，也可能是真破位，信号偏弱"
            d = 1
        elif vol == "low_vol_confirm":
            main = "低位假跌破后收回"
            note = "更像洗盘，缩量较可信"
            d = 1
        else:
            main = "低位假跌破后收回"
            note = "更像洗盘吸筹"
            d = 1
    elif wyk.get("sos_signal"):
        main, note, d = "连续放量上攻", "多头发力，趋势转强迹象", 1
    elif wyk.get("upthrust_signal"):
        main, note, d = "冲高回落假突破", "上方试盘失败，结构偏顶", -1
    elif wyk.get("bc_signal"):
        main, note, d = "高位放量滞涨", "购买高潮迹象，注意见好就收", -1
    elif wyk.get("sow_signal"):
        main, note, d = "放量跌破支撑", "弱势确认，防守优先", -1
    elif wyk.get("ar_signal"):
        main, note, d = "高潮后快速反弹", "仅反弹，还不能当反转", 1
    elif wyk.get("st_signal"):
        main, note, d = "回踩支撑站住", "二次确认支撑有效", 1
    elif wyk.get("lps_signal"):
        main, note, d = "突破后缩量回踩", "回踩不破，仍偏强", 1
    # P2/P3: 新增信号（优先级在 LPS 之后、divergence 之前）
    elif wyk.get("compression_signal"):
        main, note, d = "压缩蓄势", "振幅收窄+量能枯竭，突破在即", 1
    elif wyk.get("trend_pullback_signal"):
        main, note, d = "趋势回踩", "回踩不破均线，趋势延续", 1
    elif wyk.get("bullish_volume_divergence") and not wyk.get("bearish_volume_divergence"):
        main, note, d = "下跌缩量", "抛压减轻，有止跌迹象", 1
    elif wyk.get("bearish_volume_divergence") and not wyk.get("bullish_volume_divergence"):
        main, note, d = "上涨缩量", "上攻乏力，慎追高", -1
    else:
        # 已跑完引擎但未触发 Spring/SOS/UT 等事件 → 不是「数据不全」
        # 有 timeframe / summary 视为已计算；完全空 dict 才偏数据不足
        has_run = bool(
            wyk.get("timeframe")
            or wyk.get("wyckoff_summary")
            or any(
                k.endswith("_signal") or k.endswith("_reason")
                for k in wyk.keys()
            )
        )
        if has_run:
            return "威科夫：暂无事件 · 中性"
        return "威科夫：数据不足 · 中性"

    # 外部 fusion direction 可覆盖展示方向（保持与融合层一致）
    if direction is not None:
        d = int(direction)
    # 句式：威科夫：{判断} · {偏多|偏空|中性}（说明）
    return f"威科夫：{main} · {_dir_label(d)}（{note}）"
