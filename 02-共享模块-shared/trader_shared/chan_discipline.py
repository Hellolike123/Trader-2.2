"""缠论纪律层：回踩 / 中线看法 / 买点阶梯 / 盘整 / 分闸 / 生命线 / 周框。

只读输入 → 输出 allow_new_entry + cap + notes；禁止改写 fusion / stage / 价位数字。
开仓裁剪经 merge_discipline 与 mistery_gate 合并后生效（只收紧不放宽）。

规格：docs/chan-discipline-b-plan.md · docs/chan-ops-remaining-backlog-plan.md
"""
from __future__ import annotations

from typing import Any

# 开仓类动作（merge 时视为「松」侧，可被收紧为观望）
_OPEN_ACTIONS = frozenset({"轻仓试错", "回踩低吸", "持有"})

# rank 从松到严；更大 = 更严
_ACTION_RANK: dict[str, int] = {
    "持有": 0,
    "回踩低吸": 1,
    "轻仓试错": 2,
    "观望": 3,
    "减仓": 4,
    "止损离场": 5,
    "不做": 5,
}

_POSITION_CAP_CEILING = 50
_BUY1_CAP = 5
_BUY2_CAP = 10
_PANZHENG_CAP = 10


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _in_band(
    current: float | None,
    lo: float | None,
    hi: float | None,
    *,
    tol: float = 0.002,
) -> bool | None:
    """现价是否在 [lo, hi]（含相对容差）。None = 数据不足跳过。"""
    if current is None or lo is None or hi is None:
        return None
    if current <= 0 or lo <= 0 or hi <= 0:
        return None
    a, b = lo, hi
    if b < a:
        a, b = b, a
    if abs(b - a) < 1e-9:
        return abs(current - a) / a <= 0.005
    return a * (1.0 - tol) <= current <= b * (1.0 + tol)


def _in_midline_pullback_zone(
    current: float | None,
    pullback_low: float | None,
    pullback_high: float | None,
) -> bool | None:
    """现价是否在中线回踩区 [low, high]（含约 0.2% 容差）。"""
    return _in_band(current, pullback_low, pullback_high, tol=0.002)


def _is_mid_view_weak(mid_view: str) -> bool:
    return any(
        k in (mid_view or "")
        for k in ("暂缓", "偏空", "慎跟", "打架", "破坏", "战略减", "战略清")
    )


def _is_pan_zheng(structure_type: Any) -> bool:
    return "盘整" in str(structure_type or "")


def _last_valid_zone(zones: list[Any] | None) -> dict[str, Any] | None:
    for z in reversed(zones or []):
        if not isinstance(z, dict):
            continue
        if z.get("valid") is False:
            continue
        top = _to_float(z.get("zh_top"))
        bottom = _to_float(z.get("zh_bottom"))
        if top is None or bottom is None:
            continue
        if top < bottom:
            top, bottom = bottom, top
        if top <= 0 or bottom <= 0:
            continue
        # valid 缺省为 True（只要有价）
        if z.get("valid") is None or z.get("valid"):
            return {"zh_top": top, "zh_bottom": bottom, "zh_center": _to_float(z.get("zh_center"))}
    return None


def compute_pivot_position(
    current: float | None,
    zones: list[Any] | None = None,
    *,
    zh_top: float | None = None,
    zh_bottom: float | None = None,
) -> str:
    """现价相对最近有效中枢的位置。

    返回：中枢内 | 中枢上(回踩中) | 中枢下(反抽中) | 中枢外 | 未知
    """
    cur = _to_float(current)
    top = _to_float(zh_top)
    bottom = _to_float(zh_bottom)
    if top is None or bottom is None:
        z = _last_valid_zone(zones)
        if z is None:
            return "未知"
        top, bottom = z["zh_top"], z["zh_bottom"]
    if cur is None or cur <= 0 or top is None or bottom is None:
        return "未知"
    if top < bottom:
        top, bottom = bottom, top
    if top <= bottom:
        return "未知"
    if bottom <= cur <= top:
        return "中枢内"
    # 距中枢过远（> 区高 ×2 或 > 中枢中心 15%）标 中枢外
    height = max(top - bottom, 1e-9)
    center = (top + bottom) / 2.0
    if cur > top:
        dist = cur - top
        if dist > max(2.0 * height, center * 0.15):
            return "中枢外"
        return "中枢上(回踩中)"
    # cur < bottom
    dist = bottom - cur
    if dist > max(2.0 * height, center * 0.15):
        return "中枢外"
    return "中枢下(反抽中)"


def compute_weekly_frame(
    current: float | None = None,
    life_line: float | None = None,
    *,
    zh_bottom: float | None = None,
    zones: list[Any] | None = None,
    weekly_bars: list[Any] | None = None,
) -> str | None:
    """周框状态：完好 | 紧张 | 破坏；数据不足 → None。

    破坏：current < life_line*0.995 或明确破有效中枢下沿。
    紧张：接近 life 2% 内（上方侧）。
    否则完好。
    """
    del weekly_bars  # 预留；当前用 life/中枢即可测
    cur = _to_float(current)
    life = _to_float(life_line)
    zb = _to_float(zh_bottom)
    if zb is None:
        z = _last_valid_zone(zones)
        if z is not None:
            zb = z["zh_bottom"]
    if cur is None or cur <= 0:
        return None
    if life is None and zb is None:
        return None

    if life is not None and life > 0 and cur < life * 0.995:
        return "破坏"
    if zb is not None and zb > 0 and cur < zb:
        return "破坏"
    if life is not None and life > 0:
        # 紧张：现价在生命线附近 2% 内（含略下方未达破坏阈值）
        if abs(cur - life) / life <= 0.02:
            return "紧张"
        if cur <= life * 1.02:
            return "紧张"
    return "完好"


def _chan_low_confidence(raw: dict[str, Any]) -> tuple[bool, list[str]]:
    """缠侧低置信：mid_quality / structure_confidence（及显式 low_confidence）。"""
    reasons: list[str] = []
    mid_quality = str(raw.get("mid_quality") or raw.get("mid_key_quality") or "").lower()
    if mid_quality in ("partial", "insufficient"):
        reasons.append(f"中线价源{mid_quality}")

    conf = str(raw.get("structure_confidence") or raw.get("mid_structure_confidence") or "").lower()
    if conf == "low":
        reasons.append("中线缠论段偏少/低置信")

    if str(raw.get("data_status") or "").lower() == "partial":
        reasons.append("数据partial")

    try:
        dis = raw.get("fusion_disagreement")
        if dis is not None and int(dis) >= 1:
            reasons.append("日线多空分歧")
    except (TypeError, ValueError):
        pass

    try:
        fc = raw.get("fusion_confidence")
        if fc is not None and float(fc) < 0.45:
            reasons.append("融合置信偏低")
    except (TypeError, ValueError):
        pass

    if raw.get("low_confidence") is True:
        reasons.append("低置信标记")

    return (len(reasons) > 0, reasons)


def _normalize_stage(major_stage: str) -> str:
    s = str(major_stage or "").strip()
    if not s:
        return ""
    for base in ("蓄势", "主升", "派发", "衰退"):
        if s.startswith(base) or base in s:
            return base
    return s


# 开仓 5 项清单（C1 展示：不全绿只写缺项；全绿才可试探）
_CHECKLIST_KEYS = (
    ("mid_ok", "中线趋势"),
    ("in_pullback", "回踩到位"),
    ("short_trigger", "买点信号"),
    ("conf_ok", "信号一致"),
    ("fund_ok", "筹码资金稳"),
)


def build_entry_checklist(
    *,
    stage: str = "",
    mid_view_weak: bool = False,
    in_pullback: bool | None = None,
    buy_point_types: list[str] | None = None,
    low_confidence: bool = False,
    chip_warning: bool = False,
    fund_veto: bool = False,
    weekly_frame: str | None = None,
    broke_life: bool = False,
) -> dict[str, Any]:
    """五项开仓清单布尔；all_green 全绿才允许试探买话术。"""
    st = _normalize_stage(stage)
    mid_ok = st not in ("派发", "衰退") and not mid_view_weak
    if str(weekly_frame or "") == "破坏" or broke_life:
        mid_ok = False

    if in_pullback is True:
        pb_ok: bool | None = True
    elif in_pullback is False:
        pb_ok = False
    else:
        pb_ok = None  # 无回踩数据：不算绿

    types = buy_point_types or []
    short_trigger = any(
        any(k in t for k in ("一类买", "二类买", "三类买", "一买", "二买", "三买"))
        for t in types
    )

    conf_ok = not low_confidence
    fund_ok = not (chip_warning or fund_veto)

    items = {
        "mid_ok": mid_ok,
        "in_pullback": pb_ok is True,  # None → 展示用 false for all_green
        "short_trigger": short_trigger,
        "conf_ok": conf_ok,
        "fund_ok": fund_ok,
    }
    # 回踩无数据：清单 in_pullback 记 None 供展示
    raw_flags = {
        "mid_ok": mid_ok,
        "in_pullback": pb_ok,  # bool | None
        "short_trigger": short_trigger,
        "conf_ok": conf_ok,
        "fund_ok": fund_ok,
    }

    missing: list[str] = []
    for key, label in _CHECKLIST_KEYS:
        v = raw_flags[key]
        if v is True:
            continue
        if v is False or v is None:
            missing.append(label)

    all_green = all(raw_flags[k] is True for k, _ in _CHECKLIST_KEYS)
    return {
        "items": items,
        "flags": raw_flags,
        "missing_labels": missing,
        "all_green": bool(all_green),
        "entry_line": format_entry_line_c1(all_green=all_green, missing=missing),
    }


def format_entry_line_c1(
    *,
    all_green: bool,
    missing: list[str] | None = None,
) -> str:
    """C1：新开：否（缺：…）｜新开：可试探（清单全绿）。"""
    if all_green:
        return "新开：可试探（清单全绿）"
    miss = missing or []
    if miss:
        return f"新开：否（缺：{'｜'.join(miss)}）"
    return "新开：否"


def _normalize_buy_types(raw_types: Any) -> list[str]:
    out: list[str] = []
    if not raw_types:
        return out
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    if not isinstance(raw_types, list):
        return out
    for t in raw_types:
        if isinstance(t, dict):
            s = str(t.get("type") or "").strip()
        else:
            s = str(t or "").strip()
        if s:
            out.append(s)
    return out


def _buy_point_cap(
    buy_types: list[str],
    *,
    mid_view_weak: bool,
    max_position_pct: float,
) -> tuple[int | None, str | None]:
    """R1 买点阶梯 cap。有一类→最严试仓；仅三类+中线非弱→可到阶段上限。

    返回 (cap_or_None表示不强制, rule_tag)。
    """
    if not buy_types:
        return None, None
    joined = " ".join(buy_types)
    has1 = any("一类" in t for t in buy_types) or "一类" in joined
    has2 = any("二类" in t for t in buy_types) or "二类" in joined
    has3 = any("三类" in t for t in buy_types) or "三类" in joined
    if has1:
        return _BUY1_CAP, "buy1_cap"
    if has2:
        return _BUY2_CAP, "buy2_cap"
    if has3:
        if mid_view_weak:
            # 中线弱时三类不作主仓档
            return _BUY2_CAP, "buy3_mid_weak_cap"
        # 可到阶段上限（不额外收紧，仅标注）
        stage_cap = int(round(min(float(max_position_pct), float(_POSITION_CAP_CEILING))))
        return stage_cap, "buy3_main_cap"
    return None, None


def apply_chan_discipline(inputs: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """缠论相关纪律（纯函数，只读输入）。

    P0：回踩区外 / mid_view 弱 / 低置信 / 筹码资金 / 派发衰退。
    P1+：买点阶梯(R1) / 盘整禁重仓(R2) / low_zone 短闸(R3) / 中短分闸(R4) /
         破生命线中枢(R8) / weekly_frame 破坏(R9)。

    有持仓：只拦新开类；破位时可倾向减仓。
    """
    raw = dict(inputs or {})
    raw.update(kwargs)

    current = _to_float(raw.get("current"))
    has_position = bool(raw.get("has_position", False))
    suggested_pct = _to_float(raw.get("suggested_pct"))
    max_position_pct = _to_float(raw.get("max_position_pct"))
    if max_position_pct is None:
        max_position_pct = float(_POSITION_CAP_CEILING)

    notes: list[str] = []
    rules_fired: list[str] = []
    entry_block_reason: str | None = None
    action_override: str | None = None

    # 分闸
    allow_mid = True
    allow_short = True

    base_cap = suggested_pct if suggested_pct is not None else float(max_position_pct)
    try:
        base = float(base_cap)
    except (TypeError, ValueError):
        base = float(max_position_pct)
    base = max(0.0, min(base, float(max_position_pct), float(_POSITION_CAP_CEILING)))
    cap_mid = base
    cap_short = base

    def _note(reason: str, rule: str) -> None:
        if reason not in notes:
            notes.append(reason)
        if rule not in rules_fired:
            rules_fired.append(rule)

    def _block_mid(reason: str, rule: str, *, force_cap_zero: bool = True) -> None:
        nonlocal allow_mid, entry_block_reason, action_override, cap_mid
        allow_mid = False
        if force_cap_zero:
            cap_mid = 0.0
        if entry_block_reason is None:
            entry_block_reason = reason
        _note(reason, rule)
        if action_override is None:
            action_override = "观望"

    def _block_short(reason: str, rule: str, *, force_cap_zero: bool = True) -> None:
        nonlocal allow_short, entry_block_reason, action_override, cap_short
        allow_short = False
        if force_cap_zero:
            cap_short = 0.0
        if entry_block_reason is None:
            entry_block_reason = reason
        _note(reason, rule)
        if action_override is None:
            action_override = "观望"

    def _block_both(reason: str, rule: str, *, force_cap_zero: bool = True) -> None:
        _block_mid(reason, rule, force_cap_zero=force_cap_zero)
        _block_short(reason, rule, force_cap_zero=force_cap_zero)

    def _tighten_cap(which: str, new_cap: float, reason: str, rule: str) -> None:
        nonlocal cap_mid, cap_short, action_override
        new_cap = max(0.0, float(new_cap))
        if which in ("mid", "both"):
            cap_mid = min(cap_mid, new_cap)
        if which in ("short", "both"):
            cap_short = min(cap_short, new_cap)
        _note(reason, rule)

    # ── mid: 中线回踩区 ──
    in_pb = raw.get("in_midline_pullback")
    if in_pb is None:
        pb_lo = _to_float(raw.get("mid_pullback_low") or raw.get("pullback_low"))
        pb_hi = _to_float(raw.get("mid_pullback_high") or raw.get("pullback_high"))
        in_pb = _in_midline_pullback_zone(current, pb_lo, pb_hi)
    if in_pb is False:
        _block_mid("现价不在中线回踩区，不新开", "pullback_out")

    # ── mid: mid_view 偏空 ──
    mid_view = str(raw.get("mid_view") or raw.get("midline_view") or "")
    mid_weak = _is_mid_view_weak(mid_view)
    if mid_weak:
        _block_mid("中线看法偏空，短线买点不作主开仓", "mid_weak")

    # ── mid: 缠侧硬置信；fusion/data 降档影响 short 侧 ──
    low_conf, conf_reasons = _chan_low_confidence(raw)
    if low_conf:
        mid_q = str(raw.get("mid_quality") or raw.get("mid_key_quality") or "").lower()
        conf = str(raw.get("structure_confidence") or raw.get("mid_structure_confidence") or "").lower()
        hard_chan_conf = mid_q in ("partial", "insufficient") or conf == "low"
        for cr in conf_reasons:
            if cr not in notes:
                notes.append(cr)
        if "conf" not in rules_fired:
            rules_fired.append("conf")
        if hard_chan_conf:
            _block_mid("置信不足", "conf_block", force_cap_zero=True)
            # 中线证据不足也否决短线主开仓（总闸 AND）
            _block_short("置信不足", "conf_block", force_cap_zero=True)
        else:
            # 仅 fusion/data 低置信：中短均降档
            _tighten_cap("both", cap_mid * 0.5, "置信不足，仓位降档", "conf_down")
            if min(cap_mid, cap_short) < 5:
                _block_both("置信不足", "conf_block", force_cap_zero=True)

    # ── 筹码 / 资金：双闸 ──
    if bool(raw.get("chip_migration_warning")):
        _block_both("筹码搬家警告，不新开", "chip")
    if bool(raw.get("fund_flow_outflow_veto")):
        _block_both("主力连续流出，不新开", "fund")

    # ── 派发/衰退：双闸 ──
    stage = _normalize_stage(str(raw.get("major_stage") or ""))
    buy_pts = _normalize_buy_types(raw.get("buy_point_types") or raw.get("buy_points"))
    if stage in ("派发", "衰退"):
        _block_both(f"阶段{stage}，不新开", "stage_risk")
        if buy_pts:
            conflict_note = f"阶段{stage}与买点信号冲突，以风控为准"
            if conflict_note not in notes:
                notes.append(conflict_note)
            if "stage_buy_conflict" not in rules_fired:
                rules_fired.append("stage_buy_conflict")
        elif mid_view and not mid_weak and any(k in mid_view for k in ("偏多", "未坏", "可跟踪")):
            conflict_note = f"中线/缠论偏多，但阶段{stage} → 以风控为准，不新开"
            if conflict_note not in notes:
                notes.append(conflict_note)

    # ── R2 盘整禁趋势重仓 ──
    st_daily = str(raw.get("structure_type_daily") or raw.get("structure_type") or "")
    st_weekly = str(raw.get("structure_type_weekly") or "")
    pan_daily = _is_pan_zheng(st_daily)
    pan_weekly = _is_pan_zheng(st_weekly)
    if pan_daily or pan_weekly:
        which = "both" if (pan_daily and pan_weekly) else ("short" if pan_daily else "mid")
        _tighten_cap(which, float(_PANZHENG_CAP), "盘整不做趋势重仓", "pan_zheng_cap")
        # 开仓类最多轻仓试错；不直接否决新开
        if action_override is None or action_override in ("持有", "回踩低吸"):
            action_override = "轻仓试错"
        if which == "both":
            # 两侧都盘整时更稳：倾向观望若 cap 已很低
            if min(cap_mid, cap_short) <= 0:
                action_override = "观望"

    # ── R1 买点阶梯（短线 cap；与总 cap min）──
    bp_cap, bp_rule = _buy_point_cap(
        buy_pts, mid_view_weak=mid_weak, max_position_pct=max_position_pct
    )
    if bp_cap is not None and bp_rule:
        if bp_rule in ("buy1_cap", "buy2_cap", "buy3_mid_weak_cap"):
            _tighten_cap("short", float(bp_cap), f"买点阶梯{bp_rule} cap≤{bp_cap}", bp_rule)
        elif bp_rule == "buy3_main_cap":
            # 仅三类：可到阶段上限，不额外收紧；记录规则
            if bp_rule not in rules_fired:
                rules_fired.append(bp_rule)
            note = f"三类买+中线非弱，仓位可到阶段上限{int(bp_cap)}%"
            if note not in notes:
                notes.append(note)

    # ── R3 短线 low_zone 门禁 ──
    lz_lo = _to_float(raw.get("low_zone_lower"))
    lz_hi = _to_float(raw.get("low_zone_upper"))
    in_lz = _in_band(current, lz_lo, lz_hi, tol=0.002)
    if in_lz is False:
        _block_short("现价不在短线低吸区，不新开", "low_zone_out")

    # ── R8 破生命线 / 中枢下沿 ──
    life_line = _to_float(raw.get("life_line") or raw.get("mid_life_line"))
    zh_bottom = _to_float(raw.get("zh_bottom") or raw.get("zone_zh_bottom"))
    zones_in = raw.get("zones") or raw.get("zones_weekly") or raw.get("mid_zones")
    if zh_bottom is None:
        zlast = _last_valid_zone(zones_in if isinstance(zones_in, list) else None)
        if zlast is not None:
            zh_bottom = zlast["zh_bottom"]
    broke_life = (
        current is not None
        and life_line is not None
        and life_line > 0
        and current < life_line
    )
    broke_zh = (
        current is not None
        and zh_bottom is not None
        and zh_bottom > 0
        and current < zh_bottom
    )
    if broke_life:
        _block_mid("跌破中线生命线，不新开", "life_break")
        _block_short("跌破中线生命线，不新开", "life_break")
        if has_position:
            action_override = "减仓"
            _note("破生命线，持仓倾向减仓", "life_break_pos")
        else:
            if action_override is None or action_override in _OPEN_ACTIONS:
                action_override = "观望"
    if broke_zh:
        _block_mid("跌破中枢下沿，不新开", "zh_break")
        _block_short("跌破中枢下沿，不新开", "zh_break")
        if has_position:
            action_override = _stricter_action(action_override, "减仓")
            _note("破中枢下沿，持仓倾向减仓", "zh_break_pos")
        else:
            if action_override is None or action_override in _OPEN_ACTIONS:
                action_override = "观望"

    # ── R9 weekly_frame ──
    weekly_frame = raw.get("weekly_frame")
    if weekly_frame is None and (life_line is not None or zh_bottom is not None):
        weekly_frame = compute_weekly_frame(
            current, life_line, zh_bottom=zh_bottom, zones=zones_in if isinstance(zones_in, list) else None
        )
    if str(weekly_frame or "") == "破坏":
        _block_mid("中线框破坏，不新开", "weekly_frame_break")
        _block_short("中线框破坏，不新开", "weekly_frame_break")
        if has_position:
            action_override = _stricter_action(action_override, "减仓")
        elif action_override is None or action_override in _OPEN_ACTIONS:
            action_override = "观望"

    # ── 汇总分闸 ──
    allow_new = bool(allow_mid and allow_short)
    cap = min(cap_mid, cap_short)
    if not allow_new:
        cap = 0.0
        if action_override is None:
            action_override = "观望"
        elif action_override in _OPEN_ACTIONS and not has_position:
            action_override = "观望"
        # 盘整允许轻仓时若仍 allow=True 才保留轻仓；此处已禁止新开
        if not allow_new and action_override in _OPEN_ACTIONS and not (has_position and action_override == "减仓"):
            if action_override != "减仓":
                action_override = "观望"

    # 盘整且仍允许新开：开仓类最多轻仓试错，cap≤10
    if allow_new and (pan_daily or pan_weekly):
        cap = min(cap, float(_PANZHENG_CAP))
        cap_mid = min(cap_mid, float(_PANZHENG_CAP)) if pan_weekly else cap_mid
        cap_short = min(cap_short, float(_PANZHENG_CAP)) if pan_daily else cap_short
        if action_override in (None, "持有", "回踩低吸"):
            action_override = "轻仓试错"
        _note("盘整不做趋势重仓", "pan_zheng_cap")

    cap_i = int(round(max(0.0, min(cap, float(_POSITION_CAP_CEILING)))))
    cap_mid_i = int(round(max(0.0, min(cap_mid, float(_POSITION_CAP_CEILING)))))
    cap_short_i = int(round(max(0.0, min(cap_short, float(_POSITION_CAP_CEILING)))))
    if not allow_mid:
        cap_mid_i = 0
    if not allow_short:
        cap_short_i = 0
    if not allow_new:
        cap_i = 0

    # 位置字段（展示用，纪律层可附带）
    pivot_pos = raw.get("pivot_position")
    if pivot_pos is None:
        pivot_pos = compute_pivot_position(
            current,
            zones_in if isinstance(zones_in, list) else None,
            zh_top=_to_float(raw.get("zh_top")),
            zh_bottom=zh_bottom,
        )

    # C1 开仓五清单（展示）；全绿才渲染「可试探」。门禁仍由上方规则负责，此处不重复误杀「缺数跳过」。
    entry_checklist = build_entry_checklist(
        stage=stage,
        mid_view_weak=bool(mid_weak),
        in_pullback=in_pb,
        buy_point_types=buy_pts,
        low_confidence=bool(low_conf),
        chip_warning=bool(raw.get("chip_migration_warning")),
        fund_veto=bool(raw.get("fund_flow_outflow_veto")),
        weekly_frame=str(weekly_frame) if weekly_frame is not None else None,
        broke_life=bool(broke_life),
    )
    # 清单未全绿时：禁止开仓类 action_override（有仓减仓除外）；不单独因缺买点改 mid/short 分闸
    if not entry_checklist.get("all_green"):
        if action_override in _OPEN_ACTIONS and not (has_position and action_override == "减仓"):
            action_override = "观望"
        if "checklist" not in rules_fired:
            rules_fired.append("checklist")

    return {
        "allow_new_entry": bool(allow_new),
        "allow_new_entry_mid": bool(allow_mid),
        "allow_new_entry_short": bool(allow_short),
        "entry_block_reason": entry_block_reason,
        "suggested_pct_cap": cap_i,
        "suggested_pct_cap_mid": cap_mid_i,
        "suggested_pct_cap_short": cap_short_i,
        "action_override": action_override,
        "discipline_notes": notes,
        "rules_fired": rules_fired,
        "low_confidence": bool(low_conf),
        "in_midline_pullback": in_pb,
        "in_low_zone": in_lz,
        "mid_view_weak": bool(mid_weak),
        "weekly_frame": weekly_frame,
        "pivot_position": pivot_pos,
        "broke_life_line": bool(broke_life),
        "broke_zh_bottom": bool(broke_zh),
        "entry_checklist": entry_checklist,
        "entry_line": entry_checklist.get("entry_line"),
    }


def _gate_allows_new_entry(gate_out: dict[str, Any]) -> bool:
    """gate 侧是否允许新开：开仓类动作且 cap>0。"""
    action = str(gate_out.get("action") or "观望")
    try:
        cap = float(gate_out.get("position_cap_pct") or 0)
    except (TypeError, ValueError):
        cap = 0.0
    if action in ("观望", "不做", "减仓", "止损离场"):
        return False
    if action in _OPEN_ACTIONS and cap > 0:
        return True
    return cap > 0 and action not in ("",)


def _stricter_action(a: str | None, b: str | None) -> str:
    """取更严动作；并列优先非开仓。"""
    aa = str(a or "").strip() or "观望"
    bb = str(b or "").strip() or "观望"
    ra = _ACTION_RANK.get(aa, 3)
    rb = _ACTION_RANK.get(bb, 3)
    if ra > rb:
        return aa
    if rb > ra:
        return bb
    if aa in _OPEN_ACTIONS and bb not in _OPEN_ACTIONS:
        return bb
    if bb in _OPEN_ACTIONS and aa not in _OPEN_ACTIONS:
        return aa
    return aa


def _unique_notes(*parts: Any) -> list[str]:
    """notes 并集去重保序。支持 str（；分隔）或 list。"""
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        items: list[str] = []
        if part is None:
            continue
        if isinstance(part, list):
            items = [str(x).strip() for x in part if str(x).strip()]
        else:
            s = str(part).strip()
            if not s:
                continue
            if "；" in s:
                items = [x.strip() for x in s.split("；") if x.strip()]
            elif ";" in s:
                items = [x.strip() for x in s.split(";") if x.strip()]
            else:
                items = [s]
        for it in items:
            if it not in seen:
                seen.add(it)
                out.append(it)
    return out


def merge_discipline(
    gate_out: dict[str, Any] | None,
    chan_out: dict[str, Any] | None,
    *,
    max_position_pct: float | int | None = None,
) -> dict[str, Any]:
    """合并 gate 与 chan_discipline：只收紧不放宽。

    - allow_new_entry：两者更严（False 赢）
    - action：只收紧（开仓 < 观望 < 减仓 < 止损/不做）
    - suggested_pct_cap：min(gate.cap, chan.cap, max_position_pct or 50)
    - notes：并集去重
    - mid/short 分闸透传（总闸 = mid and short and gate）
    """
    gate = dict(gate_out or {})
    chan = dict(chan_out or {})

    gate_allow = _gate_allows_new_entry(gate)
    chan_allow = bool(chan.get("allow_new_entry", True))
    chan_mid = bool(chan.get("allow_new_entry_mid", chan_allow))
    chan_short = bool(chan.get("allow_new_entry_short", chan_allow))
    allow_new = gate_allow and chan_allow and chan_mid and chan_short

    gate_action = str(gate.get("action") or "观望")
    chan_override = chan.get("action_override")
    if chan_override:
        action = _stricter_action(gate_action, str(chan_override))
    else:
        action = gate_action

    if not allow_new and action in _OPEN_ACTIONS:
        action = "观望"

    # C1：清单未全绿不得保留开仓类动作（试探买话术）
    _cl = chan.get("entry_checklist") if isinstance(chan.get("entry_checklist"), dict) else {}
    if _cl and not _cl.get("all_green") and action in _OPEN_ACTIONS:
        action = "观望"
        allow_new = False
        cap = 0.0

    if gate_action in ("观望", "不做") and action in _OPEN_ACTIONS:
        action = gate_action if gate_action in ("观望", "不做") else "观望"
    if gate_action in ("减仓", "止损离场") and action in _OPEN_ACTIONS:
        action = gate_action

    try:
        gate_cap = float(gate.get("position_cap_pct") or 0)
    except (TypeError, ValueError):
        gate_cap = 0.0
    try:
        chan_cap = float(
            chan.get("suggested_pct_cap")
            if chan.get("suggested_pct_cap") is not None
            else _POSITION_CAP_CEILING
        )
    except (TypeError, ValueError):
        chan_cap = float(_POSITION_CAP_CEILING)

    ceiling = float(max_position_pct) if max_position_pct is not None else float(_POSITION_CAP_CEILING)
    cap = min(gate_cap, chan_cap, ceiling, float(_POSITION_CAP_CEILING))
    if not allow_new:
        cap = 0.0
    elif action in ("观望", "不做", "减仓", "止损离场"):
        cap = 0.0
    cap = round(max(0.0, min(cap, float(_POSITION_CAP_CEILING))), 1)

    # 分 cap 透传：保留中/短各自计算值（总 cap 已是 min）；仅封顶 50
    def _side_cap(key: str) -> int | None:
        v = chan.get(key)
        if v is None:
            return None
        try:
            return int(round(max(0.0, min(float(v), float(_POSITION_CAP_CEILING)))))
        except (TypeError, ValueError):
            return None

    notes_list = _unique_notes(gate.get("notes"), chan.get("discipline_notes"))
    entry_block = chan.get("entry_block_reason")
    if not entry_block and not allow_new and notes_list:
        entry_block = notes_list[0]

    hard_block = gate.get("hard_block") or "none"
    invalidation = str(gate.get("invalidation") or "")
    style = str(gate.get("style") or "")

    # C1 清单：透传；gate 否决时不能显示全绿可试探
    entry_checklist = dict(chan.get("entry_checklist") or {})
    if entry_checklist:
        if not allow_new and entry_checklist.get("all_green"):
            entry_checklist["all_green"] = False
            miss = list(entry_checklist.get("missing_labels") or [])
            if hard_block and hard_block != "none" and "门控否决" not in miss:
                miss.append("门控否决")
            elif "门控否决" not in miss and not gate_allow:
                miss.append("门控否决")
            entry_checklist["missing_labels"] = miss
            entry_checklist["entry_line"] = format_entry_line_c1(
                all_green=False, missing=miss
            )
        elif not entry_checklist.get("entry_line"):
            entry_checklist["entry_line"] = format_entry_line_c1(
                all_green=bool(entry_checklist.get("all_green")),
                missing=list(entry_checklist.get("missing_labels") or []),
            )
    entry_line = str(
        (entry_checklist or {}).get("entry_line")
        or chan.get("entry_line")
        or ""
    )

    return {
        "allow_new_entry": bool(allow_new),
        "allow_new_entry_mid": bool(gate_allow and chan_mid),
        "allow_new_entry_short": bool(gate_allow and chan_short),
        "action": action,
        "suggested_pct_cap": int(cap) if cap == int(cap) else cap,
        "suggested_pct_cap_mid": _side_cap("suggested_pct_cap_mid"),
        "suggested_pct_cap_short": _side_cap("suggested_pct_cap_short"),
        "position_cap_pct": cap,
        "entry_block_reason": entry_block,
        "discipline_notes": notes_list,
        "notes": "；".join(notes_list) if notes_list else "",
        "hard_block": hard_block,
        "invalidation": invalidation,
        "style": style,
        "low_confidence": bool(gate.get("low_confidence") or chan.get("low_confidence")),
        "in_midline_pullback": chan.get("in_midline_pullback", gate.get("in_midline_pullback")),
        "in_low_zone": chan.get("in_low_zone"),
        "mid_view_weak": bool(chan.get("mid_view_weak") or gate.get("mid_view_weak")),
        "rules_fired": list(chan.get("rules_fired") or []),
        "weekly_frame": chan.get("weekly_frame"),
        "pivot_position": chan.get("pivot_position"),
        "broke_life_line": bool(chan.get("broke_life_line")),
        "broke_zh_bottom": bool(chan.get("broke_zh_bottom")),
        "entry_checklist": entry_checklist,
        "entry_line": entry_line,
    }


def needs_same_level_tag(
    chan_obj: Any = None,
    *,
    text: str = "",
    buy_point_types: list[str] | None = None,
) -> bool:
    """是否应在缠论文案后标注（同级）：有买卖点或背驰。"""
    t = str(text or "")
    if any(k in t for k in ("一类", "二类", "三类", "背驰", "买点", "卖点")):
        return True
    bps = buy_point_types or []
    if any(str(x) for x in bps):
        return True
    chan: dict[str, Any] = {}
    if isinstance(chan_obj, dict):
        if "chanlun" in chan_obj and isinstance(chan_obj.get("chanlun"), dict):
            chan = chan_obj.get("chanlun") or {}
        else:
            chan = chan_obj
    buys = chan.get("buy_points") if isinstance(chan.get("buy_points"), list) else []
    sells = chan.get("sell_points") if isinstance(chan.get("sell_points"), list) else []
    if buys or sells:
        return True
    div = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    if div.get("top_divergence") or div.get("bottom_divergence"):
        return True
    return False


def append_same_level_tag(text: str, need: bool) -> str:
    """在缠论行末追加（同级）。"""
    s = str(text or "")
    if not need or not s:
        return s
    if "（同级）" in s or "(同级)" in s:
        return s
    return s + "（同级）"
