# -*- coding: utf-8 -*-
"""单票报告阶段函数（阶段 5：从 build_report 抽出，行为不变）。

编排总管只排队调用本模块；此处仍禁止写加权公式/检测实现。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)

MarkFn = Callable[[str], None]


def _noop_mark(_label: str) -> None:
    return None


def attach_analysis_decision_stack(
    report: dict[str, Any],
    *,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """意见卡 → 共振 → 策略匹配 → decision_view（只收紧）。

    失败不抛：尽量写占位字段，与 build_report 原行为一致。
    """
    _mark = mark or _noop_mark
    if not isinstance(report, dict):
        return report

    try:
        from trader_shared.analysis_cards import ensure_report_analysis_cards
        from trader_shared.strategy_match import match_strategies

        _pre = report.pop("_fusion_pre_cards", None)
        if isinstance(_pre, dict):
            ac = report.get("analysis_cards") if isinstance(report.get("analysis_cards"), dict) else {}
            ac.update(_pre)
            report["analysis_cards"] = ac
        ensure_report_analysis_cards(report)

        try:
            from trader_shared.resonance import attach_resonance

            attach_resonance(report)
            _mark("resonance")
        except Exception as _res_exc:
            _logger.debug("resonance skip: %s", _res_exc)
            report.setdefault(
                "resonance",
                {
                    "schema_version": "resonance_v1",
                    "scene": "pullback_probe",
                    "grade": "empty",
                    "posts": {},
                    "missing": [],
                    "conflict": False,
                    "summary_line": "共振：跳过",
                },
            )

        report["strategy_match"] = match_strategies(report)
        _mark("strategy_match")

        try:
            from trader_shared.decision_view import apply_decision_view

            apply_decision_view(report, tighten_discipline=True)
            _mark("decision_view")
        except Exception as _dv_exc:
            _logger.debug("decision_view skip: %s", _dv_exc)
            report.setdefault(
                "decision_view",
                {
                    "schema_version": "decision_view_v1",
                    "allow_new_recommend": False,
                    "summary_line": "决策：跳过",
                },
            )
    except Exception as _st_exc:
        _logger.debug("analysis_decision_stack skip: %s", _st_exc)
        try:
            from trader_shared.analysis_cards import ensure_report_analysis_cards

            report.pop("_fusion_pre_cards", None)
            ensure_report_analysis_cards(report)
        except Exception:
            report.setdefault("analysis_cards", {})
        try:
            from trader_shared.resonance import attach_resonance

            attach_resonance(report)
        except Exception:
            report.setdefault("resonance", {"schema_version": "resonance_v1", "grade": "empty"})

    return report
