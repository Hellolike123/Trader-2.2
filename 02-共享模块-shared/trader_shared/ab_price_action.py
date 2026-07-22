"""Al Brooks 价格行为信号模块 — T0 三重共振第一席位。

基于 Al Brooks《Trading Price Action》三部曲（趋势篇/区间篇/反转篇）的方法论，
用于 5 分钟级 T0 执行层的方向判定和入场信号。

核心概念：
- Always-In (总在场内): 必须一直在市场中，当前头寸方向即 Always-In 方向
- Signal Bar (信号棒): 入场依据棒线，强反转棒 = 短尾线 + 收盘在极端
- Follow-through (坚持到底): 信号棒后 1-2 根棒确认方向
- H1/L1/L2/L3 (高低点回调计数): 回调次数越多越可靠，L2/H2 通常是最佳入场
- Breakout Mode (突破模式): 交易区间内等待方向突破
"""
from __future__ import annotations

from typing import Any


def _bar_body_pct(bar: dict) -> float:
    """棒线实体占比 = |close - open| / (high - low)。"""
    o, c = float(bar.get("open", 0)), float(bar.get("close", 0))
    h, l = float(bar.get("high", 0)), float(bar.get("low", 0))
    rng = h - l
    if rng <= 0:
        return 0.0
    return abs(c - o) / rng


def _bar_direction(bar: dict) -> int:
    """+1 多头, -1 空头, 0 十字星。"""
    o, c = float(bar.get("open", 0)), float(bar.get("close", 0))
    if c > o:
        return 1
    if c < o:
        return -1
    return 0


def _bar_close_position(bar: dict) -> float:
    """收盘在棒线中的相对位置 [0,1]。1=收在最高，0=收在最低。"""
    h, l = float(bar.get("high", 0)), float(bar.get("low", 0))
    c = float(bar.get("close", 0))
    rng = h - l
    if rng <= 0:
        return 0.5
    return (c - l) / rng


def _upper_shadow_pct(bar: dict) -> float:
    """上影线占比。"""
    o, c = float(bar.get("open", 0)), float(bar.get("close", 0))
    h = float(bar.get("high", 0))
    rng = h - float(bar.get("low", 0))
    if rng <= 0:
        return 0.0
    return (h - max(o, c)) / rng


def _lower_shadow_pct(bar: dict) -> float:
    """下影线占比。"""
    o, c = float(bar.get("open", 0)), float(bar.get("close", 0))
    l = float(bar.get("low", 0))
    h = float(bar.get("high", 0))
    rng = h - l
    if rng <= 0:
        return 0.0
    return (min(o, c) - l) / rng


def _ema(values: list[float], period: int) -> float | None:
    """计算单个 EMA 值。"""
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return ema


def _calc_atr(bars: list[dict], period: int = 14) -> float:
    """计算 ATR（平均真实范围）。"""
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = float(bars[i].get("high", 0))
        l = float(bars[i].get("low", 0))
        prev_c = float(bars[i - 1].get("close", 0))
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period


# ── 信号棒检测 ──────────────────────────────────────────────────────────────

def detect_signal_bar(bar: dict, prev_bar: dict | None = None, atr: float = 0) -> dict[str, Any]:
    """检测单根棒线是否为 Al Brooks 信号棒。

    强信号棒（区间篇 Ch26 "做一笔交易需要两个理由"）：
    - 多头：收盘在高点附近（close_position > 0.7），实体占比 > 50%，下影线 > 10%
    - 空头：收盘在低点附近（close_position < 0.3），实体占比 > 50%，上影线 > 10%

    附加过滤（原典要求）：
    - 棒线范围应与近期 ATR 相当（太小的棒不是有效信号棒）
    - 内包棒（inside bar）不是好的信号棒
    - 十字星（body_pct < 0.1）不是信号棒

    Args:
        bar: 待检测的棒线
        prev_bar: 前一根棒线（用于内包棒检测）
        atr: 近期 ATR 值（用于波动率过滤）

    Returns:
        {"type": "bull"|"bear"|"none", "quality": "strong"|"weak"|"none", "score": float}
    """
    body_pct = _bar_body_pct(bar)
    close_pos = _bar_close_position(bar)
    upper = _upper_shadow_pct(bar)
    lower = _lower_shadow_pct(bar)
    direction = _bar_direction(bar)

    # 基础过滤：十字星不是信号棒
    if body_pct < 0.1:
        return {"type": "none", "quality": "none", "score": 0.0}

    # 内包棒过滤（原典：inside bar 不是好的信号棒）
    if prev_bar:
        bar_h = float(bar.get("high", 0))
        bar_l = float(bar.get("low", 0))
        prev_h = float(prev_bar.get("high", 0))
        prev_l = float(prev_bar.get("low", 0))
        is_inside = bar_h <= prev_h and bar_l >= prev_l
        if is_inside:
            return {"type": "none", "quality": "none", "score": 0.0}

    # ATR 过滤：棒线范围太小不是有效信号棒
    bar_range = float(bar.get("high", 0)) - float(bar.get("low", 0))
    if atr > 0 and bar_range < atr * 0.3:
        return {"type": "none", "quality": "none", "score": 0.0}

    if direction == 1 and body_pct > 0.3:
        score = 0.0
        if close_pos > 0.7:
            score += 0.3
        if body_pct > 0.5:
            score += 0.3
        if lower > 0.1:
            score += 0.2
        if upper < 0.15:
            score += 0.2
        if score >= 0.6:
            return {"type": "bull", "quality": "strong", "score": round(score, 2)}
        if score >= 0.3:
            return {"type": "bull", "quality": "weak", "score": round(score, 2)}

    if direction == -1 and body_pct > 0.3:
        score = 0.0
        if close_pos < 0.3:
            score += 0.3
        if body_pct > 0.5:
            score += 0.3
        if upper > 0.1:
            score += 0.2
        if lower < 0.15:
            score += 0.2
        if score >= 0.6:
            return {"type": "bear", "quality": "strong", "score": round(score, 2)}
        if score >= 0.3:
            return {"type": "bear", "quality": "weak", "score": round(score, 2)}

    return {"type": "none", "quality": "none", "score": 0.0}


# ── Follow-through 确认 ─────────────────────────────────────────────────────

def check_follow_through(bars: list[dict], signal_idx: int, direction: str) -> dict[str, Any]:
    """检查信号棒后的 follow-through（坚持到底）。

    趋势篇 Ch4: "坚持到底运动是对初始运动的延伸"。
    确认条件：信号棒后 1-2 根棒的收盘在信号棒方向的极端。

    Args:
        bars: 完整的 5m 棒线列表
        signal_idx: 信号棒在 bars 中的索引
        direction: "bull" 或 "bear"

    Returns:
        {"confirmed": bool, "bars_confirmed": int, "detail": str}
    """
    if signal_idx < 0 or signal_idx >= len(bars) - 1:
        return {"confirmed": False, "bars_confirmed": 0, "detail": "信号棒后无足够棒线"}

    confirmed_count = 0
    for offset in range(1, min(3, len(bars) - signal_idx)):
        next_bar = bars[signal_idx + offset]
        next_close_pos = _bar_close_position(next_bar)
        next_dir = _bar_direction(next_bar)

        if direction == "bull":
            if next_close_pos > 0.6 and next_dir >= 0:
                confirmed_count += 1
        elif direction == "bear":
            if next_close_pos < 0.4 and next_dir <= 0:
                confirmed_count += 1

    confirmed = confirmed_count >= 1
    detail = f"{confirmed_count}/2根确认" if confirmed else "无确认"
    return {"confirmed": confirmed, "bars_confirmed": confirmed_count, "detail": detail}


# ── Always-In 方向判定 ──────────────────────────────────────────────────────

def determine_always_in(bars: list[dict], lookback: int = 20) -> dict[str, Any]:
    """判定 Always-In（总在场内）方向。

    趋势篇 Ch18: "如果你不得不一直在市场中，那么当前头寸就是你的 Always-In 头寸"。

    判定方法（贴近原典）：
    1. 趋势棒计数 + 连续性（最近 5 根是否呈趋势）
    2. 收盘价相对 EMA20 的位置
    3. 是否有 follow-through（突破后有确认棒）
    4. 是否在创更高的高点/更低的低点

    Returns:
        {"direction": "bull"|"bear"|"neutral", "score": float, "detail": str}
    """
    if len(bars) < lookback:
        return {"direction": "neutral", "score": 0.0, "detail": "数据不足"}

    recent = bars[-lookback:]

    # 1. 趋势棒计数
    bull_count = sum(1 for b in recent if _bar_direction(b) == 1)
    bear_count = sum(1 for b in recent if _bar_direction(b) == -1)
    total = len(recent)
    bull_ratio = bull_count / total
    bear_ratio = bear_count / total

    # 2. EMA20 位置
    closes = [float(b.get("close", 0)) for b in bars]
    ema20 = _ema(closes, 20)
    current_close = closes[-1] if closes else 0
    above_ema = current_close > ema20 if ema20 else None

    # 3. 最近 5 根的趋势连续性（原典强调 follow-through）
    recent5 = bars[-5:] if len(bars) >= 5 else bars
    recent5_dirs = [_bar_direction(b) for b in recent5]
    recent5_bull = sum(1 for d in recent5_dirs if d == 1)
    recent5_bear = sum(1 for d in recent5_dirs if d == -1)
    # 连续性：最近 3 根同向
    last3_dirs = recent5_dirs[-3:] if len(recent5_dirs) >= 3 else recent5_dirs
    consec_bull = sum(1 for d in last3_dirs if d == 1)
    consec_bear = sum(1 for d in last3_dirs if d == -1)

    # 4. 更高的高点/更低的低点（趋势延续信号）
    highs = [float(b.get("high", 0)) for b in recent]
    lows = [float(b.get("low", 0)) for b in recent]
    making_higher_highs = len(highs) >= 5 and highs[-1] > max(highs[-5:-1])
    making_lower_lows = len(lows) >= 5 and lows[-1] < min(lows[-5:-1])

    # 综合评分
    score = 0.0
    # 趋势棒占比
    if bull_ratio > 0.55:
        score += (bull_ratio - 0.5) * 2
    elif bear_ratio > 0.55:
        score -= (bear_ratio - 0.5) * 2

    # EMA 位置
    if above_ema is True:
        score += 0.15
    elif above_ema is False:
        score -= 0.15

    # 连续性（原典强调的 follow-through）
    if consec_bull >= 3:
        score += 0.15
    elif consec_bear >= 3:
        score -= 0.15

    # 更高的高点/更低的低点
    if making_higher_highs:
        score += 0.1
    if making_lower_lows:
        score -= 0.1

    if score > 0.2:
        detail = f"多头棒{bull_count}/{total}"
        if above_ema:
            detail += " 收盘>EMA"
        if consec_bull >= 3:
            detail += f" 连续{consec_bull}根"
        if making_higher_highs:
            detail += " 创新高"
        return {"direction": "bull", "score": round(score, 2), "detail": detail}
    if score < -0.2:
        detail = f"空头棒{bear_count}/{total}"
        if not above_ema:
            detail += " 收盘<EMA"
        if consec_bear >= 3:
            detail += f" 连续{consec_bear}根"
        if making_lower_lows:
            detail += " 创新低"
        return {"direction": "bear", "score": round(score, 2), "detail": detail}
    return {"direction": "neutral", "score": round(score, 2),
            "detail": f"多{bull_count}:空{bear_count} 未明确"}


# ── H/L 回调计数 ────────────────────────────────────────────────────────────

def count_pullbacks(bars: list[dict], direction: str) -> dict[str, Any]:
    """回调计数：H1/H2/H3 或 L1/L2/L3。

    区间篇 Ch17: "高点1是多头旗形中高点高于前一棒的棒线"。
    L1/L2/L3 用于多头趋势中的回调入场，H1/H2/H3 用于空头趋势。

    Returns:
        {"count": int, "type": "L1"|"L2"|"L3+"|"H1"|"H2"|"H3+"|"none",
         "last_pullback_price": float|None, "detail": str}
    """
    if len(bars) < 5:
        return {"count": 0, "type": "none", "last_pullback_price": None, "detail": "数据不足"}

    if direction == "bull":
        return _count_low_pullbacks(bars)
    elif direction == "bear":
        return _count_high_pullbacks(bars)
    return {"count": 0, "type": "none", "last_pullback_price": None, "detail": "方向不明"}


def _count_low_pullbacks(bars: list[dict]) -> dict[str, Any]:
    """多头趋势中的低点回调计数（L1/L2/L3）。"""
    lows = [(i, float(b.get("low", 0))) for i, b in enumerate(bars)]
    local_lows = []
    for i in range(1, len(lows) - 1):
        if lows[i][1] <= lows[i - 1][1] and lows[i][1] <= lows[i + 1][1]:
            local_lows.append(lows[i])

    if len(local_lows) < 2:
        last_low = float(bars[-1].get("low", 0))
        prev_low = float(bars[-2].get("low", 0)) if len(bars) >= 2 else 0
        if last_low > prev_low:
            return {"count": 1, "type": "L1", "last_pullback_price": last_low,
                    "detail": "1个更高低点"}
        return {"count": 0, "type": "none", "last_pullback_price": None, "detail": "低点不足"}

    count = 0
    last_price = None
    for i in range(1, len(local_lows)):
        if local_lows[i][1] > local_lows[i - 1][1]:
            count += 1
            last_price = local_lows[i][1]
        else:
            break

    if count == 0:
        last_low = float(bars[-1].get("low", 0))
        prev_low = float(bars[-2].get("low", 0)) if len(bars) >= 2 else 0
        if last_low > prev_low:
            count = 1
            last_price = last_low

    if count >= 3:
        label = "L3+"
    elif count >= 2:
        label = "L2"
    elif count >= 1:
        label = "L1"
    else:
        label = "none"

    return {
        "count": count,
        "type": label,
        "last_pullback_price": last_price,
        "detail": f"{count}个更高低点" if count > 0 else "无回调序列",
    }


def _count_high_pullbacks(bars: list[dict]) -> dict[str, Any]:
    """空头趋势中的高点回调计数（H1/H2/H3）。"""
    highs = [(i, float(b.get("high", 0))) for i, b in enumerate(bars)]
    local_highs = []
    for i in range(1, len(highs) - 1):
        if highs[i][1] >= highs[i - 1][1] and highs[i][1] >= highs[i + 1][1]:
            local_highs.append(highs[i])

    if len(local_highs) < 2:
        last_high = float(bars[-1].get("high", 0))
        prev_high = float(bars[-2].get("high", 0)) if len(bars) >= 2 else 0
        if last_high < prev_high:
            return {"count": 1, "type": "H1", "last_pullback_price": last_high,
                    "detail": "1个更低高点"}
        return {"count": 0, "type": "none", "last_pullback_price": None, "detail": "高点不足"}

    count = 0
    last_price = None
    for i in range(1, len(local_highs)):
        if local_highs[i][1] < local_highs[i - 1][1]:
            count += 1
            last_price = local_highs[i][1]
        else:
            break

    if count == 0:
        last_high = float(bars[-1].get("high", 0))
        prev_high = float(bars[-2].get("high", 0)) if len(bars) >= 2 else 0
        if last_high < prev_high:
            count = 1
            last_price = last_high

    if count >= 3:
        label = "H3+"
    elif count >= 2:
        label = "H2"
    elif count >= 1:
        label = "H1"
    else:
        label = "none"

    return {
        "count": count,
        "type": label,
        "last_pullback_price": last_price,
        "detail": f"{count}个更低高点" if count > 0 else "无回调序列",
    }


# ── 突破模式检测 ────────────────────────────────────────────────────────────

def detect_breakout_mode(bars: list[dict], lookback: int = 10) -> dict[str, Any]:
    """检测是否处于突破模式。

    区间篇 Ch1: "交易区间内就应该认为处于突破状态"。
    判定：最近 N 根棒形成紧凑交易区间（大量重叠）。

    Returns:
        {"is_breakout_mode": bool, "range_high": float, "range_low": float,
         "overlap_ratio": float, "detail": str}
    """
    if len(bars) < lookback:
        return {"is_breakout_mode": False, "range_high": 0, "range_low": 0,
                "overlap_ratio": 0, "detail": "数据不足"}

    recent = bars[-lookback:]
    highs = [float(b.get("high", 0)) for b in recent]
    lows = [float(b.get("low", 0)) for b in recent]
    range_high = max(highs)
    range_low = min(lows)
    range_size = range_high - range_low

    if range_size <= 0:
        return {"is_breakout_mode": True, "range_high": range_high, "range_low": range_low,
                "overlap_ratio": 1.0, "detail": "极紧凑区间"}

    overlap_count = 0
    for i in range(1, len(recent)):
        curr_h = float(recent[i].get("high", 0))
        curr_l = float(recent[i].get("low", 0))
        prev_h = float(recent[i - 1].get("high", 0))
        prev_l = float(recent[i - 1].get("low", 0))
        if curr_l < prev_h and curr_h > prev_l:
            overlap_count += 1

    overlap_ratio = overlap_count / (len(recent) - 1)
    avg_range = sum(h - l for h, l in zip(highs, lows)) / len(recent)
    is_narrow = range_size < avg_range * 3 if avg_range > 0 else False
    is_breakout = overlap_ratio > 0.6 and is_narrow

    return {
        "is_breakout_mode": is_breakout,
        "range_high": range_high,
        "range_low": range_low,
        "overlap_ratio": round(overlap_ratio, 2),
        "detail": f"重叠{overlap_ratio:.0%} 区间{range_size:.2f}" + (" → 突破模式" if is_breakout else ""),
    }


# ── 主入口 ──────────────────────────────────────────────────────────────────

def analyze_ab(
    bars_5m: list[dict],
    bars_15m: list[dict] | None = None,
    current_price: float = 0,
) -> dict[str, Any]:
    """Al Brooks 价格行为分析主入口。

    替换缠论作为 T0 三重共振第一席位。

    Returns:
        {
            "buy_signal": bool, "sell_signal": bool,
            "buy_reason": str, "sell_reason": str,
            "buy_price": float|None, "sell_price": float|None,
            "always_in": "bull"|"bear"|"neutral",
            "signal_bar_quality": "strong"|"weak"|"none",
            "hl_count": {"count": int, "type": str},
            "breakout_mode": bool,
            "details": dict,
        }
    """
    result: dict[str, Any] = {
        "buy_signal": False, "sell_signal": False,
        "buy_reason": "", "sell_reason": "",
        "buy_price": None, "sell_price": None,
        "always_in": "neutral",
        "signal_bar_quality": "none",
        "hl_count": {"count": 0, "type": "none"},
        "breakout_mode": False,
        "details": {},
    }

    if len(bars_5m) < 5:
        result["details"]["error"] = "5m数据不足"
        return result

    # 1. Always-In 方向
    ai = determine_always_in(bars_5m)
    result["always_in"] = ai["direction"]
    result["details"]["always_in"] = ai

    # 计算 ATR（用于信号棒过滤）
    atr = _calc_atr(bars_5m, period=14)

    # 2. 最后一根棒的信号棒检测（传入前一根棒和 ATR）
    last_bar = bars_5m[-1]
    prev_bar = bars_5m[-2] if len(bars_5m) >= 2 else None
    sig = detect_signal_bar(last_bar, prev_bar=prev_bar, atr=atr)
    result["signal_bar_quality"] = sig["quality"]
    result["details"]["signal_bar"] = sig

    # 3. Follow-through 确认
    ft = {"confirmed": False, "bars_confirmed": 0, "detail": "无信号棒"}
    if sig["type"] != "none" and len(bars_5m) >= 2:
        ft = check_follow_through(bars_5m, len(bars_5m) - 2, sig["type"])
    result["details"]["follow_through"] = ft

    # 4. H/L 回调计数
    hl = count_pullbacks(bars_5m, ai["direction"])
    result["hl_count"] = {"count": hl["count"], "type": hl["type"]}
    result["details"]["pullbacks"] = hl

    # 5. 突破模式
    bo = detect_breakout_mode(bars_5m)
    result["breakout_mode"] = bo["is_breakout_mode"]
    result["details"]["breakout_mode"] = bo

    # ── 综合信号判定 ──

    # 买入信号
    if ai["direction"] == "bull" and sig["type"] == "bull" and sig["quality"] in ("strong", "weak"):
        if ft["confirmed"] or sig["quality"] == "strong":
            result["buy_signal"] = True
            result["buy_reason"] = f"信号棒{sig['quality']}·{sig['type']}·{ft['detail']}"
            result["buy_price"] = float(last_bar.get("close", 0))
        elif hl["type"] in ("L2", "L3+"):
            result["buy_signal"] = True
            result["buy_reason"] = f"{hl['type']}回调·信号棒{sig['quality']}"
            result["buy_price"] = float(last_bar.get("close", 0))

    # 卖出信号
    if ai["direction"] == "bear" and sig["type"] == "bear" and sig["quality"] in ("strong", "weak"):
        if ft["confirmed"] or sig["quality"] == "strong":
            result["sell_signal"] = True
            result["sell_reason"] = f"信号棒{sig['quality']}·{sig['type']}·{ft['detail']}"
            result["sell_price"] = float(last_bar.get("close", 0))
        elif hl["type"] in ("H2", "H3+"):
            result["sell_signal"] = True
            result["sell_reason"] = f"{hl['type']}回调·信号棒{sig['quality']}"
            result["sell_price"] = float(last_bar.get("close", 0))

    # 补充：Always-In + 回调计数
    if not result["buy_signal"] and ai["direction"] == "bull" and hl["type"] in ("L2", "L3+"):
        result["buy_signal"] = True
        result["buy_reason"] = f"Always-In多头·{hl['type']}回调"
        result["buy_price"] = float(last_bar.get("close", 0))

    if not result["sell_signal"] and ai["direction"] == "bear" and hl["type"] in ("H2", "H3+"):
        result["sell_signal"] = True
        result["sell_reason"] = f"Always-In空头·{hl['type']}回调"
        result["sell_price"] = float(last_bar.get("close", 0))

    return result
