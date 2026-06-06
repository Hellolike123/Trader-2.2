from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

CACHE_DIR = os.path.expanduser("~/.trader/tick_cache")


def _ensure_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str, trade_date: str | None = None) -> str:
    d = (trade_date or date.today().isoformat()).replace("-", "")
    norm = symbol.replace(".SH", "").replace(".SZ", "").strip()
    return os.path.join(CACHE_DIR, f"{norm}_{d}.json")


def save_tick_cache(symbol: str, tick_data: list[dict[str, Any]], trade_date: str | None = None) -> None:
    if not tick_data:
        return
    _ensure_dir()
    path = _cache_path(symbol, trade_date)
    payload = {
        "symbol": symbol,
        "date": (trade_date or date.today().isoformat()),
        "tick_count": len(tick_data),
        "ticks": tick_data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def load_tick_cache(symbol: str, trade_date: str | None = None) -> list[dict[str, Any]]:
    path = _cache_path(symbol, trade_date)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("ticks") or []
    except Exception:
        return []
