from __future__ import annotations

import hashlib
import json
import math
import random
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from models import BarData, QuoteData
except ImportError:
    BarData = dict
    QuoteData = dict

try:
    from mootdx.quotes import Quotes
    _MOOTDX_AVAILABLE = True
except ImportError:
    Quotes = None
    _MOOTDX_AVAILABLE = False


TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
TIMEOUT_SECONDS = 5
MAX_ATTEMPTS = 2
NAME_MAP = {
    "南网科技": "688248",
    "中国铝业": "601600",
    "三安光电": "600703",
    "贵州茅台": "600519",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "东方财富": "300059",
    "招商银行": "600036",
    "中国平安": "601318",
    "中证1000": "000852",
}

# 缓存：只用于历史数据（昨日及更早的日线）
_cache: dict[str, Any] = {}
_cache_expiry: dict[str, float] = {}

# 实时行情缓存（30秒TTL）
_realtime_cache: dict[str, tuple[Any, float]] = {}
_REALTIME_TTL = 30

DataStatus = Literal["full", "partial", "degraded", "failed"]

_MOOTDX_CLIENT: Quotes | None = None


def _get_mootdx_client() -> Quotes | None:
    global _MOOTDX_CLIENT
    if _MOOTDX_CLIENT is not None:
        return _MOOTDX_CLIENT
    if not _MOOTDX_AVAILABLE:
        return None
    try:
        _MOOTDX_CLIENT = Quotes.factory(market='std')
        return _MOOTDX_CLIENT
    except Exception:
        _MOOTDX_CLIENT = None
        return None


MOOTDX_CATEGORY = {"daily": 4, "weekly": 5, "monthly": 6, "1m": 7, "5m": 8, "15m": 9, "30m": 10, "60m": 11}

_MOOTDX_MARKET = {"SH": 1, "SZ": 0, "BJ": 2}


def _mootdx_market(sec: Security) -> int:
    return _MOOTDX_MARKET.get(sec.market.upper(), 0)


def _fetch_qfq_mootdx(sec: Security, days: int = 30) -> list[dict[str, Any]] | None:
    client = _get_mootdx_client()
    if client is None:
        return None
    try:
        df = client.bars(symbol=sec.code, category=MOOTDX_CATEGORY["daily"], offset=max(days, 20), market=_mootdx_market(sec))
        if df is None or len(df) == 0:
            return None
        bars = []
        for _, row in df.iterrows():
            raw_dt = str(row.get("datetime", ""))
            bars.append({
                "date": raw_dt.split(" ")[0],
                "open": to_float(row.get("open")),
                "close": to_float(row.get("close")),
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "volume": to_float(row.get("vol")),
                "amount": to_float(row.get("amount")),
            })
        return bars
    except Exception:
        return None


def _fetch_quote_mootdx(sec: Security) -> dict[str, Any] | None:
    client = _get_mootdx_client()
    if client is None:
        return None
    try:
        qs = client.quotes(symbol=[sec.code], market=_mootdx_market(sec))
        if qs is None or len(qs) == 0:
            return None
        q = dict(qs.iloc[0])
        now = datetime.now()
        price_v = to_float(q.get("price"))
        last_close_v = to_float(q.get("last_close"))
        result: dict[str, Any] = {
            "name": sec.name,
            "symbol": sec.ts_code,
            "trade_date": now.strftime("%Y-%m-%d"),
            "trade_time": str(q.get("servertime", ""))[:8] if q.get("servertime") else None,
            "current_price": price_v,
            "pre_close": last_close_v,
            "open": to_float(q.get("open")),
            "high": to_float(q.get("high")),
            "low": to_float(q.get("low")),
            "volume": to_float(q.get("vol")),
            "amount": to_float(q.get("amount")),
            "turnover_rate": None,
            "current_change_pct": round(((price_v or 0) / (last_close_v or 1) - 1) * 100, 2) if price_v and last_close_v else None,
            "order_book": _extract_order_book(q),
        }
        return result
    except Exception:
        return None


def _extract_order_book(q: dict[str, Any]) -> dict[str, Any] | None:
    """从 mootdx quote 原始字典提取五档盘口"""
    bids = []
    asks = []
    for i in range(1, 6):
        bid_p = to_float(q.get(f"bid{i}"))
        bid_v = to_float(q.get(f"bid_vol{i}"))
        ask_p = to_float(q.get(f"ask{i}"))
        ask_v = to_float(q.get(f"ask_vol{i}"))
        if bid_p and bid_v:
            bids.append({"price": bid_p, "volume": int(bid_v)})
        if ask_p and ask_v:
            asks.append({"price": ask_p, "volume": int(ask_v)})
    if not bids and not asks:
        return None
    bid_total = sum(b["volume"] for b in bids)
    ask_total = sum(a["volume"] for a in asks)
    return {
        "bids": bids,
        "asks": asks,
        "bid_total": bid_total,
        "ask_total": ask_total,
        "imbalance": round(bid_total / ask_total, 2) if ask_total > 0 else 99,
    }


@dataclass(frozen=True)
class MarketSnapshot:
    security: "Security"
    quote: dict[str, Any]
    daily_bars: list[dict[str, Any]]
    bars_5m: list[dict[str, Any]] = field(default_factory=list)
    order_book: dict[str, Any] | None = None
    data_status: DataStatus = "full"
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def is_usable(self) -> bool:
        return bool(self.quote and self.daily_bars)


def is_trading_time() -> bool:
    """判断当前是否是交易时间（9:30-15:00，周末返回False）"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周六、周日
        return False
    current_time = now.hour * 100 + now.minute
    # 9:30-11:30 或 13:00-15:00
    return (930 <= current_time <= 1130) or (1300 <= current_time <= 1500)


def get_cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    """生成缓存key"""
    raw = f"{url}|{json.dumps(params, sort_keys=True) if params else ''}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_from_cache(key: str) -> Any:
    """从缓存获取数据（检查过期时间）"""
    if key in _cache and key in _cache_expiry:
        if time.time() < _cache_expiry[key]:
            return _cache[key]
    return None


def save_to_cache(key: str, data: Any, ttl_seconds: int = 3600) -> None:
    """保存数据到缓存（默认1小时过期）"""
    _cache[key] = data
    _cache_expiry[key] = time.time() + ttl_seconds


def get_realtime_cache(key: str) -> Any:
    """从实时缓存获取数据（30秒TTL）"""
    if key in _realtime_cache:
        data, ts = _realtime_cache[key]
        if time.time() < ts + _REALTIME_TTL:
            return data
    return None


def save_realtime_cache(key: str, data: Any) -> None:
    """保存实时数据到缓存（30秒过期）"""
    _realtime_cache[key] = (data, time.time())


@dataclass(frozen=True)
class Security:
    code: str
    market: str
    name: str

    @property
    def ts_code(self) -> str:
        return f"{self.code}.{self.market}"

    @property
    def qq_symbol(self) -> str:
        return f"{self.market.lower()}{self.code}"


class HttpClient:
    def __init__(self) -> None:
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://finance.sina.com.cn/",
        }
        self.ssl_context = ssl._create_unverified_context()

    def get_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        full_url = f"{url}?{urlencode(params)}" if params else url
        request = Request(full_url, headers=self.headers)
        with urlopen(request, timeout=TIMEOUT_SECONDS, context=self.ssl_context) as response:
            return response.read()

    def get_text(self, url: str, params: dict[str, Any] | None = None, encoding: str = "utf-8") -> str:
        return self.get_bytes(url, params=params).decode(encoding, errors="ignore")

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return json.loads(self.get_text(url, params=params))


def retry(fn, url: str = ""):
    """带重试的HTTP请求，包含详细错误信息"""
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(0.08 * (2**attempt) + random.uniform(0, 0.02))
    # 提供更详细的错误信息
    url_info = f" (URL: {url})" if url else ""
    raise RuntimeError(f"Request failed after {MAX_ATTEMPTS} attempts: {last or 'unknown error'}{url_info}")


def to_float(value: Any) -> float | None:
    if value in (None, "", "-", "--", "null", "None"):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def resolve_security(target: str) -> Security:
    raw = str(target).strip()
    mapped = NAME_MAP.get(raw, raw)
    cleaned = mapped.upper().strip()
    market = ""
    if "." in cleaned:
        code, market = cleaned.split(".", 1)
    elif cleaned.startswith(("SH", "SZ", "BJ")):
        market, code = cleaned[:2], cleaned[2:]
    else:
        digits = re.sub(r"\D", "", cleaned)
        if not digits:
            raise RuntimeError(f"无法解析股票名称：{raw}，请改用 6 位代码")
        code = digits
    code = code[-6:].zfill(6)
    if not market:
        market = "SH" if code.startswith(("6", "688", "689")) else "BJ" if code.startswith(("8", "4")) else "SZ"
    return Security(code=code, market=market, name=raw if raw in NAME_MAP else code)


def extract_jsonp(text: str) -> Any:
    raw = text.strip()
    if "=" in raw:
        raw = raw.split("=", 1)[1].strip()
    return json.loads(raw.rstrip(";"))


def parse_trade_datetime(fields: list[str]) -> tuple[str, str | None]:
    trade_date = datetime.now().strftime("%Y-%m-%d")
    trade_time = None
    for item in reversed(fields):
        text = str(item).strip()
        if re.fullmatch(r"\d{8}", text):
            trade_date = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            trade_date = text
        elif re.fullmatch(r"\d{2}:\d{2}:\d{2}", text):
            trade_time = text
    return trade_date, trade_time


def fetch_quote(sec: Security, http: HttpClient) -> QuoteData:
    cache_key = f"quote:{sec.qq_symbol}"
    cached = get_realtime_cache(cache_key)
    if cached is not None:
        return cached

    # mootdx 主源
    mootdx_q = _fetch_quote_mootdx(sec)
    if mootdx_q is not None:
        # 腾讯补充 turnover_rate
        try:
            text = http.get_text(TENCENT_QUOTE_URL + sec.qq_symbol, encoding="gbk")
            match = re.search(r'="([^"]*)"', text)
            if match:
                fields = match.group(1).split("~")
                if len(fields) > 38:
                    mootdx_q["turnover_rate"] = to_float(fields[38])
        except Exception:
            pass
        save_realtime_cache(cache_key, mootdx_q)
        return mootdx_q

    # mootdx 不可用时，腾讯全量降级
    def do_fetch():
        text = http.get_text(TENCENT_QUOTE_URL + sec.qq_symbol, encoding="gbk")
        match = re.search(r'="([^"]*)"', text)
        if not match:
            raise RuntimeError("Tencent quote payload missing fields")
        fields = match.group(1).split("~")
        if len(fields) < 40:
            raise RuntimeError("Tencent quote payload incomplete")
        trade_date, trade_time = parse_trade_datetime(fields)
        result = {
            "name": fields[1] or sec.name,
            "symbol": sec.ts_code,
            "trade_date": trade_date,
            "trade_time": trade_time,
            "current_price": to_float(fields[3]),
            "pre_close": to_float(fields[4]),
            "open": to_float(fields[5]),
            "high": to_float(fields[33]) if len(fields) > 33 else None,
            "low": to_float(fields[34]) if len(fields) > 34 else None,
            "volume": to_float(fields[36]) if len(fields) > 36 else None,
            "amount": to_float(fields[37]) if len(fields) > 37 else None,
            "turnover_rate": to_float(fields[38]) if len(fields) > 38 else None,
            "current_change_pct": to_float(fields[32]) if len(fields) > 32 else None,
        }
        save_realtime_cache(cache_key, result)
        return result

    return retry(do_fetch, url=TENCENT_QUOTE_URL)


def _compute_atr_fields(bars: list[dict[str, Any]]) -> None:
    """对日线 bar 列表原地附加 TR / ATR14 / ATR7 / ATR_ratio 字段。
    需要至少 8 根 bar 才能计算 atr7，15 根才能计算 atr14。
    不足时字段值为 0.0，不会报错。
    """
    if not bars:
        return
    for i, bar in enumerate(bars):
        h: float = bar.get("high") or 0.0
        l: float = bar.get("low") or 0.0
        if i == 0:
            bar["tr"] = round(h - l, 4)
        else:
            pc: float = bars[i - 1].get("close") or bars[i - 1].get("open") or 0.0
            h_l = h - l
            h_pc = abs(h - pc)
            l_pc = abs(l - pc)
            bar["tr"] = round(max(h_l, h_pc, l_pc), 4)
    trs = [b.get("tr", 0.0) or 0.0 for b in bars]
    for i, bar in enumerate(bars):
        if i >= 6:
            bar["atr7"] = round(sum(trs[i - 6 : i + 1]) / 7, 4)
        else:
            bar["atr7"] = 0.0
        if i >= 13:
            bar["atr14"] = round(sum(trs[i - 13 : i + 1]) / 14, 4)
        else:
            bar["atr14"] = 0.0
        close = bar.get("close")
        atr14 = bar.get("atr14", 0.0) or 0.0
        if close and atr14 > 0:
            bar["atr_ratio"] = round(atr14 / float(close), 4)
        else:
            bar["atr_ratio"] = 0.0


def fetch_qfq_daily(sec: Security, http: HttpClient, days: int = 30) -> list[dict[str, Any]]:
    # mootdx 主源
    mootdx_bars = _fetch_qfq_mootdx(sec, days)
    if mootdx_bars is not None:
        _compute_atr_fields(mootdx_bars)
        return mootdx_bars

    # mootdx 不可用时，腾讯降级
    raw_params = f"_var=kline_dayhfq&param={sec.qq_symbol},day,,,{max(days, 20)},qfq"
    cache_key = get_cache_key(TENCENT_FQKLINE_URL, raw_params)

    cached = get_from_cache(cache_key)
    if cached is not None:
        return cached

    def do_fetch():
        full_url = f"{TENCENT_FQKLINE_URL}?{raw_params}"
        payload = extract_jsonp(http.get_text(full_url))
        sec_data = (payload.get("data") or {}).get(sec.qq_symbol) or {}
        rows = sec_data.get("qfqday") or []
        bars: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, list) and len(row) >= 6:
                bars.append({"date": row[0], "open": to_float(row[1]), "close": to_float(row[2]), "high": to_float(row[3]), "low": to_float(row[4]), "volume": to_float(row[5])})
        if not bars:
            day_rows = sec_data.get("day") or []
            for row in day_rows:
                if isinstance(row, list) and len(row) >= 6:
                    bars.append({"date": row[0], "open": to_float(row[1]), "close": to_float(row[2]), "high": to_float(row[3]), "low": to_float(row[4]), "volume": to_float(row[5])})
        if not bars:
            raise RuntimeError("Tencent qfq daily bars unavailable")
        return bars

    result = retry(do_fetch)
    _compute_atr_fields(result)

    has_today = any(bar.get("date") == datetime.now().strftime("%Y-%m-%d") for bar in result)
    if not has_today:
        save_to_cache(cache_key, result, ttl_seconds=3600)
    
    return result


def fetch_5m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    client = _get_mootdx_client()
    if client is not None:
        try:
            df = client.bars(symbol=sec.code, category=MOOTDX_CATEGORY["5m"], offset=datalen, market=_mootdx_market(sec))
            if df is not None and len(df) > 0:
                bars = []
                for _, row in df.iterrows():
                    raw_dt = str(row.get("datetime", ""))
                    parts = raw_dt.split(" ")
                    bars.append({
                        "time": raw_dt,
                        "date": parts[0] if len(parts) > 0 else "",
                        "open": to_float(row.get("open")),
                        "high": to_float(row.get("high")),
                        "low": to_float(row.get("low")),
                        "close": to_float(row.get("close")),
                        "volume": to_float(row.get("vol")),
                        "amount": to_float(row.get("amount")),
                    })
                return bars
        except Exception:
            pass
    return fetch_kline(sec, http, scale="5", datalen=datalen)


def load_market_snapshot(target: str, days: int = 30, include_5m: bool = True) -> MarketSnapshot:
    sec = resolve_security(target)
    http = HttpClient()
    source_errors: dict[str, str] = {}
    missing_sources: list[str] = []

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch_quote, sec, http): "quote",
            executor.submit(fetch_qfq_daily, sec, http, days=days): "daily",
        }
        if include_5m:
            futures[executor.submit(fetch_5m, sec, http)] = "bars_5m"

        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = None
                source_errors[key] = str(exc)
                missing_sources.append(key)

    quote = results.get("quote") or {}
    daily_bars = results.get("daily") or []
    bars_5m = results.get("bars_5m") or []
    order_book = quote.pop("order_book", None) if isinstance(quote, dict) else None
    if include_5m and not bars_5m and "bars_5m" not in missing_sources:
        missing_sources.append("bars_5m")

    if quote and daily_bars and not missing_sources:
        data_status = "full"
    elif quote and daily_bars:
        data_status = "partial"
    elif quote or daily_bars:
        data_status = "degraded"
    else:
        data_status = "failed"

    return MarketSnapshot(
        security=sec,
        quote=quote,
        daily_bars=daily_bars,
        bars_5m=bars_5m,
        order_book=order_book,
        data_status=data_status,
        missing_sources=missing_sources,
        source_errors=source_errors,
    )


def normalize_bar(raw: dict[str, Any]) -> dict[str, Any] | None:
    close = to_float(raw.get("close"))
    if close is None:
        return None
    return {
        "time": raw.get("day") or raw.get("date") or raw.get("time"),
        "date": raw.get("day") or raw.get("date") or raw.get("time"),
        "open": to_float(raw.get("open")),
        "high": to_float(raw.get("high")),
        "low": to_float(raw.get("low")),
        "close": close,
        "volume": to_float(raw.get("volume")),
        "amount": to_float(raw.get("amount")),
    }


def normalize_bars(raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for row in raw_bars:
        normalized = normalize_bar(row)
        if normalized:
            bars.append(normalized)
    return bars


def fetch_kline(sec: Security, http: HttpClient, scale: str = "5", datalen: int = 60) -> list[dict[str, Any]]:
    def do_fetch():
        params = {"symbol": sec.qq_symbol, "scale": str(scale), "ma": "no", "datalen": str(datalen)}
        payload = http.get_json(SINA_KLINE_URL, params=params)
        if not isinstance(payload, list):
            raise RuntimeError(f"Sina {scale}m payload invalid")
        raw_bars = []
        for row in payload:
            if isinstance(row, dict):
                raw_bars.append(row)
        return normalize_bars(raw_bars)

    try:
        return retry(do_fetch, url=SINA_KLINE_URL)
    except Exception as exc:
        # 分时数据是增强材料，失败时允许上层降级输出。
        print(f"Warning: Failed to fetch kline data: {exc}", file=sys.stderr)
        return []


def fetch_15m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    return fetch_kline(sec, http, scale="15", datalen=datalen)


def fetch_30m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    return fetch_kline(sec, http, scale="30", datalen=datalen)


def pct_change(start: float, end: float) -> float:
    return ((end / start) - 1.0) * 100 if start else 0.0
