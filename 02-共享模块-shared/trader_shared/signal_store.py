from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .signal_contract import assert_valid_signal
from .signal_utils import (
    build_signal_key,
    normalize_date,
    normalize_signal_id,
    normalize_signal_type,
    normalize_symbol,
    price_from_trigger,
)
from trader_shared._logging import get_logger

_logger = get_logger(__name__)

# Schema version for signal records — bump when format changes
SIGNAL_SCHEMA_VERSION: int = 1


def _get_default_store_path() -> Path:
    """Return default signal store path.

    Prefers TRADER_SIGNAL_STORE_PATH env var, otherwise falls back to
    ~/.trader/signals.jsonl.
    """
    env_path = os.environ.get("TRADER_SIGNAL_STORE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_SIGNAL_STORE_PATH


DEFAULT_SIGNAL_STORE_PATH = Path.home() / ".trader" / "signals.jsonl"
_ROTATION_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10MB


def _get_archive_path(store_path: Path) -> Path:
    """Generate quarterly archive path: signals-archive-YYYYQ#.jsonl"""
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return store_path.parent / f"{store_path.stem}-archive-{now.year}Q{quarter}{store_path.suffix}"


def _maybe_rotate(store_path: Path) -> None:
    """Rotate signals.jsonl if it exceeds the threshold."""
    try:
        if store_path.exists() and store_path.stat().st_size > _ROTATION_THRESHOLD_BYTES:
            archive_path = _get_archive_path(store_path)
            # Read current content
            content = store_path.read_bytes()
            # Append to archive (or create new)
            with open(archive_path, "ab") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(content)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            # Truncate current file
            store_path.write_text("", encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Signal rotation failed: %s", exc)  # rotation failure should not block signal writing


def append_signal(signal: dict[str, Any], path: Path | None = None) -> str:
    """Append a signal to the store.

    Does NOT mutate the caller's dict.  Returns the signal_id so callers
    that need it can capture the return value.

    Uses in-memory UUID cache for fast duplicate detection.
    Uses fcntl.flock for cross-process atomicity: check + append is a single
    locked section to prevent duplicate writes from parallel processes.
    """
    # Deep-copy so the caller's dict is never mutated.
    working = dict(signal)
    # Deep-copy nested dicts that build_signal_id may reference.
    if isinstance(working.get("trigger"), dict):
        working["trigger"] = dict(working["trigger"])
    if working.get("trigger") is None:
        working["trigger"] = {}

    if "signal_id" not in working:
        working["signal_id"] = normalize_signal_id(
            symbol=normalize_symbol(str(working.get("symbol") or "")),
            date=normalize_date(str(working.get("trade_date") or "")),
            signal_type=normalize_signal_type(str(working.get("signal_type") or "unknown").strip()),
            price=price_from_trigger(working) or "0.00",
        )

    # Add schema version for future migrations
    if "schema_version" not in working:
        working["schema_version"] = SIGNAL_SCHEMA_VERSION

    assert_valid_signal(working)

    store_path = path or _get_default_store_path()

    # ── Cross-process dedup + append: use fcntl.flock for atomicity ──
    # mkdir 必须在 open 之前，否则首次写入 ~/.trader/ 等缺失目录会 FileNotFoundError
    store_path.parent.mkdir(parents=True, exist_ok=True)
    _maybe_rotate(store_path)
    with open(store_path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            # Re-check via in-memory UUID cache (may have been populated by another process
            # that held the lock first)
            uuid_cache = _load_uuid_cache(store_path)
            if working["signal_id"] in uuid_cache:
                _logger.debug("Duplicate signal_id %s, skipping write", working["signal_id"])
                return working["signal_id"]

            # 直接写行：禁止再调 DataManager.append_signal（其对同文件二次 flock，
            # 在部分平台会自死锁）。本段已持有 LOCK_EX。
            f.write(json.dumps(working, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

            # Update in-memory UUID cache
            uuid_cache.add(working["signal_id"])
            _sig_cache.pop(str(store_path), None)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return working["signal_id"]


# Module-level cache for load_recent_signals — keyed by path.
# path_str -> { "mtime": float, "ino": int, "data": list[dict] }
_sig_cache: dict = {}
_CACHE_TTL_SECONDS = 2  # Stale a cache entry after 2 s.

# Bad-line observability for external monitoring.
_bad_line_count: int = 0
_bad_line_last_reason: str = ""
_bad_line_last_path: str = ""

# ── UUID deduplication cache ─────────────────────────────────────────
# In-memory set of signal_id values for fast duplicate detection.
# Loaded lazily on first access, updated on every append.
_uuid_cache: set[str] | None = None
_uuid_cache_path: str | None = None


def _load_uuid_cache(path: Path | None = None) -> set[str]:
    """Load all UUIDs from signals.jsonl into memory on first access.

    Returns a set of signal_id strings. Subsequent calls return the cached set
    unless the path has changed.
    """
    global _uuid_cache, _uuid_cache_path
    store_path = str(path or _get_default_store_path())

    if _uuid_cache is not None and _uuid_cache_path == store_path:
        return _uuid_cache

    uuids: set[str] = set()
    try:
        if Path(store_path).exists():
            raw = Path(store_path).read_text(encoding="utf-8")
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    sid = item.get("signal_id")
                    if sid:
                        uuids.add(str(sid))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as exc:
        _logger.debug("UUID cache load failed for %s: %s", store_path, exc)

    _uuid_cache = uuids
    _uuid_cache_path = store_path
    return _uuid_cache


def _read_store(store_path: Path) -> list[dict[str, Any]]:
    """Read store file with file-change detection in cache."""
    global _bad_line_count, _bad_line_last_reason, _bad_line_last_path

    if not store_path.exists():
        return []

    try:
        stat = store_path.stat()
        mtime = stat.st_mtime
        ino = stat.st_ino
    except OSError:
        return []

    path_key = str(store_path)
    entry = _sig_cache.get(path_key)

    # Invalidate cache when file changes on disk.
    if entry is not None and (
        entry.get("ino") != ino
        or entry.get("mtime") != mtime
        or (time.time() - entry["mtime"]) >= _CACHE_TTL_SECONDS
    ):
        entry = None

    if entry is None:
        raw = store_path.read_text(encoding="utf-8")
        signals: list[dict[str, Any]] = []
        _bad_line_count = 0
        _bad_line_last_reason = ""
        _bad_line_last_path = path_key
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, ValueError) as e:
                _bad_line_count += 1
                _bad_line_last_reason = str(e)
                continue
            if not isinstance(item, dict):
                _bad_line_count += 1
                _bad_line_last_reason = "item is not a dict"
                continue
            signals.append(item)
        _sig_cache[path_key] = {"mtime": mtime, "ino": ino, "data": signals}
    else:
        signals = entry["data"]

    return signals


def load_recent_signals(symbol: str | None = None, limit: int = 20, path: Path | None = None) -> list[dict[str, Any]]:
    store_path = path or _get_default_store_path()
    signals = _read_store(store_path)

    if symbol:
        norm_query = normalize_symbol(symbol)
        signals = [
            s for s in signals
            if normalize_symbol(str(s.get("symbol") or "")) == norm_query
        ]
    return signals[-limit:]


# ── Signal expiry cleanup ─────────────────────────────────────────────


# Terminal states that can be safely archived
_TERMINAL_STATES: set[str] = {"completed", "expired"}


def cleanup_old_signals(
    max_age_days: int = 90,
    path: Path | None = None,
) -> dict[str, int]:
    """Archive and remove old signals from the store.

    Signals older than max_age_days are archived to signals_archive_YYYYMM.jsonl
    before being removed from the main store. Signals with status "active" or
    without a terminal status are kept regardless of age.

    Args:
        max_age_days: Maximum age in days. Older terminal signals are archived.
        path: Override signal store path (default: ~/.trader/signals.jsonl).

    Returns:
        Dict with 'total', 'archived', 'kept', 'failed' counts.
    """
    store_path = path or _get_default_store_path()
    if not store_path.exists():
        return {"total": 0, "archived": 0, "kept": 0, "failed": 0}

    signals = _read_store(store_path)
    if not signals:
        return {"total": 0, "archived": 0, "kept": 0, "failed": 0}

    cutoff_time = datetime.now().timestamp() - (max_age_days * 86400)
    cutoff_date = datetime.fromtimestamp(cutoff_time).strftime("%Y-%m-%d")

    to_archive: list[dict[str, Any]] = []
    to_keep: list[dict[str, Any]] = []
    failed = 0

    for sig in signals:
        trade_date = str(sig.get("trade_date") or "")
        status = str(sig.get("status") or "").lower()

        # Keep active signals regardless of age
        if status not in _TERMINAL_STATES and status != "":
            to_keep.append(sig)
            continue

        # Keep signals without a date (can't determine age)
        if not trade_date:
            to_keep.append(sig)
            continue

        # Archive old terminal signals
        if trade_date < cutoff_date:
            to_archive.append(sig)
        else:
            to_keep.append(sig)

    # Archive to monthly file before deletion
    if to_archive:
        try:
            _archive_signals(to_archive, store_path)
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Signal archival failed: %s", exc)
            failed = len(to_archive)
            # If archival fails, keep all signals to avoid data loss
            return {"total": len(signals), "archived": 0, "kept": len(signals), "failed": failed}

    # Rewrite store with kept signals (atomic via DataManager)
    if to_archive:
        try:
            _rewrite_store(to_keep, store_path)
        except (OSError, TypeError) as exc:
            _logger.warning("Signal store rewrite failed: %s", exc)
            failed = len(to_archive)

    result = {
        "total": len(signals),
        "archived": len(to_archive) - failed,
        "kept": len(to_keep),
        "failed": failed,
    }

    if result["archived"] > 0:
        _logger.info(
            "Signal cleanup: total=%d, archived=%d, kept=%d, failed=%d, cutoff=%s",
            result["total"], result["archived"], result["kept"], result["failed"], cutoff_date,
        )

    return result


def _archive_signals(signals: list[dict[str, Any]], store_path: Path) -> None:
    """Archive signals to a monthly archive file.

    Groups signals by trade_date month and writes to signals_archive_YYYYMM.jsonl.
    """
    # Group by YYYY-MM
    by_month: dict[str, list[dict[str, Any]]] = {}
    for sig in signals:
        trade_date = str(sig.get("trade_date") or "")
        if len(trade_date) >= 7:
            month_key = trade_date[:7].replace("-", "")  # YYYYMM
        else:
            month_key = "unknown"
        by_month.setdefault(month_key, []).append(sig)

    for month_key, month_signals in by_month.items():
        archive_path = store_path.parent / f"{store_path.stem}_archive_{month_key}{store_path.suffix}"
        lines = [json.dumps(s, ensure_ascii=False, default=str) + "\n" for s in month_signals]

        with open(archive_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        _logger.debug("Archived %d signals to %s", len(month_signals), archive_path)


def _rewrite_store(signals: list[dict[str, Any]], store_path: Path) -> None:
    """Atomically rewrite the signal store with the given signals.

    Uses temp file + fsync + rename for crash safety.
    Invalidates UUID cache after rewrite.
    """
    global _uuid_cache, _uuid_cache_path
    tmp_path = store_path.with_suffix(f".{os.getpid()}.rewrite.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            for sig in signals:
                f.write(json.dumps(sig, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, store_path)
        # Invalidate UUID cache — will be rebuilt on next access
        _uuid_cache = None
        _uuid_cache_path = None
    except (OSError, TypeError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise exc


# ── Convenience helpers for downstream modules ──────────────────────


def make_signal_key(sig: dict[str, Any]) -> tuple[str, str, str, str]:
    """Compatibility alias — use signal_utils.build_signal_key directly."""
    return build_signal_key(sig)


def get_bad_line_stats() -> dict[str, Any]:
    """Return bad line diagnostics from the last _read_store() call."""
    return {
        "count": _bad_line_count,
        "last_reason": _bad_line_last_reason,
        "last_path": _bad_line_last_path,
    }
