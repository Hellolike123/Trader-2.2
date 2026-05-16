"""Tests for order_book.py — five-level order book analysis for T0 monitoring."""
from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
CANDIDATE = TESTS_DIR.parent / "02-候选逻辑-candidate"
if str(CANDIDATE.resolve()) not in sys.path:
    sys.path.insert(0, str(CANDIDATE.resolve()))

from order_book import analyze


def test_analyze_buy_strong():
    ob = {
        "bids": [
            {"price": 38.5, "volume": 5000},
            {"price": 38.49, "volume": 3000},
        ],
        "asks": [
            {"price": 38.51, "volume": 1000},
            {"price": 38.52, "volume": 500},
        ],
        "bid_total": 8000,
        "ask_total": 1500,
        "imbalance": 5.33,
    }
    result = analyze(ob)
    assert result["direction"] == "buy_strong"
    assert "买盘强" in result["line"]


def test_analyze_buy_lean_with_wall():
    ob = {
        "bids": [
            {"price": 38.5, "volume": 1000},
            {"price": 38.49, "volume": 1000},
            {"price": 38.48, "volume": 4000},
        ],
        "asks": [
            {"price": 38.51, "volume": 1500},
            {"price": 38.52, "volume": 1000},
            {"price": 38.53, "volume": 500},
        ],
        "bid_total": 6000,
        "ask_total": 3000,
        "imbalance": 2.0,
    }
    result = analyze(ob)
    assert result["direction"] == "buy_strong"
    assert "护盘" in result["line"]


def test_analyze_sell_strong():
    ob = {
        "bids": [
            {"price": 38.5, "volume": 500},
            {"price": 38.49, "volume": 500},
        ],
        "asks": [
            {"price": 38.51, "volume": 3000},
            {"price": 38.52, "volume": 2000},
        ],
        "bid_total": 1000,
        "ask_total": 5000,
        "imbalance": 0.2,
    }
    result = analyze(ob)
    assert result["direction"] == "sell_strong"
    assert "卖盘强" in result["line"]


def test_analyze_balanced():
    ob = {
        "bids": [
            {"price": 38.5, "volume": 1000},
        ],
        "asks": [
            {"price": 38.51, "volume": 1000},
        ],
        "bid_total": 1000,
        "ask_total": 1000,
        "imbalance": 1.0,
    }
    result = analyze(ob)
    assert result["direction"] == "balanced"
    assert "均衡" in result["line"]


def test_analyze_none():
    result = analyze(None)
    assert result["direction"] == "none"
    assert "缺失" in result["line"]


def test_analyze_wall_detection():
    ob = {
        "bids": [
            {"price": 38.5, "volume": 500},
            {"price": 38.49, "volume": 500},
            {"price": 38.48, "volume": 500},
            {"price": 38.47, "volume": 4000},
        ],
        "asks": [
            {"price": 38.51, "volume": 200},
            {"price": 38.52, "volume": 500},
        ],
        "bid_total": 5500,
        "ask_total": 700,
        "imbalance": 7.86,
    }
    result = analyze(ob)
    walls = result["walls"]
    assert "support_wall" in walls
    assert walls["support_wall"]["price"] == 38.47
    assert walls["support_wall"]["volume"] == 4000
