# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date, timedelta

from trader_shared.extend_data import ExtendDataProvider, eastmoney_datacenter, ths_hot_reason


class TestExtendDataProvider(unittest.TestCase):

    @patch("trader_shared.extend_data.eastmoney_datacenter")
    def test_get_shareholder_trend_success(self, mock_datacenter):
        # Mock RPT_HOLDERNUMLATEST response
        mock_datacenter.return_value = [
            {
                "SECURITY_CODE": "300750",
                "HOLDER_NUM": 227422,
                "HOLDER_NUM_RATIO": -4.25,
                "HOLD_NOTICE_DATE": "2025-10-21 00:00:00"
            }
        ]
        
        res = ExtendDataProvider.get_shareholder_trend("300750")
        self.assertEqual(res["status"], "筹码集中")
        self.assertEqual(res["change_pct"], -4.25)
        self.assertEqual(res["latest_notice_date"], "2025-10-21")
        self.assertEqual(res["latest_holder_num"], 227422)

    @patch("trader_shared.extend_data.eastmoney_datacenter")
    def test_get_shareholder_trend_insufficient(self, mock_datacenter):
        mock_datacenter.return_value = []
        res = ExtendDataProvider.get_shareholder_trend("300750")
        self.assertEqual(res["status"], "数据不足")
        self.assertEqual(res["change_pct"], 0.0)

    @patch("trader_shared.extend_data.eastmoney_datacenter")
    def test_get_upcoming_unlocks(self, mock_datacenter):
        today_str = date.today().strftime("%Y-%m-%d")
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        mock_datacenter.return_value = [
            {
                "FREE_DATE": tomorrow_str + " 00:00:00",
                "FREE_RATIO": 0.0825,
                "CURRENT_FREE_SHARES": 5000.0
            },
            {
                "FREE_DATE": yesterday_str + " 00:00:00",
                "FREE_RATIO": 0.03,
                "CURRENT_FREE_SHARES": 2000.0
            }
        ]
        
        unlocks = ExtendDataProvider.get_upcoming_unlocks("300750")
        # Should filter out yesterday and keep tomorrow
        self.assertEqual(len(unlocks), 1)
        self.assertEqual(unlocks[0]["date"], tomorrow_str)
        self.assertEqual(unlocks[0]["ratio"], 8.25) # 0.0825 * 100
        self.assertEqual(unlocks[0]["amount_wan"], 5000.0)

    @patch("trader_shared.extend_data._http_get_text")
    def test_get_ths_consensus_eps_pandas(self, mock_get_text):
        # Mock HTML string containing a table
        html_content = """
        <html>
        <table>
            <tr><th>年度</th><th>预测机构数</th><th>最小值</th><th>均值</th><th>最大值</th></tr>
            <tr><td>2026</td><td>31</td><td>18.5</td><td>20.77</td><td>22.1</td></tr>
        </table>
        </html>
        """
        mock_get_text.return_value = html_content
        
        res = ExtendDataProvider.get_ths_consensus_eps("300750")
        self.assertEqual(res["source"], "ths")
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["year"], "2026.0")
        self.assertEqual(res["rows"][0]["avg_eps"], "20.77")

    @patch("trader_shared.extend_data.ths_hot_reason")
    def test_get_ths_hot_reason_cache(self, mock_hot_reason):
        mock_df = pd.DataFrame([
            {"代码": "300750", "名称": "宁德时代", "题材归因": "锂电池龙头", "涨幅%": "5.5"}
        ])
        mock_hot_reason.return_value = mock_df
        
        # First call, should trigger request
        res1 = ExtendDataProvider.get_ths_hot_reason_for_stock("300750")
        self.assertEqual(res1["reason"], "锂电池龙头")
        self.assertEqual(res1["change_pct"], "5.5")
        
        # Second call, should use cache (mock should only be called once)
        res2 = ExtendDataProvider.get_ths_hot_reason_for_stock("300750")
        self.assertEqual(res2["reason"], "锂电池龙头")
        mock_hot_reason.assert_called_once()
