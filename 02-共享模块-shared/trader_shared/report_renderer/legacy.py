"""report_renderer/legacy.py — 旧版单票分析报告（回退模板）

仅在 SHORT_MIDLINE_REPORT=false 时使用。
"""
from __future__ import annotations

from trader_shared.report_core import render_single_legacy

__all__ = ["render_single_legacy"]
