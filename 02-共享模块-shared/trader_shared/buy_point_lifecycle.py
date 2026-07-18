"""买点「盖」生命周期 L1：状态机 + 展示字段（不进 fusion 分数）。

契约：docs/designs/buy-point-lid-lifecycle.md
- 收盘 < 盖 → failed
- 盘中 < 盖 且 收盘 ≥ 盖 → watching（不判死）
- 收盘 ≥ 盖 且有买点 → active
- 无买点 → none

L1 不持久化 failed 后的「重走站上→回踩」序列（L2）；仅当根/当日判定。
"""
from __future__ import annotations

from typing import Any


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
    """返回 buy_point_lifecycle 字段。"""
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
            "display_line": f"买点：已失效（盖 {lid:.2f}）",
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
            "display_line": f"买点：观察中（盘中破盖 {lid:.2f}，收盘收回）",
        }

    note = f"买点有效，盖 {lid:.2f}"
    return {
        "status": "active",
        "lid_price": lid,
        "signal_id": None,
        "failed_date": None,
        "note": note,
        "display_line": f"买点：有效（盖 {lid:.2f}）",
    }


def build_buy_point_lifecycle_for_report(report: dict[str, Any] | None = None) -> dict[str, Any]:
    """从 report-like dict 组装 lifecycle（report_builder / ensure 调用）。"""
    r = report if isinstance(report, dict) else {}
    kp = r.get("key_prices") if isinstance(r.get("key_prices"), dict) else {}
    mid = r.get("mid_key_prices") if isinstance(r.get("mid_key_prices"), dict) else {}
    disc = r.get("discipline") if isinstance(r.get("discipline"), dict) else {}
    cl = disc.get("entry_checklist") if isinstance(disc.get("entry_checklist"), dict) else {}

    types: list[str] = list(r.get("chan_buy_point_types") or [])
    # checklist / conclusion 无 types 时扫 chanlun
    chan = r.get("chanlun") or r.get("chanlun_daily")
    has = _has_buy_signal(types, chan)

    lid = resolve_lid_price(
        support=_f(r.get("support")),
        mid_pullback_low=_f(mid.get("pullback_low") or mid.get("life_line")),
        buy_zone_low=_f(kp.get("buy_zone_low") or kp.get("buy_ref")),
        explicit_lid=_f(r.get("buy_lid_price")),
    )

    bars = r.get("daily_bars") or r.get("bars") or []
    last_close = None
    if bars and isinstance(bars[-1], dict):
        last_close = _f(bars[-1].get("close"))
    current = _f(r.get("current"))
    # 有 live 价且不同于 last_close 视为盘中
    intraday = bool(
        r.get("intraday_as_of")
        or (
            current is not None
            and last_close is not None
            and abs(current - last_close) > 1e-6
        )
    )

    return evaluate_buy_point_lifecycle(
        current=current,
        last_close=last_close if last_close is not None else current,
        lid_price=lid,
        has_buy_signal=has,
        intraday=intraday,
    )
