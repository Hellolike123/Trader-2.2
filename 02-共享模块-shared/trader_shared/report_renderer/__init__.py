"""report_renderer — 报告渲染实现包。

实现在此；report_core 为兼容 re-export。
生产唯一路径：``render_short_midline``（via ``render_single``）。
"""
from __future__ import annotations

from trader_shared.report_renderer._helpers import _short_midline_enabled
from trader_shared.report_renderer.short_midline import render_short_midline
from trader_shared.report_renderer.legacy import render_single_legacy
from trader_shared.report_renderer.pool import render_pool_summary
from trader_shared.report_renderer.backtest import render_backtest


def render_single(r: dict) -> str:
    """生产入口：始终短中线双轨。"""
    return render_short_midline(r)


__all__ = [
    "render_single",
    "render_short_midline",
    "render_single_legacy",
    "render_pool_summary",
    "render_backtest",
    "_short_midline_enabled",
]
