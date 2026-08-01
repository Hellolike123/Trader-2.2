# -*- coding: utf-8 -*-
"""决策栈 / 短中线 / 仓位包挂接（facade — 实现见 attach_* 子模块）。"""
from __future__ import annotations

from trader_shared.report_pipeline.attach_buy_point import apply_buy_point_lifecycle
from trader_shared.report_pipeline.attach_decision_stack import attach_analysis_decision_stack
from trader_shared.report_pipeline.attach_short_midline import (
    attach_short_midline_and_decision,
    attach_short_midline_and_decision_kwargs,
)
from trader_shared.report_pipeline.attach_sync import sync_report_with_data
from trader_shared.report_pipeline.attach_stage_pack import (
    attach_stage_position_pack,
    attach_stage_position_pack_kwargs,
)

__all__ = [
    "apply_buy_point_lifecycle",
    "attach_analysis_decision_stack",
    "attach_short_midline_and_decision",
    "attach_short_midline_and_decision_kwargs",
    "sync_report_with_data",
    "attach_stage_position_pack",
    "attach_stage_position_pack_kwargs",
]
