"""统一报告渲染模块（兼容层）。

实现位于 report_renderer/；本模块 re-export 保持 import 路径稳定。
生产唯一路径：短中线双轨（``render_short_midline``）。
"""
from __future__ import annotations

from typing import Any

from trader_shared.report_renderer._helpers import (
    _reformat_mid_line,
    _short_midline_enabled,
)
from trader_shared.report_renderer.short_midline import render_short_midline
from trader_shared.report_renderer.legacy import render_single_legacy
from trader_shared.report_renderer.pool import render_pool_summary
from trader_shared.report_renderer.backtest import render_backtest


def render_single(r: dict[str, Any]) -> str:
    """渲染单票分析报告（生产入口 → 短中线）。"""
    return render_short_midline(r)


__all__ = [
    "render_single",
    "render_short_midline",
    "render_single_legacy",
    "render_pool_summary",
    "render_backtest",
    "_short_midline_enabled",
    "_reformat_mid_line",
]
