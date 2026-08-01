# -*- coding: utf-8 -*-
"""Offline seams for report_pipeline attach_* modules (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sm_ctx(**over):
    """Minimal StageContext for attach_short_midline_and_decision."""
    from trader_shared.report_pipeline.stage_context import StageContext

    base = dict(
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
        short_term_momentum="蓄势",
    )
    base.update(over)
    return StageContext.from_mapping(base)


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
    out = attach_short_midline_and_decision(report, _sm_ctx())
    assert "discipline" in out or "conclusion" in out or "key_prices" in out


def test_attach_rr11_flat_trailing_above_uses_hard_stop_no_nameerror():
    """R-R11 完整 attach：空仓 + trailing>现价 → key_prices 止损=硬止损，无 NameError。"""
    from trader_shared.report_pipeline.attach_short_midline import (
        attach_short_midline_and_decision,
    )

    report = {
        "current": 41.90,
        "has_position": False,
        "support": 41.82,
        "stop": 40.57,
        "trailing_stop": 47.21,
        "effective_stop": 47.21,
        "confirm": 42.74,
        "resistance": 42.57,
        "take": 43.59,
        "scene": "防守观察",
        "suggested_pct": 0,
        "ma": {"ma5": 42.57, "ma10": 42.65, "ma20": 48.42},
        "low_zone_lower": 41.82,
        "low_zone_upper": 41.82,
        "chanlun_midline": {},
        "wyckoff_midline": {},
        "chanlun": {},
        "key_levels": {},
    }
    out = attach_short_midline_and_decision(report, _sm_ctx(has_position=False))
    assert "gate_error" not in out or "_eff_stop" not in str(out.get("gate_error") or "")
    kp = out.get("key_prices") or {}
    assert kp.get("stop_sell") == pytest.approx(40.57)
    assert float(kp.get("stop_sell") or 0) < 41.90


def test_a3_daily_fallback_zones_not_weekly_pivots():
    """A3：daily_fallback zones 不得冒充周中枢 / pivot_position_weekly。"""
    from trader_shared.report_pipeline.attach_short_midline import (
        attach_short_midline_and_decision,
    )

    bait_zones = [{"valid": True, "zh_bottom": 9.0, "zh_top": 11.0, "zh_center": 10.0}]
    report = {
        "current": 10.0,
        "support": 9.0,
        "stop": 8.5,
        "confirm": 10.5,
        "resistance": 11.0,
        "scene": "观察",
        "suggested_pct": 0,
        "ma": {"ma5": 10, "ma10": 9.5, "ma20": 9},
        "chanlun_midline": {
            "chanlun": {
                "timeframe": "daily_fallback",
                "structure_type": "上涨趋势",
                "structure_confidence": "high",
                "zones": bait_zones,
                "buy_points": [{"type": "类二买", "confidence": 2, "price": 10.0}],
            }
        },
        "wyckoff_midline": {
            "phase": "accumulation_b",
            "phase_label": "吸筹B",
        },
        "chanlun": {},
    }
    out = attach_short_midline_and_decision(report, _sm_ctx())
    # 无真周 zones → 周枢位置未知（不得用日线回退中枢算出「中枢内」）
    assert out.get("pivot_position_weekly") in (None, "未知", "")
    # 阶段不得被 daily_fallback 类二抬成主升初期
    assert out.get("midline_stage") != "主升初期"
    mv = out.get("midline_verdict") or {}
    assert mv.get("chan_dir") == 0
    assert mv.get("stage") != "主升初期"


def test_a3_weekly_zones_feed_pivot_when_timeframe_weekly():
    """对照：真 weekly zones 仍可进 pivot_position_weekly。"""
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
        "chanlun_midline": {
            "chanlun": {
                "timeframe": "weekly",
                "structure_type": "盘整",
                "structure_confidence": "mid",
                "zones": [{"valid": True, "zh_bottom": 9.0, "zh_top": 11.0}],
            }
        },
        "wyckoff_midline": {"phase": "accumulation_b", "phase_label": "吸筹B"},
        "chanlun": {},
    }
    out = attach_short_midline_and_decision(report, _sm_ctx())
    assert out.get("pivot_position_weekly") == "中枢内"


def test_expert_conf_average_seats_use_vpf_not_wyckoff():
    """法源 BUSINESS.md §2.4：专家 conf 均值第三席为 vpf，非日线威科夫 stub。"""
    import inspect

    from trader_shared.report_pipeline import attach_short_midline as mod

    src = inspect.getsource(mod._attach_short_midline_and_decision_impl)
    assert '("chan", "momentum", "vpf")' in src or "('chan', 'momentum', 'vpf')" in src
    assert '("chan", "momentum", "wyckoff")' not in src
    assert "('chan', 'momentum', 'wyckoff')" not in src
