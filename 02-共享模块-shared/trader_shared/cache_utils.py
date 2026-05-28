"""Simple file-based cache for historical data (daily bars, fundamentals).

Usage:
    from trader_shared.cache_utils import get_cached, set_cached

    cached = get_cached("daily", "688248", ttl=86400)
    if cached is None:
        cached = fetch_from_api(...)
        set_cached("daily", "688248", cached)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path.home() / ".trader" / "cache"

# TTL constants (seconds)
TTL_DAILY = 86400       # 24 hours - daily bars change once per day
TTL_WEEKLY = 604800     # 7 days - weekly bars change once per week
TTL_FUNDAMENTAL = 43200 # 12 hours - shareholder/unlock data updates infrequently


def get_cached(key: str, target: str, ttl: int = TTL_DAILY) -> list[dict] | dict | None:
    """Read cache if exists and not expired. Returns None if miss."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    if not cache_file.exists():
        return None
    try:
        if time.time() - cache_file.stat().st_mtime > ttl:
            return None  # expired
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def set_cached(key: str, target: str, data: Any) -> None:
    """Write data to cache (atomic via temp file + rename)."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = cache_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    tmp_file.replace(cache_file)  # atomic on POSIX


def invalidate(key: str, target: str) -> None:
    """Delete a specific cache entry."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.unlink(missing_ok=True)
