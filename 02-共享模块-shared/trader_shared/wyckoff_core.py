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
        WYCKOFF_SOW_SUPPORT_LOOKBACK,
        WYCKOFF_SOW_VOL_RATIO_THRESHOLD,
        WYCKOFF_SOW_CONSECUTIVE_DAYS,
        WYCKOFF_SPRING_SUPPORT_LOOKBACK,
        WYCKOFF_SPRING_RECLAIM_RATIO,
        WYCKOFF_SPRING_ATR_MULTIPLE,
        WYCKOFF_SPRING_BULLISH_VOL_RATIO,
        WYCKOFF_UTAD_BREAKOUT_RATIO,
        WYCKOFF_UTAD_RECLAIM_RATIO,
        WYCKOFF_DIVERGENCE_BARS,
        WYCKOFF_DIVERGENCE_RATIO,
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
    )
except ImportError:
    WYCKOFF_MIN_BARS = 15
    WYCKOFF_BC_VOL_RATIO_THRESHOLD = 1.8  # must match config.py:95
    WYCKOFF_BC_CHANGE_THRESHOLD = 1.0
    WYCKOFF_BC_UPPER_SHADOW_RATIO = 0.02
    WYCKOFF_SOW_SUPPORT_LOOKBACK = 10
    WYCKOFF_SOW_VOL_RATIO_THRESHOLD = 1.0
    WYCKOFF_SOW_CONSECUTIVE_DAYS = 1
    WYCKOFF_SPRING_SUPPORT_LOOKBACK = 10
    WYCKOFF_SPRING_RECLAIM_RATIO = 0.985
    WYCKOFF_SPRING_ATR_MULTIPLE = 0.5
    WYCKOFF_SPRING_BULLISH_VOL_RATIO = 1.3
    WYCKOFF_UTAD_BREAKOUT_RATIO = 1.005
    WYCKOFF_UTAD_RECLAIM_RATIO = 0.995
    WYCKOFF_DIVERGENCE_BARS = 5
    WYCKOFF_DIVERGENCE_RATIO = 0.85
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

        # 天量 + 滞涨（收盘接近开盘或阴线）
        is_stagnant = change_pct < WYCKOFF_BC_CHANGE_THRESHOLD
        has_upper_shadow = upper_shadow_ratio > WYCKOFF_BC_UPPER_SHADOW_RATIO

        if not (is_stagnant or (cur_close < cur_open)):
            continue

        parts = []
        parts.append(f"量比 {vol_ratio:.1f}")
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
def _detect_sign_of_weakness(bars: list[dict]) -> dict:
    """Detect Sign of Weakness (SOW) — 价格跌破支撑且放量。

    Returns:
        dict with keys: sow_signal (bool), sow_reason (str), sow_price (float)
    """
    if len(bars) < WYCKOFF_SOW_SUPPORT_LOOKBACK + 1:
        return {"sow_signal": False, "sow_reason": "数据不足", "sow_price": 0.0}

    recent = bars[-(WYCKOFF_SOW_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    low_values = [to_float(b["low"]) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    cur_low = to_float(current.get("low"))
    cur_close = to_float(current.get("close"))
    cur_volume = to_float(current.get("volume"))

    if cur_low is None or cur_close is None or cur_volume is None or not valid_lows:
        return {"sow_signal": False, "sow_reason": "数据异常", "sow_price": 0.0}

    support = min(valid_lows)

    # 跌破支撑判定逻辑
    if WYCKOFF_SOW_CONSECUTIVE_DAYS > 1:
        # 需要连续 N 天跌破才算
        if cur_low >= support:
            return {"sow_signal": False, "sow_reason": "未跌破支撑", "sow_price": 0.0}
        
        # 检查前一天是否也跌破
        prev_low = to_float(bars[-2].get("low")) if len(bars) >= 2 else None
        if prev_low is None or prev_low >= support:
            return {"sow_signal": False, "sow_reason": f"仅单日跌破，需连续{WYCKOFF_SOW_CONSECUTIVE_DAYS}天确认", "sow_price": 0.0}
    else:
        # 单日判定，最低价或收盘价跌破即可触发
        if cur_low >= support and cur_close >= support:
            return {"sow_signal": False, "sow_reason": "未跌破支撑", "sow_price": 0.0}

    # 放量确认
    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)
    is_high_volume = avg_volume > 0 and cur_volume >= avg_volume * WYCKOFF_SOW_VOL_RATIO_THRESHOLD

    if not is_high_volume:
        return {"sow_signal": False, "sow_reason": "缩量跌破，非强弱势信号", "sow_price": 0.0}

    # 收盘在支撑下方（真跌破）
    if cur_close >= support:
        return {
            "sow_signal": True,
            "sow_reason": f"放量跌破支撑 {support:.2f} 后收回，弱势警告",
            "sow_price": round(support, 2),
        }

    return {
        "sow_signal": True,
        "sow_reason": f"放量跌破支撑 {support:.2f}，弱势信号",
        "sow_price": round(support, 2),
    }


# ── Spring 弹簧洗盘检测 ──
def _detect_spring(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    low_values = [to_float(b["low"]) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    current_low = to_float(current.get("low"))
    current_close = to_float(current.get("close"))
    current_volume = to_float(current.get("volume"))

    support = min(valid_lows) if valid_lows else None
    if current_low is None or current_close is None or support is None or current_volume is None:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "数据异常"}

    # P0-1: ATR 动态刺穿深度，优先使用 ATR，fallback 到固定比例
    atr14 = to_float(current.get("atr14"))
    if atr14 is not None and atr14 > 0:
        breach_level = support - atr14 * WYCKOFF_SPRING_ATR_MULTIPLE
    else:
        breach_level = support * WYCKOFF_SPRING_RECLAIM_RATIO

    # 刺穿深度判定：最低价刺穿深度线，且收盘价收回到支撑上方
    if current_low >= breach_level or current_close < support:
        return {"spring_signal": False, "spring_price": 0.0, "spring_reason": "未满足弹簧条件"}

    avg_volume = sum(to_float(b.get("volume")) or 0 for b in recent) / max(len(recent), 1)

    volume_note = "放量恐慌" if (avg_volume > 0 and current_volume >= avg_volume * WYCKOFF_SPRING_BULLISH_VOL_RATIO) else "缩量洗盘"

    return {
        "spring_signal": True,
        "spring_price": round(breach_level, 2),
        "spring_reason": f"跌破支撑后收回 {volume_note}",
    }


# ── Upthrust (UT / UTAD) 上冲回落检测 ──
def _detect_upthrust(bars: list[dict]) -> dict:
    if len(bars) < WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1:
        return {"upthrust_signal": False, "upthrust_price": 0.0, "upthrust_reason": "数据不足"}

    recent = bars[-(WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]
    current = bars[-1]

    high_values = [to_float(b["high"]) for b in recent]
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

        if vol_ratio >= WYCKOFF_BC_VOL_RATIO_THRESHOLD and (is_stagnant or is_candle):
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
      - 全部 5 根为阳线 (close > open)
      - close[4] >= open[0] (总体抬高)
      - 平均量比 > 1.2
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

    # 全部阳线
    if not all(c > o for c, o in zip(closes, opens)):
        return {"sos_signal": False, "sos_reason": "非全部阳线", "sos_price": None}

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
        "sos_reason": f"强势突破，5 连阳累计涨{gain*100:.1f}%，量能放大",
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

    low_values = [to_float(b["low"]) for b in recent]
    valid_lows = [v for v in low_values if v is not None]
    support = min(valid_lows) if valid_lows else None

    if support is None:
        return {"st_signal": False, "st_reason": "支撑位数据异常", "st_price": None}

    breach_level = support * WYCKOFF_SPRING_RECLAIM_RATIO
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
            pls = [to_float(b["low"]) for b in pre]
            vs = [v for v in pls if v is not None]
            if not vs:
                continue
            sup = min(vs)
            br = sup * WYCKOFF_SPRING_RECLAIM_RATIO
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
        pls = [to_float(b["low"]) for b in pre]
        vs = [v for v in pls if v is not None]
        if not vs:
            continue
        sup = min(vs)
        br = sup * WYCKOFF_SPRING_RECLAIM_RATIO
        if sl < br and sc >= sup:
            spring_idx = i
            break

    if spring_idx is None:
        return {"st_signal": False, "st_reason": "Spring 锚点未找到", "st_price": None}

    # 检查 Spring 后 3-15 根 K 线
    spring_avg_vol = sum(to_float(b.get("volume")) or 0 for b in
                         bars[max(0, spring_idx - WYCKOFF_SPRING_SUPPORT_LOOKBACK):spring_idx]) / \
                     max(WYCKOFF_SPRING_SUPPORT_LOOKBACK, 1)

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
    检测窗口 (25+ 根):
      bars[-5:]     = SOS 窗口
      bars[-15:-5]  = 回调窗口 (5-10 根)
      bars[-20:-15] = 前高窗口 (5 根, 用于 pre_low)
    """
    min_bars = WYCKOFF_DIVERGENCE_BARS + 10 + WYCKOFF_SPRING_SUPPORT_LOOKBACK  # ≈25
    if len(bars) < min_bars:
        return {"lps_signal": False, "lps_reason": "数据不足", "lps_price": None}

    # ── 1. 检测 SOS: bars[-5:] ──
    sos_window = bars[-WYCKOFF_DIVERGENCE_BARS:]
    sos_closes: list[float] = []
    sos_opens: list[float] = []
    sos_vols: list[float] = []
    for b in sos_window:
        o = to_float(b.get("open"))
        c = to_float(b.get("close"))
        v = to_float(b.get("volume"))
        if o is None or c is None or v is None:
            continue
        sos_opens.append(o)
        sos_closes.append(c)
        sos_vols.append(v)

    if len(sos_closes) != 5:
        return {"lps_signal": False, "lps_reason": "SOS 数据不足", "lps_price": None}
    if not all(c > o for c, o in zip(sos_closes, sos_opens)):
        return {"lps_signal": False, "lps_reason": "SOS 非全阳线", "lps_price": None}
    if sos_closes[4] <= sos_opens[0]:
        return {"lps_signal": False, "lps_reason": "SOS 涨幅不足", "lps_price": None}
    gain = (sos_closes[4] - sos_opens[0]) / max(sos_opens[0], 0.01)
    if gain < 0.02:
        return {"lps_signal": False, "lps_reason": "SOS 涨幅不足", "lps_price": None}

    # SOS 量能: 计算基线均量 (bars[-15:-5], SOS 之前 10 根)
    baseline_len = WYCKOFF_DIVERGENCE_BARS + 10  # 15
    baseline_start = max(0, len(bars) - baseline_len)
    baseline = bars[baseline_start:-WYCKOFF_DIVERGENCE_BARS]
    baseline_avg_vol = sum(to_float(b.get("volume")) or 0 for b in baseline) / max(len(baseline), 1)
    if baseline_avg_vol <= 0:
        return {"lps_signal": False, "lps_reason": "量能数据不足", "lps_price": None}
    sos_avg_vol = sum(sos_vols) / 5
    if sos_avg_vol < baseline_avg_vol * 1.2:
        return {"lps_signal": False, "lps_reason": "SOS 量能不足", "lps_price": None}

    # ── 2. 扫描回调窗口: bars[-10:-5] ──
    # 窗口内滑动检测 2-10 根的缩量回调
    pullback_start = max(0, len(bars) - WYCKOFF_DIVERGENCE_BARS - 5)  # bars[-10:-5] 的起点
    pullback = bars[pullback_start:-WYCKOFF_DIVERGENCE_BARS]  # 最多 5 根
    if len(pullback) < 2:
        return {"lps_signal": False, "lps_reason": "回调窗口不足", "lps_price": None}

    # 跳过 None 数据，与 _detect_spring 一致：静默变 0 会误触发信号
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
        return {"lps_signal": False, "lps_reason": "回调有效数据不足", "lps_price": None}

    best_lps: dict | None = None

    for end in range(1, len(pb_closes) + 1):  # 回调长度 1..5
        seg_closes = pb_closes[:end]
        seg_lows = pb_lows[:end]

        # 回调: 价格下行或横盘 (末尾 <= 起始 * 1.01)
        if seg_closes[-1] > seg_closes[0] * 1.01:
            continue

        seg_low = min(seg_lows)

        # 记录最佳 LPS (最低回调点)
        if best_lps is None or seg_low < best_lps["low"]:
            best_lps = {
                "low": seg_low,
                "close": seg_closes[-1],
                "end_idx": pullback_start + end - 1,
                "vol": pb_vols[end - 1],
            }

    if best_lps is None:
        return {"lps_signal": False, "lps_reason": "未检测到有效回调", "lps_price": None}

    # ── 3. 找前高 (回调窗口之前的 5 根: bars[-15:-10]) ──
    pre_low_start = pullback_start - 5
    pre_low_start = max(0, pre_low_start)
    pre_low_end = pullback_start
    pre_lows = [to_float(bars[i].get("low")) for i in range(pre_low_start, pre_low_end)]
    pre_lows = [v for v in pre_lows if v is not None]
    if not pre_lows:
        return {"lps_signal": False, "lps_reason": "前低数据不足", "lps_price": None}
    pre_low = min(pre_lows)

    # 不破前低 (允许 1% 容差)
    if best_lps["low"] < pre_low * 0.99:
        return {"lps_signal": False, "lps_reason": "回调跌破前低", "lps_price": None}

    # 末期缩量: 回调末端成交量 < 基线均量 * 0.7
    if best_lps["vol"] >= baseline_avg_vol * 0.7:
        return {"lps_signal": False, "lps_reason": "回调量能不萎缩", "lps_price": None}

    return {
        "lps_signal": True,
        "lps_reason": f"SOS 前缩量回调，低点 {best_lps['low']:.2f} 未破前低 {pre_low:.2f}",
        "lps_price": round(best_lps["low"], 2),
    }


# ── 威科夫综合分析入口 ──
def wyckoff_analysis(bars: list[dict]) -> dict:
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

    spring = _detect_spring(bars)
    upthrust = _detect_upthrust(bars)
    bc = _detect_buying_climax(bars)
    sow = _detect_sign_of_weakness(bars)
    bearish_div, bullish_div = _detect_volume_divergence(bars)
    ar = _detect_ar(bars)
    sos = _detect_sos(bars)
    st = _detect_st(bars)
    lps = _detect_lps(bars)

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
        "wyckoff_summary": "；".join(parts),
    }


def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None) -> dict:
    return {"wyckoff": wyckoff_analysis(bars)}


# ── Wyckoff 独立打分 ──────────────────────────────────────────────

def calculate_wyckoff_score(bars: list[dict]) -> dict:
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

    analysis = wyckoff_analysis(bars)

    raw = 0
    signals: list[str] = []

    spring = analysis.get("spring_signal")
    bullish_div = analysis.get("bullish_volume_divergence")
    bearish_div = analysis.get("bearish_volume_divergence")
    upthrust = analysis.get("upthrust_signal")
    bc = analysis.get("bc_signal")
    sow = analysis.get("sow_signal")

    # 1. Spring — 最强看多信号
    if spring:
        raw += WYCKOFF_SCORE_SPRING
        signals.append(f"Spring +{WYCKOFF_SCORE_SPRING}")

    # 2. Spring + 看多背离额外加分
    if spring and bullish_div:
        raw += WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS
        signals.append(f"Spring×看多背离 +{WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS}")

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
