"""上次加仓日持久化 — 供 T+1 冷却读取。

SSOT: ``~/.trader/last_add_dates.json``（可用 env ``TRADER_LAST_ADD_PATH`` 覆盖）。
键为规范化代码 / 裸 6 位 / 中文名（多别名同写，读时任一命中）。

写入时机（调用方）：
- 仓位状态机刚给出「回踩加仓」建议（当日防连怂）
- ``--write-signal`` 时对「回踩加仓」报告幂等再写一次
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from trader_shared._logging import get_logger

_logger = get_logger(__name__)
_LOCK = threading.Lock()

_STORE_ENV = "TRADER_LAST_ADD_PATH"
_DEFAULT_STORE = Path(os.path.expanduser("~/.trader/last_add_dates.json"))


def _store_path() -> Path:
    override = (os.environ.get(_STORE_ENV) or "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return _DEFAULT_STORE


def _today_iso() -> str:
    try:
        from trader_shared.cn_time import today_cn
        return today_cn().isoformat()
    except Exception:
        from datetime import date
        return date.today().isoformat()


def _norm_key(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        from trader_shared.signal_utils import normalize_symbol
        return normalize_symbol(s)
    except Exception:
        return s.upper()


def _alias_keys(symbol: Any = None, name: Any = None, code: Any = None) -> list[str]:
    """多别名：6位.SH/SZ、裸代码、中文名。"""
    out: list[str] = []
    seen: set[str] = set()

    def _add(v: Any) -> None:
        k = str(v or "").strip()
        if not k or k in seen:
            return
        seen.add(k)
        out.append(k)
        nk = _norm_key(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(nk)
        bare = nk.split(".")[0] if nk else ""
        if bare.isdigit() and len(bare) == 6 and bare not in seen:
            seen.add(bare)
            out.append(bare)

    _add(symbol)
    _add(code)
    _add(name)
    return out


def _load() -> dict[str, str]:
    path = _store_path()
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v)[:10] for k, v in data.items() if k and v}
    except Exception as exc:
        _logger.debug("last_add_dates load failed: %s", exc)
        return {}


def _save(data: dict[str, str]) -> None:
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        _logger.warning("last_add_dates save failed: %s", exc)


def get_last_add_date(
    symbol: Any = None,
    *,
    name: Any = None,
    code: Any = None,
) -> str | None:
    """查上次加仓日 YYYY-MM-DD；无则 None。"""
    keys = _alias_keys(symbol, name=name, code=code)
    if not keys:
        return None
    with _LOCK:
        data = _load()
    for k in keys:
        v = data.get(k)
        if v:
            return str(v)[:10]
    return None


def record_last_add(
    symbol: Any = None,
    trade_date: str | None = None,
    *,
    name: Any = None,
    code: Any = None,
) -> str:
    """记录加仓日（默认今天上海日）；返回写入的日期。"""
    td = str(trade_date or "").strip()[:10] or _today_iso()
    keys = _alias_keys(symbol, name=name, code=code)
    if not keys:
        return td
    with _LOCK:
        data = _load()
        for k in keys:
            data[k] = td
        _save(data)
    _sync_pool_item(keys, td)
    return td


def _sync_pool_item(keys: list[str], trade_date: str) -> None:
    """尽力把 pool.json 对应票也打上 last_add_date（失败静默）。"""
    try:
        path = Path(os.path.expanduser("~/.trader/pool.json"))
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items")
        if not isinstance(items, list):
            return
        keyset = {k.upper() for k in keys}
        changed = False
        for item in items:
            if not isinstance(item, dict):
                continue
            aliases = _alias_keys(
                item.get("symbol") or item.get("ts_code"),
                name=item.get("name") or item.get("target"),
                code=item.get("code"),
            )
            if any(a.upper() in keyset for a in aliases):
                if item.get("last_add_date") != trade_date:
                    item["last_add_date"] = trade_date
                    changed = True
        if changed:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        _logger.debug("pool last_add_date sync skipped: %s", exc)


def _from_pool(keys: list[str]) -> str | None:
    try:
        path = Path(os.path.expanduser("~/.trader/pool.json"))
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items") or []
        keyset = {k.upper() for k in keys}
        for item in items:
            if not isinstance(item, dict):
                continue
            aliases = _alias_keys(
                item.get("symbol") or item.get("ts_code"),
                name=item.get("name") or item.get("target"),
                code=item.get("code"),
            )
            if any(a.upper() in keyset for a in aliases):
                v = item.get("last_add_date")
                if v:
                    return str(v)[:10]
    except Exception:
        return None
    return None


def resolve_last_add_date(
    symbol: Any = None,
    *,
    name: Any = None,
    code: Any = None,
    report: dict[str, Any] | None = None,
) -> str | None:
    """解析上次加仓日：report 显式 > 本地 store > pool 字段。"""
    if isinstance(report, dict):
        v = report.get("last_add_date")
        if v:
            return str(v)[:10]
    keys = _alias_keys(symbol, name=name, code=code)
    hit = get_last_add_date(symbol, name=name, code=code)
    if hit:
        return hit
    return _from_pool(keys)


def maybe_record_from_report(report: dict[str, Any] | None) -> None:
    """报告仓位状态为「回踩加仓」时记今日加仓意图（防同日连怂）。"""
    if not isinstance(report, dict):
        return
    ps = report.get("position_state")
    if not isinstance(ps, dict) or ps.get("state") != "回踩加仓":
        return
    record_last_add(
        report.get("symbol") or report.get("ts_code"),
        name=report.get("name"),
        code=report.get("code"),
    )
