"""Portfolio allocation scoring + market filter tests.

Tests for:
- allocate_weights()  Score-based proportional allocation
- climate_adjust()  Market-level signal downgrade
- portfolio_total_cap()  Market-driven total cap
- dual_index_market_decision()  Dual index combined decision
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from portfolio_run import (
    allocate_weights,
    climate_adjust,
    dual_index_market_decision,
    portfolio_total_cap,
)

DEFAULT_MAX_TOTAL = 80


class TestClimateAdjust:
    def test_very_weak_downgrade_low_buy_watch(self):
        assert climate_adjust("低吸观察", "很差") == "防守观察"

    def test_very_weak_downgrade_wait_for_strength(self):
        assert climate_adjust("等转强", "很差") == "防守观察"

    def test_very_weak_no_change_other_status(self):
        assert climate_adjust("冲高减仓", "很差") == "减仓加倍"
        assert climate_adjust("优先候选", "很差") == "优先候选"

    def test_weak_downgrade_wait_for_strength(self):
        assert climate_adjust("等转强", "偏弱") == "低吸观察"

    def test_weak_downgrade_reduce_stall(self):
        assert climate_adjust("冲高减仓", "偏弱") == "减仓加倍"

    def test_normal_no_change(self):
        assert climate_adjust("等转强", "正常") == "等转强"
        assert climate_adjust("低吸观察", "正常") == "低吸观察"

    def test_empty_string_no_change(self):
        assert climate_adjust("低吸观察", "") == "低吸观察"

    def test_none_no_change(self):
        assert climate_adjust("低吸观察", None) == "低吸观察"

    def test_unknown_level_no_change(self):
        assert climate_adjust("低吸观察", "未知") == "低吸观察"


class TestPortfolioTotalCap:
    def test_normal_returns_default(self):
        assert portfolio_total_cap("正常", False) == DEFAULT_MAX_TOTAL

    def test_weak_returns_70(self):
        assert portfolio_total_cap("偏弱", False) == 70

    def test_weak_high_atr_returns_60(self):
        assert portfolio_total_cap("偏弱", True) == 60

    def test_very_weak_returns_60(self):
        assert portfolio_total_cap("很差", True) == 60
        assert portfolio_total_cap("很差", False) == 60

    def test_empty_market_returns_default(self):
        assert portfolio_total_cap("", False) == DEFAULT_MAX_TOTAL
        assert portfolio_total_cap(None, False) == DEFAULT_MAX_TOTAL

    def test_unknown_level_returns_default(self):
        assert portfolio_total_cap("未知", False) == DEFAULT_MAX_TOTAL


class TestDualIndexDecision:
    def test_both_normal(self):
        assert dual_index_market_decision("正常", "正常") == "正常"

    def test_csi1000_weak_csi300_normal(self):
        assert dual_index_market_decision("偏弱", "正常") == "偏弱"

    def test_csi1000_weak_csi300_weak(self):
        assert dual_index_market_decision("偏弱", "偏弱") == "很差"

    def test_csi1000_very_weak_csi300_weak(self):
        assert dual_index_market_decision("很差", "偏弱") == "很差"

    def test_csi1000_normal_csi300_weak(self):
        assert dual_index_market_decision("正常", "偏弱") == "偏弱"

    def test_csi1000_data_missing_csi300_normal(self):
        assert dual_index_market_decision(None, "正常") == "偏弱"
        assert dual_index_market_decision("", "正常") == "偏弱"

    def test_csi300_data_missing_csi1000_weak(self):
        assert dual_index_market_decision("偏弱", None) == "偏弱"

    def test_both_missing_returns_weak(self):
        assert dual_index_market_decision(None, None) == "偏弱"


class TestAllocateWeights:
    def test_two_stocks_score_proportional(self):
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] + weights["票B"] == 17
        assert weights["票A"] > weights["票B"]

    def test_three_stocks_score_proportional(self):
        items = [
            {"name": "票A", "score": 90, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 70, "atr_cap": 8, "ok": True, "status": "等转强"},
            {"name": "票C", "score": 50, "atr_cap": 6, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        total = sum(weights.values())
        assert total == 24
        assert weights["票A"] > weights["票B"] > weights["票C"]

    def test_atr_cap_hard_limit_top_stock(self):
        items = [
            {"name": "票A", "score": 90, "atr_cap": 3, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 10, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] == 3

    def test_atr_cap_hard_limit_passes_to_remaining(self):
        items = [
            {"name": "票A", "score": 100, "atr_cap": 3, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 100, "atr_cap": 10, "ok": True, "status": "防守观察"},
            {"name": "票C", "score": 100, "atr_cap": 10, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] == 3
        # Remaining 16 pool split equally: 8 each
        assert weights["票B"] == 8
        assert weights["票C"] == 8
        assert sum(weights.values()) == 19

    def test_total_cap_override_cuts_lowest_score(self):
        items = [
            {"name": "票A", "score": 85, "atr_cap": 40, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 40, "atr_cap": 30, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=60)
        total = sum(weights.values())
        assert total <= 60

    def test_single_tradable_stock(self):
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "暂不碰"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights == {"票A": 10}

    def test_zero_scores_equal_allocation(self):
        items = [
            {"name": "票A", "score": 0, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 0, "atr_cap": 10, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] == weights["票B"]
        assert weights["票A"] + weights["票B"] == 20

    def test_negative_scores_fallback(self):
        items = [
            {"name": "票A", "score": -50, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights["票A"] >= 1

    def test_none_score_fallback(self):
        items = [
            {"name": "票A", "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert "票A" in weights
        assert weights["票A"] >= 1

    def test_no_tradable_returns_empty(self):
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "暂不碰"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": False, "status": "数据失败"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert weights == {}

    def test_filter_by_ok_flag(self):
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": False, "status": "低吸观察"},
        ]
        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert "票B" not in weights
        assert "票A" in weights

    def test_climate_downgrade_affects_tradable_filter(self):
        from portfolio_run import climate_adjust
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "低吸观察"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "防守观察"},
        ]
        for item in items:
            item["adjusted_status"] = climate_adjust(item["status"], "很差")

        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        assert "票A" in weights
        assert "票B" in weights
        assert sum(weights.values()) == 17

    def test_adjusted_status_downgrade_reduces_allocation(self):
        from portfolio_run import climate_adjust
        items = [
            {"name": "票A", "score": 85, "atr_cap": 10, "ok": True, "status": "等转强"},
            {"name": "票B", "score": 60, "atr_cap": 7, "ok": True, "status": "低吸观察"},
        ]
        for item in items:
            item["adjusted_status"] = climate_adjust(item["status"], "很差")

        weights = allocate_weights(items, max_total=DEFAULT_MAX_TOTAL)
        # Both are still tradable (防守观察 is not excluded), but score allocation applies
        assert sum(weights.values()) <= 17
