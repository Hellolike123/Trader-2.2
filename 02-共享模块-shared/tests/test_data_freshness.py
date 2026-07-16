"""data_freshness 语义测试：基于「数据最后日期 vs 应有数据的交易日」判定。

旧语义仅 is_trading_time() 为真才 live，导致盘前/盘后/周末跑当日数据被误标 stale。
新语义：数据覆盖到「应有数据的交易日」即 live，只有真·滞后（停牌/断更多日）才 stale。
"""
import unittest
from datetime import date, datetime

from trader_shared.trading_context import compute_data_freshness


class TestComputeDataFreshness(unittest.TestCase):
    def test_pre_market_allows_yesterday(self):
        # 周四盘前 01:47，数据是周三收盘 → live（之前误标 stale 的核心痛点）
        self.assertEqual(
            compute_data_freshness("2026-07-15", datetime(2026, 7, 16, 1, 47)), "live"
        )

    def test_trading_hours_needs_today(self):
        self.assertEqual(
            compute_data_freshness("2026-07-16", datetime(2026, 7, 16, 13, 30)), "live"
        )

    def test_post_market_needs_today(self):
        self.assertEqual(
            compute_data_freshness("2026-07-16", datetime(2026, 7, 16, 16, 0)), "live"
        )

    def test_stale_when_behind_in_trading_hours(self):
        # 周四盘中但数据停在周三 → stale（真滞后）
        self.assertEqual(
            compute_data_freshness("2026-07-15", datetime(2026, 7, 16, 13, 30)), "stale"
        )

    def test_weekend_allows_last_trading_day(self):
        self.assertEqual(compute_data_freshness("2026-07-17", date(2026, 7, 18)), "live")  # 周六
        self.assertEqual(compute_data_freshness("2026-07-17", date(2026, 7, 19)), "live")  # 周日

    def test_monday_pre_market_allows_friday(self):
        self.assertEqual(
            compute_data_freshness("2026-07-17", datetime(2026, 7, 20, 8, 0)), "live"
        )

    def test_suspended_stock_is_stale(self):
        # 周一盘中数据停在周三（停牌）→ stale
        self.assertEqual(
            compute_data_freshness("2026-07-15", datetime(2026, 7, 20, 10, 0)), "stale"
        )

    def test_none_is_stale(self):
        self.assertEqual(compute_data_freshness(None), "stale")

    def test_bad_string_is_stale(self):
        self.assertEqual(compute_data_freshness("garbage"), "stale")

    def test_default_as_of_now(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(compute_data_freshness(today), "live")


if __name__ == "__main__":
    unittest.main()
