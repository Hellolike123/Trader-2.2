# -*- coding: utf-8 -*-
"""行情领域类型 SSOT（Security / MarketSnapshot）。

light_data 与 data_provider 共用，避免双定义 + snapshot 往返 copy-convert。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

DataStatus = Literal["full", "partial", "degraded", "failed"]


@dataclass(frozen=True)
class Security:
    code: str
    market: str = ""
    name: str = ""

    @property
    def ts_code(self) -> str:
        m = self.market.upper() if self.market else (
            "SH" if self.code.startswith(("6", "5", "9")) else "SZ"
        )
        return f"{self.code}.{m}"

    @property
    def qq_symbol(self) -> str:
        m = self.market.lower() if self.market else (
            "sh" if self.code.startswith(("6", "5", "9")) else "sz"
        )
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
    data_freshness: str = "live"
    fund_flow: dict[str, Any] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)
    fetched_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    extend_fundamental: dict[str, Any] | None = None
    extend_sentiment: dict[str, Any] | None = None
    extend_margin: dict[str, Any] | None = None
    extend_northbound: dict[str, Any] | None = None
    extend_sector: dict[str, Any] | None = None
    extend_concept: dict[str, Any] | None = None

    @property
    def is_usable(self) -> bool:
        return bool(self.quote and self.daily_bars)
