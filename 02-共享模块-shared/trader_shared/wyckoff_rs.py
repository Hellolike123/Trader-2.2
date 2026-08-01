"""Wyckoff 周线相对强弱（RS）：对照板块指数，仅修正置信/谨慎叙事，不改阶段机。"""
from __future__ import annotations

from typing import Any

from trader_shared.config import (
    WYCKOFF_RS_CONF_DELTA_MAX,
    WYCKOFF_RS_CONF_DELTA_MIN,
    WYCKOFF_RS_ENABLED,
    WYCKOFF_RS_LOOKBACK_WEEKS,
    WYCKOFF_RS_PREMATURE_STRONG_CAP,
    WYCKOFF_RS_SCALE,
    WYCKOFF_RS_SPRING_WEAK_EXTRA,
    WYCKOFF_RS_STRONG_THRESHOLD,
    WYCKOFF_RS_WEAK_THRESHOLD,
)
from trader_shared.light_data import to_float
from trader_shared.market_env import resolve_board_index

_NEUTRAL_RS: dict[str, Any] = {
    "rs_score": None,
    "rs_label": "neutral",
    "rs_index": "",
    "rs_index_label": "",
    "rs_note": "",
    "rs_gate": "",
    "rs_window_weeks": WYCKOFF_RS_LOOKBACK_WEEKS,
    "rs_confidence_delta": 0.0,
    "rs_stock_return": None,
    "rs_index_return": None,
    "rs_relative_return": None,
}


def _disabled_rs() -> dict[str, Any]:
    return {**_NEUTRAL_RS, "rs_gate": "disabled", "rs_note": "RS 已关闭"}


def _bar_close(bars: list[dict], idx: int) -> float | None:
    if not bars:
        return None
    try:
        return to_float(bars[idx].get("close"))
    except IndexError:
        return None


def _period_return(bars: list[dict], lookback: int) -> float | None:
    if len(bars) < lookback + 1:
        return None
    start = _bar_close(bars, -(lookback + 1))
    end = _bar_close(bars, -1)
    if start is None or end is None or start <= 0:
        return None
    return (end / start) - 1.0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_wyckoff_rs(
    stock_bars: list[dict],
    index_bars: list[dict] | None,
    *,
    index_code: str = "",
    index_label: str = "",
    lookback_weeks: int | None = None,
) -> dict[str, Any]:
    """计算周线 RS。缺数据 → neutral + rs_gate，不抛异常。"""
    lb = lookback_weeks if lookback_weeks is not None else WYCKOFF_RS_LOOKBACK_WEEKS
    base = {
        **_NEUTRAL_RS,
        "rs_index": index_code,
        "rs_index_label": index_label,
        "rs_window_weeks": lb,
    }

    stock_ret = _period_return(stock_bars, lb)
    if stock_ret is None:
        base["rs_gate"] = "insufficient_bars"
        base["rs_note"] = "数据不足"
        return base

    index_bars = index_bars or []
    if not index_bars:
        base["rs_gate"] = "missing"
        base["rs_note"] = "数据不足"
        return base

    index_ret = _period_return(index_bars, lb)
    if index_ret is None:
        base["rs_gate"] = "insufficient_bars"
        base["rs_note"] = "数据不足"
        return base

    spread = stock_ret - index_ret
    scale = WYCKOFF_RS_SCALE if WYCKOFF_RS_SCALE > 0 else 0.08
    rs_score = _clip(spread / scale, -1.0, 1.0)

    if rs_score >= WYCKOFF_RS_STRONG_THRESHOLD:
        rs_label = "strong"
        note = f"强于{index_label}" if index_label else "强于对照指数"
    elif rs_score <= WYCKOFF_RS_WEAK_THRESHOLD:
        rs_label = "weak"
        note = f"弱于{index_label}" if index_label else "弱于对照指数"
    else:
        rs_label = "neutral"
        note = f"与{index_label}同步" if index_label else "与对照指数同步"

    conf_delta = _clip(
        rs_score * WYCKOFF_RS_CONF_DELTA_MAX,
        WYCKOFF_RS_CONF_DELTA_MIN,
        WYCKOFF_RS_CONF_DELTA_MAX,
    )

    return {
        "rs_score": round(rs_score, 4),
        "rs_label": rs_label,
        "rs_index": index_code,
        "rs_index_label": index_label,
        "rs_note": note,
        "rs_gate": "",
        "rs_window_weeks": lb,
        "rs_confidence_delta": round(conf_delta, 4),
        "rs_stock_return": round(stock_ret, 4),
        "rs_index_return": round(index_ret, 4),
        "rs_relative_return": round(spread, 4),
    }


def fetch_index_weekly_bars(symbol: str, *, datalen: int | None = None) -> tuple[list[dict], str, str]:
    """按 resolve_board_index 取板块指数周线（测试可 mock）。"""
    idx_code, idx_label = resolve_board_index(symbol)
    n = datalen if datalen is not None else WYCKOFF_RS_LOOKBACK_WEEKS + 8
    try:
        from trader_shared.data_access import get_weekly

        bars = get_weekly(idx_code, datalen=n) or []
    except Exception:
        bars = []
    return bars, idx_code, idx_label


def apply_rs_confidence_to_phase(
    phase: dict[str, Any],
    rs: dict[str, Any],
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """用 RS 微调 phase_confidence_delta；禁止改 phase / phase_label / gated / premature。"""
    if not isinstance(phase, dict) or not isinstance(rs, dict):
        return phase
    signals = signals or {}

    rs_delta = float(rs.get("rs_confidence_delta") or 0.0)
    if rs.get("rs_label") == "weak" and signals.get("spring_signal"):
        rs_delta -= WYCKOFF_RS_SPRING_WEAK_EXTRA
        if phase.get("spring_premature"):
            rs_delta -= WYCKOFF_RS_SPRING_WEAK_EXTRA * 0.5

    if rs.get("rs_label") == "strong":
        cap = WYCKOFF_RS_CONF_DELTA_MAX
        if phase.get("spring_premature"):
            cap = min(cap, WYCKOFF_RS_PREMATURE_STRONG_CAP)
        if phase.get("phase_tr_gated"):
            cap = 0.0
        if rs_delta > cap:
            rs_delta = cap

    try:
        base_delta = float(phase.get("phase_confidence_delta") or 0.0)
    except (TypeError, ValueError):
        base_delta = 0.0

    event_delta = base_delta
    if phase.get("phase_confidence_delta_event") is not None:
        try:
            event_delta = float(phase["phase_confidence_delta_event"])
        except (TypeError, ValueError):
            event_delta = base_delta

    new_delta = _clip(
        base_delta + rs_delta,
        WYCKOFF_RS_CONF_DELTA_MIN - 0.12,
        WYCKOFF_RS_CONF_DELTA_MAX + 0.12,
    )
    return {
        **phase,
        "phase_confidence_delta_event": round(event_delta, 4),
        "phase_confidence_delta": round(new_delta, 4),
    }


def compute_and_apply_weekly_rs(
    stock_bars: list[dict],
    phase: dict[str, Any],
    signals: dict[str, Any],
    symbol: str,
    *,
    index_weekly_bars: list[dict] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """周线专用：算 RS 并写入 phase_confidence_delta（不改 phase）。"""
    if not WYCKOFF_RS_ENABLED:
        return phase, _disabled_rs()

    if not symbol:
        return phase, {**_NEUTRAL_RS, "rs_gate": "missing", "rs_note": "无标的代码"}

    if index_weekly_bars is not None:
        idx_code, idx_label = resolve_board_index(symbol)
        index_bars = index_weekly_bars
    else:
        index_bars, idx_code, idx_label = fetch_index_weekly_bars(symbol)

    rs = compute_wyckoff_rs(
        stock_bars,
        index_bars,
        index_code=idx_code,
        index_label=idx_label,
    )
    adjusted_phase = apply_rs_confidence_to_phase(phase, rs, signals)
    applied_rs_delta = round(
        float(adjusted_phase.get("phase_confidence_delta") or 0.0)
        - float(phase.get("phase_confidence_delta") or 0.0),
        4,
    )
    rs = {**rs, "rs_confidence_delta": applied_rs_delta}
    return adjusted_phase, rs
