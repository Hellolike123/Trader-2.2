from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

for name in ("config", "light_data", "contract_utils", "indicators", "ict_execution", "price_point_engine", "t0_run", "monitor", "validate_output", "candidate_core", "models"):
    sys.modules.pop(name, None)

from datetime import datetime

import indicators
from ict_execution import build_ict_signal
from indicators import calculate_rsi
from price_point_engine import (
    build_price_point_model,
    choose_level,
    completed_5m_bars,
    detect_sell_trigger,
    latest_indicator_state,
    macd_green_shrinking,
    macd_red_shrinking,
    position_size,
    t0_net_space_pct,
)
from t0_core import SIDE_ZONE_HIT, normalize_side_display, side_status
from t0_run import build_t0_event_signal, build_t0_signals, render_markdown, segment_avg_volume
from monitor import BUY_TRIGGERED, detect_state_change, persist_event_signals
from trader_shared.signal_contract import validate_signal
from trader_shared.signal_store import load_recent_signals
from trader_shared.schema.v1 import validate_t0 as validate


def test_t0_markdown_contract() -> None:
    plan = {
        "name": "南网科技",
        "symbol": "688248.SH",
        "current_price": 56.4,
        "current_change_pct": -5.39,
        "data_status": "full",
        "today_action": "等待，不主动操作",
        "max_move": "不动",
        "position_score": 6,
        "volume_score": 5,
        "vwap": 57.0,
        "volume_ratio": 1.0,
        "amplitude_pct": 0.035,
        "space_state": "normal",
        "atr_info": {"atr14": 1.20, "atr_ratio": 0.021, "level": "波动正常"},
        "ict_signal": {"summary": "无有效扫流动性确认，不加分。"},
        "data": {
            "kline_5m_completed": make_5m_bars(16),
            "quote": {"high": 58.0, "low": 55.5, "pre_close": 59.6},
        },
        "model": {
            "zones": {
                "buy_zone": {"main_support": 55.8, "upper": 55.9},
                "sell_zone": {"main_resistance": 58.5, "lower": 58.8},
            }
        },
        "buy": {
            "status": "观察中",
            "zone": {"lower": 55.5, "upper": 55.9},
            "observation_price": 55.9,
            "trigger_price": None,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 55.22,
            "matched_count": 3,
            "total_conditions": 8,
            "blocked_reasons": [],
        },
        "sell": {
            "status": "未进入候选区",
            "zone": {"lower": 58.8, "upper": 59.2, "source": "5m高点"},
            "observation_price": 58.8,
            "trigger_price": None,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 59.5,
            "matched_count": 1,
            "total_conditions": 8,
            "blocked_reasons": [],
        },
    }
    markdown = render_markdown(plan)

    assert markdown.startswith("🎯")
    assert "止损" in markdown
    assert "低吸" in markdown
    assert "高抛" in markdown
    assert "📌 盘面" in markdown
    assert "📌 买卖价" in markdown
    assert "RR" in markdown or "计划" in markdown
    assert "ATR" in markdown
    assert "人决策" in markdown
    assert "结构偏强" not in markdown.split("→", 1)[-1].split("\n", 1)[0]
    assert "可执行" not in markdown
    assert "可低吸" not in markdown
    assert "三重共振" not in markdown
    assert "无底仓" in markdown
    assert "若做正T" not in markdown
    assert "**" not in markdown
    assert validate(markdown) == []


def test_t0_markdown_hides_observation_when_space_or_data_invalid() -> None:
    plan = {
        "name": "中国铝业",
        "symbol": "601600.SH",
        "current_price": 11.66,
        "current_change_pct": -2.67,
        "data_status": "degraded",
        "today_action": "等待，不主动操作",
        "max_move": "不动",
        "position_score": 5,
        "volume_score": 5,
        "ict_signal": {"summary": "无有效扫流动性确认，不加分。"},
        "data": {"kline_5m_completed": []},
        "buy": {
            "status": "数据不足",
            "zone": {"lower": 11.58, "upper": 11.64},
            "observation_price": 11.64,
            "observation_valid": False,
            "observation_reason": "盘中数据不足，暂不生成T0观察价",
            "trigger_price": None,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 11.54,
            "matched_count": 0,
            "total_conditions": 8,
            "blocked_reasons": ["5m数据不足或非交易时段"],
        },
        "sell": {
            "status": "数据不足",
            "zone": {"lower": 11.65, "upper": 11.72, "source": "5m高点"},
            "observation_price": 11.65,
            "observation_valid": False,
            "observation_reason": "盘中数据不足，暂不生成T0观察价",
            "trigger_price": None,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 11.76,
            "matched_count": 0,
            "total_conditions": 8,
            "blocked_reasons": ["5m数据不足或非交易时段"],
        },
    }

    markdown = render_markdown(plan)

    assert "低吸" in markdown
    assert "高抛" in markdown
    assert "止损" in markdown
    assert "可执行" not in markdown
    assert "可低吸" not in markdown
    assert validate(markdown) == []


def test_t0_v2_no_exec_command_when_triggered() -> None:
    """价到关注区时仍禁止「可执行/可低吸」指令句。"""
    plan = sample_t0_plan()
    plan["buy"].update({
        "status": "已触发",
        "execution_price": 11.94,
        "acceptable_price": 11.98,
        "invalid_price": 11.72,
    })
    plan["resonance"] = {
        "score": 80,
        "sell_score": 20,
        "buy_green": True,
        "sell_red": False,
        "lights": {
            "ema": {"buy": True, "sell": False, "reason": "多头", "ok": True},
            "vwap": {"buy": True, "sell": False, "reason": "今日VWAP11.90上方", "ok": True},
            "box": {"buy": True, "sell": False, "reason": "近底", "ok": True},
            "volume": {"buy": True, "sell": False, "reason": "放量", "ok": True},
            "atr": {"buy": False, "sell": False, "reason": "ATR0.3%<2%门槛(5m常不达标)", "ok": True},
        },
        "summary": "评分80/100 · 结构偏强（参考）",
    }
    plan["vwap"] = 11.90
    plan["atr_info"] = {"atr14": 0.35, "atr_ratio": 0.029, "level": "波动正常"}
    plan["sell"]["observation_price"] = 12.30
    assert side_status(plan["buy"]) == SIDE_ZONE_HIT
    assert SIDE_ZONE_HIT == "到价关注"
    md = render_markdown(plan)
    assert "低吸 11.94～11.98" in md
    assert "📌 买卖价" in md
    assert "近买区" in md
    assert "可执行" not in md
    assert "可低吸" not in md
    assert "可加仓" not in md
    assert "人决策" in md
    assert validate(md) == []


def test_legacy_executable_display_status_normalized() -> None:
    """旧 buy_display_status=可执行 不得泄露到 markdown。"""
    plan = sample_t0_plan()
    plan["buy"].update({
        "status": "已触发",
        "execution_price": 11.94,
        "acceptable_price": 11.98,
    })
    plan["buy_display_status"] = "可执行"
    plan["vwap"] = 11.90
    assert normalize_side_display("可执行") == SIDE_ZONE_HIT
    md = render_markdown(plan)
    assert "可执行" not in md
    assert "近买区" in md
    assert "低吸 11.94～11.98" in md
    assert validate(md) == []


def test_no_position_hides_account_discipline_block() -> None:
    """无底仓不展示持仓纪律/降本块/做人清单，即使误注入 t0_account。"""
    plan = sample_t0_plan()
    plan["t0_account"] = {
        "avg_cost": 12.0,
        "total_shares": 0,
        "mode": "cost_cut",
        "allow_reverse_t": False,
        "worth_t": {"worth": True, "net_pct": 1.2, "min_edge_pct": 0.8},
    }
    md = render_markdown(plan)
    assert "无底仓" in md
    assert "不做T召唤" in md or "不做 T 召唤" in md
    assert "持仓纪律" not in md
    assert "降本模式" not in md
    assert "先卖后买" not in md
    assert "若做正T" not in md
    assert validate(md) == []


def test_v21_trade_price_rr_block() -> None:
    """操盘主区：买卖价+止损+ATR/RR；区间塌缩时用止盈价兜底。"""
    plan = sample_t0_plan()
    plan.update({
        "vwap": 12.0,
        "volume_ratio": 1.5,
        "amplitude_pct": 0.04,
        "space_state": "good",
        "atr_info": {"atr14": 0.40, "atr_ratio": 0.033, "level": "波动正常"},
        "data": {
            "kline_5m_completed": make_5m_bars(16),
            "quote": {"high": 12.3, "low": 11.7, "pre_close": 11.8},
        },
        "model": {
            "zones": {
                "buy_zone": {"main_support": 11.80, "upper": 11.90},
                "sell_zone": {"main_resistance": 12.20, "lower": 12.15},
            }
        },
        "exit_plan": {"risk_r": 1.5, "exit_plan": [{"price": 12.40, "ratio": 0.5}]},
    })
    plan["buy"]["observation_price"] = 11.90
    plan["buy"]["invalid_price"] = 11.72
    plan["sell"]["observation_price"] = 12.15
    md = render_markdown(plan)
    assert "📌 买卖价" in md
    assert "低吸 11.90" in md
    assert "止损 11.72" in md
    assert "高抛 12.15" in md
    assert "ATR 0.40" in md
    assert "RR1:" in md
    assert "计划" in md
    assert "现价" in md
    assert "可执行" not in md
    assert validate(md) == []


def test_v21_position_shows_human_checklist() -> None:
    """有底仓才出做人清单；结论不含评分主语。"""
    plan = sample_t0_plan()
    plan.update({
        "vwap": 11.90,
        "volume_ratio": 0.9,
        "amplitude_pct": 0.025,
        "space_state": "normal",
        "data": {
            "kline_5m_completed": make_5m_bars(16),
            "quote": {"high": 12.2, "low": 11.7, "pre_close": 11.8},
        },
        "model": {
            "zones": {
                "buy_zone": {"main_support": 11.80},
                "sell_zone": {"main_resistance": 12.20},
            }
        },
        "t0_account": {
            "avg_cost": 11.5,
            "total_shares": 1000,
            "mode": "grid",
            "allow_reverse_t": False,
            "worth_t": {"worth": True, "net_pct": 1.5, "min_edge_pct": 0.8},
        },
        "resonance": {"score": 80, "lights": {}},
    })
    plan["buy"]["observation_price"] = 11.80
    plan["sell"]["observation_price"] = 12.20
    md = render_markdown(plan)
    assert "若做正T（人勾选）" in md
    assert "是否动手由人决定" in md
    assert "无底仓" not in md
    conclusion = md.split("→", 1)[-1].split("\n", 1)[0]
    assert "结构偏强" not in conclusion
    assert "80" not in conclusion
    assert "可执行" not in md
    assert validate(md) == []


def test_check_resonance_uses_today_vwap() -> None:
    """评分 VWAP 必须用今日 session，与结构区同源。"""
    from datetime import datetime, timedelta
    from price_point_engine import check_resonance

    # 构造：昨日高价 bar + 今日低位 session → 跨日 VWAP 会被拉高，今日 VWAP 应偏低
    now = datetime(2026, 7, 29, 11, 0, 0)
    bars = []
    # 昨日 10 根，高价 50
    for i in range(10):
        t = now.replace(day=28, hour=10) + timedelta(minutes=5 * i)
        bars.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "open": 50.0, "high": 50.5, "low": 49.5, "close": 50.0, "volume": 1000,
        })
    # 今日 30 根，价约 40，均量
    for i in range(30):
        t = now.replace(hour=9, minute=35) + timedelta(minutes=5 * i)
        px = 40.0 + (i % 3) * 0.1
        bars.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "open": px, "high": px + 0.2, "low": px - 0.2, "close": px, "volume": 1000,
        })
    current = 40.2
    report = {
        "current_price": current,
        "kline_5m_completed": bars,
        "kline_5m": bars,
    }
    res = check_resonance(report, {}, {})
    vwap_reason = (res.get("lights") or {}).get("vwap", {}).get("reason") or ""
    assert "今日VWAP" in vwap_reason
    # 今日 VWAP 应在 ~40 一带，不应被昨日 50 拉到 45+
    vwap_price = (res.get("lights") or {}).get("vwap", {}).get("buy_price")
    assert vwap_price is not None
    assert 39.0 <= float(vwap_price) <= 42.0, vwap_price
    # 现价在今日 VWAP 上 → 偏多条件应亮
    assert res["lights"]["vwap"]["buy"] is True
    assert res["lights"]["vwap"]["sell"] is False


def sample_t0_plan() -> dict:
    return {
        "name": "中国铝业",
        "symbol": "601600.SH",
        "analysis_time": "2026-05-01 10:35",
        "current_price": 11.95,
        "current_change_pct": 1.27,
        "data_status": "full",
        "today_action": "等待，不主动操作",
        "max_move": "底仓的 10%-20%",
        "position_score": 6,
        "volume_score": 5,
        "ict_signal": {"summary": "无有效扫流动性确认，不加分。"},
        "data": {"kline_5m_completed": make_5m_bars(16)},
        "buy": {
            "status": "观察中",
            "observation_price": 11.90,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 11.72,
            "blocked_reasons": [],
        },
        "sell": {
            "status": "未进入候选区",
            "observation_price": 12.30,
            "execution_price": None,
            "acceptable_price": None,
            "invalid_price": 12.45,
            "blocked_reasons": [],
        },
    }


def test_t0_untriggered_plan_emits_watch_signals_only() -> None:
    signals = build_t0_signals(sample_t0_plan())

    assert [signal["signal_type"] for signal in signals] == ["low_buy_watch", "high_sell_watch"]
    assert all(validate_signal(signal) == [] for signal in signals)
    assert all(signal["trigger"].get("price") is not None for signal in signals)


def test_t0_triggered_buy_event_emits_low_buy_signal() -> None:
    plan = sample_t0_plan()
    plan["buy"].update({"status": "已触发", "execution_price": 11.94, "acceptable_price": 11.98})

    signal = build_t0_event_signal(BUY_TRIGGERED, plan)

    assert signal["signal_type"] == "low_buy_triggered"
    assert signal["action"] == "low_buy"
    assert signal["trigger"]["price"] == 11.94
    assert validate_signal(signal) == []


def test_monitor_event_signals_persist_to_jsonl(tmp_path: Path, monkeypatch: Any) -> None:
    import monitor as monitor_mod

    # 离线：禁止 persist 路径打到真实大盘环境（会挂网超时）
    monkeypatch.setattr(monitor_mod, "get_market_level", lambda: "正常")
    monkeypatch.setattr(monitor_mod, "get_market_note", lambda: "")

    plan = sample_t0_plan()
    plan["buy"].update({"status": "已触发", "execution_price": 11.94, "acceptable_price": 11.98})
    store_path = tmp_path / "signals.jsonl"

    persist_event_signals([BUY_TRIGGERED], plan, store_path)

    stored = load_recent_signals(path=store_path)
    assert len(stored) == 1
    assert stored[0]["signal_type"] == "low_buy_triggered"
    assert stored[0]["symbol"] == "601600.SH"


def test_price_point_model_never_executes_without_enough_5m() -> None:
    report = {
        "quote": {"current_price": 10.0, "pre_close": 10.2, "high": 10.3, "low": 9.8},
        "daily_bars": [
            {"date": f"2026-04-{day:02d}", "open": 10, "high": 10.5, "low": 9.5, "close": 10, "volume": 1000}
            for day in range(1, 22)
        ],
        "kline_5m": [],
        "kline_15m": [],
        "kline_30m": [],
        "current_price": 10.0,
    }
    model = build_price_point_model(report)

    assert model["data_status"] == "degraded"
    assert model["buy"]["execution_price"] is None
    assert model["sell"]["execution_price"] is None
    assert model["buy"]["observation_valid"] is False
    assert model["sell"]["observation_valid"] is False
    assert model["today_action"] == "等待，不主动操作"


def test_monitor_does_not_alert_when_entering_observation_only() -> None:
    events = detect_state_change(
        {"data_status": "full", "buy_status": "未进入候选区", "sell_status": "未进入候选区"},
        {
            "current_price": 10.0,
            "data_status": "full",
            "buy": {"status": "观察中", "invalid_price": 9.8, "execution_price": None},
            "sell": {"status": "未进入候选区", "invalid_price": 10.5, "execution_price": None},
        },
    )

    assert events == []


def test_monitor_alerts_first_run_trigger_only_when_executable() -> None:
    executable = detect_state_change(
        None,
        {
            "current_price": 10.0,
            "data_status": "full",
            "buy": {"status": "已触发", "invalid_price": 9.8, "execution_price": 10.01},
            "sell": {"status": "未进入候选区", "invalid_price": 10.5, "execution_price": None},
        },
    )
    expired_or_no_execution = detect_state_change(
        None,
        {
            "current_price": 10.0,
            "data_status": "full",
            "buy": {"status": "已触发", "invalid_price": 9.8, "execution_price": None},
            "sell": {"status": "未进入候选区", "invalid_price": 10.5, "execution_price": None},
        },
    )

    assert executable == [BUY_TRIGGERED]
    assert expired_or_no_execution == []


def test_completed_5m_bars_excludes_current_unfinished_bar() -> None:
    bars = [
        {"time": "2026-04-27 10:00", "close": 1},
        {"time": "2026-04-27 10:05", "close": 2},
    ]

    assert [bar["time"] for bar in completed_5m_bars(bars, datetime(2026, 4, 27, 10, 5, 1))] == ["2026-04-27 10:00"]
    assert [bar["time"] for bar in completed_5m_bars(bars, datetime(2026, 4, 27, 10, 10, 1))] == [
        "2026-04-27 10:00",
        "2026-04-27 10:05",
    ]


def test_vwap_does_not_steal_main_resistance_when_price_level_is_reasonable() -> None:
    levels = [
        {"name": "5日高点", "price": 12.60, "weight": 1.0},
        {"name": "VWAP上方偏离", "price": 12.10, "weight": 0.6},
    ]

    assert choose_level(levels, 12.07, below=False)["name"] == "5日高点"


def test_choose_level_falls_back_to_current_when_candidates_are_empty() -> None:
    level = choose_level([], 12.07, below=True)

    assert level["name"] == "现价兜底"
    assert level["price"] == 12.07


def make_5m_bars(count: int = 24) -> list[dict[str, float | str]]:
    bars = []
    base = datetime(2026, 4, 27, 9, 30)
    for idx in range(count):
        dt = base.replace(minute=base.minute + idx * 5) if idx < 6 else base
        if idx >= 6:
            minutes = idx * 5
            hour = 9 + (30 + minutes) // 60
            minute = (30 + minutes) % 60
            dt = datetime(2026, 4, 27, hour, minute)
        close = 10.0 + idx * 0.001
        bars.append({"time": dt.strftime("%Y-%m-%d %H:%M"), "open": close, "high": close + 0.02, "low": close - 0.02, "close": close, "volume": 1000})
    return bars


def test_low_intraday_amplitude_blocks_t0_execution() -> None:
    daily = [
        {"date": f"2026-04-{day:02d}", "open": 10, "high": 10.5, "low": 9.9, "close": 10, "volume": 1000}
        for day in range(1, 23)
    ]
    report = {
        "quote": {"current_price": 10.01, "pre_close": 10.0, "high": 10.06, "low": 9.98},
        "daily_bars": daily,
        "kline_5m": make_5m_bars(),
        "kline_15m": [],
        "kline_30m": [],
        "current_price": 10.01,
        "now": datetime(2026, 4, 27, 11, 30),
    }
    model = build_price_point_model(report)

    assert model["space_state"] == "too_small"
    assert "日内振幅不足" in model["buy"]["blocked_reasons"]
    assert model["buy"]["execution_price"] is None
    assert model["sell"]["execution_price"] is None
    assert model["max_move"] == "不动"


def test_position_size_requires_good_space_for_larger_t0_size() -> None:
    buy = {"status": "已触发", "matched_count": 5}
    sell = {"status": "未进入候选区", "matched_count": 0}

    assert position_size("full", "低吸优先", buy, sell, "good") == "底仓的 20%-30%"
    assert position_size("full", "低吸优先", buy, sell, "normal") == "底仓的 10%-20%"
    assert position_size("full", "低吸优先", buy, sell, "too_small") == "不动"


def test_wilder_rsi_handles_direction_and_flat_series() -> None:
    rising = calculate_rsi([float(value) for value in range(1, 21)])
    falling = calculate_rsi([float(value) for value in range(20, 0, -1)])
    flat = calculate_rsi([10.0 for _ in range(20)])

    assert rising[-1] == 100.0
    assert falling[-1] == 0.0
    assert flat[-1] == 50.0


def test_macd_conditions_wait_for_warmup_bars() -> None:
    state = latest_indicator_state(make_5m_bars(24))

    assert state["macd_ready"] is False
    assert macd_green_shrinking(state) is False
    assert macd_red_shrinking(state) is False


def test_segment_avg_volume_ignores_dirty_volume_values() -> None:
    segment = [
        {"volume": 1000},
        {"volume": "bad"},
        {"volume": None},
        {"volume": 3000},
    ]

    assert segment_avg_volume(segment) == 2000


def test_t0_net_space_filter_detects_too_narrow_zone() -> None:
    zones = {
        "buy_zone": {"upper": 10.00},
        "sell_zone": {"lower": 10.04},
    }

    assert t0_net_space_pct(zones) < 0.006


def test_nearby_5m_high_is_not_valid_sell_observation() -> None:
    daily = [
        {"date": f"2026-04-{day:02d}", "open": 11.5, "high": 11.8, "low": 11.2, "close": 11.6, "volume": 1000}
        for day in range(1, 23)
    ]
    bars = make_5m_bars(40)
    for bar in bars:
        bar.update({"open": 11.62, "high": 11.67, "low": 11.55, "close": 11.66, "volume": 1000})
    report = {
        "quote": {"current_price": 11.66, "pre_close": 11.8, "high": 12.2, "low": 11.5},
        "daily_bars": daily,
        "kline_5m": bars,
        "kline_15m": [],
        "kline_30m": [],
        "current_price": 11.66,
        "now": datetime(2026, 4, 27, 13, 5),
    }

    model = build_price_point_model(report)

    # 系统可选择 5m高点 或更高权重的 5日高点 做为止损观察来源
    assert model["sell"]["zone"]["source"] in ("5m高点", "5日高点"), f"expected 5m/5日高点 but got {model['sell']['zone']['source']}"
    assert model["sell"]["observation_valid"] is False
    assert "太近" in model["sell"]["observation_reason"] or "有效差价" in model["sell"]["observation_reason"] or "数据不足" in model["sell"]["observation_reason"]


def test_vwap_above_price_alone_does_not_block_sell() -> None:
    bars = make_5m_bars(24)
    for index, bar in enumerate(bars):
        close = 10.20 - index * 0.002
        bar.update({"open": close + 0.01, "high": close + 0.03, "low": close - 0.02, "close": close, "volume": 1000})
    state = latest_indicator_state(bars)
    state["vwap"] = 10.0
    state["prev_vwap"] = 9.99
    state["volume_ratio"] = 1.0
    report_data = {
        "kline_5m_completed": bars,
        "current_price": 10.50,
        "data_status": "full",
        "space_state": "good",
        "t0_net_space_pct": 0.02,
        "sell_net_space_pct": 0.01,
        "ict_signal": {},
    }
    zones = {
        "sell_zone": {"lower": 10.40, "upper": 10.80, "main_resistance": 11.00},
    }

    trigger = detect_sell_trigger(report_data, zones, state)

    assert "VWAP上行且放量突破主压力" not in trigger["blocked_reasons"]
    assert "放量突破主压力" not in trigger["blocked_reasons"]


def test_volume_breakout_without_vwap_uptrend_does_not_block_sell() -> None:
    bars = make_5m_bars(24)
    for index, bar in enumerate(bars):
        close = 10.20 - index * 0.002
        bar.update({"open": close + 0.01, "high": close + 0.03, "low": close - 0.02, "close": close, "volume": 1000})
    state = latest_indicator_state(bars)
    state["vwap"] = 10.0
    state["prev_vwap"] = 10.0
    state["volume_ratio"] = 1.5
    report_data = {
        "kline_5m_completed": bars,
        "current_price": 10.50,
        "data_status": "full",
        "space_state": "good",
        "t0_net_space_pct": 0.02,
        "sell_net_space_pct": 0.01,
        "ict_signal": {},
    }
    zones = {
        "sell_zone": {"lower": 10.40, "upper": 10.80, "main_resistance": 10.30},
    }

    trigger = detect_sell_trigger(report_data, zones, state)

    assert "VWAP上行且放量突破主压力" not in trigger["blocked_reasons"]


def test_ict_downside_sweep_with_bos_confirms_buy_bias() -> None:
    bars = [
        {"open": 10.10, "high": 10.16, "low": 10.05, "close": 10.12, "volume": 1000},
        {"open": 10.12, "high": 10.18, "low": 10.07, "close": 10.13, "volume": 980},
        {"open": 10.13, "high": 10.17, "low": 10.08, "close": 10.11, "volume": 950},
        {"open": 10.11, "high": 10.15, "low": 10.06, "close": 10.10, "volume": 940},
        {"open": 10.10, "high": 10.14, "low": 10.04, "close": 10.09, "volume": 930},
        {"open": 10.09, "high": 10.13, "low": 10.03, "close": 10.08, "volume": 920},
        {"open": 10.08, "high": 10.12, "low": 10.02, "close": 10.07, "volume": 910},
        {"open": 10.07, "high": 10.11, "low": 10.01, "close": 10.06, "volume": 900},
        {"open": 10.06, "high": 10.12, "low": 9.96, "close": 10.04, "volume": 1200},
        {"open": 10.04, "high": 10.21, "low": 10.02, "close": 10.20, "volume": 1100},
    ]

    signal = build_ict_signal(bars, sweep_lookback=8, recent_window=4, structure_lookback=3)

    assert signal["sweep_type"] == "downside_sweep"
    assert signal["structure_shift"] == "bullish_bos"
    assert signal["buy_confirmed"] is True
    assert signal["sell_confirmed"] is False


def test_ict_upside_sweep_with_choch_confirms_sell_bias() -> None:
    bars = [
        {"open": 10.10, "high": 10.18, "low": 10.05, "close": 10.12, "volume": 1000},
        {"open": 10.12, "high": 10.20, "low": 10.07, "close": 10.15, "volume": 980},
        {"open": 10.15, "high": 10.22, "low": 10.09, "close": 10.17, "volume": 950},
        {"open": 10.17, "high": 10.23, "low": 10.10, "close": 10.18, "volume": 940},
        {"open": 10.18, "high": 10.24, "low": 10.11, "close": 10.19, "volume": 930},
        {"open": 10.19, "high": 10.25, "low": 10.12, "close": 10.20, "volume": 920},
        {"open": 10.20, "high": 10.26, "low": 10.13, "close": 10.21, "volume": 910},
        {"open": 10.21, "high": 10.27, "low": 10.14, "close": 10.22, "volume": 900},
        {"open": 10.22, "high": 10.35, "low": 10.18, "close": 10.25, "volume": 1200},
        {"open": 10.25, "high": 10.26, "low": 10.08, "close": 10.09, "volume": 1100},
    ]

    signal = build_ict_signal(bars, sweep_lookback=8, recent_window=4, structure_lookback=3)

    assert signal["sweep_type"] == "upside_sweep"
    assert signal["structure_shift"] == "bearish_choch"
    assert signal["sell_confirmed"] is True
    assert signal["buy_confirmed"] is False


def test_monitor_suppresses_observation_and_reports_trigger_position(tmp_path, monkeypatch) -> None:
    import monitor
    monkeypatch.setattr(monitor, "is_trading_time", lambda: True)

    base_plan = {
        "name": "中国铝业",
        "symbol": "601600.SH",
        "current_price": 11.91,
        "data_status": "full",
        "max_move": "不动",
        "buy": {
            "status": "观察中",
            "zone": {"lower": 11.80, "upper": 11.92},
            "invalid_price": 11.72,
            "execution_price": None,
            "acceptable_price": None,
            "blocked_reasons": [],
        },
        "sell": {
            "status": "未进入候选区",
            "zone": {"lower": 12.30, "upper": 12.42},
            "invalid_price": 12.48,
            "execution_price": None,
            "acceptable_price": None,
            "blocked_reasons": [],
        },
    }
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(monitor, "build_plan", lambda _target: base_plan)

    first = monitor.run_once("中国铝业", state_path=state_path)
    second = monitor.run_once("中国铝业", state_path=state_path)

    assert first == ""
    assert second == ""

    triggered = dict(base_plan)
    triggered["current_price"] = 11.95
    triggered["max_move"] = "底仓的 10%-20%"
    triggered["buy"] = dict(base_plan["buy"], status="已触发", execution_price=11.94, acceptable_price=11.98)
    monkeypatch.setattr(monitor, "build_plan", lambda _target: triggered)

    alert = monitor.run_once("中国铝业", cost=11.50, position=10000, state_path=state_path)
    assert "近低吸关注区" in alert
    assert "人决策" in alert
    assert "可执行" not in alert
    assert "11.94" in alert
    assert "11.98" in alert
    assert "11.72" in alert


def test_min_trigger_matches_reduced_to_3() -> None:
    from trader_shared.t0_config import MIN_TRIGGER_MATCHES

    assert MIN_TRIGGER_MATCHES == 3



def test_buy_trigger_reaches_confirmation_with_3_signals_after_config_change(monkeypatch: Any) -> None:
    from indicators import is_new_low_recent
    monkeypatch.setattr(indicators, "is_new_low_recent", lambda bars, lookback=6: False)
    from price_point_engine import detect_buy_trigger
    from trader_shared.t0_config import MIN_TRIGGER_MATCHES

    assert MIN_TRIGGER_MATCHES == 3, "Config should require 3 signals"

    from indicators import calculate_rsi
    closes = [10.0 - i * 0.01 for i in range(20)] + [10.0 - 0.34 + 0.05, 10.0 - 0.34 + 0.07, 10.0 - 0.34 + 0.09]
    current = closes[-1]
    bars = [{"open": c, "high": c + 0.02, "low": c - 0.02, "close": c, "volume": 1000} for c in closes]
    rsi_series = calculate_rsi(closes)
    state = {
        "rsi": rsi_series[-36:] if len(rsi_series) >= 36 else rsi_series,
        "last_rsi": 42.0,
        "prev_rsi": 38.0,
        "macd_ready": False,
        "vwap": current + 0.03,
        "prev_vwap": current + 0.02,
        "volume_ratio": 0.6,
        "pct_b": -0.08,
    }
    report_data = {
        "kline_5m_completed": bars,
        "current_price": current,
        "data_status": "full",
        "space_state": "good",
        "t0_net_space_pct": 0.02,
        "sell_net_space_pct": 0.01,
        "ict_signal": {},
    }
    zones = {"buy_zone": {"lower": current - 0.3, "upper": current + 0.1, "main_support": current - 0.3}}
    trigger = detect_buy_trigger(report_data, zones, state)
    assert trigger["status"] == "已触发", f"Expected triggered but got {trigger['status']}, matched={trigger.get('matched_conditions', [])}, blocked={trigger.get('blocked_reasons', [])}"
    assert trigger["matched_count"] >= 3



def test_validate_rejects_reformatted_t0_card() -> None:
    markdown = """### ⏱️ 盘中 T0
**标的**：南网科技（688248.SH）
- **今日做法**：低吸优先

### 🎯 精细买卖点
| 项目 | 结论 |
|------|------|
| 低吸 | 可以 |

> 仅供参考，不构成投资建议。
"""
    errors = validate(markdown)
    joined = "\n".join(errors)
    assert "markdown heading syntax is not allowed" in joined
    assert "markdown bullet lists are not allowed" in joined
    assert "markdown tables are not allowed" in joined
