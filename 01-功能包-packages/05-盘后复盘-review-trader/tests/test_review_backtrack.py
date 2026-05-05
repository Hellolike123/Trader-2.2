#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACTS = ROOT.parents[1] / "02-共享模块-shared" / "03-输出校验-contracts"
MARKET = ROOT.parents[1] / "02-共享模块-shared" / "01-行情数据-market-data"
CANDIDATE = ROOT.parents[1] / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
for _p in (SCRIPTS, CONTRACTS, MARKET, CANDIDATE, SHARED_ROOT):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for name in ("signal_store", "models", "signal_contract"):
    sys.modules.pop(name, None)

from signal_store import append_signal, DEFAULT_SIGNAL_STORE_PATH
from review_model import enrich_with_signal_backtrack


def test_enrich_with_signal_backtrack_finds_same_day(tmp_path):
    store_path = tmp_path / "rt_signals.jsonl"
    sig = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
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

    review = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "date": "2026-05-01",
    }
    import signal_store as store_mod
    old = store_mod.DEFAULT_SIGNAL_STORE_PATH
    store_mod.DEFAULT_SIGNAL_STORE_PATH = store_path
    try:
        enrich_with_signal_backtrack(review)
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old

    assert len(review["historical_signals"]) >= 1


def test_enrich_with_signal_backtrack_no_symbol(tmp_path):
    review = {
        "symbol": "",
        "name": "未知股票",
        "date": "2026-05-01",
    }
    enrich_with_signal_backtrack(review)
    assert review["historical_signals"] == []


def test_enrich_with_signal_backtrack_no_signals_in_store(tmp_path):
    store_path = tmp_path / "empty.jsonl"
    review = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "date": "2026-05-01",
    }
    import signal_store as store_mod
    old = store_mod.DEFAULT_SIGNAL_STORE_PATH
    store_mod.DEFAULT_SIGNAL_STORE_PATH = store_path
    try:
        enrich_with_signal_backtrack(review, limit=10)
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old

    assert review["historical_signals"] == []


def test_enrich_with_signal_backtrack_filters_same_day(tmp_path):
    store_path = tmp_path / "filter.jsonl"
    # Add a signal for a different date
    sig_diff = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2026-04-30",
        "analysis_time": "2026-04-30 15:00",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "medium",
        "data_status": "fresh",
        "trigger": {"type": "price_confirm", "price": 56.0, "text": "站稳"},
        "invalidation": {"type": "price_break", "price": 55.0, "text": "跌破"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 15},
        "risk_flags": [],
        "summary": "跟踪中",
    }
    append_signal(sig_diff, path=store_path)

    review = {
        "symbol": "688248.SH",
        "name": "南网科技",
        "date": "2026-05-01",
    }
    import signal_store as store_mod
    old = store_mod.DEFAULT_SIGNAL_STORE_PATH
    store_mod.DEFAULT_SIGNAL_STORE_PATH = store_path
    try:
        enrich_with_signal_backtrack(review, limit=10)
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old

    # Should fall back to last N signals when no same-day match
    assert len(review["historical_signals"]) >= 1


def test_backward_compat_empty_symbols(tmp_path):
    store_path = tmp_path / "compat.jsonl"
    review = {}
    import signal_store as store_mod
    old = store_mod.DEFAULT_SIGNAL_STORE_PATH
    store_mod.DEFAULT_SIGNAL_STORE_PATH = store_path
    try:
        enrich_with_signal_backtrack(review)
    finally:
        store_mod.DEFAULT_SIGNAL_STORE_PATH = old

    assert review["historical_signals"] == []
