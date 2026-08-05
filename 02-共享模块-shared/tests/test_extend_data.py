# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date, timedelta

from trader_shared.extend_data import ExtendDataProvider, ths_hot_reason


class _FakeTsClient:
    def __init__(self, hold_rows=None, float_rows=None):
        self.hold_rows = hold_rows or []
        self.float_rows = float_rows or []

    def query_stk_holdernumber(self, ts_code: str, start_date: str = "", end_date: str = ""):
        return list(self.hold_rows)

    def query_share_float(self, ts_code: str, start_date: str = "", end_date: str = ""):
        rows = list(self.float_rows)
        if start_date or end_date:
            out = []
            for r in rows:
                d = str(r.get("float_date") or "").replace("-", "")
                if start_date and d and d < start_date:
                    continue
                if end_date and d and d > end_date:
                    continue
                out.append(r)
            return out
        return rows


class TestExtendDataProvider(unittest.TestCase):

    @patch("trader_shared.tushare_client.get_client")
    def test_get_shareholder_trend_success(self, mock_get_client):
        mock_get_client.return_value = _FakeTsClient(hold_rows=[
            {
                "ts_code": "300750.SZ",
                "ann_date": "20251001",
                "end_date": "20250930",
                "holder_num": 237422,
            },
            {
                "ts_code": "300750.SZ",
                "ann_date": "20251021",
                "end_date": "20251020",
                "holder_num": 227422,
            },
        ])

        res = ExtendDataProvider.get_shareholder_trend("300750")
        self.assertEqual(res["status"], "筹码集中")
        self.assertAlmostEqual(res["change_pct"], -4.21, places=1)
        self.assertEqual(res["latest_notice_date"], "2025-10-21")
        self.assertEqual(res["latest_holder_num"], 227422)
        self.assertEqual(res["source"], "tushare")

    @patch("trader_shared.tushare_client.get_client")
    def test_get_shareholder_trend_insufficient(self, mock_get_client):
        mock_get_client.return_value = _FakeTsClient(hold_rows=[])
        res = ExtendDataProvider.get_shareholder_trend("300750")
        self.assertEqual(res["status"], "数据不足")
        self.assertEqual(res["change_pct"], 0.0)

    @patch("trader_shared.tushare_client.get_client")
    def test_get_upcoming_unlocks(self, mock_get_client):
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        mock_get_client.return_value = _FakeTsClient(float_rows=[
            {
                "ts_code": "300750.SZ",
                "float_date": tomorrow_str.replace("-", ""),
                "float_ratio": 0.0825,
                "float_share": 5000.0,  # 万股
            },
            {
                "ts_code": "300750.SZ",
                "float_date": yesterday_str.replace("-", ""),
                "float_ratio": 0.03,
                "float_share": 2000.0,
            },
        ])

        unlocks = ExtendDataProvider.get_upcoming_unlocks("300750")
        self.assertEqual(len(unlocks), 1)
        self.assertEqual(unlocks[0]["date"], tomorrow_str)
        self.assertEqual(unlocks[0]["ratio"], 8.25)
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

    @patch("trader_shared.tushare_client.get_client")
    def test_sse_stock_success(self, mock_get_client):
        mock_get_client.return_value = _FakeTsClient()
        # attach margin rows via dynamic fake
        class C(_FakeTsClient):
            def query_margin_detail(self, ts_code="", trade_date="", start_date="", end_date=""):
                return [{
                    "ts_code": "600519.SH",
                    "trade_date": "20260709",
                    "rzye": 1250000000,
                    "rzmre": 32000000,
                    "rzche": 28000000,
                    "rqmcl": 50000,
                    "rqye": 80000000,
                }]
        mock_get_client.return_value = C()
        res = ExtendDataProvider.get_margin_data("600519")
        self.assertEqual(res["status"], "正常")
        self.assertAlmostEqual(res["margin_balance_wan"], 125000.0)
        self.assertAlmostEqual(res["margin_buy_wan"], 3200.0)
        self.assertEqual(res["date"], "2026-07-09")
        self.assertEqual(res["source"], "tushare")

    @patch("trader_shared.tushare_client.get_client")
    def test_szse_stock_success(self, mock_get_client):
        class C(_FakeTsClient):
            def query_margin_detail(self, ts_code="", trade_date="", start_date="", end_date=""):
                return [{
                    "ts_code": "000001.SZ",
                    "trade_date": "20260709",
                    "rzye": 500000000,
                    "rzmre": 15000000,
                    "rzche": 12000000,
                    "rqmcl": 30000,
                    "rqye": 40000000,
                }]
        mock_get_client.return_value = C()
        res = ExtendDataProvider.get_margin_data("000001")
        self.assertEqual(res["status"], "正常")
        self.assertAlmostEqual(res["margin_balance_wan"], 50000.0)

    @patch("trader_shared.tushare_client.get_client", side_effect=RuntimeError("no token"))
    def test_client_unavailable(self, mock_get_client):
        res = ExtendDataProvider.get_margin_data("600519")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["margin_balance_wan"], 0)

    @patch("trader_shared.tushare_client.get_client")
    def test_stock_not_found(self, mock_get_client):
        class C(_FakeTsClient):
            def query_margin_detail(self, **kwargs):
                return []
        mock_get_client.return_value = C()
        res = ExtendDataProvider.get_margin_data("600519")
        self.assertEqual(res["status"], "无数据")


class TestGetNorthboundFlow(unittest.TestCase):

    @patch("trader_shared.tushare_client.get_client")
    def test_success(self, mock_get_client):
        class C(_FakeTsClient):
            def query_moneyflow_hsgt(self, start_date="", end_date="", trade_date=""):
                return [
                    {"trade_date": "20260703", "north_money": -2000},
                    {"trade_date": "20260704", "north_money": 6000},
                    {"trade_date": "20260707", "north_money": 12000},
                    {"trade_date": "20260708", "north_money": -3500},
                    {"trade_date": "20260709", "north_money": 8200},
                ]
        mock_get_client.return_value = C()
        res = ExtendDataProvider.get_northbound_flow()
        self.assertEqual(res["status"], "正常")
        self.assertGreater(res["north_net_flow_wan"], 0)
        self.assertEqual(res["date"], "2026-07-09")
        self.assertEqual(res["source"], "tushare")

    @patch("trader_shared.tushare_client.get_client", side_effect=RuntimeError("no token"))
    def test_client_unavailable(self, mock_get_client):
        res = ExtendDataProvider.get_northbound_flow()
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["north_net_flow_wan"], 0)

    @patch("trader_shared.tushare_client.get_client")
    def test_empty(self, mock_get_client):
        class C(_FakeTsClient):
            def query_moneyflow_hsgt(self, **kwargs):
                return []
        mock_get_client.return_value = C()
        res = ExtendDataProvider.get_northbound_flow()
        self.assertEqual(res["status"], "无数据")



class TestGetSectorData(unittest.TestCase):

    @patch("trader_shared.sector_data.get_stock_sector_snapshot_cached")
    def test_success(self, mock_snap):
        mock_snap.return_value = {
            "industry": "半导体",
            "sector_name": "半导体",
            "sector_code": "885556.TI",
            "sector_change_pct": 1.82,
            "sector_rank": 1,
            "sector_total": 3,
            "status": "正常",
        }
        res = ExtendDataProvider.get_sector_data("688248")
        self.assertEqual(res["status"], "正常")
        self.assertEqual(res["sector_name"], "半导体")
        self.assertAlmostEqual(res["sector_change_pct"], 1.82)
        self.assertEqual(res["source"], "tushare")

    @patch("trader_shared.sector_data.get_stock_sector_snapshot_cached", side_effect=RuntimeError("x"))
    def test_client_unavailable(self, mock_snap):
        res = ExtendDataProvider.get_sector_data("688248")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["sector_name"], "")

    @patch("trader_shared.sector_data.get_stock_sector_snapshot_cached")
    def test_stock_not_in_any_sector(self, mock_snap):
        mock_snap.return_value = {"industry": "银行", "status": "未匹配板块"}
        res = ExtendDataProvider.get_sector_data("688248")
        self.assertEqual(res["status"], "无数据")


class TestGetConceptData(unittest.TestCase):

    @patch("trader_shared.sector_data.get_concept_detail")
    @patch("trader_shared.sector_data.get_concept_list")
    def test_success(self, mock_list, mock_detail):
        mock_list.return_value = [
            {"code": "TS001", "name": "人工智能", "pct_change": 3.5},
            {"code": "TS002", "name": "芯片", "pct_change": 2.1},
            {"code": "TS003", "name": "新能源", "pct_change": -0.5},
        ]
        def _detail(cid):
            if cid == "TS001":
                return [{"ts_code": "688248.SH"}]
            if cid == "TS002":
                return [{"ts_code": "688248.SH"}]
            return [{"ts_code": "999999.SZ"}]
        mock_detail.side_effect = _detail
        res = ExtendDataProvider.get_concept_data("688248")
        self.assertEqual(res["status"], "正常")
        self.assertIn("人工智能", res["concept_list"])
        self.assertIn("芯片", res["concept_list"])
        self.assertEqual(res["source"], "tushare")

    @patch("trader_shared.sector_data.get_concept_list", side_effect=RuntimeError("x"))
    def test_client_unavailable(self, mock_list):
        res = ExtendDataProvider.get_concept_data("688248")
        self.assertEqual(res["status"], "接口不可用")
        self.assertEqual(res["concept_list"], [])

    @patch("trader_shared.sector_data.get_concept_detail", return_value=[{"ts_code":"999999.SZ"}])
    @patch("trader_shared.sector_data.get_concept_list")
    def test_stock_not_in_any_concept(self, mock_list, mock_detail):
        mock_list.return_value = [{"code": "TS001", "name": "人工智能", "pct_change": 1.0}]
        res = ExtendDataProvider.get_concept_data("688248")
        self.assertEqual(res["status"], "无数据")


