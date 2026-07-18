# -*- coding: utf-8 -*-
"""阶段 5：report_pipeline 阶段函数。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.report_pipeline import attach_analysis_decision_stack  # noqa: E402


def test_attach_stack_writes_resonance_strategy_decision():
    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "discipline": {
            "allow_new_entry": True,
            "entry_checklist": {"all_green": True, "missing_labels": []},
        },
        "analysis_cards": {
            "chan": {"type_short": "二买", "direction": 1},
            "wyckoff_midline": {"direction": 0, "summary_line": "中性"},
            "chip": {"raw_available": True, "summary_line": "有峰"},
            "momentum": {"direction": 0, "confidence": 0.4},
        },
        "chip_peaks": [{"price": 9.5}],
        "key_prices": {"buy_zone_low": 9.5, "buy_zone_high": 10.2},
        "conclusion": {"execution": "观察"},
    }
    marks: list[str] = []
    attach_analysis_decision_stack(report, mark=marks.append)
    assert "analysis_cards" in report
    assert "resonance" in report
    assert report["resonance"].get("schema_version") == "resonance_v1"
    assert "strategy_match" in report
    assert "decision_view" in report
    assert "resonance" in marks or "strategy_match" in marks
