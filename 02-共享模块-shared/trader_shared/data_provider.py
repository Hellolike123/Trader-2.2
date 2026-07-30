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
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from trader_shared._logging import get_logger
from trader_shared.light_data import to_float
from trader_shared.market_types import DataStatus, MarketSnapshot, Security

_logger = get_logger(__name__)


def _weekly_datalen(datalen: int | None = None) -> int:
    """周线默认根数：中线缠论成笔/成段需要足够历史（见 config.WEEKLY_LOOKBACK_BARS）。"""
    if datalen is not None and datalen > 0:
        return int(datalen)
    try:
        from trader_shared.config import WEEKLY_LOOKBACK_BARS
        return int(WEEKLY_LOOKBACK_BARS)
    except Exception:
        return 260


# -------- inject shared paths so we can import light_data / models --------
_shared = Path(__file__).resolve().parents[1]


# Security / MarketSnapshot / DataStatus → market_types（SSOT）


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

    def fetch_weekly(self, sec: Security, datalen: int | None = None) -> list[dict[str, Any]]:
        """Weekly K-line bars（默认 WEEKLY_LOOKBACK_BARS，供中线缠论）。"""
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


def _enrich_payload_useful(*parts: Any) -> bool:
    """扩展字段是否含真实载荷（全 None / 空 dict 不算成功）。"""

    def _useful(x: Any) -> bool:
        if x is None:
            return False
        if isinstance(x, dict):
            return any(_useful(v) for v in x.values())
        if isinstance(x, (list, tuple, set)):
            return len(x) > 0
        if isinstance(x, str):
            return bool(x.strip())
        return True

    return any(_useful(p) for p in parts)


def _enrich_snapshot(snap: MarketSnapshot) -> MarketSnapshot:
    """Enrich the MarketSnapshot with extend_fundamental, extend_sentiment,
    extend_margin, extend_northbound, extend_sector using a thread pool.

    三层缓存策略:
    1. 文件缓存 (TTL 12小时) — 盘后预缓存的数据，进程重启不丢失
    2. 内存缓存 (TTL 10分钟) — 同一进程内快速命中
    3. 实时抓取 — 缓存全部 miss 时走 8 路 API（4 原有 + 3 Phase 1 + 1 Phase 2 概念）

    环境变量 ``TRADER_SNAPSHOT_ENRICH=0`` 时跳过扩展字段（短中线热路径可加速）。
    """
    _enrich_flag = os.environ.get("TRADER_SNAPSHOT_ENRICH", "1").strip().lower()
    if _enrich_flag in ("0", "false", "no", "off"):
        return snap
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
        # stale=True（TTL 过期）不视为命中，往下实时抓取，避免陈旧基本面被永久当真
        if file_cached is not None and isinstance(file_cached, dict) and not _cached_result.stale:
            extend_fundamental = file_cached.get("extend_fundamental", {})
            extend_sentiment = file_cached.get("extend_sentiment", {})
            extend_margin = file_cached.get("extend_margin")
            extend_northbound = file_cached.get("extend_northbound")
            extend_sector = file_cached.get("extend_sector")
            extend_concept = file_cached.get("extend_concept")
            if _enrich_payload_useful(
                extend_fundamental,
                extend_sentiment,
                extend_margin,
                extend_northbound,
                extend_sector,
                extend_concept,
            ):
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

    # ── 层3: 实时抓取（8 路并行） ──
    # 用独立小池 max_workers=4（勿用 get_shared_build_pool）：
    # refresh 已占用共享池时，再 submit+wait 同一池会死锁。
    try:
        from trader_shared.extend_data import ExtendDataProvider
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="trader-enrich") as executor:
            # 原有 4 路 + Phase1 3 路 + Phase2 概念
            f_sh = executor.submit(ExtendDataProvider.get_shareholder_trend, sec.code)
            f_eps = executor.submit(ExtendDataProvider.get_ths_consensus_eps, sec.code)
            f_unlocks = executor.submit(ExtendDataProvider.get_upcoming_unlocks, sec.code)
            f_hot = executor.submit(ExtendDataProvider.get_ths_hot_reason_for_stock, sec.code)
            f_margin = executor.submit(ExtendDataProvider.get_margin_data, sec.code)
            f_north = executor.submit(ExtendDataProvider.get_northbound_flow)
            f_sector = executor.submit(ExtendDataProvider.get_sector_data, sec.code)
            f_concept = executor.submit(ExtendDataProvider.get_concept_data, sec.code)

            def _res(fut, timeout: float = 2.0):
                try:
                    return fut.result(timeout=timeout)
                except Exception:
                    return None

            sh_trend = _res(f_sh)
            ths_eps = _res(f_eps)
            unlocks = _res(f_unlocks)
            hot_reason = _res(f_hot)
            margin_data = _res(f_margin)
            northbound_data = _res(f_north)
            sector_data = _res(f_sector)
            concept_data = _res(f_concept)

            extend_fundamental = {
                "shareholder": sh_trend,
                "consensus_eps": ths_eps,
            }
            extend_sentiment = {
                "unlocks": unlocks,
                "theme_harden": hot_reason,
            }

            # 超时/全空不落盘：禁止把 None 壳缓存 12h 冒充成功
            if not _enrich_payload_useful(
                extend_fundamental,
                extend_sentiment,
                margin_data,
                northbound_data,
                sector_data,
                concept_data,
            ):
                _logger.debug("Enrich empty/timeout for %s, skip cache", sec.code)
                return snap

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
        # 与 Tushare/light_data 统一：日 scoped + {fetch_date, rows}，禁止裸 list 脏读
        from trader_shared.cache_utils import CACHE_DAILY, get_day_scoped_bars

        self._ensure_http()
        from trader_shared.light_data import fetch_qfq_daily as _fetch

        http = self._http
        ld_sec = self._to_sec(sec)

        def _net() -> list:
            return list(_fetch(ld_sec, http, days=days) or [])

        return get_day_scoped_bars(CACHE_DAILY, sec.code, _net, min_rows=min(20, max(days, 1)))

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

    def fetch_weekly(self, sec: Security, datalen: int | None = None) -> list[dict[str, Any]]:
        """Fetch weekly K-line bars via mootdx or kline endpoint."""
        n = _weekly_datalen(datalen)
        if self._backend == "akshare":
            return self._akshare_fetch_kline(sec, "weekly", n)
        self._ensure_http()
        from trader_shared.light_data import fetch_kline as _fetch
        return _fetch(self._to_sec(sec), self._http, interval="weekly", datalen=n)

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
        snap = _load(
            target,
            days=days,
            include_5m=include_5m,
            include_weekly=include_weekly,
            include_monthly=include_monthly,
            include_ticks=include_ticks,
        )
        # light_data 与本模块共用 market_types.MarketSnapshot，无需 copy-convert
        if isinstance(snap, MarketSnapshot):
            return _enrich_snapshot(snap)
        # 兼容旧快照对象（缺字段时再组装）
        sec = Security(
            code=snap.security.code,
            market=getattr(snap.security, "market", "") or "",
            name=getattr(snap.security, "name", "") or "",
        )
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
        from trader_shared.light_data import _compute_atr_fields, ensure_bars_ascending
        fixed, rewritten = ensure_bars_ascending(bars)
        # ensure_bars_ascending 仅在重排时重算 ATR；AkShare 常已升序，须显式补算
        if not rewritten:
            _compute_atr_fields(fixed)
        for b in fixed:
            b.setdefault("data_source", "akshare")
            b.setdefault("adjust", "qfq")
            b.setdefault("data_status", "full")
        return fixed

    def _akshare_fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        self._akshare_ensure()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period=scale)
        # 先正序再取尾部，避免源倒序时 tail 截到最旧
        try:
            if "时间" in df.columns:
                df = df.sort_values("时间", ascending=True)
        except Exception:
            pass
        bars = [bar for _, row in df.tail(datalen).iterrows() if (bar := self._akshare_to_bar(row.to_dict(), dt_key="时间"))]
        from trader_shared.light_data import ensure_bars_ascending
        fixed, _ = ensure_bars_ascending(bars, recompute_atr=False)
        return fixed

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
        from trader_shared.light_data import ensure_bars_ascending
        daily_bars, _ = ensure_bars_ascending(daily_bars)
        weekly_bars, _ = ensure_bars_ascending(weekly_bars)
        monthly_bars, _ = ensure_bars_ascending(monthly_bars)
        bars_5m, _ = ensure_bars_ascending(bars_5m, recompute_atr=False)
        res_snap = MarketSnapshot(
            security=sec, quote=quote, daily_bars=daily_bars, bars_5m=bars_5m, weekly_bars=weekly_bars, monthly_bars=monthly_bars,
            tick_data=tick_data, data_status=data_status, source_errors=source_errors,
        )
        return _enrich_snapshot(res_snap)


# ═══════════════════════════════════════════════
# Tushare provider (primary source when token available)
# ═══════════════════════════════════════════════

class TushareProvider:
    """Tushare Pro 数据提供器（主源）。

    日线/周线/资金流/板块/筹码走 Tushare；**实时现价优先腾讯**（公开盘口更稳），
    仅腾讯失败时才降级到 Tushare realtime 爬虫。分钟线仍走 light_data。
    """

    name = "tushare"

    def __init__(self):
        from trader_shared.tushare_client import get_client
        self._client = get_client()
        # fallback：腾讯实时 + 分钟线（Tushare 无分钟 K）
        self._fallback = UnifiedProvider(backend="tencent")

    def resolve_security(self, target: str) -> Security:
        return self._fallback.resolve_security(target)

    @staticmethod
    def _map_tushare_realtime_record(r: dict[str, Any], sec: Security) -> dict[str, Any]:
        """把 realtime_quote 一行映射成统一 quote 字段（降级用）。"""
        pre_close = r.get("PRE_CLOSE")
        price = r.get("PRICE")
        change_pct = None
        if pre_close and price and float(pre_close) > 0:
            change_pct = round((float(price) - float(pre_close)) / float(pre_close) * 100, 2)
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
            "data_source": "tushare-realtime",
            "data_status": "partial",  # 爬虫源：字段/时效弱于腾讯盘口
        }

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        """实时现价：腾讯第一；仅腾讯无有效价时才用 Tushare realtime 爬虫。

        不做双源同时请求：腾讯成功即返回，避免多一次爬虫 RTT 与限流。
        日线/周线等仍走 Tushare，与现价解耦。
        """
        from trader_shared.light_data import sanitize_quote

        tencent_q: dict[str, Any] = {}
        try:
            tencent_q = self._fallback.fetch_quote(sec) or {}
        except Exception as e:
            _logger.debug("tencent quote failed for %s: %s", sec.code, e)
            tencent_q = {}

        tencent_price = to_float(tencent_q.get("current_price")) if tencent_q else None
        if tencent_price is not None and tencent_price > 0:
            return sanitize_quote(tencent_q) or tencent_q

        # 腾讯失败：降级 Tushare 爬虫
        records = self._client.query_realtime(sec.ts_code)
        if records:
            mapped = self._map_tushare_realtime_record(records[0], sec)
            _logger.warning(
                "quote fallback to tushare-realtime for %s (tencent empty/invalid)",
                sec.code,
            )
            return sanitize_quote(mapped) or mapped
        return tencent_q if isinstance(tencent_q, dict) else {}

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        from trader_shared.light_data import _compute_atr_fields
        from datetime import timedelta
        from trader_shared.cache_utils import get_day_scoped_bars, CACHE_DAILY

        def _net() -> list[dict[str, Any]]:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            records = self._client.query_daily(
                sec.ts_code, start_date=start_date, end_date=end_date
            )
            if not records:
                return self._fallback.fetch_qfq_daily(sec, days)

            bars: list[dict[str, Any]] = []
            def _safe_float(v, mul=1.0):
                """安全转换 Tushare 字段，兜底 None/空/脏字符串。"""
                if v is None:
                    return None
                try:
                    return float(v) * mul
                except (TypeError, ValueError):
                    return None
            # Tushare daily 常倒序；正序后再算 ATR（昨收=前一根）
            for r in sorted(records, key=lambda x: str(x.get("trade_date", ""))):
                trade_date = str(r.get("trade_date", ""))
                # Tushare returns YYYYMMDD, convert to YYYY-MM-DD
                if len(trade_date) == 8:
                    trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                # Tushare daily amount 单位为千元 → 统一成元（与腾讯/mootdx 一致）
                _amt = _safe_float(r.get("amount"), 1000.0)
                bars.append({
                    "date": trade_date,
                    "open": _safe_float(r.get("open")),
                    "close": _safe_float(r.get("close")),
                    "high": _safe_float(r.get("high")),
                    "low": _safe_float(r.get("low")),
                    "volume": _safe_float(r.get("vol")),
                    "amount": _amt,
                    "data_source": "tushare",
                    "data_status": "full",
                    # 代理 daily 不接受 adj：价格为未复权；ATR 与策略价同源
                    "adjust": "none",
                })
            _compute_atr_fields(bars)
            return bars

        # 日 K：当天第一次打网，同日复用；出口正序由 get_day_scoped_bars 统一保证
        return get_day_scoped_bars(
            CACHE_DAILY, sec.code, _net, min_rows=min(50, max(days // 3, 20))
        )

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_5m(sec, datalen)

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_15m(sec, datalen)

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        """Tushare 不提供分钟线，fallback 到腾讯。"""
        return self._fallback.fetch_30m(sec, datalen)

    def fetch_weekly(self, sec: Security, datalen: int | None = None) -> list[dict[str, Any]]:
        """周线：优先 Tushare weekly（代理可用时），失败再 fallback 新浪/腾讯。

        默认根数 WEEKLY_LOOKBACK_BARS，避免 80 周过短导致中线缠论「笔数不足」。
        当天第一次打网，同日复用。
        """
        n = _weekly_datalen(datalen)
        from trader_shared.cache_utils import get_day_scoped_bars, CACHE_WEEKLY

        def _net() -> list[dict[str, Any]]:
            try:
                from datetime import timedelta
                from trader_shared.light_data import _compute_atr_fields

                end_date = datetime.now().strftime("%Y%m%d")
                # 周线：根数 * 7 天再加缓冲，保证能取满 n 根
                start_date = (datetime.now() - timedelta(days=max(n * 8, 400))).strftime("%Y%m%d")
                records = self._client.query(
                    "weekly",
                    ts_code=sec.ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if records and len(records) >= 4:
                    def _sf(v, mul=1.0):
                        if v is None:
                            return None
                        try:
                            return float(v) * mul
                        except (TypeError, ValueError):
                            return None
                    bars: list[dict[str, Any]] = []
                    for r in sorted(records, key=lambda x: str(x.get("trade_date", ""))):
                        trade_date = str(r.get("trade_date", ""))
                        if len(trade_date) == 8 and trade_date.isdigit():
                            trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                        bars.append({
                            "date": trade_date,
                            "open": _sf(r.get("open")),
                            "close": _sf(r.get("close")),
                            "high": _sf(r.get("high")),
                            "low": _sf(r.get("low")),
                            "volume": _sf(r.get("vol")),
                            "amount": _sf(r.get("amount"), 1000.0),
                            "data_source": "tushare",
                            "data_status": "full",
                        })
                    if len(bars) > n:
                        bars = bars[-n:]
                    _compute_atr_fields(bars)
                    return bars
            except Exception as e:
                _logger.debug("tushare weekly failed, fallback: %s", e)
            return self._fallback.fetch_weekly(sec, n)

        return get_day_scoped_bars(CACHE_WEEKLY, sec.code, _net, min_rows=4)

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
        """并行拉 quote/日/周/5m（避免串行 2～3s 叠加）。

        用独立小池，禁止 get_shared_build_pool：refresh 已在该池里跑 build_report 时
        再 submit+wait 会死锁。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sec = self.resolve_security(target)
        daily_bars: list[dict[str, Any]] = []
        bars_5m: list[dict[str, Any]] = []
        weekly_bars: list[dict[str, Any]] = []
        monthly_bars: list[dict[str, Any]] = []
        quote: dict[str, Any] = {}
        tick_data: list[dict[str, Any]] = []
        source_errors: dict[str, str] = {}

        work: list[tuple[str, Any]] = [
            ("daily", lambda: self.fetch_qfq_daily(sec, days)),
            ("quote", lambda: self.fetch_quote(sec)),
        ]
        if include_5m:
            work.append(("bars_5m", lambda: self.fetch_5m(sec)))
        if include_weekly:
            work.append(("weekly", lambda: self.fetch_weekly(sec)))
        if include_monthly:
            work.append(("monthly", lambda: self.fetch_monthly(sec)))
        if include_ticks:
            work.append(("ticks", lambda: self.fetch_ticks(sec)))

        results: dict[str, Any] = {}
        with ThreadPoolExecutor(
            max_workers=min(6, len(work)), thread_name_prefix="tushare-snap"
        ) as pool:
            futs = {pool.submit(fn): key for key, fn in work}
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    results[key] = fut.result()
                except Exception as e:
                    source_errors[key] = str(e)
                    results[key] = None

        daily_bars = results.get("daily") or []
        quote = results.get("quote") or {}
        bars_5m = results.get("bars_5m") or []
        weekly_bars = results.get("weekly") or []
        monthly_bars = results.get("monthly") or []
        tick_data = results.get("ticks") or []

        # 与 light_data 一致：入口再兜正序（fetch 侧已保证，防缓存漏网）
        from trader_shared.light_data import ensure_bars_ascending
        daily_bars, _ = ensure_bars_ascending(daily_bars)
        weekly_bars, _ = ensure_bars_ascending(weekly_bars)
        monthly_bars, _ = ensure_bars_ascending(monthly_bars)
        bars_5m, _ = ensure_bars_ascending(bars_5m, recompute_atr=False)

        def _snapshot_freshness(bars: list) -> str:
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
                return compute_data_freshness(last)
            except Exception:
                return "live"

        # 与 light_data.load_market_snapshot 对齐：按分项缺失 + quote 降级判完备度
        _key_to_missing = {
            "daily": "daily",
            "quote": "quote",
            "bars_5m": "bars_5m",
            "weekly": "weekly_bars",
            "monthly": "monthly_bars",
            "ticks": "tick_data",
        }
        missing_sources: list[str] = []
        for err_key in source_errors:
            ms = _key_to_missing.get(err_key, err_key)
            if ms not in missing_sources:
                missing_sources.append(ms)
        if isinstance(quote, dict) and not quote.get("current_price"):
            if "quote" not in missing_sources:
                missing_sources.append("quote")
        if not daily_bars and "daily" not in missing_sources:
            missing_sources.append("daily")
        if include_5m and not bars_5m and "bars_5m" not in missing_sources:
            missing_sources.append("bars_5m")
        if include_weekly and not weekly_bars and "weekly_bars" not in missing_sources:
            missing_sources.append("weekly_bars")
        if include_monthly and not monthly_bars and "monthly_bars" not in missing_sources:
            missing_sources.append("monthly_bars")

        if quote and daily_bars and not missing_sources:
            if isinstance(quote, dict) and quote.get("data_status") == "partial":
                data_status: DataStatus = "partial"
            else:
                data_status = "full"
        elif quote and daily_bars:
            data_status = "partial"
        elif quote or daily_bars:
            data_status = "degraded"
        else:
            data_status = "failed"

        res_snap = MarketSnapshot(
            security=sec, quote=quote, daily_bars=daily_bars,
            bars_5m=bars_5m, weekly_bars=weekly_bars, monthly_bars=monthly_bars,
            tick_data=tick_data, data_status=data_status,
            missing_sources=missing_sources, source_errors=source_errors,
            data_freshness=_snapshot_freshness(daily_bars),
        )
        return _enrich_snapshot(res_snap)


# ═══════════════════════════════════════════════
# Global provider registry
# ═══════════════════════════════════════════════

_provider: DataProvider | None = None
_provider_set = False


def _tushare_available() -> bool:
    try:
        from trader_shared.tushare_client import get_client as _get_ts_client

        return bool(_get_ts_client().available)
    except Exception:
        return False


def _provider_from_name(name: str) -> DataProvider | None:
    """按名字构造 Provider。tdx = 本地 mootdx/pytdx 链（全量 Tdx MCP 行情尚未单立 Provider）。"""
    n = (name or "").strip().lower()
    if n == "tushare":
        if _tushare_available():
            return TushareProvider()
        _logger.warning("TRADER_DATA_PROVIDER=tushare but token unavailable")
        return None
    if n == "tdx":
        # 第一期：行情侧用 mootdx（通达信系本地源）；资金流另走 fund_flow tdx HTTP
        return UnifiedProvider(backend="mootdx")
    if n in ("mootdx", "akshare", "tencent"):
        return UnifiedProvider(backend=n)
    return None


def get_provider() -> DataProvider:
    """Return the current DataProvider instance.

    选源顺序：
    1. set_provider 注入
    2. TRADER_DATA_PROVIDER 强制（修：有 Tushare token 时也会生效）
    3. 按 TRADER_HOST / 探测：WorkBuddy 优先 tushare→mootdx→tencent（资金流另优先 tdx）
       Hermes/local：tushare→tencent
    """
    global _provider
    if _provider is not None:
        return _provider

    forced = os.environ.get("TRADER_DATA_PROVIDER", "").strip().lower()
    if forced:
        built = _provider_from_name(forced)
        if built is not None:
            _provider = built
            _logger.info("DataProvider: using %s (via TRADER_DATA_PROVIDER)", forced)
            return _provider
        _logger.warning(
            "TRADER_DATA_PROVIDER=%s unavailable; falling back to host defaults", forced
        )

    from trader_shared.trader_host import HOST_WORKBUDDY, detect_trader_host

    host = detect_trader_host()
    if _tushare_available():
        _provider = TushareProvider()
        _logger.info("DataProvider: using tushare (host=%s)", host)
        return _provider

    if host == HOST_WORKBUDDY:
        # 无 Tushare 时 WorkBuddy 走本地通达信系，再降级腾讯
        _provider = UnifiedProvider(backend="mootdx")
        _logger.info("DataProvider: using mootdx (host=workbuddy, no tushare)")
        return _provider

    _provider = UnifiedProvider(backend="tencent")
    _logger.info("DataProvider: using tencent (host=%s)", host)
    return _provider


def set_provider(p: DataProvider) -> None:
    """Replace the global data source with a custom implementation.

    仅设置模块级 _provider 单例，不再回写 os.environ，
    避免运行时全局副作用（并行/测试不可复现）。get_provider() 优先读 _provider。
    """
    global _provider
    _provider = p


def clear_provider() -> None:
    """测试用：清空全局 Provider，下次 get_provider 重新选源。"""
    global _provider
    _provider = None
