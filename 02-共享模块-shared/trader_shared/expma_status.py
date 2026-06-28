"""EXPMA 详细状态评估模块（10分制）。

在已有基础 EXPMA 计算之上，提供细粒度的 10 分制评分，
用于选股池打分和输出展示。

评分维度：
  - 均线排列（3分）：多周期 EXPMA 排列状态
  - 斜率方向（2分）：中期 EXPMA 斜率
  - 交叉信号（2分）：近 N 日内的金叉/死叉
  - 乖离程度（3分）：价格与中期 EXPMA 的偏离度

用法:
    from trader_shared.expma_status import calc_expma_status
    result = calc_expma_status(closes, current_price, bars)
"""

from __future__ import annotations

from typing import Any

from trader_shared.indicator_math import calc_expma as _calc_expma, calc_expma_series as _calc_expma_series


def calc_expma_status(
    closes: list[float],
    current_price: float,
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """EXPMA 详细状态评估（10分制）。

    Args:
        closes: 收盘价序列（按时间升序）
        current_price: 当前价格
        bars: K线数据（用于斜率计算，可选）

    Returns:
        {
            "total_score": int,        # 总分 0-10
            "alignment_score": int,    # 排列分 0-3
            "slope_score": int,        # 斜率分 0-2
            "cross_score": int,        # 交叉分 0-2
            "deviation_score": int,    # 乖离分 0-3
            "expma_values": dict,      # 各周期 EXPMA 值
            "trend_label": str,        # 中文趋势标签
            "detail": { ... },         # 详细解释
        }
    """
    if not closes or len(closes) < 10:
        return {
            "total_score": 0, "alignment_score": 0, "slope_score": 0,
            "cross_score": 0, "deviation_score": 0,
            "expma_values": {}, "trend_label": "数据不足", "detail": {},
        }

    # 计算各周期 EXPMA（使用完整历史数据，避免退化为SMA）
    expma_values: dict[str, float | None] = {}
    periods = [5, 10, 12, 20, 30, 50]
    for p in periods:
        if len(closes) >= p:
            expma_values[str(p)] = _calc_expma(closes, p)
        else:
            expma_values[str(p)] = None

    # 各维度评分
    alignment = _score_alignment(expma_values)
    slope = _score_slope(expma_values, bars)
    cross = _score_crossover(closes, expma_values)
    deviation = _score_deviation(current_price, expma_values)
    total = alignment + slope + cross + deviation

    # 趋势标签
    trend_label = _trend_label(expma_values, alignment, slope, current_price=current_price)

    # 详细解释
    detail: dict[str, Any] = {
        "expma5": expma_values.get("5"),
        "expma10": expma_values.get("10"),
        "expma20": expma_values.get("20"),
        "expma30": expma_values.get("30"),
        "expma50": expma_values.get("50"),
        "alignment_points": alignment,
        "slope_points": slope,
        "cross_points": cross,
        "deviation_points": deviation,
        "signals": _build_signals(expma_values, current_price, slope, cross, deviation),
    }

    return {
        "total_score": total,
        "alignment_score": alignment,
        "slope_score": slope,
        "cross_score": cross,
        "deviation_score": deviation,
        "expma_values": expma_values,
        "trend_label": trend_label,
        "detail": detail,
    }


# ── 均线排列评分（3分） ──────────────────────────────────────────

def _score_alignment(expma_values: dict[str, float | None]) -> int:
    """均线排列 0-3 分。

    评分因子：
      - 3周期以上多头排列：3分
      - 2周期多头：2分
      - 空头排列：0分
      - 交叉：1分
    """
    e10 = expma_values.get("10")
    e20 = expma_values.get("20")
    e30 = expma_values.get("30")

    if e10 is not None and e20 is not None and e30 is not None and e10 > 0 and e20 > 0 and e30 > 0:
        if e10 > e20 > e30:
            return 3
        elif e10 < e20 < e30:
            return 0
        else:
            return 1
    elif e10 is not None and e20 is not None and e10 > 0 and e20 > 0:
        if e10 > e20:
            return 2
        else:
            return 0
    elif e10 is not None and e10 > 0:
        return 1

    return 0


# ── 斜率评分（2分） ──────────────────────────────────────────────

def _score_slope(expma_values: dict[str, float | None],
                 bars: list[dict[str, Any]] | None) -> int:
    """斜率方向 0-2 分。

    评分因子：
      - EXPMA20 斜率向上（近5日上升>1%）：2分
      - EXPMA20 斜率平稳（近5日变化±1%）：1分
      - EXPMA20 斜率向下：0分
    """
    e20 = expma_values.get("20")
    if e20 is not None and bars and len(bars) >= 6:
        # 计算5日前的EXPMA20（用当时的收盘价计算）
        closes_5d_ago = [float(b.get("close") or 0) for b in bars[:-5] if float(b.get("close") or 0) > 0]
        if len(closes_5d_ago) >= 20:
            e20_prev = _calc_expma(closes_5d_ago, 20)
            if e20_prev is not None and e20_prev > 0:
                change_pct = (e20 - e20_prev) / e20_prev
                if change_pct > 0.01:
                    return 2
                elif change_pct > -0.01:
                    return 1
                else:
                    return 0

    # 无 bars 数据时，用 EXPMA20 vs EXPMA30 作为斜率代理
    e30 = expma_values.get("30")
    if e20 and e30:
        if e20 > e30:
            return 1  # 至少平稳
        return 0

    return 1  # 无数据时中性


# ── 交叉信号评分（2分） ─────────────────────────────────────────

def _score_crossover(closes: list[float], expma_values: dict[str, float | None]) -> int:
    """交叉信号 0-2 分。

    评分因子：
      - 近5日内金叉（EXPMA10 从下穿上 EXPMA20）：2分
      - 近5日内死叉：0分
      - 无交叉：1分
    """
    if len(closes) < 20:
        return 1

    # 计算近5日的EXPMA10和EXPMA20值（基于到当天为止的完整数据）
    golden = 0
    death = 0
    
    # 检查近5日是否有交叉
    for i in range(1, min(6, len(closes))):
        # 计算到第i天为止的EXPMA10和EXPMA20
        closes_to_day_i = closes[:-i] if i > 0 else closes
        if len(closes_to_day_i) < 20:
            continue
            
        expma10 = _calc_expma(closes_to_day_i, 10)
        expma20 = _calc_expma(closes_to_day_i, 20)
        
        # 计算到第i-1天为止的EXPMA10和EXPMA20
        closes_to_day_prev = closes[:-i+1] if i > 1 else closes
        if len(closes_to_day_prev) < 20:
            continue
            
        expma10_prev = _calc_expma(closes_to_day_prev, 10)
        expma20_prev = _calc_expma(closes_to_day_prev, 20)
        
        # 检查金叉：EXPMA10从下穿上EXPMA20
        # 注意：expma10_prev 是更新的数据，expma10 是更旧的数据
        if expma10_prev >= expma20_prev and expma10 < expma20:
            golden += 1
        # 检查死叉：EXPMA10从上穿下EXPMA20
        elif expma10_prev <= expma20_prev and expma10 > expma20:
            death += 1

    if golden > 0:
        return 2
    if death > 0:
        return 0
    return 1


# ── 乖离率评分（3分） ────────────────────────────────────────────

def _score_deviation(current_price: float, expma_values: dict[str, float | None]) -> int:
    """乖离程度 0-3 分。

    评分因子（以 EXPMA5 为参照，更快捕捉短期变化）：
      - 价格适中高于 EXPMA5（0-3%）：3分（最佳低吸/持有位）
      - 价格适中低于 EXPMA5（0-3%）：2分
      - 价格略超买（3-5%）：1分
      - 价格略超卖（-3% ~ -5%）：1分
      - 价格极端超买（>5%）：0分
      - 价格极端超卖（<-5%）：0分
    """
    e5 = expma_values.get("5")
    e20 = expma_values.get("20")
    # 优先用 EXPMA5（更灵敏），无数据时回退 EXPMA20
    ref = e5 if (e5 and e5 > 0) else e20
    if not ref or current_price <= 0 or ref <= 0:
        return 1  # 无数据中性

    deviation_pct = (current_price - ref) / ref

    if 0 <= deviation_pct <= 0.03:
        return 3  # 最佳位
    elif -0.03 <= deviation_pct < 0:
        return 2  # 略低
    elif 0.03 < deviation_pct <= 0.05:
        return 1  # 略超买
    elif -0.05 <= deviation_pct < -0.03:
        return 1  # 略超卖
    elif deviation_pct > 0.05:
        return 0  # 极端超买
    else:
        return 0  # 极端超卖（dev < -0.05）


# ── 趋势标签 ─────────────────────────────────────────────────────

def _trend_label(expma_values: dict[str, float | None],
                 alignment: int, slope: int, current_price: float = 0) -> str:
    """综合排列和斜率得出趋势标签，增加现价 vs EXPMA5 维度。"""
    e5 = expma_values.get("5")
    e10 = expma_values.get("10")

    if alignment >= 3 and slope >= 2:
        # 多头排列，但需检查现价是否在 EXPMA5 上方
        if e5 and current_price > 0 and current_price < e5:
            if e10 and e5 > e10:
                return "多头排列（回调）"
            else:
                return "多头排列失效"
        return "多头排列（强势）"
    elif alignment >= 2 and slope >= 1:
        if e5 and current_price > 0 and current_price < e5:
            return "偏多排列（回调）"
        return "偏多排列"
    elif alignment <= 0 and slope <= 0:
        return "空头排列（弱势）"
    elif alignment <= 1 and slope <= 0:
        return "偏空排列"
    else:
        return "交叉震荡"


# ── 信号聚合 ─────────────────────────────────────────────────────

def _build_signals(
    expma_values: dict[str, float | None],
    current_price: float,
    slope: int,
    cross: int,
    deviation: int,
) -> list[str]:
    """聚合关键信号。"""
    signals: list[str] = []

    e10 = expma_values.get("10")
    e20 = expma_values.get("20")
    e30 = expma_values.get("30")
    e50 = expma_values.get("50")

    # 排列信号
    if e10 and e20 and e30 and e10 > e20 > e30:
        signals.append("EXPMA10>20>30 多头排列")
    elif e10 and e20 and e30 and e10 < e20 < e30:
        signals.append("EXPMA10<20<30 空头排列")

    # 斜率信号
    if slope >= 2:
        signals.append("EXPMA20 斜率向上")
    elif slope <= 0:
        signals.append("EXPMA20 斜率向下")

    # 交叉信号
    if cross >= 2:
        signals.append("近5日金叉")
    elif cross <= 0:
        signals.append("近5日死叉")

    # 乖离信号（使用 EXPMA5 作为参考，与 _score_deviation 一致）
    e5 = expma_values.get("5")
    if e5 and current_price > 0:
        dev = (current_price - e5) / e5
        if dev > 0.05:
            signals.append(f"超买（乖离+{dev*100:.1f}%）")
        elif dev < -0.05:
            signals.append(f"超卖（乖离{dev*100:.1f}%）")

    return signals
