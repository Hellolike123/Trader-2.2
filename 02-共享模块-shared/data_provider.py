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
from pathlib import Path
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

# -------- inject shared paths so we can import light_data / models --------
_shared = Path(__file__).resolve().parents[1]
_market_data = _shared / "01-行情数据-market-data"

DataStatus = Literal["complete", "partial", "degraded", "failed"]


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
    data_status: DataStatus = "complete"
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


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

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True) -> MarketSnapshot:
        """Aggregate quote + daily + optional 5m into a single snapshot."""
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
        self._ensure_paths()
        if self._http is None:
            from light_data import HttpClient
            self._http = HttpClient()
        from light_data import fetch_qfq_daily as _fetch
        from light_data import Security as _Sec
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, days=days)

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
        return _fetch(_Sec(sec.code, sec.market, sec.name), self._http, scale=scale, datalen=datalen)

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True) -> MarketSnapshot:
        self._ensure_paths()
        from light_data import load_market_snapshot as _load
        from light_data import MarketSnapshot as _MS
        snap = _load(target, days=days, include_5m=include_5m)
        sec = Security(code=snap.security.code, market=snap.security.market, name=snap.security.name)
        return MarketSnapshot(
            security=sec,
            quote=snap.quote,
            daily_bars=snap.daily_bars,
            bars_5m=snap.bars_5m,
            data_status=snap.data_status,
            missing_sources=snap.missing_sources,
            source_errors=snap.source_errors,
            fetched_at=snap.fetched_at,
        )

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
        global _provider_set
        import os
        provider_set = os.environ.get("TRADER_DATA_PROVIDER", "")
        if provider_set:
            _provider_set = True

    @property
    def name(self) -> str:
        return "akshare"

    def resolve_security(self, target: str) -> Security:
        from light_data import resolve_security as _resolve
        sec = _resolve(target)
        return Security(code=sec.code, market=sec.market, name=sec.name)

    def _to_standard_bar(self, row: dict[str, Any], dt_key: str = "date") -> dict[str, Any] | None:
        """Convert a raw bar from akshare to standard dict format."""
        close = to_float(str(row.get("close")) if isinstance(row.get("close"), (str, int, float)) else None)
        if close is None:
            return None
        return {
            "date": row.get(dt_key, ""),
            "open": to_float(row.get("open")),
            "close": close,
            "high": to_float(row.get("high")),
            "low": to_float(row.get("low")),
            "volume": to_float(row.get("vol") or row.get("volume")),
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

        # akshare 的 ts_code 格式: 600519.SH
        ts_code = sec.ts_code
        end_date = ""
        if days:
            from datetime import timedelta
            end_date = (pd.Timestamp.today() - timedelta(days=days)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(
            symbol=sec.code,
            period="daily",
            start_date=end_date,
            end_date="",
            adjust="qfq",
        )

        bars: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            bar = self._to_standard_bar(row.to_dict())
            if bar:
                bars.append(bar)

        # 附加 ATR 字段（复用 light_data 的逻辑）
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
        for _, row in df.head(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_15m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period="15")
        bars: list[dict[str, Any]] = []
        for _, row in df.head(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def fetch_30m(self, sec: Security, datalen: int = 60) -> list[dict[str, Any]]:
        self._ensure_akshare()
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(symbol=sec.code, period="30")
        bars: list[dict[str, Any]] = []
        for _, row in df.head(datalen).iterrows():
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
        for _, row in df.head(datalen).iterrows():
            bar = self._to_standard_bar(row.to_dict(), dt_key="时间")
            if bar:
                bars.append(bar)
        return bars

    def load_market_snapshot(self, target: str, days: int = 365, include_5m: bool = True) -> MarketSnapshot:
        sec = self.resolve_security(target)
        daily_bars, bars_5m, quote = [], [], {}
        try:
            daily_bars = self.fetch_qfq_daily(sec, days=days)
        except Exception as e:
            daily_bars = []
        try:
            quote = self.fetch_quote(sec)
        except Exception:
            quote = {}
        if include_5m:
            try:
                bars_5m = self.fetch_5m(sec)
            except Exception:
                bars_5m = []

        if daily_bars and quote:
            data_status = "complete"
        elif daily_bars or quote:
            data_status = "partial"
        else:
            data_status = "failed"

        return MarketSnapshot(
            security=sec,
            quote=quote,
            daily_bars=daily_bars,
            bars_5m=bars_5m,
            data_status=data_status,
        )

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
    return TencentSinaProvider()


def get_provider() -> DataProvider:
    """Return the current DataProvider instance (lazy init via TRADER_DATA_PROVIDER env var)."""
    global _provider
    if _provider is not None:
        return _provider

    provider_name = os.environ.get("TRADER_DATA_PROVIDER", "").lower()
    if provider_name == "akshare":
        try:
            _provider = AkShareProvider()
            return _provider
        except RuntimeError:
            _provider = _init_provider()
            return _provider
    _provider = _init_provider()
    return _provider


def set_provider(p: DataProvider) -> None:
    """Replace the global data source with a custom implementation."""
    import os
    global _provider
    _provider = p
    os.environ["TRADER_DATA_PROVIDER"] = p.name
