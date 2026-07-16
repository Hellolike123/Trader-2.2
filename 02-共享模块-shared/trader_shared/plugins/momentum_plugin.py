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


def apply_supertrend_nudge(
    momentum_result: dict[str, Any],
    supertrend_direction: str | None,
) -> dict[str, Any]:
    """对动量结果做「只确认不否决」微调。

    - supertrend_direction 与动量方向相同（同为正或同为负）→ 分数 +SUPERTREND_CONFIRM_BOOST（封顶 100）
    - 方向相反 → 不变（不惩罚）
    - supertrend_direction 为 None 或动量中性 → 不变（向后兼容）

    Args:
        momentum_result: momentum_strategy() 的返回（含 "momentum" 子字典）
        supertrend_direction: "up" | "down" | None

    Returns:
        微调后的 momentum_result（原地修改 score，便于下游融合消费）
    """
    if supertrend_direction is None or not isinstance(momentum_result, dict):
        return momentum_result
    mom = momentum_result.get("momentum")
    if not isinstance(mom, dict):
        return momentum_result

    st_sign = _dir_to_sign(supertrend_direction)
    mom_sign = _dir_to_sign(mom.get("direction"))
    # 仅当两者同向（均非零）时确认增强；反向或任一中性都不动
    if st_sign != 0 and st_sign == mom_sign:
        _raw_score = mom.get("score")
        score = float(_raw_score) if isinstance(_raw_score, (int, float)) else 50.0
        mom["score"] = min(100.0, score + SUPERTREND_CONFIRM_BOOST)
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
        return 0.20  # Default weight in fusion (matches existing momentum weight)
