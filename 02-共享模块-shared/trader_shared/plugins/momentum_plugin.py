"""Momentum (动量) indicator plugin.

Wraps momentum_core.py momentum_strategy() behind the IndicatorPlugin interface.

Also applies a "Supertrend confirmation" nudge (方案 B): when the Supertrend
trend-band direction agrees with momentum's direction, momentum's score is
slightly boosted (confirmation only — disagreement is NOT punished, to avoid
killing good accumulation/吸筹 entries during healthy pullbacks).
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin

# 与 Supertrend 同向时，动量分数上限提升（0-100 量表，等价于置信度 +0.08 量级）
SUPERTREND_CONFIRM_BOOST = 8


def _dir_to_sign(direction) -> int:
    """归一化方向为 +1 / -1 / 0。"""
    if direction in ("up", "bullish", 1, 1.0):
        return 1
    if direction in ("down", "bearish", -1, -1.0):
        return -1
    return 0


def _remap_direction_from_score(score: float | None) -> str:
    """与 assess_momentum 阈值一致：≥65 bullish / ≤35 bearish / 其余 neutral。"""
    if score is None:
        return "insufficient"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "neutral"
    if s >= 65:
        return "bullish"
    if s <= 35:
        return "bearish"
    return "neutral"


def apply_supertrend_nudge(
    momentum_result: dict[str, Any],
    supertrend_direction: str | None,
) -> dict[str, Any]:
    """对动量结果做「只确认不否决」微调。

    - Supertrend 与动量同向看多 → score +BOOST（封顶 100）
    - Supertrend 与动量同向看空 → score -BOOST（触底 0）——旧逻辑误用 +BOOST 会把空头推向中性
    - 动量中性但分数已偏多/偏空（≥55 / ≤45）且 ST 同向 → 同样确认增强，便于跨 65/35 阈值
    - 方向相反 → 不变（不惩罚）
    - insufficient / score=None → 不动
    - 改分后**重映射 direction**，否则 fusion 仍按旧 direction=0 使加权贡献恒为 0

    Args:
        momentum_result: momentum_strategy() 的返回（含 "momentum" 子字典）
        supertrend_direction: "up" | "down" | None

    Returns:
        微调后的 momentum_result（原地修改 score/direction）
    """
    if supertrend_direction is None or not isinstance(momentum_result, dict):
        return momentum_result
    mom = momentum_result.get("momentum")
    if not isinstance(mom, dict):
        return momentum_result
    if mom.get("direction") == "insufficient" or mom.get("score") is None:
        return momentum_result

    st_sign = _dir_to_sign(supertrend_direction)
    mom_sign = _dir_to_sign(mom.get("direction"))
    try:
        score = float(mom.get("score"))
    except (TypeError, ValueError):
        return momentum_result

    delta = 0
    # 同向确认
    if st_sign != 0 and st_sign == mom_sign:
        delta = SUPERTREND_CONFIRM_BOOST if st_sign > 0 else -SUPERTREND_CONFIRM_BOOST
    # 近阈值中性：ST 向上且分数已偏多 / ST 向下且分数已偏空
    elif st_sign > 0 and mom_sign == 0 and score >= 55:
        delta = SUPERTREND_CONFIRM_BOOST
    elif st_sign < 0 and mom_sign == 0 and score <= 45:
        delta = -SUPERTREND_CONFIRM_BOOST

    if delta == 0:
        return momentum_result

    new_score = max(0.0, min(100.0, score + delta))
    mom["score"] = new_score
    mom["direction"] = _remap_direction_from_score(new_score)
    mom["supertrend_nudge"] = delta
    return momentum_result


class MomentumPlugin(IndicatorPlugin):
    """Momentum analysis plugin — RSI, MACD, ADX, Bollinger Bands."""

    def name(self) -> str:
        return "momentum"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
        supertrend_direction: str | None = None,
        weekly_bars: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from trader_shared.momentum_core import momentum_strategy
        result = momentum_strategy(current, bars, change_pct, quote)
        return apply_supertrend_nudge(result, supertrend_direction)

    def weight(self) -> float:
        # 名义权重；merge_decisions 实际用 regime/场景矩阵（正常约 0.30）
        return 0.30
