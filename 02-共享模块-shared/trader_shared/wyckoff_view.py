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
    ("st", "st_signal", "st_reason"),
    ("spring", "spring_signal", "spring_reason"),
    ("sos", "sos_signal", "sos_reason"),
    ("bu", "bu_signal", "bu_reason"),
    ("lps", "lps_signal", "lps_reason"),
    ("psy", "psy_signal", "psy_reason"),
    ("bc", "bc_signal", "bc_reason"),
    ("upthrust", "upthrust_signal", "upthrust_reason"),
    ("utad", "utad_signal", "utad_reason"),
    ("sow", "sow_signal", "sow_reason"),
    ("lpsy", "lpsy_signal", "lpsy_reason"),
    ("compression", "compression_signal", "compression_reason"),
    ("trend_pullback", "trend_pullback_signal", "trend_pullback_reason"),
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
    confidence: float  # 0~1，启发式，非概率校准
    premature: WyckoffPrematureView

    tr: WyckoffTRView
    active_events: list[str]
    event_detail: dict[str, WyckoffEventItem]

    cause_effect: WyckoffCauseEffectView

    bias: Bias
    invalidation_hint: str
    summary_oneline: str

    # 透传：需要原始 bool 时用，View 消费者应优先用上面字段
    raw_available: bool


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
    if wyk.get("utad_signal") or wyk.get("sow_signal") or wyk.get("lpsy_signal"):
        return "bear"
    if wyk.get("bc_signal") and not wyk.get("spring_signal"):
        return "bear"
    if wyk.get("upthrust_signal") and not wyk.get("upthrust_premature"):
        return "bear"
    if wyk.get("spring_signal") and not wyk.get("spring_premature"):
        if wyk.get("spring_strength") == "failure":
            return "bear"
        return "bull"
    if wyk.get("sos_signal") or wyk.get("bu_signal") or wyk.get("lps_signal"):
        return "bull"
    if wyk.get("ps_signal") or wyk.get("sc_signal"):
        return "bull"
    if wyk.get("spring_premature") or wyk.get("upthrust_premature"):
        return "neutral"
    phase = str(wyk.get("phase") or "")
    if phase in ("markup", "accumulation"):
        return "bull"
    if phase in ("markdown", "distribution"):
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

    view: WyckoffStateView = {
        "schema_version": "wyckoff_state_v1",
        "symbol": str(symbol or wyk.get("symbol") or ""),
        "timeframe": tf,
        "phase": str(wyk.get("phase") or "none"),
        "phase_label": str(wyk.get("phase_label") or ""),
        "confidence": _confidence(wyk, active),
        "premature": {
            "spring": bool(wyk.get("spring_premature")),
            "upthrust": bool(wyk.get("upthrust_premature")),
        },
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
        },
        "bias": bias,
        "invalidation_hint": _invalidation_hint(wyk, bias),
        "summary_oneline": oneline,
        "raw_available": bool(wyk),
    }
    return view
