from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from signal_contract import assert_valid_signal
from signal_tracker import (
    _normalize_symbol,
    _norm_date,
    _normalize_signal_type,
    _price_from_trigger,
    make_signal_id,
)


def _normalize_symbol(symbol: str) -> str:
    """Ensure bare 6-digit codes get exchange suffix so 688248 matches 688248.SH."""
    if not symbol or "." in symbol:
        return symbol
    s = str(symbol).strip()
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9", "5")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


DEFAULT_SIGNAL_STORE_PATH = Path(os.environ.get("TRADER_SIGNAL_STORE_PATH", Path.home() / ".trader" / "signals.jsonl"))


def append_signal(signal: dict[str, Any], path: Path | None = None) -> None:
    assert_valid_signal(signal)
    if "signal_id" not in signal:
        raw_type = str(signal.get("signal_type") or "unknown").strip()
        signal["signal_id"] = make_signal_id(
            symbol=_normalize_symbol(str(signal.get("symbol") or "")),
            date=_norm_date(str(signal.get("trade_date") or "")),
            signal_type=_normalize_signal_type(raw_type),
            price=_price_from_trigger(signal) or "0.00",
        )
    store_path = path or DEFAULT_SIGNAL_STORE_PATH
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(signal, ensure_ascii=False, sort_keys=True, default=str))
        handle.write("\n")
    # Invalidate cache so the next read sees the new append
    _sig_cache.pop(str(store_path), None)

# Module-level cache for load_recent_signals — keyed by path.
# Avoids re-reading/parsing the file when multiple callers query the same store.
_sig_cache: dict = {}       # path_str → { "mtime": float, "data": list[dict] }
_CACHE_TTL_SECONDS = 2      # Stale a cache entry after 2 s to pick up fresh appends.


def _read_store(store_path: Path) -> list[dict[str, Any]]:
    if not store_path.exists():
        return []
    raw = store_path.read_text(encoding="utf-8")
    signals: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        signals.append(item)
    return signals


def load_recent_signals(symbol: str | None = None, limit: int = 20, path: Path | None = None) -> list[dict[str, Any]]:
    store_path = path or DEFAULT_SIGNAL_STORE_PATH
    path_key = str(store_path)

    now = time.time()
    entry = _sig_cache.get(path_key)

    if entry is not None and (now - entry["mtime"]) < _CACHE_TTL_SECONDS:
        signals = entry["data"]
    else:
        signals = _read_store(store_path)
        _sig_cache[path_key] = {"mtime": now, "data": signals}

    if symbol:
        norm_query = _normalize_symbol(symbol)
        signals = [s for s in signals if _normalize_symbol(str(s.get("symbol") or "")) == norm_query]
    return signals[-limit:]
