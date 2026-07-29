# -*- coding: utf-8 -*-
"""Offline seams for report_pipeline attach_* modules (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_attach_facade_reexports():
    from trader_shared.report_pipeline import attach as facade
    from trader_shared.report_pipeline.attach_buy_point import apply_buy_point_lifecycle
    from trader_shared.report_pipeline.attach_short_midline import (
        attach_short_midline_and_decision,
    )

    assert facade.apply_buy_point_lifecycle is apply_buy_point_lifecycle
    assert facade.attach_short_midline_and_decision is attach_short_midline_and_decision


def test_sync_report_with_data_fixes_stop_above_support():
    from trader_shared.report_pipeline import sync_report_with_data

    report = {
        "current": 10.0,
        "support": 9.0,
        "resistance": 11.0,
        "confirm": 10.5,
        "stop": 9.5,  # invalid: >= support
        "take": 12.0,
        "scene": "观望",
        "state_label": "多头",
    }
    out = sync_report_with_data(report, {"ma_values": {"ma5": 10.1, "ma10": 9.9}, "zone_width_pct": 0.02})
    assert out["stop"] < out["support"]


def test_attach_short_midline_writes_discipline_or_conclusion():
    from trader_shared.report_pipeline.attach_short_midline import (
        attach_short_midline_and_decision,
    )

    report = {
        "current": 10.0,
        "support": 9.0,
        "stop": 8.5,
        "confirm": 10.5,
        "resistance": 11.0,
        "scene": "观察",
        "suggested_pct": 0,
        "ma": {"ma5": 10, "ma10": 9.5, "ma20": 9},
        "chanlun_midline": {},
        "wyckoff_midline": {},
        "chanlun": {},
    }
    out = attach_short_midline_and_decision(
        report,
        current=10.0,
        scene="观察",
        report_fusion={"action": "观望", "regime": "正常", "signals_detail": {}},
        stage_result={"major_stage": "蓄势", "momentum": "震荡"},
        weekly_bars=[],
        suggested=0,
        theory_status="观察",
        market_env_data={"level": "正常"},
        has_position=False,
        data_status="full",
        chip_resistance_lower=None,
        chip_resistance_upper=None,
        stage="蓄势",
    )
    assert "discipline" in out or "conclusion" in out or "key_prices" in out
