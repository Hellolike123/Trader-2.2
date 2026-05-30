"""四阶段定位模型（Stage Positioning Model）

两层嵌套：
  第一层：大阶段（蓄势/主升/派发/衰退）→ 基于 MA 关系 + 价格位置
  第二层：短期动能（走强/修复/震荡/转弱）→ 基于 MA5/MA10 + change_pct

组合决策矩阵输出仓位建议和操作方向。

用法:
    from stage_positioning import assess_stage
    result = assess_stage(current, ma_values, change_pct, bars)
"""

from __future__ import annotations

from typing import Any


# ── 大阶段判定 ──────────────────────────────────────────────

def _detect_major_stage(
    current: float,
    ma5: float | None,
    ma10: float | None,
    ma20: float | None,
    ma30: float | None,
    ma250: float | None,
    bars: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """判定大阶段：蓄势/主升/派发/衰退

    Returns:
        (stage, reason)
    """
    if ma250 is None or ma250 <= 0:
        return "蓄势", "数据不足，默认蓄势"

    # 价格相对 MA250 的位置
    above_250 = current > ma250
    distance_250 = (current - ma250) / ma250

    # 均线排列
    has_ma = [v is not None and v > 0 for v in [ma5, ma10, ma20, ma30]]
    if not all(has_ma):
        return "蓄势", "均线数据不足"

    # 多头排列: ma5 > ma10 > ma20 > ma30
    bullish_align = ma5 > ma10 > ma20 > ma30
    # 空头排列: ma5 < ma10 < ma20 < ma30
    bearish_align = ma5 < ma10 < ma20 < ma30

    # MA20 和 MA60 的关系（用 MA30 近似 MA60）
    ma20_above_ma30 = ma20 > ma30

    # 收敛判断：MA20 和 MA30 接近
    if ma30 > 0:
        convergence = abs(ma20 - ma30) / ma30
    else:
        convergence = 1.0

    # 主升：多头排列 + 价格在 MA20 上方 + 在 250 日线上方
    if bullish_align and current > ma20 and above_250:
        return "主升", "均线多头排列，价格在年线上方"

    # 衰退：空头排列 + 价格在 250 日线下方
    if bearish_align and not above_250:
        return "衰退", "均线空头排列，价格在年线下方"

    # 派发：曾经多头但现在走弱（MA5 开始下穿 MA10，或价格跌破 MA20）
    if ma20_above_ma30 and current < ma20 and above_250:
        return "派发", "价格跌破MA20但仍在年线上方"

    # 蓄势：均线收敛 + 价格在 MA250 附近
    if convergence < 0.05 and abs(distance_250) < 0.10:
        return "蓄势", "均线收敛，方向不明确"

    # 默认：根据 250 日线位置
    if above_250:
        if ma20_above_ma30:
            return "主升", "价格在年线上方，MA20>MA30"
        return "蓄势", "价格在年线上方但均线未确认"
    else:
        if bearish_align:
            return "衰退", "均线空头排列"
        return "蓄势", "价格在年线下方但未完全走坏"


# ── 短期动能判定 ──────────────────────────────────────────────

def _detect_short_term_momentum(
    current: float,
    ma5: float | None,
    ma10: float | None,
    change_pct: float,
    position_ratio: float,
) -> tuple[str, str]:
    """判定短期动能：走强/修复/震荡/转弱

    Returns:
        (momentum, reason)
    """
    if ma5 is None or ma10 is None:
        return "震荡", "均线数据不足"

    above_ma5 = current >= ma5
    above_ma10 = current >= ma10
    ma5_above_ma10 = ma5 > ma10

    # 走强：站上MA5且MA5>MA10 + 涨幅>1%
    if above_ma5 and ma5_above_ma10 and change_pct > 1.0:
        return "走强", "站上MA5且放量上涨"

    # 走强：站上MA5且MA5>MA10 + position_ratio高
    if above_ma5 and ma5_above_ma10 and position_ratio >= 0.60:
        return "走强", "站上MA5且接近确认区"

    # 修复：站上MA5但MA5还没上穿MA10
    if above_ma5 and not ma5_above_ma10:
        return "修复", "站上MA5但均线未确认"

    # 修复：在MA10附近（上下2%）
    if abs(current - ma10) / ma10 < 0.02:
        return "修复", "在MA10附近震荡"

    # 转弱：跌破MA5且MA5<MA10
    if not above_ma5 and not ma5_above_ma10:
        if change_pct < -2.0:
            return "转弱", "跌破MA5且放量下跌"
        return "转弱", "跌破MA5且均线死叉"

    # 跌破MA5但MA5还在MA10上方
    if not above_ma5 and ma5_above_ma10:
        return "震荡", "跌破MA5但均线未死叉"

    return "震荡", "无明确方向"


# ── 组合决策矩阵 ──────────────────────────────────────────────

_DECISION_MATRIX: dict[str, dict[str, tuple[str, int]]] = {
    # (stage, momentum) → (action, max_position_pct)
    "蓄势": {
        "走强": ("试探买", 10),
        "修复": ("观察", 0),
        "震荡": ("等待", 0),
        "转弱": ("不碰", 0),
    },
    "主升": {
        "走强": ("加仓", 70),
        "修复": ("持有", 50),
        "震荡": ("持有", 50),
        "转弱": ("减仓", 30),
    },
    "派发": {
        "走强": ("减仓", 30),
        "修复": ("减仓", 20),
        "震荡": ("减仓", 20),
        "转弱": ("清仓", 0),
    },
    "衰退": {
        "走强": ("不碰", 0),
        "修复": ("不碰", 0),
        "震荡": ("不碰", 0),
        "转弱": ("不碰", 0),
    },
}


def assess_stage(
    current: float,
    ma_values: dict[str, float | None],
    change_pct: float,
    bars: list[dict[str, Any]] | None = None,
    position_ratio: float = 0.5,
) -> dict[str, Any]:
    """四阶段定位主函数

    Returns:
        {
            "major_stage": str,       # 蓄势/主升/派发/衰退
            "major_reason": str,
            "momentum": str,          # 走强/修复/震荡/转弱
            "momentum_reason": str,
            "action": str,            # 操作建议
            "max_position_pct": int,  # 最大仓位百分比
            "stage_label": str,       # "蓄势期 + 修复"
        }
    """
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")
    ma20 = ma_values.get("ma20")
    ma30 = ma_values.get("ma30")
    ma250 = ma_values.get("ma250")

    major_stage, major_reason = _detect_major_stage(
        current, ma5, ma10, ma20, ma30, ma250, bars
    )

    momentum, momentum_reason = _detect_short_term_momentum(
        current, ma5, ma10, change_pct, position_ratio
    )

    action, max_position = _DECISION_MATRIX.get(major_stage, {}).get(
        momentum, ("观察", 0)
    )

    stage_label = f"{major_stage}期 + {momentum}"

    return {
        "major_stage": major_stage,
        "major_reason": major_reason,
        "momentum": momentum,
        "momentum_reason": momentum_reason,
        "action": action,
        "max_position_pct": max_position,
        "stage_label": stage_label,
    }
