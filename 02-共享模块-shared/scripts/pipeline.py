from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".trader" / "pipeline_state.json"
STATE_DIR = STATE_PATH.parent


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
    data = _load()
    data[field] = {**data.get(field, {}), **data, "updated": _now()}
    if field in ("stocks", "positions") and not override:
        existing = data.get(field, {})
        existing.update(data)
        data[field] = existing
    if field == "warnings" and not override:
        existing = data.get("warnings", [])
        existing.extend(data)
        data["warnings"] = _dedup_warn(existing)
    data["updated"] = _now()
    _save(data)


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


def conflicting_signals(name: str) -> list[str]:
    data = _load()
    results: list[str] = []
    for w in data.get("warnings", []):
        stock = str(w.get("stock") or "")
        if stock == name or stock == "":
            results.append(str(w.get("msg") or ""))
    return list(dict.fromkeys(results))


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
