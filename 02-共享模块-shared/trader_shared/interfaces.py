"""Abstract interfaces for data fetching and analysis plugins.

Defines the contracts that concrete implementations must follow.
Enables dependency injection for testability and extensibility.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DataFetcher(ABC):
    """Abstract interface for market data fetching.

    Concrete implementations (TencentFetcher, SinaFetcher, MockFetcher)
    provide the actual data retrieval logic. Consumers receive a DataFetcher
    instance via dependency injection instead of importing directly.
    """

    @abstractmethod
    def fetch_quote(self, code: str) -> dict[str, Any]:
        """Fetch real-time quote snapshot for a stock code.

        Args:
            code: Stock code (e.g. "688248" or "688248.SH")

        Returns:
            Dict with keys: current_price, pre_close, open, high, low,
            volume, amount, turnover_rate, current_change_pct, etc.
        """
        ...

    @abstractmethod
    def fetch_qfq_daily(self, code: str, days: int = 300) -> list[dict[str, Any]]:
        """Fetch forward-adjusted daily K-line bars.

        Args:
            code: Stock code
            days: Number of days of history to fetch

        Returns:
            List of bar dicts with keys: date, open, high, low, close, volume
        """
        ...

    @abstractmethod
    def fetch_kline(self, code: str, scale: str = "60", datalen: int = 60) -> list[dict[str, Any]]:
        """Fetch multi-cycle K-line bars (5m, 15m, 30m, 60m).

        Args:
            code: Stock code
            scale: K-line period ("5", "15", "30", "60")
            datalen: Number of bars to fetch

        Returns:
            List of bar dicts with keys: time, date, open, high, low, close, volume
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this data source for logging."""
        ...


class IndicatorPlugin(ABC):
    """Abstract interface for analysis indicator plugins.

    Each plugin encapsulates a single analysis theory (chanlun, wyckoff, momentum, etc.)
    and produces a standardized signal dict that the fusion layer can consume.
    """

    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g. 'chanlun', 'wyckoff', 'momentum')."""
        ...

    @abstractmethod
    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
        weekly_bars: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run analysis and return standardized result.

        Args:
            current: Current stock price
            bars: Daily K-line bars
            change_pct: Today's change percentage
            quote: Real-time quote dict
            weekly_bars: Weekly K-line bars (midline analysis / daily chan
                higher_trend filter). Plugins that don't need it should accept
                and ignore it so analyze_all can always forward it (ADR-002).

        Returns:
            Dict with at least: direction (int), confidence (float), reason (str)
        """
        ...

    def weight(self) -> float:
        """Default weight for this indicator in fusion (0.0-1.0).

        Override to customize. Default is 1.0 (equal weight).
        """
        return 1.0
