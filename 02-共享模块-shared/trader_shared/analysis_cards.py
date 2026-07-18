"""分析层意见卡（P0）：稳定小 dict，供策略匹配 / Skill 只读。

契约：docs/designs/analysis-opinion-cards.md
不重算缠/威/筹，只适配现有 resolve_* / format_* / strategy 输出。
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
    if role == "midline":
        summary = format_wyckoff_midline_light(wyckoff)
    else:
        summary = format_wyckoff_event_light(wyckoff)

    bias = "neutral"
    try:
        from trader_shared.wyckoff_view import to_wyckoff_state_view

        view = to_wyckoff_state_view(wyckoff, symbol=symbol or "", timeframe=str(info.get("timeframe") or "unknown"))
        bias = str(view.get("bias") or "neutral")
        phase = str(view.get("phase") or "")
        phase_label = str(view.get("phase_label") or info.get("phase_label") or "")
    except Exception:
        phase = str(raw.get("phase") or "")
        phase_label = str(info.get("phase_label") or "")

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
    # fusion 补强（与 short light 一致）
    line = format_chanlun_short_light(
        chan_result,
        fusion_chan=fusion_chan,
        wave_label=wave_label,
    )
    # 若 fusion 改写了类型，再 resolve 一次展示用字段
    if info.get("status") in ("none", "trend") and isinstance(fusion_chan, dict):
        info2 = resolve_chanlun_primary(chan_result)
        # format 已处理 fusion；用 line 反推 type 不可靠，保留 resolve + fusion 扫描
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
                info2 = {
                    **info2,
                    "status": "point",
                    "type_raw": raw,
                    "type_short": short,
                    "direction": _as_dir(fusion_chan.get("direction")),
                    "same_level": True,
                }
                info = info2
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
    # strategy 包装 {"momentum": {...}} 或 fusion 扁平
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


def assert_card_numeric_finite(card: dict[str, Any]) -> None:
    """A-06 辅助：意见卡数值字段不得为 NaN/Inf。"""
    for k, v in card.items():
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"card field {k} is not finite: {v}")
        if k in ("direction",) and isinstance(v, (int, float)):
            if int(v) not in (-1, 0, 1):
                raise ValueError(f"direction out of range: {v}")
