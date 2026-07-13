"""资金流向数据采集与特征工程。

通过东方财富HTTP API获取个股日线级资金流向（超大单/大单/中单/小单净流入），
并计算衍生特征供主力行为识别引擎使用。

东财加固（对齐社区 a-stock-data 实践）：
  - Session 复用 + 浏览器 UA/Referer/Origin
  - 合理超时（默认 10s，可用 FUND_FLOW_TIMEOUT 覆盖）
  - 显式 lmt（日级数）+ 429/5xx 轻量重试
  - 代理不可达时快速降级返回 []

备用数据源：通达信 MCP（当东方财富 API 不可用时自动 fallback）。

用法:
    from trader_shared.fund_flow_data import fetch_fund_flow, calc_fund_flow_features
"""

from __future__ import annotations

import json
import os
import warnings
from datetime import datetime, timedelta
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
TDX_MCP_URL = "https://txmcp.tdx.com.cn:3001/txmcp"

# 浏览器特征头：裸 UA 易被东财间歇拒/空返回（社区实测）
_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
    "Accept": "*/*",
}

# Session 复用 + 对 429/5xx 轻量重试；连接失败不无限拖
_EM_SESSION = requests.Session()
_EM_SESSION.trust_env = False  # 跳过系统代理直连
_EM_SESSION.headers.update(_EM_HEADERS)
try:
    _em_retry = Retry(
        total=2,
        connect=1,
        read=1,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    _em_adapter = HTTPAdapter(max_retries=_em_retry)
    _EM_SESSION.mount("https://", _em_adapter)
    _EM_SESSION.mount("http://", _em_adapter)
except TypeError:  # 旧 urllib3 无 allowed_methods 等
    _em_adapter = HTTPAdapter(max_retries=0)
    _EM_SESSION.mount("https://", _em_adapter)
    _EM_SESSION.mount("http://", _em_adapter)

# 兼容旧名（测试/外部若引用）
_FAST_FAIL_SESSION = _EM_SESSION


def _em_timeout() -> float | tuple[float, float]:
    """请求超时：默认 10s；FUND_FLOW_TIMEOUT 可覆盖（秒）。"""
    raw = os.environ.get("FUND_FLOW_TIMEOUT", "10").strip()
    try:
        t = float(raw)
        if t <= 0:
            t = 10.0
    except (TypeError, ValueError):
        t = 10.0
    # (connect, read)：连接卡住别拖满 read
    return (min(5.0, t), t)


_FAST_FAIL_TIMEOUT = 10  # 文档/兼容


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


def _symbol_to_ts_code(symbol: str) -> str:
    """将股票代码转换为 Tushare ts_code 格式（如 '688248' → '688248.SH'）。"""
    if "." in symbol:
        return symbol
    code = symbol.strip()
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"


def _fetch_fund_flow_tushare(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """通过 Tushare moneyflow 获取资金流向。"""
    try:
        from trader_shared.tushare_client import get_client
    except ImportError:
        return []
    client = get_client()
    if not client.available:
        return []
    ts_code = _symbol_to_ts_code(symbol)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    records = client.query_moneyflow(ts_code, start_date, end_date)
    if not records:
        return []
    result: list[dict[str, Any]] = []
    for r in records:
        trade_date = str(r.get("trade_date", ""))
        # Tushare returns YYYYMMDD, convert to YYYY-MM-DD
        if len(trade_date) == 8:
            trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        # Tushare amounts are in 万元 already for moneyflow API
        # 实测 net_mf_amount 字段不准，用成分字段自己算
        _buy_main = (r.get("buy_elg_amount") or 0) + (r.get("buy_lg_amount") or 0)
        _sell_main = (r.get("sell_elg_amount") or 0) + (r.get("sell_lg_amount") or 0)
        net_mf = _buy_main - _sell_main
        result.append({
            "date": trade_date,
            "net_flow_wan": net_mf,
            "buy_elg_amount": r.get("buy_elg_amount", 0) or 0,
            "sell_elg_amount": r.get("sell_elg_amount", 0) or 0,
            "buy_lg_amount": r.get("buy_lg_amount", 0) or 0,
            "sell_lg_amount": r.get("sell_lg_amount", 0) or 0,
            "buy_md_amount": r.get("buy_md_amount", 0) or 0,
            "sell_md_amount": r.get("sell_md_amount", 0) or 0,
            "buy_sm_amount": r.get("buy_sm_amount", 0) or 0,
            "sell_sm_amount": r.get("sell_sm_amount", 0) or 0,
            "buy_elg_vol": r.get("buy_elg_vol", 0) or 0,
            "sell_elg_vol": r.get("sell_elg_vol", 0) or 0,
            "buy_lg_vol": r.get("buy_lg_vol", 0) or 0,
            "sell_lg_vol": r.get("sell_lg_vol", 0) or 0,
            "source": "tushare",
        })
    return result


def _parse_fflow_kline_line(line: str) -> dict[str, Any] | None:
    """解析东财 daykline 单行 → 万元字段。

    字段: date, 主力净流入, 小单, 中单, 大单, 超大单（API 单位：元）。
    """
    parts = str(line or "").split(",")
    if len(parts) < 6:
        return None
    try:
        date_str = parts[0]
        # 元 → 万元
        super_large = float(parts[5]) / 10000.0 if parts[5] != "-" else 0.0
        large = float(parts[4]) / 10000.0 if parts[4] != "-" else 0.0
        medium = float(parts[3]) / 10000.0 if parts[3] != "-" else 0.0
        small = float(parts[2]) / 10000.0 if parts[2] != "-" else 0.0
        main_force = (
            float(parts[1]) / 10000.0 if parts[1] != "-" else super_large + large
        )
        return {
            "date": date_str,
            "super_large_wan": round(super_large, 2),
            "large_wan": round(large, 2),
            "medium_wan": round(medium, 2),
            "small_wan": round(small, 2),
            "net_flow_wan": round(main_force, 2),
        }
    except (ValueError, IndexError, TypeError):
        return None


def _parse_fflow_klines(klines: list[Any], days: int = 30) -> list[dict[str, Any]]:
    """批量解析 klines，取最近 days 条。"""
    if not klines:
        return []
    try:
        n = max(1, int(days))
    except (TypeError, ValueError):
        n = 30
    out: list[dict[str, Any]] = []
    for line in klines[-n:]:
        row = _parse_fflow_kline_line(str(line))
        if row:
            out.append(row)
    return out


def _market_for_akshare(symbol: str) -> tuple[str, str]:
    """返回 (6位代码, market: sh|sz|bj)。"""
    code = symbol.split(".")[0] if "." in symbol else str(symbol)
    code = code.replace("SH", "").replace("SZ", "").replace("sh", "").replace("sz", "")
    # 去掉前缀 sh/sz
    if code[:2].lower() in ("sh", "sz", "bj") and len(code) > 6:
        code = code[2:]
    code = "".join(c for c in code if c.isdigit())[-6:].zfill(6)
    suffix = symbol.split(".")[-1].upper() if "." in symbol else ""
    if suffix in ("SH",) or code.startswith(("6", "9")):
        return code, "sh"
    if suffix in ("BJ",) or code.startswith(("8", "4")):
        return code, "bj"
    return code, "sz"


def _pick_col(columns: list[Any], *candidates: str) -> str | None:
    cols = [str(c) for c in columns]
    for name in candidates:
        if name in cols:
            return name
    # 模糊包含
    for name in candidates:
        for c in cols:
            if name in c:
                return c
    return None


def _to_wan_amount(val: Any) -> float:
    """把金额统一成万元。AkShare/东财常见为元。"""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    # 绝对值很大 → 元
    if abs(x) >= 10000:
        return round(x / 10000.0, 2)
    return round(x, 2)


def _fetch_fund_flow_akshare(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """AkShare 个股资金流（底层多仍为东财；作第二通道）。

    环境 FUND_FLOW_SOURCE=eastmoney 时由上层跳过。
    """
    try:
        import akshare as ak  # type: ignore
    except Exception:
        return []

    code, market = _market_for_akshare(symbol)
    try:
        n = max(1, int(days))
    except (TypeError, ValueError):
        n = 30

    try:
        df = ak.stock_individual_fund_flow(stock=code, market=market)
    except Exception as e:
        warnings.warn(f"[fund_flow] AkShare 失败: {e}")
        return []

    if df is None:
        return []
    try:
        if getattr(df, "empty", True):
            return []
    except Exception:
        return []

    cols = list(df.columns)
    c_date = _pick_col(cols, "日期", "date", "时间")
    c_main = _pick_col(cols, "主力净流入-净额", "主力净流入", "主力净额", "main_net")
    c_super = _pick_col(cols, "超大单净流入-净额", "超大单净流入", "超大单")
    c_large = _pick_col(cols, "大单净流入-净额", "大单净流入", "大单")
    c_mid = _pick_col(cols, "中单净流入-净额", "中单净流入", "中单")
    c_small = _pick_col(cols, "小单净流入-净额", "小单净流入", "小单")
    if not c_date or not c_main:
        warnings.warn("[fund_flow] AkShare 列名不识别，跳过")
        return []

    rows: list[dict[str, Any]] = []
    try:
        tail = df.tail(n)
    except Exception:
        tail = df
    for _, r in tail.iterrows():
        try:
            date_raw = r.get(c_date) if hasattr(r, "get") else r[c_date]
            date_str = str(date_raw)[:10]
            main = _to_wan_amount(r[c_main] if c_main else 0)
            super_l = _to_wan_amount(r[c_super]) if c_super else 0.0
            large = _to_wan_amount(r[c_large]) if c_large else 0.0
            mid = _to_wan_amount(r[c_mid]) if c_mid else 0.0
            small = _to_wan_amount(r[c_small]) if c_small else 0.0
            rows.append({
                "date": date_str,
                "super_large_wan": super_l,
                "large_wan": large,
                "medium_wan": mid,
                "small_wan": small,
                "net_flow_wan": main,
                "source": "akshare",
            })
        except Exception:
            continue
    return rows


def fetch_fund_flow(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """获取个股资金流向数据。

    瀑布：东财 HTTP → AkShare（多半仍东财通道）→ 通达信 MCP。
    FUND_FLOW_SOURCE=eastmoney|akshare|tdx|auto

    Args:
        symbol: 股票代码（如 "688248.SH" 或 "688248"）
        days: 获取天数（默认30）

    Returns:
        每日资金流向列表，每条包含:
        - date: 日期
        - super_large_wan / large_wan / medium_wan / small_wan / net_flow_wan（万元）
    """
    source = os.environ.get("FUND_FLOW_SOURCE", "auto").strip().lower()

    order: list[str]
    if source == "tushare":
        order = ["tushare"]
    elif source == "eastmoney":
        order = ["eastmoney"]
    elif source == "akshare":
        order = ["akshare"]
    elif source == "tdx":
        order = ["tdx"]
    else:
        # Tushare 优先（当 token 可用时），否则走东财 → AkShare → 通达信
        order = ["tushare", "eastmoney", "akshare", "tdx"]

    for name in order:
        if name == "tushare":
            result = _fetch_fund_flow_tushare(symbol, days)
        elif name == "eastmoney":
            result = _fetch_fund_flow_eastmoney(symbol, days)
        elif name == "akshare":
            result = _fetch_fund_flow_akshare(symbol, days)
        elif name == "tdx":
            result = _fetch_fund_flow_tdx_mcp(symbol, days)
        else:
            result = []
        if result:
            # 标注源（东财解析行无 source 时补上）
            for row in result:
                if isinstance(row, dict) and not row.get("source"):
                    row["source"] = name
            return result

    return []


def _fetch_fund_flow_eastmoney(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """东方财富资金流向 daykline（加固请求）。"""
    try:
        try:
            n = max(1, int(days))
        except (TypeError, ValueError):
            n = 30
        # 显式 lmt：要 n 日则至少拉 n，上限 120（与社区实践一致）
        lmt = min(120, max(n, 30))
        params = {
            "secid": _secid(symbol),
            "lmt": str(lmt),
            "klt": "101",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        r = _EM_SESSION.get(
            FFLOW_URL,
            params=params,
            timeout=_em_timeout(),
        )
        if r.status_code != 200:
            warnings.warn(f"[fund_flow] 东方财富HTTP {r.status_code}")
            return []
        data = r.json()
        payload = data.get("data") if isinstance(data, dict) else None
        if not payload:
            return []
        klines = payload.get("klines") or []
        if not isinstance(klines, list) or not klines:
            return []
        return _parse_fflow_klines(klines, days=n)
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

    # 统一按日期升序（有的源返回最新在前）
    daily_flow = sorted(daily_flow, key=lambda x: str(x.get("date") or ""))

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

    # 最新日期（用于 VPF 时效性检查）
    latest_fund_date = ""
    if daily_flow and isinstance(daily_flow[-1], dict):
        latest_fund_date = str(daily_flow[-1].get("date") or "")

    return {
        "cum_flow_5d_wan": round(cum_5, 2),
        "cum_flow_10d_wan": round(cum_10, 2),
        "consecutive_inflow_days": consecutive_in,
        "consecutive_outflow_days": consecutive_out,
        "net_flow_pct": net_flow_pct,
        "flow_price_relation": flow_price_relation,
        "daily_flow_5d": daily_flow_5d,
        "latest_fund_date": latest_fund_date,
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
