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
    weekly_bars: list[dict[str, Any]] = field(default_factory=list)
    monthly_bars: list[dict[str, Any]] = field(default_factory=list)
    order_book: dict[str, Any] | None = None
    tick_data: list[dict[str, Any]] = field(default_factory=list)
    data_status: DataStatus = "full"
    data_freshness: str = "live"  # "live" 或 "stale"，用于停牌/离线检测
    fund_flow: dict[str, Any] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    extend_fundamental: dict[str, Any] | None = None
    extend_sentiment: dict[str, Any] | None = None
    extend_margin: dict[str, Any] | None = None       # 融资融券（Phase 1）
    extend_northbound: dict[str, Any] | None = None   # 北向资金（Phase 1）
    extend_sector: dict[str, Any] | None = None       # 行业板块数据（Phase 1）
    extend_concept: dict[str, Any] | None = None      # 概念板块数据（Phase 2）


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
        """Sina 15-minute K-line."""
        ...

    def fetch_weekly(self, sec: Security, datalen: int = 80) -> list[dict[str, Any]]:
        """Weekly K-line bars."""
        ...

    def fetch_monthly(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Monthly K-line bars."""
        ...

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        """Generic multi-cycle K-line."""
        ...

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_weekly: bool = True, include_monthly: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        """Aggregate quote + daily + optional intraday/weekly/monthly into a single snapshot."""
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

_ENRICH_CACHE: dict[str, tuple[float, dict, dict, dict, dict, dict]] = {}
_ENRICH_TTL = 600  # 10 分钟缓存，基本面数据不会盘中秒变


def _enrich_snapshot(snap: MarketSnapshot) -> MarketSnapshot:
    """Enrich the MarketSnapshot with extend_fundamental, extend_sentiment,
    extend_margin, extend_northbound, extend_sector using a thread pool.

    三层缓存策略:
    1. 文件缓存 (TTL 12小时) — 盘后预缓存的数据，进程重启不丢失
    2. 内存缓存 (TTL 10分钟) — 同一进程内快速命中
    3. 实时抓取 — 缓存全部 miss 时走 8 路 API（4 原有 + 3 Phase 1 + 1 Phase 2 概念）
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
            extend_margin = file_cached.get("extend_margin")
            extend_northbound = file_cached.get("extend_northbound")
            extend_sector = file_cached.get("extend_sector")
            extend_concept = file_cached.get("extend_concept")
            if extend_fundamental or extend_sentiment or extend_margin or extend_northbound or extend_sector or extend_concept:
                _ENRICH_CACHE[sec.code] = (time.time(), extend_fundamental, extend_sentiment,
                                           extend_margin or {}, extend_northbound or {},
                                           extend_sector or {}, extend_concept or {})
                return dataclasses.replace(
                    snap,
                    extend_fundamental=extend_fundamental,
                    extend_sentiment=extend_sentiment,
                    extend_margin=extend_margin,
                    extend_northbound=extend_northbound,
                    extend_sector=extend_sector,
                    extend_concept=extend_concept,
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
            extend_margin=cached[3] if len(cached) > 3 else None,
            extend_northbound=cached[4] if len(cached) > 4 else None,
            extend_sector=cached[5] if len(cached) > 5 else None,
            extend_concept=cached[6] if len(cached) > 6 else None,
        )

    # ── 层3: 实时抓取（4 原有 + 3 Phase 1 + 1 Phase 2 概念 = 8 路并行） ──
    try:
        from trader_shared.extend_data import ExtendDataProvider
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=8) as executor:
            # 原有 4 路
            f_sh = executor.submit(ExtendDataProvider.get_shareholder_trend, sec.code)
            f_eps = executor.submit(ExtendDataProvider.get_ths_consensus_eps, sec.code)
            f_unlocks = executor.submit(ExtendDataProvider.get_upcoming_unlocks, sec.code)
            f_hot = executor.submit(ExtendDataProvider.get_ths_hot_reason_for_stock, sec.code)
            # Phase 1 新增 3 路
            f_margin = executor.submit(ExtendDataProvider.get_margin_data, sec.code)
            f_north = executor.submit(ExtendDataProvider.get_northbound_flow)
            f_sector = executor.submit(ExtendDataProvider.get_sector_data, sec.code)
            # Phase 2 新增 1 路：概念板块
            f_concept = executor.submit(ExtendDataProvider.get_concept_data, sec.code)

            sh_trend = f_sh.result(timeout=2.0)
            ths_eps = f_eps.result(timeout=2.0)
            unlocks = f_unlocks.result(timeout=2.0)
            hot_reason = f_hot.result(timeout=2.0)
            margin_data = f_margin.result(timeout=2.0)
            northbound_data = f_north.result(timeout=2.0)
            sector_data = f_sector.result(timeout=2.0)
            concept_data = f_concept.result(timeout=2.0)

            extend_fundamental = {
                "shareholder": sh_trend,
                "consensus_eps": ths_eps,
            }
            extend_sentiment = {
                "unlocks": unlocks,
                "theme_harden": hot_reason,
            }

            # 写入内存缓存
            _ENRICH_CACHE[sec.code] = (now, extend_fundamental, extend_sentiment,
                                       margin_data, northbound_data, sector_data, concept_data)

            # 写入文件缓存
            try:
                from trader_shared.cache_utils import set_cached as _file_set, CACHE_ENRICH
                _file_set(CACHE_ENRICH, sec.code, {
                    "extend_fundamental": extend_fundamental,
                    "extend_sentiment": extend_sentiment,
                    "extend_margin": margin_data,
                    "extend_northbound": northbound_data,
                    "extend_sector": sector_data,
                    "extend_concept": concept_data,
                })
            except (ImportError, OSError) as exc:
                _logger.debug("Enrich file cache write failed for %s: %s", sec.code, exc)

            return dataclasses.replace(
                snap,
                extend_fundamental=extend_fundamental,
                extend_sentiment=extend_sentiment,
                extend_margin=margin_data,
                extend_northbound=northbound_data,
                extend_sector=sector_data,
                extend_concept=concept_data,
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

    def fetch_weekly(self, sec: Security, datalen: int = 80) -> list[dict[str, Any]]:
        """Fetch weekly K-line bars via mootdx or kline endpoint."""
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "weekly", datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_kline as _fetch
        return _fetch(self._to_sec(sec), self._http, interval="weekly", datalen=datalen)

    def fetch_monthly(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Fetch monthly K-line bars via mootdx or kline endpoint."""
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "monthly", datalen)
        self._ensure_http()
        from trader_shared.light_data import fetch_kline as _fetch
        return _fetch(self._to_sec(sec), self._http, interval="monthly", datalen=datalen)

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

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_weekly: bool = True, include_monthly: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        if self._backend == "akshare":
            return self._akshare_load_snapshot(target, days, include_5m, include_weekly, include_monthly, include_ticks)
        from trader_shared.light_data import load_market_snapshot as _load
        snap = _load(target, days=days, include_5m=include_5m, include_weekly=include_weekly, include_monthly=include_monthly, include_ticks=include_ticks)
        sec = Security(code=snap.security.code, market=snap.security.market, name=snap.security.name)
        res_snap = MarketSnapshot(
            security=sec,
            quote=snap.quote,
            daily_bars=snap.daily_bars,
            bars_5m=snap.bars_5m,
            weekly_bars=getattr(snap, "weekly_bars", []),
            monthly_bars=getattr(snap, "monthly_bars", []),
            order_book=getattr(snap, "order_book", None),
            tick_data=getattr(snap, "tick_data", []),
            data_status=snap.data_status,
            data_freshness=getattr(snap, "data_freshness", "live"),
            fund_flow=getattr(snap, "fund_flow", {}),
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

    def _akshare_load_snapshot(self, target: str, days: int, include_5m: bool, include_weekly: bool, include_monthly: bool, include_ticks: bool) -> MarketSnapshot:
        sec = self.resolve_security(target)
        daily_bars, bars_5m, weekly_bars, monthly_bars, quote, tick_data = [], [], [], [], {}, []
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
        if include_weekly:
            try:
                weekly_bars = self.fetch_weekly(sec)
            except Exception as e:
                source_errors["weekly"] = str(e)
        if include_monthly:
            try:
                monthly_bars = self.fetch_monthly(sec)
            except Exception as e:
                source_errors["monthly"] = str(e)
        data_status = "full" if (daily_bars and quote) else "partial" if (daily_bars or quote) else "failed"
        res_snap = MarketSnapshot(
            security=sec, quote=quote, daily_bars=daily_bars, bars_5m=bars_5m, weekly_bars=weekly_bars, monthly_bars=monthly_bars,
            tick_data=tick_data, data_status=data_status, source_errors=source_errors,
        )
        return _enrich_snapshot(res_snap)


# ═══════════════════════════════════════════════
# Tushare provider (primary source when token available)
# ═══════════════════════════════════════════════

class TushareProvider:
    """Tushare Pro 数据提供器（主源）。日线/行情/资金流/板块/筹码走 Tushare；分钟线 fallback 到 light_data。"""

    name = "tushare"

    def __init__(self):
        from trader_shared.tushare_client import get_client
        self._client = get_client()
        # fallback provider for minute data (Tushare doesn't have minute K-lines)
        self._fallback = UnifiedProvider(backend="tencent")

    def resolve_security(self, target: str) -> Security:
        return self._fallback.resolve_security(target)

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        records = self._client.query_realtime(sec.ts_code)
        if records:
            r = records[0]
            pre_close = r.get("PRE_CLOSE")
            price = r.get("PRICE")
            change_pct = None
            if pre_close and price and float(pre_close) > 0:
                change_pct = round((float(price) - float(pre_close)) / float(pre_close) * 100, 2)
            # trade_date: 尝试从 Tushare 字段提取, 兜底取今日(盘中 quote 就是在今天获取的)
            _td = None
            for _key in ("date", "DATE", "trade_date", "TRADE_DATE"):
                _td = r.get(_key)
                if _td:
                    break
            if _td:
                _td_str = str(_td)[:10]
                if len(_td_str) == 8 and _td_str.isdigit():  # YYYYMMDD → YYYY-MM-DD
                    _td_str = f"{_td_str[:4]}-{_td_str[4:6]}-{_td_str[6:8]}"
            else:
                _td_str = datetime.now().strftime("%Y-%m-%d")
            return {
                "name": r.get("NAME", sec.name),
                "symbol": sec.code,
                "trade_date": _td_str,
                "current_price": float(price) if price else None,
                "current_change_pct": change_pct,
                "high": float(r.get("HIGH")) if r.get("HIGH") else None,
                "low": float(r.get("LOW")) if r.get("LOW") else None,
                "volume": float(r.get("VOLUME")) if r.get("VOLUME") else None,
                "amount": float(r.get("AMOUNT")) if r.get("AMOUNT") else None,
                "pre_close": float(pre_close) if pre_close else None,
            }
        return self._fallback.fetch_quote(sec)

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        from trader_shared.light_data import _compute_atr_fields
        from datetime import timedelta

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        records = self._client.query_daily(sec.ts_code, start_date=start_date, end_date=end_date)
        if not records:
            return self._fallback.fetch_qfq_daily(sec, days)

        bars: list[dict[str, Any]] = []
        for r in records:
            trade_date = str(r.get("trade_date", ""))
            # Tushare returns YYYYMMDD, convert to YYYY-MM-DD
            if len(trade_date) == 8:
                trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            bars.append({
                "date": trade_date,
                "open": float(r["open"]) if r.get("open") is not None else None,
                "close": float(r["close"]) if r.get("close") is not None else None,
                "high": float(r["high"]) if r.get("high") is not None else None,
                "low": float(r["low"]) if r.get("low") is not None else None,
                "volume": float(r["vol"]) if r.get("vol") is not None else None,
                "amount": float(r["amount"]) if r.get("amount") is not None else None,
                "data_source": "tushare",
                "data_status": "full",
            })
        _compute_atr_fields(bars)
        return bars

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_5m(sec, datalen)

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_15m(sec, datalen)

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_30m(sec, datalen)

    def fetch_weekly(self, sec: Security, datalen: int = 80) -> list[dict[str, Any]]:
        """周线 — fallback 到腾讯（Tushare 周线需高级积分）。"""
        return self._fallback.fetch_weekly(sec, datalen)

    def fetch_monthly(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """月线 — fallback 到腾讯（Tushare 月线需高级积分）。"""
        return self._fallback.fetch_monthly(sec, datalen)

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        return self._fallback.fetch_kline(sec, scale, datalen)

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        return self._fallback.fetch_ticks(sec, count)

    def pct_change(self, start: float, end: float) -> float:
        return self._fallback.pct_change(start, end)

    def to_float(self, value: Any) -> float | None:
        return self._fallback.to_float(value)

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._fallback.normalize_bars(raw_bars)

    def load_market_snapshot(
        self, target: str, days: int = 365,
        include_5m: bool = True, include_weekly: bool = True,
        include_monthly: bool = True, include_ticks: bool = True,
    ) -> MarketSnapshot:
        sec = self.resolve_security(target)
        daily_bars: list[dict[str, Any]] = []
        bars_5m: list[dict[str, Any]] = []
        weekly_bars: list[dict[str, Any]] = []
        monthly_bars: list[dict[str, Any]] = []
        quote: dict[str, Any] = {}
        tick_data: list[dict[str, Any]] = []
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
        if include_weekly:
            try:
                weekly_bars = self.fetch_weekly(sec)
            except Exception as e:
                source_errors["weekly"] = str(e)
        if include_monthly:
            try:
                monthly_bars = self.fetch_monthly(sec)
            except Exception as e:
                source_errors["monthly"] = str(e)
        if include_ticks:
            try:
                tick_data = self.fetch_ticks(sec)
            except Exception as e:
                source_errors["ticks"] = str(e)

        data_status: DataStatus = (
            "full" if (daily_bars and quote)
            else "partial" if (daily_bars or quote)
            else "failed"
        )
        res_snap = MarketSnapshot(
            security=sec, quote=quote, daily_bars=daily_bars,
            bars_5m=bars_5m, weekly_bars=weekly_bars, monthly_bars=monthly_bars,
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

    # Tushare 主源（当 token 可用时默认启用）
    try:
        from trader_shared.tushare_client import get_client as _get_ts_client
        if _get_ts_client().available:
            _provider = TushareProvider()
            print("DataProvider: using tushare (primary source)", file=sys.stderr)
            return _provider
    except (ImportError, Exception):
        pass

    provider_name = os.environ.get("TRADER_DATA_PROVIDER", "").lower()
    if provider_name in ("mootdx", "akshare"):
        _provider = UnifiedProvider(backend=provider_name)
        print(f"DataProvider: using {provider_name} (via TRADER_DATA_PROVIDER)", file=sys.stderr)
        return _provider

    _provider = UnifiedProvider(backend="tencent")
    print(f"DataProvider: using tencent", file=sys.stderr)
    return _provider


def set_provider(p: DataProvider) -> None:
    """Replace the global data source with a custom implementation.

    仅设置模块级 _provider 单例，不再回写 os.environ，
    避免运行时全局副作用（并行/测试不可复现）。get_provider() 优先读 _provider。
    """
    global _provider
    _provider = p
