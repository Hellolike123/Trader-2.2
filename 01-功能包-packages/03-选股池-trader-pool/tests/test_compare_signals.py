#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
SHARED_SCRIPTS = SHARED_ROOT / "scripts"
CONTRACTS = SHARED_ROOT / "03-输出校验-contracts"
MARKET = SHARED_ROOT / "01-行情数据-market-data"
CANDIDATE = SHARED_ROOT / "02-候选逻辑-candidate"
for _p in (SCRIPTS, SHARED_SCRIPTS, CONTRACTS, CANDIDATE, MARKET, SHARED_ROOT):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for name in ("config", "light_data", "signal_store", "models", "pipeline", "signal_contract", "signal_tracker"):
    sys.modules.pop(name, None)

import candidate_core
from signal_store import append_signal, load_recent_signals, DEFAULT_SIGNAL_STORE_PATH
from final_pool import render_compare, _latest_signal_summary


def _fake_report(symbol: str, name: str, scene: str, current: float) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "scene": scene,
        "current": current,
        "atr14": 1.5,
        "atr_ratio": 0.015,
        "stop": 55.22,
    }


def test_latest_signal_summary_empty_when_no_signal(tmp_path):
    from signal_store import DEFAULT_SIGNAL_STORE_PATH
    with Path(tmp_path / "sig").open("w") as f:
        pass
    report = _fake_report("688248.SH", "南网科技", "低吸观察", 56.4)
    old = DEFAULT_SIGNAL_STORE_PATH
    try:
        import signal_store as store_mod
        store_mod.DEFAULT_SIGNAL_STORE_PATH = tmp_path / "sig"
        result = _latest_signal_summary(report)
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old
    assert result == ""


def test_latest_signal_summary_shows_t0_low_buy(tmp_path):
    store_path = tmp_path / "t0_signals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 10:00",
        "signal_type": "low_buy_triggered",
        "direction": "bullish_lean",
        "action": "low_buy",
        "confidence": "high",
        "data_status": "fresh",
        "trigger": {"type": "completed_5m_confirm", "price": 55.9, "text": "5m 止跌确认"},
        "invalidation": {"type": "price_break", "price": 55.22, "text": "跌破止损"},
        "position": {"max_total_pct": 20, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "低吸已触发",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("688248.SH", "南网科技", "低吸观察", 56.4)
    result = _latest_signal_summary(report, store_path=store_path)
    assert "T0低吸" in result
    assert "low_buy" in result


def test_latest_signal_summary_shows_t0_high_sell(tmp_path):
    store_path = tmp_path / "tsignals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": "601600.SH",
        "name": "中国铝业",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 11:00",
        "signal_type": "high_sell_triggered",
        "direction": "neutral",
        "action": "high_sell",
        "confidence": "high",
        "data_status": "fresh",
        "trigger": {"type": "completed_5m_confirm", "price": 58.8, "text": "5m 冲高失败"},
        "invalidation": {"type": "price_break", "price": 59.5, "text": "突破取消"},
        "position": {"max_total_pct": 20, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "高抛已触发",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("601600.SH", "中国铝业", "冲高减仓", 58.0)
    result = _latest_signal_summary(report, store_path=store_path)
    assert "T0高抛" in result


def test_latest_signal_summary_shows_risk_stop(tmp_path):
    store_path = tmp_path / "rsignals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": "002050.SZ",
        "name": "三花智控",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 09:45",
        "signal_type": "risk_stop",
        "direction": "bearish",
        "action": "stop_low_buy",
        "confidence": "medium",
        "data_status": "partial",
        "trigger": {"type": "price_break", "price": 55.0, "text": "跌破"},
        "invalidation": {"type": "price_break", "price": 54.8, "text": "止损价"},
        "position": {"max_total_pct": 20, "max_single_move_pct": 10},
        "risk_flags": ["structure_weak"],
        "summary": "跌破止损价，停止低吸",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("002050.SZ", "三花智控", "防守观察", 55.1)
    result = _latest_signal_summary(report, store_path=store_path)
    assert "止损" in result


def test_latest_signal_summary_shows_reduce(tmp_path):
    store_path = tmp_path / "assignals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 14:00",
        "signal_type": "reduce",
        "direction": "bearish_lean",
        "action": "reduce",
        "confidence": "medium",
        "data_status": "fresh",
        "trigger": {"type": "price_confirm", "price": 1680.0, "text": "冲高失败确认"},
        "invalidation": {"type": "price_break", "price": 1700.0, "text": "重回均线"},
        "position": {"max_total_pct": 20, "max_single_move_pct": 10},
        "risk_flags": ["limited_upside_space"],
        "summary": "冲高减仓",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("600519.SH", "贵州茅台", "冲高减仓", 1675.0)
    result = _latest_signal_summary(report, store_path=store_path)
    assert "减仓" in result
    assert "reduce" in result


def test_latest_signal_summary_shows_track(tmp_path):
    store_path = tmp_path / "tsignals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 10:30",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "high",
        "data_status": "fresh",
        "trigger": {"type": "price_confirm", "price": 57.0, "text": "站稳均线"},
        "invalidation": {"type": "price_break", "price": 55.5, "text": "跌破"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 15},
        "risk_flags": [],
        "summary": "已确认，保持跟踪",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("688248.SH", "南网科技", "优先候选", 57.2)
    result = _latest_signal_summary(report, store_path=store_path)
    assert "跟踪" in result


def test_latest_signal_summary_symbol_mismatch_returns_empty(tmp_path):
    store_path = tmp_path / "mismatch.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 10:00",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "high",
        "data_status": "fresh",
        "trigger": {"type": "price_confirm", "price": 57.0, "text": "站稳均线"},
        "invalidation": {"type": "price_break", "price": 55.5, "text": "跌破止损"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 15},
        "risk_flags": [],
        "summary": "跟踪中",
    }
    append_signal(sig, path=store_path)
    report = _fake_report("688248.SH", "南网科技", "低吸观察", 56.4)
    result = _latest_signal_summary(report, store_path=store_path)
    assert result == ""


def test_render_compare_includes_signal_summary(tmp_path):
    store_path = tmp_path / "compare.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 10:00",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "high",
        "data_status": "fresh",
        "trigger": {"type": "price_confirm", "price": 57.0, "text": "站稳"},
        "invalidation": {"type": "price_break", "price": 55.5, "text": "跌破"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 15},
        "risk_flags": [],
        "summary": "跟踪中",
    }
    append_signal(sig, path=store_path)

    report1 = _fake_report("688248.SH", "南网科技", "低吸观察", 56.4)
    report2 = _fake_report("601600.SH", "中国铝业", "等待确认", 11.5)
    old = DEFAULT_SIGNAL_STORE_PATH
    import signal_store as store_mod
    store_mod.DEFAULT_SIGNAL_STORE_PATH = store_path
    try:
        result = render_compare([report1, report2])
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old

    assert "南网科技" in result
    assert "跟踪" in result
    assert "中国铝业" in result
    assert "对比 —" in result
