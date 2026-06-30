"""Unified DataProvider interface — pluggable data source abstraction.

Usage:
    from trader_shared.data_provider import get_provider
    provider = get_provider()
    sec = provider.resolve_security("南网科技")
    bars = provider.fetch_qfq_daily(sec, days=365)

Plugin a custom provider:
    from trader_shared.data_provider import set_provider
    set_provider(MyAkShareProvider())
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from trader_shared._logging import get_logger
from trader_shared.light_data import to_float

_logger = get_logger(__name__)

# -------- inject shared paths so we can import light_data / models --------
_shared = Path(__file__).resolve().parents[1]
_market_data = _shared / "01-行情数据-market-data"

DataStatus = Literal["full", "partial", "degraded", "failed"]


@dataclass(frozen=True)
class Security:
    code: str
    market: str = ""
    name: str = ""

    @property
    def ts_code(self) -> str:
        m = self.market.upper() if self.market else ("SH" if self.code.startswith(("6", "5", "9")) else "SZ")
        return f"{self.code}.{m}"

    @property
    def qq_symbol(self) -> str:
        m = self.market.lower() if self.market else ("sh" if self.code.startswith(("6", "5", "9")) else "sz")
        return f"{m}{self.code}"


@dataclass(frozen=True)
class MarketSnapshot:
    security: Security
    quote: dict[str, Any]
    daily_bars: list[dict[str, Any]]
    bars_5m: list[dict[str, Any]] = field(default_factory=list)
    order_book: dict[str, Any] | None = None
    tick_data: list[dict[str, Any]] = field(default_factory=list)
    data_status: DataStatus = "full"
    data_freshness: str = "live"  # "live" 或 "stale"，用于停牌/离线检测
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    extend_fundamental: dict[str, Any] | None = None
    extend_sentiment: dict[str, Any] | None = None


# ═══════════════════════════════════════════════
# Abstract DataProvider protocol
# ═══════════════════════════════════════════════

@runtime_checkable
class DataProvider(Protocol):
    """Interface that all data sources must implement."""

    def resolve_security(self, target: str) -> Security:
        """Parse stock name or code → Security."""
        ...

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        """Real-time quote snapshot from Tencent or equivalent."""
        ...

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        """Forward-adjusted daily bars with ATR fields."""
        ...

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Sina 5-minute K-line."""
        ...

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Sina 15-minute K-line."""
        ...

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Sina 30-minute K-line."""
        ...

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        """Generic multi-cycle K-line."""
        ...

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        """Aggregate quote + daily + optional 5m into a single snapshot."""
        ...

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        """Fetch transaction ticks for the security."""
        ...

    def pct_change(self, start: float, end: float) -> float:
        """Percentage change."""
        ...

    def to_float(self, value: Any) -> float | None:
        """Safe string → float conversion."""
        ...

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize raw K-line bars."""
        ...

    @property
    def name(self) -> str:
        """Human-readable provider name for logging."""
        ...


# ═══════════════════════════════════════════════
# Default provider: Tencent + Sina (via light_data)
# ═══════════════════════════════════════════════

_ENRICH_CACHE: dict[str, tuple[float, dict, dict]] = {}
_ENRICH_TTL = 600  # 10 分钟缓存，基本面数据不会盘中秒变


def _enrich_snapshot(snap: MarketSnapshot) -> MarketSnapshot:
    """Enrich the MarketSnapshot with extend_fundamental and extend_sentiment using a thread pool.

    三层缓存策略:
    1. 文件缓存 (TTL 12小时) — 盘后预缓存的数据，进程重启不丢失
    2. 内存缓存 (TTL 10分钟) — 同一进程内快速命中
    3. 实时抓取 — 缓存全部 miss 时走 4 路 API
    """
    sec = snap.security
    if not sec or not sec.code or len(sec.code) != 6 or not sec.code.isdigit():
        return snap

    import time
    import dataclasses

    # ── 层1: 文件缓存命中 (TTL 12小时) ──
    try:
        from trader_shared.cache_utils import get_cached as _file_cached, CACHE_ENRICH, TTL_FUNDAMENTAL
        _cached_result = _file_cached(CACHE_ENRICH, sec.code, ttl=TTL_FUNDAMENTAL)
        file_cached = _cached_result.data if _cached_result is not None else None
        if file_cached is not None and isinstance(file_cached, dict):
            extend_fundamental = file_cached.get("extend_fundamental", {})
            extend_sentiment = file_cached.get("extend_sentiment", {})
            if extend_fundamental or extend_sentiment:
                _ENRICH_CACHE[sec.code] = (time.time(), extend_fundamental, extend_sentiment)
                return dataclasses.replace(
                    snap,
                    extend_fundamental=extend_fundamental,
                    extend_sentiment=extend_sentiment,
                )
    except (ImportError, OSError) as exc:
        _logger.debug("Enrich file cache read failed for %s: %s", sec.code, exc)

    # ── 层2: 内存缓存命中 (TTL 10分钟) ──
    now = time.time()
    cached = _ENRICH_CACHE.get(sec.code)
    if cached is not None and now - cached[0] < _ENRICH_TTL:
        return dataclasses.replace(
            snap,
            extend_fundamental=cached[1],
            extend_sentiment=cached[2],
        )

    # ── 层3: 实时抓取 ──
    try:
        from trader_shared.extend_data import ExtendDataProvider
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_sh = executor.submit(ExtendDataProvider.get_shareholder_trend, sec.code)
            f_eps = executor.submit(ExtendDataProvider.get_ths_consensus_eps, sec.code)
            f_unlocks = executor.submit(ExtendDataProvider.get_upcoming_unlocks, sec.code)
            f_hot = executor.submit(ExtendDataProvider.get_ths_hot_reason_for_stock, sec.code)

            sh_trend = f_sh.result(timeout=2.0)
            ths_eps = f_eps.result(timeout=2.0)
            unlocks = f_unlocks.result(timeout=2.0)
            hot_reason = f_hot.result(timeout=2.0)

            extend_fundamental = {
                "shareholder": sh_trend,
                "consensus_eps": ths_eps,
            }
            extend_sentiment = {
                "unlocks": unlocks,
                "theme_harden": hot_reason,
            }

            # 写入内存缓存
            _ENRICH_CACHE[sec.code] = (now, extend_fundamental, extend_sentiment)

            # 写入文件缓存
            try:
                from trader_shared.cache_utils import set_cached as _file_set, CACHE_ENRICH
                _file_set(CACHE_ENRICH, sec.code, {
                    "extend_fundamental": extend_fundamental,
                    "extend_sentiment": extend_sentiment,
                })
            except (ImportError, OSError) as exc:
                _logger.debug("Enrich file cache write failed for %s: %s", sec.code, exc)

            return dataclasses.replace(
                snap,
                extend_fundamental=extend_fundamental,
                extend_sentiment=extend_sentiment,
            )
    except Exception as e:
        _logger.warning("Failed to enrich snapshot with advanced metrics for %s: %s", sec.code, e)
        return snap


class UnifiedProvider:
    """Unified data provider — single implementation for all backends.

    For tencent/mootdx backends, delegates to light_data.py functions.
    For akshare backend, uses akshare API directly.
    """

    def __init__(self, backend: str = "tencent") -> None:
        self._backend = backend
        self._http = None

    @property
    def name(self) -> str:
        return self._backend

    def _ensure_http(self) -> None:
        if self._http is None:
            from trader_shared.light_data import HttpClient
            self._http = HttpClient()

    def _to_sec(self, sec: Security):
        from trader_shared.light_data import Security as _Sec
        return _Sec(sec.code, sec.market, sec.name)

    # ── Common methods (all backends) ──

    def resolve_security(self, target: str) -> Security:
        from trader_shared.light_data import resolve_security as _resolve
        sec = _resolve(target)
        return Security(code=sec.code, market=sec.market, name=sec.name)

    def pct_change(self, start: float, end: float) -> float:
        from trader_shared.light_data import pct_change as _fn
        return _fn(start, end)

    def to_float(self, value: Any) -> float | None:
        from trader_shared.light_data import to_float as _fn
        return _fn(value)

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from trader_shared.light_data import normalize_bars as _fn
        return _fn(raw_bars)

    # ── Tencent/Mootdx backend (default) ──

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        if self._backend == "akshare":
            return self._akshare_fetch_quote(sec)
        self._ensure_http()
        from trader_shared.light_data import fetch_quote as _fetch
        return _fetch(self._to_sec(sec), self._http)

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        if self._backend == "akshare":
            return self._akshare_fetch_qfq_daily(sec, days)
        from trader_shared.cache_utils import get_cached, set_cached, TTL_DAILY
        cached = get_cached("daily", sec.code, ttl=TTL_DAILY)
        if cached is not None:
            return cached.data
        self._ensure_http()
        from trader_shared.light_data import fetch_qfq_daily as _fetch
        bars = _fetch(self._to_sec(sec), self._http, days=days)
        set_cached("daily", sec.code, bars)
        return bars

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "5", datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_5m as _fetch
        return _fetch(self._to_sec(sec), self._http, datalen=datalen)

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "15", datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_15m as _fetch
        return _fetch(self._to_sec(sec), self._http, datalen=datalen)

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "30", datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_30m as _fetch
        return _fetch(self._to_sec(sec), self._http, datalen=datalen)

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, scale, datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_kline as _fetch
        return _fetch(self._to_sec(sec), self._http, interval=scale, datalen=datalen)

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        if self._backend != "mootdx":
            return []
        self._ensure_http()
        try:
            from trader_shared.light_data import _fetch_ticks_tdx3
            res = _fetch_ticks_tdx3(self._to_sec(sec), count=count)
            return res if res is not None else []
        except ImportError:
            return []

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        if self._backend == "akshare":
            return self._akshare_load_snapshot(target, days, include_5m, include_ticks)
        from trader_shared.light_data import load_market_snapshot as _load
        snap = _load(target, days=days, include_5m=include_5m, include_ticks=include_ticks)
        sec = Security(code=snap.security.code, market=snap.security.market, name=snap.security.name)
        res_snap = MarketSnapshot(
            security=sec,
            quote=snap.quote,
            daily_bars=snap.daily_bars,
            bars_5m=snap.bars_5m,
            order_book=getattr(snap, "order_book", None),
            tick_data=getattr(snap, "tick_data", []),
            data_status=snap.data_status,
            data_freshness=getattr(snap, "data_freshness", "live"),
            missing_sources=snap.missing_sources,
            source_errors=snap.source_errors,
            fetched_at=snap.fetched_at,
        )
        return _enrich_snapshot(res_snap)

    # ── AkShare-specific methods ──

    def _akshare_ensure(self) -> None:
        try:
            import akshare  # noqa: F401
        except ImportError:
            raise RuntimeError("akshare 未安装。请运行: pip install akshare")

    def _akshare_to_bar(self, row: dict[str, Any], dt_key: str = "date") -> dict[str, Any] | None:
        close = to_float(row.get("收盘") or row.get("close"))
        if close is None:
            return None
        date_val = str(row.get("日期") or row.get(dt_key, ""))
        return {
            "date": date_val.split(" ")[0] if " " in date_val else date_val,
            "time": date_val,
            "open": to_float(row.get("开盘") or row.get("open")),
            "close": close,
            "high": to_float(row.get("最高") or row.get("high")),
            "low": to_float(row.get("最低") or row.get("low")),
            "volume": to_float(row.get("成交量") or row.get("vol") or row.get("volume")),
            "amount": to_float(row.get("成交额") or row.get("amount")),
        }

    def _akshare_fetch_quote(self, sec: Security) -> dict[str, Any]:
        self._akshare_ensure()
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == sec.code]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "name": str(r.get("名称", sec.name)),
            "symbol": sec.ts_code,
            "current_price": to_float(r.get("最新价")),
            "pre_close": to_float(r.get("昨收")),
            "open": to_float(r.get("今开")),
            "high": to_float(r.get("最高")),
            "low": to_float(r.get("最低")),
            "volume": to_float(r.get("成交量")),
            "turnover_rate": to_float(r.get("换手率")),
            "current_change_pct": to_float(r.get("涨跌幅")),
        }

    def _akshare_fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        self._akshare_ensure()
        import akshare as ak
        import pandas as pd
        start_date = ""
        if days:
            from datetime import timedelta
            start_date = (pd.Timestamp.today() - timedelta(days=days)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=sec.code, period="daily", start_date=start_date, end_date="", adjust="qfq")
        bars = [bar for _, row in df.iterrows() if (bar := self._akshare_to_bar(row.to_dict()))]
        from trader_shared.light_data import _compute_atr_fields
        _compute_atr_fields(bars)
        return bars

    def _akshare_fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        self._akshare_ensure()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period=scale)
        return [bar for _, row in df.tail(datalen).iterrows() if (bar := self._akshare_to_bar(row.to_dict(), dt_key="时间"))]

    def _akshare_load_snapshot(self, target: str, days: int, include_5m: bool, include_ticks: bool) -> MarketSnapshot:
        sec = self.resolve_security(target)
        daily_bars, bars_5m, quote, tick_data = [], [], {}, []
        source_errors: dict[str, str] = {}
        try:
            daily_bars = self.fetch_qfq_daily(sec, days=days)
        except Exception as e:
            source_errors["daily"] = str(e)
        try:
            quote = self.fetch_quote(sec)
        except Exception as e:
            source_errors["quote"] = str(e)
        if include_5m:
            try:
                bars_5m = self.fetch_5m(sec)
            except Exception as e:
                source_errors["5m"] = str(e)
        data_status = "full" if (daily_bars and quote) else "partial" if (daily_bars or quote) else "failed"
        res_snap = MarketSnapshot(
            security=sec, quote=quote, daily_bars=daily_bars, bars_5m=bars_5m,
            tick_data=tick_data, data_status=data_status, source_errors=source_errors,
        )
        return _enrich_snapshot(res_snap)


# ═══════════════════════════════════════════════
# Global provider registry
# ═══════════════════════════════════════════════

_provider: DataProvider | None = None
_provider_set = False


def get_provider() -> DataProvider:
    """Return the current DataProvider instance (lazy init via TRADER_DATA_PROVIDER env var)."""
    global _provider
    if _provider is not None:
        return _provider

    provider_name = os.environ.get("TRADER_DATA_PROVIDER", "").lower()
    if provider_name in ("mootdx", "akshare"):
        _provider = UnifiedProvider(backend=provider_name)
        print(f"DataProvider: using {provider_name} (via TRADER_DATA_PROVIDER)", file=sys.stderr)
        return _provider

    _provider = UnifiedProvider(backend="tencent")
    print(f"DataProvider: using tencent", file=sys.stderr)
    return _provider


def set_provider(p: DataProvider) -> None:
    """Replace the global data source with a custom implementation."""
    import os
    global _provider
    _provider = p
    os.environ["TRADER_DATA_PROVIDER"] = p.name
