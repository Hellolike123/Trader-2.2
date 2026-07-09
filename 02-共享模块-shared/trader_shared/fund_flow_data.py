"""资金流向数据采集与特征工程。

通过东方财富HTTP API获取个股日线级资金流向（超大单/大单/中单/小单净流入），
并计算衍生特征供主力行为识别引擎使用。

备用数据源：通达信 MCP（当东方财富 API 不可用时自动 fallback）。

用法:
    from trader_shared.fund_flow_data import fetch_fund_flow, calc_fund_flow_features
"""

from __future__ import annotations

import json
import warnings
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
TDX_MCP_URL = "https://txmcp.tdx.com.cn:3001/txmcp"

# 加固：东方财富 API 在代理/网络不可达时，默认 urllib3 会做多次重试，
# 单次 10s × 3 重试 = 30s 挂起才放弃。改为「不重试 + 3s 超时」，
# 让 fund_flow_data 快速降级（返回 []），避免代理环境长时间阻塞 + warning 刷屏。
_FAST_FAIL_SESSION = requests.Session()
_FAST_FAIL_ADAPTER = HTTPAdapter(
    max_retries=Retry(
        total=0,  # 禁用重试
        connect=0,
        read=0,
        other=0,
    ),
)
_FAST_FAIL_SESSION.mount("https://", _FAST_FAIL_ADAPTER)
_FAST_FAIL_SESSION.mount("http://", _FAST_FAIL_ADAPTER)

# 单次请求超时（秒）：代理挡住时 3s 即放弃
_FAST_FAIL_TIMEOUT = 3


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


def _fetch_fund_flow_tdx_mcp(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """通过通达信 MCP 获取资金流向数据（备用数据源）。

    MCP 协议调用 tdx-connector 的资金流向工具。
    需要 WorkBuddy 环境下的 OAuth 认证（自动管理）。
    """
    import os
    # 检查是否启用 TDX MCP
    source = os.environ.get("FUND_FLOW_SOURCE", "auto")
    if source == "eastmoney":
        return []  # 明确指定东方财富时跳过 TDX

    code = symbol.split(".")[0] if "." in symbol else symbol
    try:
        # MCP 协议：调用工具
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_fund_flow",
                "arguments": {"code": code, "days": days}
            }
        }
        headers = {"Content-Type": "application/json"}

        # 尝试从 WorkBuddy connector 读取 token
        token_file = os.path.expanduser(
            "~/.workbuddy/connectors/572cf11d-9298-4719-8350-617354ea6617/connector-states.json"
        )
        if os.path.exists(token_file):
            with open(token_file) as f:
                states = json.load(f)
                bearer = states.get("headerOverridesBearerStripped")
                if bearer:
                    headers["Authorization"] = f"Bearer {bearer}"

        r = requests.post(TDX_MCP_URL, json=payload, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        data = r.json()
        if "error" in data:
            warnings.warn(f"[fund_flow] TDX MCP 错误: {data['error']}")
            return []

        # 解析 MCP 响应（格式取决于 tdx-connector 的实现）
        result_data = data.get("result", {})
        if isinstance(result_data, dict) and "content" in result_data:
            content = result_data["content"]
            if isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
                if text:
                    return json.loads(text)

        return []
    except Exception as e:
        warnings.warn(f"[fund_flow] TDX MCP 失败: {e}")
        return []


def fetch_fund_flow(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """获取个股资金流向数据。

    优先使用东方财富 API，失败时自动 fallback 到通达信 MCP。

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
        - net_flow_wan: 主力净流入（万元）
    """
    import os
    source = os.environ.get("FUND_FLOW_SOURCE", "auto")

    # 东方财富
    if source != "tdx":
        result = _fetch_fund_flow_eastmoney(symbol, days)
        if result:
            return result

    # TDX MCP 备用
    if source != "eastmoney":
        result = _fetch_fund_flow_tdx_mcp(symbol, days)
        if result:
            return result

    return []


def _fetch_fund_flow_eastmoney(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """东方财富资金流向 API（原始实现）。"""
    try:
        params = {
            "secid": _secid(symbol),
            "lmt": "0",
            "klt": "101",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        r = _FAST_FAIL_SESSION.get(
            FFLOW_URL, params=params, headers={"User-Agent": "Mozilla/5.0"},
            timeout=_FAST_FAIL_TIMEOUT,
        )
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
                # 东方财富 API 字段顺序: parts[1]=主力净流入(超大+大), parts[2]=小单, parts[3]=中单, parts[4]=大单, parts[5]=超大单
                # Fix P0: 字段映射全部错位，以 parts[4]+parts[5]=parts[1] 的约束关系验证
                # fix: unit mismatch — eastmoney API returns yuan, _wan fields require wan (÷10000)
                super_large = float(parts[5]) / 10000.0 if parts[5] != "-" else 0.0
                large = float(parts[4]) / 10000.0 if parts[4] != "-" else 0.0
                medium = float(parts[3]) / 10000.0 if parts[3] != "-" else 0.0
                small = float(parts[2]) / 10000.0 if parts[2] != "-" else 0.0
                main_force = float(parts[1]) / 10000.0 if parts[1] != "-" else super_large + large
                # 主力净流入 = 超大单 + 大单（用于缓存格式兼容，保留 net_flow 字段）
                net_flow = main_force
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
        warnings.warn(f"[fund_flow] 东方财富API失败: {e}")
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
    # fix: None guard — d.get(k, 0) returns None when key exists with None value
    cum_5 = sum((d.get("net_flow_wan") or 0) for d in recent5)
    cum_10 = sum((d.get("net_flow_wan") or 0) for d in recent10)

    # 连续流入/流出天数
    # net_flow=0 时：若已有方向则延续，否则中断
    consecutive_in = 0
    consecutive_out = 0
    for d in reversed(daily_flow):
        nf = d.get("net_flow_wan") or 0  # fix: None guard
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
            # net_flow=0: 若已有方向则延续，否则中断
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
    daily_flow_5d = [d.get("net_flow_wan") or 0 for d in recent5]  # fix: None guard

    return {
        "cum_flow_5d_wan": round(cum_5, 2),
        "cum_flow_10d_wan": round(cum_10, 2),
        "consecutive_inflow_days": consecutive_in,
        "consecutive_outflow_days": consecutive_out,
        "net_flow_pct": net_flow_pct,
        "flow_price_relation": flow_price_relation,
        "daily_flow_5d": daily_flow_5d,
    }


def calc_fund_flow_features_from_bars(
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """从K线数据推导近似资金流向特征。

    当东方财富 API 不可用时，用价格 + 成交量估算主力方向。
    原理：上涨放量 ≈ 主力买入，下跌放量 ≈ 主力卖出。

    注意：此为近似值，精度远低于真实资金流向数据，
    仅用于 detect_main_force_stage 的 fallback 分支。

    Args:
        bars: 近期 K 线数据（至少 10 根）

    Returns:
        与 calc_fund_flow_features() 相同结构的特征字典
    """
    if not bars or len(bars) < 10:
        return {
            "cum_flow_5d_wan": 0,
            "cum_flow_10d_wan": 0,
            "consecutive_inflow_days": 0,
            "consecutive_outflow_days": 0,
            "net_flow_pct": 0.0,
            "flow_price_relation": "无数据",
            "daily_flow_5d": [],
        }

    # 每日估算净流量（万元）
    # 方法：当日涨跌方向 * 成交额 → 正为流入，负为流出
    # 成交额 = close * volume (简化)
    daily_estimates: list[float] = []
    for b in bars:
        close = float(b.get("close") or 0)
        open_ = float(b.get("open") or 0)
        volume = float(b.get("volume") or 0)  # 股数
        if open_ > 0 and volume > 0:
            # 成交额
            amount = close * volume
            # 涨跌幅方向
            change = (close - open_) / open_
            # 估算净流量（万元）: 成交额 * 涨跌幅方向 / 10000
            # 除 10000 因为 volume 是股数, amount 是元
            est = amount * abs(change) / 10000.0
            daily_estimates.append(est * (1 if change > 0 else -1))
        else:
            daily_estimates.append(0)

    # 累计净流入
    cum_5 = sum(daily_estimates[-5:])
    cum_10 = sum(daily_estimates[-10:])

    # 连续流入/流出天数（从 K 线数据推导）
    consecutive_in = 0
    consecutive_out = 0
    for est in reversed(daily_estimates):
        if est > 0:
            if consecutive_out == 0:
                consecutive_in += 1
            else:
                break
        elif est < 0:
            if consecutive_in == 0:
                consecutive_out += 1
            else:
                break
        else:
            if consecutive_in > 0:
                consecutive_in += 1
            elif consecutive_out > 0:
                consecutive_out += 1
            else:
                break

    # 净流入占成交额比（近似）
    total_amount_5d = sum(
        float(bars[-(i+1)].get("close", 0) or 0) * float(bars[-(i+1)].get("volume", 0) or 0)
        for i in range(min(5, len(bars)))
    )
    net_flow_pct = round(cum_5 * 10000 / total_amount_5d, 4) if total_amount_5d > 0 else 0.0

    # 价资关系：用近5日累计估算流向 vs 价格变动
    recent5 = bars[-5:]
    if len(recent5) >= 2 and (recent5[0].get("close") or 0) > 0:  # fix: None guard
        price_up = (recent5[-1].get("close") or 0) > (recent5[0].get("close") or 0)
        flow_up = cum_5 > 0
        if price_up and flow_up:
            flow_price_relation = "价涨资入"
        elif price_up and not flow_up:
            flow_price_relation = "价涨资出"
        elif not price_up and flow_up:
            flow_price_relation = "价跌资入"
        else:
            flow_price_relation = "价跌资出"
    else:
        flow_price_relation = "无数据"

    daily_flow_5d = [round(x, 2) for x in daily_estimates[-5:]]

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
    cum_flow = sum((d.get("net_flow_wan") or 0) for d in recent5_flow)  # fix: None guard
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
