"""资金流向数据采集与特征工程。

标准数据格式（统一万元）：
    {
        "date": "2026-07-13",
        "net_flow_wan": -1927,       # 主力净额（超大+大）
        "super_large_wan": -1205,    # 超大单净额
        "large_wan": -722,           # 大单净额
        "medium_wan": 0,             # 中单净额
        "small_wan": 0,              # 小单净额
        "source": "tdx"              # 数据来源
    }

架构：取数器(各源) → 存(标准化) → 计算器(读存储算特征)

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
_FAST_FAIL_SESSION = _EM_SESSION  # 兼容旧名


# ── 标准记录工厂 ──────────────────────────────────────────────
def _make_record(
    date: str,
    net_flow_wan: float,
    super_large_wan: float = 0.0,
    large_wan: float = 0.0,
    medium_wan: float = 0.0,
    small_wan: float = 0.0,
    source: str = "",
) -> dict[str, Any]:
    return {
        "date": date,
        "net_flow_wan": round(net_flow_wan, 2),
        "super_large_wan": round(super_large_wan, 2),
        "large_wan": round(large_wan, 2),
        "medium_wan": round(medium_wan, 2),
        "small_wan": round(small_wan, 2),
        "source": source,
    }


# ══════════════════════════════════════════════════════════════
# 第一层：取数器 — 各数据源独立，只管取
# ══════════════════════════════════════════════════════════════

def _fetch_from_tdx(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """取数器：通达信 MCP → 标准格式（万元）。
    
    TDX API 返回 主力净额金额(元)，转为万元。
    """
    code = symbol.split(".")[0] if "." in symbol else symbol
    try:
        endpoint = "http://tdxhub.icfqs.com:7615/TQLEX"
        payload = {
            "Params": [code, "zjlx", ""]
        }
        # 从 connector 配置读 token
        token = ""
        cdir = os.path.expanduser("~/.workbuddy/connectors")
        for d in os.listdir(cdir):
            cf = os.path.join(cdir, d, "connector-states.v3.json")
            if os.path.exists(cf):
                try:
                    with open(cf) as f:
                        st = json.load(f)
                    t = st.get("headerOverridesBearerStripped") or ""
                    if t:
                        token = t
                        break
                except Exception:
                    continue

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        tables = (data.get("transformed") or data).get("tables", []) if isinstance(data, dict) else []
        rows = []
        for tbl in tables:
            if tbl.get("name") == "capital_flow":
                for r in tbl.get("rows", []):
                    date = str(r.get("日期", ""))[:10]
                    # 主力净额金额(元) → 万元
                    net_yuan = float(r.get("主力净额金额(元)") or 0)
                    rows.append(_make_record(
                        date=date,
                        net_flow_wan=net_yuan / 10000.0,
                        super_large_wan=float(r.get("超大单净买入金额(元)") or 0) / 10000.0,
                        large_wan=float(r.get("大单净买入金额(元)") or 0) / 10000.0,
                        source="tdx",
                    ))
        return rows
    except Exception as e:
        warnings.warn(f"[fund_flow] TDX 取数失败: {e}")
        return []


def _fetch_from_tushare(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """取数器：Tushare moneyflow → 标准格式（万元）。
    
    Tushare 金额已经是万元。不用 net_mf_amount（实测不准），
    用 buy/sell_elg + buy/sell_lg 自己算主力净额。
    """
    try:
        from trader_shared.tushare_client import get_client
    except ImportError:
        return []
    client = get_client()
    ts_code = _symbol_to_ts_code(symbol)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    records = client.query_moneyflow(ts_code, start_date, end_date)
    if not records:
        return []
    result: list[dict[str, Any]] = []
    for r in records:
        trade_date = str(r.get("trade_date", ""))
        if len(trade_date) == 8:
            trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        buy_main = (r.get("buy_elg_amount") or 0) + (r.get("buy_lg_amount") or 0)
        sell_main = (r.get("sell_elg_amount") or 0) + (r.get("sell_lg_amount") or 0)
        net_mf = buy_main - sell_main
        result.append(_make_record(
            date=trade_date,
            net_flow_wan=net_mf,
            super_large_wan=(r.get("buy_elg_amount") or 0) - (r.get("sell_elg_amount") or 0),
            large_wan=(r.get("buy_lg_amount") or 0) - (r.get("sell_lg_amount") or 0),
            medium_wan=(r.get("buy_md_amount") or 0) - (r.get("sell_md_amount") or 0),
            small_wan=(r.get("buy_sm_amount") or 0) - (r.get("sell_sm_amount") or 0),
            source="tushare",
        ))
    result.sort(key=lambda x: str(x.get("date") or ""))
    return result


def _fetch_from_eastmoney(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """取数器：东方财富 → 标准格式（万元）。"""
    try:
        n = max(1, int(days))
    except (TypeError, ValueError):
        n = 30
    lmt = min(120, max(n, 30))
    params = {
        "secid": _secid(symbol),
        "lmt": str(lmt),
        "klt": "101",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
    }
    try:
        r = _EM_SESSION.get(FFLOW_URL, params=params, timeout=_em_timeout())
        if r.status_code != 200:
            return []
        data = r.json()
        payload = data.get("data") if isinstance(data, dict) else None
        if not payload:
            return []
        klines = payload.get("klines") or []
        if not isinstance(klines, list) or not klines:
            return []
        return _parse_em_klines(klines, days=n)
    except Exception as e:
        warnings.warn(f"[fund_flow] 东方财富失败: {e}")
        return []


def _fetch_from_akshare(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """取数器：AkShare → 标准格式（万元）。"""
    try:
        import akshare as ak
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
    if df is None or getattr(df, "empty", True):
        return []
    cols = list(df.columns)
    c_date = _pick_col(cols, "日期", "date", "时间")
    c_main = _pick_col(cols, "主力净流入-净额", "主力净流入", "主力净额", "main_net")
    c_super = _pick_col(cols, "超大单净流入-净额", "超大单净流入", "超大单")
    c_large = _pick_col(cols, "大单净流入-净额", "大单净流入", "大单")
    c_mid = _pick_col(cols, "中单净流入-净额", "中单净流入", "中单")
    c_small = _pick_col(cols, "小单净流入-净额", "小单净流入", "小单")
    if not c_date or not c_main:
        return []
    rows: list[dict[str, Any]] = []
    # 先按日期正序再取最近 n 行，避免 DF 倒序时 tail 拿到最旧段
    try:
        df = df.copy()
        df["__flow_date"] = df[c_date].astype(str).str[:10]
        df = df.sort_values("__flow_date", ascending=True).tail(n)
    except Exception:
        df = df.tail(n)
    for _, r in df.iterrows():
        try:
            date_str = str(r.get(c_date) if hasattr(r, "get") else r[c_date])[:10]
            rows.append(_make_record(
                date=date_str,
                net_flow_wan=_to_wan_amount(r[c_main]),
                super_large_wan=_to_wan_amount(r[c_super]) if c_super else 0.0,
                large_wan=_to_wan_amount(r[c_large]) if c_large else 0.0,
                medium_wan=_to_wan_amount(r[c_mid]) if c_mid else 0.0,
                small_wan=_to_wan_amount(r[c_small]) if c_small else 0.0,
                source="akshare",
            ))
        except Exception:
            continue
    rows.sort(key=lambda x: str(x.get("date") or ""))
    return rows


# ══════════════════════════════════════════════════════════════
# 第二层：存储 — 标准格式写/读缓存
# ══════════════════════════════════════════════════════════════

def _cache_dir() -> str:
    p = os.path.expanduser("~/.trader/cache/fund_flow")
    os.makedirs(p, exist_ok=True)
    return p


def _cache_key(symbol: str) -> str:
    code = symbol.split(".")[0] if "." in symbol else symbol
    return f"{code}.json"


def save_fund_flow(symbol: str, daily_flow: list[dict[str, Any]]) -> None:
    """将标准化资金流向数据写入缓存。"""
    if not daily_flow:
        return
    record = {
        "daily_flow": daily_flow,
        "cached_at": datetime.now().isoformat(),
        "latest_date": daily_flow[-1].get("date", "") if daily_flow else "",
        "source": daily_flow[0].get("source", "") if daily_flow else "",
    }
    path = os.path.join(_cache_dir(), _cache_key(symbol))
    try:
        with open(path, "w") as f:
            json.dump(record, f, ensure_ascii=False)
    except Exception:
        pass


def load_fund_flow(symbol: str, max_age_hours: float = 6) -> list[dict[str, Any]]:
    """从缓存读取标准化资金流向数据。过期返回空列表。"""
    path = os.path.join(_cache_dir(), _cache_key(symbol))
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            record = json.load(f)
        # 检查时效
        cached_at = record.get("cached_at", "")
        if cached_at:
            try:
                ct = datetime.fromisoformat(cached_at)
                if (datetime.now() - ct).total_seconds() > max_age_hours * 3600:
                    return []
            except Exception:
                pass
        rows = record.get("daily_flow", [])
        return _sort_fund_flow_asc(rows) if isinstance(rows, list) else []
    except Exception:
        return []


def _sort_fund_flow_asc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows or [], key=lambda x: str(x.get("date") or ""))


# ══════════════════════════════════════════════════════════════
# 第三层：调度 — 瀑布选最优源 → 存 → 返回
# ══════════════════════════════════════════════════════════════

FETCHERS: dict[str, Any] = {
    "tdx": _fetch_from_tdx,
    "tushare": _fetch_from_tushare,
    "eastmoney": _fetch_from_eastmoney,
    "akshare": _fetch_from_akshare,
}


def fetch_fund_flow(symbol: str, days: int = 30) -> list[dict[str, Any]]:
    """获取个股资金流向数据（标准格式，万元）。

    流程：缓存命中 → 直接读；否则瀑布选最优源 → 存 → 返回。

    Args:
        symbol: 股票代码（如 "688248.SH"）
        days: 获取天数

    Returns:
        每日资金流向列表，每条含 date / net_flow_wan / super_large_wan / large_wan ...
    """
    # 1. 尝试读缓存
    cached = load_fund_flow(symbol)
    if cached:
        return cached

    # 2. 瀑布调度（WorkBuddy：tdx 优先；Hermes：tushare 优先）
    source = os.environ.get("FUND_FLOW_SOURCE", "auto").strip().lower()
    if source == "auto":
        try:
            from trader_shared.trader_host import fund_flow_source_order

            order = fund_flow_source_order()
        except Exception:
            order = ["tushare", "tdx", "eastmoney", "akshare"]
    else:
        order = [source]

    for name in order:
        fetcher = FETCHERS.get(name)
        if not fetcher:
            continue
        result = fetcher(symbol, days)
        if result:
            # 按日期升序
            result.sort(key=lambda x: x.get("date", ""))
            save_fund_flow(symbol, result)
            return result

    return []


# ══════════════════════════════════════════════════════════════
# 第四层：计算器 — 读存储算特征，不问来源
# ══════════════════════════════════════════════════════════════

def calc_fund_flow_features(
    daily_flow: list[dict[str, Any]],
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """计算资金流向衍生特征。

    Args:
        daily_flow: fetch_fund_flow() 返回的标准格式列表
        bars: 近期K线数据

    Returns:
        特征字典（cum_flow_5d_wan / consecutive_inflow_days 等）
    """
    if not daily_flow:
        return _empty_features()

    if not daily_flow:
        return _empty_features()

    # 统一按日期升序
    daily_flow = sorted(daily_flow, key=lambda x: str(x.get("date") or ""))

    recent5 = daily_flow[-5:]
    recent10 = daily_flow[-10:]
    cum_5 = sum((d.get("net_flow_wan") or 0) for d in recent5)
    cum_10 = sum((d.get("net_flow_wan") or 0) for d in recent10)

    # 连续流入/流出天数
    consecutive_in = 0
    consecutive_out = 0
    for d in reversed(daily_flow):
        nf = d.get("net_flow_wan") or 0
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
            # 零流入打断连续，不计入流出/流入天数
            break

    # 净流入占成交额比
    net_flow_pct = 0.0
    if bars and len(bars) >= 5:
        recent_bars = bars[-5:]
        total_amount = sum(float(b.get("amount") or 0) for b in recent_bars)
        if total_amount > 0:
            net_flow_pct = round(cum_5 * 10000 / total_amount, 4)

    daily_flow_5d = [d.get("net_flow_wan") or 0 for d in recent5]
    latest_fund_date = str(daily_flow[-1].get("date") or "") if daily_flow else ""
    source = str(daily_flow[-1].get("source") or "") if daily_flow else ""

    return {
        "cum_flow_5d_wan": round(cum_5, 2),
        "cum_flow_10d_wan": round(cum_10, 2),
        "consecutive_inflow_days": consecutive_in,
        "consecutive_outflow_days": consecutive_out,
        "net_flow_pct": net_flow_pct,
        "flow_price_relation": _calc_flow_price_relation(daily_flow, bars),
        "daily_flow_5d": daily_flow_5d,
        "latest_fund_date": latest_fund_date,
        "data_source": source,
    }


def calc_fund_flow_features_from_bars(
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """从K线数据推算近似资金流向特征（API不可用时的降级）。"""
    if not bars or len(bars) < 10:
        return _empty_features()

    daily_estimates: list[float] = []
    for b in bars:
        close = float(b.get("close") or 0)
        open_ = float(b.get("open") or 0)
        volume = float(b.get("volume") or 0)
        if open_ > 0 and volume > 0:
            amount = close * volume
            change = (close - open_) / open_
            est = amount * abs(change) / 10000.0
            daily_estimates.append(est * (1 if change > 0 else -1))
        else:
            daily_estimates.append(0)

    cum_5 = sum(daily_estimates[-5:])
    cum_10 = sum(daily_estimates[-10:])

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
            # 零流入打断连续，不计入流出/流入天数
            break

    total_amount_5d = sum(
        float(bars[-(i+1)].get("close", 0) or 0) * float(bars[-(i+1)].get("volume", 0) or 0)
        for i in range(min(5, len(bars)))
    )
    net_flow_pct = round(cum_5 * 10000 / total_amount_5d, 4) if total_amount_5d > 0 else 0.0

    recent5 = bars[-5:]
    if len(recent5) >= 2 and (recent5[0].get("close") or 0) > 0:
        price_up = (recent5[-1].get("close") or 0) > (recent5[0].get("close") or 0)
        flow_up = cum_5 > 0
        if price_up and flow_up:
            fp_rel = "价涨资入"
        elif price_up and not flow_up:
            fp_rel = "价涨资出"
        elif not price_up and flow_up:
            fp_rel = "价跌资入"
        else:
            fp_rel = "价跌资出"
    else:
        fp_rel = "无数据"

    return {
        "cum_flow_5d_wan": round(cum_5, 2),
        "cum_flow_10d_wan": round(cum_10, 2),
        "consecutive_inflow_days": consecutive_in,
        "consecutive_outflow_days": consecutive_out,
        "net_flow_pct": net_flow_pct,
        "flow_price_relation": fp_rel,
        "daily_flow_5d": [round(x, 2) for x in daily_estimates[-5:]],
        "data_source": "bars_estimate",
    }


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════

def _empty_features() -> dict[str, Any]:
    return {
        "cum_flow_5d_wan": 0,
        "cum_flow_10d_wan": 0,
        "consecutive_inflow_days": 0,
        "consecutive_outflow_days": 0,
        "net_flow_pct": 0.0,
        "flow_price_relation": "无数据",
        "daily_flow_5d": [],
        "latest_fund_date": "",
        "data_source": "",
    }


def _calc_flow_price_relation(
    daily_flow: list[dict[str, Any]],
    bars: list[dict[str, Any]] | None,
) -> str:
    if not daily_flow or len(daily_flow) < 5:
        return "无数据"
    recent5_flow = daily_flow[-5:]
    cum_flow = sum((d.get("net_flow_wan") or 0) for d in recent5_flow)
    flow_in = cum_flow > 0
    flow_out = cum_flow < 0

    if bars and len(bars) >= 6:
        price_start = float(bars[-6].get("close") or 0)
        price_end = float(bars[-1].get("close") or 0)
        price_change = (price_end - price_start) / price_start if price_start > 0 else 0.0
    else:
        return "价资关系未知"

    price_up = price_change > 0.02
    price_down = price_change < -0.02
    price_flat = not price_up and not price_down

    if price_up and flow_in: return "价涨资入"
    if price_up and flow_out: return "价涨资出"
    if price_down and flow_in: return "价跌资入"
    if price_down and flow_out: return "价跌资出"
    if price_flat and flow_in: return "价平资入"
    if price_flat and flow_out: return "价平资出"
    return "价资中性"


def _em_timeout() -> float | tuple[float, float]:
    raw = os.environ.get("FUND_FLOW_TIMEOUT", "10").strip()
    try:
        t = float(raw)
        if t <= 0:
            t = 10.0
    except (TypeError, ValueError):
        t = 10.0
    return (min(5.0, t), t)


def _secid(symbol: str) -> str:
    code = symbol.split(".")[0] if "." in symbol else symbol
    suffix = symbol.split(".")[-1] if "." in symbol else ""
    if suffix in ("SH", "sh"):
        return f"1.{code}"
    if suffix in ("SZ", "sz"):
        return f"0.{code}"
    return f"1.{code}" if code.startswith(("6", "9")) else f"0.{code}"


def _symbol_to_ts_code(symbol: str) -> str:
    if "." in symbol:
        return symbol
    code = symbol.strip()
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"


def _parse_em_klines(klines: list[Any], days: int = 30) -> list[dict[str, Any]]:
    if not klines:
        return []
    n = max(1, int(days))
    out: list[dict[str, Any]] = []
    for line in klines:
        row = _parse_em_kline_line(str(line))
        if row:
            out.append(row)
    # 先正序再取最近 n 根，避免源倒序时 [-n:] 拿到最旧段
    out.sort(key=lambda x: str(x.get("date") or ""))
    return out[-n:] if len(out) > n else out


def _parse_em_kline_line(line: str) -> dict[str, Any] | None:
    """东财行 → 标准格式。
    
    字段: date, 主力净, 小单, 中单, 大单, 超大单（API 单位：元）。
    """
    parts = str(line or "").split(",")
    if len(parts) < 6:
        return None
    try:
        date_str = parts[0]
        super_large = float(parts[5]) / 10000.0 if parts[5] != "-" else 0.0
        large = float(parts[4]) / 10000.0 if parts[4] != "-" else 0.0
        medium = float(parts[3]) / 10000.0 if parts[3] != "-" else 0.0
        small = float(parts[2]) / 10000.0 if parts[2] != "-" else 0.0
        main_force = float(parts[1]) / 10000.0 if parts[1] != "-" else super_large + large
        return _make_record(
            date=date_str,
            net_flow_wan=main_force,
            super_large_wan=round(super_large, 2),
            large_wan=round(large, 2),
            medium_wan=round(medium, 2),
            small_wan=round(small, 2),
        )
    except (ValueError, IndexError, TypeError):
        return None


def _market_for_akshare(symbol: str) -> tuple[str, str]:
    code = symbol.split(".")[0] if "." in symbol else str(symbol)
    code = code.replace("SH", "").replace("SZ", "").replace("sh", "").replace("sz", "")
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
    for name in candidates:
        for c in cols:
            if name in c:
                return c
    return None


def _to_wan_amount(val: Any) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.0
    if x != x:
        return 0.0
    if abs(x) >= 10000:
        return round(x / 10000.0, 2)
    return round(x, 2)
