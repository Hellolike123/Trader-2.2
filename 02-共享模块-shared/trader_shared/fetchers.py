"""Concrete data fetcher implementations.

Wraps existing light_data.py functions behind the DataFetcher interface.
Enables dependency injection: consumers receive a fetcher instance instead
of importing light_data directly.

Usage:
    from trader_shared.fetchers import TencentFetcher
    fetcher = TencentFetcher()
    quote = fetcher.fetch_quote("688248")
"""
from __future__ import annotations

from typing import Any

from trader_shared.interfaces import DataFetcher


class TencentFetcher(DataFetcher):
    """Tencent HTTP API data fetcher (default, production-grade).

    Delegates to light_data.py functions which already implement:
    - Circuit breaker for fault tolerance
    - Rate limiting to prevent IP bans
    - Fallback chain (Tencent → Sina → mootdx → pytdx3)
    - File caching for daily bars
    """

    def __init__(self) -> None:
        self._http = None

    def _ensure_http(self) -> None:
        if self._http is None:
            from trader_shared.light_data import HttpClient
            self._http = HttpClient()

    def fetch_quote(self, code: str) -> dict[str, Any]:
        from trader_shared.light_data import fetch_quote, resolve_security
        self._ensure_http()
        sec = resolve_security(code)
        return fetch_quote(sec, self._http)

    def fetch_qfq_daily(self, code: str, days: int = 300) -> list[dict[str, Any]]:
        from trader_shared.light_data import fetch_qfq_daily, resolve_security
        self._ensure_http()
        sec = resolve_security(code)
        return fetch_qfq_daily(sec, self._http, days=days)

    def fetch_kline(self, code: str, scale: str = "60", datalen: int = 60) -> list[dict[str, Any]]:
        from trader_shared.light_data import fetch_kline, resolve_security
        self._ensure_http()
        sec = resolve_security(code)
        return fetch_kline(sec, self._http, datalen=datalen, interval=scale)

    @property
    def name(self) -> str:
        return "tencent"


class SinaFetcher(DataFetcher):
    """Sina HTTP API data fetcher (alternative source).

    Uses Sina's API directly for all data types.
    """

    def __init__(self) -> None:
        self._http = None

    def _ensure_http(self) -> None:
        if self._http is None:
            from trader_shared.light_data import HttpClient
            self._http = HttpClient()

    def fetch_quote(self, code: str) -> dict[str, Any]:
        # Sina doesn't have a clean quote API; fall back to Tencent
        fetcher = TencentFetcher()
        return fetcher.fetch_quote(code)

    def fetch_qfq_daily(self, code: str, days: int = 300) -> list[dict[str, Any]]:
        from trader_shared.light_data import _fetch_daily_sina, resolve_security
        sec = resolve_security(code)
        result = _fetch_daily_sina(sec, days)
        if result:
            from trader_shared.light_data import _compute_atr_fields
            _compute_atr_fields(result)
        return result or []

    def fetch_kline(self, code: str, scale: str = "60", datalen: int = 60) -> list[dict[str, Any]]:
        from trader_shared.light_data import _fetch_mins_fallback, resolve_security
        sec = resolve_security(code)
        return _fetch_mins_fallback(sec, scale, datalen) or []

    @property
    def name(self) -> str:
        return "sina"


class MockFetcher(DataFetcher):
    """Mock data fetcher for testing.

    Returns pre-configured data without any network calls.
    """

    def __init__(
        self,
        quote: dict[str, Any] | None = None,
        daily_bars: list[dict[str, Any]] | None = None,
        kline_bars: list[dict[str, Any]] | None = None,
    ) -> None:
        self._quote = quote or {}
        self._daily_bars = daily_bars or []
        self._kline_bars = kline_bars or []

    def fetch_quote(self, code: str) -> dict[str, Any]:
        return dict(self._quote)

    def fetch_qfq_daily(self, code: str, days: int = 300) -> list[dict[str, Any]]:
        return list(self._daily_bars)

    def fetch_kline(self, code: str, scale: str = "60", datalen: int = 60) -> list[dict[str, Any]]:
        return list(self._kline_bars)

    @property
    def name(self) -> str:
        return "mock"


# ── Global default fetcher (backward compatibility) ──

_default_fetcher: DataFetcher | None = None


def get_fetcher() -> DataFetcher:
    """Return the global default DataFetcher (lazy init).

    Backward compatibility: modules that don't use DI can call this.
    """
    global _default_fetcher
    if _default_fetcher is not None:
        return _default_fetcher
    _default_fetcher = TencentFetcher()
    return _default_fetcher


def set_fetcher(fetcher: DataFetcher) -> None:
    """Replace the global default DataFetcher."""
    global _default_fetcher
    _default_fetcher = fetcher
