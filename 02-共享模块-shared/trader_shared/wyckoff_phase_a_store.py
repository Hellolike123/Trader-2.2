"""Persistent Phase A anchor store for Wyckoff Path A.

The store is intentionally separate from ``wyckoff_phase.json``.  It records
only alive Phase A anchors and relocates ``sc_bar_idx`` by ``sc_date`` on load.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trader_shared.json_atomic import load_json_dict, locked_rmw_json
from trader_shared.light_data import to_float
from trader_shared.trader_paths import path as trader_path

_ALIVE_STATUS = {"forming", "established"}


def _wyckoff_phase_a_anchor_path() -> Path:
    """``~/.trader/wyckoff_phase_a_anchor.json`` (via trader_paths)."""
    return trader_path("wyckoff_phase_a_anchor")


def _anchor_key(symbol: str, timeframe: str = "daily") -> str:
    """Persist key: caller-provided symbol + isolated timeframe suffix."""
    return f"{str(symbol or '').strip()}::{str(timeframe or 'daily').strip().lower()}"


def _bar_date(bar: dict[str, Any]) -> str:
    raw = str((bar or {}).get("date") or "").strip()
    return raw[:10] if raw else ""


def _locate_sc_bar_idx(bars: list[dict[str, Any]], sc_date: str) -> int | None:
    target = str(sc_date or "").strip()[:10]
    if not target:
        return None
    for idx, bar in enumerate(bars):
        if _bar_date(bar) == target:
            return idx
    return None


def _delete_key(key: str) -> None:
    if not key:
        return
    try:
        def _mutate(data: dict[str, Any]) -> dict[str, Any]:
            data.pop(key, None)
            return data

        locked_rmw_json(_wyckoff_phase_a_anchor_path(), _mutate)
    except OSError:
        pass


def load_phase_a_anchor(
    symbol: str,
    timeframe: str,
    bars: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Load an alive anchor and relocate ``sc_bar_idx`` by ``sc_date``.

    Bad records self-heal by deleting the key and returning ``None``.
    """
    sym = str(symbol or "").strip()
    if not sym:
        return None
    key = _anchor_key(sym, timeframe)
    try:
        data = load_json_dict(_wyckoff_phase_a_anchor_path())
    except (OSError, TypeError, ValueError):
        return None
    rec = data.get(key)
    if not isinstance(rec, dict):
        return None

    status = str(rec.get("status") or "").strip()
    sc_date = str(rec.get("sc_date") or "").strip()[:10]
    sc_low = to_float(rec.get("sc_low"))
    sc_bar_idx = _locate_sc_bar_idx(bars, sc_date)
    if status not in _ALIVE_STATUS or not sc_date or sc_low is None or sc_bar_idx is None:
        _delete_key(key)
        return None

    ar_high_raw = rec.get("ar_high")
    ar_high = to_float(ar_high_raw) if ar_high_raw is not None else None
    return {
        "status": status,
        "sc_date": sc_date,
        "sc_low": round(float(sc_low), 2),
        "sc_bar_idx": sc_bar_idx,
        "ar_high": round(float(ar_high), 2) if ar_high is not None else None,
        "timeframe": str(timeframe or "daily").strip().lower(),
    }


def save_phase_a_anchor(
    symbol: str,
    timeframe: str,
    phase_a_range: dict[str, Any] | None,
    bars: list[dict[str, Any]],
) -> None:
    """Save alive anchors; delete the key for failed/none/invalid results."""
    sym = str(symbol or "").strip()
    if not sym:
        return
    key = _anchor_key(sym, timeframe)
    pa = phase_a_range if isinstance(phase_a_range, dict) else {}
    status = str(pa.get("status") or "").strip()
    if status not in _ALIVE_STATUS:
        _delete_key(key)
        return

    try:
        sc_idx = int(pa.get("sc_bar_idx"))
    except (TypeError, ValueError):
        _delete_key(key)
        return
    if sc_idx < 0 or sc_idx >= len(bars):
        _delete_key(key)
        return
    sc_date = _bar_date(bars[sc_idx])
    sc_low = to_float(pa.get("sc_low"))
    if not sc_date or sc_low is None:
        _delete_key(key)
        return

    ar_high_raw = pa.get("ar_high")
    ar_high = to_float(ar_high_raw) if ar_high_raw is not None else None
    rec: dict[str, Any] = {
        "sc_date": sc_date,
        "sc_low": round(float(sc_low), 2),
        "ar_high": round(float(ar_high), 2) if ar_high is not None else None,
        "status": status,
        "timeframe": str(timeframe or "daily").strip().lower(),
        "sc_bar_idx": sc_idx,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        def _mutate(data: dict[str, Any]) -> dict[str, Any]:
            data[key] = rec
            return data

        locked_rmw_json(_wyckoff_phase_a_anchor_path(), _mutate)
    except OSError:
        pass


def delete_phase_a_anchor(symbol: str, timeframe: str = "daily") -> None:
    """Delete a persisted anchor key; missing keys are successful."""
    sym = str(symbol or "").strip()
    if not sym:
        return
    _delete_key(_anchor_key(sym, timeframe))
