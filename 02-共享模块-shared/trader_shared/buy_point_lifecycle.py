"""买点「盖」生命周期：L1 当日判定 + L2 跨日持久化。

契约：docs/designs/buy-point-lid-lifecycle.md
- 收盘 < 盖 → failed
- 盘中 < 盖 且 收盘 ≥ 盖 → watching（不判死）
- 收盘 ≥ 盖 且有买点 → active
- 无买点 → none

L2：failed 写入 ~/.trader/buy_point_lifecycle.json；跨日禁止接旧 signal_id；
站回后只允许新 signal_id（新序列），不得复活失败记录里的旧 id。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from trader_shared.json_atomic import load_json_dict, locked_rmw_json
from trader_shared.signal_utils import normalize_signal_id

_STORE_ENV = "TRADER_BUY_POINT_LIFECYCLE_PATH"
_DEFAULT_STORE = Path(os.path.expanduser("~/.trader/buy_point_lifecycle.json"))


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except (TypeError, ValueError):
        return None


def store_path() -> Path:
    override = (os.environ.get(_STORE_ENV) or "").strip()
    return Path(override) if override else _DEFAULT_STORE


def _has_buy_signal(
    buy_point_types: list[str] | None = None,
    chan_result: Any = None,
) -> bool:
    keys = ("一类买", "类一买", "二类买", "三类买", "类二买", "一买", "二买", "三买", "底背驰")
    for t in buy_point_types or []:
        s = str(t)
        if any(k in s for k in keys):
            return True
    chan: dict = {}
    if isinstance(chan_result, dict):
        chan = chan_result.get("chanlun") if isinstance(chan_result.get("chanlun"), dict) else chan_result
    if not isinstance(chan, dict):
        return False
    for bp in chan.get("buy_points") or []:
        if isinstance(bp, dict) and any(k in str(bp.get("type") or "") for k in keys):
            return True
    div = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    if div.get("bottom_divergence"):
        return True
    return False


def resolve_lid_price(
    *,
    support: float | None = None,
    mid_pullback_low: float | None = None,
    buy_zone_low: float | None = None,
    explicit_lid: float | None = None,
) -> float | None:
    """盖价：显式 > 回踩下沿 > 买点区下沿 > 结构支撑。"""
    for v in (explicit_lid, mid_pullback_low, buy_zone_low, support):
        fv = _f(v)
        if fv is not None and fv > 0:
            return round(fv, 4)
    return None


def evaluate_buy_point_lifecycle(
    *,
    current: float | None = None,
    last_close: float | None = None,
    lid_price: float | None = None,
    has_buy_signal: bool = False,
    intraday: bool = False,
) -> dict[str, Any]:
    """返回 buy_point_lifecycle 字段（当日判定，不含持久化）。"""
    lid = _f(lid_price)
    cur = _f(current)
    close = _f(last_close)
    if close is None:
        close = cur

    if not has_buy_signal or lid is None or lid <= 0:
        return {
            "status": "none",
            "lid_price": lid,
            "signal_id": None,
            "failed_date": None,
            "note": "无买点或无盖价",
            "display_line": "",
        }

    # 收盘证伪
    if close is not None and close < lid:
        note = f"收盘破盖 {lid:.2f}，买点作废（须重走站上→回踩）"
        return {
            "status": "failed",
            "lid_price": lid,
            "signal_id": None,
            "failed_date": None,
            "note": note,
            "display_line": f"买点：已失效（破 {lid:.2f}，须重走）",
        }

    # 盘中刺穿、收盘仍在盖上
    if (
        intraday
        and cur is not None
        and close is not None
        and cur < lid <= close
    ):
        note = f"盘中刺穿盖 {lid:.2f}，收盘站回，先不判死"
        return {
            "status": "watching",
            "lid_price": lid,
            "signal_id": None,
            "failed_date": None,
            "note": note,
            "display_line": f"买点：观察中（刺穿 {lid:.2f} 已收回）",
        }

    note = f"买点有效，盖 {lid:.2f}"
    return {
        "status": "active",
        "lid_price": lid,
        "signal_id": None,
        "failed_date": None,
        "note": note,
        "display_line": f"买点：有效（守 {lid:.2f}）",
    }


def _load_store(path: Path | None = None) -> dict[str, Any]:
    return load_json_dict(path or store_path())


def _save_store(data: dict[str, Any], path: Path | None = None) -> None:
    """全量写（须已持有外部语义一致的数据）；优先用 locked_rmw 入口。"""
    p = path or store_path()

    def _mutate(_old: dict[str, Any]) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    try:
        locked_rmw_json(p, _mutate)
    except OSError:
        pass


def load_failed_record(symbol: str, *, path: Path | None = None) -> dict[str, Any] | None:
    key = _symbol_key(symbol)
    if not key:
        return None
    rec = _load_store(path).get(key)
    if not isinstance(rec, dict):
        return None
    if str(rec.get("status") or "") != "failed":
        return None
    return rec


def save_failed_record(
    symbol: str,
    *,
    signal_id: str,
    lid_price: float | None,
    failed_date: str,
    path: Path | None = None,
) -> None:
    key = _symbol_key(symbol)
    if not key or not signal_id:
        return
    p = path or store_path()
    payload = {
        "status": "failed",
        "signal_id": str(signal_id),
        "lid_price": _f(lid_price),
        "failed_date": str(failed_date),
    }

    def _mutate(store: dict[str, Any]) -> dict[str, Any]:
        store[key] = payload
        return store

    try:
        locked_rmw_json(p, _mutate)
    except OSError:
        pass


def clear_failed_record(symbol: str, *, path: Path | None = None) -> None:
    key = _symbol_key(symbol)
    if not key:
        return
    p = path or store_path()

    def _mutate(store: dict[str, Any]) -> dict[str, Any] | None:
        if key not in store:
            return None
        store.pop(key, None)
        return store

    try:
        locked_rmw_json(p, _mutate)
    except OSError:
        pass


def mint_lifecycle_signal_id(
    symbol: str,
    trade_date: str,
    lid_price: float | None,
) -> str:
    """生命周期自有 signal_id（与缠论 bp id 隔离，source_skill=buy_lid）。"""
    return normalize_signal_id(
        symbol,
        trade_date,
        "buy_point_lid",
        lid_price if lid_price is not None else 0,
        source_skill="buy_lid",
    )


def _symbol_key(symbol: Any) -> str:
    s = str(symbol or "").strip().upper()
    if not s:
        return ""
    # 统一 6 位.SH/SZ 或纯代码
    try:
        from trader_shared.signal_utils import normalize_symbol
        return normalize_symbol(s)
    except Exception:
        return s


def _trade_date_from_report(report: dict[str, Any]) -> str:
    for key in ("trade_date", "analysis_date", "intraday_as_of"):
        v = report.get(key)
        if v:
            return str(v)[:10]
    bars = report.get("daily_bars") or report.get("bars") or []
    if bars and isinstance(bars[-1], dict):
        d = bars[-1].get("date") or bars[-1].get("trade_date")
        if d:
            return str(d)[:10]
    try:
        from trader_shared.cn_time import today_cn
        return today_cn().isoformat()
    except Exception:
        return date.today().isoformat()


def _symbol_from_report(report: dict[str, Any]) -> str:
    for key in ("symbol", "ts_code", "code"):
        v = report.get(key)
        if v:
            return _symbol_key(v)
    return ""


def extract_candidate_signal_id(report: dict[str, Any] | None = None) -> str | None:
    """优先取缠论买点上的 signal_id。"""
    r = report if isinstance(report, dict) else {}
    chan = r.get("chanlun") or r.get("chanlun_daily") or {}
    if isinstance(chan, dict) and isinstance(chan.get("chanlun"), dict):
        chan = chan["chanlun"]
    if not isinstance(chan, dict):
        return None
    for bp in chan.get("buy_points") or []:
        if not isinstance(bp, dict):
            continue
        sid = bp.get("signal_id")
        if sid:
            return str(sid)
    return None


def reconcile_with_store(
    life: dict[str, Any],
    *,
    symbol: str,
    trade_date: str,
    candidate_signal_id: str | None = None,
    persist: bool = True,
    path: Path | None = None,
) -> dict[str, Any]:
    """L2：对照持久化失败记录，禁止接旧 signal_id；站回签发新 id。"""
    out = dict(life) if isinstance(life, dict) else {}
    sym = _symbol_key(symbol)
    if str(trade_date or "").strip()[:10]:
        td = str(trade_date)[:10]
    else:
        try:
            from trader_shared.cn_time import today_cn
            td = today_cn().isoformat()
        except Exception:
            td = date.today().isoformat()
    lid = _f(out.get("lid_price"))
    status = str(out.get("status") or "none")
    prev = load_failed_record(sym, path=path) if sym else None
    cand = (candidate_signal_id or out.get("signal_id") or None)
    if cand is not None:
        cand = str(cand)

    def _failed_payload(
        *,
        signal_id: str | None,
        failed_date: str | None,
        note: str,
        display: str,
        blocked: bool = False,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "lid_price": lid if lid is not None else _f((prev or {}).get("lid_price")),
            "signal_id": signal_id,
            "failed_date": failed_date,
            "note": note,
            "display_line": display,
            "blocked_reuse": blocked,
        }

    # 当日失败 → 落盘
    if status == "failed":
        sid = cand or mint_lifecycle_signal_id(sym or "UNKNOWN", td, lid)
        out["signal_id"] = sid
        out["failed_date"] = td
        if persist and sym:
            save_failed_record(
                sym, signal_id=sid, lid_price=lid, failed_date=td, path=path
            )
        return out

    # 无本地失败记录：active/watching 补 id
    if not prev:
        if status in ("active", "watching"):
            out["signal_id"] = cand or mint_lifecycle_signal_id(sym or "UNKNOWN", td, lid)
        return out

    old_sid = str(prev.get("signal_id") or "")
    old_failed = str(prev.get("failed_date") or "")[:10]
    prev_lid = _f(prev.get("lid_price"))
    show_lid = lid if lid is not None else prev_lid

    # 仍无当日买点/盖：继续展示历史失败（跨日记忆）
    if status == "none":
        lid_txt = f"{show_lid:.2f}" if show_lid is not None else "?"
        return _failed_payload(
            signal_id=old_sid or None,
            failed_date=old_failed or None,
            note=f"旧买点已于 {old_failed or '?'} 作废，须重走站上→回踩",
            display=f"买点：已失效（破 {lid_txt}，须重走）",
            blocked=True,
        )

    # 站回 active/watching：仅允许新 id，且须跨过失败日
    if status in ("active", "watching"):
        cross_day = bool(old_failed and td > old_failed)
        new_sid = cand
        if not new_sid or new_sid == old_sid:
            if cross_day:
                new_sid = mint_lifecycle_signal_id(sym or "UNKNOWN", td, show_lid)
            else:
                new_sid = None

        if cross_day and new_sid and new_sid != old_sid:
            out["signal_id"] = new_sid
            out["failed_date"] = None
            out["note"] = (
                f"新序列（旧信号已作废于 {old_failed}）；" + str(out.get("note") or "")
            ).rstrip("；")
            out["blocked_reuse"] = False
            if persist and sym:
                clear_failed_record(sym, path=path)
            return out

        lid_txt = f"{show_lid:.2f}" if show_lid is not None else "?"
        return _failed_payload(
            signal_id=old_sid or None,
            failed_date=old_failed or None,
            note=(
                f"禁止接旧信号 {old_sid[:8] + '…' if len(old_sid) > 8 else old_sid}；"
                f"须重走站上→回踩（失败日 {old_failed or '?'}）"
            ),
            display=f"买点：已失效（破 {lid_txt}，须重走）",
            blocked=True,
        )

    return out


def build_buy_point_lifecycle_for_report(
    report: dict[str, Any] | None = None,
    *,
    persist: bool = True,
    store: Path | None = None,
) -> dict[str, Any]:
    """从 report-like dict 组装 lifecycle（含 L2 持久化对账）。"""
    r = report if isinstance(report, dict) else {}
    kp = r.get("key_prices") if isinstance(r.get("key_prices"), dict) else {}
    mid = r.get("mid_key_prices") if isinstance(r.get("mid_key_prices"), dict) else {}
    disc = r.get("discipline") if isinstance(r.get("discipline"), dict) else {}
    _ = disc  # 保留读取点，避免误删 checklist 扩展位

    types: list[str] = list(r.get("chan_buy_point_types") or [])
    chan = r.get("chanlun") or r.get("chanlun_daily")
    has = _has_buy_signal(types, chan)

    lid = resolve_lid_price(
        support=_f(r.get("support")),
        # life_line 是中线结构支撑，不是回踩下沿；不得抢在 buy_zone_low 之前
        mid_pullback_low=_f(mid.get("pullback_low")),
        buy_zone_low=_f(kp.get("buy_zone_low") or kp.get("buy_ref")),
        explicit_lid=_f(r.get("buy_lid_price")),
    )

    bars = r.get("daily_bars") or r.get("bars") or []
    last_close = None
    if bars and isinstance(bars[-1], dict):
        last_close = _f(bars[-1].get("close"))
    current = _f(r.get("current"))
    intraday = bool(
        r.get("intraday_as_of")
        or (
            current is not None
            and last_close is not None
            and abs(current - last_close) > 1e-6
        )
    )

    life = evaluate_buy_point_lifecycle(
        current=current,
        last_close=last_close if last_close is not None else current,
        lid_price=lid,
        has_buy_signal=has,
        intraday=intraday,
    )

    symbol = _symbol_from_report(r)
    trade_date = _trade_date_from_report(r)
    candidate = extract_candidate_signal_id(r)
    if symbol or persist:
        life = reconcile_with_store(
            life,
            symbol=symbol,
            trade_date=trade_date,
            candidate_signal_id=candidate,
            persist=bool(persist and symbol),
            path=store,
        )
    return life
