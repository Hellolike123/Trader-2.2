"""VWAP (成交量加权均价) indicator plugin — 展示型，不进融合层。

计算当日机构成本线（VWAP）及偏离度，仅用于报告展示（主力成本段落）。
依赖当日 5 分钟 K 线；由 build_report 通过 quote["_bars_5m"] 注入快照数据，
避免每次渲染重拉行情（呼应性能优化约定）。
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import IndicatorPlugin
from trader_shared.indicator_math import calc_vwap


class VwapPlugin(IndicatorPlugin):
    """VWAP analysis plugin — intraday institutional cost line (display only)."""

    def name(self) -> str:
        return "vwap"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
    ) -> dict[str, Any]:
        # 5 分钟 K 线由 build_report 注入（quote["_bars_5m"]），不在此重拉行情
        bars_5m = (quote or {}).get("_bars_5m") or []
        v = calc_vwap(bars_5m, current_price=current)
        return {
            "vwap": v["vwap"],
            "vwap_dev": v["deviation_pct"],
            "vwap_position": v["position"],
            "level": v["level"],
            "display_only": True,
        }

    def weight(self) -> float:
        return 0.0  # 不参与融合加权
