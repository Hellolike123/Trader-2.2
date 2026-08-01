"""Unified holdings SSOT — ``~/.trader/holdings.json`` (via trader_paths).

Shape (holdings_v1)::

    {
      "schema": "holdings_v1",
      "by_symbol": {
        "600519.SH": {
          "cost": 1600.0,
          "shares": 100,
          "name": "贵州茅台",
          "source": "manual|t0|portfolio",
          "updated_at": "..."
        }
      }
    }

Legacy ``position.json`` (T0) and ``positions.json`` (portfolio) are dual-written
for one release; they are not deleted. Lazy migrate into holdings on first read
when a key is missing / holdings empty.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trader_shared.json_atomic import load_json_dict, locked_rmw_json
from trader_shared.trader_paths import path as trader_path

_SCHEMA = "holdings_v1"
_migrated_once = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_symbol(symbol: str) -> str:
    s = str(symbol or "").strip()
    if not s:
        return ""
    try:
        from trader_shared.signal_utils import normalize_symbol
        return normalize_symbol(s) or s
    except Exception:
        return s


def holdings_path():
    return trader_path("holdings")


def _empty_doc() -> dict[str, Any]:
    return {"schema": _SCHEMA, "by_symbol": {}}


def _ensure_doc(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_doc()
    out = dict(raw)
    out.setdefault("schema", _SCHEMA)
    by = out.get("by_symbol")
    if not isinstance(by, dict):
        out["by_symbol"] = {}
    return out


def migrate_legacy_into_holdings() -> dict[str, Any]:
    """Import from position.json / positions.json into holdings (non-destructive).

    - Prefer existing holdings keys (do not overwrite).
    - Portfolio rows without a code/symbol are skipped (do not invent codes).
    """
    store = holdings_path()

    def _mutate(data: dict[str, Any]) -> dict[str, Any]:
        doc = _ensure_doc(data)
        by = doc["by_symbol"]
        # T0 position.json: {positions: {sym: {avg_cost|cost, total_shares|shares, name?}}}
        try:
            pos_path = trader_path("position")
            legacy = load_json_dict(pos_path)
            positions = legacy.get("positions") if isinstance(legacy, dict) else None
            if isinstance(positions, dict):
                for sym, rec in positions.items():
                    if not isinstance(rec, dict):
                        continue
                    key = _norm_symbol(sym)
                    if not key or key in by:
                        continue
                    cost = float(rec.get("avg_cost") or rec.get("cost") or 0)
                    shares = int(rec.get("total_shares") or rec.get("shares") or 0)
                    if cost <= 0 and shares <= 0:
                        continue
                    by[key] = {
                        "cost": cost,
                        "shares": shares,
                        "name": str(rec.get("name") or ""),
                        "source": "t0",
                        "updated_at": str(rec.get("updated_at") or _now_iso()),
                    }
        except (OSError, TypeError, ValueError):
            pass

        # Portfolio positions.json: {holdings: [{name, shares, cost, symbol?/code?}]}
        try:
            pf_path = trader_path("positions_portfolio")
            legacy_pf = load_json_dict(pf_path)
            rows = legacy_pf.get("holdings") if isinstance(legacy_pf, dict) else None
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    code = row.get("symbol") or row.get("code") or row.get("ts_code")
                    if not code:
                        # name-only: skip (do not invent codes)
                        continue
                    key = _norm_symbol(str(code))
                    if not key or key in by:
                        continue
                    cost = float(row.get("cost") or 0)
                    shares = int(row.get("shares") or 0)
                    if cost <= 0 and shares <= 0:
                        continue
                    by[key] = {
                        "cost": cost,
                        "shares": shares,
                        "name": str(row.get("name") or ""),
                        "source": "portfolio",
                        "updated_at": _now_iso(),
                    }
        except (OSError, TypeError, ValueError):
            pass

        doc["by_symbol"] = by
        return doc

    return locked_rmw_json(store, _mutate)


def _maybe_migrate() -> None:
    global _migrated_once
    if _migrated_once:
        return
    _migrated_once = True
    try:
        store = holdings_path()
        raw = load_json_dict(store)
        by = raw.get("by_symbol") if isinstance(raw, dict) else None
        # Migrate when missing file / empty by_symbol
        if not isinstance(by, dict) or not by:
            migrate_legacy_into_holdings()
    except Exception:
        pass


def _load_doc() -> dict[str, Any]:
    _maybe_migrate()
    return _ensure_doc(load_json_dict(holdings_path()))


def list_holdings() -> dict[str, dict[str, Any]]:
    """Return ``by_symbol`` mapping (copy)."""
    doc = _load_doc()
    by = doc.get("by_symbol") or {}
    return {str(k): dict(v) for k, v in by.items() if isinstance(v, dict)}


def get_holding(symbol: str) -> dict[str, Any] | None:
    key = _norm_symbol(symbol)
    if not key:
        return None
    by = list_holdings()
    hit = by.get(key)
    if hit is not None:
        return hit
    # bare / alias: scan
    bare = key.split(".")[0]
    for k, v in by.items():
        if k == key or k.split(".")[0] == bare:
            return v
    return None


def upsert_holding(
    symbol: str,
    *,
    cost: float,
    shares: int = 0,
    name: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    """Create/update one holding; returns the stored record."""
    key = _norm_symbol(symbol)
    if not key:
        raise ValueError("symbol required")

    stamp = _now_iso()
    record = {
        "cost": float(cost or 0),
        "shares": int(shares or 0),
        "name": str(name or ""),
        "source": str(source or "manual"),
        "updated_at": stamp,
    }

    def _mutate(data: dict[str, Any]) -> dict[str, Any]:
        doc = _ensure_doc(data)
        prev = doc["by_symbol"].get(key)
        if isinstance(prev, dict) and not record["name"] and prev.get("name"):
            record["name"] = str(prev.get("name") or "")
        doc["by_symbol"][key] = record
        return doc

    locked_rmw_json(holdings_path(), _mutate)
    return dict(record)


def clear_holding(symbol: str) -> None:
    key = _norm_symbol(symbol)
    if not key:
        return

    def _mutate(data: dict[str, Any]) -> dict[str, Any] | None:
        doc = _ensure_doc(data)
        if key not in doc["by_symbol"]:
            # also try bare match
            bare = key.split(".")[0]
            for k in list(doc["by_symbol"]):
                if k.split(".")[0] == bare:
                    doc["by_symbol"].pop(k, None)
                    return doc
            return None
        doc["by_symbol"].pop(key, None)
        return doc

    locked_rmw_json(holdings_path(), _mutate)


def resolve_cost_price(symbol: str, explicit_cost: float = 0.0) -> float:
    """Priority: explicit_cost > 0 → use it; else holdings SSOT cost if shares>0 or cost>0; else 0.

    Does **not** read signals.jsonl track/trigger prices (M3).
    """
    try:
        ex = float(explicit_cost or 0)
    except (TypeError, ValueError):
        ex = 0.0
    if ex > 0:
        return ex
    hit = get_holding(symbol)
    if not isinstance(hit, dict):
        return 0.0
    try:
        cost = float(hit.get("cost") or 0)
    except (TypeError, ValueError):
        cost = 0.0
    try:
        shares = int(hit.get("shares") or 0)
    except (TypeError, ValueError):
        shares = 0
    if shares > 0 or cost > 0:
        return cost if cost > 0 else 0.0
    return 0.0
