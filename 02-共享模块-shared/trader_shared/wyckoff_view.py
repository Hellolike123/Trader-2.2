"""威科夫统一出口契约 WyckoffStateView（A 档：定 View，不改检测逻辑）。

用途：
- 文档化「报告 / 打分 / AI 应读什么」
- 从现有 wyckoff_analysis 大 dict 薄适配，不重算 Spring/phase
- 后续 B 档再把 events/phase 内部收成层；消费方优先迁到本 View

约定：
- 不直接下单；bias / invalidation_hint 仅供中线叙事与可选旁路
- 日线威科夫仍不进短线 fusion 主权重（既有契约）
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

# 与 wyckoff_analysis 返回字段对齐的「原典/扩展事件」键
_EVENT_SPECS: list[tuple[str, str, str]] = [
    # (event_id, signal_key, reason_key)
    ("ps", "ps_signal", "ps_reason"),
    ("sc", "sc_signal", "sc_reason"),
    ("ar", "ar_signal", "ar_reason"),
    ("are", "are_signal", "are_reason"),
    ("secondary_test_sc", "secondary_test_sc_signal", "secondary_test_sc_reason"),
    ("spring_test", "spring_test_signal", "spring_test_reason"),
    ("st", "st_signal", "st_reason"),  # 兼容；与 spring_test 同亮时下方去重
    ("spring", "spring_signal", "spring_reason"),
    ("sos", "sos_signal", "sos_reason"),
    ("jac", "jac_signal", "jac_reason"),
    ("bu", "bu_signal", "bu_reason"),
    ("lps", "lps_signal", "lps_reason"),
    ("psy", "psy_signal", "psy_reason"),
    ("bc", "bc_signal", "bc_reason"),
    ("upthrust", "upthrust_signal", "upthrust_reason"),
    ("utad", "utad_signal", "utad_reason"),
    ("sow", "sow_signal", "sow_reason"),
    ("lpsy", "lpsy_signal", "lpsy_reason"),
    ("stopping_volume", "stopping_volume_signal", "stopping_volume_reason"),
    ("compression", "compression_signal", "compression_reason"),
    ("trend_pullback", "trend_pullback_signal", "trend_pullback_reason"),
    ("trend_rally", "trend_rally_signal", "trend_rally_reason"),
]

Bias = Literal["bull", "bear", "neutral"]
Timeframe = Literal["daily", "weekly", "insufficient", "unknown"]


class WyckoffEventItem(TypedDict, total=False):
    """单个仍亮灯的事件摘要。"""
    id: str
    reason: str
    price: float | None


class WyckoffTRView(TypedDict, total=False):
    upper: float | None
    lower: float | None
    quality: float | None
    in_range: bool | None
    width: int | None
    amplitude_pct: float | None
    baseline_volume: float | None


class WyckoffCauseEffectView(TypedDict, total=False):
    up_target: float | None
    down_target: float | None
    range: float | None
    note: str
    pnf_box_size: float | None
    pnf_columns: int | None
    pnf_method: str | None  # horizontal | vertical | height_1to1_fallback
    # L0–L3 量度闸（与顶栏同名；缺省时 format 不得贴假量度）
    tr_maturity: str
    measure_allowed: bool
    box_display_mode: str
    tr_maturity_reason: str


class WyckoffPrematureView(TypedDict, total=False):
    spring: bool
    upthrust: bool


class WyckoffStateView(TypedDict, total=False):
    """威科夫统一出口（schema_version 固定便于以后演进）。

    字段含义见 docs/designs/wyckoff-state-view.md
    """
    schema_version: str  # "wyckoff_state_v1"
    symbol: str
    timeframe: Timeframe

    phase: str
    phase_label: str
    phase_a_status: str  # none | forming | established | failed
    confidence: float  # 0~1，启发式，非概率校准
    premature: WyckoffPrematureView
    # CM 行为模式（轻量映射透出）
    cm_mode: str
    cm_note: str

    tr: WyckoffTRView
    active_events: list[str]
    event_detail: dict[str, WyckoffEventItem]

    cause_effect: WyckoffCauseEffectView

    # L0–L3 箱体/量度成熟度（顶栏必有；见 wyckoff-tr-maturity-l0l3-handoff）
    tr_maturity: str  # L0 | L1 | L2 | L3
    tr_maturity_reason: str
    measure_allowed: bool
    box_display_mode: str  # none | proto | box

    bias: Bias
    invalidation_hint: str
    summary_oneline: str

    # 透传：需要原始 bool 时用，View 消费者应优先用上面字段
    raw_available: bool


_GATE_REASON_NOTES: dict[str, str] = {
    "no_tr": "无清晰TR，阶段不参与定论",
    "low_quality": "TR质量不足，阶段不参与定论",
    "forming_phase_a": "箱体未成形，阶段不抬升",
    "no_established_seed": "无Phase A种子箱，阶段不抬升",
    "phase_a_failed": "Phase A失败，阶段不参与定论",
}


def _unwrap_wyckoff(wyckoff: dict[str, Any] | None) -> dict[str, Any]:
    wyk = wyckoff if isinstance(wyckoff, dict) else {}
    if "wyckoff" in wyk and isinstance(wyk.get("wyckoff"), dict):
        return wyk["wyckoff"]
    return wyk


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _bias_from_analysis(wyk: dict[str, Any]) -> Bias:
    """与 format_wyckoff_oneline 主信号优先级大致对齐的弱 bias（不用于下单）。"""
    if wyk.get("timeframe") == "insufficient":
        return "neutral"
    if str(wyk.get("phase_a_status") or "").strip() == "failed":
        return "bear"
    if wyk.get("utad_signal") or wyk.get("sow_signal") or wyk.get("lpsy_signal"):
        return "bear"
    if wyk.get("bc_signal") and not wyk.get("spring_signal"):
        return "bear"
    if wyk.get("upthrust_signal") and not wyk.get("upthrust_premature"):
        return "bear"
    if wyk.get("are_signal") or wyk.get("trend_rally_signal"):
        return "bear"
    if wyk.get("spring_signal") and not wyk.get("spring_premature"):
        if wyk.get("spring_strength") == "failure":
            return "bear"
        # 弱弹簧/高量警告：事件存在但不抬偏多（与打分降权对齐）
        if (
            wyk.get("spring_strength") == "weak"
            or wyk.get("spring_vol_class") == "high_vol_warning"
        ):
            return "neutral"
        return "bull"
    if wyk.get("sos_signal") or wyk.get("bu_signal") or wyk.get("lps_signal"):
        return "bull"
    if wyk.get("ar_signal") or wyk.get("trend_pullback_signal"):
        return "bull"
    if wyk.get("ps_signal") or wyk.get("sc_signal"):
        return "bull"
    if wyk.get("spring_premature") or wyk.get("upthrust_premature"):
        return "neutral"
    phase = str(wyk.get("phase") or "").strip().lower()
    # 生产枚举为 accumulation_a/b/c/d、distribution_a/c/d、markup/markdown
    if phase in ("markup", "accumulation") or phase.startswith("accumulation"):
        return "bull"
    if phase in ("markdown", "distribution") or phase.startswith("distribution"):
        return "bear"
    return "neutral"


def _invalidation_hint(wyk: dict[str, Any], bias: Bias) -> str:
    tr_lo = wyk.get("tr_lower")
    tr_hi = wyk.get("tr_upper")
    if bias == "bull" and tr_lo is not None:
        try:
            return f"收盘有效跌破 TR 下沿 {float(tr_lo):.2f} 则偏多结构受损"
        except (TypeError, ValueError):
            pass
    if bias == "bear" and tr_hi is not None:
        try:
            return f"收盘有效站上 TR 上沿 {float(tr_hi):.2f} 则偏空结构受损"
        except (TypeError, ValueError):
            pass
    if wyk.get("timeframe") == "insufficient":
        return "周线不足，威科夫不参与定论"
    return "暂无明确失效价；以阶段破坏与反向高潮事件为准"


def _confidence(wyk: dict[str, Any], active: list[str]) -> float:
    base = 0.45
    if wyk.get("timeframe") == "insufficient":
        return 0.0
    try:
        delta = float(wyk.get("phase_confidence_delta") or 0.0)
    except (TypeError, ValueError):
        delta = 0.0
    # phase_confidence_delta 常见小幅 ±，映射到置信
    base += delta
    if active:
        base += min(0.2, 0.04 * len(active))
    if wyk.get("spring_premature") or wyk.get("upthrust_premature"):
        base -= 0.15
    if wyk.get("tr_quality") is not None:
        try:
            q = float(wyk["tr_quality"])
            if q >= 0.6:
                base += 0.08
            elif q < 0.35:
                base -= 0.08
        except (TypeError, ValueError):
            pass
    if wyk.get("phase_tr_gated"):
        base = min(base, 0.35)
    return round(_clip01(base), 3)


def to_wyckoff_state_view(
    wyckoff: dict[str, Any] | None,
    *,
    symbol: str = "",
    timeframe: str | None = None,
) -> WyckoffStateView:
    """从 wyckoff_analysis / strategy 包装 dict 适配为统一 View。

    纯映射 + 调用 format_wyckoff_oneline，不重跑检测。
    """
    from trader_shared.wyckoff_core import format_wyckoff_oneline

    wyk = _unwrap_wyckoff(wyckoff)
    tf_raw = timeframe or wyk.get("timeframe") or "unknown"
    if tf_raw not in ("daily", "weekly", "insufficient", "unknown"):
        tf_raw = "unknown"
    tf: Timeframe = tf_raw  # type: ignore[assignment]

    active: list[str] = []
    detail: dict[str, WyckoffEventItem] = {}
    for eid, sig_k, reason_k in _EVENT_SPECS:
        if not wyk.get(sig_k):
            continue
        # spring_test 与 st 同源双写：只展示 Spring确认
        if eid == "st" and wyk.get("spring_test_signal"):
            continue
        active.append(eid)
        price_key = f"{eid}_price"
        # spring/upthrust/compression 等同名；部分用完整前缀
        price = wyk.get(price_key)
        if price is None and eid == "upthrust":
            price = wyk.get("upthrust_price")
        if price is None and eid == "trend_pullback":
            price = wyk.get("trend_pullback_price")
        if price is None and eid == "compression":
            price = wyk.get("compression_price")
        if price is None and eid == "spring_test":
            price = wyk.get("spring_test_price") or wyk.get("st_price")
        if price is None and eid == "secondary_test_sc":
            price = (
                wyk.get("secondary_test_sc_price")
                or wyk.get("secondary_test_sc_low")
                or wyk.get("st_sc_low")
            )
        if price is None and eid == "jac":
            price = wyk.get("jac_price")
        if price is None and eid == "stopping_volume":
            price = wyk.get("stopping_volume_price")
        item: WyckoffEventItem = {
            "id": eid,
            "reason": str(wyk.get(reason_k) or ""),
        }
        try:
            if price is not None:
                item["price"] = float(price)
        except (TypeError, ValueError):
            item["price"] = None
        detail[eid] = item

    bias = _bias_from_analysis(wyk)
    oneline = format_wyckoff_oneline(wyk, show_phase=False)
    phase_a_status = str(wyk.get("phase_a_status") or "").strip() or "none"
    phase_label = str(wyk.get("phase_label") or "")
    # forming：摘要补「箱体未成形」（微信红线：无 #/**/表格）
    if (
        phase_a_status == "forming"
        or "箱体未成形" in phase_label
        or "区间未钉" in phase_label
    ):
        if oneline and "箱体未成形" not in oneline and "区间未钉" not in oneline:
            oneline = f"{oneline} · 箱体未成形"
        elif not oneline:
            oneline = "箱体未成形"
    if wyk.get("phase_tr_gated"):
        reason = str(wyk.get("phase_tr_gate_reason") or "")
        note = _GATE_REASON_NOTES.get(reason) or "阶段不参与定论"
        if oneline and note not in oneline and "不参与定论" not in oneline and "不抬升" not in oneline:
            oneline = f"{oneline} · {note}"

    cm_mode = str(wyk.get("cm_mode") or "none").strip() or "none"
    cm_note = str(wyk.get("cm_note") or "").strip()
    if cm_mode != "none" and cm_note:
        if oneline and cm_note not in oneline:
            oneline = f"{oneline} · CM:{cm_note}"
        elif not oneline:
            oneline = f"CM:{cm_note}"

    tr_maturity = str(wyk.get("tr_maturity") or "").strip().upper()
    box_mode = str(wyk.get("box_display_mode") or "").strip().lower()
    if "measure_allowed" in wyk:
        measure_allowed = bool(wyk.get("measure_allowed"))
    else:
        measure_allowed = tr_maturity == "L3"
    maturity_reason = str(wyk.get("tr_maturity_reason") or "")

    view: WyckoffStateView = {
        "schema_version": "wyckoff_state_v1",
        "symbol": str(symbol or wyk.get("symbol") or ""),
        "timeframe": tf,
        "phase": str(wyk.get("phase") or "none"),
        "phase_label": phase_label,
        "phase_a_status": phase_a_status,
        "confidence": _confidence(wyk, active),
        "premature": {
            "spring": bool(wyk.get("spring_premature")),
            "upthrust": bool(wyk.get("upthrust_premature")),
        },
        "cm_mode": cm_mode,
        "cm_note": cm_note,
        "tr": {
            "upper": wyk.get("tr_upper"),
            "lower": wyk.get("tr_lower"),
            "quality": wyk.get("tr_quality"),
            "in_range": wyk.get("tr_in_range"),
            "width": wyk.get("tr_width"),
            "amplitude_pct": wyk.get("tr_amplitude_pct"),
            "baseline_volume": wyk.get("tr_baseline_volume"),
        },
        "active_events": active,
        "event_detail": detail,
        "cause_effect": {
            "up_target": wyk.get("cause_effect_up_target"),
            "down_target": wyk.get("cause_effect_down_target"),
            "range": wyk.get("cause_effect_range"),
            "note": str(wyk.get("cause_effect_note") or ""),
            "pnf_box_size": wyk.get("pnf_box_size"),
            "pnf_columns": wyk.get("pnf_columns"),
            "pnf_method": wyk.get("pnf_method"),
            "tr_maturity": tr_maturity,
            "measure_allowed": measure_allowed,
            "box_display_mode": box_mode,
            "tr_maturity_reason": maturity_reason,
        },
        "tr_maturity": tr_maturity,
        "tr_maturity_reason": maturity_reason,
        "measure_allowed": measure_allowed,
        "box_display_mode": box_mode,
        "bias": bias,
        "invalidation_hint": _invalidation_hint(wyk, bias),
        "summary_oneline": oneline,
        "raw_available": bool(wyk),
    }
    return view


def format_cause_effect_display(wyckoff: dict[str, Any] | None) -> str:
    """量度目标短行（仅 L3 / measure_allowed）。

    规则（``docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`` §2.3）：
    - 无上下目标 → 空串
    - ``measure_allowed is False`` → 空串（防御：残留目标也不展示）
    - 缺省 ``measure_allowed`` 时：仅当顶栏/嵌套 ``tr_maturity==L3`` 才展示；否则空串
    - ``pnf_method == height_1to1_fallback`` → ``（高度1:1，非出手）``
    - 其他有目标 → ``（P&F，非出手）``
    """
    raw = _unwrap_wyckoff(wyckoff) if wyckoff else {}
    if not isinstance(raw, dict):
        return ""
    # 兼容 view 形态：cause_effect 嵌套；优先读顶栏再嵌套
    ce = raw.get("cause_effect") if isinstance(raw.get("cause_effect"), dict) else {}

    allowed: bool | None = None
    if "measure_allowed" in raw:
        allowed = bool(raw.get("measure_allowed"))
    elif "measure_allowed" in ce:
        allowed = bool(ce.get("measure_allowed"))
    else:
        maturity = str(raw.get("tr_maturity") or ce.get("tr_maturity") or "").strip().upper()
        # 键缺失：不得贴假量度；仅显式 L3 放行
        allowed = maturity == "L3"
    if not allowed:
        return ""

    up = raw.get("cause_effect_up_target")
    down = raw.get("cause_effect_down_target")
    if up is None and down is None:
        up = ce.get("up_target")
        down = ce.get("down_target")
    try:
        up_f = float(up) if up is not None else None
    except (TypeError, ValueError):
        up_f = None
    try:
        down_f = float(down) if down is not None else None
    except (TypeError, ValueError):
        down_f = None
    if up_f is None or down_f is None:
        return ""

    method = raw.get("pnf_method")
    if method is None:
        method = ce.get("pnf_method")
    if method == "height_1to1_fallback":
        tag = "高度1:1，非出手"
    else:
        tag = "P&F，非出手"
    return f"量度目标：上 {up_f:.2f}｜下 {down_f:.2f}（{tag}）"


def format_midline_display(
    wyckoff: dict[str, Any] | None,
    *,
    symbol: str = "",
    direction: int | None = None,
) -> str:
    """报告边界威科夫中线展示：经 View 适配后再格式化（render 勿直接调 wyckoff_core）。"""
    from trader_shared.wyckoff_core import format_wyckoff_midline_light

    view = to_wyckoff_state_view(wyckoff, symbol=symbol, timeframe="weekly")
    # 中线 light 仍需引擎 dict 字段；View 保证已 unwrap / 可追溯
    raw = _unwrap_wyckoff(wyckoff) if wyckoff else {}
    if not raw and view.get("raw_available"):
        raw = {"phase": view.get("phase"), "phase_label": view.get("phase_label")}
    line = format_wyckoff_midline_light(raw or wyckoff, direction=direction)
    return line


def format_event_display(
    wyckoff: dict[str, Any] | None,
    *,
    symbol: str = "",
) -> str:
    """短线威科夫事件轻量行：报告边界统一经 View。"""
    from trader_shared.wyckoff_core import format_wyckoff_event_light

    to_wyckoff_state_view(wyckoff, symbol=symbol, timeframe="daily")
    return format_wyckoff_event_light(wyckoff if isinstance(wyckoff, dict) else {})


def format_daily_phase_display(
    wyckoff: dict[str, Any] | None,
    *,
    symbol: str = "",
) -> str:
    """短线「威科夫：」只读展示：报告边界经 View 再格式化（禁止「日线阶段：」标签）。

    不进背景岗 / fusion / 出手；与中线阶段同构诚实无箱。
    """
    from trader_shared.wyckoff_core import format_wyckoff_daily_phase_light

    to_wyckoff_state_view(wyckoff, symbol=symbol, timeframe="daily")
    body = format_wyckoff_daily_phase_light(wyckoff if isinstance(wyckoff, dict) else {})
    body = str(body or "").strip()
    if body.startswith("威科夫："):
        return body
    if body.startswith("日线阶段："):
        body = body[len("日线阶段："):].strip()
    return f"威科夫：{body or '数据不足 · 仅对照'}"
