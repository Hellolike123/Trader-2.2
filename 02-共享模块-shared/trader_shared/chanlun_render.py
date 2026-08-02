"""缠论专项结构卡渲染（微信安全；只读引擎薄 view）。

法源：docs/plans/chanlun-cd-followup-handoff.md §2.3 / §3。
禁止在此模块重算笔或从其他文案补出买卖点。
"""
from __future__ import annotations

from typing import Any


_DIRECTION_LABEL = {
    "up": "向上笔",
    "down": "向下笔",
}
_DIRECTION_ARROW = {
    "up": "↑",
    "down": "↓",
}
_ADJUST_LABEL = {
    "qfq": "前复权",
    "hfq": "后复权",
    "none": "未复权",
    "mixed": "混合",
    "unknown": "未知",
    "mixed/unknown": "混合／未知",
}


def _fmt_price(value: Any) -> str | None:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None


def _fmt_points(points: Any) -> str:
    """仅展示引擎给出的 type/price；空数组不得推断或手补。"""
    if not isinstance(points, list):
        return "未形成"
    rendered: list[str] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        point_type = str(point.get("type") or "").strip()
        if not point_type:
            continue
        price = _fmt_price(point.get("price"))
        rendered.append(f"{point_type} {price}" if price else point_type)
    return "、".join(rendered) if rendered else "未形成"


def _tip_leave_label(view: dict[str, Any]) -> str:
    """C-D4e：笔尖离价降级文案（与 conclusion_block 同源语义）。"""
    tip = str(view.get("tip_leave") or "")
    if tip == "up_left":
        return "高点已离开·向下未成笔"
    if tip == "down_left":
        return "低点已离开·向上未成笔"
    return ""


def _fmt_current_direction(view: dict[str, Any]) -> str:
    demoted = _tip_leave_label(view)
    if demoted:
        return demoted
    direction = str(view.get("current_stroke_direction") or "")
    return _DIRECTION_LABEL.get(direction, "未形成")


def _fmt_recent_directions(view: dict[str, Any]) -> str:
    directions = view.get("recent_stroke_directions")
    if not isinstance(directions, list):
        return "—"
    arrows = [
        _DIRECTION_ARROW[str(direction)]
        for direction in directions
        if str(direction) in _DIRECTION_ARROW
    ]
    return "".join(arrows) if arrows else "—"


def _fmt_structure(view: dict[str, Any]) -> str:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    structure = str(view.get("structure_type") or "").strip()
    return structure if structure and structure != "无结构" else "中枢未成型"


def _fmt_trend(view: dict[str, Any]) -> str:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    demoted = _tip_leave_label(view)
    if demoted:
        return demoted
    return str(view.get("trend_label") or "暂无明确走势")


def _midline_heading(view: dict[str, Any]) -> str:
    timeframe = str(view.get("timeframe") or "insufficient")
    if timeframe == "weekly":
        return "⏱ 中线副读（周）"
    if timeframe == "daily_fallback":
        return "⏱ 中线副读（日线 fallback）"
    return "⏱ 中线副读（数据不足）"


def _view_lines(view: dict[str, Any]) -> list[str]:
    return [
        (
            f"  结构 {_fmt_structure(view)}｜走势 {_fmt_trend(view)}"
            f"｜笔 {int(view.get('stroke_count') or 0)}"
            f"｜当前笔 {_fmt_current_direction(view)}"
            f"｜近笔 {_fmt_recent_directions(view)}"
        ),
        (
            f"  中枢 {int(view.get('zones_count') or 0)}"
            f"｜段 {int(view.get('segments_count') or 0)}"
            f"｜买点 {_fmt_points(view.get('buy_points'))}"
            f"｜卖点 {_fmt_points(view.get('sell_points'))}"
        ),
    ]


def _wechat_safe(text: str) -> str:
    """兜底清理外部名称/错误串可能带入的 Markdown 控制符。"""
    return (
        text.replace("**", "")
        .replace("---", "—")
        .replace("|", "｜")
        .replace("#", "＃")
        .replace("*", "＊")
        .replace(">", "＞")
    )


def render_chanlun_card(plan: dict[str, Any]) -> str:
    """渲染日线短线 + 周线中线副读结构卡。"""
    name = str(plan.get("name") or plan.get("target") or "未知")
    code = str(plan.get("code") or "")
    title = f"缠论 — {name}" + (f"（{code}）" if code else "") + "｜短中线结构卡"
    daily_count = int(plan.get("data_bars_daily") or 0)
    weekly_count = int(plan.get("data_bars_weekly") or 0)
    adjust_mode = str(plan.get("adjust_mode") or "unknown").lower()
    adjust_label = _ADJUST_LABEL.get(adjust_mode, adjust_mode or "未知")
    data_note = str(plan.get("data_note") or "日周数据齐")
    short_view = plan.get("short_view") if isinstance(plan.get("short_view"), dict) else {}
    midline_view = (
        plan.get("midline_view") if isinstance(plan.get("midline_view"), dict) else {}
    )

    lines = [title]
    price = _fmt_price(plan.get("price"))
    if price is not None:
        lines.append(f"现价 {price}")
    lines.extend(
        [
            f"取数：日{daily_count}根｜周{weekly_count}根｜复权{adjust_label}｜{data_note}",
            "",
            "⏱ 短线（日）",
        ]
    )
    lines.extend(_view_lines(short_view))
    lines.extend(["", _midline_heading(midline_view)])
    lines.extend(_view_lines(midline_view))
    lines.extend(
        [
            "",
            "💬 说明：本卡只复述缠论引擎结构与买卖点；中线阶段仍由周线威科夫负责",
        ]
    )
    return _wechat_safe("\n".join(lines))


__all__ = ["render_chanlun_card"]
