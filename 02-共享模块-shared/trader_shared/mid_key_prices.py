"""中线关键价地图 — 薄封装。

主路径：周线引擎 trader_shared.midline_structure（weekly_v1）。
规格：docs/midline-price-engine-plan.md（含 §9）。
成功路径禁止 daily_key_levels_proxy；日线 key_levels/stop 默认忽略。
"""
from __future__ import annotations

from typing import Any

from trader_shared.midline_structure import (
    _daily_fallback_enabled,
    build_degraded_daily_key_levels,
    build_midline_levels,
)


def build_mid_key_prices(
    *,
    current: float | None = None,
    weekly_bars: list[Any] | None = None,
    chanlun_midline: dict[str, Any] | None = None,
    wyckoff_midline: dict[str, Any] | None = None,
    ma_weekly: dict[str, Any] | None = None,
    # 旧参默认忽略；仅 MIDLINE_PRICE_DAILY_FALLBACK=true 时 degraded
    key_levels: dict[str, Any] | None = None,
    ma20: float | None = None,
    stop: float | None = None,
    stop_losses: dict[str, Any] | None = None,
    stage_stop_price: float | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """构建中线关键价：生命线 / 回踩区 / 压力 / 目标 + 固定解释句。

    主参：current, weekly_bars, chanlun_midline[, wyckoff_midline]。
    key_levels/stop/stop_losses 默认不参与填价。
    """
    # 显式降级：仅开关开且无足够周线时，或调用方只给了 daily 且开关开
    if _daily_fallback_enabled():
        bars = weekly_bars or []
        # 有足够周线仍走周引擎；仅周线不足/缺失时用日链 degraded
        from trader_shared.midline_structure import MIN_WEEKLY

        if not bars or len(bars) < MIN_WEEKLY:
            return build_degraded_daily_key_levels(
                current=current,
                key_levels=key_levels,
                ma20=ma20,
                stop=stop,
                stop_losses=stop_losses,
                stage_stop_price=stage_stop_price,
            )

    # 主路径：周线引擎。key_levels/stop 故意不传入算法（默认忽略）。
    return build_midline_levels(
        current=current,
        weekly_bars=weekly_bars,
        chanlun_midline=chanlun_midline,
        wyckoff_midline=wyckoff_midline,
        ma_weekly=ma_weekly,
    )
