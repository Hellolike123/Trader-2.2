"""资金流向数据采集与特征工程。

通过东方财富HTTP API获取个股日线级资金流向（超大单/大单/中单/小单净流入），
并计算衍生特征供主力行为识别引擎使用。

用法:
    from trader_shared.fund_flow_data import fetch_fund_flow, calc_fund_flow_features
"""

from __future__ import annotations

import json
import warnings
from typing import Any

import requests

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"


def _secid(symbol: str) -> str:
    """将股票代码转换为东方财富 secid 格式。

    沪市=1, 深市=0, 含创业板/科创板识别。
    """
    code = symbol.split(".")[0] if "." in symbol else symbol
    suffix = symbol.split(".")[-1] if "." in symbol else ""

    if suffix in ("SH", "sh"):
        return f"1.{code}"
    if suffix in ("SZ", "sz"):
        return f"0.{code}"
    # 无后缀时按代码段判断
    if code.startswith(("6", "9")):
        return f"1.{code}"
    return f"0.{code}"


def fetch_fund_flow(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """获取个股资金流向数据。

    Args:
        symbol: 股票代码（如 "688248.SH" 或 "688248"）
        days: 获取天数（默认30）

    Returns:
        每日资金流向列表，每条包含:
        - date: 日期
        - super_large_wan: 超大单净流入（万元）
        - large_wan: 大单净流入（万元）
        - medium_wan: 中单净流入（万元）
        - small_wan: 小单净流入（万元）
        - net_flow_wan: 主力净流入（万元）= super_large + large

        API不可用时返回空列表。
    """
    try:
        params = {
            "secid": _secid(symbol),
            "lmt": "0",
            "klt": "101",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        r = requests.get(FFLOW_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return []

        result = []
        for line in klines[-days:]:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                date_str = parts[0]
                super_large = float(parts[1]) if parts[1] != "-" else 0.0
                large = float(parts[2]) if parts[2] != "-" else 0.0
                medium = float(parts[3]) if parts[3] != "-" else 0.0
                small = float(parts[4]) if parts[4] != "-" else 0.0
                # parts[5] = 主力净流入, parts[6] = 小单净流入 (有时重复)
                net_flow = float(parts[5]) if parts[5] != "-" else super_large + large
                result.append({
                    "date": date_str,
                    "super_large_wan": round(super_large, 2),
                    "large_wan": round(large, 2),
                    "medium_wan": round(medium, 2),
                    "small_wan": round(small, 2),
                    "net_flow_wan": round(net_flow, 2),
                })
            except (ValueError, IndexError):
                continue
        return result
    except Exception as e:
        warnings.warn(f"[fund_flow] 东方财富资金流向API失败: {e}")
        return []


def calc_fund_flow_features(
    daily_flow: list[dict[str, Any]],
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """计算资金流向衍生特征。

    Args:
        daily_flow: fetch_fund_flow() 返回的每日资金流向列表
        bars: 近期K线数据（用于计算价资关系）

    Returns:
        特征字典，包含:
        - cum_flow_5d_wan: 近5日累计净流入（万元）
        - cum_flow_10d_wan: 近10日累计净流入（万元）
        - consecutive_inflow_days: 连续流入天数
        - consecutive_outflow_days: 连续流出天数
        - net_flow_pct: 净流入占成交额比
        - flow_price_relation: 价资关系描述
        - daily_flow_5d: 近5日每日净流入列表（用于趋势符号）
    """
    if not daily_flow:
        return {
            "cum_flow_5d_wan": 0,
            "cum_flow_10d_wan": 0,
            "consecutive_inflow_days": 0,
            "consecutive_outflow_days": 0,
            "net_flow_pct": 0.0,
            "flow_price_relation": "无数据",
            "daily_flow_5d": [],
        }

    # 累计净流入
    recent5 = daily_flow[-5:]
    recent10 = daily_flow[-10:]
    cum_5 = sum(d.get("net_flow_wan", 0) for d in recent5)
    cum_10 = sum(d.get("net_flow_wan", 0) for d in recent10)

    # 连续流入/流出天数（net_flow=0 视为当前方向延续）
    consecutive_in = 0
    consecutive_out = 0
    for d in reversed(daily_flow):
        nf = d.get("net_flow_wan", 0)
        if nf > 0:
            if consecutive_out == 0:
                consecutive_in += 1
            else:
                break
        elif nf < 0:
            if consecutive_in == 0:
                consecutive_out += 1
            else:
                break
        else:
            # net_flow=0: 视为当前方向延续
            if consecutive_in > 0:
                consecutive_in += 1
            elif consecutive_out > 0:
                consecutive_out += 1
            else:
                break

    # 净流入占成交额比
    net_flow_pct = 0.0
    if bars and len(bars) >= 5:
        recent_bars = bars[-5:]
        total_amount = sum(float(b.get("amount") or 0) for b in recent_bars)
        if total_amount > 0:
            net_flow_pct = round(cum_5 * 10000 / total_amount, 4)  # wan → yuan

    # 价资关系
    flow_price_relation = _calc_flow_price_relation(daily_flow, bars)

    # 近5日每日净流入
    daily_flow_5d = [d.get("net_flow_wan", 0) for d in recent5]

    return {
        "cum_flow_5d_wan": round(cum_5, 2),
        "cum_flow_10d_wan": round(cum_10, 2),
        "consecutive_inflow_days": consecutive_in,
        "consecutive_outflow_days": consecutive_out,
        "net_flow_pct": net_flow_pct,
        "flow_price_relation": flow_price_relation,
        "daily_flow_5d": daily_flow_5d,
    }


def _calc_flow_price_relation(
    daily_flow: list[dict[str, Any]],
    bars: list[dict[str, Any]] | None,
) -> str:
    """判断价资关系：比较近5日价格变动与资金流向方向。"""
    if not daily_flow or len(daily_flow) < 5:
        return "无数据"

    recent5_flow = daily_flow[-5:]
    cum_flow = sum(d.get("net_flow_wan", 0) for d in recent5_flow)
    flow_in = cum_flow > 0
    flow_out = cum_flow < 0

    if bars and len(bars) >= 6:
        price_start = float(bars[-6].get("close") or 0)
        price_end = float(bars[-1].get("close") or 0)
        if price_start > 0:
            price_change = (price_end - price_start) / price_start
        else:
            price_change = 0.0
    else:
        return "价资关系未知"

    price_up = price_change > 0.02
    price_down = price_change < -0.02
    price_flat = not price_up and not price_down

    if price_up and flow_in:
        return "价涨资入"
    if price_up and flow_out:
        return "价涨资出"
    if price_down and flow_in:
        return "价跌资入"
    if price_down and flow_out:
        return "价跌资出"
    if price_flat and flow_in:
        return "价平资入"
    if price_flat and flow_out:
        return "价平资出"
    return "价资中性"
