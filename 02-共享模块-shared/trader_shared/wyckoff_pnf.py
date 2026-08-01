"""威科夫 Point & Figure：建图 + 水平/垂直计数 → 因果目标价。

规格法源：docs/plans/wyckoff-pnf-handoff.md
只估目标，不改阶段/事件/出手。
"""
from __future__ import annotations

import math
from typing import Any

from trader_shared.config import (
    WYCKOFF_PNF_BOX_MIN,
    WYCKOFF_PNF_BOX_PCT,
    WYCKOFF_PNF_ENABLED,
    WYCKOFF_PNF_INCLUDE_REVERSAL,
    WYCKOFF_PNF_MIN_COLUMNS,
    WYCKOFF_PNF_MIN_TR_QUALITY,
    WYCKOFF_PNF_REVERSAL,
    WYCKOFF_PNF_VERTICAL_ENABLED,
)
from trader_shared.light_data import to_float

METHOD_HORIZONTAL = "horizontal"
METHOD_VERTICAL = "vertical"
METHOD_HEIGHT_1TO1 = "height_1to1_fallback"


def _empty_ce(note: str) -> dict[str, Any]:
    return {
        "cause_effect_up_target": None,
        "cause_effect_down_target": None,
        "cause_effect_range": None,
        "cause_effect_note": note,
        "pnf_box_size": None,
        "pnf_columns": None,
        "pnf_method": None,
    }


def resolve_box_size(
    tr_upper: float,
    tr_lower: float,
    *,
    box_pct: float | None = None,
    box_min: float | None = None,
) -> float:
    """Box = max(TR 中轴 × pct, box_min)。"""
    pct = WYCKOFF_PNF_BOX_PCT if box_pct is None else float(box_pct)
    floor = WYCKOFF_PNF_BOX_MIN if box_min is None else float(box_min)
    mid = (tr_upper + tr_lower) / 2.0
    if mid <= 0:
        return max(floor, 0.01)
    return max(mid * pct, floor)


def price_to_box(price: float, box_size: float) -> int:
    return int(math.floor(price / box_size + 1e-12))


def build_pnf_columns(
    bars: list[dict],
    box_size: float,
    reversal: int | None = None,
) -> list[dict[str, Any]]:
    """从 OHLC 构建 P&F 列（High-Low 法，3 格转向默认）。

    每列：{direction: 'X'|'O', top: int, bottom: int, box_count: int}
    """
    if box_size <= 0 or not bars:
        return []
    rev = WYCKOFF_PNF_REVERSAL if reversal is None else int(reversal)
    if rev < 1:
        return []

    columns: list[dict[str, Any]] = []
    pending_box: int | None = None

    def _ohlc(bar: dict) -> tuple[float, float, float] | None:
        h = to_float(bar.get("high"))
        l = to_float(bar.get("low"))
        c = to_float(bar.get("close"))
        if h is None or l is None or c is None:
            return None
        if h < l:
            h, l = l, h
        return h, l, c

    def _push(direction: str, top: int, bottom: int) -> None:
        if top < bottom:
            top, bottom = bottom, top
        columns.append(
            {
                "direction": direction,
                "top": top,
                "bottom": bottom,
                "box_count": top - bottom + 1,
            }
        )

    def _extend_x(h_box: int) -> None:
        col = columns[-1]
        if h_box > col["top"]:
            col["top"] = h_box
            col["box_count"] = col["top"] - col["bottom"] + 1

    def _extend_o(l_box: int) -> None:
        col = columns[-1]
        if l_box < col["bottom"]:
            col["bottom"] = l_box
            col["box_count"] = col["top"] - col["bottom"] + 1

    for bar in bars:
        ohlc = _ohlc(bar)
        if ohlc is None:
            continue
        high, low, close = ohlc
        h_box = price_to_box(high, box_size)
        l_box = price_to_box(low, box_size)
        c_box = price_to_box(close, box_size)

        if not columns:
            if pending_box is None:
                pending_box = c_box
                continue
            # 相对初始格：上涨开 X，下跌开 O；同格则继续等。开列当日不再转向。
            if h_box > pending_box:
                _push("X", h_box, pending_box)
                pending_box = None
                continue
            if l_box < pending_box:
                _push("O", pending_box, l_box)
                pending_box = None
                continue
            continue

        # 经典 High-Low：当日能延伸则只延伸、忽略反向；不能延伸才检查转向。
        direction = columns[-1]["direction"]
        if direction == "X":
            if h_box > columns[-1]["top"]:
                _extend_x(h_box)
            else:
                top = columns[-1]["top"]
                if l_box <= top - rev:
                    new_top = top - 1
                    new_bottom = min(l_box, new_top)
                    _push("O", new_top, new_bottom)
        else:
            if l_box < columns[-1]["bottom"]:
                _extend_o(l_box)
            else:
                bottom = columns[-1]["bottom"]
                if h_box >= bottom + rev:
                    new_bottom = bottom + 1
                    new_top = max(h_box, new_bottom)
                    _push("X", new_top, new_bottom)

    return columns


def columns_overlapping_tr(
    columns: list[dict[str, Any]],
    tr_upper: float,
    tr_lower: float,
    box_size: float,
) -> list[dict[str, Any]]:
    """列价格带与 [tr_lower, tr_upper] 有交集则计入水平计数。"""
    if box_size <= 0:
        return []
    out: list[dict[str, Any]] = []
    for col in columns:
        # 列覆盖 [bottom*box, (top+1)*box)
        col_lo = col["bottom"] * box_size
        col_hi = (col["top"] + 1) * box_size
        if col_lo <= tr_upper and col_hi > tr_lower:
            out.append(col)
    return out


def _effect_from_units(units: int, box_size: float, *, include_reversal: bool, reversal: int) -> float:
    effect = units * box_size
    if include_reversal:
        effect *= reversal
    return effect


def _project(
    tr_upper: float,
    tr_lower: float,
    effect: float,
    *,
    method: str,
    note: str,
    box_size: float | None,
    columns: int | None,
) -> dict[str, Any]:
    return {
        "cause_effect_up_target": round(tr_upper + effect, 2),
        "cause_effect_down_target": round(tr_lower - effect, 2),
        "cause_effect_range": round(effect, 2),
        "cause_effect_note": note,
        "pnf_box_size": round(box_size, 4) if box_size is not None else None,
        "pnf_columns": columns,
        "pnf_method": method,
    }


def _height_1to1(
    tr_upper: float,
    tr_lower: float,
    note: str,
    *,
    box_size: float | None = None,
    columns: int | None = None,
) -> dict[str, Any]:
    height = tr_upper - tr_lower
    return _project(
        tr_upper,
        tr_lower,
        height,
        method=METHOD_HEIGHT_1TO1,
        note=note,
        box_size=box_size,
        columns=columns,
    )


def _slice_tr_bars(bars: list[dict], tr_ctx: dict) -> list[dict]:
    n = len(bars)
    if n == 0:
        return []
    start = tr_ctx.get("tr_start")
    end = tr_ctx.get("tr_end")
    try:
        s = int(start) if start is not None else 0
        e = int(end) if end is not None else n - 1
    except (TypeError, ValueError):
        return list(bars)
    s = max(0, min(s, n - 1))
    e = max(s, min(e, n - 1))
    return bars[s : e + 1]


def compute_cause_effect_targets(
    tr_ctx: dict | None,
    bars: list[dict] | None = None,
    *,
    enabled: bool | None = None,
    box_pct: float | None = None,
    box_min: float | None = None,
    reversal: int | None = None,
    min_columns: int | None = None,
    vertical_enabled: bool | None = None,
    include_reversal: bool | None = None,
    min_tr_quality: float | None = None,
) -> dict[str, Any]:
    """因果律目标：P&F 水平计数主路径，垂直/高度 1:1 降级。"""
    if not tr_ctx:
        return _empty_ce("无有效 TR，无法做因果目标")
    try:
        upper = float(tr_ctx["tr_upper"])
        lower = float(tr_ctx["tr_lower"])
    except (TypeError, ValueError, KeyError):
        return _empty_ce("无有效 TR，无法做因果目标")
    if upper <= lower:
        return _empty_ce("无有效 TR，无法做因果目标")

    pnf_on = WYCKOFF_PNF_ENABLED if enabled is None else bool(enabled)
    rev = WYCKOFF_PNF_REVERSAL if reversal is None else int(reversal)
    # 至少 1 列：min_columns≤0 时禁止把「0 列 → effect=0」当成水平成功
    min_cols = max(
        1,
        WYCKOFF_PNF_MIN_COLUMNS if min_columns is None else int(min_columns),
    )
    vert_on = (
        WYCKOFF_PNF_VERTICAL_ENABLED if vertical_enabled is None else bool(vertical_enabled)
    )
    inc_rev = (
        WYCKOFF_PNF_INCLUDE_REVERSAL
        if include_reversal is None
        else bool(include_reversal)
    )
    q_floor = (
        WYCKOFF_PNF_MIN_TR_QUALITY if min_tr_quality is None else float(min_tr_quality)
    )

    quality = tr_ctx.get("tr_quality")
    quality_f: float | None
    try:
        quality_f = float(quality) if quality is not None else None
    except (TypeError, ValueError):
        quality_f = None
    low_q_note = ""
    if quality_f is not None and q_floor > 0 and quality_f < q_floor:
        low_q_note = f"；低质量 TR({quality_f:.2f}<{q_floor:.2f})"
        # 质量门槛触发时强制 1:1（诚实降级，不假装 P&F）
        height = upper - lower
        return _height_1to1(
            upper,
            lower,
            (
                f"TR 质量不足，回退高度 1:1 投射（高度 {height:.2f}）"
                f"{low_q_note}"
            ),
        )

    if not pnf_on:
        height = upper - lower
        return _height_1to1(
            upper,
            lower,
            (
                f"P&F 已关闭；TR 高度 {height:.2f} 作 1:1 投射"
                f"{low_q_note}"
            ),
        )

    box_size = resolve_box_size(upper, lower, box_pct=box_pct, box_min=box_min)
    bar_list = list(bars or [])
    if not bar_list:
        height = upper - lower
        return _height_1to1(
            upper,
            lower,
            (
                f"缺 K 线，无法建 P&F；回退高度 1:1 投射（高度 {height:.2f}）"
                f"{low_q_note}"
            ),
            box_size=box_size,
        )

    tr_bars = _slice_tr_bars(bar_list, tr_ctx)
    columns = build_pnf_columns(tr_bars, box_size, reversal=rev)
    if not columns:
        height = upper - lower
        return _height_1to1(
            upper,
            lower,
            (
                f"P&F 建图失败（无有效列）；回退高度 1:1 投射（高度 {height:.2f}）"
                f"{low_q_note}"
            ),
            box_size=box_size,
            columns=0,
        )

    overlap = columns_overlapping_tr(columns, upper, lower, box_size)
    n_overlap = len(overlap)

    if n_overlap >= min_cols:
        effect = _effect_from_units(
            n_overlap, box_size, include_reversal=inc_rev, reversal=rev
        )
        rev_txt = f"×转向{rev}" if inc_rev else ""
        return _project(
            upper,
            lower,
            effect,
            method=METHOD_HORIZONTAL,
            note=(
                f"P&F 水平计数：{n_overlap} 列 × box {box_size:.4f}{rev_txt}"
                f" → effect {effect:.2f}；"
                f"↑{upper:.2f}+effect / ↓{lower:.2f}-effect"
                f"{low_q_note}"
            ),
            box_size=box_size,
            columns=n_overlap,
        )

    if vert_on and overlap:
        tallest = max(overlap, key=lambda c: int(c.get("box_count") or 0))
        box_count = int(tallest.get("box_count") or 0)
        if box_count >= 1:
            effect = _effect_from_units(
                box_count, box_size, include_reversal=inc_rev, reversal=rev
            )
            rev_txt = f"×转向{rev}" if inc_rev else ""
            return _project(
                upper,
                lower,
                effect,
                method=METHOD_VERTICAL,
                note=(
                    f"水平列不足({n_overlap}<{min_cols})，垂直计数降级："
                    f"{box_count} 格 × box {box_size:.4f}{rev_txt}"
                    f" → effect {effect:.2f}"
                    f"{low_q_note}"
                ),
                box_size=box_size,
                columns=n_overlap,
            )

    height = upper - lower
    return _height_1to1(
        upper,
        lower,
        (
            f"P&F 计数失败（水平列 {n_overlap}<{min_cols}"
            f"{'，垂直未启用或不可用' if not vert_on or not overlap else ''}）；"
            f"回退高度 1:1 投射（高度 {height:.2f}）"
            f"{low_q_note}"
        ),
        box_size=box_size,
        columns=n_overlap,
    )
