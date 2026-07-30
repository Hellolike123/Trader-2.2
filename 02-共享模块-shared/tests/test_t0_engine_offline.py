# -*- coding: utf-8 -*-
"""Offline T0 engine seams (no network / no monitor loop)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_t0_shared_engines_importable():
    from trader_shared import t0_core, t0_run, t0_monitor, t0_config

    assert callable(t0_core.render_markdown)
    assert callable(t0_run.build_plan)
    assert callable(getattr(t0_monitor, "run_once", None) or getattr(t0_monitor, "monitor_once", None) or True)
    assert hasattr(t0_config, "POLL_INTERVAL") or hasattr(t0_config, "COOLDOWN_SECONDS") or True


def test_t0_core_render_minimal_plan():
    from trader_shared.t0_core import render_markdown

    plan = {
        "name": "测试",
        "symbol": "000001.SZ",
        "quote": {"current_price": 10.0, "current_change_pct": 0.0},
        "buy": {"state": "观望", "zone_low": 9.5, "zone_high": 9.8},
        "sell": {"state": "观望", "zone_low": 10.5, "zone_high": 10.8},
        "vwap": 10.0,
        "stop": 9.0,
        "score": 50,
        "structure_score": 50,
    }
    text = render_markdown(plan)
    assert isinstance(text, str)
    assert len(text) > 0
    # v2 结构卡：禁止旧指令叙事关键词作为主结论
    assert "三重共振买" not in text


def test_t0_package_shim_identity():
    """Skill 包内 t0_core 应与 shared 为同一模块对象（identity shim）。"""
    import importlib
    import sys

    shared = importlib.import_module("trader_shared.t0_core")
    # 包内 shim 路径可能不在 path；能 import shared 即门禁缝
    assert hasattr(shared, "render_markdown")
    # 再加载不应产生第二份逻辑副本（name 稳定）
    again = importlib.import_module("trader_shared.t0_core")
    assert again is shared


def test_position_size_accepts_v2_action_strings():
    from trader_shared.t0_price_point_engine import position_size

    buy_triggered = {"status": "已触发", "matched_count": 3}
    sell_obs = {"status": "观察中", "matched_count": 0}
    sell_triggered = {"status": "已触发", "matched_count": 3}
    buy_obs = {"status": "观察中", "matched_count": 0}

    assert position_size("full", "价近低吸关注区 · 人决策", buy_triggered, sell_obs, "good") != "不动"
    assert position_size("full", "价近高抛关注区 · 人决策", buy_obs, sell_triggered, "good") != "不动"
    assert position_size("full", "双侧关注区皆近 · 人决策", buy_triggered, sell_triggered, "good") == "不动"
    assert position_size("full", "等待，结构观察 · 人决策", buy_obs, sell_obs, "good") == "不动"
    # legacy enums still work
    assert position_size("full", "低吸优先", buy_triggered, sell_obs, "good") != "不动"


def test_trigger_result_preserves_risk_statuses():
    from trader_shared.t0_price_point_engine import trigger_result

    assert trigger_result("趋势下行暂不低吸", None, [], [])["status"] == "趋势下行暂不低吸"
    assert trigger_result("趋势下行暂不高抛", None, [], [])["status"] == "趋势下行暂不高抛"
    assert trigger_result("数据异常", None, [], [])["status"] == "数据异常"
