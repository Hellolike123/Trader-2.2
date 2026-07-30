from __future__ import annotations

import hashlib
import json
import math
import random
import re
import socket
import ssl
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trader_shared._logging import get_logger
from trader_shared.cache_utils import get_shared_build_pool
from trader_shared.market_types import DataStatus, MarketSnapshot, Security

_logger = get_logger(__name__)

try:
    from trader_shared.models import BarData, QuoteData
except ImportError:
    BarData = dict
    QuoteData = dict

# 懒加载重量级 fallback 依赖，避免 import 时浪费 ~0.8s
Quotes = None
_MOOTDX_AVAILABLE = None  # None = 未检测, True/False = 已检测
_AKSHARE = None
_AKSHARE_AVAILABLE = None
TdxHq_API = None
TDXParams = None
_TDX3_AVAILABLE = None


def _check_mootdx() -> bool:
    global Quotes, _MOOTDX_AVAILABLE
    if _MOOTDX_AVAILABLE is not None:
        return _MOOTDX_AVAILABLE
    try:
        from mootdx.quotes import Quotes
        _MOOTDX_AVAILABLE = True
    except ImportError:
        Quotes = None
        _MOOTDX_AVAILABLE = False
    return _MOOTDX_AVAILABLE


def _check_akshare() -> bool:
    global _AKSHARE, _AKSHARE_AVAILABLE
    if _AKSHARE_AVAILABLE is not None:
        return _AKSHARE_AVAILABLE
    try:
        import akshare as _ak
        _AKSHARE = _ak
        _AKSHARE_AVAILABLE = True
    except ImportError:
        _AKSHARE_AVAILABLE = False
    return _AKSHARE_AVAILABLE


def _check_pytdx3() -> bool:
    global TdxHq_API, TDXParams, _TDX3_AVAILABLE
    if _TDX3_AVAILABLE is not None:
        return _TDX3_AVAILABLE
    try:
        from pytdx3.hq import TdxHq_API as _Tdx
        from pytdx3.params import TDXParams as _TDXP
        TdxHq_API = _Tdx
        TDXParams = _TDXP
        _TDX3_AVAILABLE = True
    except ImportError:
        _TDX3_AVAILABLE = False
    return _TDX3_AVAILABLE


TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
TIMEOUT_SECONDS = 5
MAX_ATTEMPTS = 2
NAME_MAP = {
    "南网科技": "688248",
    "三花智控": "002050",
    "中国铝业": "601600",
    "三安光电": "600703",
    "贵州茅台": "600519",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "东方财富": "300059",
    "招商银行": "600036",
    "中国平安": "601318",
    "中证1000": "000852",
    "华工科技": "000988",
}

# 运行时名称→代码缓存（避免重复搜索）
_NAME_SEARCH_CACHE: dict[str, str] = {}
_name_search_lock = threading.Lock()


def _search_code_by_name(name: str) -> str | None:
    """通过新浪 suggest 接口，用股票名称查 6 位代码。

    返回代码字符串（如 '603459'），找不到返回 None。
    使用运行时内存缓存，同一进程内不重复请求。
    """
    with _name_search_lock:
        if name in _NAME_SEARCH_CACHE:
            return _NAME_SEARCH_CACHE[name]

    try:
        from urllib.parse import quote as _quote
        # 新浪联想词搜索接口（支持 A 股 type=11/12）
        # 新浪联想接口主机名为 sinajs.cn（非 sinus/sinais 拼写）
        url = f"http://suggest3.sinajs.cn/suggest/type=11,12&key={_quote(name)}"
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://finance.sina.com.cn/",
            },
        )
        with urlopen(req, timeout=3.0) as resp:
            raw = resp.read().decode("gbk", errors="ignore")

        # 响应格式: var suggestvalue="红板科技,11,603459,sh603459,红板科技,,红板科技,99,1,,,";
        # 多条结果用 ";" 分隔
        m = re.search(r'suggestvalue="([^"]*)"', raw)
        if not m:
            return None

        entries = m.group(1).split(";")
        for entry in entries:
            parts = entry.split(",")
            if len(parts) < 3:
                continue
            found_name = parts[0].strip()
            code_raw = parts[2].strip()  # 纯数字代码，如 603459
            if not code_raw.isdigit() or len(code_raw) != 6:
                continue
            # 精确名称匹配优先
            if found_name == name:
                with _name_search_lock:
                    _NAME_SEARCH_CACHE[name] = code_raw
                return code_raw

        # 无精确匹配时取第一条有效结果
        for entry in entries:
            parts = entry.split(",")
            if len(parts) < 3:
                continue
            code_raw = parts[2].strip()
            if code_raw.isdigit() and len(code_raw) == 6:
                with _name_search_lock:
                    _NAME_SEARCH_CACHE[name] = code_raw
                return code_raw

    except Exception as exc:
        _logger.debug("股票名称搜索失败 name=%s: %s", name, exc)

    return None

# 缓存：只用于历史数据（昨日及更早的日线）
_cache: dict[str, Any] = {}
_cache_expiry: dict[str, float] = {}

# 实时行情缓存（30秒TTL）
_realtime_cache: dict[str, tuple[Any, float]] = {}
_REALTIME_TTL = 30

# -------- Local Rate Limiter to prevent IP bans --------
import os
import atexit
class APIRequestRateLimiter:
    def __init__(self, limit_file: str | None = None) -> None:
        self.limit_file = limit_file or os.path.expanduser("~/.trader/api_limits.json")
        self._ensure_dir()
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._dirty = False

    def _ensure_dir(self) -> None:
        os.makedirs(os.path.dirname(self.limit_file), exist_ok=True)

    def _load_from_disk(self) -> dict[str, list[float]]:
        if not os.path.exists(self.limit_file):
            return {"calls": []}
        try:
            with open(self.limit_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            _logger.debug("Rate limiter load failed: %s", exc)
            return {"calls": []}

    def _save(self, data: dict[str, list[float]]) -> None:
        try:
            with open(self.limit_file, "w") as f:
                json.dump(data, f)
        except OSError as exc:
            _logger.debug("Rate limiter save failed: %s", exc)

    def _get_data(self) -> dict:
        with self._lock:
            if self._cache is None:
                self._cache = self._load_from_disk()
            return self._cache

    def _flush(self) -> None:
        with self._lock:
            if self._dirty and self._cache is not None:
                self._save(self._cache)
                self._dirty = False

    def check_and_record(self, max_per_min: int = 15, max_per_hour: int = 80) -> bool:
        """Return True if allowed, False if throttled. (线程安全)"""
        with self._lock:
            if self._cache is None:
                self._cache = self._load_from_disk()
            now = time.time()
            data = self._cache
            calls = [t for t in data.get("calls", []) if now - t < 3600]

            min_calls = [t for t in calls if now - t < 60]
            if len(min_calls) >= max_per_min:
                warnings.warn(f"⚠️ [RateLimit] 1分钟内API请求频次触发上限 ({max_per_min}次)，本地拦截并自适应降级。")
                return False

            if len(calls) >= max_per_hour:
                warnings.warn(f"⚠️ [RateLimit] 1小时内API请求频次触发上限 ({max_per_hour}次)，本地拦截并自适应降级。")
                return False

            calls.append(now)
            data["calls"] = calls
            self._dirty = True
            return True

_API_RATE_LIMITER = APIRequestRateLimiter()
atexit.register(_API_RATE_LIMITER._flush)

# Minimum delay between consecutive API calls (seconds)
_API_CALL_DELAY = 0.1
_last_api_call_time: float = 0.0
_api_call_lock = threading.Lock()


def _rate_limit_delay() -> None:
    """Enforce minimum delay between consecutive API calls."""
    global _last_api_call_time
    with _api_call_lock:
        now = time.time()
        elapsed = now - _last_api_call_time
        if elapsed < _API_CALL_DELAY:
            time.sleep(_API_CALL_DELAY - elapsed)
        _last_api_call_time = time.time()

_TDX3_CLIENT: TdxHq_API | None = None

def _get_tdx3_client() -> TdxHq_API | None:
    global _TDX3_CLIENT
    if not _check_pytdx3():
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


_TDX3_HARD_TIMEOUT_S = 2.0


def _run_with_hard_timeout(func, timeout_s: float, *args, **kwargs) -> Any:
    """Run ``func`` in a daemon thread; raise ``TimeoutError`` if over ``timeout_s``.

    Daemon threads will not block process exit if abandoned after timeout.
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def _call() -> None:
        try:
            box["result"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — surface to caller thread
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_call, name="hard-timeout-worker", daemon=True).start()
    if not done.wait(timeout=timeout_s):
        raise TimeoutError(f"hard-timeout after {timeout_s:.1f}s")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def run_tdx3_with_timeout(func, *args, **kwargs) -> Any:
    """Execute a pytdx3 API call with a hard wall-clock timeout (default 2.0s).

    socket.setdefaulttimeout alone cannot abort hung pytdx reads; we run the
    call in a worker and abandon it after the deadline so callers can fallback.
    """
    global _TDX3_CLIENT
    api = _get_tdx3_client()
    if api is None:
        return None

    def _call():
        orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(_TDX3_HARD_TIMEOUT_S)
        try:
            return func(api, *args, **kwargs)
        finally:
            socket.setdefaulttimeout(orig_timeout)

    try:
        return _run_with_hard_timeout(_call, _TDX3_HARD_TIMEOUT_S)
    except TimeoutError:
        _TDX3_CLIENT = None
        warnings.warn(
            f"⚠️ pytdx3 call hard-timeout after {_TDX3_HARD_TIMEOUT_S:.1f}s; abandoning worker"
        )
        return None
    except (socket.timeout,) as exc:
        warnings.warn(f"⚠️ pytdx3 call timed out: {exc}")
        _TDX3_CLIENT = None
        return None
    except Exception as exc:
        warnings.warn(f"⚠️ pytdx3 call failed: {exc}")
        _TDX3_CLIENT = None
        return None


def _fetch_qfq_tdx3(sec: Security, days: int = 300) -> list[dict[str, Any]] | None:
    if not _check_pytdx3():
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
    if not _check_pytdx3():
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
            "current_change_pct": round(((price_v or 0) / (last_close_v if last_close_v and last_close_v > 0 else 1) - 1) * 100, 2) if price_v and last_close_v else None,
            "order_book": _extract_order_book(q),
        }
        return result
    except Exception as exc:
        warnings.warn(f"⚠️ _fetch_quote_tdx3 error: {exc}")
        return None


def _fetch_ticks_tdx3(sec: Security, count: int = 500) -> list[dict[str, Any]] | None:
    if not _check_pytdx3():
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

_MOOTDX_CLIENT: Quotes | None = None


class MarketDataSourceController:
    """Manages the connection state and health of the mootdx quotes client.

    Tracks consecutive failures, enforces cooldown isolation on repeated failures,
    and maintains healthy/unhealthy state flags. (线程安全)
    """
    def __init__(self, max_failures: int = 3, cooldown_seconds: float = 30.0) -> None:
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.cool_down_until = 0.0
        self.healthy = True
        
        self.total_calls = 0
        self.total_failures = 0

    def is_healthy(self) -> bool:
        """Check if mootdx client is healthy or if cooldown has expired."""
        with self._lock:
            if not self.healthy:
                if time.time() >= self.cool_down_until:
                    self.healthy = True
                    self.consecutive_failures = 0
                    return True
                return False
            return True

    def report_success(self) -> None:
        """Report a successful client call, resetting consecutive failure counts."""
        with self._lock:
            self.total_calls += 1
            self.consecutive_failures = 0
            self.healthy = True

    def report_failure(self) -> None:
        """Report a failed client call. Triggers cooldown isolation if failures persist."""
        with self._lock:
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

    def report_hard_timeout(self) -> None:
        """Hard wall-clock timeout: isolate immediately so callers fallback in seconds."""
        with self._lock:
            self.total_calls += 1
            self.total_failures += 1
            self.consecutive_failures = self.max_failures
            self.last_failure_time = time.time()
            self.healthy = False
            self.cool_down_until = time.time() + self.cooldown_seconds
            warnings.warn(
                f"⚠️ mootdx client marked as UNHEALTHY after hard timeout. "
                f"Isolated for {self.cooldown_seconds} seconds."
            )


_DATA_SOURCE_CONTROLLER = MarketDataSourceController()

# Wall-clock hard timeout for mootdx. socket.setdefaulttimeout alone does NOT
# abort hung pytdx/mootdx reads (observed ~38s despite "1.5s limit").
_MOOTDX_HARD_TIMEOUT_S = 1.5


class _CircuitBreaker:
    """Circuit breaker for API calls.

    After `threshold` consecutive failures, pauses requests for `cooldown_seconds`.
    During pause, calls return None (caller should fallback).
    Successful request resets failure counter.
    """

    def __init__(self, threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures: int = 0
        self._paused_until: float = 0.0

    @property
    def is_open(self) -> bool:
        """True if circuit is open (requests should be paused)."""
        if self._paused_until > 0 and time.time() < self._paused_until:
            return True
        if self._paused_until > 0 and time.time() >= self._paused_until:
            # Cooldown expired, half-open state — allow one attempt
            self._paused_until = 0.0
        return False

    def record_success(self) -> None:
        """Reset failure counter on success."""
        self._consecutive_failures = 0
        self._paused_until = 0.0

    def record_failure(self) -> None:
        """Record a failure. Opens circuit after threshold consecutive failures."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.threshold:
            self._paused_until = time.time() + self.cooldown_seconds
            _logger.warning(
                "Circuit breaker OPEN after %d consecutive failures. Pausing for %.0fs",
                self._consecutive_failures, self.cooldown_seconds,
            )


_circuit_tencent_quote = _CircuitBreaker(threshold=5, cooldown_seconds=60.0)
_circuit_tencent_daily = _CircuitBreaker(threshold=5, cooldown_seconds=60.0)


def run_mootdx_with_timeout(func, *args, **kwargs) -> Any:
    """Execute a mootdx call with a hard wall-clock timeout (default 1.5s).

    Runs the call in a daemon worker so a hung TCP read cannot block the caller
    for tens of seconds. On hard timeout the client is discarded and the source
    controller isolates immediately for cooldown.
    """
    global _MOOTDX_CLIENT
    if not _DATA_SOURCE_CONTROLLER.is_healthy():
        return None

    def _call():
        orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(_MOOTDX_HARD_TIMEOUT_S)
        try:
            return func(*args, **kwargs)
        finally:
            socket.setdefaulttimeout(orig_timeout)

    try:
        res = _run_with_hard_timeout(_call, _MOOTDX_HARD_TIMEOUT_S)
    except TimeoutError:
        _MOOTDX_CLIENT = None
        _DATA_SOURCE_CONTROLLER.report_hard_timeout()
        warnings.warn(
            f"⚠️ mootdx call hard-timeout after {_MOOTDX_HARD_TIMEOUT_S:.1f}s; "
            "abandoning worker and falling back"
        )
        return None
    except (socket.timeout,) as exc:
        _MOOTDX_CLIENT = None
        _DATA_SOURCE_CONTROLLER.report_failure()
        warnings.warn(f"⚠️ mootdx call timed out: {exc}")
        return None
    except Exception as exc:
        _MOOTDX_CLIENT = None
        _DATA_SOURCE_CONTROLLER.report_failure()
        warnings.warn(f"⚠️ mootdx call failed with exception: {exc}")
        return None

    _DATA_SOURCE_CONTROLLER.report_success()
    return res


def _get_mootdx_client() -> Quotes | None:
    global _MOOTDX_CLIENT
    if _MOOTDX_CLIENT is not None:
        return _MOOTDX_CLIENT
    if not _check_mootdx():
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


def _fetch_qfq_mootdx(sec: Security, days: int = 300) -> list[dict[str, Any]] | None:
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
            "current_change_pct": round(((price_v or 0) / (last_close_v if last_close_v and last_close_v > 0 else 1) - 1) * 100, 2) if price_v and last_close_v else None,
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


# MarketSnapshot → market_types


def is_trading_time() -> bool:
    """判断当前是否是交易时间（9:25-15:00，周末/节假日返回False）"""
    try:
        from trader_shared.trading_context import is_trading_time as _itt
        return _itt()
    except ImportError:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        current_time = now.hour * 100 + now.minute
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


# Security → market_types


class HttpClient:
    """HTTP 客户端，带连接池和指数退避重试。"""

    def __init__(self) -> None:
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://finance.sina.com.cn/",
        }
        self.ssl_context = ssl.create_default_context()

    def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 2,
        backoffs: tuple = (0.2, 0.5),
    ) -> bytes:
        """获取 URL 字节内容，带指数退避重试。

        仅对网络类异常重试（TimeoutError, socket.timeout, OSError 但非 HTTPError）。
        HTTP 4xx/5xx 错误不重试，直接抛出。
        """
        from urllib.error import HTTPError
        full_url = f"{url}?{urlencode(params)}" if params else url
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                request = Request(full_url, headers=self.headers)
                with urlopen(request, timeout=TIMEOUT_SECONDS, context=self.ssl_context) as response:
                    return response.read()
            except HTTPError:
                raise  # HTTP 错误码不重试，直接失败
            except (TimeoutError, socket.timeout, OSError) as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(backoffs[attempt])
                else:
                    raise
        raise last_error  # type: ignore[misc]

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        encoding: str = "utf-8",
        max_retries: int = 2,
    ) -> str:
        """获取 URL 文本内容，带指数退避重试。"""
        return self.get_bytes(url, params=params, max_retries=max_retries).decode(encoding, errors="ignore")

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
    """兼容入口；实现见 ``trader_shared.safe_cast.to_float``。"""
    from trader_shared.safe_cast import to_float as _to_float

    return _to_float(value)


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
            # 纯名称输入：先用腾讯搜索接口尝试查代码
            found_code = _search_code_by_name(raw)
            if found_code:
                digits = found_code
                _logger.debug("股票名称 '%s' 解析为代码 %s（在线搜索）", raw, found_code)
            else:
                raise RuntimeError(
                    f"无法解析股票名称：{raw}，请改用 6 位代码"
                    f"（提示：可先手动将 '{raw}' 添加到 NAME_MAP）"
                )
        code = digits
    code = code[-6:].zfill(6)
    if not market:
        market = infer_a_share_market(code)
    # 名称：已知 NAME_MAP > 在线搜索成功 > 回退到代码
    display_name = raw if (raw in NAME_MAP or not re.sub(r"\D", "", raw)) else code
    return Security(code=code, market=market, name=display_name)


def infer_a_share_market(code: str) -> str:
    """由 6 位代码推断交易所，与 signal_utils.normalize_symbol 对齐。

    SH: 6xxxxx 主板/科创, 5xxxxx 沪 ETF/基金, 9xxxxx 沪 B
    SZ: 0/1/2/3 开头（含深 ETF 15/16/18 等）
    BJ: 4/8 开头北交所
    """
    c = str(code or "").strip().zfill(6)[-6:]
    if c.startswith(("8", "4")):
        return "BJ"
    if c.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def extract_jsonp(text: str) -> Any:
    raw = text.strip()
    if "=" in raw:
        raw = raw.split("=", 1)[1].strip()
    return json.loads(raw.rstrip(";"))


def parse_trade_datetime(fields: list[str]) -> tuple[str, str | None]:
    """Parse trade date/time from Tencent quote fields.

    Tencent stores a 14-digit timestamp at fields[30]: "20260529161443".
    Fallback: scan for 8-digit date or HH:MM:SS patterns.
    """
    trade_date = None
    trade_time = None

    # 优先从 fields[30] 提取 14 位时间戳
    if len(fields) > 30:
        ts = str(fields[30]).strip()
        if len(ts) >= 8 and ts[:8].isdigit():
            trade_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if len(ts) >= 14 and ts[8:14].isdigit():
                trade_time = f"{ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
            return trade_date, trade_time

    # Fallback: 从后往前扫描
    for item in reversed(fields):
        text = str(item).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            trade_date = text
        elif re.fullmatch(r"\d{2}:\d{2}:\d{2}", text):
            trade_time = text
    return trade_date, trade_time


def _hl_is_data_glitch(val: float, current: float, pre_close: float | None) -> bool:
    """仅拦截明显脏高低价；真实涨跌停日（约 ±10%/±20%）不得误杀。"""
    if val <= 0 or current <= 0:
        return True
    ref = pre_close if pre_close and pre_close > 0 else current
    # 绝对溢出（通达信/脏字段常见百万级）
    if val > max(ref * 5.0, current * 5.0) or val > 100_000:
        return True
    # 相对现价离谱（>3 倍或 <1/3）才改；20% 宽幅日保留
    if val > current * 3.0 or val < current * (1.0 / 3.0):
        return True
    return False


def sanitize_quote(q: dict[str, Any] | None) -> dict[str, Any] | None:
    if q is None:
        return None
    curr = q.get("current_price") or q.get("close")
    if curr is None:
        return q
    try:
        current = float(curr)
        if current <= 0:
            return q
        pre = q.get("pre_close")
        pre_f = float(pre) if pre is not None else None
        low_val = q.get("low")
        if low_val is not None:
            fl = float(low_val)
            if _hl_is_data_glitch(fl, current, pre_f):
                q["low"] = current
        high_val = q.get("high")
        if high_val is not None:
            fh = float(high_val)
            if _hl_is_data_glitch(fh, current, pre_f):
                q["high"] = current
    except (TypeError, ValueError):
        pass
    return q


def fetch_quote(sec: Security, http: HttpClient) -> QuoteData:
    cache_key = f"quote:{sec.qq_symbol}"
    cached = get_realtime_cache(cache_key)
    if cached is not None:
        return sanitize_quote(cached)

    # ── Circuit breaker check — skip Tencent if paused ──
    tencent_available = not _circuit_tencent_quote.is_open

    # Tencent HTTP first — fast and stable for most cases
    if tencent_available:
        try:
            _rate_limit_delay()
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
                    "data_freshness": "live" if is_trading_time() else "stale",
                }
                _circuit_tencent_quote.record_success()
                save_realtime_cache(cache_key, tencent_q)
                return sanitize_quote(tencent_q)
        except (OSError, ValueError, KeyError) as exc:
            _circuit_tencent_quote.record_failure()
            _logger.debug("Tencent HTTP quote failed for %s: %s", sec.qq_symbol, exc)

    # Fallback: pytdx3 (fast timeout, mainly a backup)
    if _check_pytdx3():
        tdx3_q = _fetch_quote_tdx3(sec)
        if tdx3_q is not None:
            tdx3_q["data_source"] = "pytdx3"
            tdx3_q["data_status"] = "full"
            save_realtime_cache(cache_key, tdx3_q)
            return sanitize_quote(tdx3_q)

    # Fallback: mootdx
    mootdx_q = _fetch_quote_mootdx(sec)
    if mootdx_q is not None:
        # 注意：不再走 Tencent HTTP 补充（第 1 优先已失败，跳过重复超时）
        mootdx_q["data_source"] = "mootdx"
        mootdx_q["data_status"] = "full"
        save_realtime_cache(cache_key, mootdx_q)
        return sanitize_quote(mootdx_q)

    # Cleanup: 移除了重复的 Tencent HTTP retry（do_fetch），
    # 因为 Tencent HTTP 已在上方尝试过，再次 retry 不会成功。
    # 全源失败时返回空 dict 而非 None，避免下游 .get() 调用引发 AttributeError。
    return {}


def _ohlc_float(v: Any) -> float | None:
    """OHLC 安全转 float；None/空/非数 → None（禁止当成 0 参与 ATR）。"""
    if v is None or v == "" or v == "--":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _compute_atr_fields(bars: list[dict[str, Any]]) -> None:
    """对日线 bar 列表原地附加 TR / ATR14 / ATR7 / ATR_ratio 字段。

    需要至少 8 根 bar 才能计算 atr7，15 根才能计算 atr14。
    不足或 OHLC 缺失时字段为 None（与 indicator_math.calc_atr_series 预热语义一致）。
    下游请用 ``(atr14 or 0)`` / ``atr14 is not None``；勿把不足当成 ATR=0。
    """
    if not bars:
        return
    for i, bar in enumerate(bars):
        h = _ohlc_float(bar.get("high"))
        l = _ohlc_float(bar.get("low"))
        if h is None or l is None or h < l:
            bar["tr"] = None
            continue
        if i == 0:
            bar["tr"] = round(h - l, 4)
            continue
        pc = _ohlc_float(bars[i - 1].get("close"))
        if pc is None:
            pc = _ohlc_float(bars[i - 1].get("open"))
        if pc is None:
            bar["tr"] = None
            continue
        bar["tr"] = round(max(h - l, abs(h - pc), abs(l - pc)), 4)

    def _sma_atr(i: int, period: int) -> float | None:
        if i < period - 1:
            return None
        window = [bars[j].get("tr") for j in range(i - period + 1, i + 1)]
        if any(t is None for t in window):
            return None
        return round(sum(float(t) for t in window) / period, 4)

    for i, bar in enumerate(bars):
        bar["atr7"] = _sma_atr(i, 7)
        bar["atr14"] = _sma_atr(i, 14)
        close = _ohlc_float(bar.get("close"))
        atr14 = bar.get("atr14")
        if close is not None and close > 0 and atr14 is not None and atr14 > 0:
            bar["atr_ratio"] = round(float(atr14) / float(close), 4)
        else:
            bar["atr_ratio"] = None


def ensure_bars_ascending(
    bars: list[dict[str, Any]] | None,
    *,
    recompute_atr: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """K 线契约：时间正序，bars[-1]=最新。

    Tushare 等源常倒序；倒序下 ATR（用 bars[i-1].close 作昨收）、MA、
    lookback ``[-n:]``、intraday_as_of 全会错。

    日线用日期键；分钟线保留完整 ``date``/``datetime`` 字符串（勿截成日，
    否则同日内倒序无法纠正）。

    Returns:
        (bars, rewritten) — rewritten=True 表示曾重排；若 recompute_atr 则已重算 ATR。
    """
    rows = list(bars or [])
    if len(rows) < 2:
        return rows, False

    def _d(b: dict[str, Any]) -> str:
        # 完整时间戳优先，保证 5m/15m/30m 同日内也能正序
        raw = str(
            b.get("datetime")
            or b.get("date")
            or b.get("trade_date")
            or b.get("time")
            or ""
        ).strip()
        # Tushare 等源常见 YYYYMMDD：规范化后再比，避免与 YYYY-MM-DD 混排错位
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        if len(raw) >= 8 and raw[:8].isdigit() and (len(raw) == 8 or raw[8] in " T"):
            # 20260728 / 20260728 10:00
            head, _, rest = raw.partition(" ")
            if len(head) == 8 and head.isdigit():
                norm = f"{head[:4]}-{head[4:6]}-{head[6:8]}"
                return f"{norm} {rest}".rstrip() if rest else norm
        return raw

    dates = [_d(b) for b in rows]
    if not all(dates):
        return rows, False
    if dates == sorted(dates):
        return rows, False
    rows.sort(key=_d)
    if recompute_atr:
        _compute_atr_fields(rows)
    return rows, True


def _fetch_daily_sina(sec: Security, days: int = 300) -> list[dict[str, Any]] | None:
    """Fetch daily K-line from Sina API as fallback when Tencent fails.

    Uses the same Sina endpoint as minute bars but with scale=240 (daily).
    Returns None on failure.
    """
    try:
        _rate_limit_delay()
        url = (
            f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={sec.qq_symbol}&scale=240"
            f"&ma=no&datalen={max(days, 20)}"
        )
        ssl_ctx = ssl.create_default_context()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://finance.sina.com.cn/",
        }
        # 指数退避重试（仅网络异常，HTTP 错误码不重试）
        from urllib.error import HTTPError
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = Request(url, headers=headers)
                with urlopen(request, timeout=TIMEOUT_SECONDS, context=ssl_ctx) as response:
                    text = response.read().decode("gbk", errors="ignore")
                    break
            except HTTPError:
                raise  # HTTP 错误码不重试
            except (TimeoutError, socket.timeout, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2 * (2 ** attempt))
        else:
            raise last_error  # type: ignore[misc]

        raw_data = json.loads(text or "[]")

        if not raw_data or not isinstance(raw_data, list) or isinstance(raw_data, dict):
            return None

        bars: list[dict[str, Any]] = []
        for row in raw_data:
            dt_str = str(row.get("day", ""))
            close = to_float(row.get("close"))
            if close is None:
                continue
            bars.append({
                "date": dt_str.split(" ")[0] if dt_str else "",
                "open": to_float(row.get("open")),
                "high": to_float(row.get("high")),
                "low": to_float(row.get("low")),
                "close": close,
                "volume": to_float(row.get("volume")),
                "amount": None,
            })
        return bars if bars else None
    except Exception as exc:
        _logger.debug("Sina daily fallback failed for %s: %s", sec.qq_symbol, exc)
        return None


def fetch_qfq_daily(sec: Security, http: HttpClient, days: int = 300) -> list[dict[str, Any]]:
    """拉取日线（腾讯优先）。出口保证时间正序，bars[-1]=最新。"""
    bars = _fetch_qfq_daily_raw(sec, http, days=days)
    fixed, _ = ensure_bars_ascending(bars if isinstance(bars, list) else [])
    return fixed


def _fetch_qfq_daily_raw(sec: Security, http: HttpClient, days: int = 300) -> list[dict[str, Any]]:
    from trader_shared.cache_utils import daily_bars_cache_target as _daily_cache_target

    _qfq_cache_target = _daily_cache_target(sec.code, provider="tencent", adjust="qfq")

    # ── Circuit breaker check — return cached data if paused ──
    if _circuit_tencent_daily.is_open:
        _logger.debug("Circuit breaker open for daily bars, returning cached data for %s", sec.code)
        try:
            from trader_shared.cache_utils import (
                get_cached as _file_cached,
                CACHE_DAILY,
                is_fetch_date_today,
                unwrap_bars_payload,
            )
            # 熔断：先读分桶 qfq；兼容旧裸 code 缓存
            for _ck in (_qfq_cache_target, sec.code):
                _cached_result = _file_cached(CACHE_DAILY, _ck, ttl=86400 * 7)
                if _cached_result is None:
                    continue
                _data = _cached_result.data
                # 熔断时优先同日包装缓存；裸 list 仅未过 TTL 可用
                if is_fetch_date_today(_data):
                    _rows = unwrap_bars_payload(_data)
                    if _rows:
                        return _rows
                if isinstance(_data, list) and not _cached_result.stale:
                    return _data
        except (ImportError, OSError):
            pass
        return []

    # ── 文件缓存：按自然日 fetch_date 复用（与 Tushare 路径一致）──
    try:
        from trader_shared.cache_utils import (
            get_cached as _file_cached,
            CACHE_DAILY,
            TTL_BARS_DAY,
            is_fetch_date_today,
            unwrap_bars_payload,
        )
        _cached_result = _file_cached(CACHE_DAILY, _qfq_cache_target, ttl=TTL_BARS_DAY)
        if _cached_result is not None:
            _data = _cached_result.data
            if is_fetch_date_today(_data):
                _rows = unwrap_bars_payload(_data)
                if isinstance(_rows, list) and len(_rows) >= 200:
                    return _rows
            # 兼容旧裸 list + 未过 TTL
            if (
                isinstance(_data, list)
                and len(_data) >= 200
                and not _cached_result.stale
            ):
                return _data
    except (ImportError, OSError) as exc:
        _logger.debug("File cache read failed for %s: %s", sec.code, exc)

    # Tencent HTTP first — fast and stable
    raw_params = f"_var=kline_dayhfq&param={sec.qq_symbol},day,,,{max(days, 20)},qfq"
    cache_key = get_cache_key(TENCENT_FQKLINE_URL, raw_params)

    cached = get_from_cache(cache_key)
    if cached is not None:
        return cached

    def do_fetch():
        _rate_limit_delay()
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
                    "adjust": "qfq",
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
                        "data_status": "partial",  # 非前复权数据，标记为 partial
                        "adjust": "none",
                    })
        if not bars:
            raise RuntimeError("Tencent qfq daily bars unavailable")
        return bars

    try:
        result = retry(do_fetch)
        _circuit_tencent_daily.record_success()
        _compute_atr_fields(result)
        # 是否覆盖「应有最新交易日」：用 trading_context，勿比墙钟日历日
        _dates = [b.get("date") for b in result if b.get("date")]
        _latest_date = max(_dates) if _dates else None
        try:
            from trader_shared.trading_context import compute_data_freshness
            has_today = bool(_latest_date) and compute_data_freshness(_latest_date) == "live"
        except Exception:
            has_today = bool(_latest_date) and _latest_date >= datetime.now().strftime("%Y-%m-%d")
        if not has_today:
            save_to_cache(cache_key, result, ttl_seconds=3600)
        # ── 写入文件缓存（带 fetch_date，同日复用；按 adjust 分桶）──
        try:
            from trader_shared.cache_utils import (
                set_cached,
                validate_bars,
                CACHE_DAILY,
                cache_calendar_date,
                daily_bars_cache_target,
            )
            if validate_bars(result):
                _adj = (
                    "qfq"
                    if any(
                        isinstance(b, dict) and b.get("adjust") == "qfq"
                        for b in result[-min(5, len(result)) :]
                    )
                    else "none"
                )
                set_cached(
                    CACHE_DAILY,
                    daily_bars_cache_target(
                        sec.code, provider="tencent", adjust=_adj
                    ),
                    {"fetch_date": cache_calendar_date(), "rows": result},
                )
        except (ImportError, OSError) as exc:
            _logger.debug("File cache write failed for %s: %s", sec.code, exc)
        return result
    except RuntimeError:
        _circuit_tencent_daily.record_failure()

    # Fallback: Sina daily bars (scale=240 = daily)
    sina_bars = _fetch_daily_sina(sec, days)
    if sina_bars:
        for bar in sina_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "partial"
        _compute_atr_fields(sina_bars)
        return sina_bars

    # Fallback: pytdx3
    if _check_pytdx3():
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
    category_map = {"5m": "5m", "15m": "15m", "30m": "30m", "60m": "60m", "weekly": "weekly", "monthly": "monthly"}
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
        fixed, _ = ensure_bars_ascending(fallback_bars, recompute_atr=False)
        return fixed
    
    _logger.warning("Sina HTTP fetch_5m failed or incomplete for %s, falling back to Mootdx", sec.qq_symbol)
    bars = _fetch_mins_mootdx(sec, "5m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        fixed, _ = ensure_bars_ascending(bars, recompute_atr=False)
        return fixed
    return []


def fetch_15m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, "15m", datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        fixed, _ = ensure_bars_ascending(fallback_bars, recompute_atr=False)
        return fixed
    
    _logger.warning("Sina HTTP fetch_15m failed or incomplete for %s, falling back to Mootdx", sec.qq_symbol)
    bars = _fetch_mins_mootdx(sec, "15m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        fixed, _ = ensure_bars_ascending(bars, recompute_atr=False)
        return fixed
    return []


def fetch_30m(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, "30m", datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        fixed, _ = ensure_bars_ascending(fallback_bars, recompute_atr=False)
        return fixed
    
    _logger.warning("Sina HTTP fetch_30m failed or incomplete for %s, falling back to Mootdx", sec.qq_symbol)
    bars = _fetch_mins_mootdx(sec, "30m", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        fixed, _ = ensure_bars_ascending(bars, recompute_atr=False)
        return fixed
    return []


def fetch_weekly(sec: Security, http: HttpClient, datalen: int | None = None) -> list[dict[str, Any]]:
    """Fetch weekly K-line bars. Sina HTTP first, fallback to mootdx.

    默认根数见 config.WEEKLY_LOOKBACK_BARS（中线缠论需要足够周线成笔/成段）。
    当天第一次打网，同日复用。
    """
    if datalen is None:
        try:
            from trader_shared.config import WEEKLY_LOOKBACK_BARS
            datalen = int(WEEKLY_LOOKBACK_BARS)
        except Exception:
            datalen = 260

    from trader_shared.cache_utils import get_day_scoped_bars, CACHE_WEEKLY

    def _net() -> list[dict[str, Any]]:
        fallback_bars = _fetch_mins_fallback(sec, "weekly", datalen)
        if fallback_bars and len(fallback_bars) >= 4:
            for bar in fallback_bars:
                bar["data_source"] = "sina"
                bar["data_status"] = "full"
            return fallback_bars
        bars = _fetch_mins_mootdx(sec, "weekly", datalen)
        if bars:
            for bar in bars:
                bar["data_source"] = "mootdx (fallback)"
                bar["data_status"] = "partial"
            return bars
        return []

    return get_day_scoped_bars(CACHE_WEEKLY, sec.code, _net, min_rows=4)


def fetch_monthly(sec: Security, http: HttpClient, datalen: int = 60) -> list[dict[str, Any]]:
    """Fetch monthly K-line bars. Sina HTTP first, fallback to mootdx."""
    fallback_bars = _fetch_mins_fallback(sec, "monthly", datalen)
    if fallback_bars and len(fallback_bars) >= 3:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        fixed, _ = ensure_bars_ascending(fallback_bars)
        return fixed

    bars = _fetch_mins_mootdx(sec, "monthly", datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        fixed, _ = ensure_bars_ascending(bars)
        return fixed
    return []


def fetch_kline(sec: Security, http: HttpClient, datalen: int = 60, interval: str = "60") -> list[dict[str, Any]]:
    fallback_bars = _fetch_mins_fallback(sec, interval, datalen)
    if fallback_bars and len(fallback_bars) >= 8:
        for bar in fallback_bars:
            bar["data_source"] = "sina"
            bar["data_status"] = "full"
        fixed, _ = ensure_bars_ascending(fallback_bars, recompute_atr=False)
        return fixed

    warnings.warn(f"⚠️ Sina HTTP fetch_kline (interval {interval}) failed or incomplete. Falling back to Mootdx Quote client.")
    bars = _fetch_mins_mootdx(sec, interval, datalen)
    if bars:
        for bar in bars:
            bar["data_source"] = "mootdx (fallback)"
            bar["data_status"] = "partial"
        fixed, _ = ensure_bars_ascending(bars, recompute_atr=False)
        return fixed
    return []


def _fetch_mins_fallback(sec: Security, interval: str, datalen: int) -> list[dict[str, Any]]:
    """Try Sina HTTP API first to avoid AkShare proxy/TLS disconnections, then fallback to AkShare.
    
    Sina HTTP (CN_MarketData.getKLineData) is highly reliable, robust, and performs well
    without third-party packages or proxy interference.
    """
    try:
        period_map = {"5m": "5", "15m": "15", "30m": "30", "60m": "60", "60": "60", "weekly": "1200", "monthly": "7200"}
        scale = period_map.get(interval, "5")
        
        import ssl
        from urllib.request import Request, urlopen
        import json
        
        _rate_limit_delay()
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sec.qq_symbol}&scale={scale}&ma=no&datalen={datalen}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://finance.sina.com.cn/",
        }
        ssl_ctx = ssl.create_default_context()
        
        # 指数退避重试（仅网络异常，HTTP 错误码不重试）
        from urllib.error import HTTPError
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = Request(url, headers=headers)
                with urlopen(request, timeout=5, context=ssl_ctx) as response:
                    text = response.read().decode("gbk", errors="ignore")
                    break
            except HTTPError:
                raise  # HTTP 错误码不重试
            except (TimeoutError, socket.timeout, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2 * (2 ** attempt))
        else:
            raise last_error  # type: ignore[misc]

        raw_data = json.loads(text or "[]")
            
        if raw_data and isinstance(raw_data, list):
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
        _logger.debug("Sina HTTP fallback failed for %s %s: %s", sec.qq_symbol, interval, e)

    try:
        import akshare as ak
    except ImportError:
        return []
    try:
        period_map = {"5m": "5", "15m": "15", "30m": "30", "60": "60", "weekly": "weekly", "monthly": "monthly"}
        period = period_map.get(interval, "60")
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period=period, adjust="qfq")
        if df is None or df.empty:
            return []
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
    except (ImportError, OSError, ValueError) as exc:
        _logger.debug("AkShare fallback failed for %s %s: %s", sec.qq_symbol, interval, exc)
        return []  # 返回空列表而非 None，避免调用方 len(None) TypeError


def _fetch_fund_flow_safe(target: str) -> dict[str, Any]:
    """获取资金流向数据（安全包装，失败返回空 dict）。"""
    try:
        from trader_shared.cache_utils import fetch_fund_flow_cached
        from trader_shared.fund_flow_data import calc_fund_flow_features
        from trader_shared.main_force import detect_main_force_stage
        ff_data = fetch_fund_flow_cached(target)
        if ff_data:
            daily_flow = ff_data.get("daily_flow", [])
            features = ff_data.get("features", {})
            if daily_flow:
                mf = detect_main_force_stage(features)
                return {"features": features, "stage": mf}
    except (ImportError, OSError, ValueError) as exc:
        _logger.debug("Fund flow fetch failed for %s: %s", target, exc)
    return {}


def load_market_snapshot(target: str, days: int = 300, include_5m: bool = True, include_weekly: bool = True, include_monthly: bool = True, include_ticks: bool = True) -> MarketSnapshot:
    sec = resolve_security(target)
    http = HttpClient()
    source_errors: dict[str, str] = {}
    missing_sources: list[str] = []

    results: dict[str, Any] = {}
    # 复用全局共享线程池，避免嵌套 ThreadPoolExecutor 导致线程爆炸
    pool = get_shared_build_pool()
    f_quote = pool.submit(fetch_quote, sec, http)
    f_daily = pool.submit(fetch_qfq_daily, sec, http, days=days)
    f_futures: dict[Any, str] = {f_quote: "quote", f_daily: "daily"}
    if include_5m:
        f_futures[pool.submit(fetch_5m, sec, http)] = "bars_5m"
    if include_weekly:
        f_futures[pool.submit(fetch_weekly, sec, http)] = "weekly_bars"
    if include_monthly:
        f_futures[pool.submit(fetch_monthly, sec, http)] = "monthly_bars"
    if include_ticks:
        f_futures[pool.submit(_fetch_ticks_tdx3, sec, 500)] = "tick_data"

    for future in as_completed(f_futures):
        key = f_futures[future]
        try:
            results[key] = future.result(timeout=30)
        except Exception as exc:
            results[key] = None
            source_errors[key] = str(exc)
            missing_sources.append(key)

    quote = results.get("quote") or {}
    # 空 {} 引致 "quote and ..." 为 False，到第 3 分支 degraded。但 missing_sources 未含 "quote"，
    # 且下游 quote.get("current_price") 为 None。显式补录 missing_sources。
    if isinstance(quote, dict) and not quote.get("current_price"):
        if "quote" not in missing_sources:
            missing_sources.append("quote")
    daily_bars = results.get("daily") or []
    bars_5m = results.get("bars_5m") or []
    weekly_bars = results.get("weekly_bars") or []
    monthly_bars = results.get("monthly_bars") or []
    # 快照边界：统一正序，防止任一源/缓存倒序污染 ATR/MA/缠论 lookback
    daily_bars, _ = ensure_bars_ascending(daily_bars)
    weekly_bars, _ = ensure_bars_ascending(weekly_bars)
    monthly_bars, _ = ensure_bars_ascending(monthly_bars)
    bars_5m, _ = ensure_bars_ascending(bars_5m, recompute_atr=False)
    tick_data = results.get("tick_data") or []
    order_book = quote.get("order_book")
    if isinstance(quote, dict):
        quote = dict(quote)  # shallow copy to avoid mutating the cache
        if "order_book" in quote:
            del quote["order_book"]

    def _snapshot_data_freshness(bars) -> str:
        """基于日线最新日期判定数据是否最新可用（覆盖到最近交易日 → live）。

        用 max(date) 而非 bars[-1]，防止偶发倒序误判 stale/live。
        """
        if not bars:
            return "stale"
        dates = [
            str(b.get("date") or b.get("time") or "")[:10]
            for b in bars
            if b.get("date") or b.get("time")
        ]
        last = max(dates) if dates else None
        if not last:
            return "stale"
        try:
            from trader_shared.trading_context import compute_data_freshness
        except ImportError:
            return "live"
        return compute_data_freshness(last)

    # ── 日 K 不与实时 quote 合并 ──
    # 与 report_builder / TushareProvider 一致：策略用 bars 保持收盘序列；
    # 盘中现价走 quote + build_live_bar_anchor，避免 partial 今日 bar 污染 MA/ATR。
    # 若调用方显式需要 merge，请用 cache_utils.merge_daily_bars_with_quote。

    if include_5m and not bars_5m and "bars_5m" not in missing_sources:
        missing_sources.append("bars_5m")

    if include_weekly and not weekly_bars and "weekly_bars" not in missing_sources:
        missing_sources.append("weekly_bars")

    if include_monthly and not monthly_bars and "monthly_bars" not in missing_sources:
        missing_sources.append("monthly_bars")

    if quote and daily_bars and not missing_sources:
        # 完备度由「分项源是否缺失」(missing_sources) 与「核心行情 quote 是否降级」决定。
        # 各源内部个别 bar 的 data_status（如日线非前复权、分钟线 fallback）属数据质量细分，
        # 已在各 bar 的 data_status 字段暴露给下游消费，不应反向降级整体 data_status，
        # 否则即使所有源都取到数据，整体也会因个别 bar 标记而永远 partial。
        if isinstance(quote, dict) and quote.get("data_status") == "partial":
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
        weekly_bars=weekly_bars,
        monthly_bars=monthly_bars,
        order_book=order_book,
        tick_data=tick_data,
        data_status=data_status,
        data_freshness=_snapshot_data_freshness(daily_bars),
        fund_flow=_fetch_fund_flow_safe(target),
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
    # 契约：时间正序，bars[-1]=最新（部分源如 Tushare 可能倒序）
    bars.sort(key=lambda b: str(b.get("date") or b.get("trade_date") or "")[:10])
    return bars


def pct_change(start: float, end: float) -> float:
    if start == 0:
        return 0.0 if end == 0 else float('inf')
    return ((end / start) - 1.0) * 100


# ── Memory-efficient batch reading ────────────────────────────────────


def iter_qfq_daily_batches(
    sec: Security,
    http: HttpClient,
    days: int = 300,
    batch_size: int = 50,
) -> list[list[dict[str, Any]]]:
    """Fetch daily K-line data and return as batches for memory efficiency.

    Instead of returning all bars as a single list, this function splits them
    into batches of ``batch_size``. This allows callers to process bars in
    chunks (e.g., for parallel analysis) without holding the entire dataset
    in memory at once.

    Args:
        sec: Security to fetch data for.
        http: HTTP client instance.
        days: Number of days to fetch (default 300).
        batch_size: Number of bars per batch (default 50).

    Returns:
        List of batches, where each batch is a list of bar dicts.
        Returns empty list if fetch fails.
    """
    all_bars = fetch_qfq_daily(sec, http, days=days)
    if not all_bars:
        return []

    batches: list[list[dict[str, Any]]] = []
    for i in range(0, len(all_bars), batch_size):
        batches.append(all_bars[i : i + batch_size])
    return batches


def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB.

    Returns 0.0 if psutil is not available.
    """
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0
