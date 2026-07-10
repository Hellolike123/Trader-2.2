"""缠论纪律层：回踩区 / 中线看法 / 低置信 / 筹码资金否决。

只读输入 → 输出 allow_new_entry + cap + notes；禁止改写 fusion / stage / 价位数字。
开仓裁剪经 merge_discipline 与 mistery_gate 合并后生效（只收紧不放宽）。

规格：docs/chan-discipline-b-plan.md
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


def _in_midline_pullback_zone(
    current: float | None,
    pullback_low: float | None,
    pullback_high: float | None,
) -> bool | None:
    """现价是否在中线回踩区 [low, high]（含约 0.2% 容差）。

    返回 None 表示回踩区数据不足，调用方应跳过本规则（不因缺数误杀）。
    """
    if current is None or pullback_low is None or pullback_high is None:
        return None
    if current <= 0 or pullback_low <= 0 or pullback_high <= 0:
        return None
    lo, hi = pullback_low, pullback_high
    if hi < lo:
        lo, hi = hi, lo
    if abs(hi - lo) < 1e-9:
        return abs(current - lo) / lo <= 0.005
    return lo * 0.998 <= current <= hi * 1.002


def _is_mid_view_weak(mid_view: str) -> bool:
    return any(
        k in (mid_view or "")
        for k in ("暂缓", "偏空", "慎跟", "打架", "破坏", "战略减", "战略清")
    )


def _chan_low_confidence(raw: dict[str, Any]) -> tuple[bool, list[str]]:
    """缠侧低置信：mid_quality / structure_confidence（及显式 low_confidence）。

    fusion_disagreement / data_status 可与 gate 分摊；此处一并读取以便 notes 完整。
    """
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


def apply_chan_discipline(inputs: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """缠论相关纪律（纯函数，只读输入）。

    P0 规则：
      1. 中线回踩区外 → 不新开
      2. mid_view 偏空关键词 → 不新开
      3. mid_quality partial/insufficient、structure_confidence=low → 降档/否决
      4. chip_migration_warning / fund_flow_outflow_veto → 不新开
      5. 缺回踩数据 → 跳过回踩规则（不误杀）
      另：派发/衰退冲突 notes + 否决新开

    有持仓：只拦新开类，不强制改减仓/止损。
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
    allow_new = True
    entry_block_reason: str | None = None
    action_override: str | None = None

    # 默认 cap：参考 suggested / max，上限 50
    base_cap = suggested_pct if suggested_pct is not None else float(max_position_pct)
    try:
        cap = float(base_cap)
    except (TypeError, ValueError):
        cap = float(max_position_pct)
    cap = max(0.0, min(cap, float(max_position_pct), float(_POSITION_CAP_CEILING)))

    def _block_new(reason: str, rule: str, *, force_cap_zero: bool = True) -> None:
        nonlocal allow_new, entry_block_reason, action_override, cap
        allow_new = False
        if force_cap_zero:
            cap = 0.0
        if entry_block_reason is None:
            entry_block_reason = reason
        if reason not in notes:
            notes.append(reason)
        if rule not in rules_fired:
            rules_fired.append(rule)
        # 只拦新开：有仓不强制改减仓；无 override 时建议观望
        if action_override is None:
            action_override = "观望"

    def _downgrade_cap(reason: str, rule: str, factor: float = 0.5) -> None:
        nonlocal cap, action_override
        cap = round(max(0.0, cap * factor), 1)
        if reason not in notes:
            notes.append(reason)
        if rule not in rules_fired:
            rules_fired.append(rule)
        # 轻仓语义：不直接否决时可设观望倾向（若 cap 已 0 则否决）
        if cap <= 0 and action_override is None:
            action_override = "观望"

    # ── 1. 中线回踩区 ──
    in_pb = raw.get("in_midline_pullback")
    if in_pb is None:
        pb_lo = _to_float(raw.get("mid_pullback_low") or raw.get("pullback_low"))
        pb_hi = _to_float(raw.get("mid_pullback_high") or raw.get("pullback_high"))
        in_pb = _in_midline_pullback_zone(current, pb_lo, pb_hi)
    # in_pb is None → 缺数据跳过；False → 否决
    if in_pb is False:
        _block_new("现价不在中线回踩区，不新开", "pullback_out")

    # ── 2. mid_view 偏空 ──
    mid_view = str(raw.get("mid_view") or raw.get("midline_view") or "")
    mid_weak = _is_mid_view_weak(mid_view)
    if mid_weak:
        _block_new("中线看法偏空，短线买点不作主开仓", "mid_weak")

    # ── 3. 缠侧 / 融合低置信 ──
    low_conf, conf_reasons = _chan_low_confidence(raw)
    if low_conf:
        # partial / low structure → 否决或降档：P0 统一为观望+cap 砍半或 0
        # mid_quality / structure_confidence=low 视为缠侧证据不足 → 否决新开更稳
        mid_q = str(raw.get("mid_quality") or raw.get("mid_key_quality") or "").lower()
        conf = str(raw.get("structure_confidence") or raw.get("mid_structure_confidence") or "").lower()
        hard_chan_conf = mid_q in ("partial", "insufficient") or conf == "low"
        for cr in conf_reasons:
            if cr not in notes:
                notes.append(cr)
        if "conf" not in rules_fired:
            rules_fired.append("conf")
        if hard_chan_conf:
            _block_new("置信不足，轻仓或不动", "conf_block", force_cap_zero=True)
        else:
            # 仅 fusion/data 低置信：降档
            _downgrade_cap("置信不足，仓位降档", "conf_down", factor=0.5)
            if allow_new and cap < 5:
                _block_new("置信不足，轻仓或不动", "conf_block", force_cap_zero=True)

    # ── 4. 筹码搬家 / 资金流出 ──
    chip_warn = bool(raw.get("chip_migration_warning"))
    fund_veto = bool(raw.get("fund_flow_outflow_veto"))
    if chip_warn:
        _block_new("筹码搬家警告，不新开", "chip")
    if fund_veto:
        _block_new("主力连续流出，不新开", "fund")

    # ── 冲突：派发/衰退 + 可能偏多的缠信号 → notes + 否决新开 ──
    stage = _normalize_stage(str(raw.get("major_stage") or ""))
    if stage in ("派发", "衰退"):
        _block_new(f"阶段{stage}，不新开", "stage_risk")
        buy_pts = raw.get("buy_point_types") or []
        if isinstance(buy_pts, list) and buy_pts:
            conflict_note = f"阶段{stage}与买点信号冲突，以风控为准"
            if conflict_note not in notes:
                notes.append(conflict_note)
            if "stage_buy_conflict" not in rules_fired:
                rules_fired.append("stage_buy_conflict")
        elif mid_view and not mid_weak and any(
            k in mid_view for k in ("偏多", "未坏", "可跟踪")
        ):
            conflict_note = f"中线/缠论偏多，但阶段{stage} → 以风控为准，不新开"
            if conflict_note not in notes:
                notes.append(conflict_note)

    # 有持仓：不因本层强制改写「减仓」语义；action_override 仅作新开收紧
    # has_position 时 cap 仍可为 0（禁止加仓）
    _ = has_position  # 显式：减仓动作由 gate/merge 保留更严侧

    cap_i = int(round(max(0.0, min(cap, float(_POSITION_CAP_CEILING)))))
    if not allow_new:
        cap_i = 0

    return {
        "allow_new_entry": bool(allow_new),
        "allow_new_entry_mid": bool(allow_new),  # P0 合并
        "allow_new_entry_short": bool(allow_new),
        "entry_block_reason": entry_block_reason,
        "suggested_pct_cap": cap_i,
        "suggested_pct_cap_mid": None,
        "suggested_pct_cap_short": None,
        "action_override": action_override,
        "discipline_notes": notes,
        "rules_fired": rules_fired,
        "low_confidence": bool(low_conf),
        "in_midline_pullback": in_pb,
        "mid_view_weak": bool(mid_weak),
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
    # 其它未知动作：cap>0 才算允许
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
    # 同 rank：优先非开仓
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
            # gate notes 用中文分号
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
    """
    gate = dict(gate_out or {})
    chan = dict(chan_out or {})

    gate_allow = _gate_allows_new_entry(gate)
    chan_allow = bool(chan.get("allow_new_entry", True))
    allow_new = gate_allow and chan_allow

    gate_action = str(gate.get("action") or "观望")
    chan_override = chan.get("action_override")
    # chan 无 override 时仅用 gate；有 override 则取更严
    if chan_override:
        action = _stricter_action(gate_action, str(chan_override))
    else:
        action = gate_action

    # 禁止新开时：开仓类必须收紧为观望（不放宽减仓）
    if not allow_new and action in _OPEN_ACTIONS:
        action = "观望"

    # 再保险：gate 已是观望/不做时，不得被 chan 放宽（chan 不应给开仓 override，双保险）
    if gate_action in ("观望", "不做") and action in _OPEN_ACTIONS:
        action = gate_action if gate_action in ("观望", "不做") else "观望"
    if gate_action in ("减仓", "止损离场") and action in _OPEN_ACTIONS:
        action = gate_action

    try:
        gate_cap = float(gate.get("position_cap_pct") or 0)
    except (TypeError, ValueError):
        gate_cap = 0.0
    try:
        chan_cap = float(chan.get("suggested_pct_cap") if chan.get("suggested_pct_cap") is not None else _POSITION_CAP_CEILING)
    except (TypeError, ValueError):
        chan_cap = float(_POSITION_CAP_CEILING)

    ceiling = float(max_position_pct) if max_position_pct is not None else float(_POSITION_CAP_CEILING)
    cap = min(gate_cap, chan_cap, ceiling, float(_POSITION_CAP_CEILING))
    if not allow_new or action in ("观望", "不做", "减仓", "止损离场"):
        # 新开 cap：减仓类持仓语义仍 cap=0（新开）
        if action in ("观望", "不做", "减仓", "止损离场") or not allow_new:
            cap = min(cap, 0.0) if not allow_new else (
                0.0 if action in ("观望", "不做", "减仓", "止损离场") else cap
            )
    if not allow_new:
        cap = 0.0
    cap = round(max(0.0, min(cap, float(_POSITION_CAP_CEILING))), 1)

    notes_list = _unique_notes(gate.get("notes"), chan.get("discipline_notes"))
    entry_block = chan.get("entry_block_reason")
    if not entry_block and not allow_new and notes_list:
        entry_block = notes_list[0]

    hard_block = gate.get("hard_block") or "none"
    invalidation = str(gate.get("invalidation") or "")
    style = str(gate.get("style") or "")

    return {
        "allow_new_entry": bool(allow_new),
        "action": action,
        "suggested_pct_cap": int(cap) if cap == int(cap) else cap,
        "position_cap_pct": cap,  # 兼容 gate 字段名
        "entry_block_reason": entry_block,
        "discipline_notes": notes_list,
        "notes": "；".join(notes_list) if notes_list else "",
        "hard_block": hard_block,
        "invalidation": invalidation,
        "style": style,
        "low_confidence": bool(gate.get("low_confidence") or chan.get("low_confidence")),
        "in_midline_pullback": chan.get("in_midline_pullback", gate.get("in_midline_pullback")),
        "mid_view_weak": bool(chan.get("mid_view_weak") or gate.get("mid_view_weak")),
        "rules_fired": list(chan.get("rules_fired") or []),
    }
