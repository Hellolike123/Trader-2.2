"""Deprecated legacy single-ticket renderer.

生产路径已锁定 ``render_short_midline``。本模块仅保留 import 兼容：
调用 ``render_single_legacy`` 会发出 DeprecationWarning 并委托短中线渲染。
"""
from __future__ import annotations

import warnings
from typing import Any


def render_single_legacy(r: dict[str, Any]) -> str:
    """旧版单票报告入口（已废弃）→ 委托 ``render_short_midline``。"""
    warnings.warn(
        "render_single_legacy is deprecated; use render_short_midline / render_single. "
        "SHORT_MIDLINE_REPORT=false is ignored.",
        DeprecationWarning,
        stacklevel=2,
    )
    from trader_shared.report_renderer.short_midline import render_short_midline

    return render_short_midline(r)
