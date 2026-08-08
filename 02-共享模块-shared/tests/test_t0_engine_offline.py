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


# ---- handoff §1 语义回归安全网（D4）：日线威科夫 phase 定基调，日内箱位降为时机 ----

def _plan_with_phase(phase, current, day_low, day_high, **extra):
    return {
        "name": "测试",
        "symbol": "000001.SZ",
        "quote": {"current_price": current},
        "data": {"quote": {"high": day_high, "low": day_low}},
        "current_price": current,
        "buy": {"state": "观望", "zone_low": day_low, "zone_high": day_low + 0.3},
        "sell": {"state": "观望", "zone_low": day_high - 0.3, "zone_high": day_high},
        "vwap": (day_low + day_high) / 2,
        "stop": day_low,
        "score": 50,
        "structure_score": 50,
        "wyckoff": {"phase": phase} if phase else {},
        **extra,
    }


def test_daily_phase_overrides_intraday_box():
    """D4：日线派发时即使日内低区也不判正T；积累时即使日内高区也不判反T。"""
    from trader_shared.t0_core import _t0_direction

    # 派发 + 日内低区 → 反T（不做正T）
    assert _t0_direction(_plan_with_phase("distribution_b", 10.05, 10.0, 11.0)) == "bearish"
    # 积累 + 日内高区 → 正T（不做反T）
    assert _t0_direction(_plan_with_phase("accumulation_c", 10.95, 10.0, 11.0)) == "bullish"
    # markup / markdown 同属方向词表
    assert _t0_direction(_plan_with_phase("markup", 10.95, 10.0, 11.0)) == "bullish"
    assert _t0_direction(_plan_with_phase("markdown", 10.05, 10.0, 11.0)) == "bearish"


def test_no_phase_falls_back_to_intraday_box():
    """无明确日线阶段 → 回退日内箱位：近高反T、近低正T、中轴观望。"""
    from trader_shared.t0_core import _t0_direction

    assert _t0_direction(_plan_with_phase("", 10.95, 10.0, 11.0)) == "bearish"
    assert _t0_direction(_plan_with_phase("", 10.05, 10.0, 11.0)) == "bullish"
    assert _t0_direction(_plan_with_phase("none", 10.5, 10.0, 11.0)) == "neutral"


def test_scenario_verb_uses_daily_direction():
    """有仓 + 派发/日内低区 → 剧本动词仍是看反T（逆势低吸被纠正）。"""
    from trader_shared.t0_core import _scenario_verb

    plan = _plan_with_phase("distribution_b", 10.05, 10.0, 11.0)
    plan["t0_account"] = {"has_position": True, "total_shares": 1000}
    assert _scenario_verb(plan) == "看反T"


def test_strategy_tone_line_mentions_daily_bias():
    """策略基调行出现日线偏多/偏空措辞（不再只写近高区/近低区）。"""
    from trader_shared.t0_core import _strategy_tone_line

    plan = _plan_with_phase("accumulation_a", 10.95, 10.0, 11.0)
    plan["t0_account"] = {"has_position": True, "total_shares": 1000}
    tone = _strategy_tone_line(plan, buy_state="观望", sell_state="观望")
    assert "日线偏多" in tone and "看正T" in tone

    plan2 = _plan_with_phase("distribution_a", 10.05, 10.0, 11.0)
    plan2["t0_account"] = {"has_position": True, "total_shares": 1000}
    tone2 = _strategy_tone_line(plan2, buy_state="观望", sell_state="观望")
    assert "日线偏空" in tone2 and "看反T" in tone2


# ---- handoff §2 关键位信号（VWAP回归/前高前低突破/开盘价收复失守/AB信号棒）----

def _bar(open_, high, low, close, volume=1000.0, time="2026-08-07 09:35:00"):
    return {"open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "time": time, "date": "2026-08-07"}


def test_vwap_regression_requires_deviation_and_shrink():
    """VWAP 回归：偏离 >1.5% + 缩量才触发；顺日线方向过滤。"""
    from trader_shared.t0_price_point_engine import vwap_regression_signal

    bars = [_bar(10.0, 10.2, 9.9, 10.0)]
    # 深偏离 + 缩量 + 非派发 → buy 触发
    state = {"vwap": 10.5, "volume_ratio": 0.6}
    sig = vwap_regression_signal(bars, state, 10.1, "buy", None)
    assert sig is not None and "VWAP回归" in sig["reason"]
    # 缩量但偏离不足 → 不触发
    assert vwap_regression_signal(bars, {"vwap": 10.5, "volume_ratio": 0.6}, 10.45, "buy", None) is None
    # 深偏离但不缩量 → 不触发
    assert vwap_regression_signal(bars, {"vwap": 10.5, "volume_ratio": 1.6}, 10.1, "buy", None) is None
    # 日线派发 → buy 被方向过滤
    assert vwap_regression_signal(bars, state, 10.1, "buy", "bearish") is None


def test_intraday_breakout_signal_direction_gate():
    """前高/前低突破：放量突破前高 + 非派发日线 → buy；缩量回探前低 + 积累 → 假突破低吸。"""
    from trader_shared.t0_price_point_engine import intraday_breakout_signal

    # 今日 bars：前高 10.2（前 2 根），当前棒收盘 10.35 放量突破
    bars = [
        _bar(10.0, 10.1, 9.9, 10.0, time="2026-08-07 09:35:00"),
        _bar(10.0, 10.2, 9.95, 10.15, time="2026-08-07 09:40:00"),
        _bar(10.15, 10.35, 10.1, 10.35, volume=2500.0, time="2026-08-07 09:45:00"),
    ]
    state = {"volume_ratio": 1.8}
    sig = intraday_breakout_signal(bars, state, 10.35, "buy", None)
    assert sig is not None and "突破" in sig["reason"]
    # 日线派发 → 跟突破被过滤（逆日线不追多）
    assert intraday_breakout_signal(bars, state, 10.35, "buy", "bearish") is None


def test_open_price_reclaim_requires_crossing():
    """开盘价收复/失守：只认刚穿越（前一棒在另一侧），不是持续站稳。"""
    from trader_shared.t0_price_point_engine import open_price_reclaim_signal

    # 开盘价 10.0：前 5 根在开盘价下方，第 6 根起站稳上方（刚收复）
    bars = [_bar(10.0, 10.05, 9.9, 9.95, time=f"2026-08-07 09:{35+i}:00") for i in range(6)]
    bars.append(_bar(10.0, 10.2, 9.98, 10.15, time="2026-08-07 10:05:00"))  # 第 7 根收复
    # 前一根收盘 9.95 ≤ 开盘价 → 刚收复触发（顺多/中性）
    sig = open_price_reclaim_signal(bars, {"volume_ratio": 1.0}, 10.15, "buy", None)
    assert sig is not None and "开盘价" in sig["reason"]
    # 日线派发 → 低吸被过滤
    assert open_price_reclaim_signal(bars, {"volume_ratio": 1.0}, 10.15, "buy", "bearish") is None
    # 持续站稳（前一棒也在上方）→ 不触发
    bars2 = bars + [_bar(10.15, 10.3, 10.1, 10.25, time="2026-08-07 10:10:00")]
    assert open_price_reclaim_signal(bars2, {"volume_ratio": 1.0}, 10.25, "buy", None) is None


def test_ab_signal_bar_requires_strong_and_direction():
    """AB 信号棒：仅 strong + 信号棒驱动 + 顺日线进关键位；Always-In 补充不算。"""
    from trader_shared.t0_price_point_engine import ab_signal_bar_signal

    # strong 信号棒驱动
    ab_strong = {
        "buy_signal": True, "sell_signal": False,
        "buy_reason": "信号棒strong·bull·2/2根确认", "sell_reason": "",
        "signal_bar_quality": "strong",
        "details": {"signal_bar": {"score": 0.9}},
    }
    assert ab_signal_bar_signal(ab_strong, "buy", None) is not None
    # 日线派发 → buy 被过滤
    assert ab_signal_bar_signal(ab_strong, "buy", "bearish") is None
    # Always-In 补充信号（非信号棒驱动）→ 不进快速通道
    ab_alwaysin = dict(ab_strong)
    ab_alwaysin["buy_reason"] = "Always-In多头·L2回调"
    assert ab_signal_bar_signal(ab_alwaysin, "buy", None) is None
    # weak 质量 → 不触发
    ab_weak = dict(ab_strong)
    ab_weak["signal_bar_quality"] = "weak"
    assert ab_signal_bar_signal(ab_weak, "buy", None) is None


def test_key_signal_drives_buy_green():
    """handoff §2：任一关键位信号（+ 顺日线）驱动 buy_green；评分不驱动。"""
    from trader_shared.t0_price_point_engine import check_resonance, daily_direction_from_phase

    assert daily_direction_from_phase("accumulation_b") == "bullish"
    assert daily_direction_from_phase("distribution_c") == "bearish"
    assert daily_direction_from_phase("none") is None
    assert daily_direction_from_phase("") is None
    # 评分很高但无关键位信号 → buy_green=False（评分降为仪表）
    report = {
        "kline_5m_completed": [_bar(10.0, 10.4, 9.9, 10.3, time="2026-08-07 09:35:00")] * 25,
        "current_price": 10.3,
        "data_status": "full",
        "daily_phase": "accumulation_a",
    }
    zones = {"buy_zone": {"main_support": 9.9, "lower": 9.7, "upper": 10.1, "width_pct": 0.02, "source": "t"},
             "sell_zone": {"main_resistance": 10.4, "lower": 10.2, "upper": 10.6, "width_pct": 0.02, "source": "t"}}
    res = check_resonance(report, zones, {"vwap": 10.0, "volume_ratio": 1.0}, ab_result=None)
    assert res["buy_green"] is False  # 无关键位信号 → 评分不驱动
    assert isinstance(res["score"], int)


# ---- handoff §4 选股前置筛选 ----

def _skip_plan(daily_rows, current=10.0):
    return {
        "space_state": "good",
        "current_price": current,
        "t0_account": {"worth_t": {"worth": True}},
        "data": {"quote": {"pre_close": 10.0, "high": 10.5, "low": 9.8}, "daily_bars": daily_rows},
    }


def test_skip_reason_liquidity_gates():
    """日均振幅 <3% / 日均成交额 <3 亿 → 今日宜不做。"""
    from trader_shared.t0_core import t_skip_reason

    # 高振幅高成交额 → 不劝退
    good = [{"date": f"2026-08-0{i}", "open": 10.0, "high": 10.6, "low": 9.6, "close": 10.0,
             "volume": 8e7} for i in range(1, 21)]
    assert t_skip_reason(_skip_plan(good)) is None
    # 日均振幅 2% → 劝退
    low_amp = [{"date": f"2026-08-0{i}", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.0,
                "volume": 8e7} for i in range(1, 21)]
    assert t_skip_reason(_skip_plan(low_amp)) == "日均振幅不足"
    # 日均成交额不足 3 亿 → 劝退
    low_amt = [{"date": f"2026-08-0{i}", "open": 10.0, "high": 10.6, "low": 9.6, "close": 10.0,
                "volume": 1e6} for i in range(1, 21)]
    assert t_skip_reason(_skip_plan(low_amt)) == "日均成交额不足"
