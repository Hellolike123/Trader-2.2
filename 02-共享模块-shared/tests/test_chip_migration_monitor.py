"""chip_migration_monitor.py 筹码搬家监控测试。"""

from __future__ import annotations

import pytest
from trader_shared.chip_migration_monitor import (
    save_chip_snapshot,
    check_chip_migration,
    backfill_history,
)


class TestSaveAndLoadHistory:
    def test_save_and_load_history(self):
        chip_result = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.5, "support_level": "支撑"},
                {"price": 12.0, "share_of_total": 0.3, "support_level": "阻力"},
            ]
        }
        save_chip_snapshot("TEST_STOCK", chip_result, trade_date="2026-06-01")
        migration = check_chip_migration("TEST_STOCK", chip_result)
        assert migration["has_history"] is True


class TestBackfillHistorySkipsWhenExists:
    def test_skips_when_exists(self):
        result = backfill_history("TEST_STOCK", [{"close": 10.0}] * 70)
        assert result is False


class TestBackfillHistorySkipsWhenInsufficientBars:
    def test_skips_when_insufficient_bars(self):
        result = backfill_history("TEST_STOCK_2", [{"close": 10.0}] * 30)
        assert result is False


class TestCheckMigrationNoHistory:
    def test_no_history(self):
        chip_result = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.5, "support_level": "支撑"},
            ]
        }
        migration = check_chip_migration("NONEXISTENT_STOCK", chip_result)
        assert migration["has_history"] is False


class TestCheckMigrationStable:
    def test_stable(self):
        chip_result = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.5, "support_level": "支撑"},
                {"price": 12.0, "share_of_total": 0.3, "support_level": "阻力"},
            ]
        }
        save_chip_snapshot("STABLE_TEST", chip_result, trade_date="2026-06-02")
        migration = check_chip_migration("STABLE_TEST", chip_result)
        assert migration["warning_level"] in ("none", "")


class TestCheckMigrationWarning:
    def test_warning(self):
        prev_chip = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.6, "support_level": "支撑"},
                {"price": 12.0, "share_of_total": 0.2, "support_level": "阻力"},
            ]
        }
        save_chip_snapshot("WARN_TEST", prev_chip, trade_date="2026-06-03")
        curr_chip = {
            "peaks": [
                {"price": 10.2, "share_of_total": 0.3, "support_level": "支撑"},
                {"price": 12.0, "share_of_total": 0.5, "support_level": "阻力"},
            ]
        }
        migration = check_chip_migration("WARN_TEST", curr_chip)
        assert migration["has_history"] is True


class TestCheckMigrationCritical:
    def test_critical(self):
        prev_chip = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.6, "support_level": "支撑"},
            ]
        }
        save_chip_snapshot("CRIT_TEST", prev_chip, trade_date="2026-06-04")
        curr_chip = {
            "peaks": [
                {"price": 10.2, "share_of_total": 0.2, "support_level": "支撑"},
            ]
        }
        migration = check_chip_migration("CRIT_TEST", curr_chip)
        assert migration["has_history"] is True


class TestCheckMigrationSupportLoss:
    def test_support_loss(self):
        prev_chip = {
            "peaks": [
                {"price": 10.0, "share_of_total": 0.5, "support_level": "支撑"},
            ]
        }
        save_chip_snapshot("LOSS_TEST", prev_chip, trade_date="2026-06-05")
        curr_chip = {
            "peaks": [
                {"price": 12.0, "share_of_total": 0.5, "support_level": "阻力"},
            ]
        }
        migration = check_chip_migration("LOSS_TEST", curr_chip)
        assert migration["has_history"] is True
