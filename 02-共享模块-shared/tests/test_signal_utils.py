#!/usr/bin/env python3
"""Tests for signal_utils.py — the new shared utility module."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from pathlib import Path

UTILS_DIR = Path(__file__).resolve().parent.parent / "03-输出校验-contracts"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from signal_utils import (
    build_signal_key,
    normalize_date,
    normalize_signal_id,
    normalize_signal_type,
    normalize_symbol,
    price_from_trigger,
)


class TestNormalizeSignalId:
    def test_deterministic(self):
        id1 = normalize_signal_id("688248.SH", "2025-05-01", "low_buy_watch", "55.90")
        id2 = normalize_signal_id("688248.SH", "2025-05-01", "low_buy_watch", "55.90")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = normalize_signal_id("688248.SH", "2025-05-01", "low_buy_watch", "55.90")
        id2 = normalize_signal_id("688248.SH", "2025-05-01", "high_sell_watch", "55.90")
        assert id1 != id2

    def test_length(self):
        assert len(normalize_signal_id("a", "b", "c", "d")) == 16


class TestNormalizeSignalType:
    def test_chinese_legacy_to_english(self):
        assert normalize_signal_type("低吸观察") == "low_buy_watch"
        assert normalize_signal_type("高抛观察") == "high_sell_watch"

    def test_english_legacy_to_canonical(self):
        assert normalize_signal_type("low_buy") == "low_buy_watch"
        assert normalize_signal_type("high_sell") == "high_sell_watch"

    def test_pass_through(self):
        assert normalize_signal_type("low_buy_watch") == "low_buy_watch"
        assert normalize_signal_type("high_sell_triggered") == "high_sell_triggered"

    def test_unknown_passthrough(self):
        assert normalize_signal_type("unknown_type") == "unknown_type"


class TestNormalizeDate:
    def test_standard_zero_padded(self):
        assert normalize_date("2025-05-01") == "2025-05-01"

    def test_non_zero_padded(self):
        assert normalize_date("2025-5-2") == "2025-05-02"

    def test_datetime_string(self):
        assert normalize_date("2025-05-01T14:30:00") == "2025-05-01"
        assert normalize_date("2025-05-01 10:00") == "2025-05-01"

    def test_other_formats(self):
        result = normalize_date("not-a-date")
        assert result == "not-a-date"[:10]


class TestNormalizeSymbol:
    def test_shanghai_6xx(self):
        assert normalize_symbol("600519") == "600519.SH"

    def test_shanghai_5xx(self):
        assert normalize_symbol("510300") == "510300.SH"

    def test_shanghai_9xx(self):
        assert normalize_symbol("900901") == "900901.SH"

    def test_shenzhen_0xx(self):
        assert normalize_symbol("000001") == "000001.SZ"

    def test_shenzhen_3xx(self):
        assert normalize_symbol("300750") == "300750.SZ"

    def test_already_has_suffix(self):
        assert normalize_symbol("688248.SH") == "688248.SH"
        assert normalize_symbol("000001.SZ") == "000001.SZ"

    def test_empty(self):
        assert normalize_symbol("") == ""
        assert normalize_symbol(None) is None  # type: ignore[arg-type]


class TestPriceFromTrigger:
    def test_trigger_price(self):
        assert price_from_trigger({"trigger": {"price": 55.9}}) == "55.90"

    def test_trigger_zero_price_returns_none(self):
        assert price_from_trigger({"trigger": {"price": 0}}) is None
        assert price_from_trigger({"trigger": {"price": -1}}) is None

    def test_current_fallback(self):
        assert price_from_trigger({"current": 42.5}) == "42.50"

    def test_no_price_returns_none(self):
        assert price_from_trigger({}) is None

    def test_trigger_over_current(self):
        sig = {"trigger": {"price": 100.0}, "current": 90.0}
        assert price_from_trigger(sig) == "100.00"


class TestBuildSignalKey:
    def test_key_components(self):
        sig = {
            "symbol": "688248",
            "trade_date": "2025-5-2",
            "signal_type": "低吸观察",
            "trigger": {"price": 55.9},
        }
        key = build_signal_key(sig)
        assert key[0] == "688248.SH"
        assert key[1] == "2025-05-02"
        assert key[2] == "low_buy_watch"
        assert key[3] == "55.90"

    def test_normalized_signal_types(self):
        sig = {
            "symbol": "600519",
            "trade_date": "2025-01-15",
            "signal_type": "high_sell",
            "trigger": {"price": 1800.0},
        }
        key = build_signal_key(sig)
        assert key[2] == "high_sell_watch"

        sig["signal_type"] = "low_buy_watch"
        key2 = build_signal_key(sig)
        assert key2[2] == "low_buy_watch"

    def test_different_prices_different_keys(self):
        base = {"symbol": "688248", "trade_date": "2025-01-01",
                "signal_type": "low_buy_watch", "trigger": {"price": 50.0}}
        key1 = build_signal_key(base)
        base2 = dict(base)
        base2["trigger"] = {"price": 55.0}
        key2 = build_signal_key(base2)
        assert key1[3] != key2[3]
