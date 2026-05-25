from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from signal_contract import assert_valid_signal
from signal_utils import (
    build_signal_key,
    normalize_date,
    normalize_signal_id,
    normalize_signal_type,
    normalize_symbol,
    price_from_trigger,
)


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


def append_signal(signal: dict[str, Any], path: Path | None = None) -> str:
    """Append a signal to the store.

    Does NOT mutate the caller's dict.  Returns the signal_id so callers
    that need it can capture the return value.
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

    assert_valid_signal(working)

    store_path = path or _get_default_store_path()
    
    from trader_shared.data_manager import DataManager
    DataManager.append_signal(working, path=store_path)

    _sig_cache.pop(str(store_path), None)
    return working["signal_id"]


# Module-level cache for load_recent_signals — keyed by path.
# path_str -> { "mtime": float, "ino": int, "data": list[dict] }
_sig_cache: dict = {}
_CACHE_TTL_SECONDS = 2  # Stale a cache entry after 2 s.

# Bad-line observability for external monitoring.
_bad_line_count: int = 0
_bad_line_last_reason: str = ""
_bad_line_last_path: str = ""


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
            except Exception as e:
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


# ── Convenience helpers for downstream modules ──────────────────────


def make_signal_key(sig: dict[str, Any]) -> tuple[str, str, str, str]:
    """Compatibility alias — use signal_utils.build_signal_key directly."""
    return build_signal_key(sig)
