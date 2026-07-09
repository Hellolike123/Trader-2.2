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


class TestGetMarginData(unittest.TestCase):

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_sse_stock_success(self, mock_check):
        """沪市股票（6开头）调用 stock_margin_detail_sse"""
        mock_ak = MagicMock()
        mock_df = pd.DataFrame({
            "标的证券": ["600519"],
            "融资余额(元)": [1250000000],
            "融资买入额(元)": [32000000],
            "融资偿还额(元)": [28000000],
            "融券卖出量(股)": [50000],
            "融券余额(元)": [80000000],
            "信用交易日期": ["2026-07-09"],
        })
        mock_ak.stock_margin_detail_sse.return_value = mock_df
        mock_ak.stock_margin_detail_szse.return_value = pd.DataFrame()

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_margin_data("600519")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "正常")
        self.assertAlmostEqual(res["margin_balance_wan"], 125000.0)
        self.assertAlmostEqual(res["margin_buy_wan"], 3200.0)
        self.assertEqual(res["date"], "2026-07-09")

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_szse_stock_success(self, mock_check):
        """深市股票（0/3开头）调用 stock_margin_detail_szse"""
        mock_ak = MagicMock()
        mock_df = pd.DataFrame({
            "证券代码": ["000001"],
            "融资余额(元)": [500000000],
            "融资买入额(元)": [15000000],
            "融资偿还额(元)": [12000000],
            "融券卖出量(股)": [30000],
            "融券余额(元)": [40000000],
            "日期": ["2026-07-09"],
        })
        mock_ak.stock_margin_detail_szse.return_value = mock_df
        mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame()

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_margin_data("000001")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "正常")
        self.assertAlmostEqual(res["margin_balance_wan"], 50000.0)

    @patch("trader_shared.extend_data._check_akshare", return_value=False)
    def test_akshare_not_available(self, mock_check):
        """akshare 不可用时返回接口不可用"""
        res = ExtendDataProvider.get_margin_data("600519")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["margin_balance_wan"], 0)

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_stock_not_found(self, mock_check):
        """股票不在融资融券列表中返回无数据"""
        mock_ak = MagicMock()
        mock_ak.stock_margin_detail_sse.return_value = pd.DataFrame({
            "标的证券": ["999999"],
            "融资余额(元)": [0],
        })
        mock_ak.stock_margin_detail_szse.return_value = pd.DataFrame()

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_margin_data("600519")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")


class TestGetNorthboundFlow(unittest.TestCase):

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_success(self, mock_check):
        mock_ak = MagicMock()
        mock_df = pd.DataFrame({
            "date": ["2026-07-09", "2026-07-08", "2026-07-07", "2026-07-04", "2026-07-03", "2026-07-02"],
            "value": [820000000, -350000000, 1200000000, 600000000, -200000000, 450000000],
        })
        mock_ak.stock_hsgt_north_net_flow_in_em.return_value = mock_df

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_northbound_flow()
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "正常")
        # 820000000 / 10000 = 82000 万 = 8.2 亿
        self.assertGreater(res["north_net_flow_wan"], 0)
        self.assertEqual(res["date"], "2026-07-09")

    @patch("trader_shared.extend_data._check_akshare", return_value=False)
    def test_akshare_not_available(self, mock_check):
        res = ExtendDataProvider.get_northbound_flow()
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["north_net_flow_wan"], 0)

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_empty_data(self, mock_check):
        mock_ak = MagicMock()
        mock_ak.stock_hsgt_north_net_flow_in_em.return_value = pd.DataFrame()

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_northbound_flow()
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")


class TestGetSectorData(unittest.TestCase):

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_success(self, mock_check):
        mock_ak = MagicMock()
        # 板块行情数据
        spot_df = pd.DataFrame({
            "板块名称": ["半导体", "银行", "医药"],
            "涨跌幅": [1.82, 0.5, -0.3],
        })
        mock_ak.stock_board_industry_spot_em.return_value = spot_df

        # 半导体板块成分股
        cons_df = pd.DataFrame({
            "代码": ["688248", "600519"],
        })
        mock_ak.stock_board_industry_cons_em.return_value = cons_df

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_sector_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "正常")
        self.assertEqual(res["sector_name"], "半导体")
        self.assertAlmostEqual(res["sector_change_pct"], 1.82)
        self.assertEqual(res["sector_rank"], 1)
        self.assertEqual(res["sector_total"], 3)

    @patch("trader_shared.extend_data._check_akshare", return_value=False)
    def test_akshare_not_available(self, mock_check):
        res = ExtendDataProvider.get_sector_data("688248")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["sector_name"], "")

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_stock_not_in_any_sector(self, mock_check):
        """股票不在前50板块中"""
        mock_ak = MagicMock()
        # 创建 60 个板块，每个都不含目标股票
        spot_df = pd.DataFrame({
            "板块名称": [f"板块{i}" for i in range(60)],
            "涨跌幅": [1.0 - i * 0.1 for i in range(60)],
        })
        mock_ak.stock_board_industry_spot_em.return_value = spot_df
        # 所有板块成分股都不含目标
        mock_ak.stock_board_industry_cons_em.return_value = pd.DataFrame({"代码": ["999999"]})

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_sector_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")
        self.assertEqual(res["sector_total"], 60)

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_api_exception(self, mock_check):
        """API 异常时返回无数据"""
        mock_ak = MagicMock()
        mock_ak.stock_board_industry_spot_em.side_effect = Exception("network error")

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_sector_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")


class TestGetConceptData(unittest.TestCase):

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_success(self, mock_check):
        mock_ak = MagicMock()
        # 概念板块行情
        spot_df = pd.DataFrame({
            "板块名称": ["人工智能", "芯片", "新能源"],
            "涨跌幅": [3.5, 2.1, -0.5],
        })
        mock_ak.stock_board_concept_spot_em.return_value = spot_df

        # 个股命中多个概念
        cons_ai = pd.DataFrame({"代码": ["688248", "600519"]})
        cons_chip = pd.DataFrame({"代码": ["688248"]})
        cons_ne = pd.DataFrame({"代码": ["999999"]})

        def _cons_side(symbol):
            if symbol == "人工智能":
                return cons_ai
            if symbol == "芯片":
                return cons_chip
            return cons_ne

        mock_ak.stock_board_concept_cons_em.side_effect = _cons_side

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_concept_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "正常")
        self.assertIn("人工智能", res["concept_list"])
        self.assertIn("芯片", res["concept_list"])
        self.assertEqual(len(res["concept_list"]), 2)
        self.assertEqual(res["concept_total"], 3)
        # 人工智能涨 3.5% → rank 1
        self.assertEqual(res["concept_rank"]["人工智能"]["rank"], 1)

    @patch("trader_shared.extend_data._check_akshare", return_value=False)
    def test_akshare_not_available(self, mock_check):
        res = ExtendDataProvider.get_concept_data("688248")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["concept_list"], [])

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_stock_not_in_any_concept(self, mock_check):
        mock_ak = MagicMock()
        spot_df = pd.DataFrame({
            "板块名称": [f"概念{i}" for i in range(60)],
            "涨跌幅": [1.0 - i * 0.1 for i in range(60)],
        })
        mock_ak.stock_board_concept_spot_em.return_value = spot_df
        mock_ak.stock_board_concept_cons_em.return_value = pd.DataFrame({"代码": ["999999"]})

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_concept_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")
        self.assertEqual(res["concept_total"], 60)

    @patch("trader_shared.extend_data._check_akshare", return_value=True)
    def test_api_exception(self, mock_check):
        mock_ak = MagicMock()
        mock_ak.stock_board_concept_spot_em.side_effect = Exception("network error")

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            import trader_shared.extend_data as ed
            old = ed._akshare_available
            ed._akshare_available = True
            try:
                res = ExtendDataProvider.get_concept_data("688248")
            finally:
                ed._akshare_available = old

        self.assertEqual(res["status"], "无数据")
