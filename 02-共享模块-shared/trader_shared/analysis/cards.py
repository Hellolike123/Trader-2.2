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
    """int 或生产动量字符串 bullish/bearish/neutral/insufficient → ±1/0。"""
    if isinstance(x, str):
        key = x.strip().lower()
        str_map = {
            "bullish": 1,
            "bearish": -1,
            "neutral": 0,
            "insufficient": 0,
            "多": 1,
            "空": -1,
            "中性": 0,
        }
        if key in str_map:
            return str_map[key]
        # 中文原样
        if x.strip() in str_map:
            return str_map[x.strip()]
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

    from trader_shared.wyckoff_view import _panel_fail_copy, to_wyckoff_state_view

    bias = "neutral"
    phase = str(raw.get("phase") or "")
    phase_label = str(info.get("phase_label") or "")
    try:
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

    # P-L1/P-L2：卡可见 phase_label / main 与 view 同源 sanitize
    phase_label = _panel_fail_copy(phase_label)
    main = _panel_fail_copy(str(info.get("main") or ""))
    note = _panel_fail_copy(str(info.get("note") or ""))

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
        "main": main,
        "note": note,
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
    # C-D3：禁止从 fusion_chan.reason 手补买卖点/背驰；只认引擎 resolve 结果。
    line = format_chanlun_short_light(
        chan_result,
        fusion_chan=None,
        wave_label=wave_label,
    )

    point = info.get("point") if isinstance(info.get("point"), dict) else None
    # fusion 契约字段：与 classic _point_conf 对齐
    point_confidence = None
    lower_confirmed = None
    nesting_confirmed = None
    if point is not None:
        try:
            pc = point.get("confidence")
            if pc is not None:
                point_confidence = int(pc)
        except (TypeError, ValueError):
            point_confidence = None
        if "lower_confirmed" in point:
            lower_confirmed = point.get("lower_confirmed")
        if "nesting_confirmed" in point:
            nesting_confirmed = point.get("nesting_confirmed")
    # 背驰区间套：挂在 divergence 上
    chan_raw = info.get("chan") if isinstance(info.get("chan"), dict) else {}
    div = chan_raw.get("divergence") if isinstance(chan_raw.get("divergence"), dict) else {}
    if info.get("status") == "divergence":
        if info.get("type_raw") == "底背驰" and "bottom_divergence_lower_confirmed" in div:
            lower_confirmed = div.get("bottom_divergence_lower_confirmed")
        if info.get("type_raw") == "顶背驰" and "top_divergence_lower_confirmed" in div:
            lower_confirmed = div.get("top_divergence_lower_confirmed")

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
        "point_confidence": point_confidence,
        "lower_confirmed": lower_confirmed,
        "nesting_confirmed": nesting_confirmed,
    }


def build_momentum_card(
    momentum_result: dict[str, Any] | None = None,
    *,
    role: str = "daily",
) -> dict[str, Any]:
    """动量意见卡 schema_version=momentum_card_v1。

    兼容两种输入：
    - 生产：assess_momentum → {score, direction: bullish|bearish|…, signals}
    - 测试桩：{direction: ±1, confidence, reason}
    """
    m = momentum_result if isinstance(momentum_result, dict) else {}
    if "momentum" in m and isinstance(m.get("momentum"), dict):
        inner = m["momentum"]
        payload = m
    else:
        inner = m
        payload = {"momentum": m}

    # cards 生产路径自有映射（不再依赖 classic 实现）
    from trader_shared.analysis.fusion_card_signals import momentum_raw_to_fusion_signal

    sig = momentum_raw_to_fusion_signal(payload)
    direction = int(sig.get("direction") or 0)
    conf = float(sig.get("confidence") or 0.0)

    # 显式 confidence 优先（测试桩 / 已标准化信号）
    explicit_conf = _finite(inner.get("confidence", m.get("confidence")), None)
    if explicit_conf is not None and inner.get("score") is None and m.get("score") is None:
        # 无 score 时保留桩上的 confidence；有 score 时以 classic 为准
        conf = max(0.0, min(1.0, explicit_conf))
        # 桩若给了 int direction 且 classic 因字符串缺失得到 0，补方向
        if direction == 0 and inner.get("direction") is not None:
            direction = _as_dir(inner.get("direction"))

    # 若 classic 仍为中性但内层有 int 方向
    if direction == 0 and inner.get("direction") is not None:
        d2 = _as_dir(inner.get("direction"))
        if d2 != 0:
            direction = d2

    reason = str(sig.get("reason") or inner.get("reason") or m.get("reason") or "")
    if not reason or reason in ("动量中性", "动量数据不足"):
        signals_list = inner.get("signals") or m.get("signals") or []
        if isinstance(signals_list, list) and signals_list:
            reason = "、".join(str(x) for x in signals_list[-2:])
    strength = str(inner.get("strength") or m.get("strength") or sig.get("strength") or "")
    conf = max(0.0, min(1.0, conf))
    has_score = inner.get("score") is not None or m.get("score") is not None
    raw_ok = bool(inner) and (
        has_score
        or explicit_conf is not None
        or bool(reason)
        or str(inner.get("direction") or "") not in ("", "insufficient")
    )
    return {
        "schema_version": "momentum_card_v1",
        "source": "momentum",
        "role": role,
        "raw_available": raw_ok,
        "direction": direction,
        "confidence": conf,
        "strength": strength,
        "reason": reason,
        "summary_line": reason or "动量中性",
        "score": _finite(inner.get("score", m.get("score")), None),
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
            # 法源 BUSINESS.md §2.0/§2.2：日卡只认日线；禁周线 wyckoff 冒充（对齐 short_midline）
            _wd = report.get("wyckoff_daily")
            _wd_ok = isinstance(_wd, dict) and bool(_wd)
            if not _wd_ok:
                _fb = report.get("wyckoff")
                if isinstance(_fb, dict) and bool(_fb):
                    _fb_tf = str(_fb.get("timeframe") or "").strip().lower()
                    if _fb_tf not in ("weekly", "week", "w"):
                        _wd = _fb
                        _wd_ok = True
                    else:
                        _wd = None
                        _wd_ok = False
            if _wd_ok:
                cards["wyckoff"] = build_wyckoff_card(_wd, role="daily", symbol=symbol)
            else:
                cards["wyckoff"] = _empty_card("wyckoff", "wyckoff_card_v1")
    except Exception:
        cards["wyckoff"] = _empty_card("wyckoff", "wyckoff_card_v1")

    try:
        if "wyckoff_midline" not in cards or not isinstance(cards.get("wyckoff_midline"), dict):
            # 法源 BUSINESS.md §2.0/§2.2：中线卡只认周线 wyckoff_midline；禁日线/unknown 冒充
            wm = report.get("wyckoff_midline")
            _wm_tf = ""
            _wm_st = ""
            if isinstance(wm, dict) and wm:
                _wm_tf = str(wm.get("timeframe") or "").strip().lower()
                _wm_st = str(wm.get("status") or "").strip().lower()
            _weekly_ok = (
                isinstance(wm, dict)
                and bool(wm)
                and _wm_tf in ("weekly", "week", "w")
                and _wm_st not in ("insufficient", "no_data")
            )
            if _weekly_ok:
                cards["wyckoff_midline"] = build_wyckoff_card(
                    wm,
                    role="midline",
                    symbol=symbol,
                )
            else:
                _mid_empty = _empty_card("wyckoff", "wyckoff_card_v1", role="midline")
                _mid_empty["timeframe"] = "insufficient"
                _mid_empty["status"] = "insufficient"
                _mid_empty["bias"] = "neutral"
                _mid_empty["summary_line"] = "周线不足 · 不参与定论"
                cards["wyckoff_midline"] = _mid_empty
    except Exception:
        _mid_empty = _empty_card("wyckoff", "wyckoff_card_v1", role="midline")
        _mid_empty["timeframe"] = "insufficient"
        _mid_empty["status"] = "insufficient"
        _mid_empty["bias"] = "neutral"
        _mid_empty["summary_line"] = "周线不足 · 不参与定论"
        cards["wyckoff_midline"] = _mid_empty

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
