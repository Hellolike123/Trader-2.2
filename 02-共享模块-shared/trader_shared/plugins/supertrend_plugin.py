"""Supertrend (超级趋势) indicator plugin — 展示型，不进融合层。

仅用于报告展示（趋势带方向 / ATR / 波动率级别），不作为独立融合信号。
方向可被动量插件消费做「只确认不否决」微调（见 momentum_plugin）。
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin
from trader_shared.indicator_math import calc_supertrend


class SupertrendPlugin(IndicatorPlugin):
    """Supertrend analysis plugin — trend band direction (display only)."""

    def name(self) -> str:
        return "supertrend"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
    ) -> dict[str, Any]:
        st = calc_supertrend(bars)
        direction = st["direction"]
        direction_cn = "多头" if direction == "up" else ("空头" if direction == "down" else "中性")
        reason = (
            f"Supertrend {direction_cn}，轨道 {st['stop_long']:.2f}"
            if st["stop_long"] is not None
            else f"Supertrend {direction_cn}"
        )
        return {
            "direction": 1 if direction == "up" else (-1 if direction == "down" else 0),
            "confidence": 0.0,  # 展示型，不进融合
            "reason": reason,
            "stop_long": st["stop_long"],
            "stop_short": st["stop_short"],
            "atr": st["atr"],
            "atr_pct": st["atr_pct"],
            "vol_level": st["vol_level"],
            "display_only": True,
        }

    def weight(self) -> float:
        return 0.0  # 不参与融合加权
