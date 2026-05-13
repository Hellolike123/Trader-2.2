from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from signal_contract import assert_valid_signal
from signal_tracker import (
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


def _get_default_store_path() -> Path:
    """返回默认信号存储路径。
    
    优先读取环境变量，否则 fallback 到 ~/.trader/signals.jsonl。
    测试可通过 patch DEFAULT_SIGNAL_STORE_PATH 覆盖此值。
    """
    env_path = os.environ.get("TRADER_SIGNAL_STORE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_SIGNAL_STORE_PATH


DEFAULT_SIGNAL_STORE_PATH = Path.home() / ".trader" / "signals.jsonl"


def append_signal(signal: dict[str, Any], path: Path | None = None) -> None:
    # Use a working copy so normalize/assert don't mutate the caller's dict,
    # but still sync the computed signal_id back to avoid silent mismatches.
    working = dict(signal)
    if "signal_id" not in working:
        raw_type = str(working.get("signal_type") or "unknown").strip()
        working["signal_id"] = make_signal_id(
            symbol=_normalize_symbol(str(working.get("symbol") or "")),
            date=_norm_date(str(working.get("trade_date") or "")),
            signal_type=_normalize_signal_type(raw_type),
            price=_price_from_trigger(working) or "0.00",
        )
        signal["signal_id"] = working["signal_id"]  # sync back
    assert_valid_signal(working)
    store_path = path or _get_default_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(working, ensure_ascii=False, sort_keys=True, default=str))
        handle.write("\n")
    _sig_cache.pop(str(store_path), None)

# Module-level cache for load_recent_signals — keyed by path.
# Avoids re-reading/parsing the file when multiple callers query the same store.
_sig_cache: dict = {}       # path_str → { "mtime": float, "data": list[dict] }
_CACHE_TTL_SECONDS = 2      # Stale a cache entry after 2 s to pick up fresh appends.
_bad_line_count: int = 0     # 坏行计数，供外部监控


def _read_store(store_path: Path) -> list[dict[str, Any]]:
    global _bad_line_count
    if not store_path.exists():
        return []
    raw = store_path.read_text(encoding="utf-8")
    signals: list[dict[str, Any]] = []
    _bad_line_count = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            _bad_line_count += 1
            continue
        if not isinstance(item, dict):
            _bad_line_count += 1
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
