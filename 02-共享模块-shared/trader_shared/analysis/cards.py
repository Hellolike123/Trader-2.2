"""分析层意见卡（P0 + 架构加固 B）：稳定小 dict，供策略匹配 / Skill 只读。

契约：
- docs/designs/analysis-opinion-cards.md
- docs/designs/analysis-strategy-boundaries.md

规则：
- 本模块是分析对外主出口；可适配 cores，但 strategy 不得绕过本模块去调检测实现。
- ensure_report_analysis_cards(report) 保证 report['analysis_cards'] 键齐全。
"""
from __future__ import annotations

import math
from typing import Any


def _finite(x: Any, default: float | None = None) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _as_dir(x: Any) -> int:
    try:
        d = int(x)
    except (TypeError, ValueError):
        return 0
    if d > 0:
        return 1
    if d < 0:
        return -1
    return 0


def _empty_card(source: str, schema: str, role: str = "daily") -> dict[str, Any]:
    return {
        "schema_version": schema,
        "source": source,
        "role": role,
        "raw_available": False,
        "direction": 0,
        "summary_line": "",
    }


def build_wyckoff_card(
    wyckoff: dict[str, Any] | None = None,
    *,
    role: str = "daily",
    symbol: str = "",
) -> dict[str, Any]:
    """威科夫意见卡 schema_version=wyckoff_card_v1。"""
    from trader_shared.wyckoff_core import (
        format_wyckoff_event_light,
        format_wyckoff_midline_light,
        resolve_wyckoff_primary,
        _unwrap_wyckoff_dict,
    )

    info = resolve_wyckoff_primary(wyckoff)
    raw = _unwrap_wyckoff_dict(wyckoff)
    tr_ok = bool(
        raw.get("tr_upper") is not None
        and raw.get("tr_lower") is not None
        and raw.get("tr_quality") is not None
    )
    if role in ("midline", "weekly"):
        summary = format_wyckoff_midline_light(wyckoff)
    else:
        summary = format_wyckoff_event_light(wyckoff)

    bias = "neutral"
    phase = str(raw.get("phase") or "")
    phase_label = str(info.get("phase_label") or "")
    try:
        from trader_shared.wyckoff_view import to_wyckoff_state_view

        view = to_wyckoff_state_view(
            wyckoff,
            symbol=symbol or "",
            timeframe=str(info.get("timeframe") or "unknown"),
        )
        bias = str(view.get("bias") or "neutral")
        phase = str(view.get("phase") or phase)
        phase_label = str(view.get("phase_label") or phase_label)
    except Exception:
        pass

    return {
        "schema_version": "wyckoff_card_v1",
        "source": "wyckoff",
        "role": role,
        "raw_available": info.get("status") not in ("no_data",),
        "timeframe": info.get("timeframe") or raw.get("timeframe") or "unknown",
        "status": info.get("status") or "no_data",
        "phase": phase,
        "phase_label": phase_label,
        "event_code": str(info.get("code") or "—"),
        "event_cn": str(info.get("cn_name") or ""),
        "direction": _as_dir(info.get("direction")),
        "main": str(info.get("main") or ""),
        "note": str(info.get("note") or ""),
        "summary_line": summary,
        "tr_ok": tr_ok,
        "bias": bias,
    }


def build_chan_card(
    chan_result: Any = None,
    *,
    fusion_chan: dict | None = None,
    wave_label: str = "",
    role: str = "daily",
) -> dict[str, Any]:
    """缠论意见卡 schema_version=chan_card_v1。"""
    from trader_shared.chan_core import format_chanlun_short_light, resolve_chanlun_primary

    info = resolve_chanlun_primary(chan_result)
    line = format_chanlun_short_light(
        chan_result,
        fusion_chan=fusion_chan,
        wave_label=wave_label,
    )
    if info.get("status") in ("none", "trend") and isinstance(fusion_chan, dict):
        reason = str(fusion_chan.get("reason") or "")
        for raw, short in (
            ("一类买", "一买"),
            ("二类买", "二买"),
            ("三类买", "三买"),
            ("类二买", "类二买"),
            ("一类卖", "一卖"),
            ("二类卖", "二卖"),
            ("三类卖", "三卖"),
        ):
            if raw in reason or short in reason:
                info = {
                    **info,
                    "status": "point",
                    "type_raw": raw,
                    "type_short": short,
                    "direction": _as_dir(fusion_chan.get("direction")),
                    "same_level": True,
                }
                break
        else:
            if "底背驰" in reason:
                info = {
                    **info,
                    "status": "divergence",
                    "type_raw": "底背驰",
                    "type_short": "底背驰",
                    "direction": 1,
                    "same_level": True,
                }
            elif "顶背驰" in reason:
                info = {
                    **info,
                    "status": "divergence",
                    "type_raw": "顶背驰",
                    "type_short": "顶背驰",
                    "direction": -1,
                    "same_level": True,
                }

    return {
        "schema_version": "chan_card_v1",
        "source": "chan",
        "role": role,
        "raw_available": bool(info.get("chan")) or info.get("status") not in ("none",),
        "status": str(info.get("status") or "none"),
        "type_raw": str(info.get("type_raw") or ""),
        "type_short": str(info.get("type_short") or ""),
        "direction": _as_dir(info.get("direction")),
        "note": str(info.get("note") or ""),
        "same_level": bool(info.get("same_level")),
        "summary_line": line,
    }


def build_momentum_card(
    momentum_result: dict[str, Any] | None = None,
    *,
    role: str = "daily",
) -> dict[str, Any]:
    """动量意见卡 schema_version=momentum_card_v1。"""
    m = momentum_result if isinstance(momentum_result, dict) else {}
    if "momentum" in m and isinstance(m.get("momentum"), dict):
        inner = m["momentum"]
    else:
        inner = m
    direction = _as_dir(inner.get("direction", m.get("direction")))
    conf = _finite(inner.get("confidence", m.get("confidence")), 0.0) or 0.0
    conf = max(0.0, min(1.0, conf))
    reason = str(inner.get("reason") or m.get("reason") or "")
    strength = str(inner.get("strength") or m.get("strength") or "")
    return {
        "schema_version": "momentum_card_v1",
        "source": "momentum",
        "role": role,
        "raw_available": bool(inner) or bool(reason),
        "direction": direction,
        "confidence": conf,
        "strength": strength,
        "reason": reason,
        "summary_line": reason or "动量中性",
    }


def build_chip_card(
    current: float,
    peaks: list[dict[str, Any]] | None = None,
    migration: dict[str, Any] | None = None,
    profit_pct: float | None = None,
    *,
    role: str = "report",
) -> dict[str, Any]:
    """筹码意见卡 schema_version=chip_card_v1（方案 C）。"""
    from trader_shared.chip_core import format_chip_position_light

    line = format_chip_position_light(current, peaks, migration, profit_pct)
    cur = _finite(current, 0.0) or 0.0
    clean: list[dict[str, Any]] = []
    for p in peaks or []:
        if not isinstance(p, dict):
            continue
        px = _finite(p.get("price"))
        if px is None or px <= 0:
            continue
        clean.append({"price": px})

    below = [x for x in clean if x["price"] < cur] if cur > 0 else []
    above = sorted([x for x in clean if x["price"] > cur], key=lambda x: x["price"]) if cur > 0 else []

    if below:
        support_tag = f"支撑 {below[-1]['price']:.2f}"
    else:
        support_tag = "支撑弱" if clean or profit_pct is not None else ""

    resist_px: float | None = None
    if above:
        resist_px = above[0]["price"]
        resist_tag = f"阻力 {resist_px:.2f}"
    else:
        resist_tag = "阻力弱" if clean or profit_pct is not None else ""

    trapped_tag = ""
    if profit_pct is not None:
        pp = _finite(profit_pct)
        if pp is not None:
            if pp < 20:
                trapped_tag = "套牢面大"
            elif pp > 80:
                trapped_tag = "套牢面小"
            else:
                trapped_tag = "套牢面中性"

    migration_tag = ""
    mig = migration if isinstance(migration, dict) else {}
    if mig.get("has_history"):
        level = str(mig.get("warning_level") or "none")
        try:
            mp_f = float(mig.get("migration_pct") or 0)
        except (TypeError, ValueError):
            mp_f = 0.0
        if level in ("clear", "exit", "critical") or mp_f >= 50:
            migration_tag = "底部松动重"
        elif level in ("warning", "warn") or mp_f >= 40:
            migration_tag = "底部松动"

    has_data = bool(line)
    return {
        "schema_version": "chip_card_v1",
        "source": "chip",
        "role": role,
        "raw_available": has_data,
        "has_data": has_data,
        "support_tag": support_tag,
        "resist_px": resist_px,
        "resist_tag": resist_tag,
        "trapped_tag": trapped_tag,
        "migration_tag": migration_tag,
        "summary_line": line,
    }


def build_vpf_card(
    vpf_result: dict[str, Any] | None = None,
    *,
    role: str = "daily",
) -> dict[str, Any]:
    """VPF 意见卡 schema_version=vpf_card_v1。"""
    v = vpf_result if isinstance(vpf_result, dict) else {}
    conf = _finite(v.get("confidence"), 0.0) or 0.0
    conf = max(0.0, min(1.0, conf))
    return {
        "schema_version": "vpf_card_v1",
        "source": "vpf",
        "role": role,
        "raw_available": bool(v),
        "direction": _as_dir(v.get("direction")),
        "confidence": conf,
        "reason": str(v.get("reason") or ""),
        "fund_direction": _as_dir(v.get("fund_direction")),
        "vp_direction": _as_dir(v.get("vp_direction")),
        "warning_type": str(v.get("warning_type") or ""),
        "fund_quality": str(v.get("fund_quality") or ""),
        "summary_line": str(v.get("reason") or "价量资金中性"),
    }


def ensure_report_analysis_cards(report: dict[str, Any]) -> dict[str, Any]:
    """保证 report['analysis_cards'] 键齐全（架构加固 B）。

    幂等：已有合法卡则保留并补缺键。
    返回 analysis_cards 引用。
    """
    if not isinstance(report, dict):
        return {}

    existing = report.get("analysis_cards") if isinstance(report.get("analysis_cards"), dict) else {}
    cards: dict[str, Any] = dict(existing)

    fusion = report.get("fusion") if isinstance(report.get("fusion"), dict) else {}
    sig = fusion.get("signals_detail") if isinstance(fusion.get("signals_detail"), dict) else {}
    conclusion = report.get("conclusion") if isinstance(report.get("conclusion"), dict) else {}
    current = _finite(report.get("current"), 0.0) or 0.0
    symbol = str(report.get("symbol") or "")

    try:
        if "chan" not in cards or not isinstance(cards.get("chan"), dict):
            cards["chan"] = build_chan_card(
                report.get("chanlun") or report.get("chan"),
                fusion_chan=sig.get("chan") if isinstance(sig.get("chan"), dict) else None,
                wave_label=str(conclusion.get("wave_label") or ""),
                role="daily",
            )
    except Exception:
        cards["chan"] = _empty_card("chan", "chan_card_v1")

    try:
        if "wyckoff" not in cards or not isinstance(cards.get("wyckoff"), dict):
            cards["wyckoff"] = build_wyckoff_card(
                report.get("wyckoff_daily") or report.get("wyckoff"),
                role="daily",
                symbol=symbol,
            )
    except Exception:
        cards["wyckoff"] = _empty_card("wyckoff", "wyckoff_card_v1")

    try:
        if "wyckoff_midline" not in cards or not isinstance(cards.get("wyckoff_midline"), dict):
            cards["wyckoff_midline"] = build_wyckoff_card(
                report.get("wyckoff_midline") or report.get("wyckoff"),
                role="midline",
                symbol=symbol,
            )
    except Exception:
        cards["wyckoff_midline"] = _empty_card("wyckoff", "wyckoff_card_v1", role="midline")

    try:
        if "momentum" not in cards or not isinstance(cards.get("momentum"), dict):
            cards["momentum"] = build_momentum_card(
                sig.get("momentum") if isinstance(sig.get("momentum"), dict) else report.get("momentum"),
            )
    except Exception:
        cards["momentum"] = _empty_card("momentum", "momentum_card_v1")

    try:
        if "vpf" not in cards or not isinstance(cards.get("vpf"), dict):
            cards["vpf"] = build_vpf_card(
                sig.get("vpf") if isinstance(sig.get("vpf"), dict) else None,
            )
    except Exception:
        cards["vpf"] = _empty_card("vpf", "vpf_card_v1")

    try:
        if "chip" not in cards or not isinstance(cards.get("chip"), dict):
            cards["chip"] = build_chip_card(
                current,
                report.get("chip_peaks") or [],
                report.get("chip_migration") if isinstance(report.get("chip_migration"), dict) else None,
                report.get("chip_current_pct") if isinstance(report.get("chip_current_pct"), (int, float)) else None,
            )
    except Exception:
        cards["chip"] = _empty_card("chip", "chip_card_v1", role="report")

    report["analysis_cards"] = cards
    return cards


def assert_card_numeric_finite(card: dict[str, Any]) -> None:
    """A-06 辅助：意见卡数值字段不得为 NaN/Inf。"""
    for k, v in card.items():
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"card field {k} is not finite: {v}")
        if k in ("direction",) and isinstance(v, (int, float)):
            if int(v) not in (-1, 0, 1):
                raise ValueError(f"direction out of range: {v}")
