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

def _enrich_snapshot(snap: MarketSnapshot) -> MarketSnapshot:
    """Enrich the MarketSnapshot with extend_fundamental and extend_sentiment using a thread pool."""
    sec = snap.security
    if not sec or not sec.code or len(sec.code) != 6 or not sec.code.isdigit():
        return snap
        
    try:
        from trader_shared.extend_data import ExtendDataProvider
        from concurrent.futures import ThreadPoolExecutor
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_sh = executor.submit(ExtendDataProvider.get_shareholder_trend, sec.code)
            f_eps = executor.submit(ExtendDataProvider.get_ths_consensus_eps, sec.code)
            f_unlocks = executor.submit(ExtendDataProvider.get_upcoming_unlocks, sec.code)
            f_hot = executor.submit(ExtendDataProvider.get_ths_hot_reason_for_stock, sec.code)
            
            sh_trend = f_sh.result(timeout=4.0)
            ths_eps = f_eps.result(timeout=4.0)
            unlocks = f_unlocks.result(timeout=4.0)
            hot_reason = f_hot.result(timeout=4.0)
            
            extend_fundamental = {
                "shareholder": sh_trend,
                "consensus_eps": ths_eps
            }
            extend_sentiment = {
                "unlocks": unlocks,
                "theme_harden": hot_reason
            }
            
            import dataclasses
            return dataclasses.replace(
                snap,
                extend_fundamental=extend_fundamental,
                extend_sentiment=extend_sentiment
            )
    except Exception as e:
        import sys
        print(f"📡 [DataProvider-Enrich-Warn]: Failed to enrich snapshot with advanced metrics: {e}", file=sys.stderr)
        return snap


class MootdxProvider:
    """Mootdx-backed implementation using light_data.py mootdx-priority functions."""

    def __init__(self) -> None:
        self._http = None

    @property
    def name(self) -> str:
        return "mootdx"

    def _ensure_paths(self) -> None:
        _market = _market_data
        _candidate = _shared / "02-候选逻辑-candidate"
        for _p in (_market, _candidate):
            if str(_p) not in sys.path:
                sys.path.insert(0, str(_p))

    def resolve_security(self, target: str) -> Security:
        self._ensure_paths()
        from light_data import resolve_security as _resolve
        sec = _resolve(target)
        return Security(code=sec.code, market=sec.market, name=sec.name)

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_quote as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http)

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        from trader_shared.cache_utils import get_cached, set_cached, TTL_DAILY
        cached = get_cached("daily", sec.code, ttl=TTL_DAILY)
        if cached is not None:
            return cached
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_qfq_daily as _fetch
        from light_data import Security as _Sec
        bars = _fetch(_Sec(sec.code, sec.market, sec.name), self._http, days=days)
        set_cached("daily", sec.code, bars)
        return bars

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_5m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_15m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_30m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_kline as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, interval=scale, datalen=datalen)

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import Security as _Sec
        try:
            from light_data import _fetch_ticks_tdx3
            res = _fetch_ticks_tdx3(_Sec(sec.code, sec.market, sec.name), count=count)
            return res if res is not None else []
        except ImportError:
            return []

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        self._ensure_paths()
        from light_data import load_market_snapshot as _load
        from light_data import MarketSnapshot as _MS
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
            missing_sources=snap.missing_sources,
            source_errors=snap.source_errors,
            fetched_at=snap.fetched_at,
        )
        return _enrich_snapshot(res_snap)

    def pct_change(self, start: float, end: float) -> float:
        self._ensure_paths()
        from light_data import pct_change as _fn
        return _fn(start, end)

    def to_float(self, value: Any) -> float | None:
        self._ensure_paths()
        from light_data import to_float as _fn
        return _fn(value)

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._ensure_paths()
        from light_data import normalize_bars as _fn
        return _fn(raw_bars)


class TencentSinaProvider:
    """Default implementation using the existing light_data.py module."""

    def __init__(self) -> None:
        self._http = None

    @property
    def name(self) -> str:
        return "tencent-sina"

    def _ensure_paths(self) -> None:
        _market = _market_data
        _candidate = _shared / "02-候选逻辑-candidate"
        for _p in (_market, _candidate):
            if str(_p) not in sys.path:
                sys.path.insert(0, str(_p))

    def resolve_security(self, target: str) -> Security:
        self._ensure_paths()
        from light_data import resolve_security as _resolve
        sec = _resolve(target)
        return Security(code=sec.code, market=sec.market, name=sec.name)

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_quote as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http)

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        from trader_shared.cache_utils import get_cached, set_cached, TTL_DAILY
        cached = get_cached("daily", sec.code, ttl=TTL_DAILY)
        if cached is not None:
            return cached
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_qfq_daily as _fetch
        from light_data import Security as _Sec
        bars = _fetch(_Sec(sec.code, sec.market, sec.name), self._http, days=days)
        set_cached("daily", sec.code, bars)
        return bars

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_5m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_15m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_30m as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, datalen=datalen)

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_kline as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, interval=scale, datalen=datalen)

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        return []

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
        self._ensure_paths()
        from light_data import load_market_snapshot as _load
        from light_data import MarketSnapshot as _MS
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
            missing_sources=snap.missing_sources,
            source_errors=snap.source_errors,
            fetched_at=snap.fetched_at,
        )
        return _enrich_snapshot(res_snap)

    def pct_change(self, start: float, end: float) -> float:
        self._ensure_paths()
        from light_data import pct_change as _fn
        return _fn(start, end)

    def to_float(self, value: Any) -> float | None:
        self._ensure_paths()
        from light_data import to_float as _fn
        return _fn(value)

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._ensure_paths()
        from light_data import normalize_bars as _fn
        return _fn(raw_bars)


# ═══════════════════════════════════════════════
# AkShare provider (optional, requires akshare)
# ═══════════════════════════════════════════════


class AkShareProvider:
    """Provider backed by akshare library.

    Usage:
        from trader_shared.data_provider import get_provider_set_from_env
        # Then all code that imports from light_data can remain unchanged;
        # the env var just affects future imports.
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "akshare"

    def resolve_security(self, target: str) -> Security:
        from light_data import resolve_security as _resolve
        sec = _resolve(target)
        return Security(code=sec.code, market=sec.market, name=sec.name)

    def _to_standard_bar(self, row: dict[str, Any], dt_key: str = "date") -> dict[str, Any] | None:
        """Convert a raw bar from akshare to standard dict format.

        AkShare stock_zh_a_hist returns Chinese column names:
            日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 换手率 ...
        AkShare stock_zh_a_hist_min_em returns Chinese column names too:
            时间, 开盘, 收盘, 最高, 最低, 成交量, 成交额 ...
        Always try Chinese names first, then fall back to English.
        """
        # Chinese column names (akshare standard)
        close = to_float(row.get("收盘") or row.get("close"))
        if close is None:
            return None
        # 日期: 日线用"日期", 分钟线用 dt_key（如"时间"）
        date_val = str(row.get("日期") or row.get(dt_key, ""))
        return {
            "date": date_val.split(" ")[0] if " " in date_val else date_val,
            "time": date_val,   # review_core bar_time() 需要读这个
            "open": to_float(row.get("开盘") or row.get("open")),
            "close": close,
            "high": to_float(row.get("最高") or row.get("high")),
            "low": to_float(row.get("最低") or row.get("low")),
            "volume": to_float(row.get("成交量") or row.get("vol") or row.get("volume")),
            "amount": to_float(row.get("成交额") or row.get("amount")),
        }



    def _ensure_akshare(self) -> None:
        try:
            import akshare  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "akshare 未安装。请运行: pip install akshare"
            )

    def fetch_qfq_daily(self, sec: Security, days: int = 30) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        import pandas as pd

        start_date = ""
        if days:
            from datetime import timedelta
            start_date = (pd.Timestamp.today() - timedelta(days=days)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(
            symbol=sec.code,
            period="daily",
            start_date=start_date,
            end_date="",
            adjust="qfq",
        )

        bars: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            bar = self._to_standard_bar(row.to_dict())
            if bar:
                bars.append(bar)

        # 附加 ATR 字段（复用 light_data 的逻辑）
        from light_data import _compute_atr_fields
        _compute_atr_fields(bars)
        return bars

    def fetch_quote(self, sec: Security) -> dict[str, Any]:
        self._ensure_akshare()
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

    def fetch_5m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period="5")
        bars: list[dict[str, Any]] = []
        for _, row in df.tail(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period="15")
        bars: list[dict[str, Any]] = []
        for _, row in df.tail(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period="30")
        bars: list[dict[str, Any]] = []
        for _, row in df.tail(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_kline(self, sec: Security, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        period_map = {"5": "5", "15": "15", "30": "30", "60": "60"}
        period = period_map.get(scale, "5")
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period=period)
        bars: list[dict[str, Any]] = []
        for _, row in df.tail(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_ticks(self, sec: Security, count: int = 500) -> list[dict[str, Any]]:
        return []

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True, include_ticks: bool = True) -> MarketSnapshot:
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
        if include_ticks:
            try:
                tick_data = self.fetch_ticks(sec, count=500)
            except Exception as e:
                source_errors["ticks"] = str(e)

        if daily_bars and quote:
            data_status = "full"
        elif daily_bars or quote:
            data_status = "partial"
        else:
            data_status = "failed"

        res_snap = MarketSnapshot(
            security=sec,
            quote=quote,
            daily_bars=daily_bars,
            bars_5m=bars_5m,
            tick_data=tick_data,
            data_status=data_status,
            source_errors=source_errors,
        )
        return _enrich_snapshot(res_snap)

    def pct_change(self, start: float, end: float) -> float:
        from light_data import pct_change as _fn
        return _fn(start, end)

    def to_float(self, value: Any) -> float | None:
        from light_data import to_float as _fn
        return _fn(value)

    def normalize_bars(self, raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from light_data import normalize_bars as _fn
        return _fn(raw_bars)


# ═══════════════════════════════════════════════
# Global provider registry
# ═══════════════════════════════════════════════

_provider: DataProvider | None = None
_provider_set = False


def _init_provider() -> DataProvider:
    try:
        return TencentSinaProvider()
    except Exception:
        try:
            return MootdxProvider()
        except Exception:
            return TencentSinaProvider()


def get_provider() -> DataProvider:
    """Return the current DataProvider instance (lazy init via TRADER_DATA_PROVIDER env var)."""
    global _provider
    if _provider is not None:
        return _provider

    provider_name = os.environ.get("TRADER_DATA_PROVIDER", "").lower()
    if provider_name == "mootdx":
        try:
            _provider = MootdxProvider()
            print(f"DataProvider: using mootdx (via TRADER_DATA_PROVIDER=mootdx)", file=sys.stderr)
            return _provider
        except Exception as e:
            warnings.warn(f"[data_provider] TRADER_DATA_PROVIDER=mootdx 创建失败: {e}，静默降级", stacklevel=2)
    if provider_name == "akshare":
        try:
            _provider = AkShareProvider()
            print(f"DataProvider: using akshare (via TRADER_DATA_PROVIDER=akshare)", file=sys.stderr)
            return _provider
        except RuntimeError as e:
            warnings.warn(f"[data_provider] TRADER_DATA_PROVIDER=akshare 创建失败: {e}，静默降级", stacklevel=2)
    _provider = _init_provider()
    source_name = _provider.name
    print(f"DataProvider: using {source_name}", file=sys.stderr)
    return _provider


def set_provider(p: DataProvider) -> None:
    """Replace the global data source with a custom implementation."""
    import os
    global _provider
    _provider = p
    os.environ["TRADER_DATA_PROVIDER"] = p.name
