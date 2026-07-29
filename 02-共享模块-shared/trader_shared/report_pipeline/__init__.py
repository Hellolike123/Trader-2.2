# -*- coding: utf-8 -*-
"""单票报告阶段函数包（原 report_pipeline.py 拆分）。

编排只排队；禁止写加权公式/缠威检测实现。
"""
from __future__ import annotations

from trader_shared.report_pipeline._common import MarkFn, _noop_mark
from trader_shared.report_pipeline.prelude import (
    build_live_bar_anchor,
    detect_risk_flags,
    tag_fusion_as_instrument,
)
from trader_shared.report_pipeline.attach import (
    apply_buy_point_lifecycle,
    attach_analysis_decision_stack,
    attach_short_midline_and_decision,
    attach_stage_position_pack,
    sync_report_with_data,
)
from trader_shared.report_pipeline.fusion_stage import run_fusion_stage
from trader_shared.report_pipeline.structure_stage import run_structure_stage
from trader_shared.report_pipeline.chip_stage import run_chip_enrichment_stage
from trader_shared.report_pipeline.assemble_stage import (
    _calc_volume_ratio_from_bars,
    assemble_base_report,
    run_stage_positioning_stage,
)
from trader_shared.report_pipeline.context_stage import run_analysis_context_stage

__all__ = [
    "MarkFn",
    "_noop_mark",
    "detect_risk_flags",
    "build_live_bar_anchor",
    "tag_fusion_as_instrument",
    "apply_buy_point_lifecycle",
    "attach_analysis_decision_stack",
    "attach_short_midline_and_decision",
    "sync_report_with_data",
    "attach_stage_position_pack",
    "run_fusion_stage",
    "run_structure_stage",
    "run_chip_enrichment_stage",
    "_calc_volume_ratio_from_bars",
    "run_stage_positioning_stage",
    "assemble_base_report",
    "run_analysis_context_stage",
]
