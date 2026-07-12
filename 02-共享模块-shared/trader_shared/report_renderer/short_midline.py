"""report_renderer/short_midline.py — 中短线双轨报告渲染

主力报告模板：meta → 🧭 中线 → ⚡ 短线 → 说明/亮点风险 → T0/池。

此模块是 report_core.render_short_midline 的直接 re-export，
在保持功能完全一致的同时使代码结构更清晰。

未来若需更换输出格式（如 HTML），只需在此文件中替换实现，
report_core 的兼容层不受影响。
"""
from __future__ import annotations

from typing import Any

# re-export：功能实现保留在 report_core 中（单一真实来源）
from trader_shared.report_core import render_short_midline

__all__ = ["render_short_midline"]
