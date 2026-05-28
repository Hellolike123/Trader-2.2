# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import time
from datetime import datetime, date
from io import StringIO
from typing import Any

import requests
import pandas as pd

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def _http_get_json(url: str, params: dict[str, Any] | None = None) -> dict:
    """Helper to perform HTTP GET returning JSON via requests for SSL safety on macOS."""
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
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
    except Exception:
        pass
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
            if data.get("errocode", 0) == 0 and data.get("data"):
                rows = data["data"]
                df = pd.DataFrame(rows)
                rename_map = {
                    "name": "名称", "code": "代码", "reason": "题材归因",
                    "close": "收盘价", "zhangfu": "涨幅%", "huanshou": "换手率%",
                }
                return df.rename(columns=rename_map)
    except Exception:
        pass
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
        except Exception:
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
        today_str = date.today().strftime("%Y-%m-%d")
        
        # 懒加载 / 缓存
        if today_str not in _hot_reason_cache:
            df = ths_hot_reason(today_str)
            if df.empty:
                # 尝试昨天数据作为 fallback
                from datetime import timedelta
                yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
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
        except Exception:
            pass

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
        except Exception:
            pass

        return {"rows": [], "source": "ths"}
