"""短中线结论块：中线看法（周线理论）/ 短线看法 / 出手 / 原因 / 本周 / 冲突说明。

规格：docs/mid-short-dual-track-plan.md（B3C / B1A）。
"""
from __future__ import annotations

import re
from typing import Any

from trader_shared.mistery_gate import gate_action_to_execution_text

# 看法行禁止四阶段词（B3C）
_STAGE_WORDS_RE = re.compile(r"蓄势|主升|派发|衰退")


def _unwrap_chan(chan_result: Any) -> dict[str, Any]:
    if not isinstance(chan_result, dict):
        return {}
    try:
        from trader_shared.chan_core import unwrap_chan
        return unwrap_chan(chan_result) or {}
    except Exception:
        if "chanlun" in chan_result and isinstance(chan_result.get("chanlun"), dict):
            return chan_result["chanlun"]
        return chan_result


def _unwrap_wyck(wyck_result: Any) -> dict[str, Any]:
    if not isinstance(wyck_result, dict):
        return {}
    if "wyckoff" in wyck_result and isinstance(wyck_result.get("wyckoff"), dict):
        return wyck_result["wyckoff"]
    return wyck_result


def chanlun_midline_dir(chanlun_midline: Any) -> int:
    """与 format_chanlun_theory_line 同源方向：+1 / 0 / -1。"""
    chan = _unwrap_chan(chanlun_midline)
    if not chan:
        return 0

    buy_points = chan.get("buy_points") if isinstance(chan.get("buy_points"), list) else []
    sell_points = chan.get("sell_points") if isinstance(chan.get("sell_points"), list) else []
    divergence = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    trend_label = str(chan.get("trend_label") or "")
    st = str(chan.get("structure_type") or "")

    if any(isinstance(p, dict) and p.get("type") in ("一类卖", "二类卖", "三类卖") for p in sell_points):
        return -1
    if divergence.get("top_divergence"):
        return -1
    if any(isinstance(p, dict) and p.get("type") in ("一类买", "二类买", "三类买") for p in buy_points):
        return 1
    if divergence.get("bottom_divergence"):
        return 1
    if "上涨" in trend_label or "多" in trend_label:
        return 1
    if "下跌" in trend_label or "空" in trend_label:
        return -1
    # structure_type 兜底（与展示文案一致）
    if "下跌" in st or "空" in st:
        return -1
    if "上涨" in st or "多" in st:
        return 1
    # 盘整且无买卖点 → 中性；若 format 行含看跌则靠 trend
    try:
        from trader_shared.chan_core import format_chanlun_theory_line
        line = format_chanlun_theory_line(chanlun_midline)
        if "看跌" in line:
            return -1
        if "看涨" in line:
            return 1
    except Exception:
        pass
    return 0


def wyckoff_midline_bias(wyckoff_midline: Any) -> str:
    """strong_bull | strong_bear | neutral（B1A）。"""
    w = _unwrap_wyck(wyckoff_midline)
    if not w:
        return "neutral"

    strong_bear = bool(
        w.get("upthrust_signal") or w.get("bc_signal") or w.get("sow_signal")
    )
    strong_bull = bool(w.get("spring_signal") or w.get("sos_signal"))
    # 多信号：strong_bear 优先
    if strong_bear:
        return "strong_bear"
    if strong_bull:
        return "strong_bull"
    return "neutral"


def midline_theory_dirs(
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
) -> tuple[int, str]:
    """返回 (chan_dir, wyck_bias)。"""
    return chanlun_midline_dir(chanlun_midline), wyckoff_midline_bias(wyckoff_midline)


def _midline_view_from_theory(
    *,
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    weekly_frame: str | None = None,
) -> str:
    """中线看法：周线缠+威合成（B1A），禁止四阶段词。"""
    if weekly_frame == "破坏":
        return "中线框破坏 · 战略减/清倾向"

    chan_dir, wyck_bias = midline_theory_dirs(chanlun_midline, wyckoff_midline)
    chan = _unwrap_chan(chanlun_midline)
    st = str(chan.get("structure_type") or "").strip()

    if wyck_bias == "strong_bear":
        return "中线慎跟 · 偏空信号"

    if chan_dir < 0 and wyck_bias == "strong_bull":
        return "中线信号打架 · 暂缓跟踪"

    if chan_dir < 0:
        # 可用 structure_type 主词，不得插入 major_stage
        if st and not st.startswith("线段不足") and st != "无结构":
            main = st.replace("趋势", "").strip() or st
            if "下跌" in st:
                return f"{st} · 暂缓跟踪"
            if "盘整" in st:
                return "盘整偏空 · 暂缓跟踪"
            return f"{st} · 暂缓跟踪"
        return "盘整偏空 · 暂缓跟踪"

    if chan_dir > 0 and wyck_bias != "strong_bear":
        if "上涨" in st:
            return "上涨趋势未坏 · 可跟踪、不加仓"
        return "结构偏多 · 可跟踪、不加仓"

    return "中线观察"


def _assert_no_stage_words(text: str) -> str:
    """防御：看法不得含四阶段词。"""
    if _STAGE_WORDS_RE.search(text or ""):
        # 不应发生；若发生则降级为中性观察
        return "中线观察"
    return text


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
    chanlun_midline: Any = None,
    wyckoff_midline: Any = None,
    **_extra: Any,
) -> dict[str, Any]:
    """组装结论块字段。

    major_stage 仅用于 stage_line 展示与门控侧，不驱动 conclusion.midline。
    """
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

    mid = _assert_no_stage_words(
        _midline_view_from_theory(
            chanlun_midline=chanlun_midline,
            wyckoff_midline=wyckoff_midline,
            weekly_frame=weekly_frame,
        )
    )
    short = _shortline_view(scene, theory_status, ruling, chase_ok)
    execution = gate_action_to_execution_text(
        gate_action,
        has_position=has_position,
        position_cap_pct=cap,
    )

    # 原因：只讲「账」与硬纪律
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
    _gnotes = str(gate.get("notes") or "")
    if "不在中线回踩区" in _gnotes and not any("回踩区" in p for p in reason_parts):
        reason_parts.append("现价不在中线回踩区，不新开")
    if "中线看法偏空" in _gnotes and not any("中线看法偏空" in p for p in reason_parts):
        reason_parts.append("中线看法偏空，短线买点不作主开仓")
    if "置信不足" in _gnotes and not any("置信" in p for p in reason_parts):
        reason_parts.append("置信不足，轻仓或不动")
    if "筹码搬家" in _gnotes and not any("筹码" in p for p in reason_parts):
        reason_parts.append("筹码搬家警告，不新开")
    if "主力连续流出" in _gnotes and not any("流出" in p for p in reason_parts):
        reason_parts.append("主力连续流出，不新开")
    seen: set[str] = set()
    uniq: list[str] = []
    for p in reason_parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    reason = "；".join(uniq) if uniq else "纪律门控"
    if len(uniq) == 1:
        reason = uniq[0]
    elif uniq:
        reason = "，".join(uniq)

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

    # 冲突说明：中短冲突 + 验收3 缠多 vs 风控
    conflict = ""
    mid_track = "可跟踪" in mid or "未坏" in mid or "偏多" in mid
    mid_weak = any(k in mid for k in ("暂缓", "慎跟", "打架", "偏空", "破坏", "减/清"))
    short_no = (
        any(k in short for k in ("不适合追", "不宜追", "观望，不追"))
        or "不宜追" in ruling
        or "偏空" in ruling
        or any(k in execution for k in ("不买", "不追"))
    )

    stage_txt = str(major_stage or "").strip()
    if stage_txt == "None":
        stage_txt = ""
    stage_n = stage_txt
    for base in ("蓄势", "主升", "派发", "衰退"):
        if stage_n.startswith(base) or base in stage_n:
            stage_n = base
            break

    risk_sides: list[str] = []
    if stage_n in ("派发", "衰退"):
        risk_sides.append(f"阶段{stage_n}")
    _cm = _extra.get("chip_migration") if isinstance(_extra.get("chip_migration"), dict) else {}
    if _extra.get("chip_migration_warning") or (
        str(_cm.get("warning_level") or "") not in ("", "none", "None")
    ):
        risk_sides.append("筹码搬家警告")
    if _extra.get("fund_flow_outflow_veto") or bool((fusion or {}).get("fund_flow_outflow_veto")):
        risk_sides.append("主力连续流出")
    if "筹码搬家" in _gnotes and "筹码搬家警告" not in risk_sides:
        risk_sides.append("筹码搬家警告")
    if "主力连续流出" in _gnotes and "主力连续流出" not in risk_sides:
        risk_sides.append("主力连续流出")

    if mid_track and risk_sides:
        conflict = f"中线/缠论偏多，但{'/'.join(risk_sides)} → 以风控为准，不新开"
    elif mid_track and short_no:
        conflict = "中线还能看，现价别买"
    elif mid_weak and short_no:
        conflict = "周线偏空，短线也不追"
    elif mid_weak and not short_no:
        conflict = "中线偏空，短线信号不作主开仓"

    return {
        "midline": mid,
        "stage_line": stage_txt,
        "shortline": short,
        "execution": execution,
        "reason": reason,
        "this_week": this_week,
        "conflict": conflict,
        "daily_ruling": ruling,
        "weekly_frame": weekly_frame,
    }
