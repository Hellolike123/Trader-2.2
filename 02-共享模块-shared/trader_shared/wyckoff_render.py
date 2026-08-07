"""威科夫 Skill 人读渲染（微信安全；不作交易指令）。

法源：docs/plans/wyckoff-detail-slim-b-handoff.md
旧完整详析：docs/plans/wyckoff-skill-deep-card-handoff.md（--full）
只拼装引擎/View 字段；禁止在本模块检测 SC 或发明价格。
"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.wyckoff_chain import (
    ACCUM_CHAIN,
    extract_accum_events,
    first_missing_accum,
    format_wyckoff_chain_plain,
    is_phase_a_failed,
)

_logger = get_logger(__name__)

_BIAS_CN = {
    "bull": "偏多",
    "bear": "偏空",
    "neutral": "中性",
}

# handoff §2.2 缩写释义（上屏括号内必须用此表；未知 → 事件）
_EVENT_CN: dict[str, str] = {
    "SC": "卖力高潮",
    "AR": "自动反弹",
    "ST": "SC区回测",
    "Spring": "弹簧确认",
    "SpringTest": "弹簧确认",
    "LPS": "最后支撑点",
    "SOS": "强势信号",
    "PS": "初步止跌",
    "BC": "买力高潮",
    "ARE": "自动回落",
    "SOW": "弱势信号",
    "LPSY": "最后供应点",
    "UT": "上冲",
    "UTAD": "派发后上冲",
    "BU": "回调买入",
    "Markup": "主升",
    "Markdown": "主跌",
    "TR": "交易区间",
    "PSY": "初步供应",
    "JAC": "跳溪",
    "SV": "止跌量",
}

# view active_events id → 展示 CODE
_VIEW_ID_TO_CODE: dict[str, str] = {
    "sc": "SC",
    "ar": "AR",
    "secondary_test_sc": "ST",
    # st_* / spring_test_* = Spring 确认（phase-a §4.4.2）；禁止映成 ST（二次测试）
    "spring_test": "Spring",
    "st": "Spring",
    "spring": "Spring",
    "sos": "SOS",
    "lps": "LPS",
    "ps": "PS",
    "bc": "BC",
    "are": "ARE",
    "sow": "SOW",
    "lpsy": "LPSY",
    "upthrust": "UT",
    "utad": "UTAD",
    "bu": "BU",
    "psy": "PSY",
    "jac": "JAC",
    "stopping_volume": "SV",
}

_DIST_VIEW_IDS = frozenset({"are", "bc", "sow", "lpsy", "utad", "upthrust"})
_DIST_CHAIN = ("BC", "ARE", "SOW", "LPSY", "UTAD")
_DIST_CODES = frozenset(_DIST_CHAIN) | {"UT", "PSY"}

_FORBIDDEN_BUY_WORDS = (
    "可执行",
    "宜买",
    "去买",
    "可低吸",
    "三重共振买",
    "该买了",
    "立即买入",
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


def _cn(code: str) -> str:
    c = str(code or "").strip()
    return _EVENT_CN.get(c) or "事件"


def _panel_fail_copy(text: str) -> str:
    """面板可见失败词 → 失效（SSOT：wyckoff_view._panel_fail_copy；P-L2）。"""
    from trader_shared.wyckoff_view import _panel_fail_copy as _ssot

    return _ssot(text)


def _as_view(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _as_raw(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    nested = obj.get("wyckoff")
    if isinstance(nested, dict) and nested:
        return nested
    return obj


def _warn_contradictory_phase_a(result: dict[str, Any]) -> None:
    """渲染前防御 check：accumulation_confirmed=True 与 phase_a failed 并存 → 告警。

    只告警、绝不改渲染输出（上游引擎合同已防并存，此为兜底）。
    """
    candidates = [
        result,
        _as_raw(result.get("daily_raw")),
        _as_raw(result.get("daily_view")),
    ]
    for candidate in candidates:
        if candidate.get("accumulation_confirmed") and (
            (candidate.get("phase_a_range") or {}).get("status") == "failed"
        ):
            _logger.warning(
                "[wyckoff] 矛盾字段: accumulation_confirmed=True 与 phase_a_status=failed 并存，请检查上游引擎"
            )
            return


def _display_chain_plain(chain_plain: str | None, raw: dict[str, Any], view: dict[str, Any]) -> str:
    """failed Phase A 时忽略旧缓存，统一走 chain SSOT 的失败态短句。

    保守合并：raw / view 任一 failed 即收口。事件灯优先取 raw；失败态字段
    从 view 强制写入，避免「view=failed 但 raw 未带 status」漏出还差下一灯。
    """
    if not (is_phase_a_failed(raw) or is_phase_a_failed(view)):
        return str(chain_plain or "威：吸筹链未成型")
    src: dict[str, Any] = dict(raw) if isinstance(raw, dict) and raw else {}
    if not src and isinstance(view, dict):
        src = dict(view)
    # 强制失败态（handoff：两字段不一致时按更保守的失败处理）
    src["phase_a_status"] = "failed"
    pa = dict(src["phase_a_range"]) if isinstance(src.get("phase_a_range"), dict) else {}
    if isinstance(view, dict) and isinstance(view.get("phase_a_range"), dict):
        pa = {**view.get("phase_a_range"), **pa}
    pa["status"] = "failed"
    src["phase_a_range"] = pa
    # view.active_events → 回填灯（raw 缺旗时仍能保留已亮事实）
    if isinstance(view, dict):
        active = view.get("active_events")
        if isinstance(active, (list, tuple)):
            mapping = {
                "sc": "sc_signal",
                "ar": "ar_signal",
                "st": "st_signal",
                "lps": "lps_signal",
                "sos": "sos_signal",
            }
            for ev in active:
                key = mapping.get(str(ev).strip().lower())
                if key and not src.get(key):
                    src[key] = True
    return format_wyckoff_chain_plain(src)


def _box_mode(view: dict[str, Any], raw: dict[str, Any]) -> str:
    mode = str(view.get("box_display_mode") or raw.get("box_display_mode") or "").strip().lower()
    if mode:
        return mode
    maturity = str(view.get("tr_maturity") or raw.get("tr_maturity") or "").strip().upper()
    return {"L0": "none", "L1": "proto", "L2": "box", "L3": "box"}.get(maturity, "none")


def _maturity(view: dict[str, Any], raw: dict[str, Any]) -> str:
    return str(view.get("tr_maturity") or raw.get("tr_maturity") or "").strip().upper()


def _measure_allowed(view: dict[str, Any], raw: dict[str, Any]) -> bool:
    if "measure_allowed" in view:
        return bool(view.get("measure_allowed"))
    if "measure_allowed" in raw:
        return bool(raw.get("measure_allowed"))
    return _maturity(view, raw) == "L3"


def _phase_a_bounds(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    """批准源：Phase A sc_low/ar_high（及 ST refine）；不用分位 tr 冒充。"""
    pa = raw.get("phase_a_range") if isinstance(raw.get("phase_a_range"), dict) else {}

    def _num(*keys: str) -> float | None:
        for src in (raw, pa):
            for k in keys:
                v = src.get(k)
                if v is None:
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    lo = _num("sc_low")
    st_lo = _num("st_sc_low", "sc_low_refined", "secondary_test_sc_low")
    if lo is not None and st_lo is not None:
        lo = min(lo, st_lo)
    elif lo is None:
        lo = st_lo
    hi = _num("ar_high")
    if lo is not None and hi is not None and lo >= hi:
        return None, None
    return lo, hi


def _range_phrase(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """L0–L3 区间门禁（W-D3/W-D4）。分位种子不得进区间主行。"""
    mode = _box_mode(view, raw)
    maturity = _maturity(view, raw)
    seed = str(raw.get("tr_seed_source") or "").strip().lower()

    # L0 / none / 纯分位：禁止箱/雏形数字
    if maturity == "L0" or mode == "none" or (seed == "percentile" and mode not in ("proto", "box")):
        base = "无成熟箱／无雏形"
        if not _measure_allowed(view, raw):
            return f"{base}｜未达 L3，暂不测算"
        return base

    lo, hi = _phase_a_bounds(raw)
    if mode == "proto" or maturity == "L1":
        if lo is not None and hi is not None:
            phrase = f"雏形 下沿{_fmt_price(lo)}／上沿{_fmt_price(hi)}（待SC区回测）"
        elif lo is not None:
            phrase = f"雏形 下沿{_fmt_price(lo)}（上沿未出）"
        else:
            phrase = "雏形 · 上沿未出"
        return f"{phrase}｜未达 L3，暂不测算"

    # L2/L3 box
    if lo is not None and hi is not None:
        phrase = f"箱体 下沿{_fmt_price(lo)}／上沿{_fmt_price(hi)}"
    elif lo is not None:
        phrase = f"箱体 下沿{_fmt_price(lo)}"
    else:
        phrase = "箱体未钉完整上下沿"

    if _measure_allowed(view, raw):
        from trader_shared.wyckoff_view import format_cause_effect_display

        ce = format_cause_effect_display(raw) or format_cause_effect_display(view)
        if ce:
            return f"{phrase}｜{ce}"
        return phrase
    return f"{phrase}｜未达 L3，暂不测算"


def _invalidation_phrase(view: dict[str, Any], raw: dict[str, Any]) -> str:
    hint = str(view.get("invalidation_hint") or "").strip()
    mode = _box_mode(view, raw)
    maturity = _maturity(view, raw)
    if mode == "none" or maturity == "L0":
        if not hint:
            return "暂无明确箱体失效价"
        # hint 若引用 TR 沿但不当箱：改写
        if any(k in hint for k in ("TR", "下沿", "上沿", "箱")):
            return "暂无明确箱体失效价"
    return _panel_fail_copy(hint or "暂无明确失效价")


def _primary_light_label(raw: dict[str, Any], view: dict[str, Any]) -> str:
    from trader_shared.wyckoff_core import resolve_wyckoff_primary

    info = resolve_wyckoff_primary(raw if raw else view)
    if info.get("status") == "event":
        code = str(info.get("code") or "").strip() or "—"
        # 对齐 handoff 释义表（resolve 的 cn 可能略异）
        return f"{code}（{_cn(code)}）"
    active = view.get("active_events") or []
    if active:
        eid = str(active[0])
        code = _VIEW_ID_TO_CODE.get(eid, eid.upper())
        return f"{code}（{_cn(code)}）"
    return "无主灯"


def _slim_is_scene_change(view: dict[str, Any], raw: dict[str, Any]) -> bool:
    """突然拉升类：Phase A 失效 + 破后仍有 SOS/LPS → 破后强势（双段对照）。"""
    return (is_phase_a_failed(raw) or is_phase_a_failed(view)) and bool(
        _slim_post_fail_strength(view, raw)
    )


def _primary_light_code(raw: dict[str, Any], view: dict[str, Any]) -> str:
    if _slim_is_scene_change(view, raw):
        return "破后强势"
    if is_phase_a_failed(raw) or is_phase_a_failed(view):
        return "PhaseAFail"
    from trader_shared.wyckoff_core import resolve_wyckoff_primary

    info = resolve_wyckoff_primary(raw if raw else view)
    if info.get("status") == "event":
        return str(info.get("code") or "").strip() or "无主灯"
    active = view.get("active_events") or []
    if active:
        eid = str(active[0])
        return _VIEW_ID_TO_CODE.get(eid, eid.upper()) or "无主灯"
    return "无主灯"


def _event_price_from_sources(
    code: str,
    *,
    view: dict[str, Any],
    raw: dict[str, Any],
) -> float | None:
    """亮灯价：event_detail / *_price 信号价（禁止行情 min）。"""
    detail = view.get("event_detail") if isinstance(view.get("event_detail"), dict) else {}
    id_candidates: list[str] = []
    if code == "SC":
        id_candidates = ["sc"]
    elif code == "AR":
        id_candidates = ["ar"]
    elif code == "ST":
        # 灯文案 ST（二次测试）= 广义 ST；勿吃 Spring 确认价
        id_candidates = ["secondary_test_sc"]
    elif code in ("Spring", "SpringTest"):
        id_candidates = ["spring", "spring_test", "st"]
    elif code == "LPS":
        id_candidates = ["lps"]
    elif code == "SOS":
        id_candidates = ["sos"]
    else:
        # reverse map
        for eid, c in _VIEW_ID_TO_CODE.items():
            if c == code:
                id_candidates.append(eid)

    for eid in id_candidates:
        item = detail.get(eid)
        if isinstance(item, dict) and item.get("price") is not None:
            try:
                return float(item["price"])
            except (TypeError, ValueError):
                pass

    price_keys = {
        "SC": ("sc_price", "sc_low"),
        "AR": ("ar_price", "ar_high"),
        "ST": (
            "secondary_test_sc_price",
            "secondary_test_sc_low",
            "st_sc_low",
        ),
        "Spring": ("spring_price", "spring_test_price", "st_price"),
        "SpringTest": ("spring_test_price", "st_price"),
        "LPS": ("lps_price",),
        "SOS": ("sos_price",),
        "PS": ("ps_price",),
        "BC": ("bc_price",),
        "ARE": ("are_price",),
        "SOW": ("sow_price",),
        "LPSY": ("lpsy_price",),
        "UT": ("upthrust_price",),
        "UTAD": ("utad_price",),
        "BU": ("bu_price",),
        "PSY": ("psy_price",),
        "JAC": ("jac_price",),
        "SV": ("stopping_volume_price",),
    }
    for k in price_keys.get(code, ()):
        v = raw.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


# 日线五灯之外：引擎已实现且 view/信号已亮时追加展示（W-D10 防静默黑洞）
_EXTRA_DAILY_ORDER = (
    "PS",
    "Spring",
    "BU",
    "JAC",
    "SV",
    "PSY",
    "BC",
    "ARE",
    "UT",
    "UTAD",
    "SOW",
    "LPSY",
)
_EXTRA_SIGNAL_KEYS: dict[str, str] = {
    "ps_signal": "PS",
    "spring_signal": "Spring",
    # Spring 确认（与广义 ST 分离；phase-a §4.4.2）
    "spring_test_signal": "Spring",
    "st_signal": "Spring",
    "bu_signal": "BU",
    "jac_signal": "JAC",
    "stopping_volume_signal": "SV",
    "psy_signal": "PSY",
    "bc_signal": "BC",
    "are_signal": "ARE",
    "upthrust_signal": "UT",
    "utad_signal": "UTAD",
    "sow_signal": "SOW",
    "lpsy_signal": "LPSY",
}


def _spring_confirm_lit(raw: dict[str, Any], view: dict[str, Any]) -> bool:
    """Spring 确认是否亮（st_* / spring_test_* / spring_signal；非广义 ST）。"""
    src = raw if raw else view
    if src.get("spring_test_signal") or src.get("st_signal") or src.get("spring_signal"):
        return True
    active = view.get("active_events") if isinstance(view.get("active_events"), list) else []
    return any(str(eid) in ("spring_test", "st", "spring") for eid in active)


def _accum_lit_set(raw: dict[str, Any], view: dict[str, Any]) -> set[str]:
    """吸筹灯集合：ST（二次测试）只认广义 ST；链槽 Spring确认 → 展示码 Spring。

    池链 extract 的 ST 槽仍指 Spring 确认（中文「Spring确认」），但 B/详析灯
    「ST（二次测试）」禁止并灌 spring_test（phase-a §4.4.2 / slim-b §4.4）。
    """
    src = raw if raw else view
    events: set[str] = set()
    for code in extract_accum_events(src):
        if code == "ST":
            events.add("Spring")
        else:
            events.add(code)
    # 广义 ST（测 SC）→ 灯 ST（二次测试）；抬 L2 的那条
    if src.get("secondary_test_sc_signal"):
        events.add("ST")
    if _spring_confirm_lit(src, view):
        events.add("Spring")
    active = view.get("active_events") if isinstance(view.get("active_events"), list) else []
    for eid in active:
        eid_s = str(eid)
        if eid_s == "secondary_test_sc":
            events.add("ST")
            continue
        code = _VIEW_ID_TO_CODE.get(eid_s, "")
        if code == "Spring":
            events.add("Spring")
        elif code in ACCUM_CHAIN:
            events.add(code)
    return events


def _extra_lit_codes(raw: dict[str, Any], view: dict[str, Any]) -> list[str]:
    """非五灯已亮事件（只展示引擎已点亮的，不编造未亮全集）。"""
    src = raw if raw else view
    found: set[str] = set()
    for sig, code in _EXTRA_SIGNAL_KEYS.items():
        if src.get(sig):
            found.add(code)
    active = view.get("active_events") if isinstance(view.get("active_events"), list) else []
    for eid in active:
        code = _VIEW_ID_TO_CODE.get(str(eid), "")
        if code and code not in ACCUM_CHAIN:
            found.add(code)
    # Spring 确认也可能仅由 _accum_lit_set 认出（无 spring_signal）
    if "Spring" in _accum_lit_set(raw, view):
        found.add("Spring")
    return [c for c in _EXTRA_DAILY_ORDER if c in found]


def _format_lamp_line(code: str, *, lit: bool, view: dict[str, Any], raw: dict[str, Any]) -> str:
    cn = _cn(code)
    if not lit:
        return f"○ {code}（{cn}）未亮"
    px_s = _fmt_price(_event_price_from_sources(code, view=view, raw=raw))
    if px_s:
        return f"● {code}（{cn}）{px_s}"
    return f"● {code}（{cn}）"


def _format_daily_lights(view: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    """日线默认五灯 + 其他已亮主灯（handoff §1/§2.4 + W-D10）。"""
    lit = _accum_lit_set(raw, view)
    lines = [
        _format_lamp_line(code, lit=(code in lit), view=view, raw=raw) for code in ACCUM_CHAIN
    ]
    # ST（SC区回测）未亮但 Spring 确认已亮 → 二次测试已完成，防误读（2026-08-05 ST双口径修复单 改动3）
    if "ST" not in lit and _spring_confirm_lit(raw, view):
        lines.append("（注：ST=SC区回测，强势吸筹可不回测；二次测试已完成＝看Spring确认灯）")
    for code in _extra_lit_codes(raw, view):
        lines.append(_format_lamp_line(code, lit=True, view=view, raw=raw))
    return lines


def _format_weekly_lights(view: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    active = [str(x) for x in (view.get("active_events") or [])]
    lines: list[str] = []
    seen_codes: set[str] = set()
    for eid in active:
        code = _VIEW_ID_TO_CODE.get(eid, eid.upper() if eid else "")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        cn = _cn(code)
        px = _event_price_from_sources(code, view=view, raw=raw)
        # also try detail by eid
        if px is None:
            detail = view.get("event_detail") if isinstance(view.get("event_detail"), dict) else {}
            item = detail.get(eid)
            if isinstance(item, dict) and item.get("price") is not None:
                try:
                    px = float(item["price"])
                except (TypeError, ValueError):
                    px = None
        px_s = _fmt_price(px)
        if px_s:
            lines.append(f"● {code}（{cn}）{px_s}")
        else:
            lines.append(f"● {code}（{cn}）")
    if not lines:
        lines.append("○ 其他主灯未亮")
    else:
        lines.append("○ 其他主灯未亮")
    return lines


def _slim_range_phrase(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """Slim-B 区间门禁：L0 不展示分位沿；量度只在 L3 出现。"""
    if is_phase_a_failed(raw) or is_phase_a_failed(view):
        return "无箱｜未达 L3"
    mode = _box_mode(view, raw)
    maturity = _maturity(view, raw)
    seed = str(raw.get("tr_seed_source") or "").strip().lower()
    if maturity == "L0" or mode == "none" or (seed == "percentile" and mode not in ("proto", "box")):
        return "无箱｜未达 L3"

    lo, hi = _phase_a_bounds(raw)
    if mode == "proto" or maturity == "L1":
        if lo is not None and hi is not None:
            phrase = f"雏形 {_fmt_price(lo)}～{_fmt_price(hi)}（待SC区回测）"
        elif lo is not None:
            phrase = f"雏形 {_fmt_price(lo)}（上沿未出）"
        else:
            phrase = "雏形待确认"
        return f"{phrase}｜未达 L3"

    if lo is not None and hi is not None:
        phrase = f"箱体 {_fmt_price(lo)}～{_fmt_price(hi)}"
    elif lo is not None:
        phrase = f"箱体下沿 {_fmt_price(lo)}"
    else:
        phrase = "箱体边界待确认"
    if _measure_allowed(view, raw):
        from trader_shared.wyckoff_view import format_cause_effect_display

        ce = format_cause_effect_display(raw) or format_cause_effect_display(view)
        return f"{phrase}｜{ce}" if ce else phrase
    return f"{phrase}｜未达 L3"


def _slim_measure_line(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """推演量度行（法源：wyckoff-tr-maturity-l0l3 §2.3；slim-b §3.5）。

    - measure_allowed / L3 → ``format_cause_effect_display``（有上下目标才出数字）
    - 否则 → ``未达 L3，暂不测算``（禁止贴残留假目标）
    """
    if not view and not raw:
        return "数据不足，暂不测算"
    if _measure_allowed(view, raw):
        from trader_shared.wyckoff_view import format_cause_effect_display

        ce = format_cause_effect_display(raw) or format_cause_effect_display(view)
        if ce:
            return ce
        return "已达 L3，暂无可用目标"
    return "未达 L3，暂不测算"


def _slim_lit_codes(view: dict[str, Any], raw: dict[str, Any], *, weekly: bool) -> list[str]:
    if weekly:
        codes: list[str] = []
        seen: set[str] = set()
        for eid in view.get("active_events") or []:
            code = _VIEW_ID_TO_CODE.get(str(eid), str(eid).upper())
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        if not codes:
            for code in ACCUM_CHAIN:
                if code in _accum_lit_set(raw, view):
                    codes.append(code)
        return codes
    codes = [code for code in ACCUM_CHAIN if code in _accum_lit_set(raw, view)]
    for code in _extra_lit_codes(raw, view):
        if code not in codes:
            codes.append(code)
    return codes


def _slim_post_fail_strength(view: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    """Phase A failed 后仍亮、但不属于「原吸筹链复活」的强势灯（如 SOS/LPS）。"""
    lit = _slim_lit_codes(view, raw, weekly=False)
    # SC 是旧锚事件史；AR/ST 在 failed 合同下本不应健康点亮
    return [c for c in lit if c in ("SOS", "LPS")]


def _slim_is_dist_side(view: dict[str, Any], raw: dict[str, Any]) -> bool:
    active = {str(x) for x in (view.get("active_events") or [])}
    if active & _DIST_VIEW_IDS:
        return True
    lit = set(_slim_lit_codes(view, raw, weekly=True))
    return bool(lit & _DIST_CODES)


def _slim_next_hollow(
    view: dict[str, Any],
    raw: dict[str, Any],
    *,
    failed: bool,
    weekly: bool = False,
) -> str:
    if weekly:
        if _slim_is_dist_side(view, raw):
            lit = set(_slim_lit_codes(view, raw, weekly=True))
            # ARE 无 BC：辅助派发，禁止瞎接吸筹 SC
            if "ARE" in lit and "BC" not in lit:
                return "○ 下一盯：派发未确认（缺 BC），中线观望"
            for code in _DIST_CHAIN:
                if code not in lit:
                    return f"○ {code}（{_cn(code)}）下一盯"
            return "○ 下一盯：派发侧观望"
        lit = set(_slim_lit_codes(view, raw, weekly=True))
        for code in ACCUM_CHAIN:
            if code not in lit:
                return f"○ {code}（{_cn(code)}）下一盯"
        return "○ 下一盯：回踩确认／延续"
    if failed:
        if _slim_post_fail_strength(view, raw):
            return "○ 下一盯：回踩是否站稳"
        return "○ 下一盯：本波新SC"
    lit = set(_slim_lit_codes(view, raw, weekly=False))
    # 日线已亮派发侧、吸筹链全空 → 下一盯走派发链，避免只空喊 SC
    dist_lit = lit & _DIST_CODES
    accum_lit = lit & set(ACCUM_CHAIN)
    if dist_lit and not accum_lit:
        for code in _DIST_CHAIN:
            if code not in lit:
                return f"○ {code}（{_cn(code)}）下一盯"
        return "○ 下一盯：派发侧观望"
    for code in ACCUM_CHAIN:
        if code not in lit:
            return f"○ {code}（{_cn(code)}）下一盯"
    return "○ 下一盯：回踩确认／延续"


def _format_slim_lights(view: dict[str, Any], raw: dict[str, Any], *, weekly: bool) -> list[str]:
    failed = (not weekly) and (is_phase_a_failed(raw) or is_phase_a_failed(view))
    # 破后强势：灯只列破后强势事实；旧 SC 另作历史对照，避免 SC+SOS 同框拧巴
    if (not weekly) and _slim_is_scene_change(view, raw):
        codes = _slim_post_fail_strength(view, raw)
    else:
        codes = _slim_lit_codes(view, raw, weekly=weekly)
    lines = [
        _format_lamp_line(code, lit=True, view=view, raw=raw) for code in codes
    ]
    lines.append(_slim_next_hollow(view, raw, failed=failed, weekly=weekly))
    return lines


def _slim_current_act_sentence(view: dict[str, Any], raw: dict[str, Any]) -> str:
    post = _slim_post_fail_strength(view, raw)
    if not post:
        post_s = "破后强势"
    elif len(post) == 1:
        c = post[0]
        post_s = f"{c}（{_cn(c)}）"
    else:
        post_s = "、".join(f"{c}（{_cn(c)}）" for c in post)
    return f"破后强势：{post_s}｜这是新一段，不是旧吸筹复活｜无箱"


def _slim_prev_act_lines(view: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    sc_px = _fmt_price(_event_price_from_sources("SC", view=view, raw=raw))
    head = (
        f"吸筹 Phase A：SC {sc_px} → 破位 → Phase A 失效"
        if sc_px
        else "吸筹 Phase A：破位 → Phase A 失效"
    )
    lines = [
        "📎 Phase A 失效（历史对照）",
        f"  {head}",
    ]
    if "SC" in _accum_lit_set(raw, view) or bool(raw.get("sc_signal")):
        lamp = _format_lamp_line("SC", lit=True, view=view, raw=raw)
        lines.append(f"  {lamp}（历史，不参与当前推进）")
    return lines


def _slim_structure_sentence(
    view: dict[str, Any],
    raw: dict[str, Any],
    *,
    weekly: bool = False,
    daily_scene_change: bool = False,
) -> str:
    bias = _BIAS_CN.get(str(view.get("bias") or "neutral"), "中性")
    if weekly:
        lit = set(_slim_lit_codes(view, raw, weekly=True))
        if lit & _DIST_CODES:
            main = next((c for c in _DIST_CHAIN if c in lit), next(iter(lit)))
            lead = f"{main}已亮{bias}"
            note = "｜与日线破后强势可并存（中线仍冷）" if daily_scene_change else ""
            return f"{lead}，{_slim_range_phrase(view, raw)}{note}"
        if {"SC", "AR"}.issubset(lit):
            lead = f"SC后反弹{bias}"
        elif "SC" in lit:
            lead = f"SC已亮{bias}"
        else:
            main = _primary_light_code(raw, view)
            lead = (
                f"{main}已亮{bias}"
                if main not in {"无主灯", "破后强势", "PhaseAFail"}
                else f"结构未明{bias}"
            )
        note = "｜与日线破后强势可并存（中线仍冷）" if daily_scene_change else ""
        return f"{lead}，{_slim_range_phrase(view, raw)}{note}"

    if _slim_is_scene_change(view, raw):
        return _slim_current_act_sentence(view, raw)
    if is_phase_a_failed(raw) or is_phase_a_failed(view):
        sc_px = _fmt_price(_event_price_from_sources("SC", view=view, raw=raw))
        old = f"旧筑底已破（SC {sc_px}）" if sc_px else "旧筑底已破"
        return f"{old}｜无箱｜旧吸筹链停止推进（本波无新SC）"

    lit = set(_slim_lit_codes(view, raw, weekly=False))
    if {"SC", "AR"}.issubset(lit):
        lead = f"SC后反弹{bias}"
    elif "SC" in lit:
        lead = f"SC已亮{bias}"
    else:
        main = _primary_light_code(raw, view)
        lead = f"{main}已亮{bias}" if main != "无主灯" else f"结构未明{bias}"
    return f"{lead}，{_slim_range_phrase(view, raw)}"


def _slim_change_line(change: str | None) -> str | None:
    text = str(change or "").strip()
    if not text or "首次记录" in text or "暂无对比" in text:
        return None
    parts: list[str] = []
    for raw_part in text.replace("；", "｜").split("｜"):
        part = raw_part.strip()
        if not part:
            continue
        if part.startswith("仍亮："):
            continue
        if part.startswith(("新亮：", "熄灭：")):
            payload = part.split("：", 1)[1].strip()
            if payload and payload != "无":
                parts.append(part)
    return "；".join(parts) if parts else None


def _slim_next_label(view: dict[str, Any], raw: dict[str, Any]) -> str:
    lit = set(_slim_lit_codes(view, raw, weekly=False))
    for code in ACCUM_CHAIN:
        if code not in lit:
            return f"{code}（{_cn(code)}）"
    return "回踩确认／延续"


def _slim_chain_token(
    view: dict[str, Any],
    raw: dict[str, Any],
    *,
    failed: bool,
    weekly: bool = False,
) -> str:
    """推演「现在」用的短链 token（非完整 chain_plain）。"""
    if (not weekly) and _slim_is_scene_change(view, raw):
        post = _slim_post_fail_strength(view, raw)
        return f"破后强势（{'+'.join(post)}）；Phase A 失效"
    if failed:
        return "Phase A 失效｜本波无新SC"
    # 周线 / 派发侧优先，禁止 ARE 被误当成吸筹链再「待SC」
    dist_lit = set(_slim_lit_codes(view, raw, weekly=True)) & _DIST_CODES
    if weekly or dist_lit:
        if dist_lit:
            main = next((c for c in _DIST_CHAIN if c in dist_lit), next(iter(dist_lit)))
            if "ARE" in dist_lit and "BC" not in dist_lit:
                return f"{main}（派发未确认）"
            return f"{main}，待下一派发灯"
        if weekly:
            lit_w = _slim_lit_codes(view, raw, weekly=True)
            if not lit_w:
                return "周线结构未明"
            miss = first_missing_accum(lit_w)
            chain = "→".join(lit_w)
            return f"{chain}，待{miss}" if miss else chain
    lit = _slim_lit_codes(view, raw, weekly=False)
    # 日线 token 忽略派发灯，避免 ARE 混入吸筹链
    lit = [c for c in lit if c in ACCUM_CHAIN or c in ("SOS", "LPS", "Spring")]
    if not lit:
        return "吸筹链未成型"
    miss = first_missing_accum(lit)
    chain = "→".join(lit)
    if miss:
        return f"{chain}，待{miss}"
    return chain


def _slim_weekly_watch_hint(weekly_view: dict[str, Any], weekly_raw: dict[str, Any]) -> str:
    if not weekly_view:
        return "周线数据不足"
    if _slim_is_dist_side(weekly_view, weekly_raw):
        lit = set(_slim_lit_codes(weekly_view, weekly_raw, weekly=True))
        if "ARE" in lit and "BC" not in lit:
            return "周线派发未确认（缺 BC），中线观望"
        return "周线派发侧观望"
    return f"周线盯 {_slim_next_label(weekly_view, weekly_raw)}"


def _slim_watch_lines(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
) -> list[str]:
    if _slim_is_scene_change(daily_view, daily_raw):
        return [f"日线盯回踩是否站稳；{_slim_weekly_watch_hint(weekly_view, weekly_raw)}"]
    daily_failed = is_phase_a_failed(daily_raw) or is_phase_a_failed(daily_view)
    if daily_failed:
        return [
            f"日线盯本波新SC；{_slim_weekly_watch_hint(weekly_view, weekly_raw)}"
        ]
    daily_next = _slim_next_label(daily_view, daily_raw)
    return [f"日线盯 {daily_next}；{_slim_weekly_watch_hint(weekly_view, weekly_raw)}"]


def _slim_story_lines(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
) -> list[str]:
    """B 卡短推演：现在 / 若变好 / 若变坏 / 盯（每项一行）。"""
    daily_failed = is_phase_a_failed(daily_raw) or is_phase_a_failed(daily_view)
    weekly_failed = (
        is_phase_a_failed(weekly_raw) or is_phase_a_failed(weekly_view)
        if weekly_view
        else False
    )
    scene = _slim_is_scene_change(daily_view, daily_raw)
    d_now = _slim_chain_token(daily_view, daily_raw, failed=daily_failed, weekly=False)
    if weekly_view:
        w_now = _slim_chain_token(
            weekly_view, weekly_raw, failed=weekly_failed, weekly=True
        )
        now = f"日线 {d_now}｜周线 {w_now}"
    else:
        now = f"日线 {d_now}｜周线数据不足"

    if scene:
        better = "日线回踩不破，破后强势延续（旧吸筹不复活）"
        worse = "若回踩失守、破后强势熄火，则短线转弱"
    elif daily_failed:
        better = "日线出现本波新SC"
        worse = "日线继续破位走弱则 Phase A 失效、短线更弱"
    else:
        d_next = _slim_next_label(daily_view, daily_raw)
        better = f"日线出现 {d_next} 且站稳"
        if _box_mode(daily_view, daily_raw) == "none":
            worse = "日线继续破位走弱则结构转弱"
        else:
            worse = _invalidation_phrase(daily_view, daily_raw) or "若日线结构破坏则链失效"
            if worse.startswith("失效："):
                worse = worse[len("失效：") :]

    if weekly_view and not weekly_failed and not _slim_is_dist_side(weekly_view, weekly_raw):
        if not scene:
            w_next = _slim_next_label(weekly_view, weekly_raw)
            if "确认雏形" not in better and "周线" not in better:
                better += f"；周线出 {w_next} 确认雏形"
        mode = _box_mode(weekly_view, weekly_raw)
        if mode in ("proto", "box"):
            lo, _hi = _phase_a_bounds(weekly_raw)
            if lo is None:
                lo = (weekly_view.get("tr") or {}).get("lower") if isinstance(weekly_view.get("tr"), dict) else None
            if lo is not None:
                worse += f"；周线失守 {_fmt_price(lo)} 一带则雏形不成立"
    elif weekly_view and _slim_is_dist_side(weekly_view, weekly_raw):
        better += "；周线仍偏冷，不要求跟日线同步转多"
        worse += "；周线派发若加深则中线更冷"

    watch = _slim_watch_lines(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
    )
    watch_s = watch[0] if watch else "继续观察结构"

    return [
        "现在",
        now,
        "",
        "若变好",
        better,
        "",
        "若变坏",
        worse,
        "",
        "⭐ 盯",
        watch_s,
        "本卡不下单；出手/分道看 trader",
    ]


def _pool_advice(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
) -> str:
    """入池三档（软建议，不下单）。见 handoff §2.5。"""
    w_bias = str(weekly_view.get("bias") or "neutral").strip().lower()
    w_active = {str(x) for x in (weekly_view.get("active_events") or [])}
    has_dist = bool(w_active & _DIST_VIEW_IDS)
    if not has_dist:
        # also check raw signals
        for sig in (
            "are_signal",
            "bc_signal",
            "sow_signal",
            "lpsy_signal",
            "utad_signal",
            "upthrust_signal",
        ):
            if weekly_raw.get(sig):
                has_dist = True
                break

    if w_bias == "bear" and has_dist:
        return "结构偏空，暂不建议入池"

    events = extract_accum_events(daily_raw if daily_raw else daily_view)
    ev_set = set(events)
    d_mat = _maturity(daily_view, daily_raw)
    w_mat = _maturity(weekly_view, weekly_raw)
    d_mode = _box_mode(daily_view, daily_raw)

    has_lps_sos = "LPS" in ev_set or "SOS" in ev_set
    has_sc_ar_st = {"SC", "AR", "ST"}.issubset(ev_set)
    l2_plus = d_mat in ("L2", "L3") or d_mode == "box"

    if (has_lps_sos or (has_sc_ar_st and l2_plus)) and w_bias != "bear":
        if has_lps_sos:
            return "建议入池（日线已见 LPS/SOS，周线非偏空）"
        return "建议入池（日线 SC→AR→ST 且箱体 L2+，周线非偏空）"

    # 暂不建议：链未成型 / 双 L0 / 早期无 ST 且无箱
    if d_mat == "L0" and w_mat == "L0":
        return "暂不建议入池（双线均 L0）"
    if not events:
        return "暂不建议入池（日线吸筹链未成型）"
    if "ST" not in ev_set and not has_lps_sos and d_mat in ("L0", "L1"):
        return "暂不建议入池（早期结构，尚无 ST/LPS）"
    return "暂不建议入池"


def _slim_active_codes(view: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for eid in view.get("active_events") or []:
        code = _VIEW_ID_TO_CODE.get(str(eid), str(eid).upper())
        if code:
            out.add(code)
    return out


_SLIM_SIGNAL_KEYS: dict[str, tuple[str, ...]] = {
    "SC": ("sc_signal", "wyckoff_sc_signal"),
    "AR": ("ar_signal", "wyckoff_ar_signal"),
    # ST（二次测试）只认广义 ST；Spring 确认见 _spring_confirm_lit / 额外灯
    "ST": ("secondary_test_sc_signal",),
    "LPS": ("lps_signal", "wyckoff_lps_signal"),
    "SOS": ("sos_signal", "wyckoff_sos_signal"),
    "BC": ("bc_signal",),
    "ARE": ("are_signal",),
    "SOW": ("sow_signal",),
    "LPSY": ("lpsy_signal",),
    "UTAD": ("utad_signal", "upthrust_signal"),
}


def _slim_code_lit(code: str, view: dict[str, Any], raw: dict[str, Any]) -> bool:
    active = _slim_active_codes(view)
    if code in active:
        return True
    if code in ACCUM_CHAIN and code in _accum_lit_set(raw, view):
        return True
    return any(bool(raw.get(key)) for key in _SLIM_SIGNAL_KEYS.get(code, ()))


def _slim_lit_set(
    chain: tuple[str, ...],
    view: dict[str, Any],
    raw: dict[str, Any],
) -> set[str]:
    return {code for code in chain if _slim_code_lit(code, view, raw)}


def _format_slim_full_lights(
    chain: tuple[str, ...],
    view: dict[str, Any],
    raw: dict[str, Any],
    *,
    weekly: bool = False,
) -> list[str]:
    """竖排满灯。

    日线默认主槽仍是吸筹五灯；已亮的派发/辅助 extras（BC/ARE/LPSY…）
    必须附在后面，避免 🔔「新亮 LPSY」但灯区全空心。
    """
    daily_failed = (not weekly) and (_slim_daily_failed(view, raw))
    lines: list[str] = []
    shown: set[str] = set()

    def _lit_line(code: str, *, lit: bool) -> str:
        if not lit:
            return f"○ {code}（{_cn(code)}）"
        px_s = _fmt_price(_event_price_from_sources(code, view=view, raw=raw))
        tag = _slim_lamp_price_tag(
            code, lit=True, weekly=weekly, daily_failed=daily_failed
        )
        core = f"● {code}（{_cn(code)}）"
        if px_s:
            core += px_s
        if tag:
            core += tag
        return core

    for code in chain:
        lit = _slim_code_lit(code, view, raw)
        lines.append(_lit_line(code, lit=lit))
        shown.add(code)

    # 日线吸筹主槽之外：附已亮 extras（含 LPSY 等派发灯）
    if (not weekly) and chain == tuple(ACCUM_CHAIN):
        for code in _extra_lit_codes(raw, view):
            if code in shown:
                continue
            # Spring 下面单独处理注释；这里先画灯
            lines.append(_lit_line(code, lit=True))
            shown.add(code)
        if _spring_confirm_lit(raw, view) and "Spring" not in shown:
            lines.append(_lit_line("Spring", lit=True))
            shown.add("Spring")
        if "Spring" in shown and not _slim_code_lit("ST", view, raw):
            lines.append(
                "（注：ST=SC区回测，强势吸筹可不回测；二次测试已完成＝看Spring确认灯）"
            )
    elif chain == tuple(ACCUM_CHAIN) and _spring_confirm_lit(raw, view):
        # 周线若仍走吸筹链，保留原 Spring 附灯
        if "Spring" not in shown:
            lines.append(_lit_line("Spring", lit=True))
        if not _slim_code_lit("ST", view, raw):
            lines.append(
                "（注：ST=SC区回测，强势吸筹可不回测；二次测试已完成＝看Spring确认灯）"
            )
    return lines


def _slim_weekly_side(view: dict[str, Any], raw: dict[str, Any]) -> str:
    bias = str(view.get("bias") or "neutral").strip().lower()
    if _slim_is_dist_side(view, raw) or bias == "bear":
        return "distribution"
    return "accumulation"


def _slim_range_head(view: dict[str, Any], raw: dict[str, Any]) -> str:
    phrase = _slim_range_phrase(view, raw)
    return phrase.split("｜", 1)[0]


def _slim_failed_anchor_ref(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """failed → L0：禁止健康雏形/箱体；只写旧 SC 低点供对照（不带上沿冒充区间）。"""
    lo, _hi = _phase_a_bounds(raw)
    if lo is not None:
        return f"旧SC {_fmt_price(lo)}（对照）"
    px = _event_price_from_sources("SC", view=view, raw=raw)
    px_s = _fmt_price(px)
    if px_s:
        return f"旧SC {px_s}（对照）"
    return ""


def _slim_phase_display(view: dict[str, Any]) -> str | None:
    """有明确 phase 时套 Phase X · 中文；无则不强编（不写「有效」）。"""
    phase = str(view.get("phase") or "").strip().lower()
    label = str(view.get("phase_label") or "").strip()
    mapping = {
        "accumulation_a": "Phase A · 止跌开场",
        "accumulation_b": "Phase B · 建因横盘",
        "accumulation_c": "Phase C · 试盘",
        "accumulation_d": "Phase D · 强度确认",
        "accumulation_e": "Phase E · 离开区间",
        "markup": "Phase E · 离开区间",
    }
    if phase in mapping:
        return mapping[phase]
    # 仅当 label 已点明 B/C（或 A/D/E）时套用，避免无 phase 字段时假写
    for key, text in (
        ("积累期 a", mapping["accumulation_a"]),
        ("积累期a", mapping["accumulation_a"]),
        ("吸筹a", mapping["accumulation_a"]),
        ("吸筹 a", mapping["accumulation_a"]),
        ("phase a", mapping["accumulation_a"]),
        ("积累期 b", mapping["accumulation_b"]),
        ("积累期b", mapping["accumulation_b"]),
        ("吸筹b", mapping["accumulation_b"]),
        ("吸筹 b", mapping["accumulation_b"]),
        ("phase b", mapping["accumulation_b"]),
        ("积累期 c", mapping["accumulation_c"]),
        ("积累期c", mapping["accumulation_c"]),
        ("吸筹c", mapping["accumulation_c"]),
        ("吸筹 c", mapping["accumulation_c"]),
        ("phase c", mapping["accumulation_c"]),
        ("积累期 d", mapping["accumulation_d"]),
        ("积累期d", mapping["accumulation_d"]),
        ("吸筹d", mapping["accumulation_d"]),
        ("吸筹 d", mapping["accumulation_d"]),
        ("phase d", mapping["accumulation_d"]),
        ("积累期 e", mapping["accumulation_e"]),
        ("积累期e", mapping["accumulation_e"]),
        ("吸筹e", mapping["accumulation_e"]),
        ("吸筹 e", mapping["accumulation_e"]),
        ("phase e", mapping["accumulation_e"]),
    ):
        if key in label.lower():
            return text
    return None


def _slim_weekly_stage_short(view: dict[str, Any], raw: dict[str, Any]) -> str:
    if not view:
        return "周线数据不足"
    side = _slim_weekly_side(view, raw)
    bias = _BIAS_CN.get(str(view.get("bias") or "neutral"), "中性")
    if side == "distribution":
        lit = _slim_lit_set(_DIST_CHAIN, view, raw)
        if "ARE" in lit and "BC" not in lit:
            return "ARE 先亮但缺 BC，派发未确认"
        main = next((code for code in _DIST_CHAIN if code in lit), "")
        if main:
            return f"{main} 已亮，派发侧观察"
        return "派发未确认"

    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    range_head = _slim_range_head(view, raw)
    if {"SC", "AR"}.issubset(lit):
        # L1 雏形有价就写进总览，方便对照（非成熟箱体）
        if "雏形" in range_head or "箱体" in range_head:
            return f"SC后反弹，{range_head}"
        return "SC后反弹，雏形待SC区回测"
    if "SC" in lit:
        if "雏形" in range_head:
            return f"SC 已亮，{range_head}"
        return "SC 已亮，待 AR"
    if lit:
        main = next((code for code in ACCUM_CHAIN if code in lit), next(iter(lit)))
        return f"{main} 已亮，结构观察"
    return f"{bias}，结构未明"


def _slim_weekly_tier(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """周/总动作建议（展示用，不下单）。"""
    if not view:
        return "谨慎"
    side = _slim_weekly_side(view, raw)
    if side == "distribution" or str(view.get("bias") or "").strip().lower() == "bear":
        return "暂不参与"
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    maturity = _maturity(view, raw)
    if lit & {"LPS", "SOS"} or maturity in ("L2", "L3"):
        return "可跟踪"
    return "谨慎"


def _slim_weekly_sentence(view: dict[str, Any], raw: dict[str, Any]) -> str:
    if not view:
        return "周线数据不足｜无箱｜未达 L3"
    bias = _BIAS_CN.get(str(view.get("bias") or "neutral"), "中性")
    side = _slim_weekly_side(view, raw)
    if side == "distribution":
        lit = _slim_lit_set(_DIST_CHAIN, view, raw)
        if "ARE" in lit and "BC" not in lit:
            # 周线 failed + 真实派发灯：不得空「派发未确认」盖住失效（wyckoff-b-card-spring-st §3 #5）
            if is_phase_a_failed(raw) or is_phase_a_failed(view):
                return "Phase A 失效｜派发侧另察（ARE 先亮但缺 BC 确认）"
            return "ARE（自动回落）先亮但缺 BC（买力高潮）确认｜派发未确认｜中线观望"
        main = next((code for code in _DIST_CHAIN if code in lit), "")
        if main:
            return f"{main}（{_cn(main)}）已亮{bias}｜{_slim_range_phrase(view, raw)}"
        if is_phase_a_failed(raw) or is_phase_a_failed(view):
            return f"Phase A 失效{bias}｜派发侧另察"
        return f"派发侧{bias}｜派发未确认｜中线观望"

    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if is_phase_a_failed(raw) or is_phase_a_failed(view):
        return "Phase A 失效｜本波无新SC"
    if {"SC", "AR"}.issubset(lit):
        return f"SC后反弹{bias}，{_slim_range_phrase(view, raw)}"
    if "SC" in lit:
        return f"SC已亮{bias}，{_slim_range_phrase(view, raw)}"
    main = next((code for code in ACCUM_CHAIN if code in lit), "")
    if main:
        return f"{main}（{_cn(main)}）已亮{bias}，{_slim_range_phrase(view, raw)}"
    return f"结构未明{bias}｜{_slim_range_phrase(view, raw)}"


def _slim_daily_failed(view: dict[str, Any], raw: dict[str, Any]) -> bool:
    return is_phase_a_failed(raw) or is_phase_a_failed(view)


def _slim_daily_wave_short(view: dict[str, Any], raw: dict[str, Any]) -> str:
    failed = _slim_daily_failed(view, raw)
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if failed:
        if "SOS" in lit:
            return "Phase A 失效 · 破后强势｜本波 SOS 强"
        if "LPS" in lit:
            return "Phase A 失效｜本波 LPS 修复"
        return "Phase A 失效｜本波无新SC"
    if "SOS" in lit:
        event = f"SOS 强｜{_slim_range_head(view, raw)}"
    elif "LPS" in lit:
        event = f"LPS 修复｜{_slim_range_head(view, raw)}"
    elif "ST" in lit:
        event = f"ST 已现｜{_slim_range_head(view, raw)}"
    elif _spring_confirm_lit(raw, view):
        event = f"Spring 确认｜{_slim_range_head(view, raw)}"
    elif "AR" in lit:
        event = f"AR 反弹｜{_slim_range_head(view, raw)}"
    elif "SC" in lit:
        event = f"SC 已现｜{_slim_range_head(view, raw)}"
    else:
        event = f"本波未成型｜{_slim_range_head(view, raw)}"
    phase_head = _slim_phase_display(view)
    if phase_head:
        return f"{phase_head}｜{event}"
    return event


def _slim_daily_sentence(view: dict[str, Any], raw: dict[str, Any]) -> str:
    failed = _slim_daily_failed(view, raw)
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if failed:
        ref = _slim_failed_anchor_ref(view, raw)
        ref_tail = f"｜{ref}" if ref else ""
        if "SOS" in lit:
            return f"Phase A 失效 · 破后强势｜本波 SOS 强{ref_tail}"
        if "LPS" in lit:
            return f"Phase A 失效｜本波 LPS 修复{ref_tail}"
        return f"Phase A 失效｜本波无新SC{ref_tail}"
    wave = _slim_daily_wave_short(view, raw)
    full_range = _slim_range_phrase(view, raw)
    range_head = _slim_range_head(view, raw)
    if f"｜{range_head}" in wave:
        tail = full_range.split("｜", 1)[1] if "｜" in full_range else ""
        return f"{wave}｜{tail}" if tail else wave
    return f"{wave}｜{full_range}"


def _slim_daily_explain(view: dict[str, Any], raw: dict[str, Any]) -> str | None:
    if not _slim_daily_failed(view, raw):
        return None
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if "SOS" in lit:
        return "说明：●SC 是旧底事实，●SOS 是本波强势事实；不按顺序推进读。"
    if "LPS" in lit:
        return "说明：旧底事实与本波修复事实并列；不按顺序推进读。"
    return None


def _slim_chain_now(
    chain: tuple[str, ...],
    view: dict[str, Any],
    raw: dict[str, Any],
    *,
    weekly: bool,
) -> str:
    lit = [code for code in chain if _slim_code_lit(code, view, raw)]
    if weekly and chain == _DIST_CHAIN:
        if "ARE" in lit and "BC" not in lit:
            return "ARE（自动回落）先亮但缺 BC（买力高潮），派发未确认"
        return "→".join(lit) if lit else "派发未确认"
    if not lit:
        if not weekly and _spring_confirm_lit(raw, view):
            # 孤岛 Spring 确认：不得写成「ST，待 SC」
            return "Spring（弹簧确认），待 SC（卖力高潮）"
        return "结构未明" if weekly else "本波未成型"
    missing = next((code for code in chain if code not in lit), "")
    text = "→".join(lit)
    if missing and not (not weekly and _slim_daily_failed(view, raw)):
        text += f"，待 {missing}（{_cn(missing)}）"
    return text


def _slim_weekly_story_lines(view: dict[str, Any], raw: dict[str, Any]) -> dict[str, str]:
    if not view:
        return {
            "now": "数据不足",
            "better": "补足周线数据后再评估",
            "worse": "数据不足时不引用箱沿",
            "watch": "先补周线结构",
        }
    side = _slim_weekly_side(view, raw)
    chain = _DIST_CHAIN if side == "distribution" else tuple(ACCUM_CHAIN)
    lit = _slim_lit_set(chain, view, raw)
    now = _slim_chain_now(chain, view, raw, weekly=True)
    if side == "distribution":
        if "ARE" in lit and "BC" not in lit:
            return {
                "now": now,
                "better": "派发未确认先观望，需后续结构证伪偏空",
                "worse": "出现 SOW（弱势信号）则派发压力加深",
                "watch": "盯 BC（买力高潮）是否确认，未确认则观望",
            }
        return {
            "now": now,
            "better": "派发压力缓和后再重看吸筹侧",
            "worse": "派发链继续加深则中线更冷",
            "watch": "盯派发链是否继续点亮",
        }

    range_head = _slim_range_head(view, raw)
    if "ST" not in lit and {"SC", "AR"}.issubset(lit):
        better = "出现 ST（二次测试）并守住雏形下沿"
        watch = "盯 ST（二次测试）是否出现"
    else:
        missing = next((code for code in ACCUM_CHAIN if code not in lit), "")
        if missing == "SC":
            better = "出现本波新SC"
            watch = "盯本波新SC"
        elif missing:
            better = f"出现 {missing}（{_cn(missing)}）并站稳"
            watch = f"盯 {missing}（{_cn(missing)}）"
        else:
            better = "吸筹链保持完整并延续"
            watch = "盯回踩是否守住"
    worse = "失守雏形下沿，雏形不成立" if "雏形" in range_head else "结构继续转弱则保持观察"
    lo, _hi = _phase_a_bounds(raw)
    if lo is not None and ("雏形" in range_head or "箱体" in range_head):
        worse = f"失守 {_fmt_price(lo)} 一带，结构不成立"
    return {"now": now, "better": better, "worse": worse, "watch": watch}


def _slim_daily_story_lines(view: dict[str, Any], raw: dict[str, Any]) -> dict[str, str]:
    failed = _slim_daily_failed(view, raw)
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if failed:
        if "SOS" in lit:
            return {
                "now": "Phase A 失效 · 破后强势｜本波 SOS 强",
                "better": "回踩不破并继续站稳 SOS（强势信号）区域",
                "worse": "SOS 熄火或继续破位则保持无箱观察",
                "watch": "盯 SOS（强势信号）后回踩是否站稳",
            }
        if "LPS" in lit:
            return {
                "now": "Phase A 失效｜本波 LPS 修复",
                "better": "修复延续并出现 SOS（强势信号）",
                "worse": "修复失败则本波无新SC",
                "watch": "盯 LPS（最后支撑点）修复是否守住",
            }
        return {
            "now": "Phase A 失效｜本波无新SC",
            "better": "出现本波新SC",
            "worse": "继续破位则保持无箱观察",
            "watch": "盯本波新SC",
        }

    now = _slim_chain_now(tuple(ACCUM_CHAIN), view, raw, weekly=False)
    missing = next((code for code in ACCUM_CHAIN if code not in lit), "")
    if missing == "SC":
        better = "出现本波新SC"
        watch = "盯本波新SC"
    elif missing:
        better = f"出现 {missing}（{_cn(missing)}）并站稳"
        watch = f"盯 {missing}（{_cn(missing)}）"
    else:
        better = "吸筹链保持完整并延续"
        watch = "盯回踩是否守住"
    if _box_mode(view, raw) == "none":
        worse = "继续破位则保持无箱观察"
    else:
        lo, _hi = _phase_a_bounds(raw)
        worse = f"失守 {_fmt_price(lo)} 一带则本波转弱" if lo is not None else "结构破坏则本波转弱"
    return {"now": now, "better": better, "worse": worse, "watch": watch}


def _oneline_compress(view: dict[str, Any], raw: dict[str, Any]) -> str:
    """一句话：阶段（phase_label）必带，避免详析阶段黑洞（W-D10）。"""
    phase = _panel_fail_copy(str(view.get("phase_label") or view.get("phase") or "").strip())
    if phase in ("none", "None"):
        phase = "无明确阶段"
    summary = _panel_fail_copy(str(view.get("summary_oneline") or "").strip())
    if summary:
        if len(summary) > 40:
            summary = summary[:38] + "…"
        if phase:
            return f"{phase}｜{summary}"
        return summary
    bias = _BIAS_CN.get(str(view.get("bias") or "neutral"), "中性")
    primary = _primary_light_label(raw, view)
    if phase:
        return f"{phase}｜{bias} · {primary}"
    return f"{bias} · {primary}"


def _story_block(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
    chain_plain: str,
    pool_line: str,
) -> list[str]:
    events = extract_accum_events(daily_raw if daily_raw else daily_view)
    miss = first_missing_accum(events)
    w_bias = _BIAS_CN.get(str(weekly_view.get("bias") or "neutral"), "中性")
    d_bias = _BIAS_CN.get(str(daily_view.get("bias") or "neutral"), "中性")
    d_range = _range_phrase(daily_view, daily_raw)
    d_inv = _invalidation_phrase(daily_view, daily_raw)
    daily_failed = is_phase_a_failed(daily_raw) or is_phase_a_failed(daily_view)
    chain_plain = _display_chain_plain(chain_plain, daily_raw, daily_view)

    # 现在
    now_parts = [chain_plain or "威：吸筹链未成型", f"日线{d_bias}", f"周线背景{w_bias}"]
    now = "｜".join(now_parts)

    # 若变好（failed 与默认 B 同源：Phase A 失效｜本波无新SC）
    if daily_failed:
        better = "Phase A 失效｜本波无新SC；观察是否出现本波新SC"
    elif miss:
        miss_cn = _cn(miss)
        better = f"若出现 {miss}（{miss_cn}）且站稳，链可推进"
        px = _event_price_from_sources(miss, view=daily_view, raw=daily_raw)
        # miss 未亮通常无价；引用已批准箱沿作背景（L1/L2）
        mode = _box_mode(daily_view, daily_raw)
        if mode in ("proto", "box"):
            lo, hi = _phase_a_bounds(daily_raw)
            if miss in ("LPS", "ST", "Spring") and lo is not None:
                better += f"；关注下沿{_fmt_price(lo)}一带是否守住"
            elif miss == "SOS" and hi is not None:
                better += f"；关注站稳上沿{_fmt_price(hi)}之上"
        if px is not None:
            better += f"；参考位{_fmt_price(px)}"
    else:
        better = "吸筹链已齐；关注回踩 LPS（最后支撑点）是否守住、Markup（主升）是否延续"

    # 若变坏
    worse = d_inv if d_inv else "暂无明确失效价"
    if "无成熟箱" in d_range or _box_mode(daily_view, daily_raw) == "none":
        worse = "暂无明确失效价；若日线继续破位走弱则链失效"

    # 盯
    if daily_failed:
        watch = f"盯本波新SC；区间：{d_range}"
    elif miss:
        watch = f"盯下一灯 {miss}（{_cn(miss)}）；区间：{d_range}"
    else:
        watch = f"盯回踩是否守住；区间：{d_range}"

    return [
        "🔮 故事链（以日线推进；周线作背景）",
        "",
        "现在",
        now,
        "",
        "若变好",
        better,
        "",
        "若变坏",
        worse,
        "",
        "⭐ 盯",
        watch,
        "",
        f"入池：{pool_line}",
        "说明：本卡不下单；买卖看 trader 门禁；分道仍听 trader",
    ]


def format_light_change(
    prev: dict[str, Any] | None,
    curr: dict[str, Any],
) -> str:
    """🔔 变化文案。prev 为空 → 首次记录。"""
    if not prev:
        return "首次记录，暂无对比"

    def _codes(entry: dict[str, Any], key: str) -> set[str]:
        vals = entry.get(key) or []
        return {str(x) for x in vals}

    prev_d = _codes(prev, "daily_events")
    prev_w = _codes(prev, "weekly_events")
    curr_d = _codes(curr, "daily_events")
    curr_w = _codes(curr, "weekly_events")
    prev_all = prev_d | {f"W:{c}" for c in prev_w}
    curr_all = curr_d | {f"W:{c}" for c in curr_w}

    # 展示用：合并日周，周线加「周」前缀避免混淆
    def _label(token: str) -> str:
        if token.startswith("W:"):
            code = token[2:]
            return f"周{code}（{_cn(code)}）"
        return f"{token}（{_cn(token)}）"

    new_lit = sorted(curr_all - prev_all)
    still = sorted(curr_all & prev_all)
    gone = sorted(prev_all - curr_all)

    parts: list[str] = []
    parts.append("新亮：" + ("、".join(_label(x) for x in new_lit) if new_lit else "无"))
    parts.append("仍亮：" + ("、".join(_label(x) for x in still) if still else "无"))
    parts.append("熄灭：" + ("、".join(_label(x) for x in gone) if gone else "无"))
    return "｜".join(parts)


def build_light_snapshot_entry(
    plan: dict[str, Any],
    *,
    ts: str | None = None,
) -> dict[str, Any]:
    """从 plan 提取快照条目（不写盘）。"""
    from datetime import datetime, timezone

    daily_view = _as_view(plan.get("daily_view"))
    weekly_view = _as_view(plan.get("weekly_view"))
    daily_raw = _as_raw(plan.get("daily_raw"))
    weekly_raw = _as_raw(plan.get("weekly_raw"))

    # 五灯链 + 已亮非五灯（与详析灯块同源，供 🔔 变化对比）
    # ST 仅广义二次测试；Spring 确认走 extras（禁止 snapshot 把 Spring 记成 ST）
    lit = _accum_lit_set(daily_raw if daily_raw else daily_view, daily_view)
    chain = [c for c in ACCUM_CHAIN if c in lit]
    extras = _extra_lit_codes(daily_raw, daily_view)
    daily_events = chain + [c for c in extras if c not in chain]
    weekly_codes: list[str] = []
    seen: set[str] = set()
    for eid in weekly_view.get("active_events") or []:
        code = _VIEW_ID_TO_CODE.get(str(eid), str(eid).upper())
        if code and code not in seen:
            seen.add(code)
            weekly_codes.append(code)

    daily_prices: dict[str, float] = {}
    for code in daily_events:
        px = _event_price_from_sources(code, view=daily_view, raw=daily_raw)
        if px is not None:
            daily_prices[code] = round(px, 4)

    weekly_prices: dict[str, float] = {}
    for code in weekly_codes:
        px = _event_price_from_sources(code, view=weekly_view, raw=weekly_raw)
        if px is not None:
            weekly_prices[code] = round(px, 4)

    return {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "daily_events": list(daily_events),
        "weekly_events": weekly_codes,
        "daily_prices": daily_prices,
        "weekly_prices": weekly_prices,
    }


def render_wyckoff_card(plan: dict[str, Any]) -> str:
    """单票威科夫结构短卡（--brief）。

    plan 字段：name/code/price/chain_plain/daily_view/weekly_view/
    event_line/data_ok/error
    """
    _warn_contradictory_phase_a(plan)
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
    daily_raw = _as_raw(plan.get("daily_raw"))

    # 面板可见串做失败→失效映射（骨架不变；core fail_reason 不动）
    phase = _panel_fail_copy(str(daily.get("phase_label") or daily.get("phase") or "未知"))
    bias = _BIAS_CN.get(str(daily.get("bias") or "neutral"), "中性")
    chain = _panel_fail_copy(_display_chain_plain(plan.get("chain_plain"), daily_raw, daily))
    events = _panel_fail_copy(_events_line(daily, plan.get("event_line")))
    tr_line = _fmt_tr(daily.get("tr") if isinstance(daily.get("tr"), dict) else None)
    invalid = _panel_fail_copy(str(daily.get("invalidation_hint") or "暂无明确失效价"))
    oneline = _panel_fail_copy(str(daily.get("summary_oneline") or "无摘要"))

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

    w_phase = _panel_fail_copy(str(weekly.get("phase_label") or weekly.get("phase") or "").strip())
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



def _slim_board_weekly_label(view: dict[str, Any], raw: dict[str, Any]) -> str:
    if not view:
        return "结构未明"
    if _slim_is_dist_side(view, raw):
        lit = _slim_lit_set(_DIST_CHAIN, view, raw)
        if "ARE" in lit and "BC" not in lit:
            return "派发未确认"
        return "派发中"
    if is_phase_a_failed(raw) or is_phase_a_failed(view):
        return "吸筹失效"
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if lit:
        return "吸筹中"
    return "结构未明"


def _slim_board_daily_label(view: dict[str, Any], raw: dict[str, Any]) -> str:
    if not view and not raw:
        return "结构未明"
    failed = _slim_daily_failed(view, raw)
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), view, raw)
    if failed:
        if "SOS" in lit:
            return "破后强势"
        if "LPS" in lit:
            return "修复中"
        return "本波无新SC"
    if not lit and not _spring_confirm_lit(raw, view):
        return "本波未成型"
    if lit or _spring_confirm_lit(raw, view):
        return "链推进中"
    return "结构未明"


def _slim_action_tier(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
    pool_line: str,
) -> str:
    """动作建议：暂不参与 / 谨慎 / 等确认 / 可跟踪（非下单指令）。"""
    if pool_line.startswith("建议入池"):
        return "可跟踪"
    if pool_line.startswith("结构偏空") or "双线均 L0" in pool_line:
        return "暂不参与"
    d_lab = _slim_board_daily_label(daily_view, daily_raw)
    w_lab = _slim_board_weekly_label(weekly_view, weekly_raw)
    if d_lab in ("本波未成型", "本波无新SC") or w_lab in ("派发中", "派发未确认"):
        return "暂不参与"
    lit = _slim_lit_set(tuple(ACCUM_CHAIN), daily_view, daily_raw)
    miss = next((c for c in ACCUM_CHAIN if c not in lit), "")
    if lit and miss and not _slim_daily_failed(daily_view, daily_raw):
        return "等确认"
    return "谨慎"


def _slim_situation_reason(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
) -> str:
    w = _slim_board_weekly_label(weekly_view, weekly_raw)
    d = _slim_board_daily_label(daily_view, daily_raw)
    w_part = {
        "派发中": "中线派发",
        "派发未确认": "中线派发未确认",
        "吸筹失效": "周线吸筹失效",
        "吸筹中": "中线吸筹中",
        "结构未明": "周线结构未明",
    }.get(w, w)
    d_part = {
        "本波未成型": "日线吸筹未成型",
        "本波无新SC": "日线本波无新SC",
        "破后强势": "日线破后强势",
        "修复中": "日线修复中",
        "链推进中": "日线链推进中",
        "结构未明": "日线结构未明",
    }.get(d, d)
    return f"{w_part}，{d_part}"


def _slim_stance_better_worse(
    *,
    daily_view: dict[str, Any],
    weekly_view: dict[str, Any],
    daily_raw: dict[str, Any],
    weekly_raw: dict[str, Any],
) -> tuple[str, str]:
    w_lab = _slim_board_weekly_label(weekly_view, weekly_raw)
    d_lab = _slim_board_daily_label(daily_view, daily_raw)
    if w_lab in ("派发中", "派发未确认") and d_lab in ("本波未成型", "本波无新SC"):
        return (
            "派发缓和，并且出现本波新SC",
            "派发再加深，或日线无SC继续破位",
        )
    if d_lab == "本波无新SC":
        return ("出现本波新SC", "日线无SC继续破位")
    if d_lab == "本波未成型":
        return ("出现本波新SC", "日线无SC继续破位")
    if d_lab == "破后强势":
        return (
            "回踩不破并继续站稳 SOS（强势信号）区域",
            "SOS 熄火或继续破位则保持无箱观察",
        )
    if d_lab == "修复中":
        return (
            "修复延续并出现 SOS（强势信号）",
            "修复失败则本波无新SC",
        )
    w_story = _slim_weekly_story_lines(weekly_view, weekly_raw)
    d_story = _slim_daily_story_lines(daily_view, daily_raw)
    better_parts = []
    for part in (w_story.get("better"), d_story.get("better")):
        s = str(part or "").strip()
        if s and s not in better_parts:
            better_parts.append(s)
    worse_parts = []
    for part in (w_story.get("worse"), d_story.get("worse")):
        s = str(part or "").strip()
        if s and s not in worse_parts:
            worse_parts.append(s)
    better = "；".join(better_parts) if better_parts else "结构改善并站稳"
    worse = "；".join(worse_parts) if worse_parts else "结构转弱则保持观察"
    return better, worse


def _slim_lamp_price_tag(
    code: str,
    *,
    lit: bool,
    weekly: bool,
    daily_failed: bool,
) -> str:
    if not lit:
        return ""
    if weekly and code in _DIST_CODES:
        return "（事件价）"
    if (not weekly) and daily_failed and code == "SC":
        return "（对照）"
    return ""



def render_wyckoff_slim(plan: dict[str, Any]) -> str:
    """默认 B·中剪瘦身卡（--target）。

    旧完整详析保留在 render_wyckoff_detail，供 --full 使用。
    局/姿态 + 现在/变好/变差：见 wyckoff-stance-posture-handoff。
    """
    _warn_contradictory_phase_a(plan)
    name = str(plan.get("name") or plan.get("target") or "未知")
    code = str(plan.get("code") or "")
    price_s = _fmt_price(plan.get("price")) or "—"
    title = f"{name}（{code}）｜现价 {price_s}" if code else f"{name}｜现价 {price_s}"
    if plan.get("error") and not plan.get("data_ok", True):
        err = str(plan.get("error") or "数据不足")
        lines = [
            title,
            "状态：数据不足",
            "动作：谨慎｜数据不足",
            "周线：中性｜数据不足",
            f"日线本波：{err}",
            "",
            "📌 现在 / 变好 / 变差",
            "  现在：谨慎｜数据不足",
            "  变好：数据齐全后再评估",
            "  变差：数据不足时不引用箱沿",
        ]
        return "\n".join(lines)

    daily_view = _as_view(plan.get("daily_view"))
    weekly_view = _as_view(plan.get("weekly_view"))
    daily_raw = _as_raw(plan.get("daily_raw"))
    weekly_raw = _as_raw(plan.get("weekly_raw"))
    w_bias = _BIAS_CN.get(str(weekly_view.get("bias") or "neutral"), "中性")
    weekly_side = _slim_weekly_side(weekly_view, weekly_raw) if weekly_view else "accumulation"
    weekly_chain = _DIST_CHAIN if weekly_side == "distribution" else tuple(ACCUM_CHAIN)
    pool_line = _pool_advice(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
    )
    w_lab = _slim_board_weekly_label(weekly_view, weekly_raw)
    d_lab = _slim_board_daily_label(daily_view, daily_raw)
    action = _slim_action_tier(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
        pool_line=pool_line,
    )
    situation = _slim_situation_reason(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
    )
    better, worse = _slim_stance_better_worse(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
    )

    action_line = _slim_weekly_tier(weekly_view, weekly_raw)
    # 动作以综合档为准；周线偏空/派发时与综合档取更冷
    if action == "暂不参与" or action_line == "暂不参与":
        action_show = "暂不参与"
    elif action == "可跟踪" and action_line == "可跟踪":
        action_show = "可跟踪"
    elif action == "等确认":
        action_show = "等确认"
    elif action_line == "可跟踪" and action != "暂不参与":
        action_show = "可跟踪"
    else:
        action_show = action if action in ("暂不参与", "等确认", "可跟踪", "谨慎") else action_line

    # 入池与动作冷建议重复：仅「建议入池」并入动作行；暂不建议不再单列
    action_display = action_show
    if pool_line.startswith("建议入池"):
        reason = pool_line[len("建议入池"):].strip()
        # reason like "（日线已见…）"
        action_display = f"{action_show}｜建议入池{reason}" if reason else f"{action_show}｜建议入池"

    lines: list[str] = [
        title,
        f"状态：{situation}",
        f"动作：{action_display}",
        f"周线：{w_lab}｜{w_bias}｜{_slim_weekly_stage_short(weekly_view, weekly_raw)}",
        f"日线本波：{_slim_daily_wave_short(daily_view, daily_raw)}",
        "",
        f"🧭 周线 · {w_lab}",
        f"  {_slim_weekly_sentence(weekly_view, weekly_raw)}",
        "  灯",
    ]
    for lamp in _format_slim_full_lights(
        weekly_chain, weekly_view, weekly_raw, weekly=True
    ):
        lines.append(f"  {lamp}")

    lines.extend(
        [
            "",
            f"⚡ 日线 · {d_lab}",
            f"  {_slim_daily_sentence(daily_view, daily_raw)}",
        ]
    )
    explain = _slim_daily_explain(daily_view, daily_raw)
    if explain:
        lines.append(f"  {explain}")
    lines.append("  灯")
    for lamp in _format_slim_full_lights(
        tuple(ACCUM_CHAIN), daily_view, daily_raw, weekly=False
    ):
        lines.append(f"  {lamp}")

    change = _slim_change_line(plan.get("change_line"))
    if change:
        lines.extend(["", "🔔 变化", f"  {change}"])

    lines.extend(
        [
            "",
            "📌 现在 / 变好 / 变差",
            f"  现在：{action_show}｜{situation}",
            f"  变好：{better}",
            f"  变差：{worse}",
        ]
    )

    text = "\n".join(lines)
    for bad in _FORBIDDEN_BUY_WORDS:
        if bad in text:
            text = text.replace(bad, "（结构参考）")
    return text



def render_wyckoff_detail(plan: dict[str, Any]) -> str:
    """单票威科夫完整详析卡（--full）。

    plan：name/code/price/daily_view/weekly_view/daily_raw/weekly_raw/
    chain_plain/change_line/data_ok/error
    纯展示；灯变化文案由调用方写入 change_line（对比在写快照前完成）。
    """
    _warn_contradictory_phase_a(plan)
    if plan.get("error") and not plan.get("data_ok", True):
        name = str(plan.get("name") or plan.get("target") or "未知")
        code = str(plan.get("code") or "")
        title = f"威科夫详析 — {name}" + (f"（{code}）" if code else "") + "｜日线+周线"
        return "\n".join(
            [
                title,
                "",
                "📊 现况",
                f"  ⚠ {plan['error']}",
                "",
                "💬 综述",
                "  数据不足，仅现价；本卡不下单",
            ]
        )

    name = str(plan.get("name") or "未知")
    code = str(plan.get("code") or "")
    price_s = _fmt_price(plan.get("price")) or "—"
    daily_view = _as_view(plan.get("daily_view"))
    weekly_view = _as_view(plan.get("weekly_view"))
    daily_raw = _as_raw(plan.get("daily_raw"))
    weekly_raw = _as_raw(plan.get("weekly_raw"))
    chain_plain = _panel_fail_copy(
        _display_chain_plain(plan.get("chain_plain"), daily_raw, daily_view)
    )

    d_bias = _BIAS_CN.get(str(daily_view.get("bias") or "neutral"), "中性")
    w_bias = _BIAS_CN.get(str(weekly_view.get("bias") or "neutral"), "中性")
    d_primary = _primary_light_label(daily_raw, daily_view)
    w_primary = _primary_light_label(weekly_raw, weekly_view) if weekly_view else "无主灯"

    d_meas = _measure_allowed(daily_view, daily_raw)
    w_meas = _measure_allowed(weekly_view, weekly_raw) if weekly_view else False
    meas_label = "已给出" if (d_meas or w_meas) else "均未达 L3"

    change = _panel_fail_copy(str(plan.get("change_line") or "首次记录，暂无对比").strip())

    pool_line = _pool_advice(
        daily_view=daily_view,
        weekly_view=weekly_view,
        daily_raw=daily_raw,
        weekly_raw=weekly_raw,
    )

    w_oneline = _oneline_compress(weekly_view, weekly_raw) if weekly_view else "周线数据不足"
    d_oneline = _oneline_compress(daily_view, daily_raw)
    w_range = _range_phrase(weekly_view, weekly_raw) if weekly_view else "无成熟箱／无雏形｜未达 L3，暂不测算"
    d_range = _range_phrase(daily_view, daily_raw)
    w_inv = _invalidation_phrase(weekly_view, weekly_raw) if weekly_view else "暂无明确箱体失效价"
    d_inv = _invalidation_phrase(daily_view, daily_raw)

    lines: list[str] = [
        f"威科夫详析 — {name}（{code}）｜日线+周线" if code else f"威科夫详析 — {name}｜日线+周线",
        "",
        "📊 现况",
        f"  现价 {price_s}｜周线{w_bias} · {w_primary}｜日线{d_bias} · {d_primary}｜测算{meas_label}",
        "",
        "🔔 变化",
        f"  {change}",
        "",
        "🧭 中线（周线 · 入池看这里）",
        f"  一句话：{w_oneline}",
        f"  区间：{w_range}",
        f"  失效：{w_inv}",
        f"  入池：{pool_line}",
        "",
        "  灯",
    ]
    for lamp in _format_weekly_lights(weekly_view, weekly_raw):
        lines.append(f"  {lamp}")

    lines.extend(
        [
            "",
            "⚡ 短线（日线 · 盯触发看这里）",
            f"  一句话：{d_oneline}",
            f"  区间：{d_range}",
            f"  失效：{d_inv}",
            "",
            "  灯",
        ]
    )
    for lamp in _format_daily_lights(daily_view, daily_raw):
        lines.append(f"  {lamp}")

    lines.append("")
    lines.extend(
        _story_block(
            daily_view=daily_view,
            weekly_view=weekly_view,
            daily_raw=daily_raw,
            weekly_raw=weekly_raw,
            chain_plain=chain_plain,
            pool_line=pool_line,
        )
    )

    # 综述：只复述已上屏事实
    summary_bits = [
        f"日线{d_bias}",
        chain_plain,
        f"周线{w_bias}",
        pool_line,
    ]
    lines.extend(
        [
            "",
            "💬 综述",
            f"  {'｜'.join(summary_bits)}。本卡只读威科夫结构，不下单。",
        ]
    )

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
        # A-R3：rank 面板 phase_label 与 view/card 同源 sanitize（禁「Phase A失败」）
        phase = _panel_fail_copy(str(row.get("phase_label") or row.get("phase") or "—"))
        lines.append(f"{i}. {name}｜{chain}｜{phase}")
    lines.append("说明：排序仅看吸筹链进度；出手仍以 trader 分道与 decision_view 为准")
    return "\n".join(lines)


__all__ = [
    "build_light_snapshot_entry",
    "format_light_change",
    "render_wyckoff_card",
    "render_wyckoff_detail",
    "render_wyckoff_slim",
    "render_wyckoff_rank",
]
