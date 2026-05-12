from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── Path setup ──────────────────────────────────────────────
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent  # 02-共享模块-shared/
SCRIPTS = SHARED / "scripts"
CONTRACTS = SHARED / "03-输出校验-contracts"
for _p in (SHARED, SCRIPTS, CONTRACTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from signal_store import append_signal
from signal_tracker import (
    _normalize_symbol,
    _norm_date,
    _normalize_signal_type,
    _price_from_trigger,
    make_signal_id,
)


def test_append_signal_generates_signal_id(tmp_path):
    """Signal written without signal_id gets one auto-generated."""
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"type": "price_confirm", "price": 10.5, "text": "test"},
        "invalidation": {"type": "price_break", "price": 10.0, "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test summary",
    }

    store_path = tmp_path / "signals.jsonl"

    # Precondition: no signal_id
    assert "signal_id" not in signal, "Test precondition: signal has no signal_id"

    append_signal(signal, path=store_path)

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16

    # Verify ID matches make_signal_id
    expected_id = make_signal_id(
        symbol=_normalize_symbol("688248.SH"),
        date=_norm_date("2025-05-02"),
        signal_type=_normalize_signal_type("low_buy_watch"),
        price=str(_price_from_trigger(signal)),
    )
    assert written["signal_id"] == expected_id


def test_append_signal_preserves_existing_signal_id(tmp_path):
    """Signal already carrying signal_id is written unmodified."""
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "trade_date": "2025-05-01",
        "analysis_time": "2025-05-01 09:30:00",
        "signal_type": "track",
        "direction": "bullish",
        "action": "track",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"type": "price_confirm", "price": 1600.0, "text": "test"},
        "invalidation": {"type": "price_break", "price": 1550.0, "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test",
        "signal_id": "abcdef1234567890",  # Pre-existing
    }

    store_path = tmp_path / "signals.jsonl"
    append_signal(signal, path=store_path)

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert written["signal_id"] == "abcdef1234567890"  # Unchanged


def test_append_signal_for_review_result(tmp_path):
    """review_result type with no trigger.price gets signal_id with price='0.00'."""
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "review-trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 15:00:00",
        "signal_type": "review_result",
        "direction": "neutral",
        "action": "observe",
        "confidence": "medium",
        "data_status": "stale",
        "trigger": {"text": "缠论结构分析"},
        "invalidation": {"text": "威科夫量价背离"},
        "position": {"max_total_pct": 0, "max_single_move_pct": 0},
        "risk_flags": [],
        "summary": "复盘结论",
    }

    store_path = tmp_path / "signals.jsonl"
    append_signal(signal, path=store_path)

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16


def test_append_signal_two_signals_different_id(tmp_path):
    """Two different signals produce two different signal_ids."""
    sig1 = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish_lean",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"price": 10.5, "type": "price_confirm", "text": "test"},
        "invalidation": {"price": 10.0, "type": "price_break", "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test1",
    }
    sig2 = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2025-05-03",
        "analysis_time": "2025-05-03 10:00:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish_lean",
        "action": "observe",
        "confidence": "medium",
        "data_status": "full",
        "trigger": {"price": 10.5, "type": "price_confirm", "text": "test"},
        "invalidation": {"price": 10.0, "type": "price_break", "text": "test"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test2",
    }

    store_path = tmp_path / "signals.jsonl"
    append_signal(sig1, path=store_path)
    append_signal(sig2, path=store_path)

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    w1 = json.loads(lines[0])
    w2 = json.loads(lines[1])
    assert len(lines) == 2
    assert w1["signal_id"] != w2["signal_id"]  # Different dates --> different IDs
