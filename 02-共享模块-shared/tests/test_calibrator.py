from __future__ import annotations

import sys
from pathlib import Path

# Use absolute paths so pytest can find the module regardless of cwd
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent  # 02-共享模块-shared/
CANDIDATE = SHARED / "02-候选逻辑-candidate"
MARKET = SHARED / "01-行情数据-market-data"
SCRIPTS = SHARED / "scripts"
TRADER_SHARED = SHARED / "trader_shared"
for p in (SHARED, SCRIPTS, CANDIDATE, MARKET, TRADER_SHARED):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

import calibrator as cal


class TestBySignalType:
    def test_groups_by_type(self):
        trades = [
            {"signal_type": "低吸观察", "pnl_pct": 3.5, "days_held": 5},
            {"signal_type": "低吸观察", "pnl_pct": -1.2, "days_held": 3},
            {"signal_type": "等转强", "pnl_pct": 8.0, "days_held": 10},
        ]
        result = cal._by_signal_type(trades)
        assert len(result) == 2
        low = result["低吸观察"]
        assert low["count"] == 2
        assert low["win_rate"] == 0.5
        assert low["avg_gain"] == 3.5
        assert low["avg_loss"] == -1.2
        assert low["avg_days_held"] == 4
        assert low["best_pnl"] == 3.5
        assert low["worst_pnl"] == -1.2

    def test_empty(self):
        assert cal._by_signal_type([]) == {}

    def test_single_type(self):
        trades = [
            {"signal_type": "防守观察", "pnl_pct": 5.0, "days_held": 7},
        ]
        result = cal._by_signal_type(trades)
        assert result["防守观察"]["win_rate"] == 1.0
        assert result["防守观察"]["avg_loss"] == 0.0


class TestByMonth:
    def test_groups_by_month(self):
        trades = [
            {"exit_date": "2026-04-05", "pnl_pct": 3.5, "days_held": 5},
            {"exit_date": "2026-04-15", "pnl_pct": -1.2, "days_held": 3},
            {"exit_date": "2026-05-01", "pnl_pct": 2.1, "days_held": 7},
        ]
        result = cal._by_month(trades)
        assert "2026-04" in result
        assert "2026-05" in result
        assert result["2026-04"]["count"] == 2
        assert result["2026-04"]["wins"] == 1
        assert result["2026-04"]["total_return_pct"] == 2.3

    def test_empty(self):
        assert cal._by_month([]) == {}

    def test_unsorted_months(self):
        trades = [
            {"exit_date": "2026-06-10", "pnl_pct": 1.0, "days_held": 2},
            {"exit_date": "2026-03-05", "pnl_pct": 2.0, "days_held": 3},
        ]
        result = cal._by_month(trades)
        keys = list(result.keys())
        assert keys == ["2026-03", "2026-06"]


class TestComputeStats:
    def test_all_wins(self):
        trades = [
            {"pnl_pct": 5.0, "days_held": 3},
            {"pnl_pct": 10.0, "days_held": 5},
        ]
        stats = cal._compute_stats(trades)
        assert stats["total_trades"] == 2
        assert stats["win_rate"] == 1.0
        assert stats["avg_gain"] == 7.5
        assert stats["profit_factor"] == 999

    def test_all_losses(self):
        trades = [
            {"pnl_pct": -3.0, "days_held": 2},
            {"pnl_pct": -2.0, "days_held": 4},
        ]
        stats = cal._compute_stats(trades)
        assert stats["win_rate"] == 0.0
        assert stats["avg_loss"] == -2.5

    def test_empty(self):
        stats = cal._compute_stats([])
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0

    def test_max_drawdown(self):
        trades = [
            {"pnl_pct": 5.0},
            {"pnl_pct": -10.0},  # cumulative=-5, peak=5, drawdown=10
            {"pnl_pct": 3.0},   # cumulative=-2, peak=5, drawdown=7
        ]
        stats = cal._compute_stats(trades)
        assert stats["max_drawdown"] == 10.0
        assert stats["total_return"] == -2.0

    def test_profit_factor(self):
        trades = [
            {"pnl_pct": 10.0},
            {"pnl_pct": 5.0},
            {"pnl_pct": -3.0},
            {"pnl_pct": -2.0},
        ]
        stats = cal._compute_stats(trades)
        assert stats["profit_factor"] > 1


class TestGenerateSuggestions:
    def test_insufficient_trades(self):
        stats = {"total_trades": 3, "win_rate": 0.8, "max_drawdown": 5, "profit_factor": 2.0}
        by_signal = {}
        by_month = {}
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert len(suggestions) == 1
        assert "交易次数不足" in suggestions[0]

    def test_strong_strategy(self):
        stats = {"total_trades": 10, "win_rate": 0.70, "max_drawdown": 8, "profit_factor": 1.8}
        by_signal = {"低吸观察": {"count": 5, "win_rate": 0.80, "avg_gain": 0, "avg_loss": 0, "avg_days_held": 0, "best_pnl": 0, "worst_pnl": 0}}
        by_month = {}
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert any("策略有效" in s for s in suggestions)

    def test_weak_strategy(self):
        stats = {"total_trades": 10, "win_rate": 0.30, "max_drawdown": 8, "profit_factor": 0.8}
        by_signal = {"等转强": {"count": 5, "win_rate": 0.30, "avg_gain": 0, "avg_loss": 0, "avg_days_held": 0, "best_pnl": 0, "worst_pnl": 0}}
        by_month = {}
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert any("策略有效" not in s and "仅" in s for s in suggestions)

    def test_high_drawdown(self):
        stats = {"total_trades": 10, "win_rate": 0.60, "max_drawdown": 20, "profit_factor": 1.5}
        by_signal = {}
        by_month = {}
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert any("最大回撤" in s for s in suggestions)

    def test_monthly_trend_improvement(self):
        stats = {"total_trades": 10, "win_rate": 0.60, "max_drawdown": 5, "profit_factor": 1.5}
        by_signal = {}
        by_month = cal._by_month([
            {"exit_date": "2026-03-05", "pnl_pct": -2.0, "days_held": 2},
            {"exit_date": "2026-03-15", "pnl_pct": 5.0, "days_held": 3},  # 1 win + 1 loss = 50%
            {"exit_date": "2026-04-05", "pnl_pct": 8.0, "days_held": 4},
            {"exit_date": "2026-04-15", "pnl_pct": 6.0, "days_held": 5},  # 2 wins = 100%
        ])
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert any("改善" in s for s in suggestions)

    def test_monthly_trend_decline(self):
        stats = {"total_trades": 10, "win_rate": 0.40, "max_drawdown": 5, "profit_factor": 0.8}
        by_signal = {}
        # March 2 wins = 100%, April 1W1L = 50% → 100 > 50+10 → decline
        by_month = cal._by_month([
            {"exit_date": "2026-03-05", "pnl_pct": 5.0, "days_held": 2},
            {"exit_date": "2026-03-15", "pnl_pct": 3.0, "days_held": 3},
            {"exit_date": "2026-04-05", "pnl_pct": -8.0, "days_held": 4},
            {"exit_date": "2026-04-15", "pnl_pct": 2.0, "days_held": 5},
        ])
        suggestions = cal.generate_suggestions(stats, by_signal, by_month)
        assert any("下滑" in s for s in suggestions)


class TestDefaults:
    def test_default_signal_types(self):
        assert cal.DEFAULT_SIGNAL_TYPES == ("低吸观察", "等转强")

    def test_buy_signal_types(self):
        assert cal.BUY_SIGNAL_TYPES == ("低吸观察", "等转强", "防守观察", "空间不足")

    def test_all_signal_types(self):
        assert len(cal.ALL_SIGNAL_TYPES) >= 5


class TestPandasPath:
    def test_has_pandas_flag(self):
        assert hasattr(cal, "_HAS_PANDAS")
        assert isinstance(cal._HAS_PANDAS, bool)

    def test_compute_stats_pandas_same_result(self):
        trades = [
            {"pnl_pct": 5.0},
            {"pnl_pct": -10.0},
            {"pnl_pct": 3.0},
            {"pnl_pct": 7.0},
            {"pnl_pct": -4.0},
        ]
        stats = cal._compute_stats(trades)
        assert stats["total_trades"] == 5
        assert stats["win_rate"] in (0.6, 0.60)
        assert stats["max_drawdown"] == 10.0
        assert isinstance(stats["profit_factor"], (int, float))

    def test_by_signal_type_pandas_same_result(self):
        trades = [
            {"signal_type": "A", "pnl_pct": 10.0, "days_held": 3},
            {"signal_type": "A", "pnl_pct": -5.0, "days_held": 7},
            {"signal_type": "B", "pnl_pct": 2.0, "days_held": 1},
            {"signal_type": "B", "pnl_pct": -1.0, "days_held": 2},
            {"signal_type": "B", "pnl_pct": 8.0, "days_held": 5},
        ]
        result = cal._by_signal_type(trades)
        assert len(result) == 2
        assert result["A"]["count"] == 2
        assert result["A"]["win_rate"] == 0.5
        assert result["B"]["count"] == 3
        assert result["B"]["win_rate"] in (0.67, 2 / 3)
        # check pandas path produces same keys
        expected_keys = {"count", "win_rate", "avg_gain", "avg_loss", "avg_days_held", "best_pnl", "worst_pnl"}
        assert set(result["A"].keys()) == expected_keys

    def test_by_month_pandas_same_result(self):
        trades = [
            {"exit_date": "2026-01-05", "pnl_pct": 3.5},
            {"exit_date": "2026-01-20", "pnl_pct": -1.2},
            {"exit_date": "2026-02-10", "pnl_pct": 8.0},
        ]
        result = cal._by_month(trades)
        assert "2026-01" in result
        assert "2026-02" in result
        assert result["2026-01"]["count"] == 2
        assert result["2026-01"]["wins"] == 1
        assert result["2026-01"]["losses"] == 1
        # verify sorted
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_compute_stats_pandas_all_losses(self):
        trades = [
            {"pnl_pct": -2.0},
            {"pnl_pct": -5.0},
            {"pnl_pct": -1.0},
        ]
        stats = cal._compute_stats(trades)
        assert stats["win_rate"] == 0.0
        assert stats["total_return"] == -8.0

    def test_compute_stats_pandas_single_win(self):
        trades = [
            {"pnl_pct": 10.0},
            {"pnl_pct": -3.0},
        ]
        stats = cal._compute_stats(trades)
        assert stats["win_rate"] == 0.5
        assert stats["avg_loss"] == -3.0
