"""report_renderer — 报告渲染子包

将 report_core.py 中各渲染函数按功能分文件组织，便于独立维护和单元测试。
对外接口与 report_core 完全兼容：

    from trader_shared.report_renderer import render_single
    from trader_shared.report_renderer import render_short_midline
    from trader_shared.report_renderer import render_pool_summary
    from trader_shared.report_renderer import render_backtest

各子模块功能：
    short_midline.py  — 中短线双轨报告（默认主模板）
    legacy.py         — 旧版单票报告（SHORT_MIDLINE_REPORT=false 回退）
    pool.py           — 选股池汇总/排序报告
    backtest.py       — 回测结果报告
"""
from __future__ import annotations

# 对外统一导出，与 report_core 接口完全兼容
from trader_shared.report_renderer.short_midline import render_short_midline
from trader_shared.report_renderer.legacy import render_single_legacy
from trader_shared.report_renderer.pool import render_pool_summary
from trader_shared.report_renderer.backtest import render_backtest
from trader_shared.report_renderer._helpers import _short_midline_enabled


def render_single(r: dict) -> str:
    """渲染单票分析报告（生产入口）。

    默认短中线双轨模板；SHORT_MIDLINE_REPORT=false 回退旧模板。
    """
    if _short_midline_enabled():
        return render_short_midline(r)
    return render_single_legacy(r)


__all__ = [
    "render_single",
    "render_short_midline",
    "render_single_legacy",
    "render_pool_summary",
    "render_backtest",
]
