from __future__ import annotations

import unittest
import sys
from pathlib import Path

# Add shared paths
_ROOT = Path(__file__).resolve().parents[2]
_SHARED_MARKET = _ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
sys.path.insert(0, str(_SHARED_MARKET))

from light_data import sanitize_quote


class TestPriceOverflowGuard(unittest.TestCase):
    def test_sanitize_quote_filters_overflow_high_low(self):
        """确保如果 quote 中的 high/low 偏离当前价 20% 以上时能成功自愈"""
        corrupted_q = {
            "name": "南网科技",
            "symbol": "688248.SH",
            "current_price": 59.33,
            "pre_close": 57.50,
            "open": 58.00,
            "high": 6556720.00,  # 严重溢出的今日最高
            "low": 3195758.00,   # 严重溢出的今日最低
        }
        
        sanitized = sanitize_quote(corrupted_q)
        self.assertIsNotNone(sanitized)
        # 价格应该自动收敛，降级自愈为现价本身！
        self.assertEqual(sanitized["high"], 59.33)
        self.assertEqual(sanitized["low"], 59.33)

    def test_sanitize_quote_ignores_normal_range(self):
        """确保如果今日最高最低在正常波幅 20% 范围内时，不进行拦截干扰"""
        normal_q = {
            "name": "南网科技",
            "symbol": "688248.SH",
            "current_price": 59.33,
            "pre_close": 57.50,
            "open": 58.00,
            "high": 62.20,  # 涨约 4.8%，完全合理
            "low": 58.10,   # 跌约 2%，完全合理
        }
        
        sanitized = sanitize_quote(normal_q)
        self.assertIsNotNone(sanitized)
        self.assertEqual(sanitized["high"], 62.20)
        self.assertEqual(sanitized["low"], 58.10)


if __name__ == "__main__":
    unittest.main()
