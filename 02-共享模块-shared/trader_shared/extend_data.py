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

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


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


def _to_ts_code(code: str) -> str:
    """6 位码 / 已带后缀 → tushare ts_code。"""
    s = str(code or "").strip().upper()
    if not s:
        return ""
    if "." in s:
        return s
    if s.startswith(("6", "5", "9")):
        return f"{s}.SH"
    return f"{s}.SZ"


def _ymd(val: Any) -> str:
    """把 20260102 / 2026-01-02 / datetime 压成 YYYY-MM-DD。"""
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        try:
            return val.strftime("%Y-%m-%d")
        except Exception:
            pass
    s = str(val).strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s[:10]


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and val != val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default

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
        """查询股东户数变动趋势（Tushare stk_holdernumber）。

        返回:
            {
                "latest_notice_date": "2026-05-15",
                "latest_holder_num": 120000.0,
                "change_pct": -4.2,
                "status": "筹码集中" | "筹码松散" | "持平" | "数据不足",
                "source": "tushare"
            }
        """
        empty = {
            "status": "数据不足",
            "change_pct": 0.0,
            "latest_notice_date": "",
            "latest_holder_num": 0.0,
            "source": "tushare",
        }
        ts_code = _to_ts_code(code)
        if not ts_code:
            return empty
        try:
            from trader_shared.tushare_client import get_client

            rows = get_client().query_stk_holdernumber(ts_code) or []
        except Exception as exc:
            _logger.debug("Shareholder tushare fetch failed for %s: %s", code, exc)
            return empty
        if not rows:
            return empty

        def _sort_key(r: dict[str, Any]) -> str:
            return _ymd(r.get("ann_date") or r.get("end_date") or r.get("trade_date") or "")

        try:
            ordered = sorted(
                [r for r in rows if isinstance(r, dict)],
                key=_sort_key,
            )
            if not ordered:
                return empty
            latest_row = ordered[-1]
            latest = _safe_float(
                latest_row.get("holder_num")
                or latest_row.get("holder_nums")
                or latest_row.get("holder")
            )
            prev = None
            if len(ordered) >= 2:
                prev = _safe_float(
                    ordered[-2].get("holder_num")
                    or ordered[-2].get("holder_nums")
                    or ordered[-2].get("holder")
                )
            # tushare 偶发直接给变动比
            raw_chg = latest_row.get("holder_num_ratio")
            if raw_chg is None:
                raw_chg = latest_row.get("holder_num_change_pct")
            if raw_chg is None:
                raw_chg = latest_row.get("change_pct")
            if raw_chg is not None and str(raw_chg).strip() != "":
                change = _safe_float(raw_chg)
            elif prev and prev > 0 and latest > 0:
                change = (latest - prev) / prev * 100.0
            else:
                change = 0.0

            status = "持平"
            if change <= -3.0:
                status = "筹码集中"
            elif change >= 3.0:
                status = "筹码松散"

            return {
                "latest_notice_date": _ymd(
                    latest_row.get("ann_date") or latest_row.get("end_date") or latest_row.get("trade_date")
                ),
                "latest_holder_num": latest,
                "change_pct": round(float(change or 0.0), 2),
                "status": status,
                "source": "tushare",
            }
        except (TypeError, ValueError, KeyError) as exc:
            _logger.debug("Shareholder trend parse failed for %s: %s", code, exc)
            return empty

    @staticmethod
    def get_upcoming_unlocks(code: str, *, days: int = 90, as_of: str | None = None) -> list[dict[str, Any]]:
        """查询个股未来待解禁（Tushare share_float）。

        返回:
            [{"date": "2026-06-12", "ratio": 8.2, "amount_wan": 5000.0}, ...]
        """
        ts_code = _to_ts_code(code)
        if not ts_code:
            return []
        try:
            from trader_shared.cn_time import today_cn

            today_str = _ymd(as_of) if as_of else today_cn().isoformat()
        except Exception:
            today_str = _ymd(as_of) if as_of else date.today().strftime("%Y-%m-%d")
        if not today_str:
            today_str = date.today().strftime("%Y-%m-%d")

        # 窗口：as_of 起 ~ days 天
        try:
            y, m, d = [int(x) for x in today_str.split("-")[:3]]
            start_dt = date(y, m, d)
            end_dt = start_dt + __import__("datetime").timedelta(days=max(1, int(days)))
            start_s = start_dt.strftime("%Y%m%d")
            end_s = end_dt.strftime("%Y%m%d")
        except Exception:
            start_s = today_str.replace("-", "")
            end_s = ""

        try:
            from trader_shared.tushare_client import get_client

            rows = get_client().query_share_float(ts_code, start_date=start_s, end_date=end_s) or []
        except Exception as exc:
            _logger.debug("Unlock tushare fetch failed for %s: %s", code, exc)
            return []

        unlocks: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            free_date = _ymd(row.get("float_date") or row.get("free_date") or row.get("ann_date"))
            if not free_date or free_date < today_str:
                continue
            if days > 0:
                try:
                    y, m, d = [int(x) for x in free_date.split("-")[:3]]
                    if (date(y, m, d) - date.fromisoformat(today_str)).days > int(days):
                        continue
                except Exception:
                    pass
            # float_ratio 常见为绝对比例 0.05=5%；也兼容已是百分数
            ratio_raw = _safe_float(row.get("float_ratio") or row.get("free_ratio") or row.get("ratio"))
            ratio = ratio_raw * 100.0 if 0 < abs(ratio_raw) <= 1.5 else ratio_raw
            # 解禁股数：股 / 万股 兼容
            shares = _safe_float(
                row.get("float_share")
                or row.get("free_share")
                or row.get("current_free_shares")
                or row.get("share")
            )
            amount_wan = shares / 10000.0 if shares > 100000 else shares
            unlocks.append({
                "date": free_date,
                "ratio": round(ratio, 2),
                "amount_wan": round(amount_wan, 2),
                "source": "tushare",
            })
        unlocks.sort(key=lambda x: str(x.get("date") or ""))
        return unlocks

    @staticmethod
    def get_all_unlocks(code: str) -> list[dict[str, Any]]:
        """回测用：全部限售解禁事件（不过滤 today）。"""
        ts_code = _to_ts_code(code)
        if not ts_code:
            return []
        try:
            from trader_shared.tushare_client import get_client

            rows = get_client().query_share_float(ts_code) or []
        except Exception as exc:
            _logger.debug("Unlock-all tushare fetch failed for %s: %s", code, exc)
            return []
        unlocks: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            free_date = _ymd(row.get("float_date") or row.get("free_date") or row.get("ann_date"))
            if not free_date:
                continue
            ratio_raw = _safe_float(row.get("float_ratio") or row.get("free_ratio") or row.get("ratio"))
            ratio = ratio_raw * 100.0 if 0 < abs(ratio_raw) <= 1.5 else ratio_raw
            shares = _safe_float(
                row.get("float_share")
                or row.get("free_share")
                or row.get("current_free_shares")
                or row.get("share")
            )
            amount_wan = shares / 10000.0 if shares > 100000 else shares
            unlocks.append({
                "date": free_date,
                "ratio": round(ratio, 2),
                "amount_wan": round(amount_wan, 2),
                "source": "tushare",
            })
        unlocks.sort(key=lambda x: str(x.get("date") or ""))
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
        """获取个股融资融券明细（Tushare margin_detail）。

        返回:
            {
                "margin_balance_wan": float,  # 融资余额（万元）
                "margin_buy_wan": float,      # 融资买入额（万元）
                "margin_sell_wan": float,     # 融资偿还额（万元）
                "short_sell_vol": float,      # 融券卖出量（股）
                "short_balance_wan": float,   # 融券余额（万元）
                "date": str,                  # 数据日期
                "status": str,                # "正常" | "无数据" | "接口不可用"
                "source": "tushare",
            }
        """
        empty = {
            "margin_balance_wan": 0.0,
            "margin_buy_wan": 0.0,
            "margin_sell_wan": 0.0,
            "short_sell_vol": 0.0,
            "short_balance_wan": 0.0,
            "date": "",
            "status": "无数据",
            "source": "tushare",
        }
        ts_code = _to_ts_code(code)
        if not ts_code:
            return {**empty, "status": "无数据"}
        try:
            from trader_shared.tushare_client import get_client

            client = get_client()
        except Exception as exc:
            _logger.debug("Margin tushare client failed for %s: %s", code, exc)
            return {**empty, "status": "接口不可用"}

        rows: list[dict[str, Any]] = []
        try:
            # 近约 20 个自然日窗口，取最新有数的一天
            try:
                from trader_shared.cn_time import today_cn
                end_d = today_cn()
            except Exception:
                end_d = date.today()
            start_d = end_d - __import__("datetime").timedelta(days=20)
            rows = client.query_margin_detail(
                ts_code=ts_code,
                start_date=start_d.strftime("%Y%m%d"),
                end_date=end_d.strftime("%Y%m%d"),
            ) or []
            if not rows:
                # 再试无日期参数（部分 token 只回最新）
                rows = client.query_margin_detail(ts_code=ts_code) or []
        except Exception as exc:
            _logger.debug("Margin tushare fetch failed for %s: %s", code, exc)
            return {**empty, "status": "无数据"}

        if not rows:
            return empty

        def _row_date(r: dict[str, Any]) -> str:
            return _ymd(r.get("trade_date") or r.get("date") or r.get("end_date"))

        try:
            ordered = sorted([r for r in rows if isinstance(r, dict)], key=_row_date)
            if not ordered:
                return empty
            r = ordered[-1]
            # tushare 常见单位：元；余额/买入/偿还 → 万元
            def _yuan_to_wan(v: Any) -> float:
                x = _safe_float(v)
                # 极大数当元；已经是万的量级则保持
                return round(x / 10000.0, 2) if abs(x) >= 100000 else round(x, 2)

            margin_balance = _yuan_to_wan(
                r.get("rzye") or r.get("rz_balance") or r.get("fin_balance") or r.get("margin_balance")
            )
            margin_buy = _yuan_to_wan(
                r.get("rzmre") or r.get("rz_buy") or r.get("fin_buy") or r.get("margin_buy")
            )
            margin_sell = _yuan_to_wan(
                r.get("rzche") or r.get("rz_repay") or r.get("fin_repay") or r.get("margin_repay")
            )
            short_sell = _safe_float(
                r.get("rqmcl") or r.get("rq_sell") or r.get("short_sell") or r.get("short_volume")
            )
            short_balance = _yuan_to_wan(
                r.get("rqye") or r.get("rq_balance") or r.get("short_balance")
            )
            return {
                "margin_balance_wan": margin_balance,
                "margin_buy_wan": margin_buy,
                "margin_sell_wan": margin_sell,
                "short_sell_vol": short_sell,
                "short_balance_wan": short_balance,
                "date": _row_date(r),
                "status": "正常",
                "source": "tushare",
            }
        except Exception as exc:
            _logger.debug("Margin parse failed for %s: %s", code, exc)
            return empty

    @staticmethod
    def get_northbound_flow() -> dict[str, Any]:
        """获取北向资金（沪深港通）净流入（Tushare moneyflow_hsgt）。

        返回:
            {
                "north_net_flow_wan": float,   # 当日北向净流入（万元）
                "north_flow_5d_wan": float,    # 近5日累计净流入（万元）
                "date": str,
                "status": str,
                "source": "tushare",
            }
        """
        empty = {
            "north_net_flow_wan": 0.0,
            "north_flow_5d_wan": 0.0,
            "date": "",
            "status": "无数据",
            "source": "tushare",
        }
        try:
            from trader_shared.tushare_client import get_client

            client = get_client()
        except Exception as exc:
            _logger.debug("Northbound tushare client failed: %s", exc)
            return {**empty, "status": "接口不可用"}

        try:
            try:
                from trader_shared.cn_time import today_cn
                end_d = today_cn()
            except Exception:
                end_d = date.today()
            start_d = end_d - __import__("datetime").timedelta(days=20)
            rows = client.query_moneyflow_hsgt(
                start_date=start_d.strftime("%Y%m%d"),
                end_date=end_d.strftime("%Y%m%d"),
            ) or []
            if not rows:
                rows = client.query_moneyflow_hsgt() or []
        except Exception as exc:
            _logger.debug("Northbound tushare fetch failed: %s", exc)
            return empty

        if not rows:
            return empty

        def _row_date(r: dict[str, Any]) -> str:
            return _ymd(r.get("trade_date") or r.get("date"))

        try:
            ordered = sorted([r for r in rows if isinstance(r, dict)], key=_row_date)
            if not ordered:
                return empty
            recent = ordered[-5:]
            latest = recent[-1]

            def _to_wan(v: Any) -> float:
                x = _safe_float(v)
                # moneyflow_hsgt 常见单位：百万元 或 元；做粗兼容
                if abs(x) >= 1000000:  # 元
                    return round(x / 10000.0, 2)
                if abs(x) >= 1000:  # 可能是百万元 → 万元 *100
                    # 百万元 * 100 = 万元
                    return round(x * 100.0, 2)
                return round(x, 2)

            # north_money / north_net_flow / hgt+sgt
            def _north_of(r: dict[str, Any]) -> float:
                if r.get("north_money") is not None:
                    return _to_wan(r.get("north_money"))
                if r.get("north_net_flow") is not None:
                    return _to_wan(r.get("north_net_flow"))
                hgt = _safe_float(r.get("hgt"))
                sgt = _safe_float(r.get("sgt"))
                if hgt or sgt:
                    return _to_wan(hgt + sgt)
                return _to_wan(r.get("value") or r.get("net_flow") or 0)

            day_vals = [_north_of(r) for r in recent]
            return {
                "north_net_flow_wan": day_vals[-1],
                "north_flow_5d_wan": round(sum(day_vals), 2),
                "date": _row_date(latest),
                "status": "正常",
                "source": "tushare",
            }
        except Exception as exc:
            _logger.debug("Northbound parse failed: %s", exc)
            return empty

    @staticmethod
    def get_sector_data(code: str) -> dict[str, Any]:
        """个股所属行业板块（Tushare / sector_data 缓存路径）。

        返回字段对齐历史契约，供 fusion / assess_stage 消费。
        """
        empty = {
            "sector_name": "",
            "sector_change_pct": 0.0,
            "sector_rank": 0,
            "sector_total": 0,
            "stock_vs_sector": "",
            "status": "无数据",
            "source": "tushare",
        }
        ts_code = _to_ts_code(code)
        if not ts_code:
            return empty
        try:
            from trader_shared.sector_data import get_stock_sector_snapshot_cached

            snap = get_stock_sector_snapshot_cached(ts_code)
        except Exception as exc:
            _logger.debug("Sector tushare snapshot failed for %s: %s", code, exc)
            return {**empty, "status": "接口不可用"}
        if not isinstance(snap, dict):
            return empty
        status = str(snap.get("status") or "")
        if status != "正常":
            return {
                **empty,
                "sector_name": str(snap.get("sector_name") or snap.get("industry") or ""),
                "status": "无数据" if status else "无数据",
                "industry": snap.get("industry") or "",
                "sector_code": snap.get("sector_code") or "",
            }
        return {
            "sector_name": str(snap.get("sector_name") or snap.get("industry") or ""),
            "sector_change_pct": float(snap.get("sector_change_pct") or 0),
            "sector_rank": int(snap.get("sector_rank") or 0),
            "sector_total": int(snap.get("sector_total") or 0),
            "stock_vs_sector": str(snap.get("stock_vs_sector") or ""),
            "status": "正常",
            "source": "tushare",
            "industry": snap.get("industry") or "",
            "sector_code": snap.get("sector_code") or "",
        }

    @staticmethod
    def get_concept_data(code: str, *, max_concepts: int = 40) -> dict[str, Any]:
        """个股所属概念（Tushare concept / concept_detail，有上限扫描）。

        仅在 TRADER_ENRICH_BOARDS=1 时主链路会调用；失败返回空，不拖主报告。
        """
        empty = {
            "concept_list": [],
            "concept_change_pct": [],
            "concept_rank": {},
            "concept_total": 0,
            "status": "无数据",
            "source": "tushare",
        }
        ts_code = _to_ts_code(code)
        bare = ts_code.split(".")[0] if ts_code else str(code or "").strip()
        if not bare:
            return empty
        try:
            from trader_shared.sector_data import get_concept_detail, get_concept_list

            concepts = get_concept_list() or []
        except Exception as exc:
            _logger.debug("Concept list tushare failed for %s: %s", code, exc)
            return {**empty, "status": "接口不可用"}
        if not concepts:
            return empty

        concept_list: list[str] = []
        concept_change_pct: list[float] = []
        concept_rank: dict[str, dict[str, Any]] = {}
        total = len(concepts)
        checked = 0
        for i, c in enumerate(concepts):
            if checked >= max(1, int(max_concepts)):
                break
            if not isinstance(c, dict):
                continue
            cid = str(c.get("code") or c.get("id") or c.get("ts_code") or "").strip()
            cname = str(c.get("name") or c.get("concept_name") or "").strip()
            if not cid or not cname:
                continue
            try:
                members = get_concept_detail(cid) or []
            except Exception:
                continue
            checked += 1
            hit = False
            for mrow in members:
                if not isinstance(mrow, dict):
                    continue
                mcode = str(mrow.get("ts_code") or mrow.get("code") or mrow.get("symbol") or "")
                if bare and bare in mcode.replace(".SH", "").replace(".SZ", ""):
                    hit = True
                    break
                if ts_code and mcode.upper() == ts_code.upper():
                    hit = True
                    break
            if not hit:
                continue
            chg = _safe_float(c.get("pct_change") or c.get("change_pct") or c.get("pct_chg") or 0)
            concept_list.append(cname)
            concept_change_pct.append(round(chg, 2))
            concept_rank[cname] = {
                "rank": int(c.get("rank") or (i + 1)),
                "total": total,
                "change_pct": round(chg, 2),
            }
            # 面板只需要少数概念，命中 5 个就够
            if len(concept_list) >= 5:
                break

        if not concept_list:
            return {**empty, "concept_total": total}
        return {
            "concept_list": concept_list,
            "concept_change_pct": concept_change_pct,
            "concept_rank": concept_rank,
            "concept_total": total,
            "status": "正常",
            "source": "tushare",
        }

