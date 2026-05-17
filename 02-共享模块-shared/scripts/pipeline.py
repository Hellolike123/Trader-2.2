from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".trader" / "pipeline_state.json"
STATE_DIR = STATE_PATH.parent

STATE_SCHEMA = {
    "version": 1,
    "fields": ["updated", "stocks", "market", "positions", "warnings"]
}


def _ensure_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict[str, Any]:
    _ensure_dir()
    if not STATE_PATH.exists():
        return _empty()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty()
        return data
    except (json.JSONDecodeError, OSError):
        return _empty()


def _save(data: dict[str, Any]) -> None:
    _ensure_dir()
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(STATE_PATH))
    except OSError:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        print("WARN: pipeline atomic write failed, using non-atomic fallback", file=sys.stderr)
        _write_fallback(data)


def _write_fallback(data: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _empty() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated": "",
        "stocks": {},
        "market": {},
        "positions": {},
        "warnings": [],
    }


def write(field: str, data: dict[str, Any], override: bool = False) -> None:
    """Atomically write/update a named field in pipeline_state.json."""
    raw_data = data
    state = _load()
    
    if field in ("stocks", "positions") and not override:
        existing = state.get(field, {})
        existing.update(raw_data)
        existing["updated"] = _now()
        state[field] = existing
    elif field == "warnings" and not override:
        if not isinstance(raw_data, list):
            raise TypeError(f"write('warnings'): expected list, got {type(raw_data).__name__}")
        existing = state.get("warnings", [])
        existing.extend(raw_data)
        state["warnings"] = _dedup_warn(existing)
    else:
        if not isinstance(raw_data, dict):
            raise TypeError(f"write('{field}'): expected dict, got {type(raw_data).__name__}")
        state[field] = {**state.get(field, {}), **raw_data, "updated": _now()}
    state["updated"] = _now()
    _save(state)


def write_stock(name: str, status: str, weight: int, source: str) -> None:
    data = _load()
    stocks = data.setdefault("stocks", {})
    stocks[name] = {
        "status": status,
        "weight": weight,
        "from": source,
        "updated": _now(),
    }
    data["updated"] = _now()
    _save(data)


def write_market(level: str, note: str) -> None:
    data = _load()
    data["market"] = {"level": level, "note": note, "updated": _now()}
    data["updated"] = _now()
    _save(data)


def write_positions(total_pct: float, cash_pct: float, holdings: list[str]) -> None:
    data = _load()
    data["positions"] = {
        "total": total_pct,
        "cash": cash_pct,
        "holdings": holdings,
        "updated": _now(),
    }
    data["updated"] = _now()
    _save(data)


def add_warning(msg: str, related_stock: str = "") -> None:
    data = _load()
    warnings = data.setdefault("warnings", [])
    today = _today()
    key = f"{related_stock}::{msg}::{today}"
    if any(w.get("_key") == key for w in warnings):
        return
    warnings.append({
        "msg": msg,
        "stock": related_stock,
        "time": _now(),
        "_key": key,
    })
    MAX_WARNINGS = 50
    if len(warnings) > MAX_WARNINGS:
        warnings = warnings[-MAX_WARNINGS:]
    data["warnings"] = warnings
    data["updated"] = _now()
    _save(data)


def clear_old_warnings(days: int = 3) -> int:
    data = _load()
    warnings = data.get("warnings", [])
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    before = len(warnings)
    warnings = [w for w in warnings if str(w.get("time", "")[:10]) >= cutoff]
    if len(warnings) != before:
        data["warnings"] = warnings
        data["updated"] = _now()
        _save(data)
    return before - len(warnings)


def get_stock_weight(name: str) -> int:
    data = _load()
    stock = data.get("stocks", {}).get(name, {})
    return int(stock.get("weight") or 0)


def get_market_level() -> str:
    data = _load()
    return str(data.get("market", {}).get("level") or "")


def get_market_note() -> str:
    data = _load()
    return str(data.get("market", {}).get("note") or "")


def get_full_market() -> dict[str, Any]:
    data = _load()
    result = dict(data.get("market", {}))
    result.setdefault("level", "未知")
    return result


def _symbol_bare_digits(symbol: str) -> str:
    """Extract just the 6-digit code from any symbol format.
    
    E.g. '688248.SH' → '688248', '688248' → '688248', '南网科技' → ''.
    """
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    # Strip known exchange suffixes
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    if len(s) == 6 and s.isdigit():
        return s
    return ""


def _symbols_match(a: str, b: str) -> bool:
    bare_a = _symbol_bare_digits(a)
    bare_b = _symbol_bare_digits(b)
    if bare_a and bare_b:
        return bare_a == bare_b
    # 一方或双方是中文名或非标准代码，直接字符串匹配
    return a.strip().lower() == b.strip().lower()


def conflicting_signals(name: str) -> list[str]:
    """Return warnings matching the stock by name, code, or normalized symbol.
    
    FIX: Skip warnings with empty stock (global/no-owner warnings) so they
    don't leak into every stock's conflict list.  Only return warnings that
    are explicitly about this stock by name/code/symbol.
    """
    state = _load()
    results: list[str] = []
    for w in state.get("warnings", []):
        stock = str(w.get("stock") or "")
        if stock == "":
            # Global warning — do not leak into per-stock queries
            continue
        if stock == name:
            results.append(str(w.get("msg") or ""))
            continue
        if _symbols_match(stock, name):
            results.append(str(w.get("msg") or ""))
    return list(dict.fromkeys(results))


def _is_short_number(s: str) -> bool:
    """True if s looks like a bare 6-digit stock code (no exchange suffix)."""
    s = (s or "").strip()
    return len(s) == 6 and s.isdigit() and "." not in s


def _normalize_symbol(symbol: str) -> str:
    """Map a bare 6-digit code to its exchange-suffix form (e.g. 688248 -> 688248.SH)."""
    if not symbol:
        return symbol
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9", "5")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _dedup_warn(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for w in warnings:
        key = w.get("_key", f"{w.get('stock', '')}::{w.get('msg', '')}::{_today()}")
        if key not in seen:
            seen.add(key)
            result.append(w)
    return result


def read() -> dict[str, Any]:
    return _load()


if __name__ == "__main__":
    write_stock("南网科技", "低吸观察", 80, "trader")
    write_market("偏弱", "中证1000 五日线下 + 今日跌1.2%")
    add_warning("日线和T0信号冲突，等统一再动手", "南网科技")
    state = read()
    print("stocks:", state.get("stocks"))
    print("market:", state.get("market"))
    print("warnings:", state.get("warnings"))
    print("南网科技 weight:", get_stock_weight("南网科技"))
    print("conflicts:", conflicting_signals("南网科技"))
