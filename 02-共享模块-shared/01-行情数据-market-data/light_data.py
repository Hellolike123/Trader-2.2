from __future__ import annotations

import hashlib
import json
import math
import random
import re
import socket
import ssl
import sys
import time
import warnings
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

try:
    import akshare as _AKSHARE
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False

try:
    from pytdx3.hq import TdxHq_API
    from pytdx3.params import TDXParams
    _TDX3_AVAILABLE = True
except ImportError:
    TdxHq_API = None
    TDXParams = None
    _TDX3_AVAILABLE = False


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

# -------- Local Rate Limiter to prevent IP bans --------
import os
class APIRequestRateLimiter:
    def __init__(self, limit_file: str | None = None) -> None:
        self.limit_file = limit_file or os.path.expanduser("~/.trader/api_limits.json")
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        os.makedirs(os.path.dirname(self.limit_file), exist_ok=True)

    def _load(self) -> dict[str, list[float]]:
        if not os.path.exists(self.limit_file):
            return {"calls": []}
        try:
            with open(self.limit_file, "r") as f:
                return json.load(f)
        except Exception:
            return {"calls": []}

    def _save(self, data: dict[str, list[float]]) -> None:
        try:
            with open(self.limit_file, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def check_and_record(self, max_per_min: int = 15, max_per_hour: int = 80) -> bool:
        """Return True if allowed, False if throttled."""
        now = time.time()
        data = self._load()
        calls = [t for t in data.get("calls", []) if now - t < 3600] # 只保留一小时内
        
        min_calls = [t for t in calls if now - t < 60] # 一分钟内
        if len(min_calls) >= max_per_min:
            warnings.warn(f"⚠️ [RateLimit] 1分钟内API请求频次触发上限 ({max_per_min}次)，本地拦截并自适应降级。")
            return False
            
        if len(calls) >= max_per_hour:
            warnings.warn(f"⚠️ [RateLimit] 1小时内API请求频次触发上限 ({max_per_hour}次)，本地拦截并自适应降级。")
            return False
            
        calls.append(now)
        data["calls"] = calls
        self._save(data)
        return True

_API_RATE_LIMITER = APIRequestRateLimiter()

_TDX3_CLIENT: TdxHq_API | None = None

def _get_tdx3_client() -> TdxHq_API | None:
    global _TDX3_CLIENT
    if not _TDX3_AVAILABLE:
        return None
    if _TDX3_CLIENT is not None:
        return _TDX3_CLIENT
        
    servers = [
        ("119.147.212.81", 7709), # 深圳双线
        ("124.78.224.238", 7709), # 上海双线
        ("60.191.117.167", 7709), # 浙江电信
    ]
    
    # 动态测速并连接最快节点
    api = TdxHq_API()
    orig_timeout = socket.getdefaulttimeout()
    for ip, port in servers:
        try:
            socket.setdefaulttimeout(1.0)
            if api.connect(ip, port):
                _TDX3_CLIENT = api
                warnings.warn(f"📡 pytdx3 成功连接最快行情节点: {ip}:{port}")
                socket.setdefaulttimeout(orig_timeout)
                return _TDX3_CLIENT
        except Exception:
            continue
    socket.setdefaulttimeout(orig_timeout)
    return None


def run_tdx3_with_timeout(func, *args, **kwargs) -> Any:
    """Execute a pytdx3 API call with socket timeout and auto-reconnection on failure."""
    global _TDX3_CLIENT
    api = _get_tdx3_client()
    if api is None:
        return None
        
    orig_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(2.0)
    try:
        start_time = time.time()
        res = func(api, *args, **kwargs)
        duration = time.time() - start_time
        if duration > 2.0:
            warnings.warn(f"⚠️ pytdx3 call exceeded execution time limit of 2.0s (took {duration:.2f}s)")
            _TDX3_CLIENT = None
            return None
        return res
    except (socket.timeout, TimeoutError) as exc:
        warnings.warn(f"⚠️ pytdx3 call timed out: {exc}")
        _TDX3_CLIENT = None
        return None
    except Exception as exc:
        warnings.warn(f"⚠️ pytdx3 call failed: {exc}")
        _TDX3_CLIENT = None
        return None
    finally:
        socket.setdefaulttimeout(orig_timeout)


def _fetch_qfq_tdx3(sec: Security, days: int = 30) -> list[dict[str, Any]] | None:
    if not _TDX3_AVAILABLE:
        return None
    try:
        def call_bars(api):
            return api.get_security_bars(category=9, market=_mootdx_market(sec), code=sec.code, start=0, count=max(days, 20))
            
        raw_bars = run_tdx3_with_timeout(call_bars)
        if raw_bars is None or len(raw_bars) == 0:
            return None
            
        bars = []
        for row in raw_bars:
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
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_qfq_tdx3 error: {exc}")
        return None


def _fetch_quote_tdx3(sec: Security) -> dict[str, Any] | None:
    if not _TDX3_AVAILABLE:
        return None
    try:
        def call_quotes(api):
            return api.get_security_quotes([(_mootdx_market(sec), sec.code)])
            
        qs = run_tdx3_with_timeout(call_quotes)
        if qs is None or len(qs) == 0:
            return None
        q = dict(qs[0])
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
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_quote_tdx3 error: {exc}")
        return None


def _fetch_ticks_tdx3(sec: Security, count: int = 500) -> list[dict[str, Any]] | None:
    if not _TDX3_AVAILABLE:
        return []
    if not _API_RATE_LIMITER.check_and_record(max_per_min=15, max_per_hour=80):
        return []

    market = _mootdx_market(sec)
    
    def call_today_ticks(api):
        return api.get_transaction_data(market, sec.code, 0, count)
        
    ticks = run_tdx3_with_timeout(call_today_ticks)
    
    if not ticks:
        bars = _fetch_qfq_tdx3(sec, days=1)
        if bars:
            last_date = bars[-1].get("date", "")
            if last_date:
                try:
                    date_int = int(last_date.replace("-", ""))
                    
                    def call_history_ticks(api):
                        return api.get_history_transaction_data(market, sec.code, 0, count, date_int)
                        
                    ticks = run_tdx3_with_timeout(call_history_ticks)
                    if ticks:
                        warnings.warn(f"📡 [TickSelfCalibration] 盘中当日Tick为空，自适应激活周末/盘后历史Tick自愈，成功调取 {last_date} 明细数据。")
                except Exception:
                    pass

    if not ticks:
        return []

    norm_ticks = []
    for tick in ticks:
        bos_raw = tick.get("buyorsell")
        if bos_raw == 1:
            side = "buy"
        elif bos_raw == 0:
            side = "sell"
        elif bos_raw == 2:
            side = "neutral"
        else:
            side = "neutral"
            
        norm_ticks.append({
            "time": str(tick.get("time", "")),
            "price": to_float(tick.get("price")),
            "vol": to_float(tick.get("vol")),
            "buyorsell": side,
        })
    return norm_ticks

DataStatus = Literal["full", "partial", "degraded", "failed"]

_MOOTDX_CLIENT: Quotes | None = None


class MarketDataSourceController:
    """Manages the connection state and health of the mootdx quotes client.

    Tracks consecutive failures, enforces cooldown isolation on repeated failures,
    and maintains healthy/unhealthy state flags.
    """
    def __init__(self, max_failures: int = 3, cooldown_seconds: float = 30.0) -> None:
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.cool_down_until = 0.0
        self.healthy = True
        
        self.total_calls = 0
        self.total_failures = 0

    def is_healthy(self) -> bool:
        """Check if mootdx client is healthy or if cooldown has expired."""
        if not self.healthy:
            if time.time() >= self.cool_down_until:
                # Cooldown expired, tentatively treat as healthy
                self.healthy = True
                self.consecutive_failures = 0
                return True
            return False
        return True

    def report_success(self) -> None:
        """Report a successful client call, resetting consecutive failure counts."""
        self.total_calls += 1
        self.consecutive_failures = 0
        self.healthy = True

    def report_failure(self) -> None:
        """Report a failed client call. Triggers cooldown isolation if failures persist."""
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        if self.consecutive_failures >= self.max_failures:
            self.healthy = False
            self.cool_down_until = time.time() + self.cooldown_seconds
            warnings.warn(
                f"⚠️ mootdx client marked as UNHEALTHY due to {self.consecutive_failures} "
                f"consecutive failures. Isolated for {self.cooldown_seconds} seconds."
            )


_DATA_SOURCE_CONTROLLER = MarketDataSourceController()


def run_mootdx_with_timeout(func, *args, **kwargs) -> Any:
    """Execute a mootdx connection or call with a strict 1.5-second socket timeout."""
    global _MOOTDX_CLIENT
    if not _DATA_SOURCE_CONTROLLER.is_healthy():
        return None

    orig_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(1.5)
    try:
        start_time = time.time()
        res = func(*args, **kwargs)
        duration = time.time() - start_time
        if duration > 1.5:
            # Enforce strict 1.5s execution limit even if socket doesn't raise timeout
            _MOOTDX_CLIENT = None
            _DATA_SOURCE_CONTROLLER.report_failure()
            warnings.warn(f"⚠️ mootdx call exceeded execution time limit of 1.5s (took {duration:.2f}s)")
            return None
        _DATA_SOURCE_CONTROLLER.report_success()
        return res
    except (socket.timeout, TimeoutError) as exc:
        _MOOTDX_CLIENT = None
        _DATA_SOURCE_CONTROLLER.report_failure()
        warnings.warn(f"⚠️ mootdx call timed out: {exc}")
        return None
    except Exception as exc:
        _MOOTDX_CLIENT = None
        _DATA_SOURCE_CONTROLLER.report_failure()
        warnings.warn(f"⚠️ mootdx call failed with exception: {exc}")
        return None
    finally:
        socket.setdefaulttimeout(orig_timeout)


def _get_mootdx_client() -> Quotes | None:
    global _MOOTDX_CLIENT
    if _MOOTDX_CLIENT is not None:
        return _MOOTDX_CLIENT
    if not _MOOTDX_AVAILABLE:
        return None
    if not _DATA_SOURCE_CONTROLLER.is_healthy():
        return None
        
    def init_client():
        return Quotes.factory(market='std')
        
    client = run_mootdx_with_timeout(init_client)
    if client is not None:
        _MOOTDX_CLIENT = client
        return _MOOTDX_CLIENT
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
        def call_bars():
            return client.bars(symbol=sec.code, category=MOOTDX_CATEGORY["daily"], offset=max(days, 20), market=_mootdx_market(sec))
            
        df = run_mootdx_with_timeout(call_bars)
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
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_qfq_mootdx error processing DataFrame: {exc}")
        return None


def _fetch_quote_mootdx(sec: Security) -> dict[str, Any] | None:
    client = _get_mootdx_client()
    if client is None:
        return None
    try:
        def call_quotes():
            return client.quotes(symbol=[sec.code], market=_mootdx_market(sec))
            
        qs = run_mootdx_with_timeout(call_quotes)
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
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_quote_mootdx error processing DataFrame: {exc}")
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
    tick_data: list[dict[str, Any]] = field(default_factory=list)
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


def _prune_cache() -> None:
    now = time.time()
    expired_keys = [k for k, exp in _cache_expiry.items() if now >= exp]
    for k in expired_keys:
        _cache.pop(k, None)
        _cache_expiry.pop(k, None)
    expired_rt = [k for k, (_, ts) in _realtime_cache.items() if now >= ts + _REALTIME_TTL]
    for k in expired_rt:
        _realtime_cache.pop(k, None)


def get_from_cache(key: str) -> Any:
    _prune_cache()
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


def sanitize_quote(q: dict[str, Any] | None) -> dict[str, Any] | None:
    if q is None:
        return None
    curr = q.get("current_price") or q.get("close")
    if curr is None:
        return q
    try:
        current = float(curr)
        if current > 0:
            # 价格偏离防线：若今日低点/高点偏离当前现价超过 20%，截断并降级自愈为当前现价本身
            low_val = q.get("low")
            if low_val is not None:
                fl = float(low_val)
                if fl < current * 0.80 or fl > current * 1.20:
                    q["low"] = current
            high_val = q.get("high")
            if high_val is not None:
                fh = float(high_val)
                if fh < current * 0.80 or fh > current * 1.20:
                    q["high"] = current
    except (TypeError, ValueError):
        pass
    return q


def fetch_quote(sec: Security, http: HttpClient) -> QuoteData:
    cache_key = f"quote:{sec.qq_symbol}"
    cached = get_realtime_cache(cache_key)
    if cached is not None:
        return sanitize_quote(cached)

    # Tencent HTTP first — fast and stable for most cases
    try:
        text = http.get_text(TENCENT_QUOTE_URL + sec.qq_symbol, encoding="gbk")
        match = re.search(r'="([^"]*)"', text)
        if match and len(match.group(1).split("~")) >= 35:
            trade_date, trade_time = parse_trade_datetime(match.group(1).split("~"))
            fields = match.group(1).split("~")
            tencent_q = {
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
                "data_source": "tencent-http",
                "data_status": "full",
            }
            save_realtime_cache(cache_key, tencent_q)
            return sanitize_quote(tencent_q)
    except Exception:
        pass

    # Fallback: pytdx3 (fast timeout, mainly a backup)
    if _TDX3_AVAILABLE:
        tdx3_q = _fetch_quote_tdx3(sec)
        if tdx3_q is not None:
            tdx3_q["data_source"] = "pytdx3"
            tdx3_q["data_status"] = "full"
            save_realtime_cache(cache_key, tdx3_q)
            return sanitize_quote(tdx3_q)

    # Fallback: mootdx
    mootdx_q = _fetch_quote_mootdx(sec)
    if mootdx_q is not None:
        try:
            text = http.get_text(TENCENT_QUOTE_URL + sec.qq_symbol, encoding="gbk")
            match = re.search(r'="([^"]*)"', text)
            if match:
                fields = match.group(1).split("~")
                if len(fields) > 38:
                    mootdx_q["turnover_rate"] = to_float(fields[38])
                if len(fields) > 34:
                    if mootdx_q.get("high") is None:
                        mootdx_q["high"] = to_float(fields[33])
                    if mootdx_q.get("low") is None:
                        mootdx_q["low"] = to_float(fields[34])
        except Exception:
            pass
        mootdx_q["data_source"] = "mootdx"
        mootdx_q["data_status"] = "full"
        save_realtime_cache(cache_key, mootdx_q)
        return sanitize_quote(mootdx_q)

    def do_fetch():
        text = http.get_text(TENCENT_QUOTE_URL + sec.qq_symbol, encoding="gbk")
        match = re.search(r'="([^"]*)"', text)
        if not match:
            raise RuntimeError("Tencent quote payload missing fields")
        fields = match.group(1).split("~")
        if len(fields) < 35:
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
            "data_source": "tencent (fallback)",
            "data_status": "partial",
        }
        save_realtime_cache(cache_key, result)
        return result

    return sanitize_quote(retry(do_fetch, url=TENCENT_QUOTE_URL))


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
    # Tencent HTTP first — fast and stable
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
                bars.append({
                    "date": row[0],
                    "open": to_float(row[1]),
                    "close": to_float(row[2]),
                    "high": to_float(row[3]),
                    "low": to_float(row[4]),
                    "volume": to_float(row[5]),
                    "data_source": "tencent-http",
                    "data_status": "full",
                })
        if not bars:
            day_rows = sec_data.get("day") or []
            for row in day_rows:
                if isinstance(row, list) and len(row) >= 6:
                    bars.append({
                        "date": row[0],
                        "open": to_float(row[1]),
                        "close": to_float(row[2]),
                        "high": to_float(row[3]),
                        "low": to_float(row[4]),
                        "volume": to_float(row[5]),
                        "data_source": "tencent-http",
                        "data_status": "full",
                    })
        if not bars:
            raise RuntimeError("Tencent qfq daily bars unavailable")
        return bars

    try:
        result = retry(do_fetch)
        _compute_atr_fields(result)
        has_today = any(bar.get("date") == datetime.now().strftime("%Y-%m-%d") for bar in result)
        if not has_today:
            save_to_cache(cache_key, result, ttl_seconds=3600)
        return result
    except RuntimeError:
        pass

    # Fallback: pytdx3
    if _TDX3_AVAILABLE:
        tdx3_bars = _fetch_qfq_tdx3(sec, days)
        if tdx3_bars is not None:
            for bar in tdx3_bars:
                bar["data_source"] = "pytdx3"
                bar["data_status"] = "full"
            _compute_atr_fields(tdx3_bars)
            return tdx3_bars

    # Fallback: mootdx
    mootdx_bars = _fetch_qfq_mootdx(sec, days)
    if mootdx_bars is not None:
        for bar in mootdx_bars:
            bar["data_source"] = "mootdx"
            bar["data_status"] = "full"
        _compute_atr_fields(mootdx_bars)
        return mootdx_bars

    # 全源失败，返回空列表（避免下游 bars[-1] 炸 TypeError）
    return []


def _fetch_mins_mootdx(sec: Security, interval: str, datalen: int = 60) -> list[dict[str, Any]] | None:
    client = _get_mootdx_client()
    if client is None:
        return None
    category_map = {"5m": "5m", "15m": "15m", "30m": "30m", "60m": "60m"}
    cat = category_map.get(interval)
    if cat is None:
        return None
    cat_num = MOOTDX_CATEGORY.get(cat)
    if cat_num is None:
        return None
    try:
        def call_bars():
            return client.bars(symbol=sec.code, category=cat_num, offset=datalen, market=_mootdx_market(sec))
            
        df = run_mootdx_with_timeout(call_bars)
        if df is None or len(df) == 0:
            return None
        bars: list[dict[str, Any]] = []
        for _, row in df.tail(datalen).iterrows():
            raw_dt = str(row.get("datetime", ""))
            bars.append({
                "time": raw_dt,
                "date": raw_dt[:10],
                "open": to_float(row.get("open")),
                "close": to_float(row.get("close")),
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "volume": to_float(row.get("vol")),
                "amount": to_float(row.get("amount")),
            })
        return bars
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_mins_mootdx error processing DataFrame: {exc}")
        return None


def fetch_5m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    # Prioritize robust Sina HTTP API to ensure complete 5m data without weekend truncation
    fallback_bars = _fetch_mins_fallback(sec, "5m", datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        return fallback_bars
    
    warnings.warn(f"⚠️ Sina HTTP fetch_5m failed or incomplete. Falling back to Mootdx Quote client.")
    bars = _fetch_mins_mootdx(sec, "5m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        return bars
    return []


def fetch_15m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, "15m", datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        return fallback_bars
    
    warnings.warn(f"⚠️ Sina HTTP fetch_15m failed or incomplete. Falling back to Mootdx Quote client.")
    bars = _fetch_mins_mootdx(sec, "15m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        return bars
    return []


def fetch_30m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, "30m", datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        return fallback_bars
    
    warnings.warn(f"⚠️ Sina HTTP fetch_30m failed or incomplete. Falling back to Mootdx Quote client.")
    bars = _fetch_mins_mootdx(sec, "30m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        return bars
    return []


def fetch_kline(sec: Security, http: HttpClient, datalen: int = 60, interval: str = "60") -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, interval, datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        return fallback_bars
    
    warnings.warn(f"⚠️ Sina HTTP fetch_kline (interval {interval}) failed or incomplete. Falling back to Mootdx Quote client.")
    bars = _fetch_mins_mootdx(sec, interval, datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        return bars
    return []


def _fetch_mins_fallback(sec: Security, interval: str, datalen: int) -> list[dict[str, Any]]:
    """Try Sina HTTP API first to avoid AkShare proxy/TLS disconnections, then fallback to AkShare.
    
    Sina HTTP (CN_MarketData.getKLineData) is highly reliable, robust, and performs well
    without third-party packages or proxy interference.
    """
    try:
        period_map = {"5m": "5", "15m": "15", "30m": "30", "60m": "60", "60": "60"}
        scale = period_map.get(interval, "5")
        
        import ssl
        from urllib.request import Request, urlopen
        import json
        
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sec.qq_symbol}&scale={scale}&ma=no&datalen={datalen}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://finance.sina.com.cn/",
        }
        ssl_ctx = ssl._create_unverified_context()
        request = Request(url, headers=headers)
        
        with urlopen(request, timeout=5, context=ssl_ctx) as response:
            text = response.read().decode("gbk", errors="ignore")
            raw_data = json.loads(text or "[]")
            
        if raw_data and isinstance(raw_data, list) and not isinstance(raw_data, dict):
            bars: list[dict[str, Any]] = []
            for row in raw_data:
                dt_str = str(row.get("day", ""))
                bars.append({
                    "time": dt_str,
                    "date": dt_str.split(" ")[0] if dt_str else "",
                    "open": to_float(row.get("open")),
                    "high": to_float(row.get("high")),
                    "low": to_float(row.get("low")),
                    "close": to_float(row.get("close")),
                    "volume": to_float(row.get("volume")),
                    "amount": None,
                })
            return bars
    except Exception as e:
        warnings.warn(f"⚠️ Sina HTTP fallback failed: {e}. Trying akshare as last resort.")

    try:
        import akshare as ak
    except ImportError:
        return None
    try:
        period_map = {"5m": "5", "15m": "15", "30m": "30", "60": "60"}
        period = period_map.get(interval, "60")
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period=period, adjust="qfq")
        if df is None or df.empty:
            return None
        bars: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            dt_val = str(row_dict.get("时间") or row_dict.get("time") or row_dict.get("datetime") or "")
            close = to_float(row_dict.get("收盘") or row_dict.get("close"))
            if close is None:
                continue
            bars.append({
                "time": dt_val,
                "date": dt_val.split(" ")[0] if " " in dt_val else dt_val,
                "open": to_float(row_dict.get("开盘") or row_dict.get("open")),
                "high": to_float(row_dict.get("最高") or row_dict.get("high")),
                "low": to_float(row_dict.get("最低") or row_dict.get("low")),
                "close": close,
                "volume": to_float(row_dict.get("成交量") or row_dict.get("volume") or row_dict.get("vol")),
                "amount": to_float(row_dict.get("成交额") or row_dict.get("amount")),
            })
        return bars[-datalen:] if len(bars) > datalen else bars
    except Exception:
        return None


def load_market_snapshot(target: str, days: int = 30, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
    sec = resolve_security(target)
    http = HttpClient()
    source_errors: dict[str, str] = {}
    missing_sources: list[str] = []

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_quote, sec, http): "quote",
            executor.submit(fetch_qfq_daily, sec, http, days=days): "daily",
        }
        if include_5m:
            futures[executor.submit(fetch_5m, sec, http)] = "bars_5m"
        if include_ticks:
            futures[executor.submit(_fetch_ticks_tdx3, sec, 500)] = "tick_data"

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
    tick_data = results.get("tick_data") or []
    order_book = quote.get("order_book")
    if isinstance(quote, dict):
        quote = dict(quote)  # shallow copy to avoid mutating the cache
        if "order_book" in quote:
            del quote["order_book"]
    if include_5m and not bars_5m and "bars_5m" not in missing_sources:
        missing_sources.append("bars_5m")

    if quote and daily_bars and not missing_sources:
        # Check if fallback occurred
        if (isinstance(quote, dict) and quote.get("data_status") == "partial") or \
           (isinstance(daily_bars, list) and any(b.get("data_status") == "partial" for b in daily_bars)) or \
           (isinstance(bars_5m, list) and any(b.get("data_status") == "partial" for b in bars_5m)):
            data_status = "partial"
        else:
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
        tick_data=tick_data,
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


def pct_change(start: float, end: float) -> float:
    return ((end / start) - 1.0) * 100 if start else 0.0
