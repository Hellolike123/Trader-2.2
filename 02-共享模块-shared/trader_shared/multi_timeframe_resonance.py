"""多时间窗共振分析模块（11分制）。

基于周线定方向、日线定结构、60分钟定买点的三层共振理念，
提供 11 分制评分，用于选股池打分和输出展示。

评分维度：
  - 周线方向（3分）：周线趋势、支撑/阻力位置
  - 日线结构（3分）：日线 EXPMA 排列、动量状态
  - 60分钟买卖点（2分）：60分钟价格相对于关键位
  - 共振加分（3分）：多时间窗一致性

用法:
    from trader_shared.multi_timeframe_resonance import calc_resonance
    result = calc_resonance(daily_bars, weekly_bars, bars_60m, current_price)
"""

from __future__ import annotations

from typing import Any

from trader_shared.indicator_math import calc_expma as _calc_expma


def calc_resonance(
    daily_closes: list[float],
    current_price: float,
    weekly_bars: list[dict[str, Any]] | None = None,
    bars_60m: list[dict[str, Any]] | None = None,
    daily_support: float = 0,
    daily_resistance: float = 0,
) -> dict[str, Any]:
    """多时间窗共振分析（10分制）。

    Args:
        daily_closes: 日线收盘价序列（用于日线结构评分）
        current_price: 当前价格
        weekly_bars: 周线K线数据（可选）
        bars_60m: 60分钟K线数据（可选）
        daily_support: 日线支撑位（用于共振判断）
        daily_resistance: 日线阻力位（用于共振判断）

    Returns:
        {
            "total_score": int,        # 总分 0-10
            "weekly_score": int,       # 周线分 0-3
            "daily_score": int,        # 日线分 0-3
            "timming_score": int,      # 60min分 0-2
            "resonance_score": int,    # 共振分 0-2
            "weekly_label": str,       # 周线标签
            "daily_label": str,        # 日线标签
            "timing_label": str,       # 60min标签
            "resonance_label": str,    # 共振标签
            "detail": { ... },         # 详细解释
        }
    """
    if not daily_closes or len(daily_closes) < 10:
        return _empty_result()

    weekly = _score_weekly(weekly_bars, current_price, daily_closes)
    daily = _score_daily(daily_closes, current_price, daily_support, daily_resistance)
    timing = _score_timing_60m(bars_60m, current_price, daily_support, daily_resistance)
    resonance = _score_resonance(weekly, daily, timing)

    total = weekly.get("points", 0) + daily.get("points", 0) + timing.get("points", 0) + resonance

    resonance_label = _resonance_label(resonance, weekly, daily, timing)

    detail: dict[str, Any] = {
        "weekly_points": weekly,
        "daily_points": daily,
        "timing_points": timing,
        "resonance_points": resonance,
        "weekly_label": weekly.get("label", "未知"),
        "daily_label": daily.get("label", "未知"),
        "timing_label": timing.get("label", "未知"),
        "signals": _build_signals(weekly, daily, timing, resonance),
    }

    return {
        "total_score": total,
        "weekly_score": weekly.get("points", 0),
        "daily_score": daily.get("points", 0),
        "timing_score": timing.get("points", 0),
        "resonance_score": resonance,
        "weekly_label": weekly.get("label", "未知"),
        "daily_label": daily.get("label", "未知"),
        "timing_label": timing.get("label", "未知"),
        "resonance_label": resonance_label,
        "detail": detail,
    }


# ── 周线方向评分（3分） ──────────────────────────────────────────

def _score_weekly(
    weekly_bars: list[dict[str, Any]] | None,
    current_price: float,
    daily_closes: list[float],
) -> dict[str, Any]:
    """周线方向 0-3 分。

    评分因子：
      - 周线趋势（2分）：周线 EXPMA20 方向
      - 周线支撑（1分）：价格在周线支撑上方
    """
    score = 0
    label = "周线未知"

    # 优先用周线数据
    if weekly_bars and len(weekly_bars) >= 20:
        weekly_closes = [float(b.get("close", 0)) for b in weekly_bars if float(b.get("close", 0)) > 0]
        if weekly_closes:
            e20 = _calc_expma(weekly_closes, 20)
            e10 = _calc_expma(weekly_closes, 10) if len(weekly_closes) >= 10 else e20

            if e20 > 0:
                # 趋势判断
                if e10 and e20 and e10 > e20:
                    score += 2
                    label = "周线多头"
                elif e10 and e20 and e10 < e20:
                    label = "周线空头"
                else:
                    score += 1
                    label = "周线中性"

                # 支撑判断
                if current_price > e20:
                    score += 1
                    label = f"{label}（站上EXPMA20）"
    else:
        # 用日线最后20根作为周线代理（大约4周数据）
        if len(daily_closes) >= 20:
            e20 = _calc_expma(daily_closes, 20)
            e10 = _calc_expma(daily_closes, 10) if len(daily_closes) >= 10 else e20
            if e20 > 0:
                if e10 and e10 > e20:
                    score += 1
                    label = "日线代理多头"
                elif e10 and e10 < e20:
                    label = "日线代理空头"
                else:
                    label = "日线代理中性"

                if current_price > e20:
                    score += 1
                    label = f"{label}（站上）"

    # 至少1分基础分（有数据时）
    if not weekly_bars or len(weekly_bars) < 5:
        score = max(score, 0)
        # 如果已经有日线代理评分，保留并添加注释
        if score > 0 and label and label != "无周线数据":
            label = f"{label}（无周线数据）"
        else:
            label = "无周线数据"

    return {"points": min(3, score), "label": label}


# ── 日线结构评分（3分） ─────────────────────────────────────────

def _score_daily(
    daily_closes: list[float],
    current_price: float,
    daily_support: float,
    daily_resistance: float,
) -> dict[str, Any]:
    """日线结构 0-3 分。

    评分因子：
      - 日线 EXPMA 排列（2分）：多头/空头/交叉
      - 位置（1分）：在支撑和阻力之间的位置
    """
    score = 0
    label = "日线未知"

    if not daily_closes or len(daily_closes) < 10:
        return {"points": 0, "label": "数据不足"}

    e10 = _calc_expma(daily_closes, 10) if len(daily_closes) >= 10 else 0
    e20 = _calc_expma(daily_closes, 20) if len(daily_closes) >= 20 else 0
    e50 = _calc_expma(daily_closes, 50) if len(daily_closes) >= 50 else 0

    # EXPMA 排列（2分）
    if e10 and e20:
        if e10 > e20:
            score += 1
            if e50 and e20 > e50:
                score += 1
                label = "日线多头排列"
            else:
                label = "日线偏多"
        else:
            if e50 and e20 < e50:
                label = "日线空头排列"
            else:
                label = "日线偏空"

    # 位置（1分）
    if daily_support > 0 and daily_resistance > 0:
        range_size = daily_resistance - daily_support
        if range_size > 0:
            position = (current_price - daily_support) / range_size
            if 0.3 <= position <= 0.7:
                score += 1  # 在中间偏下，安全区间
                label = f"{label}（安全位）"
            elif position < 0.3:
                label = f"{label}（低位）"
            # 高位不给分（风险区）
    elif daily_support > 0 and current_price > daily_support:
        score += 1  # 在支撑上方
        label = f"{label}（支撑上）"

    return {"points": min(3, score), "label": label}


# ── 60分钟买卖点评分（2分） ─────────────────────────────────────

def _score_timing_60m(
    bars_60m: list[dict[str, Any]] | None,
    current_price: float,
    daily_support: float,
    daily_resistance: float,
) -> dict[str, Any]:
    """60分钟买卖点 0-2 分。

    评分因子：
      - 在支撑位附近（1分）：60分钟显示回调到位
      - 60分钟趋势向好（1分）：60分钟价格相对自身趋势
    """
    score = 0
    label = "60min未知"

    if not bars_60m or len(bars_60m) < 10:
        return {"points": 0, "label": "无60分钟数据"}

    # 60分钟价格相对日线支撑位
    if daily_support > 0 and abs(current_price - daily_support) / daily_support <= 0.03:
        score += 1  # 接近日线支撑位，好的买点
        label = "60min回调到位"

    # 60分钟趋势
    closes_60m = [float(b.get("close", 0)) for b in bars_60m if float(b.get("close", 0)) > 0]
    if len(closes_60m) >= 10:
        e10_60 = _calc_expma(closes_60m, 10)
        if e10_60 and current_price > e10_60:
            score += 1
            label = f"{label}（60min站上EXPMA10）" if score > 0 else "60min偏多（站上EXPMA10）"

    return {"points": min(2, score), "label": label}


# ── 共振加分（2分） ─────────────────────────────────────────────

def _score_resonance(weekly: dict, daily: dict, timing: dict) -> int:
    """共振加分 0-3 分。

    当多个时间窗方向一致时加分：
      - 周线+日线同向：1分
      - 三窗同向：2分
      - 60分钟强势共振：3分
    """
    score = 0

    # 判断各窗方向
    weekly_bullish = "多头" in weekly.get("label", "")
    weekly_bearish = "空头" in weekly.get("label", "")
    daily_bullish = "多头" in daily.get("label", "") or "偏多" in daily.get("label", "")
    daily_bearish = "空头" in daily.get("label", "") or "偏空" in daily.get("label", "")
    timing_positive = timing.get("points", 0) >= 1
    timing_strong = timing.get("points", 0) >= 2

    # 周线+日线同向
    if (weekly_bullish and daily_bullish) or (weekly_bearish and daily_bearish):
        score += 1
        if timing_positive:
            score += 1  # 三窗同向
            if timing_strong:
                score += 1  # 60分钟强势共振
    elif weekly_bullish or daily_bullish:
        # 至少一个偏多，给半分
        if timing_positive:
            score += 1

    return min(3, score)


# ── 共振标签 ─────────────────────────────────────────────────────

def _resonance_label(resonance: int, weekly: dict = None, daily: dict = None, timing: dict = None) -> str:
    """共振等级标签。"""
    if resonance >= 3:
        return "三窗强势共振"
    elif resonance >= 2:
        return "多窗共振（较强）"
    elif resonance >= 1:
        return "部分共振"
    else:
        return "无共振（分歧）"


# ── 信号聚合 ─────────────────────────────────────────────────────

def _build_signals(weekly: dict, daily: dict, timing: dict, resonance: int) -> list[str]:
    """聚合关键信号。"""
    signals: list[str] = []

    w_label = weekly.get("label", "")
    d_label = daily.get("label", "")
    t_label = timing.get("label", "")

    if w_label and "多头" in w_label:
        signals.append(f"周线{w_label}")
    if d_label and "多头" in d_label:
        signals.append(f"日线{d_label}")
    if t_label and "回调到位" in t_label:
        signals.append(f"60min{t_label}")

    return signals



def _empty_result() -> dict[str, Any]:
    """返回空结果。"""
    return {
        "total_score": 0, "weekly_score": 0, "daily_score": 0,
        "timing_score": 0, "resonance_score": 0,
        "weekly_label": "无数据", "daily_label": "无数据",
        "timing_label": "无数据", "resonance_label": "无数据",
        "detail": {},
    }
