"""report_renderer/_helpers.py — 共享辅助函数

供各子模块引用，避免循环依赖。
"""
from __future__ import annotations

import os
import re


def _short_midline_enabled() -> bool:
    """判断是否启用短中线双轨报告模板。"""
    # 直接从 report_core 导入，保持单一实现
    from trader_shared.report_core import _short_midline_enabled as _impl
    return _impl()


def _reformat_mid_line(line: str) -> str:
    """中线关键价行格式转换：价格前置 + 动作统一。

    旧格式「生命线 41.14（破则中线转弱）」→ 新格式「41.14 生命线（跌破则减仓）」。
    已是新格式时原样返回。
    """
    # 直接从 report_core 导入，保持单一实现
    from trader_shared.report_core import _reformat_mid_line as _impl
    return _impl(line)
