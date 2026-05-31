"""Simple file-based cache for historical data (daily bars, fundamentals).

Usage:
    from trader_shared.cache_utils import get_cached, set_cached, get_cached_data

    result = get_cached("daily", "688248", ttl=86400)
    if result is not None:
        data = result.data  # or use get_cached_data("daily", "688248", ttl=86400)
        if result.stale:
            print(f"Warning: data is {result.age_seconds}s old")
    else:
        data = fetch_from_api(...)
        set_cached("daily", "688248", data)
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

CACHE_DIR = Path.home() / ".trader" / "cache"

# Subdirectory constants
CACHE_DAILY = "daily"
CACHE_ENRICH = "enrich"
CACHE_MARKET_ENV = "market_env"
CACHE_FUND_FLOW = "fund_flow"

# TTL constants (seconds)
TTL_DAILY = 86400       # 24 hours - daily bars change once per day
TTL_WEEKLY = 604800     # 7 days - weekly bars change once per week
TTL_FUNDAMENTAL = 43200 # 12 hours - shareholder/unlock data updates infrequently
TTL_FUND_FLOW = 86400   # 24 hours - fund flow data updates daily after market close


@dataclass
class CacheResult:
    """Cache wrapper supporting stale-while-revalidate."""
    data: Any
    stale: bool
    age_seconds: float
    source: str  # "memory" | "file"


def validate_bars(bars: list[dict]) -> bool:
    """Validate bar data before writing to cache.

    Checks:
    - Bar count >= 200 (enough history for MA250)
    - Each bar has close > 0
    - Dates are monotonically increasing
    """
    if not isinstance(bars, list) or len(bars) < 200:
        return False
    prev_date = ""
    for bar in bars:
        close = bar.get("close")
        if close is None or float(close) <= 0:
            return False
        date = str(bar.get("date") or bar.get("time") or "")
        if date and date < prev_date:
            return False
        if date:
            prev_date = date
    return True


def get_cached(key: str, target: str, ttl: int = TTL_DAILY) -> CacheResult | None:
    """Read cache if exists. Returns CacheResult with stale flag if expired, None if missing."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    if not cache_file.exists():
        return None
    try:
        age = time.time() - cache_file.stat().st_mtime
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        stale = age > ttl
        return CacheResult(data=data, stale=stale, age_seconds=round(age, 1), source="file")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        _logger.debug("Cache read failed for %s/%s: %s", key, target, exc)
        return None


def get_cached_data(key: str, target: str, ttl: int = TTL_DAILY) -> Any | None:
    """Compatibility helper: returns cache data or None (ignores stale)."""
    result = get_cached(key, target, ttl)
    return result.data if result is not None else None


def set_cached(key: str, target: str, data: Any) -> None:
    """Write data to cache (atomic via temp file + rename, with file lock)."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = cache_file.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp_file.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        with open(cache_file, "a") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                tmp_file.replace(cache_file)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    except (OSError, TypeError) as exc:
        _logger.warning("Cache write failed for %s/%s: %s", key, target, exc)
        tmp_file.unlink(missing_ok=True)
        raise


def set_cached_validated(
    key: str,
    target: str,
    data: Any,
    validator: Callable[[Any], bool] | None = None,
) -> bool:
    """Write data to cache only if validation passes.

    Returns True if written, False if validation failed or write errored.
    """
    if validator is not None and not validator(data):
        return False
    try:
        set_cached(key, target, data)
        return True
    except (OSError, TypeError) as exc:
        _logger.debug("Validated cache write failed for %s/%s: %s", key, target, exc)
        return False


def invalidate(key: str, target: str) -> None:
    """Delete a specific cache entry."""
    cache_file = CACHE_DIR / key / f"{target}.json"
    cache_file.unlink(missing_ok=True)


def fetch_fund_flow_cached(symbol: str) -> dict[str, Any]:
    """获取资金流向数据（带缓存）。

    读缓存 → 过期则调API → 写缓存。
    返回 {"daily_flow": [...], "features": {...}} 或空 dict。
    """
    cached = get_cached_data(CACHE_FUND_FLOW, symbol, ttl=TTL_FUND_FLOW)
    if cached is not None:
        return cached
    try:
        from trader_shared.fund_flow_data import fetch_fund_flow, calc_fund_flow_features
        daily_flow = fetch_fund_flow(symbol)
        if not daily_flow:
            return {}
        features = calc_fund_flow_features(daily_flow)
        result = {"daily_flow": daily_flow, "features": features}
        set_cached(CACHE_FUND_FLOW, symbol, result)
        return result
    except (ImportError, OSError, ValueError) as exc:
        _logger.debug("Fund flow fetch/cache failed for %s: %s", symbol, exc)
        return {}


def cleanup_old_cache(max_age_days: int = 30) -> dict[str, int]:
    """Remove cache files older than max_age_days.

    Scans all subdirectories under CACHE_DIR and deletes .json files
    whose modification time is older than max_age_days.

    Args:
        max_age_days: Maximum age in days. Files older than this are deleted.

    Returns:
        Dict with 'scanned', 'deleted', 'failed' counts.
    """
    if not CACHE_DIR.exists():
        return {"scanned": 0, "deleted": 0, "failed": 0}

    cutoff_time = time.time() - (max_age_days * 86400)
    scanned = 0
    deleted = 0
    failed = 0

    for cache_file in CACHE_DIR.rglob("*.json"):
        scanned += 1
        try:
            if cache_file.stat().st_mtime < cutoff_time:
                cache_file.unlink()
                deleted += 1
                _logger.debug("Cleaned old cache file: %s", cache_file)
        except OSError as exc:
            failed += 1
            _logger.debug("Failed to clean cache file %s: %s", cache_file, exc)

    if deleted > 0:
        _logger.info("Cache cleanup: scanned=%d, deleted=%d, failed=%d", scanned, deleted, failed)

    return {"scanned": scanned, "deleted": deleted, "failed": failed}


def warm_pool_cache() -> dict[str, Any]:
    """Pre-cache data for all active stocks in the pool.

    Called after market close (15:00) to prepare data for next day's analysis.
    Reads ~/.trader/pool.json and fetches full data for each active stock.

    Returns:
        {"total": int, "success": int, "failed": int, "skipped": int, "errors": list}
    """
    import sys
    from pathlib import Path

    pool_path = Path.home() / ".trader" / "pool.json"
    if not pool_path.exists():
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    try:
        pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
        items = pool_data.get("items", [])
        targets = [
            item["name"] for item in items
            if item.get("status") not in ("淘汰", "已退出")
        ]
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        _logger.warning("Failed to read pool.json: %s", exc)
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    if not targets:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "errors": []}

    # Ensure paths
    root = Path(__file__).resolve().parents[2]
    for p in (
        root / "01-行情数据-market-data",
        root / "02-候选逻辑-candidate",
        root / "scripts",
    ):
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    try:
        from trader_shared.data_provider import get_provider
        from trader_shared.config import LOOKBACK_DAYS
    except ImportError:
        return {"total": len(targets), "success": 0, "failed": len(targets), "skipped": 0,
                "errors": ["data_provider or config not available"]}

    provider = get_provider()
    success = 0
    failed = 0
    errors: list[str] = []

    for name in targets:
        try:
            snapshot = provider.load_market_snapshot(name, days=LOOKBACK_DAYS, include_5m=False, include_ticks=False)
            if snapshot.daily_bars and snapshot.quote:
                success += 1
            else:
                failed += 1
                errors.append(f"{name}: incomplete data")
        except Exception as e:
            failed += 1
            errors.append(f"{name}: {e}")

    # Also warm market env cache
    try:
        sys.path.insert(0, str(root / "scripts"))
        from market_env import assess as _assess
        _assess()
    except (ImportError, OSError) as exc:
        _logger.debug("Market env cache warm failed: %s", exc)

    # Warm fund flow cache
    ff_success = 0
    ff_failed = 0
    for name in targets:
        try:
            result = fetch_fund_flow_cached(name)
            if result:
                ff_success += 1
            else:
                ff_failed += 1
        except Exception:
            ff_failed += 1

    # Clean up old cache files (older than 30 days)
    cleanup_result = cleanup_old_cache(max_age_days=30)

    return {
        "total": len(targets), "success": success, "failed": failed, "skipped": 0, "errors": errors,
        "fund_flow_success": ff_success, "fund_flow_failed": ff_failed,
        "cache_cleanup": cleanup_result,
    }


def clear_cache(cache_type: str | None = None) -> int:
    """Clear cache files. If cache_type is specified, only clear that subdirectory.

    Returns number of files deleted.
    """
    if cache_type:
        target_dir = CACHE_DIR / cache_type
    else:
        target_dir = CACHE_DIR
    if not target_dir.exists():
        return 0
    count = 0
    for f in target_dir.rglob("*.json"):
        try:
            f.unlink()
            count += 1
        except OSError as exc:
            _logger.debug("Failed to delete cache file %s: %s", f, exc)
    return count


def merge_daily_bars_with_quote(
    cached_bars: list[dict],
    quote: dict[str, Any],
) -> list[dict]:
    """Merge cached historical daily bars with today's real-time quote.

    Strategy:
    - Use cached bars as base (historical data, immutable after close)
    - Build today's bar from quote data
    - If today's date already exists in cached bars, replace it (quote is more recent)
    - Otherwise append today's bar at the end
    """
    if not cached_bars or not quote:
        return cached_bars

    today_str = datetime.now().strftime("%Y-%m-%d")

    def _to_float(v: Any) -> float | None:
        if v in (None, "", "-", "--"):
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    current_price = _to_float(quote.get("current_price"))
    if current_price is None:
        return cached_bars

    today_bar = {
        "date": today_str,
        "time": today_str,
        "open": _to_float(quote.get("open")) or current_price,
        "high": _to_float(quote.get("high")) or current_price,
        "low": _to_float(quote.get("low")) or current_price,
        "close": current_price,
        "volume": _to_float(quote.get("volume")),
        "amount": None,
        "data_source": "realtime-merge",
        "data_status": "partial",
    }

    # Copy ATR fields from the last cached bar (ATR is a slow variable, previous day's value is a good approximation)
    if cached_bars:
        prev_bar = cached_bars[-1]
        for atr_key in ("atr14", "atr_ratio", "atr7", "tr"):
            if prev_bar.get(atr_key) is not None:
                today_bar[atr_key] = prev_bar[atr_key]

    # Check if today already exists in cached bars
    result = []
    today_replaced = False
    for bar in cached_bars:
        bar_date = str(bar.get("date") or bar.get("time") or "")
        if bar_date == today_str:
            result.append(today_bar)
            today_replaced = True
        else:
            result.append(bar)

    if not today_replaced:
        result.append(today_bar)

    return result
