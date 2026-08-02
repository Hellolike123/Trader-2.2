"""Named keys → Path under ~/.trader (or TRADER_ROOT override).

Registry for trader JSON / jsonl stores. Prefer ``path(key)`` over hardcoding
``Path.home() / ".trader" / ...``.

Env overrides (per-key, when already used elsewhere):
  TRADER_ROOT                      → root for default files under ~/.trader
  TRADER_BUY_POINT_LIFECYCLE_PATH  → buy_point_lifecycle
  TRADER_LAST_ADD_PATH             → last_add_dates
  TRADER_SIGNAL_STORE_PATH         → signals
  T0_TRADER_STATE_PATH             → t0_state
  T0_CACHE_DIR                     → parent of t0_state when T0_TRADER_STATE_PATH unset

PATH_KEYS (filenames under trader_root unless noted):
  root                     → directory itself
  pool                     → pool.json
  pending                  → pending.json
  last_plan                → last_plan.json
  pool_archive             → pool_archive.json
  signals                  → signals.jsonl
  signal_results           → signal_results.jsonl   (tracker settlement)
  chip_history             → chip_history.json
  calibrated_params        → calibrated_params.json
  trailing_stop_watermark  → trailing_stop_watermark.json
  buy_point_lifecycle      → buy_point_lifecycle.json
  last_add_dates           → last_add_dates.json
  wyckoff_phase            → wyckoff_phase.json
  wyckoff_light_snapshot   → wyckoff_light_snapshot.json  (详析卡灯变化)
  wyckoff_phase_a_anchor   → wyckoff_phase_a_anchor.json
  position                 → position.json          (T0)
  positions_portfolio      → positions.json         (review portfolio)
  account                  → account.json
  t0_ledger                → t0_ledger.jsonl
  t0_state                 → ~/.t0-trader/state.json by default (not under root)
  holdings                 → holdings.json          (unified SSOT)
  last_target              → last_target.txt        (final_report / pool add-last)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from trader_shared.json_atomic import load_json_dict, locked_rmw_json

# key → relative filename under trader_root()
_FILE_BY_KEY: dict[str, str] = {
    "pool": "pool.json",
    "pending": "pending.json",
    "last_plan": "last_plan.json",
    "pool_archive": "pool_archive.json",
    "signals": "signals.jsonl",
    "signal_results": "signal_results.jsonl",
    "chip_history": "chip_history.json",
    "calibrated_params": "calibrated_params.json",
    "trailing_stop_watermark": "trailing_stop_watermark.json",
    "buy_point_lifecycle": "buy_point_lifecycle.json",
    "last_add_dates": "last_add_dates.json",
    "wyckoff_phase": "wyckoff_phase.json",
    "wyckoff_light_snapshot": "wyckoff_light_snapshot.json",
    "wyckoff_phase_a_anchor": "wyckoff_phase_a_anchor.json",
    "position": "position.json",
    "positions_portfolio": "positions.json",
    "account": "account.json",
    "t0_ledger": "t0_ledger.jsonl",
    "holdings": "holdings.json",
    "last_target": "last_target.txt",
}

# key → env var that overrides the full path
_ENV_OVERRIDE: dict[str, str] = {
    "buy_point_lifecycle": "TRADER_BUY_POINT_LIFECYCLE_PATH",
    "last_add_dates": "TRADER_LAST_ADD_PATH",
    "signals": "TRADER_SIGNAL_STORE_PATH",
    "t0_state": "T0_TRADER_STATE_PATH",
}

PATH_KEYS: frozenset[str] = frozenset({"root", "t0_state", *_FILE_BY_KEY.keys()})


def trader_root() -> Path:
    """Return TRADER_ROOT if set, else ``~/.trader``."""
    override = (os.environ.get("TRADER_ROOT") or "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".trader"


def path(key: str) -> Path:
    """Resolve a named persist key to an absolute Path.

    Raises KeyError for unknown keys.
    """
    k = str(key or "").strip()
    if k not in PATH_KEYS:
        raise KeyError(f"unknown trader_paths key: {key!r}; known={sorted(PATH_KEYS)}")

    env_name = _ENV_OVERRIDE.get(k)
    if env_name:
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            return Path(os.path.expanduser(raw))

    if k == "root":
        return trader_root()

    if k == "t0_state":
        # Historical default: ~/.t0-trader/state.json (outside ~/.trader)
        cache = (os.environ.get("T0_CACHE_DIR") or "").strip()
        if cache:
            return Path(os.path.expanduser(cache)) / "state.json"
        if (os.environ.get("TRADER_ROOT") or "").strip():
            # Test / override isolation: keep under TRADER_ROOT
            return trader_root() / "t0_state.json"
        return Path.home() / ".t0-trader" / "state.json"

    return trader_root() / _FILE_BY_KEY[k]


def load_json(key: str) -> dict[str, Any]:
    """Thin wrapper: load_json_dict(path(key))."""
    return load_json_dict(path(key))


def rmw_json(
    key: str,
    mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    skip_on_corrupt: bool = False,
) -> dict[str, Any]:
    """Thin wrapper: locked_rmw_json(path(key), mutator)."""
    return locked_rmw_json(path(key), mutator, skip_on_corrupt=skip_on_corrupt)
