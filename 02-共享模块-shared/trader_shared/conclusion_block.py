"""短中线结论块：中线看法 / 短线看法 / 出手 / 原因 / 本周 / 冲突说明。"""
from __future__ import annotations

from typing import Any

from trader_shared.mistery_gate import gate_action_to_execution_text


def _norm_stage(major_stage: str) -> str:
    s = str(major_stage or "").strip()
    for base in ("蓄势", "主升", "派发", "衰退"):
        if s.startswith(base) or base in s:
            return base
    return s


def _midline_view(major_stage: str, regime: str, weekly_frame: str | None = None) -> str:
    """中线看法：故事在不在（阶段驱动，非日线 fusion 单独清仓）。"""
    stage = _norm_stage(major_stage)
    full = str(major_stage or "")
    regime = str(regime or "")

    # P1: weekly_frame 破坏 → 战略减/清倾向（P0 仅文案预留）
    if weekly_frame == "破坏":
        return "中线框破坏，战略减仓/清仓倾向"

    if stage == "衰退":
        return "故事结束倾向，中线不做多"
    if stage == "派发":
        return "派发期，中线不加、只减"
    if stage == "主升":
        return "主升叙事仍在，可跟踪持有"
    if stage == "蓄势":
        if "偏强" in full:
            return "可跟踪"
        if "偏弱" in full:
            return "偏弱，待确认"
        return "蓄势观察"
    if not stage:
        return "中线数据不足，先观察"
    if regime == "很差":
        return "大盘很差，中线宜收缩"
    return "中线观察"


def _shortline_view(
    scene: str,
    theory_status: str,
    daily_ruling: str,
    chase_ok: bool,
) -> str:
    """短线看法：追不追、冲高/回踩。"""
    sc = str(scene or theory_status or "")
    if any(k in sc for k in ("冲高", "减仓", "高抛")):
        return "不适合追，偏冲高减"
    if "突破确认" in sc:
        return "突破观察，确认后再跟"
    if any(k in sc for k in ("低吸", "防守观察")):
        return "宜等回踩/买点，不宜追高" if not chase_ok else "回踩附近可关注"
    if "不宜追" in daily_ruling or "偏空" in daily_ruling:
        return "不适合追"
    if chase_ok:
        return "短线空间尚可，谨慎参与"
    return "短线观望，不追"


def build_daily_ruling(
    fusion: dict[str, Any] | None = None,
    *,
    scene: str = "",
    theory_status: str = "",
    chase_ok: bool = False,
    gate_action: str = "",
) -> str:
    """日线裁定人话：偏多/偏空/中性 + 宜追|不宜追高|观望。

    主报告不展示 raw weighted_score。
    """
    fusion = fusion or {}
    score = fusion.get("weighted_score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0

    action = str(fusion.get("action") or "")
    sc = str(scene or theory_status or "")

    if score_f >= 0.15:
        bias = "偏多"
    elif score_f <= -0.1:
        bias = "偏空"
    else:
        bias = "中性"

    # 空仓「减仓」类 → 不宜追高/不新开
    reduce_like = any(k in action for k in ("减仓", "空仓", "止损", "观望"))
    if gate_action in ("不做", "观望", "减仓", "止损离场") or not chase_ok:
        stance = "不宜追高"
    elif bias == "偏多" and chase_ok:
        stance = "宜追" if "突破" in sc else "观望"
    else:
        stance = "观望"

    if reduce_like and bias != "偏多":
        stance = "不宜追高"

    return f"{bias}，{stance}"


def build_conclusion_block(
    *,
    major_stage: str = "",
    short_term_momentum: str = "",
    scene: str = "",
    theory_status: str = "",
    regime: str = "",
    mistery_gate: dict[str, Any] | None = None,
    key_prices: dict[str, Any] | None = None,
    fusion: dict[str, Any] | None = None,
    has_position: bool = False,
    daily_ruling: str | None = None,
    weekly_frame: str | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """组装结论块字段。"""
    gate = mistery_gate or {}
    kp = key_prices or {}
    chase_ok = bool(kp.get("chase_ok"))
    gate_action = str(gate.get("action") or "观望")
    cap = float(gate.get("position_cap_pct") or 0)

    ruling = daily_ruling or build_daily_ruling(
        fusion,
        scene=scene,
        theory_status=theory_status,
        chase_ok=chase_ok,
        gate_action=gate_action,
    )

    mid = _midline_view(major_stage, regime, weekly_frame=weekly_frame)
    short = _shortline_view(scene, theory_status, ruling, chase_ok)
    execution = gate_action_to_execution_text(
        gate_action,
        has_position=has_position,
        position_cap_pct=cap,
    )

    # 原因：只讲「账」与硬纪律，不与说明重复
    line_chase = str(kp.get("line_chase") or "")
    risk_c = kp.get("risk_chase")
    rew_c = kp.get("reward_chase")
    reason_parts: list[str] = []
    if risk_c is not None and rew_c is not None:
        try:
            rc, rw = float(risk_c), float(rew_c)
            if rc > 0 or rw > 0:
                if rw <= rc:
                    reason_parts.append(f"现价追大约亏 {rc:.1f}、赚 {rw:.1f}，不划算")
                elif not chase_ok:
                    # 账上未必更差，但是场景/门控禁止追
                    reason_parts.append("现价偏冲高，纪律不追")
                else:
                    reason_parts.append(f"现价追大约亏 {rc:.1f}、赚 {rw:.1f}")
        except (TypeError, ValueError):
            pass
    if not reason_parts and line_chase and "→" in line_chase:
        tag = line_chase.split("→")[-1].strip()
        if tag and tag != "可考虑":
            reason_parts.append("现价" + tag)
    if gate.get("hard_block") and gate.get("hard_block") != "none":
        hb = str(gate["hard_block"])
        if "H5" in hb or "H6" in hb:
            if not any("不划算" in p for p in reason_parts):
                reason_parts.append("近端空间不划算")
        elif "H1" in hb:
            reason_parts.append("大盘很差")
        elif "H2" in hb:
            reason_parts.append("衰退阶段不做多")
        elif "H3" in hb:
            reason_parts.append("派发不加仓")
        elif "H4" in hb:
            reason_parts.append("止损无法定义")
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for p in reason_parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    reason = "，".join(uniq) if uniq else "纪律门控"

    # 本周单焦点（渲染时只在 📌 出现一次，结论里仍带字段）
    if gate_action in ("不做", "观望"):
        this_week = "不追现价；回买点再谈"
    elif gate_action in ("轻仓试错", "回踩低吸"):
        buy_ref = kp.get("buy_ref")
        this_week = f"只做买点挂单（参考 {buy_ref:.2f}）" if buy_ref else "只做买点挂单"
    elif gate_action == "持有":
        this_week = "持有跟踪，破位再议，不加仓"
    elif gate_action in ("减仓", "止损离场"):
        this_week = "按关键价减仓/止损，不新开"
    else:
        this_week = "观察为主"

    # 说明：仅中线可跟踪 且 日线偏空；短句，不重复原因里的亏赚
    conflict = ""
    mid_ok = any(k in mid for k in ("可跟踪", "主升", "蓄势观察", "待确认"))
    short_no = any(k in short for k in ("不适合追", "不宜追")) or "不宜追" in ruling or "偏空" in ruling
    if mid_ok and short_no:
        conflict = "中线还能看，但今天这个价别买"

    return {
        "midline": mid,
        "shortline": short,
        "execution": execution,
        "reason": reason,
        "this_week": this_week,
        "conflict": conflict,
        "daily_ruling": ruling,
        # P1 预留
        "weekly_frame": weekly_frame,
    }
