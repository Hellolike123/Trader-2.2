# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import time
import warnings
from datetime import datetime, date
from io import StringIO
from typing import Any

import requests
import pandas as pd

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

# akshare 可用性缓存（避免重复 import 尝试）
_akshare_available: bool | None = None
AKSHARE_ENABLED = os.environ.get("AKSHARE_ENABLED", "true").lower() in ("true", "1", "yes")


def _check_akshare() -> bool:
    """检查 akshare 是否可用，结果缓存到模块级变量。"""
    global _akshare_available
    if _akshare_available is not None:
        return _akshare_available
    if not AKSHARE_ENABLED:
        _akshare_available = False
        return False
    try:
        import akshare  # noqa: F401
        _akshare_available = True
    except ImportError:
        _logger.debug("akshare 未安装，跳过相关数据采集")
        _akshare_available = False
    return _akshare_available

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def _http_get_json(url: str, params: dict[str, Any] | None = None) -> dict:
    """Helper to perform HTTP GET returning JSON via requests for SSL safety on macOS."""
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except (requests.RequestException, ValueError) as e:
        _logger.debug("HTTP GET JSON failed for %s: %s", url, e)
    return {}

def _http_get_text(url: str, referer: str | None = None, encoding: str = "utf-8") -> str:
    """Helper to perform HTTP GET returning plain text via requests."""
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = encoding
        if r.status_code == 200:
            return r.text
    except requests.RequestException as e:
        _logger.debug("HTTP GET text failed for %s: %s", url, e)
    return ""

def eastmoney_datacenter(report_name: str, filter_str: str = "", page_size: int = 10, sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一接口"""
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    d = _http_get_json(DATACENTER_URL, params=params)
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []

# 全局内存缓存：同花顺强势股列表（避免日内重复请求）
_hot_reason_cache: dict[str, pd.DataFrame] = {}

def ths_hot_reason(date_str: str | None = None) -> pd.DataFrame:
    """同花顺当日强势股归因（直连无鉴权接口）"""
    if date_str is None:
        try:
            from trader_shared.cn_time import today_cn
            date_str = today_cn().isoformat()
        except Exception:
            date_str = date.today().strftime("%Y-%m-%d")

    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_str}/orderby/date/orderway/desc/charset/GBK/"
    )
    
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=10)
        r.encoding = "gbk"
        if r.status_code == 200:
            data = r.json()
            if data.get("errcode", 0) == 0 and data.get("data"):
                rows = data["data"]
                df = pd.DataFrame(rows)
                rename_map = {
                    "name": "名称", "code": "代码", "reason": "题材归因",
                    "close": "收盘价", "zhangfu": "涨幅%", "huanshou": "换手率%",
                }
                return df.rename(columns=rename_map)
    except (requests.RequestException, ValueError, KeyError) as exc:
        _logger.debug("THS hot reason fetch failed for %s: %s", date_str, exc)
    return pd.DataFrame()


class ExtendDataProvider:
    """高阶投研数据提供器封装"""

    @staticmethod
    def get_shareholder_trend(code: str) -> dict[str, Any]:
        """查询股东户数变动趋势 (RPT_HOLDERNUMLATEST)
        
        返回:
            {
                "latest_notice_date": "2026-05-15",
                "latest_holder_num": 120000.0,
                "change_pct": -4.2,
                "status": "筹码集中" | "筹码松散" | "持平" | "数据不足"
            }
        """
        data = eastmoney_datacenter(
            report_name="RPT_HOLDERNUMLATEST",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=1,
            sort_columns="HOLD_NOTICE_DATE"
        )
        if not data:
            return {"status": "数据不足", "change_pct": 0.0, "latest_notice_date": "", "latest_holder_num": 0.0}
        
        try:
            row = data[0]
            latest = float(row.get("HOLDER_NUM", 0) or 0)
            change = float(row.get("HOLDER_NUM_RATIO", 0) or 0)
            
            status = "持平"
            if change <= -3.0:
                status = "筹码集中"
            elif change >= 3.0:
                status = "筹码松散"
                
            return {
                "latest_notice_date": (row.get("HOLD_NOTICE_DATE") or row.get("END_DATE") or "")[:10],
                "latest_holder_num": latest,
                "change_pct": round(change, 2),
                "status": status
            }
        except (TypeError, ValueError, KeyError) as exc:
            _logger.debug("Shareholder trend parse failed for %s: %s", code, exc)
            return {"status": "数据不足", "change_pct": 0.0, "latest_notice_date": "", "latest_holder_num": 0.0}

    @staticmethod
    def get_upcoming_unlocks(code: str) -> list[dict[str, Any]]:
        """查询个股未来 90 天待解禁信息 (RPT_LIFT_STAGE)
        
        返回:
            [{"date": "2026-06-12", "ratio": 8.2, "amount_wan": 5000.0}, ...]
        """
        data = eastmoney_datacenter(
            report_name="RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=10,
            sort_columns="FREE_DATE",
            sort_types="1"
        )
        unlocks = []
        try:
            from trader_shared.cn_time import today_cn
            today_str = today_cn().isoformat()
        except Exception:
            today_str = date.today().strftime("%Y-%m-%d")
        for row in data:
            free_date = (row.get("FREE_DATE") or "")[:10]
            if free_date and free_date >= today_str:
                try:
                    # FREE_RATIO is in absolute fraction (e.g. 0.05 for 5%), so multiply by 100 to get percentage
                    ratio = float(row.get("FREE_RATIO", 0) or 0) * 100
                    # CURRENT_FREE_SHARES is in ten thousand shares (万股)
                    amount_wan = float(row.get("CURRENT_FREE_SHARES", 0) or 0)
                    unlocks.append({
                        "date": free_date,
                        "ratio": round(ratio, 2),
                        "amount_wan": round(amount_wan, 2)
                    })
                except (ValueError, TypeError):
                    continue
        return unlocks

    @staticmethod
    def get_ths_hot_reason_for_stock(code: str) -> dict[str, Any]:
        """获取特定股票的同花顺题材催化归因，采用每日内存缓存设计"""
        try:
            from trader_shared.cn_time import today_cn, now_cn
            today_str = today_cn().isoformat()
            _now = now_cn()
        except Exception:
            today_str = date.today().strftime("%Y-%m-%d")
            _now = datetime.now()

        # 懒加载 / 缓存
        if today_str not in _hot_reason_cache:
            df = ths_hot_reason(today_str)
            if df.empty:
                # 尝试昨天数据作为 fallback
                from datetime import timedelta
                yesterday_str = (_now - timedelta(days=1)).strftime("%Y-%m-%d")
                df = ths_hot_reason(yesterday_str)
            _hot_reason_cache[today_str] = df

        df = _hot_reason_cache[today_str]
        if not df.empty:
            row = df[df["代码"] == code]
            if not row.empty:
                return {
                    "reason": row.iloc[0].get("题材归因", "题材催化异动"),
                    "change_pct": row.iloc[0].get("涨幅%", "0.00"),
                }
        return {"reason": None, "change_pct": None}

    @staticmethod
    def get_ths_consensus_eps(code: str) -> dict[str, Any]:
        """同花顺机构一致预期，支持 Pandas + 正则双解析机制，防库缺失"""
        url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
        html = _http_get_text(url, referer="https://basic.10jqka.com.cn/", encoding="gbk")
        if not html:
            return {"rows": [], "source": "ths"}

        # 方式 1: Pandas 表格解析
        try:
            dfs = pd.read_html(StringIO(html))
            for df in dfs:
                cols = [str(c) for c in df.columns]
                if any("每股收益" in c or "均值" in c for c in cols):
                    rows = []
                    for _, row in df.iterrows():
                        row_dict = row.to_dict()
                        rows.append({
                            "year": str(row_dict.get("年度", "")),
                            "count": str(row_dict.get("预测机构数", "")),
                            "min_eps": str(row_dict.get("最小值", "")),
                            "avg_eps": str(row_dict.get("均值", "")),
                            "max_eps": str(row_dict.get("最大值", ""))
                        })
                    return {"rows": rows, "source": "ths"}
        except (ValueError, KeyError) as exc:
            _logger.debug("THS EPS pandas parse failed for %s: %s", code, exc)

        # 方式 2: 正则回退解析 (针对无 lxml 库或 Pandas 解析失败的情况)
        try:
            # 抓取表格中包含“每股收益”或特定一致预估字段行的 <tr> 结构
            tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
            td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
            th_pattern = re.compile(r'<th[^>]*>(.*?)</th>', re.DOTALL)
            
            trs = tr_pattern.findall(html)
            headers = []
            rows = []
            
            for tr in trs:
                ths = th_pattern.findall(tr)
                if ths:
                    headers = [re.sub(r'<[^>]+>', '', th).strip() for th in ths]
                    continue
                tds = td_pattern.findall(tr)
                if tds:
                    vals = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                    if len(vals) >= 4 and any("预测" in h or "均值" in h or "年度" in h for h in headers):
                        row_data = dict(zip(headers, vals))
                        rows.append({
                            "year": str(row_data.get("年度", vals[0])),
                            "count": str(row_data.get("预测机构数", vals[1])),
                            "min_eps": str(row_data.get("最小值", vals[2])),
                            "avg_eps": str(row_data.get("均值", vals[3])),
                            "max_eps": str(row_data.get("最大值", vals[4] if len(vals) > 4 else ""))
                        })
            if rows:
                return {"rows": rows, "source": "ths-regex"}
        except (ValueError, KeyError) as exc:
            _logger.debug("THS EPS regex parse failed for %s: %s", code, exc)

        return {"rows": [], "source": "ths"}

    # ── Phase 1 新增：融资融券 / 北向资金 / 板块数据 ──

    @staticmethod
    def get_margin_data(code: str) -> dict[str, Any]:
        """获取个股融资融券明细数据（via akshare）。

        自动识别沪/深市，调用对应接口获取最近交易日的融资融券数据。

        返回:
            {
                "margin_balance_wan": float,  # 融资余额（万元）
                "margin_buy_wan": float,      # 融资买入额（万元）
                "margin_sell_wan": float,     # 融资偿还额（万元）
                "short_sell_vol": float,      # 融券卖出量（股）
                "short_balance_wan": float,   # 融券余额（万元）
                "date": str,                  # 数据日期
                "status": str                 # "正常" | "无数据" | "接口不可用"
            }
        """
        if not _check_akshare():
            return {"margin_balance_wan": 0, "margin_buy_wan": 0, "margin_sell_wan": 0,
                    "short_sell_vol": 0, "short_balance_wan": 0, "date": "", "status": "接口不可用"}

        try:
            import akshare as ak
            # 识别市场：6/9 开头为沪市，其余为深市
            is_sse = code.startswith(("5", "6", "9"))  # 含沪市 ETF 51xxxx
            try:
                from trader_shared.cn_time import today_cn
                today_str = today_cn().strftime("%Y%m%d")
            except Exception:
                today_str = date.today().strftime("%Y%m%d")

            if is_sse:
                df = ak.stock_margin_detail_sse(date=today_str)
            else:
                df = ak.stock_margin_detail_szse(date=today_str)

            if df is None or df.empty:
                return {"margin_balance_wan": 0, "margin_buy_wan": 0, "margin_sell_wan": 0,
                        "short_sell_vol": 0, "short_balance_wan": 0, "date": "", "status": "无数据"}

            # 按股票代码筛选（列名可能是 "标的证券" 或 "证券代码" 或 "股票代码"）
            code_col = None
            for candidate in ["标的证券", "证券代码", "股票代码", "代码"]:
                if candidate in df.columns:
                    code_col = candidate
                    break
            if code_col is None:
                _logger.debug("Margin data columns not recognized for %s: %s", code, list(df.columns))
                return {"margin_balance_wan": 0, "margin_buy_wan": 0, "margin_sell_wan": 0,
                        "short_sell_vol": 0, "short_balance_wan": 0, "date": "", "status": "无数据"}

            # 代码匹配（akshare 返回的代码可能是纯数字或带前缀）
            row = df[df[code_col].astype(str).str.contains(code, na=False)]
            if row.empty:
                return {"margin_balance_wan": 0, "margin_buy_wan": 0, "margin_sell_wan": 0,
                        "short_sell_vol": 0, "short_balance_wan": 0, "date": "", "status": "无数据"}

            r = row.iloc[0]

            def _safe_float(val: Any) -> float:
                try:
                    return float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            # 列名兼容多种命名
            margin_balance = _safe_float(r.get("融资余额(元)", r.get("融资余额", 0)))
            margin_buy = _safe_float(r.get("融资买入额(元)", r.get("融资买入额", r.get("融资买入", 0))))
            margin_sell = _safe_float(r.get("融资偿还额(元)", r.get("融资偿还额", r.get("融资偿还", 0))))
            short_sell = _safe_float(r.get("融券卖出量(股)", r.get("融券卖出量", r.get("融券卖出", 0))))
            short_balance = _safe_float(r.get("融券余额(元)", r.get("融券余额", 0)))

            data_date = str(r.get("信用交易日期", r.get("日期", today_str)))[:10]

            return {
                "margin_balance_wan": round(margin_balance / 10000, 2),
                "margin_buy_wan": round(margin_buy / 10000, 2),
                "margin_sell_wan": round(margin_sell / 10000, 2),
                "short_sell_vol": short_sell,
                "short_balance_wan": round(short_balance / 10000, 2),
                "date": data_date,
                "status": "正常",
            }
        except Exception as exc:
            _logger.debug("Margin data fetch failed for %s: %s", code, exc)
            return {"margin_balance_wan": 0, "margin_buy_wan": 0, "margin_sell_wan": 0,
                    "short_sell_vol": 0, "short_balance_wan": 0, "date": "", "status": "无数据"}

    @staticmethod
    def get_northbound_flow() -> dict[str, Any]:
        """获取北向资金（沪深港通）当日净流入数据（via akshare）。

        返回:
            {
                "north_net_flow_wan": float,   # 当日北向净流入（万元）
                "north_flow_5d_wan": float,    # 近5日累计净流入（万元）
                "date": str,                   # 数据日期
                "status": str                  # "正常" | "无数据" | "接口不可用"
            }
        """
        if not _check_akshare():
            return {"north_net_flow_wan": 0, "north_flow_5d_wan": 0, "date": "", "status": "接口不可用"}

        try:
            import akshare as ak
            df = ak.stock_hsgt_north_net_flow_in_em(symbol="北向资金")

            if df is None or df.empty:
                return {"north_net_flow_wan": 0, "north_flow_5d_wan": 0, "date": "", "status": "无数据"}

            # 列名兼容：可能是 "value", "当日净流入", "净流入" 等
            flow_col = None
            for candidate in ["value", "当日净流入", "净流入", "north_net_flow_in_em"]:
                if candidate in df.columns:
                    flow_col = candidate
                    break

            date_col = None
            for candidate in ["date", "日期", "datetime"]:
                if candidate in df.columns:
                    date_col = candidate
                    break

            if flow_col is None or date_col is None:
                _logger.debug("Northbound flow columns not recognized: %s", list(df.columns))
                return {"north_net_flow_wan": 0, "north_flow_5d_wan": 0, "date": "", "status": "无数据"}

            # 按日期排序取最新
            df = df.sort_values(date_col, ascending=False)
            latest = df.iloc[0]

            def _safe_float(val: Any) -> float:
                try:
                    return float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            # 净流入值单位可能是元或万元，akshare 北向资金通常返回元
            net_flow_raw = _safe_float(latest[flow_col])
            # 近5日累计
            recent5 = df.head(5)
            flow_5d_raw = sum(_safe_float(row[flow_col]) for _, row in recent5.iterrows())

            data_date = str(latest[date_col])[:10]

            return {
                "north_net_flow_wan": round(net_flow_raw / 10000, 2) if abs(net_flow_raw) > 100000 else round(net_flow_raw, 2),
                "north_flow_5d_wan": round(flow_5d_raw / 10000, 2) if abs(flow_5d_raw) > 100000 else round(flow_5d_raw, 2),
                "date": data_date,
                "status": "正常",
            }
        except Exception as exc:
            _logger.debug("Northbound flow fetch failed: %s", exc)
            return {"north_net_flow_wan": 0, "north_flow_5d_wan": 0, "date": "", "status": "无数据"}

    @staticmethod
    def get_sector_data(code: str) -> dict[str, Any]:
        """获取个股所属行业板块及板块行情数据（via akshare）。

        通过板块成分股反查个股所属板块，再获取板块实时行情。

        返回:
            {
                "sector_name": str,             # 板块名称
                "sector_change_pct": float,     # 板块今日涨跌幅
                "sector_rank": int,             # 板块排名（按涨跌幅）
                "sector_total": int,            # 板块总数
                "stock_vs_sector": str,         # 个股 vs 板块相对强弱
                "status": str                   # "正常" | "无数据" | "接口不可用"
            }
        """
        if not _check_akshare():
            return {"sector_name": "", "sector_change_pct": 0, "sector_rank": 0,
                    "sector_total": 0, "stock_vs_sector": "", "status": "接口不可用"}

        try:
            import akshare as ak

            # Step 1: 获取所有行业板块实时行情（含涨跌幅排名）
            spot_df = ak.stock_board_industry_spot_em()
            if spot_df is None or spot_df.empty:
                return {"sector_name": "", "sector_change_pct": 0, "sector_rank": 0,
                        "sector_total": 0, "stock_vs_sector": "", "status": "无数据"}

            # 板块名称列
            name_col = None
            for candidate in ["板块名称", "名称"]:
                if candidate in spot_df.columns:
                    name_col = candidate
                    break
            # 涨跌幅列
            chg_col = None
            for candidate in ["涨跌幅", "板块涨跌幅"]:
                if candidate in spot_df.columns:
                    chg_col = candidate
                    break

            if name_col is None or chg_col is None:
                _logger.debug("Sector spot columns not recognized: %s", list(spot_df.columns))
                return {"sector_name": "", "sector_change_pct": 0, "sector_rank": 0,
                        "sector_total": 0, "stock_vs_sector": "", "status": "无数据"}

            # 按涨跌幅排序
            spot_df = spot_df.sort_values(chg_col, ascending=False).reset_index(drop=True)
            spot_df["_rank"] = range(1, len(spot_df) + 1)
            sector_total = len(spot_df)

            # Step 2: 遍历板块找到个股所属板块
            # 为避免遍历全部板块（太慢），只检查涨幅前 50 的板块
            matched_sector = ""
            matched_chg = 0.0
            matched_rank = 0

            checked = 0
            for _, sector_row in spot_df.iterrows():
                if checked >= 50:
                    break
                sector_name = str(sector_row.get(name_col, ""))
                if not sector_name:
                    continue
                try:
                    cons_df = ak.stock_board_industry_cons_em(symbol=sector_name)
                    checked += 1
                    if cons_df is None or cons_df.empty:
                        continue
                    # 成分股代码列
                    code_col_cons = None
                    for c in ["代码", "股票代码", "证券代码"]:
                        if c in cons_df.columns:
                            code_col_cons = c
                            break
                    if code_col_cons is None:
                        continue
                    if code in cons_df[code_col_cons].astype(str).values:
                        matched_sector = sector_name

                        def _safe_float(val: Any) -> float:
                            try:
                                return float(val) if pd.notna(val) else 0.0
                            except (ValueError, TypeError):
                                return 0.0

                        matched_chg = _safe_float(sector_row.get(chg_col, 0))
                        matched_rank = int(sector_row.get("_rank", 0))
                        break
                except Exception:
                    continue

            if not matched_sector:
                return {"sector_name": "", "sector_change_pct": 0, "sector_rank": 0,
                        "sector_total": sector_total, "stock_vs_sector": "", "status": "无数据"}

            return {
                "sector_name": matched_sector,
                "sector_change_pct": round(matched_chg, 2),
                "sector_rank": matched_rank,
                "sector_total": sector_total,
                "stock_vs_sector": "",  # 需要个股涨幅才能计算，在 build_report 中填充
                "status": "正常",
            }
        except Exception as exc:
            _logger.debug("Sector data fetch failed for %s: %s", code, exc)
            return {"sector_name": "", "sector_change_pct": 0, "sector_rank": 0,
                    "sector_total": 0, "stock_vs_sector": "", "status": "无数据"}

    @staticmethod
    def get_concept_data(code: str) -> dict[str, Any]:
        """获取个股所属概念板块及行情数据（via akshare）。

        通过概念板块成分股反查个股所属概念，再获取各概念实时行情。
        个股可同时属于多个概念板块。

        返回:
            {
                "concept_list": [str],        # 命中概念名称列表
                "concept_change_pct": [float],# 各概念今日涨跌幅（与 concept_list 对齐）
                "concept_rank": dict,         # {概念名: {"rank": int, "total": int, "change_pct": float}}
                "concept_total": int,         # 概念板块总数
                "status": str                 # "正常" | "无数据" | "接口不可用"
            }
        """
        if not _check_akshare():
            return {"concept_list": [], "concept_change_pct": [], "concept_rank": {},
                    "concept_total": 0, "status": "接口不可用"}

        try:
            import akshare as ak

            # Step 1: 获取所有概念板块实时行情（含涨跌幅排名）
            spot_df = ak.stock_board_concept_spot_em()
            if spot_df is None or spot_df.empty:
                return {"concept_list": [], "concept_change_pct": [], "concept_rank": {},
                        "concept_total": 0, "status": "无数据"}

            # 板块名称列
            name_col = None
            for candidate in ["板块名称", "名称"]:
                if candidate in spot_df.columns:
                    name_col = candidate
                    break
            # 涨跌幅列
            chg_col = None
            for candidate in ["涨跌幅", "板块涨跌幅"]:
                if candidate in spot_df.columns:
                    chg_col = candidate
                    break

            if name_col is None or chg_col is None:
                _logger.debug("Concept spot columns not recognized: %s", list(spot_df.columns))
                return {"concept_list": [], "concept_change_pct": [], "concept_rank": {},
                        "concept_total": 0, "status": "无数据"}

            # 按涨跌幅排序（热门概念优先检查）
            spot_df = spot_df.sort_values(chg_col, ascending=False).reset_index(drop=True)
            spot_df["_rank"] = range(1, len(spot_df) + 1)
            concept_total = len(spot_df)

            def _safe_float(val: Any) -> float:
                try:
                    return float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            # Step 2: 遍历概念板块找到个股所属概念（个股可命中多个）
            concept_list: list[str] = []
            concept_change_pct: list[float] = []
            concept_rank: dict[str, dict[str, Any]] = {}

            checked = 0
            for _, concept_row in spot_df.iterrows():
                if checked >= 80:
                    break
                concept_name = str(concept_row.get(name_col, ""))
                if not concept_name:
                    continue
                try:
                    cons_df = ak.stock_board_concept_cons_em(symbol=concept_name)
                    checked += 1
                    if cons_df is None or cons_df.empty:
                        continue
                    # 成分股代码列
                    code_col_cons = None
                    for c in ["代码", "股票代码", "证券代码"]:
                        if c in cons_df.columns:
                            code_col_cons = c
                            break
                    if code_col_cons is None:
                        continue
                    if code in cons_df[code_col_cons].astype(str).values:
                        c_chg = _safe_float(concept_row.get(chg_col, 0))
                        c_rank = int(concept_row.get("_rank", 0))
                        concept_list.append(concept_name)
                        concept_change_pct.append(round(c_chg, 2))
                        concept_rank[concept_name] = {
                            "rank": c_rank,
                            "total": concept_total,
                            "change_pct": round(c_chg, 2),
                        }
                except Exception:
                    continue

            if not concept_list:
                return {"concept_list": [], "concept_change_pct": [], "concept_rank": {},
                        "concept_total": concept_total, "status": "无数据"}

            return {
                "concept_list": concept_list,
                "concept_change_pct": concept_change_pct,
                "concept_rank": concept_rank,
                "concept_total": concept_total,
                "status": "正常",
            }
        except Exception as exc:
            _logger.debug("Concept data fetch failed for %s: %s", code, exc)
            return {"concept_list": [], "concept_change_pct": [], "concept_rank": {},
                    "concept_total": 0, "status": "无数据"}
