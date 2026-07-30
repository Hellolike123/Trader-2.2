"""威科夫 Skill 人读渲染（微信安全；不作交易指令）。"""
from __future__ import annotations

from typing import Any

_BIAS_CN = {
    "bull": "偏多",
    "bear": "偏空",
    "neutral": "中性",
}

_FORBIDDEN_BUY_WORDS = (
    "可执行",
    "宜买",
    "去买",
    "可低吸",
    "三重共振买",
)


def _fmt_price(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None


def _fmt_tr(tr: dict[str, Any] | None) -> str:
    if not isinstance(tr, dict):
        return "暂无"
    lo = _fmt_price(tr.get("lower"))
    hi = _fmt_price(tr.get("upper"))
    q = tr.get("quality")
    parts: list[str] = []
    if lo is not None and hi is not None:
        parts.append(f"下沿{lo}／上沿{hi}")
    elif lo is not None:
        parts.append(f"下沿{lo}")
    elif hi is not None:
        parts.append(f"上沿{hi}")
    if q is not None:
        try:
            parts.append(f"质量{float(q):.2f}")
        except (TypeError, ValueError):
            pass
    return "｜".join(parts) if parts else "暂无"


def _events_line(view: dict[str, Any], event_line: str | None = None) -> str:
    if event_line and str(event_line).strip():
        return str(event_line).strip()
    active = view.get("active_events") or []
    if not active:
        return "无亮灯事件"
    return "、".join(str(x) for x in active)


def render_wyckoff_card(plan: dict[str, Any]) -> str:
    """单票威科夫结构卡。

    plan 字段：name/code/price/chain_plain/daily_view/weekly_view/
    event_line/data_ok/error
    """
    if plan.get("error"):
        name = str(plan.get("name") or plan.get("target") or "未知")
        code = str(plan.get("code") or "")
        title = f"威科夫 — {name}" + (f"（{code}）" if code else "")
        return "\n".join([title, f"⚠ {plan['error']}", "💬 一句：数据不足，仅现价"])

    name = str(plan.get("name") or "未知")
    code = str(plan.get("code") or "")
    price = plan.get("price")
    price_s = _fmt_price(price)
    daily = plan.get("daily_view") if isinstance(plan.get("daily_view"), dict) else {}
    weekly = plan.get("weekly_view") if isinstance(plan.get("weekly_view"), dict) else {}

    phase = str(daily.get("phase_label") or daily.get("phase") or "未知")
    bias = _BIAS_CN.get(str(daily.get("bias") or "neutral"), "中性")
    chain = str(plan.get("chain_plain") or "威：吸筹链未成型")
    events = _events_line(daily, plan.get("event_line"))
    tr_line = _fmt_tr(daily.get("tr") if isinstance(daily.get("tr"), dict) else None)
    invalid = str(daily.get("invalidation_hint") or "暂无明确失效价")
    oneline = str(daily.get("summary_oneline") or "无摘要")

    lines = [
        f"威科夫 — {name}（{code}）" if code else f"威科夫 — {name}",
    ]
    if price_s:
        lines.append(f"现价 {price_s}")
    lines.extend(
        [
            f"🧭 阶段：{phase}｜偏向 {bias}",
            f"📎 链：{chain}",
            f"📌 事件：{events}",
            f"📐 TR：{tr_line}",
            f"⚠ 失效：{invalid}",
        ]
    )

    w_phase = str(weekly.get("phase_label") or weekly.get("phase") or "").strip()
    if w_phase and w_phase not in ("none", "未知"):
        w_bias = _BIAS_CN.get(str(weekly.get("bias") or "neutral"), "中性")
        lines.append(f"🧭 中线阶段：{w_phase}｜偏向 {w_bias}")

    if not plan.get("data_ok", True):
        lines.append("💬 一句：数据不足，仅现价")
    else:
        lines.append(f"💬 一句：{oneline}")

    text = "\n".join(lines)
    for bad in _FORBIDDEN_BUY_WORDS:
        if bad in text:
            text = text.replace(bad, "（结构参考）")
    return text


def render_wyckoff_rank(rows: list[dict[str, Any]], *, empty_hint: str | None = None) -> str:
    """池内威科夫链排序面板（不改分道）。"""
    lines = ["威科夫池排序（链视角，非分道）"]
    if not rows:
        lines.append(empty_hint or "池空或无可用缓存；可先 trader pool refresh")
        return "\n".join(lines)
    for i, row in enumerate(rows, 1):
        name = str(row.get("name") or row.get("target") or "?")
        chain = str(row.get("chain_plain") or "威：吸筹链未成型")
        phase = str(row.get("phase_label") or row.get("phase") or "—")
        lines.append(f"{i}. {name}｜{chain}｜{phase}")
    lines.append("说明：排序仅看吸筹链进度；出手仍以 trader 分道与 decision_view 为准")
    return "\n".join(lines)


__all__ = [
    "render_wyckoff_card",
    "render_wyckoff_rank",
]
