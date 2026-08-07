"""Wyckoff core facade: public API + re-export of split submodules."""
from __future__ import annotations

import json
import os
from typing import Any

from trader_shared.light_data import to_float

# ── Wyckoff 常量（唯一来源：trader_shared.config） ----
from trader_shared.config import (
    WYCKOFF_MIN_BARS,
    WYCKOFF_CLIMAX_ANCHOR_BARS,
    WYCKOFF_SC_COLD_START_BARS_DAILY,
    WYCKOFF_SC_COLD_START_BARS_WEEKLY,
    WYCKOFF_MEASURE_MIN_BARS,
    WYCKOFF_PNF_MIN_COLUMNS,
    WYCKOFF_BC_VOL_RATIO_THRESHOLD,
    WYCKOFF_BC_CHANGE_THRESHOLD,
    WYCKOFF_BC_UPPER_SHADOW_RATIO,
    WYCKOFF_BC_MIN_POS_PCT,
    WYCKOFF_SOW_SUPPORT_LOOKBACK,
    WYCKOFF_SOW_VOL_RATIO_THRESHOLD,
    WYCKOFF_SOW_CONSECUTIVE_DAYS,
    WYCKOFF_SPRING_SUPPORT_LOOKBACK,
    WYCKOFF_SPRING_RECLAIM_RATIO,
    WYCKOFF_SPRING_ATR_MULTIPLE,
    WYCKOFF_SPRING_BULLISH_VOL_RATIO,
    WYCKOFF_SPRING_LOW_VOL_RATIO,
    WYCKOFF_UTAD_BREAKOUT_RATIO,
    WYCKOFF_UTAD_RECLAIM_RATIO,
    WYCKOFF_UT_VOL_RATIO,
    WYCKOFF_DIVERGENCE_BARS,
    WYCKOFF_DIVERGENCE_RATIO,
    WYCKOFF_SOS_RECENT_LOOKBACK,
    WYCKOFF_PHASE_LOOKBACK,
    WYCKOFF_PHASE_MIN_TR_QUALITY,
    WYCKOFF_PHASE_A_SEED_MIN_QUALITY,
    WYCKOFF_VSA_AVG_SPREAD_PERIOD,
    WYCKOFF_SCORE_SPRING,
    WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS,
    WYCKOFF_SCORE_BULLISH_DIV,
    WYCKOFF_SCORE_UT,
    WYCKOFF_SCORE_BEARISH_DIV,
    WYCKOFF_SCORE_BC,
    WYCKOFF_SCORE_SOW,
    WYCKOFF_SCORE_MAX_ABS,
    WYCKOFF_SCORE_AR,
    WYCKOFF_SCORE_ARE,
    WYCKOFF_SCORE_SOS,
    WYCKOFF_SCORE_ST,
    WYCKOFF_SCORE_LPS,
    WYCKOFF_SCORE_LPSY,
    WYCKOFF_SCORE_COMPRESSION,
    WYCKOFF_SCORE_TREND_PB,
    WYCKOFF_SCORE_TREND_RALLY,
    WYCKOFF_SCORE_PS,
    WYCKOFF_SCORE_PSY,
    WYCKOFF_SCORE_BU,
    WYCKOFF_SCORE_UTAD,
    WYCKOFF_SCORE_STOPPING_VOLUME,
    WYCKOFF_SCORE_CLUSTER_CONFIRM,
    WYCKOFF_SCORE_CLUSTER_DISTRIB,
    WYCKOFF_SCORE_CLUSTER_FAIL,
    # ① TR 质量接打分
    WYCKOFF_TR_QUALITY_NEUTRAL,
    WYCKOFF_SCORE_TR_QUALITY_GAIN,
    WYCKOFF_COMPRESSION_LOOKBACK,
    WYCKOFF_COMPRESSION_ATR_QUANTILE,
    WYCKOFF_COMPRESSION_VOL_RATIO,
    WYCKOFF_COMPRESSION_VOL_REF_WINDOW,
    WYCKOFF_TREND_PB_LOOKBACK,
    WYCKOFF_TREND_PB_MIN_PULLBACK,
    WYCKOFF_TREND_PB_MAX_PULLBACK,
    WYCKOFF_TREND_PB_VOL_SHRINK,
    WYCKOFF_TREND_PB_MA_WINDOW,
)


# ── 共享工具：Spring 刺穿深度 / BC 高位过滤 ─────────────────────────


from .wyckoff_phase import (
    _PHASE_ORDER,
    _WYCKOFF_PHASE_FILE,
    _detect_phase,
    _load_phase_state,
    _phase_key,
    _save_phase_state,
    _scan_for_signal,
    _transition_phase
)
from .wyckoff_phase_a_store import (
    delete_phase_a_anchor,
    load_phase_a_anchor,
    save_phase_a_anchor,
)

from .wyckoff_events import (
    _board_vol_scale,
    _compute_dynamic_support,
    _detect_ar,
    _detect_are,
    _detect_buying_climax,
    _detect_compression,
    _detect_effort_vs_result,
    _find_sc_anchor,
    _detect_lps,
    _detect_lpsy,
    _detect_selling_climax,
    _detect_sign_of_weakness,
    _detect_sos,
    _detect_spring,
    _detect_st,
    _spring_test_fields_from_st,
    _detect_secondary_test_sc,
    _detect_trend_pullback,
    _detect_trend_rally,
    _detect_upthrust,
    _detect_volume_divergence,
    _is_bc_high_position,
    _is_frozen_board,
    _is_trading_range,
    _detect_trading_range,
    _detect_event_cluster,
    _detect_preliminary_support,
    _detect_preliminary_supply,
    _detect_backup,
    _detect_utad,
    _detect_jump_across_creek,
    _detect_stopping_volume,
    _classify_cm_mode,
    _cause_effect_targets,
    _price_pos_pct,
    _spring_breach_level,
    resolve_wyckoff_is_index,
)


def _resolve_score_conflicts(analysis: dict) -> set[str]:
    """同段反向极性互斥：返回应抑制打分的信号键，避免 SC+SOW 等对冲成假中性 50 分。

    规则（主叙事优先）：
    - SC vs SOW：有 AR/Spring/积累确认 → 抑 SOW；否则抑 SC（破位叙事）
    - Spring vs UT：premature 先抑；否则积累侧/SOS 抑 UT，派发侧/SOW 抑 Spring
    - LPS vs LPSY：有派发背景只计 LPSY，否则只计 LPS
    - AR vs ARE / TrendPB vs TrendRally：按积累/派发极性抑一侧；两边都有或都无则双侧抑
    - 双背离同时：都抑（冲突）
    - UTAD 成立时普通 UT 分不再重复计（只计 UTAD）
    """
    suppress: set[str] = set()
    sc = bool(analysis.get("sc_signal"))
    sow = bool(analysis.get("sow_signal"))
    spring = bool(analysis.get("spring_signal"))
    ut = bool(analysis.get("upthrust_signal"))
    lps = bool(analysis.get("lps_signal"))
    lpsy = bool(analysis.get("lpsy_signal"))
    bull = bool(analysis.get("bullish_volume_divergence"))
    bear = bool(analysis.get("bearish_volume_divergence"))
    ar = bool(analysis.get("ar_signal"))
    are = bool(analysis.get("are_signal"))
    tpb = bool(analysis.get("trend_pullback_signal"))
    trally = bool(analysis.get("trend_rally_signal"))

    has_acc = any(
        analysis.get(k)
        for k in (
            "sc_signal",
            "spring_signal",
            "sos_signal",
            "st_signal",
            "bu_signal",
            "accumulation_confirmed",
        )
    )
    has_dist = any(
        analysis.get(k)
        for k in (
            "bc_signal",
            "upthrust_signal",
            "sow_signal",
            "utad_signal",
            "distribution_confirmed",
        )
    )

    if sc and sow:
        if (
            analysis.get("ar_signal")
            or spring
            or analysis.get("accumulation_confirmed")
            or analysis.get("st_signal")
        ):
            suppress.add("sow_signal")
        else:
            suppress.add("sc_signal")

    if spring and ut:
        sp_prem = bool(analysis.get("spring_premature"))
        ut_prem = bool(analysis.get("upthrust_premature"))
        if sp_prem and not ut_prem:
            suppress.add("spring_signal")
        elif ut_prem and not sp_prem:
            suppress.add("upthrust_signal")
        elif (
            analysis.get("accumulation_confirmed")
            or analysis.get("sos_signal")
            or analysis.get("lps_signal")
            or analysis.get("bu_signal")
        ):
            suppress.add("upthrust_signal")
        elif (
            analysis.get("distribution_confirmed")
            or sow
            or analysis.get("bc_signal")
            or analysis.get("utad_signal")
        ):
            suppress.add("spring_signal")
        else:
            # 默认保留 Spring 叙事（试探吸筹），抑 UT
            suppress.add("upthrust_signal")

    if lps and lpsy:
        if has_dist:
            suppress.add("lps_signal")
        else:
            suppress.add("lpsy_signal")

    if ar and are:
        if has_dist and not has_acc:
            suppress.add("ar_signal")
        elif has_acc and not has_dist:
            suppress.add("are_signal")
        else:
            suppress.add("ar_signal")
            suppress.add("are_signal")

    if tpb and trally:
        if has_dist and not has_acc:
            suppress.add("trend_pullback_signal")
        elif has_acc and not has_dist:
            suppress.add("trend_rally_signal")
        else:
            suppress.add("trend_pullback_signal")
            suppress.add("trend_rally_signal")

    if bull and bear:
        suppress.add("bullish_volume_divergence")
        suppress.add("bearish_volume_divergence")

    if analysis.get("utad_signal") and ut:
        suppress.add("upthrust_signal")  # UTAD 已单独计分

    return suppress


def _cold_start_anchor_bars(timeframe: str = "daily") -> int:
    return (
        int(WYCKOFF_SC_COLD_START_BARS_WEEKLY)
        if str(timeframe or "").lower() == "weekly"
        else int(WYCKOFF_SC_COLD_START_BARS_DAILY)
    )


def _build_phase_a_range(sc: dict, ar: dict, *, timeframe: str = "daily") -> dict:
    """Phase A 区间边界：SC 低点 + AR 高点；status 诚实透出四态。"""
    sc_low = sc.get("sc_low") if sc.get("sc_signal") else None
    if sc_low is None and sc.get("sc_signal") and sc.get("sc_price"):
        sc_low = sc.get("sc_price")
    ar_high = ar.get("ar_high") if ar.get("ar_signal") else None
    sc_bar_idx = sc.get("sc_bar_idx") if sc.get("sc_signal") else ar.get("sc_bar_idx")
    ar_bar_idx = ar.get("ar_bar_idx") if ar.get("ar_signal") else None

    if sc.get("phase_a_failed"):
        status = "failed"
    elif not sc.get("sc_signal"):
        status = "none"
    elif ar.get("ar_signal") and ar_high is not None:
        status = "established"
    else:
        status = "forming"

    return {
        "sc_low": sc_low,
        "ar_high": ar_high,
        "sc_bar_idx": sc_bar_idx,
        "ar_bar_idx": ar_bar_idx,
        "status": status,
        "anchor_bars": sc.get("anchor_bars") or ar.get("anchor_bars") or _cold_start_anchor_bars(timeframe),
        "search_mode": sc.get("search_mode") or ar.get("search_mode") or "cold_start",
        "fail_bar_idx": sc.get("fail_bar_idx"),
        "fail_reason": sc.get("fail_reason"),
        "st_sc_low": None,
        "sc_low_refined": None,
    }


def _refine_phase_a_sc_low(phase_a_range: dict, st_sc: dict) -> dict:
    """若广义 ST 有效，记录 st_sc_low / sc_low_refined；不覆盖原 SC 棒 sc_low。

    合同：``sc_low`` = SC 棒最低价 SSOT；更低的成功 ST low 写入 ``sc_low_refined``
    （见 ``wyckoff-phase-a-range-handoff.md`` §4.4.3）。成熟箱下沿在 overlay /
    箱体文案侧取 ``min(sc_low, st_sc_low)``。
    """
    if not st_sc.get("secondary_test_sc_signal"):
        return phase_a_range
    st_low = st_sc.get("st_sc_low")
    sc_low = phase_a_range.get("sc_low")
    if st_low is None or sc_low is None:
        return phase_a_range
    out = dict(phase_a_range)
    out["st_sc_low"] = st_low
    try:
        if float(st_low) < float(sc_low):
            out["sc_low_refined"] = round(float(st_low), 2)
    except (TypeError, ValueError):
        pass
    return out


def _tr_window_bar_count(
    bars: list[dict] | None,
    phase_a_range: dict | None,
    tr_ctx: dict | None = None,
) -> int:
    """TR 窗根数：优先 tr_start..tr_end，缺省 sc_bar_idx..len-1。"""
    n = len(bars or [])
    start = None
    end = None
    if tr_ctx:
        start = tr_ctx.get("tr_start")
        end = tr_ctx.get("tr_end")
    pa = phase_a_range or {}
    if start is None:
        start = pa.get("sc_bar_idx")
    if end is None and n > 0:
        end = n - 1
    if start is None or end is None:
        return 0
    try:
        return max(0, int(end) - int(start) + 1)
    except (TypeError, ValueError):
        return 0


def _resolve_tr_maturity(
    phase_a_range: dict,
    st_sc: dict,
    *,
    bars: list[dict] | None = None,
    tr_ctx: dict | None = None,
    min_bars: int | None = None,
) -> dict:
    """TR 成熟度 L0–L3（法源：wyckoff-tr-maturity-l0l3-handoff）。

    L0 无 SC；L1 有 SC/SC+AR 但无成功 ST，或有 ST 无 ar_high；
    L2 = 成功 ST ∧ 有效 ar_high；L3 = L2 ∧ 窗宽足够。
    """
    status = str(phase_a_range.get("status") or "none")
    # 严格：无 SC（status=none）/ 已失败（status=failed）→ L0；仅分位 TR 不得抬级
    if status in {"none", "failed"}:
        reason = (
            "Phase A 失败（有效跌破 SC 未收回）"
            if status == "failed"
            else "无有效 SC（无 Phase A）"
        )
        return {
            "tr_maturity": "L0",
            "tr_maturity_reason": reason,
            "measure_allowed": False,
            "box_display_mode": "none",
        }

    st_ok = bool(st_sc.get("secondary_test_sc_signal"))
    ar_high = phase_a_range.get("ar_high")
    try:
        ar_ok = ar_high is not None and float(ar_high) > 0
    except (TypeError, ValueError):
        ar_ok = False

    if not st_ok:
        reason = (
            "有 SC+AR，缺成功广义 ST（雏形）"
            if status == "established"
            else "有 SC，缺 AR/ST（雏形）"
        )
        return {
            "tr_maturity": "L1",
            "tr_maturity_reason": reason,
            "measure_allowed": False,
            "box_display_mode": "proto",
        }
    if not ar_ok:
        return {
            "tr_maturity": "L1",
            "tr_maturity_reason": "有成功 ST，上沿未钉（无有效 ar_high）",
            "measure_allowed": False,
            "box_display_mode": "proto",
        }

    # L2 基线；宽度够 → L3
    width = _tr_window_bar_count(bars, phase_a_range, tr_ctx)
    need = int(WYCKOFF_MEASURE_MIN_BARS if min_bars is None else min_bars)
    if width >= need:
        return {
            "tr_maturity": "L3",
            "tr_maturity_reason": f"ST+AR 成立且 TR 窗 {width}≥{need}",
            "measure_allowed": True,
            "box_display_mode": "box",
        }
    return {
        "tr_maturity": "L2",
        "tr_maturity_reason": f"箱体已立（ST+AR），宽度不足（窗 {width}<{need}）",
        "measure_allowed": False,
        "box_display_mode": "box",
    }


def _promote_maturity_by_pnf(maturity: dict, ce: dict) -> dict:
    """L2 时若 P&F 水平计数列数够宽，升为 L3。"""
    if maturity.get("tr_maturity") != "L2":
        return maturity
    if ce.get("pnf_method") != "horizontal":
        return maturity
    try:
        cols = int(ce.get("pnf_columns") or 0)
    except (TypeError, ValueError):
        cols = 0
    if cols < int(WYCKOFF_PNF_MIN_COLUMNS):
        return maturity
    out = dict(maturity)
    out["tr_maturity"] = "L3"
    out["measure_allowed"] = True
    out["box_display_mode"] = "box"
    out["tr_maturity_reason"] = (
        f"箱体已立且 P&F 水平列 {cols}≥{int(WYCKOFF_PNF_MIN_COLUMNS)}"
    )
    return out


def _measure_gate_note(tr_maturity: str) -> str:
    if tr_maturity == "L0":
        return "未达 L3（无 Phase A）"
    if tr_maturity == "L1":
        return "未达 L3（缺成功 ST / 仍为雏形）"
    if tr_maturity == "L2":
        return "未达 L3（箱体已立、宽度不足）"
    return ""


def _apply_measure_gate(ce: dict, maturity: dict) -> dict:
    """非 L3 强制清空量度目标；保留诚实 note。"""
    if maturity.get("measure_allowed"):
        return ce
    note = _measure_gate_note(str(maturity.get("tr_maturity") or "L0"))
    out = dict(ce or {})
    out["cause_effect_up_target"] = None
    out["cause_effect_down_target"] = None
    out["cause_effect_range"] = None
    prev = str(out.get("cause_effect_note") or "").strip()
    if note:
        out["cause_effect_note"] = note if not prev else f"{note}；{prev}"
    return out


def _seed_tr_quality_from_bounds(sc_low: float, ar_high: float) -> float:
    """established 种子箱宽度 → tr_quality（避免分位 TR 缺失时永久 gated）。"""
    if sc_low <= 0 or ar_high <= sc_low:
        return WYCKOFF_PHASE_A_SEED_MIN_QUALITY
    width_pct = (ar_high - sc_low) / sc_low * 100
    if 3.0 <= width_pct <= 25.0:
        return min(1.0, 0.45 + width_pct / 40.0)
    if width_pct > 0:
        return max(WYCKOFF_PHASE_A_SEED_MIN_QUALITY, min(0.55, width_pct / 50.0))
    return WYCKOFF_PHASE_A_SEED_MIN_QUALITY


def _overlay_phase_a_seed_tr_ctx(
    tr_ctx: dict | None,
    phase_a_range: dict,
    *,
    tr_maturity: str | None = None,
) -> dict | None:
    """成熟箱 overlay：仅 L2/L3 用 sc_low/ar_high 写 phase_a_seed。

    L1（含 SC+AR 无 ST）保留 phase_a_range 候选边界供雏形展示，不放出种子箱量度。
    ``tr_maturity is None`` 时回退旧行为（established → seed），供单测直接调用。
    """
    status = phase_a_range.get("status") or "none"
    ctx: dict = dict(tr_ctx) if tr_ctx else {}
    ctx["phase_a_status"] = status
    mature = tr_maturity in ("L2", "L3") or (
        tr_maturity is None and status == "established"
    )
    if not mature:
        if ctx and ctx.get("tr_lower") is not None and not ctx.get("tr_seed_source"):
            ctx["tr_seed_source"] = "percentile"
        # L1 候选边界仅挂在 phase_a_* 字段，不改 tr_lower/tr_upper
        return ctx or None

    sc_low = phase_a_range.get("sc_low")
    ar_high = phase_a_range.get("ar_high")
    if sc_low is None or ar_high is None:
        return ctx or None
    try:
        # 成熟箱下沿 = min(SC low, 成功 ST low)；上沿 = AR high
        lo = float(sc_low)
        st_low = phase_a_range.get("st_sc_low")
        if st_low is None:
            st_low = phase_a_range.get("sc_low_refined")
        if st_low is not None:
            lo = min(lo, float(st_low))
        hi = float(ar_high)
    except (TypeError, ValueError):
        return ctx or None
    if lo >= hi:
        return ctx or None

    ctx["tr_lower_ref"] = ctx.get("tr_lower")
    ctx["tr_upper_ref"] = ctx.get("tr_upper")
    ctx["tr_quality_ref"] = ctx.get("tr_quality")
    ctx["tr_lower"] = lo
    ctx["tr_upper"] = hi
    ctx["tr_amplitude_pct"] = round((hi - lo) / lo * 100, 2)
    ctx["tr_width"] = int(phase_a_range.get("anchor_bars") or WYCKOFF_CLIMAX_ANCHOR_BARS)
    seed_q = _seed_tr_quality_from_bounds(lo, hi)
    prev_q = ctx.get("tr_quality")
    try:
        prev_q_f = float(prev_q) if prev_q is not None else None
    except (TypeError, ValueError):
        prev_q_f = None
    if prev_q_f is None or prev_q_f < float(WYCKOFF_PHASE_MIN_TR_QUALITY):
        ctx["tr_quality"] = max(seed_q, float(WYCKOFF_PHASE_A_SEED_MIN_QUALITY))
    else:
        ctx["tr_quality"] = max(prev_q_f, seed_q)
    ctx["phase_a_seed"] = True
    ctx["tr_seed_source"] = "phase_a_seed"
    ctx["phase_a_status"] = "established"
    if ctx.get("tr_baseline_volume") is None:
        ctx["tr_baseline_volume"] = 0.0
    last_close = ctx.get("last_close")
    if last_close is not None:
        ctx["in_tr"] = lo <= float(last_close) <= hi
    elif ctx.get("in_tr") is None:
        ctx["in_tr"] = True
    return ctx


def wyckoff_analysis(
    bars: list[dict],
    symbol: str = "",
    timeframe: str = "daily",
    use_persisted_phase: bool = True,
    index_weekly_bars: list[dict] | None = None,
    phase_a_range: dict | None = None,
    use_persisted_phase_a_anchor: bool = True,
) -> dict:
    if len(bars) < WYCKOFF_MIN_BARS:
        result = {
            "spring_signal": False, "spring_reason": "数据不足", "spring_price": None,
            "upthrust_signal": False, "upthrust_reason": "数据不足", "upthrust_price": None,
            "bc_signal": False, "bc_reason": "数据不足", "bc_price": None,
            "sc_signal": False, "sc_reason": "数据不足", "sc_price": None,
            "sow_signal": False, "sow_intraday_warn": False,
            "sow_reason": "数据不足", "sow_price": None,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            # 新增信号
            "ar_signal": False, "ar_reason": "数据不足", "ar_price": None,
            "are_signal": False, "are_reason": "数据不足", "are_price": None,
            "sos_signal": False, "sos_reason": "数据不足", "sos_price": None,
            "st_signal": False, "st_reason": "数据不足", "st_price": None,
            "lps_signal": False, "lps_reason": "数据不足", "lps_price": None,
            "lpsy_signal": False, "lpsy_reason": "数据不足", "lpsy_price": None,
            "ps_signal": False, "ps_reason": "数据不足", "ps_price": None,
            "psy_signal": False, "psy_reason": "数据不足", "psy_price": None,
            "bu_signal": False, "bu_reason": "数据不足", "bu_price": None,
            "utad_signal": False, "utad_reason": "数据不足", "utad_price": None,
            "cause_effect_up_target": None, "cause_effect_down_target": None,
            "cause_effect_range": None, "cause_effect_note": "数据不足",
            "pnf_box_size": None, "pnf_columns": None, "pnf_method": None,
            "wyckoff_summary": "K线数据不足，无法进行威科夫分析",
            "tr_upper": None, "tr_lower": None, "tr_baseline_volume": None,
            "tr_width": None, "tr_amplitude_pct": None, "tr_quality": None, "tr_in_range": None,
            # P0-5: 事件簇确认透出（数据不足全 None/False）
            "accumulation_confirmed": False, "distribution_confirmed": False,
            "accumulation_failed": False, "distribution_failed": False,
            "cluster_quality": None, "cluster_confidence": 0.0, "cluster_reason": "数据不足",
            # 五阶段机原典串联：过早信号标注（数据不足时全 False）
            "spring_premature": False,
            "upthrust_premature": False,
            "compression_signal": False, "compression_reason": "数据不足", "compression_price": None,
            "trend_pullback_signal": False, "trend_pullback_reason": "数据不足", "trend_pullback_price": None,
            "trend_rally_signal": False, "trend_rally_reason": "数据不足", "trend_rally_price": None,
            "spring_test_signal": False, "spring_test_reason": "数据不足", "spring_test_price": None,
            "phase_tr_gated": False, "phase_tr_gate_reason": "",
            "phase_a_status": "none",
            "phase_a_range": {
                "sc_low": None, "ar_high": None, "sc_bar_idx": None, "ar_bar_idx": None,
                "status": "none", "anchor_bars": _cold_start_anchor_bars(timeframe),
                "st_sc_low": None, "sc_low_refined": None,
            },
            "sc_low": None, "sc_low_refined": None, "ar_high": None,
            "secondary_test_sc_signal": False, "secondary_test_sc_reason": "数据不足", "st_sc_low": None,
            "tr_maturity": "L0",
            "tr_maturity_reason": "数据不足",
            "measure_allowed": False,
            "box_display_mode": "none",
        }
        if use_persisted_phase_a_anchor and str(symbol or "").strip():
            delete_phase_a_anchor(symbol, timeframe)
        return result

    # P2-2: 动态支撑位计算（多源集成）— 仅用于 Spring 检测
    _is_weekly = str(timeframe or "").lower() == "weekly"
    _weekly_scale = 0.2 if _is_weekly else 1.0
    _phase_lb = max(10, int(WYCKOFF_PHASE_LOOKBACK * _weekly_scale))
    _support_lb = max(3, int(10 * _weekly_scale))
    dynamic_support = _compute_dynamic_support(bars, lookback=_support_lb)

    # P0-3: TR 识别层 — 先定位当前交易区间，作为事件检测的语境
    # 周线：根数更少、单根振幅更大，须缩放 min_width/lookback，并放宽 amp 上限
    if _is_weekly:
        from trader_shared.config import (
            WYCKOFF_TR_LOOKBACK,
            WYCKOFF_TR_MIN_WIDTH,
            WYCKOFF_TR_AMPLITUDE_MAX,
            WYCKOFF_TR_AMPLITUDE_MIN,
        )
        tr_ctx = _detect_trading_range(
            bars,
            lookback=max(24, int(WYCKOFF_TR_LOOKBACK * _weekly_scale)),
            min_width=max(4, int(WYCKOFF_TR_MIN_WIDTH * _weekly_scale)),
            max_amplitude_pct=max(WYCKOFF_TR_AMPLITUDE_MAX, 55.0),
            min_amplitude_pct=max(3.0, WYCKOFF_TR_AMPLITUDE_MIN * 0.7),
        )
    else:
        tr_ctx = _detect_trading_range(bars)
    if (
        use_persisted_phase_a_anchor
        and str(symbol or "").strip()
        and phase_a_range is None
    ):
        phase_a_range = load_phase_a_anchor(symbol, timeframe, bars)
    event_tr_ctx = dict(tr_ctx) if isinstance(tr_ctx, dict) else {}
    if isinstance(phase_a_range, dict):
        event_tr_ctx["phase_a_range"] = phase_a_range
    if not event_tr_ctx:
        event_tr_ctx = None

    # 指数标的：仅放宽 SC 检测量阈（_sc_detector_params）；禁止软 ST 绕过
    is_index = resolve_wyckoff_is_index(symbol)
    spring = _detect_spring(bars, _support=dynamic_support, symbol=symbol, tr_ctx=event_tr_ctx)
    upthrust = _detect_upthrust(bars, tr_ctx=event_tr_ctx)
    bc = _detect_buying_climax(bars, tr_ctx=event_tr_ctx)
    sc = _detect_selling_climax(bars, tr_ctx=event_tr_ctx, timeframe=timeframe, is_index=is_index)
    sow = _detect_sign_of_weakness(bars, tr_ctx=event_tr_ctx)  # SOW 使用自己的支撑位计算（处理 consecutive 逻辑）
    bearish_div, bullish_div = _detect_volume_divergence(bars)
    ar = _detect_ar(bars, tr_ctx=event_tr_ctx, timeframe=timeframe, is_index=is_index)
    are = _detect_are(bars, tr_ctx=event_tr_ctx)
    # 主路径近端回扫 SOS（突破后数日仍亮）；须晚于 SC，防派发段旧强势
    # 簇/BU 内仍 tip-only（默认 lookback_tips=1）
    _sc_tip_floor = sc.get("sc_bar_idx")
    try:
        _sc_tip_floor = int(_sc_tip_floor) if _sc_tip_floor is not None else None
    except (TypeError, ValueError):
        _sc_tip_floor = None
    sos = _detect_sos(
        bars,
        tr_ctx=event_tr_ctx,
        lookback_tips=int(WYCKOFF_SOS_RECENT_LOOKBACK),
        min_tip_idx=_sc_tip_floor,
    )
    st = _detect_st(bars, tr_ctx=event_tr_ctx)
    spring_test = _spring_test_fields_from_st(st)
    lps = _detect_lps(bars, tr_ctx=event_tr_ctx)
    lpsy = _detect_lpsy(bars, tr_ctx=event_tr_ctx)
    # LPSY 门控与打分一致：无派发背景则不亮灯（避免展示吓人、分数不扣）
    _has_dist_bg = bool(bc.get("bc_signal") or upthrust.get("upthrust_signal") or sow.get("sow_signal"))
    if lpsy.get("lpsy_signal") and not _has_dist_bg:
        lpsy = {
            "lpsy_signal": False,
            "lpsy_reason": "无派发背景（BC/UT/SOW），LPSY 不成立",
            "lpsy_price": None,
            "lpsy_gated": True,
        }
    # 原典补齐
    ps = _detect_preliminary_support(bars, tr_ctx=event_tr_ctx)
    psy = _detect_preliminary_supply(bars, tr_ctx=event_tr_ctx)
    bu = _detect_backup(bars, tr_ctx=event_tr_ctx)
    utad = _detect_utad(
        bars,
        tr_ctx=event_tr_ctx,
        bc_signal=bool(bc.get("bc_signal")),
        sow_signal=bool(sow.get("sow_signal")),
        upthrust_signal=bool(upthrust.get("upthrust_signal")),
        upthrust_result=upthrust,
    )
    # P2/P3: 新增信号
    compression = _detect_compression(bars)
    trend_pullback = _detect_trend_pullback(bars)
    trend_rally = _detect_trend_rally(bars)
    # P0-5: 事件簇确认 — 将孤立信号升级为可信的积累/派发事件簇（校验先后顺序 + strength 定级）
    cluster = _detect_event_cluster(bars, tr_ctx=event_tr_ctx)
    phase_a_range = _build_phase_a_range(sc, ar, timeframe=timeframe)
    st_sc = _detect_secondary_test_sc(
        bars,
        tr_ctx=event_tr_ctx,
        phase_a_range=phase_a_range,
        timeframe=timeframe,
        is_index=is_index,
    )
    phase_a_range = _refine_phase_a_sc_low(phase_a_range, st_sc)
    # Bug G：Phase A 失败时强制作废事件簇，禁止 accum✓ 与 phase_a failed 并存
    # 法源 docs/plans/wyckoff-sos-epic-bcg-handoff.md
    if str(phase_a_range.get("status") or "") == "failed":
        cluster = {
            "accumulation_confirmed": False,
            "distribution_confirmed": False,
            "accumulation_failed": False,
            "distribution_failed": False,
            "cluster_quality": None,
            "cluster_confidence": 0.0,
            "cluster_reason": "Phase A 失败，事件簇作废",
        }
    # L0–L3 成熟度：先按 SC/ST/AR + 窗宽定级，再决定是否成熟箱 overlay
    maturity = _resolve_tr_maturity(
        phase_a_range, st_sc, bars=bars, tr_ctx=tr_ctx
    )
    phase_tr_ctx = _overlay_phase_a_seed_tr_ctx(
        tr_ctx, phase_a_range, tr_maturity=maturity["tr_maturity"]
    )
    # TR/种子 overlay 后用更完整 tr_ctx 重判近端 SOS + BU（南网：分位 TR 或种子上沿）
    # 合并顺序：原始 TR（保留 tr_start 供 thrust 溪内量基线）→ event → phase overlay → AR
    _sos_tr: dict = {}
    if isinstance(tr_ctx, dict):
        _sos_tr.update(tr_ctx)
    if isinstance(event_tr_ctx, dict):
        _sos_tr.update(event_tr_ctx)
    if isinstance(phase_tr_ctx, dict):
        _sos_tr.update(phase_tr_ctx)
    if isinstance(phase_a_range, dict):
        _sos_tr["phase_a_range"] = phase_a_range
        if phase_a_range.get("ar_high") is not None:
            _sos_tr["ar_high"] = phase_a_range.get("ar_high")
    if ar.get("ar_signal") and ar.get("ar_high") is not None:
        _sos_tr.setdefault("ar_high", ar.get("ar_high"))
    _sc_floor2 = phase_a_range.get("sc_bar_idx")
    if _sc_floor2 is None:
        _sc_floor2 = _sc_tip_floor
    else:
        try:
            _sc_floor2 = int(_sc_floor2)
        except (TypeError, ValueError):
            _sc_floor2 = _sc_tip_floor
    if _sos_tr:
        sos2 = _detect_sos(
            bars,
            tr_ctx=_sos_tr,
            lookback_tips=int(WYCKOFF_SOS_RECENT_LOOKBACK),
            min_tip_idx=_sc_floor2,
        )
        if sos2.get("sos_signal"):
            sos = sos2
            bu = _detect_backup(bars, tr_ctx=_sos_tr)
    if phase_tr_ctx is not None:
        phase_tr_ctx["last_close"] = to_float(bars[-1].get("close")) if bars else None
        # 种子箱补 TR 窗口，供周/日线 P&F 水平计数落在 cause 区间内
        _sc_i = phase_a_range.get("sc_bar_idx")
        if (
            phase_tr_ctx.get("phase_a_seed")
            and _sc_i is not None
            and phase_tr_ctx.get("tr_start") is None
        ):
            try:
                phase_tr_ctx["tr_start"] = int(_sc_i)
                phase_tr_ctx["tr_end"] = len(bars) - 1
                phase_tr_ctx["tr_width"] = max(
                    1, int(phase_tr_ctx["tr_end"]) - int(phase_tr_ctx["tr_start"]) + 1
                )
            except (TypeError, ValueError):
                pass
        # overlay 后按真实窗宽再裁定一次（L2→L3）
        if maturity["tr_maturity"] in ("L2", "L3"):
            maturity = _resolve_tr_maturity(
                phase_a_range, st_sc, bars=bars, tr_ctx=phase_tr_ctx
            )
    # P2-R6：因果目标在种子 overlay（+ST refine）之后重算；中线必须吃周 K bars
    ce = _cause_effect_targets(phase_tr_ctx or tr_ctx, bars)
    # L2 且 P&F 水平列够宽 → 升 L3；非 L3 强制清空量度目标
    maturity = _promote_maturity_by_pnf(maturity, ce)
    ce = _apply_measure_gate(ce, maturity)
    phase_a_range = {
        **phase_a_range,
        "tr_maturity": maturity["tr_maturity"],
        "tr_maturity_reason": maturity["tr_maturity_reason"],
        "measure_allowed": maturity["measure_allowed"],
        "box_display_mode": maturity["box_display_mode"],
    }

    # P1-1: 阶段状态机 — 基于信号序列推断积累/派发阶段
    signals_dict = {
        "spring_signal": spring["spring_signal"],
        "upthrust_signal": upthrust["upthrust_signal"],
        "bc_signal": bc["bc_signal"],
        "sc_signal": sc["sc_signal"],
        "sow_signal": sow["sow_signal"],
        "ar_signal": ar["ar_signal"],
        "are_signal": are["are_signal"],
        "sos_signal": sos["sos_signal"],
        "st_signal": st["st_signal"],
        "spring_test_signal": spring_test["spring_test_signal"],
        "secondary_test_sc_signal": st_sc["secondary_test_sc_signal"],
        "lps_signal": lps["lps_signal"],
        "lpsy_signal": lpsy["lpsy_signal"],
        "compression_signal": compression["compression_signal"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
        "trend_rally_signal": trend_rally["trend_rally_signal"],
        "bu_signal": bu.get("bu_signal"),
        "utad_signal": utad.get("utad_signal"),
        "ps_signal": ps.get("ps_signal"),
        "psy_signal": psy.get("psy_signal"),
        "tr_in_range": bool(phase_tr_ctx.get("in_tr")) if phase_tr_ctx else False,
        "tr_upper": phase_tr_ctx.get("tr_upper") if phase_tr_ctx else None,
        "last_close": to_float(bars[-1].get("close")) if bars else None,
    }
    # P-M1/P-M6（Bug I 收尾）：统一 SC 锚注入阶段机 —— 与主流程 SC 灯
    # （wc.py _detect_selling_climax）同 event_tr_ctx 同源；_find_sc_anchor 已支持
    # tr_ctx.sc_anchor 短路（wyckoff-epic-context-refactor-handoff I-M1），周线路径
    # 同一行覆盖（timeframe/is_index 透传 → 周线冷启动 39 帽，P-M6/P5）。
    # phase_tr_ctx 由 _overlay_phase_a_seed_tr_ctx 保证为 dict（恒含 phase_a_status）。
    # 须在 _sos_tr merge（wc.py 下方 _sos_tr.update(phase_tr_ctx)）**之后**注入：
    # 否则 sc_anchor 会经 _sos_tr 泄漏给 _detect_sos/_detect_backup 复检（查 Agent 复核）。
    _unified_sc_anchor = _find_sc_anchor(
        bars,
        event_tr_ctx,
        timeframe=timeframe,
        is_index=is_index,
        include_failed=True,
    )
    if _unified_sc_anchor is not None:
        phase_tr_ctx["sc_anchor"] = _unified_sc_anchor

    phase = _detect_phase(
        bars,
        signals_dict,
        _phase_lookback=_phase_lb,
        tr_ctx=phase_tr_ctx,
        timeframe=timeframe,
        is_index=is_index,
    )

    # 周线 RS：仅修正 phase_confidence_delta，不改 phase；日线显式 disabled
    rs_fields: dict[str, Any] = {}
    if timeframe == "weekly" and symbol:
        from trader_shared.wyckoff_rs import compute_and_apply_weekly_rs

        phase, rs_fields = compute_and_apply_weekly_rs(
            bars,
            phase,
            signals_dict,
            symbol,
            index_weekly_bars=index_weekly_bars,
        )
    elif timeframe != "weekly":
        rs_fields = {
            "rs_label": "neutral",
            "rs_gate": "disabled",
            "rs_confidence_delta": 0.0,
            "rs_note": "日线不接 RS",
        }

    # B: 跨日持久化状态机 — 加载旧状态、过渡、存储
    # use_persisted_phase=False 时（如中线威科夫）跳过持久化，直接返回本次
    # K 线的即时推断，避免「只进不退」状态机掩盖当前周期的真实阶段。
    # Phase A 破位失败：强制落下 none（S-A5），禁止 none→黏回健康「停止：SC+AR」。
    if use_persisted_phase:
        _gate_reason = str(phase.get("phase_tr_gate_reason") or "")
        _force_clear = _gate_reason == "phase_a_failed"
        _detect_meta = {
            "spring_premature": bool(phase.get("spring_premature")),
            "upthrust_premature": bool(phase.get("upthrust_premature")),
            "phase_tr_gated": bool(phase.get("phase_tr_gated", False)),
            "phase_tr_gate_reason": _gate_reason,
        }
        old_state = _load_phase_state(symbol, timeframe)
        new_phase_state = _transition_phase(
            old_state,
            phase["phase"],
            phase["phase_label"],
            phase.get("phase_confidence_delta", 0.0),
            force_apply_none=_force_clear,
        )
        _save_phase_state(symbol, timeframe, new_phase_state)
        # 用过渡后状态覆盖瞬时推断；保留门控/孤立信号元数据（过渡态不含这些键）
        phase = {**new_phase_state, **_detect_meta}

    # 原典专名灯（不进阶段机 / 不抬 L2/L3）：跳溪 + 止跌量
    jac = _detect_jump_across_creek(
        bars,
        tr_ctx=phase_tr_ctx,
        ar_high=ar.get("ar_high") if ar.get("ar_signal") else phase_a_range.get("ar_high"),
        sos_signal=bool(sos.get("sos_signal")),
        bu_signal=bool(bu.get("bu_signal")),
        phase=str(phase.get("phase") or ""),
    )
    stopping_vol = _detect_stopping_volume(bars, tr_ctx=phase_tr_ctx)
    cm = _classify_cm_mode(
        phase=str(phase.get("phase") or ""),
        signals={
            **signals_dict,
            "jac_signal": bool(jac.get("jac_signal")),
            "stopping_volume_signal": bool(stopping_vol.get("stopping_volume_signal")),
            "phase": str(phase.get("phase") or ""),
        },
    )

    # P3-1: VSA 量价幅度分析
    vsa = _detect_effort_vs_result(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bc["bc_signal"]:
        parts.append(f"购买高潮: {bc['bc_reason']}")
    if phase_a_range.get("status") == "failed":
        parts.append(phase_a_range.get("fail_reason") or "Phase A 失败：有效跌破 SC 未收回")
    elif sc["sc_signal"]:
        parts.append(f"卖力高潮: {sc['sc_reason']}")
    if sow["sow_signal"]:
        parts.append(f"弱势信号: {sow['sow_reason']}")
    elif sow.get("sow_intraday_warn"):
        parts.append(f"弱势警告(不计分): {sow['sow_reason']}")
    if ar["ar_signal"]:
        parts.append(f"自动反弹: {ar['ar_reason']}")
    if are["are_signal"]:
        parts.append(f"自动回落: {are['are_reason']}")
    if sos["sos_signal"]:
        parts.append(f"强势信号: {sos['sos_reason']}")
    if spring_test["spring_test_signal"] or st["st_signal"]:
        parts.append(f"Spring确认: {spring_test.get('spring_test_reason') or st.get('st_reason')}")
    if st_sc["secondary_test_sc_signal"]:
        parts.append(f"SC二次测试: {st_sc['secondary_test_sc_reason']}")
    if lps["lps_signal"]:
        parts.append(f"最后支撑: {lps['lps_reason']}")
    if lpsy["lpsy_signal"]:
        parts.append(f"最后供应点: {lpsy['lpsy_reason']}")
    if ps.get("ps_signal"):
        parts.append(f"初步止跌: {ps['ps_reason']}")
    if psy.get("psy_signal"):
        parts.append(f"初步供应: {psy['psy_reason']}")
    if bu.get("bu_signal"):
        parts.append(f"备份买: {bu['bu_reason']}")
    if utad.get("utad_signal"):
        parts.append(f"UTAD: {utad['utad_reason']}")
    if jac.get("jac_signal"):
        parts.append(f"跳溪: {jac['jac_reason']}")
    if stopping_vol.get("stopping_volume_signal"):
        parts.append(f"止跌量: {stopping_vol['stopping_volume_reason']}")
    if cm.get("cm_mode") and cm.get("cm_mode") != "none" and cm.get("cm_note"):
        parts.append(f"CM:{cm['cm_note']}")
    if bearish_div and bullish_div:
        parts.append("量价信号冲突，无法确定方向")
    elif bearish_div:
        parts.append("看空量价背离")
    elif bullish_div:
        parts.append("看多量价背离")
    if vsa["effort_no_result"]:
        parts.append("高量窄幅（努力无结果）")
    if vsa["no_supply"]:
        parts.append("低量窄幅（供应耗尽）")
    if compression["compression_signal"]:
        parts.append(f"压缩蓄势: {compression['compression_reason']}")
    if trend_pullback["trend_pullback_signal"]:
        parts.append(f"趋势回踩: {trend_pullback['trend_pullback_reason']}")
    if trend_rally["trend_rally_signal"]:
        parts.append(f"趋势反抽: {trend_rally['trend_rally_reason']}")
    if ce.get("cause_effect_up_target") is not None:
        parts.append(
            f"因果目标↑{ce['cause_effect_up_target']}/↓{ce['cause_effect_down_target']}"
        )
    if not parts:
        parts.append("无明显威科夫信号")

    result = {
        "spring_signal": spring["spring_signal"],
        "spring_reason": spring["spring_reason"],
        "spring_price": round(spring["spring_price"], 2) if spring["spring_signal"] else None,
        "upthrust_signal": upthrust["upthrust_signal"],
        "upthrust_reason": upthrust["upthrust_reason"],
        "upthrust_price": round(upthrust["upthrust_price"], 2) if upthrust["upthrust_signal"] else None,
        # P0-4 Spring/Upthrust 真假分级
        "spring_strength": spring.get("spring_strength"),
        "spring_strength_note": spring.get("spring_strength_note"),
        "spring_depth_pct": spring.get("spring_depth_pct"),
        "spring_vol_ratio": spring.get("spring_vol_ratio"),
        "spring_reclaim_ratio": spring.get("spring_reclaim_ratio"),
        "upthrust_strength": upthrust.get("upthrust_strength"),
        "upthrust_strength_note": upthrust.get("upthrust_strength_note"),
        "upthrust_depth_pct": upthrust.get("upthrust_depth_pct"),
        "upthrust_vol_ratio": upthrust.get("upthrust_vol_ratio"),
        "upthrust_reclaim_ratio": upthrust.get("upthrust_reclaim_ratio"),
        "bc_signal": bc["bc_signal"],
        "bc_reason": bc["bc_reason"],
        "bc_price": round(bc["bc_price"], 2) if bc["bc_signal"] else None,
        "sow_signal": sow["sow_signal"],
        "sow_intraday_warn": bool(sow.get("sow_intraday_warn")),
        "sow_reason": sow["sow_reason"],
        "sow_price": (
            round(sow["sow_price"], 2)
            if (sow["sow_signal"] or sow.get("sow_intraday_warn")) and sow.get("sow_price")
            else None
        ),
        "sc_signal": sc["sc_signal"],
        "sc_reason": sc["sc_reason"],
        # sc_price / sc_low = SC 棒最低价 SSOT（勿被 ST refine 覆盖）
        "sc_price": round(sc["sc_price"], 2) if sc["sc_signal"] else None,
        "sc_low": (
            round(float(sc["sc_low"]), 2)
            if sc.get("sc_signal") and sc.get("sc_low") is not None
            else (phase_a_range.get("sc_low") if sc.get("sc_signal") else None)
        ),
        "sc_low_refined": phase_a_range.get("sc_low_refined"),
        "sc_bar_idx": sc.get("sc_bar_idx"),
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        # 新增信号
        "ar_signal": ar["ar_signal"],
        "ar_reason": ar["ar_reason"],
        "ar_price": round(ar["ar_price"], 2) if ar["ar_signal"] else None,
        "ar_high": ar.get("ar_high") if ar.get("ar_signal") else None,
        "ar_bar_idx": ar.get("ar_bar_idx"),
        "ar_volume_soft": bool(ar.get("ar_volume_soft")),
        "are_signal": are["are_signal"],
        "are_reason": are["are_reason"],
        "are_price": round(are["are_price"], 2) if are["are_signal"] else None,
        "sos_signal": sos["sos_signal"],
        "sos_reason": sos["sos_reason"],
        "sos_price": round(sos["sos_price"], 2) if sos["sos_signal"] else None,
        "sos_kind": sos.get("sos_kind"),  # climb | thrust | None；法源 wyckoff-sos-single-day-handoff
        "st_signal": st["st_signal"],
        "st_reason": st["st_reason"],
        "st_price": round(st["st_price"], 2) if st["st_signal"] else None,
        # P0-A: Test of Spring 与 st_* 双写（打分只计 st 一次）
        "spring_test_signal": spring_test["spring_test_signal"],
        "spring_test_reason": spring_test["spring_test_reason"],
        "spring_test_price": (
            round(spring_test["spring_test_price"], 2)
            if spring_test["spring_test_signal"] and spring_test.get("spring_test_price") is not None
            else None
        ),
        "lps_signal": lps["lps_signal"],
        "lps_reason": lps["lps_reason"],
        "lps_price": round(lps["lps_price"], 2) if lps["lps_signal"] else None,
        "lpsy_signal": lpsy["lpsy_signal"],
        "lpsy_reason": lpsy["lpsy_reason"],
        "lpsy_price": round(lpsy["lpsy_price"], 2) if lpsy["lpsy_signal"] and lpsy.get("lpsy_price") is not None else None,
        # 原典补齐 PS/PSY/BU/UTAD + 因果目标
        "ps_signal": bool(ps.get("ps_signal")),
        "ps_reason": ps.get("ps_reason"),
        "ps_price": ps.get("ps_price"),
        "psy_signal": bool(psy.get("psy_signal")),
        "psy_reason": psy.get("psy_reason"),
        "psy_price": psy.get("psy_price"),
        "bu_signal": bool(bu.get("bu_signal")),
        "bu_reason": bu.get("bu_reason"),
        "bu_price": bu.get("bu_price"),
        "utad_signal": bool(utad.get("utad_signal")),
        "utad_reason": utad.get("utad_reason"),
        "utad_price": utad.get("utad_price"),
        # Jump Across the Creek / Stopping Volume（专名灯；JAC 不计分）
        "jac_signal": bool(jac.get("jac_signal")),
        "jac_reason": jac.get("jac_reason"),
        "jac_price": jac.get("jac_price"),
        "jac_bar_idx": jac.get("jac_bar_idx"),
        "stopping_volume_signal": bool(stopping_vol.get("stopping_volume_signal")),
        "stopping_volume_reason": stopping_vol.get("stopping_volume_reason"),
        "stopping_volume_price": stopping_vol.get("stopping_volume_price"),
        "stopping_volume_bar_idx": stopping_vol.get("stopping_volume_bar_idx"),
        # CM 行为模式（轻量映射；不改 phase）
        "cm_mode": cm.get("cm_mode") or "none",
        "cm_note": cm.get("cm_note") or "",
        "cause_effect_up_target": ce.get("cause_effect_up_target"),
        "cause_effect_down_target": ce.get("cause_effect_down_target"),
        "cause_effect_range": ce.get("cause_effect_range"),
        "cause_effect_note": ce.get("cause_effect_note"),
        "pnf_box_size": ce.get("pnf_box_size"),
        "pnf_columns": ce.get("pnf_columns"),
        "pnf_method": ce.get("pnf_method"),
        # P0-1: 弹簧量能分级（signal=False 时仍透传 high_vol_warning 等审计字段）
        "spring_vol_class": spring.get("spring_vol_class")
        if spring.get("spring_vol_class") is not None
        else ("normal" if spring["spring_signal"] else None),
        # P1-1: 阶段状态机
        "phase": phase["phase"],
        "phase_label": phase["phase_label"],
        "phase_confidence_delta": phase.get("phase_confidence_delta", 0.0),
        # 五阶段机原典串联：孤立信号标注
        "spring_premature": phase.get("spring_premature", False),
        "upthrust_premature": phase.get("upthrust_premature", False),
        # P0-B: TR 质量门控透出
        "phase_tr_gated": bool(phase.get("phase_tr_gated", False)),
        "phase_tr_gate_reason": phase.get("phase_tr_gate_reason") or "",
        # P3-1: VSA 量价幅度分析
        "effort_no_result": vsa["effort_no_result"],
        "no_supply": vsa["no_supply"],
        # P2/P3: 新增信号
        "compression_signal": compression["compression_signal"],
        "compression_reason": compression["compression_reason"],
        "compression_price": compression["compression_price"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
        "trend_pullback_reason": trend_pullback["trend_pullback_reason"],
        "trend_pullback_price": trend_pullback["trend_pullback_price"],
        "trend_rally_signal": trend_rally["trend_rally_signal"],
        "trend_rally_reason": trend_rally["trend_rally_reason"],
        "trend_rally_price": trend_rally["trend_rally_price"],
        # P0-3: TR 识别层透出（established 时 tr_* 优先种子箱 overlay）
        "tr_upper": (phase_tr_ctx or tr_ctx or {}).get("tr_upper"),
        "tr_lower": (phase_tr_ctx or tr_ctx or {}).get("tr_lower"),
        "tr_baseline_volume": (phase_tr_ctx or tr_ctx or {}).get("tr_baseline_volume"),
        "tr_width": (phase_tr_ctx or tr_ctx or {}).get("tr_width"),
        "tr_amplitude_pct": (phase_tr_ctx or tr_ctx or {}).get("tr_amplitude_pct"),
        "tr_quality": (phase_tr_ctx or tr_ctx or {}).get("tr_quality"),
        "tr_in_range": (phase_tr_ctx or tr_ctx or {}).get("in_tr"),
        "tr_upper_ref": (phase_tr_ctx or {}).get("tr_upper_ref"),
        "tr_lower_ref": (phase_tr_ctx or {}).get("tr_lower_ref"),
        "tr_seed_source": (
            (phase_tr_ctx or {}).get("tr_seed_source")
            or ("percentile" if tr_ctx else None)
        ),
        # P0-5: 事件簇确认透出
        "accumulation_confirmed": cluster["accumulation_confirmed"],
        "distribution_confirmed": cluster["distribution_confirmed"],
        "accumulation_failed": cluster["accumulation_failed"],
        "distribution_failed": cluster["distribution_failed"],
        "cluster_quality": cluster["cluster_quality"],
        "cluster_confidence": cluster["cluster_confidence"],
        "cluster_reason": cluster["cluster_reason"],
        # P1: Phase A 区间边界（SC low + AR high）
        "phase_a_status": phase_a_range["status"],
        "phase_a_range": phase_a_range,
        "secondary_test_sc_signal": st_sc["secondary_test_sc_signal"],
        "secondary_test_sc_reason": st_sc["secondary_test_sc_reason"],
        "secondary_test_sc_price": st_sc.get("secondary_test_sc_price"),
        "secondary_test_sc_bar_idx": st_sc.get("secondary_test_sc_bar_idx"),
        "st_sc_low": st_sc.get("st_sc_low"),
        "secondary_test_sc_low": st_sc.get("st_sc_low"),
        # L0–L3 TR 成熟度（顶栏必有；与 phase_a_status 并存）
        "tr_maturity": maturity["tr_maturity"],
        "tr_maturity_reason": maturity["tr_maturity_reason"],
        "measure_allowed": bool(maturity["measure_allowed"]),
        "box_display_mode": maturity["box_display_mode"],
        "wyckoff_summary": "；".join(parts),
        # 周线 RS（仅置信修正；缺省 neutral）
        "rs_score": rs_fields.get("rs_score"),
        "rs_label": rs_fields.get("rs_label", "neutral"),
        "rs_index": rs_fields.get("rs_index", ""),
        "rs_index_label": rs_fields.get("rs_index_label", ""),
        "rs_note": rs_fields.get("rs_note", ""),
        "rs_gate": rs_fields.get("rs_gate", ""),
        "rs_window_weeks": rs_fields.get("rs_window_weeks", 0),
        "rs_confidence_delta": rs_fields.get("rs_confidence_delta", 0.0),
        "rs_stock_return": rs_fields.get("rs_stock_return"),
        "rs_index_return": rs_fields.get("rs_index_return"),
        "rs_relative_return": rs_fields.get("rs_relative_return"),
        "phase_confidence_delta_event": phase.get("phase_confidence_delta_event"),
    }
    if use_persisted_phase_a_anchor and str(symbol or "").strip():
        save_phase_a_anchor(symbol, timeframe, result.get("phase_a_range"), bars)
    return result

def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None, symbol: str = "") -> dict:
    """日线威科夫（短线侧兼容 / 插件日线轨）。

    注意：短线 fusion 第三席已是 VPF，本结果**不**进入 ``merge_decisions`` 加权；
    日线威科夫主要用于 ``calculate_wyckoff_score``（池/复盘）与兼容导出字段。
    中线展示读 ``wyckoff_strategy_midline``（周线独占）。
    """
    if not symbol and isinstance(quote, dict):
        symbol = str(
            quote.get("symbol") or quote.get("ts_code") or quote.get("code") or ""
        ).strip()
    result = wyckoff_analysis(bars, symbol=symbol)
    if isinstance(result, dict):
        result = {**result, "timeframe": "daily"}
    return {"wyckoff": result}

def wyckoff_strategy_midline(
    current: float,
    weekly_bars: list[dict] | None = None,
    daily_bars: list[dict] | None = None,  # 保留兼容签名；中线威科夫周线独占，不再用于回退兜底
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str = "",
) -> dict:
    """中线威科夫独立判断：仅周K（周线不足则不参与中线定论，不回退日线）。

    与日线 fusion 路径分离：报告「威科夫：…」定性用本结果。
    """
    weekly_bars = weekly_bars or []
    if not symbol and isinstance(quote, dict):
        symbol = str(quote.get("symbol") or quote.get("code") or "").strip()
    # 中线威科夫周线独占：周线不足直接返回 insufficient，不参与 🧭 中线定论，
    # 不再回退日线（避免日线噪音稀释中线战略依据，违反 output-template.md:94）。
    if len(weekly_bars) < WYCKOFF_MIN_BARS:
        return {
            "wyckoff": {
                "timeframe": "insufficient",
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "wyckoff_summary": "周线数据不足，中线威科夫不参与定论",
            }
        }
    result = wyckoff_analysis(weekly_bars, symbol=symbol, timeframe="weekly", use_persisted_phase=False)
    if isinstance(result, dict):
        result = {**result, "timeframe": "weekly"}
    return {"wyckoff": result}

def calculate_wyckoff_score(bars: list[dict], symbol: str = "", analysis: dict | None = None) -> dict:
    """基于 Wyckoff 信号规则的独立打分函数。

    先调用 wyckoff_analysis() 获取 5 路信号，按权重累加 raw_score，
    再线性映射到 0-100 分数（50 为中性）。

    Args:
        bars: 日线 K 线数据列表，最少 WYCKOFF_MIN_BARS 根。
        analysis: 可选，已计算的 wyckoff_analysis 结果，避免重复调用。

    Returns:
        {
            "score": int,          # 0-100 分数
            "raw": int,            # 加权累加原始分（范围约 -80 ~ +80）
            "signals": list[str],  # 参与打分的信号明细
            "summary": str,        # 一句话总结
        }
    """
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "score": 50,
            "raw": 0,
            "signals": [],
            "summary": "K线数据不足，无法打分",
        }

    # 打分应为纯函数：analysis 缺失时重算，但不触发 phase 持久化写盘
    analysis = analysis if analysis is not None else wyckoff_analysis(
        bars, symbol=symbol, use_persisted_phase=False
    )

    raw = 0
    signals: list[str] = []
    suppress = _resolve_score_conflicts(analysis)
    if suppress:
        signals.append("互斥抑制:" + ",".join(sorted(suppress)))

    spring = analysis.get("spring_signal") and "spring_signal" not in suppress
    bullish_div = analysis.get("bullish_volume_divergence") and "bullish_volume_divergence" not in suppress
    bearish_div = analysis.get("bearish_volume_divergence") and "bearish_volume_divergence" not in suppress
    upthrust = analysis.get("upthrust_signal") and "upthrust_signal" not in suppress
    bc = analysis.get("bc_signal")
    sow = analysis.get("sow_signal") and "sow_signal" not in suppress
    spring_vol_class = analysis.get("spring_vol_class")
    sc_on = analysis.get("sc_signal") and "sc_signal" not in suppress
    lps_on = analysis.get("lps_signal") and "lps_signal" not in suppress
    lpsy_on = analysis.get("lpsy_signal") and "lpsy_signal" not in suppress

    # 1. Spring — 最强看多信号；孤立/过早、高量警告、弱弹簧（缩量无承接）均降权减半
    spring_strength = analysis.get("spring_strength")
    spring_deweight = bool(
        analysis.get("spring_premature")
        or spring_vol_class == "high_vol_warning"
        or spring_strength == "weak"
    )
    if spring:
        spring_pts = WYCKOFF_SCORE_SPRING
        if analysis.get("spring_premature"):
            spring_pts = spring_pts // 2
            signals.append(f"Spring(孤立/过早,降权) +{spring_pts}")
        elif spring_vol_class == "high_vol_warning":
            spring_pts = spring_pts // 2  # 高量 Spring 分数减半（注入 analysis 时）
            signals.append(f"Spring(高量降权) +{spring_pts}")
        elif spring_strength == "weak":
            spring_pts = spring_pts // 2
            signals.append(f"Spring(弱/缩量无承接,降权) +{spring_pts}")
        else:
            signals.append(f"Spring +{spring_pts}")
        raw += spring_pts

    # 2. Spring + 看多背离额外加分；与 Spring 本体同步降权
    if spring and bullish_div:
        bonus = WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS
        if spring_deweight:
            bonus = bonus // 2  # 孤立/高量/弱弹簧时背离加成减半（0 当 1 时 floor 为 0）
            if bonus > 0:
                signals.append(f"Spring×看多背离(降权) +{bonus}")
            else:
                signals.append("Spring×看多背离(降权) +0")
        else:
            signals.append(f"Spring×看多背离 +{bonus}")
        raw += bonus

    # 3. 独立看多背离
    if bullish_div and not spring:
        raw += WYCKOFF_SCORE_BULLISH_DIV
        signals.append(f"看多背离 +{WYCKOFF_SCORE_BULLISH_DIV}")

    # 4. Upthrust — 假突破派发；孤立/过早 UT（缺 Phase B 背景）降权为噪声，分数减半
    if upthrust:
        ut_pts = WYCKOFF_SCORE_UT
        if analysis.get("upthrust_premature"):
            ut_pts = ut_pts // 2
            signals.append(f"Upthrust(孤立/过早,降权) {ut_pts}")
        else:
            signals.append(f"Upthrust {ut_pts}")
        raw += ut_pts

    # 5. 看空背离
    if bearish_div and not bullish_div:
        raw += WYCKOFF_SCORE_BEARISH_DIV
        signals.append(f"看空背离 {WYCKOFF_SCORE_BEARISH_DIV}")

    # 6. Buying Climax — 天量滞涨
    if bc:
        raw += WYCKOFF_SCORE_BC
        signals.append(f"购买高潮 {WYCKOFF_SCORE_BC}")

    # 7. Sign of Weakness — 放量跌破
    if sow:
        raw += WYCKOFF_SCORE_SOW
        signals.append(f"弱势信号 {WYCKOFF_SCORE_SOW}")

    # ── 新增经典信号 ──

    # 8. AR (Automatic Rally) — SC 后自动反弹
    if analysis.get("ar_signal") and "ar_signal" not in suppress:
        raw += WYCKOFF_SCORE_AR
        signals.append(f"AR 反弹 +{WYCKOFF_SCORE_AR}")

    # 8b. ARE (Automatic Reaction) — BC 后自动回落（对称 AR）
    if analysis.get("are_signal") and "are_signal" not in suppress:
        raw += WYCKOFF_SCORE_ARE
        signals.append(f"ARE 回落 {WYCKOFF_SCORE_ARE}")

    # 9. SOS (Sign of Strength) — 强势突破
    if analysis.get("sos_signal"):
        raw += WYCKOFF_SCORE_SOS
        signals.append(f"SOS +{WYCKOFF_SCORE_SOS}")

    # 10. Spring确认 / ST — 同源只计一次（spring_test_* 与 st_* 双写）
    if analysis.get("st_signal") or analysis.get("spring_test_signal"):
        raw += WYCKOFF_SCORE_ST
        signals.append(f"Spring确认 +{WYCKOFF_SCORE_ST}")

    # 11. LPS (Last Point of Support) — 最后支撑点
    if lps_on:
        raw += WYCKOFF_SCORE_LPS
        signals.append(f"LPS +{WYCKOFF_SCORE_LPS}")

    # 12. P2: Compression — 压缩蓄势
    if analysis.get("compression_signal"):
        raw += WYCKOFF_SCORE_COMPRESSION
        signals.append(f"压缩蓄势 +{WYCKOFF_SCORE_COMPRESSION}")

    # 13. P3: Trend Pullback — 趋势回踩（多）
    if analysis.get("trend_pullback_signal") and "trend_pullback_signal" not in suppress:
        raw += WYCKOFF_SCORE_TREND_PB
        signals.append(f"趋势回踩 +{WYCKOFF_SCORE_TREND_PB}")

    # 13b. Trend Rally — 趋势反抽（空，对称回踩）
    if analysis.get("trend_rally_signal") and "trend_rally_signal" not in suppress:
        raw += WYCKOFF_SCORE_TREND_RALLY
        signals.append(f"趋势反抽 {WYCKOFF_SCORE_TREND_RALLY}")

    # 14. SC (Selling Climax) — 卖力高潮，看多
    if sc_on:
        raw += WYCKOFF_SCORE_AR  # SC 的看多强度与 AR 同级（+10）
        signals.append(f"SC +{WYCKOFF_SCORE_AR}")

    # 15. LPSY — 已在 analysis 层做派发背景门控；此处再防互斥
    if lpsy_on:
        raw += WYCKOFF_SCORE_LPSY
        signals.append(f"LPSY {WYCKOFF_SCORE_LPSY}")

    # 16. PS / PSY / BU / UTAD
    if analysis.get("ps_signal"):
        raw += WYCKOFF_SCORE_PS
        signals.append(f"PS +{WYCKOFF_SCORE_PS}")
    if analysis.get("psy_signal"):
        raw += WYCKOFF_SCORE_PSY
        signals.append(f"PSY {WYCKOFF_SCORE_PSY}")
    if analysis.get("bu_signal"):
        raw += WYCKOFF_SCORE_BU
        signals.append(f"BU +{WYCKOFF_SCORE_BU}")
    if analysis.get("utad_signal"):
        raw += WYCKOFF_SCORE_UTAD
        signals.append(f"UTAD {WYCKOFF_SCORE_UTAD}")

    # 16b. Stopping Volume — 与 SC 同亮时不计分（防双计）；JAC 永不计分
    if analysis.get("stopping_volume_signal") and not sc_on:
        raw += WYCKOFF_SCORE_STOPPING_VOLUME
        signals.append(f"止跌量 +{WYCKOFF_SCORE_STOPPING_VOLUME}")

    # ── P3-1: VSA 量价幅度修正 ──
    effort_no_result = analysis.get("effort_no_result", False)
    no_supply = analysis.get("no_supply", False)

    # Spring + 低量窄幅（供应耗尽）→ 额外加分
    if spring and no_supply:
        raw += 5
        signals.append("Spring×供应耗尽 +5")

    # UT + 高量窄幅（努力无结果）→ 额外扣分（派发确认）
    if upthrust and effort_no_result:
        raw -= 5
        signals.append("UT×努力无结果 -5")

    # SOS + 高量窄幅 → SOS 不可靠，取消加分
    if analysis.get("sos_signal") and effort_no_result:
        raw -= WYCKOFF_SCORE_SOS
        signals.append(f"SOS×努力无结果 撤销 +{WYCKOFF_SCORE_SOS}")

    # VSA 单独修正：低量窄幅（供应耗尽）独立看多
    if no_supply and not spring and not analysis.get("sos_signal"):
        raw += 5
        signals.append("供应耗尽 +5")
    # VSA 单独修正：高量窄幅（努力无结果）独立看空
    if effort_no_result and not upthrust and not analysis.get("sos_signal"):
        raw -= 5
        signals.append("努力无结果 -5")

    # ── P0-5 事件簇确认打分：顺序确认的簇比孤立信号更可靠 ──
    # 消费面：仅本函数 score → final_pool / review 排序；
    # 不进短线 fusion（第三席已是 VPF，见 fusion_core.merge_decisions）。
    if analysis.get("accumulation_confirmed"):
        raw += WYCKOFF_SCORE_CLUSTER_CONFIRM
        signals.append(f"积累确认(Spring→SOS) +{WYCKOFF_SCORE_CLUSTER_CONFIRM}")
    if analysis.get("distribution_confirmed"):
        raw += WYCKOFF_SCORE_CLUSTER_DISTRIB
        signals.append(f"派发确认(Upthrust→SOW) {WYCKOFF_SCORE_CLUSTER_DISTRIB}")
    # 失败簇：Spring 后接 SOW → 假突破实为派发，强看空（覆盖孤立 Spring 的看多分）
    if analysis.get("accumulation_failed"):
        raw += WYCKOFF_SCORE_CLUSTER_FAIL
        signals.append(f"积累失败(Spring→SOW) {WYCKOFF_SCORE_CLUSTER_FAIL}")
    # 失败簇：Upthrust 后接 SOS → 假派发实为吸筹，强看多
    if analysis.get("distribution_failed"):
        raw += -WYCKOFF_SCORE_CLUSTER_FAIL
        signals.append(f"派发失败(Upthrust→SOS) +{-WYCKOFF_SCORE_CLUSTER_FAIL}")

    # ── ① TR 质量接打分：干净 TR 中信号更可信，高质→加分、低质→向中性回拉 ──
    # 调整量 = (tr_quality - 0.5) * 2 * GAIN，封顶 ±GAIN。tr_quality=None(无TR)不调整。
    tr_quality = analysis.get("tr_quality")
    if tr_quality is not None:
        tr_adj = int(round((tr_quality - WYCKOFF_TR_QUALITY_NEUTRAL)
                           * 2.0 * WYCKOFF_SCORE_TR_QUALITY_GAIN))
        tr_adj = max(-WYCKOFF_SCORE_TR_QUALITY_GAIN, min(WYCKOFF_SCORE_TR_QUALITY_GAIN, tr_adj))
        if tr_adj != 0:
            raw += tr_adj
            signals.append(f"TR质量{tr_quality:.02f} {tr_adj:+d}")

    # ── 阶段置信度修正：phase_confidence_delta * 20 取整后微调 raw ──
    phase_delta = analysis.get("phase_confidence_delta") or 0.0
    try:
        phase_adj = int(round(float(phase_delta) * 20))
    except (TypeError, ValueError):
        phase_adj = 0
    if phase_adj:
        raw += phase_adj
        signals.append(f"阶段修正 {phase_adj:+d}")

    # 线性映射: raw ∈ [-MAX_ABS, +MAX_ABS] → score ∈ [0, 100]
    score = max(0, min(100, 50 + raw * 50 // WYCKOFF_SCORE_MAX_ABS))

    if score >= 70:
        summary = f"威科夫看多（{score}/100）"
    elif score >= 60:
        summary = f"威科夫偏多（{score}/100）"
    elif score <= 30:
        summary = f"威科夫看空（{score}/100）"
    elif score <= 40:
        summary = f"威科夫偏空（{score}/100）"
    else:
        summary = f"威科夫中性（{score}/100）"

    return {
        "score": score,
        "raw": raw,
        "signals": signals,
        "summary": summary,
    }

def _unwrap_wyckoff_dict(wyckoff: dict[str, Any] | None) -> dict[str, Any]:
    wyk = wyckoff if isinstance(wyckoff, dict) else {}
    if "wyckoff" in wyk and isinstance(wyk.get("wyckoff"), dict):
        return wyk["wyckoff"]
    return wyk


def _wyckoff_dir_label(d: int) -> str:
    if d > 0:
        return "偏多"
    if d < 0:
        return "偏空"
    return "中性"


def resolve_wyckoff_primary(
    wyckoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析当前主事件（展示用，不进 fusion 打分）。

    返回字段：
      status: event | none | insufficient | no_data
      code: 英文灯标（Spring / UT / SOS …；无事件为 —）
      cn_name: 中文短名（弹簧 / 假突破 …）
      main: 主句白话
      note: 补充说明
      direction: +1 / 0 / -1
      phase_label: 原 phase_label（可能空）
      timeframe: 原 timeframe
    """
    wyk = _unwrap_wyckoff_dict(wyckoff)
    phase = str(wyk.get("phase_label") or "")
    tf = wyk.get("timeframe")

    empty = {
        "status": "no_data",
        "code": "—",
        "cn_name": "无",
        "main": "数据不足",
        "note": "中性",
        "direction": 0,
        "phase_label": phase,
        "timeframe": tf,
    }

    if tf == "insufficient":
        return {
            **empty,
            "status": "insufficient",
            "code": "—",
            "cn_name": "不足",
            "main": "周线不足",
            "note": "不参与定论",
            "direction": 0,
        }

    # 优先级与 format_wyckoff_oneline 一致（含 UTAD/BU 优先于 Spring）
    if str(wyk.get("phase_a_status") or "").strip() == "failed":
        # 人话直接进面板（oneline / view）；写「失效」不写「失败」（R-F* / §1.2.6）
        return {
            "status": "event",
            "code": "PhaseAFail",
            "cn_name": "破位失效",
            "main": "Phase A 失效，本波无新SC",
            "note": "失效结构，不按健康吸筹推进",
            "direction": -1,
            "phase_label": phase,
            "timeframe": tf,
        }

    code = cn = main = note = None
    d = 0

    # 日线短波侧：派发波优先暴露 LPSY/SOW/UTAD，避免 BC 永远盖住
    try:
        from trader_shared.wyckoff_view import infer_daily_short_wave

        _wave = infer_daily_short_wave(wyk)
        _side = str(_wave.get("side") or "")
    except Exception:
        _wave, _side = {}, ""

    if _side == "distribution":
        if wyk.get("utad_signal"):
            code, cn, main, note, d = "UTAD", "派发末上冲", "派发末上冲回落", "警惕破位下行", -1
        elif wyk.get("lpsy_signal"):
            code, cn, main, note, d = "LPSY", "最后供应点", "反弹受阻缩量", "最后供应，反抽别追", -1
        elif wyk.get("sow_signal"):
            code, cn, main, note, d = "SOW", "弱势下跌", "放量跌破支撑", "弱势确认，防守优先", -1
        elif wyk.get("upthrust_signal"):
            code, cn = "UT", "假突破"
            if wyk.get("upthrust_premature"):
                main, note, d = "冲高回落假突破", "孤立/过早信号，缺派发背景，当噪声看待", 0
            else:
                main, note, d = "冲高回落假突破", "上方试盘失败，结构偏顶", -1
        elif wyk.get("bc_signal"):
            code, cn, main, note, d = "BC", "买力高潮", "高位放量滞涨", "购买高潮迹象，注意见好就收", -1
        elif wyk.get("are_signal"):
            code, cn, main, note, d = "ARE", "自动回落", "高潮后自动回落", "派发侧回落观察", -1

    if code is None and wyk.get("utad_signal"):
        code, cn, main, note, d = "UTAD", "派发末上冲", "派发末上冲回落", "警惕破位下行", -1
    elif code is None and wyk.get("jac_signal"):
        code, cn, main, note, d = (
            "JAC", "跳溪", "强势越过溪并站稳", "专名灯，非单独开仓", 1
        )
    elif wyk.get("bu_signal"):
        code, cn, main, note, d = "BU", "回踩确认", "强势后缩量回踩", "趋势启动区试探", 1
    elif wyk.get("spring_signal"):
        code, cn = "Spring", "弹簧"
        vol = wyk.get("spring_vol_class") or "normal"
        strength = wyk.get("spring_strength")
        if wyk.get("spring_premature"):
            main, note, d = "低位假跌破后收回", "孤立/过早信号，缺蓄势背景，当噪声看待", 0
        elif vol == "high_vol_warning":
            main, note, d = "低位跌破后收回", "放量跌破，也可能是真破位，信号偏弱", 1
        elif vol == "low_vol_confirm":
            main, note, d = "低位假跌破后收回", "更像洗盘，缩量较可信", 1
        else:
            main, note, d = "低位假跌破后收回", "更像洗盘吸筹", 1
        if strength == "strong" and d > 0 and vol != "high_vol_warning":
            note = note + "，强度偏高"
        elif strength == "weak" and d > 0:
            note = note + "，强度偏弱"
        elif strength == "failure":
            main, note, d = "低位跌破未收回", "刺穿失败，偏破位风险", -1
    elif wyk.get("sos_signal"):
        code, cn, main, note, d = "SOS", "强势上攻", "连续放量上攻", "多头发力，趋势转强迹象", 1
    elif wyk.get("upthrust_signal"):
        code, cn = "UT", "假突破"
        if wyk.get("upthrust_premature"):
            main, note, d = "冲高回落假突破", "孤立/过早信号，缺派发背景，当噪声看待", 0
        else:
            main, note, d = "冲高回落假突破", "上方试盘失败，结构偏顶", -1
            ut_str = wyk.get("upthrust_strength")
            if ut_str == "strong":
                note = note + "，强度偏高"
            elif ut_str == "weak":
                note = note + "，强度偏弱"
            elif ut_str == "failure":
                note, d = "上冲未回落，突破可能有效", 1
    elif wyk.get("bc_signal"):
        code, cn, main, note, d = "BC", "买力高潮", "高位放量滞涨", "购买高潮迹象，注意见好就收", -1
    elif wyk.get("sow_signal"):
        code, cn, main, note, d = "SOW", "弱势下跌", "放量跌破支撑", "弱势确认，防守优先", -1
    elif wyk.get("sow_intraday_warn"):
        code, cn, main, note, d = "SOWw", "弱势警告", "日内刺穿支撑后收回", "仅警告，未收盘确认，不计分", 0
    elif wyk.get("ar_signal"):
        code, cn, main, note, d = (
            "AR", "自动反弹", "SC后快速反弹", "钉潜在上沿，仅反弹不能当反转", 1
        )
    elif wyk.get("are_signal"):
        code, cn, main, note, d = "ARE", "自动回落", "BC后快速回落", "仅回落，还不能当反转空", -1
    elif wyk.get("sc_signal"):
        code, cn, main, note, d = "SC", "卖力高潮", "天量宽幅下跌", "卖力高潮，抛压宣泄后可能止跌", 1
    elif wyk.get("stopping_volume_signal"):
        code, cn, main, note, d = (
            "SV", "止跌量", "下跌末段放量收回", "卖压被吸收，可与SC同亮", 1
        )
    elif wyk.get("spring_test_signal") or wyk.get("st_signal"):
        code, cn, main, note, d = (
            "SpringTest", "Spring确认", "Spring后缩量回测", "确认测试有效，非笼统ST", 1
        )
    elif wyk.get("lps_signal"):
        code, cn, main, note, d = "LPS", "最后支撑", "突破后缩量回踩", "回踩不破，仍偏强", 1
    elif wyk.get("lpsy_signal"):
        code, cn, main, note, d = "LPSY", "最后供应", "反弹受阻缩量", "最后供应点，警惕破位下行", -1
    elif wyk.get("ps_signal"):
        code, cn, main, note, d = "PS", "初步支撑", "低位放量止跌", "尚待 SC/Spring 确认", 1
    elif wyk.get("psy_signal"):
        code, cn, main, note, d = "PSY", "初步供应", "高位放量滞涨", "尚待 BC/UT 确认", -1
    elif wyk.get("compression_signal"):
        code, cn, main, note, d = "Compression", "压缩蓄势", "压缩蓄势", "振幅收窄+量能枯竭，突破在即", 1
    elif wyk.get("trend_pullback_signal"):
        code, cn, main, note, d = "TrendPullback", "趋势回踩", "趋势回踩", "回踩不破均线，趋势延续", 1
    elif wyk.get("trend_rally_signal"):
        code, cn, main, note, d = "TrendRally", "趋势反抽", "趋势反抽", "反抽不过均线，跌势延续", -1
    elif wyk.get("bullish_volume_divergence") and not wyk.get("bearish_volume_divergence"):
        code, cn, main, note, d = "BullDiv", "看多背离", "下跌缩量", "抛压减轻，有止跌迹象", 1
    elif wyk.get("bearish_volume_divergence") and not wyk.get("bullish_volume_divergence"):
        code, cn, main, note, d = "BearDiv", "看空背离", "上涨缩量", "上攻乏力，慎追高", -1
    else:
        has_run = bool(
            tf
            or wyk.get("wyckoff_summary")
            or any(k.endswith("_signal") or k.endswith("_reason") for k in wyk.keys())
        )
        if has_run:
            return {
                "status": "none",
                "code": "—",
                "cn_name": "无事件",
                "main": "暂无事件",
                "note": "中性",
                "direction": 0,
                "phase_label": phase,
                "timeframe": tf,
            }
        return empty

    return {
        "status": "event",
        "code": code,
        "cn_name": cn,
        "main": main,
        "note": note,
        "direction": d,
        "phase_label": phase,
        "timeframe": tf,
    }


def format_wyckoff_event_light(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
) -> str:
    """短线报告：英文灯 + 中文括号解释（不参与评分）。

    例：
      状态：Spring（弹簧）· 低位假跌破后收回（更像洗盘）· 偏多
      状态：— · 暂无事件 · 中性
    """
    info = resolve_wyckoff_primary(wyckoff)
    if info["status"] == "insufficient":
        return "状态：— · 数据不足 · 不参与"
    if info["status"] == "no_data":
        return "状态：— · 数据不足 · 中性"
    if info["status"] == "none":
        return "状态：— · 暂无事件 · 中性"

    d = int(direction) if direction is not None else int(info["direction"])
    code = str(info.get("code") or "—").strip() or "—"
    cn = str(info.get("cn_name") or "").strip()
    main = info["main"]
    note = info["note"]
    event = f"{code}（{cn}）" if cn and cn not in ("无", "不足", "无事件") else code
    return f"状态：{event} · {main}（{note}）· {_wyckoff_dir_label(d)}"


def _plain_phase_midline(phase_label: str) -> str:
    """相位 → 中线人话（去掉括号里的 AR/Spring 等英文，避免和事件灯重复）。"""
    import re

    raw = str(phase_label or "").strip()
    if not raw or "无明确阶段" in raw:
        return ""
    # 去掉（辅助：…）（测试：…）等，里面常塞英文事件名
    core = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
    core = re.sub(r"\s+", " ", core)

    # 先匹配更具体的标签
    rules: list[tuple[str, str]] = [
        ("主升", "已离开吸筹、偏主升"),
        ("Markup", "已离开吸筹、偏主升"),
        ("主跌", "已离开派发、偏主跌"),
        ("Markdown", "已离开派发、偏主跌"),
        ("积累期 A", "吸筹早期"),
        ("积累期 B", "还在吸筹中"),
        ("积累期 C", "吸筹测试段"),
        ("积累期 D", "吸筹末段、待启动"),
        ("积累期 E", "吸筹结束、抬升中"),
        ("派发期 A", "派发早期"),
        ("派发期 B", "还在派发中"),
        ("派发期 C", "派发测试段"),
        ("派发期 D", "派发末段"),
        ("派发期 E", "派发结束、下行中"),
        ("积累", "吸筹阶段"),
        ("派发", "派发阶段"),
    ]
    for key, plain in rules:
        if key in core or key in raw:
            return plain
    return core or raw


def _midline_meaning(code: str, cn_name: str, note: str, direction: int) -> str:
    """中线含义：只留防误读短句（事件名已在 Code（中文）里，不重复叙述）。"""
    c = (code or "").strip()
    by_code = {
        "AR": "不能当已经转强",
        "PS": "不能当已经转强",
        "SC": "还要等弹簧/确认",
        "ST": "还不能当主升",
        "Spring": "回踩区再谈",
        "SOS": "仍看回踩站不站稳",
        "BU": "勿追高",
        "JAC": "非单独开仓",
        "LPS": "破了就不算",
        "BC": "不能当还能续涨",
        "UT": "不能当突破成功",
        "UTAD": "小心往下破",
        "SOW": "先防守",
        "LPSY": "反抽别追",
        "PSY": "还不能当见顶定论",
        "SV": "可与SC同亮非双开仓",
        "Compression": "等方向选择",
        "TrendPullback": "破位就算假",
        "BullDiv": "不能当反转",
        "BearDiv": "别追高",
    }
    if c in by_code:
        return by_code[c]
    n = (note or "").strip()
    if n:
        return n
    if direction > 0:
        return "不能单独当开仓理由"
    if direction < 0:
        return "先防守"
    return "暂无明确含义"


def _phase_a_box_bounds(wyk: dict[str, Any]) -> tuple[float | None, float | None]:
    """Phase A 箱体下沿/上沿：只认事件种子（SC/ST 低 + AR 高）。

    法源：``wyckoff-tr-maturity-l0l3-handoff.md`` §1.1 / §2.3；``range-diff-fixes`` W-DIFF-1。
    下沿 = ``sc_low``（可被 ``st_sc_low`` / ``sc_low_refined`` 压低）；上沿 = ``ar_high``。
    **禁止**用分位 ``tr_lower`` / ``tr_upper`` 冒充雏形或成熟箱边界。
    """
    pa = wyk.get("phase_a_range") if isinstance(wyk.get("phase_a_range"), dict) else {}

    def _num(keys: tuple[str, ...], sources: tuple[dict, ...]) -> float | None:
        for src in sources:
            for k in keys:
                v = src.get(k)
                if v is None:
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    sources = (wyk, pa)
    lo = _num(("sc_low",), sources)
    # 成熟箱 / 雏形下沿：可被成功 ST 或 sc_low_refined 压低（不覆盖原 sc_low 字段）
    st_lo = _num(("st_sc_low", "sc_low_refined", "secondary_test_sc_low"), sources)
    if lo is not None and st_lo is not None:
        lo = min(lo, st_lo)
    elif lo is None:
        lo = st_lo
    # 上沿只认 AR 种子；无 ar_high → hi=None（短语走「上沿未出」），禁止 tr_upper
    hi = _num(("ar_high",), sources)
    if lo is not None and hi is not None and lo >= hi:
        return None, None
    return lo, hi


def _phase_a_box_phrase(wyk: dict[str, Any]) -> str:
    """箱体人话片段（中短线共用）。

    L0–L3 合同（``tr_maturity`` / ``box_display_mode`` 优先；见
    ``wyckoff-tr-maturity-l0l3-handoff.md`` §2.3）：
      none → 空；proto → 雏形（禁用「箱体」）；box → ``箱体 lo-hi``。
    无字段时：forming / established 无 ST → 雏形；established+ST → 箱体。
    """
    lo, hi = _phase_a_box_bounds(wyk)
    mode = str(wyk.get("box_display_mode") or "").strip()
    if not mode:
        maturity = str(wyk.get("tr_maturity") or "").strip().upper()
        mode = {"L0": "none", "L1": "proto", "L2": "box", "L3": "box"}.get(maturity, "")

    if mode == "none":
        return ""
    if mode == "proto":
        if lo is not None and hi is not None:
            return f"雏形 {lo:.2f}-{hi:.2f}（待 ST）"
        if lo is not None:
            return f"雏形 下沿 {lo:.2f}（上沿未出）"
        return "雏形 · 上沿未出"
    if mode == "box":
        if lo is not None and hi is not None:
            return f"箱体 {lo:.2f}-{hi:.2f}"
        return ""

    # 兼容回落：无 Gate 字段时，established 单独不得写「箱体 lo-hi」
    phase_a = str(wyk.get("phase_a_status") or "").strip() or "none"
    label = str(wyk.get("phase_label") or "").strip()
    st_ok = bool(wyk.get("secondary_test_sc_signal"))
    if phase_a == "forming" or "箱体未成形" in label or "区间未钉" in label:
        if lo is not None:
            return f"雏形 下沿 {lo:.2f}（上沿未出）"
        return "箱体未成形 · 上沿未出"
    if phase_a == "established":
        if st_ok and lo is not None and hi is not None:
            return f"箱体 {lo:.2f}-{hi:.2f}"
        if lo is not None and hi is not None:
            return f"雏形 {lo:.2f}-{hi:.2f}（待 ST）"
        if lo is not None:
            return f"雏形 下沿 {lo:.2f}（上沿未出）"
        return ""
    return ""


def _box_display_mode_of(wyk: dict[str, Any]) -> str:
    """解析 box_display_mode；缺省时由 tr_maturity 推导。"""
    mode = str(wyk.get("box_display_mode") or "").strip()
    if mode:
        return mode
    maturity = str(wyk.get("tr_maturity") or "").strip().upper()
    return {"L0": "none", "L1": "proto", "L2": "box", "L3": "box"}.get(maturity, "")


def _suppress_mature_box(wyk: dict[str, Any], *, gated: bool, gate_r: str) -> bool:
    """无/低质量分位 TR 时压制成熟「箱体」；L1 雏形提示始终可展示。"""
    if _box_display_mode_of(wyk) == "proto":
        return False
    if str(wyk.get("tr_maturity") or "").strip().upper() == "L1":
        return False
    return bool(gated) and gate_r in ("no_tr", "low_quality")


def format_wyckoff_daily_phase_light(
    wyckoff: dict[str, Any] | None = None,
) -> str:
    """短线威科夫只读展示正文（标签由渲染层统一加「威科夫：」；禁止「日线阶段：」）。

    产品契约（BUSINESS §2.2）：
      - 只给人看；不进中线定论 / fusion / 共振背景岗 / 单独开仓
      - 无箱体：无清晰区间 · 暂定不出
      - L1 雏形：写出「雏形 …（待 ST）」提示（非成熟箱体、非量度）
      - L2/L3：箱体 lo-hi
    """
    wyk = _unwrap_wyckoff_dict(wyckoff)
    if not wyk:
        return "数据不足 · 仅对照"

    if wyk.get("timeframe") == "insufficient":
        return "数据不足 · 仅对照"

    phase_a = str(wyk.get("phase_a_status") or "").strip() or "none"
    phase = str(wyk.get("phase") or "none").strip() or "none"
    label = str(wyk.get("phase_label") or "").strip()
    gate_r = str(wyk.get("phase_tr_gate_reason") or "").strip()
    gated = bool(wyk.get("phase_tr_gated"))
    plain = _plain_phase_midline(label)
    box = _phase_a_box_phrase(wyk)

    if phase_a == "failed":
        return "Phase A 失效｜本波无新SC｜对照"

    # P0-B 无/低质量 TR：压制成熟箱体；若有 L1 雏形仍提示
    if gated and gate_r in ("no_tr", "low_quality") and _suppress_mature_box(
        wyk, gated=gated, gate_r=gate_r
    ):
        if gate_r == "low_quality":
            return "无 · 区间质量差 · 暂定不出 · 仅对照"
        return "无 · 无清晰区间 · 暂定不出 · 仅对照"
    if gated and gate_r in ("no_tr", "low_quality") and box:
        slot = plain or "吸筹早期"
        return f"{slot} · {box} · 仅对照"

    # forming：有 SC、尚无 AR 定上沿（有下沿则带出）
    if phase_a == "forming" or "箱体未成形" in label or "区间未钉" in label:
        slot = plain or "吸筹早期"
        return f"{slot} · {box or '箱体未成形 · 上沿未出'} · 仅对照"

    # 有明确叙事（箱体/雏形 或过门控后的 A–E / markup…）
    if phase != "none" and plain:
        if box:
            return f"{plain} · {box} · 仅对照"
        return f"{plain} · 仅对照"

    # established 雏形但阶段被闸成 none：仍提示雏形
    if box:
        slot = plain or "吸筹早期"
        return f"{slot} · {box} · 仅对照"

    # 无 SC、无叙事：与中线 none 同构
    has_bounds = wyk.get("tr_upper") is not None or wyk.get("tr_lower") is not None
    if not has_bounds and wyk.get("tr_quality") is None:
        return "无 · 无清晰区间 · 暂定不出 · 仅对照"

    return "无 · 暂无定论 · 仅对照"


def format_wyckoff_midline_light(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
) -> str:
    """中线威科夫人话版（周线；不进短线评分）。

    结构「阶段 · [箱体/雏形] · 事件 · 含义」（阶段不明用「无」，不跳段）：
      威科夫：还在吸筹中 · 箱体 40.30-43.00 · AR（自动反弹）· 不能当已经转强
      威科夫：无 · 雏形 37.80-43.85（待 ST） · AR（自动反弹）· 不能当已经转强
      威科夫：吸筹早期 · 雏形 下沿 38.14（上沿未出） · SC（卖力高潮）· 还要等弹簧/确认
      威科夫：无 · BullDiv（看多背离）· 不能当反转
      威科夫：周线不足 · 不参与定论
    """
    info = resolve_wyckoff_primary(wyckoff)
    if info["status"] == "insufficient":
        return "威科夫：周线不足 · 不参与定论"
    if info["status"] == "no_data":
        return "威科夫：数据不足 · 中性"

    wyk = _unwrap_wyckoff_dict(wyckoff)
    if str(wyk.get("phase_a_status") or "").strip() == "failed":
        return "威科夫：Phase A 失效｜本波无新SC｜不据此开仓"
    phase_plain = _plain_phase_midline(str(info.get("phase_label") or ""))
    d = int(direction) if direction is not None else int(info["direction"] or 0)
    # 契约：中线威科夫始终「阶段 · 事件」；阶段定不出时用「无」，禁止直接跳到事件灯
    phase_slot = phase_plain or "无"
    parts: list[str] = []
    gate_r = str(wyk.get("phase_tr_gate_reason") or "").strip()
    gated = bool(wyk.get("phase_tr_gated"))
    # 无/低质量分位 TR：压制成熟箱体；L1 雏形仍提示
    suppress_box = _suppress_mature_box(wyk, gated=gated, gate_r=gate_r)
    proto_box = _phase_a_box_phrase(wyk) if not suppress_box else ""

    if info["status"] == "none":
        # 已跑周线引擎：不是「没算」，而是 TR/事件定不出阶段
        tr_q = wyk.get("tr_quality")
        if proto_box:
            # L1 雏形：即使阶段/分位 TR 被闸，也给人看候选区间提示
            parts.append(phase_slot)
            parts.append(proto_box)
            parts.append("暂无关键事件")
            parts.append("不据此开仓")
        elif suppress_box or (tr_q is None and not wyk.get("tr_upper") and not wyk.get("tr_lower")):
            parts.append("周线已算")
            if gate_r == "low_quality":
                parts.append("区间质量差")
            else:
                parts.append("构不成清晰吸筹/派发区间")
            parts.append("阶段暂定不出，不据此开仓")
        else:
            parts.append(phase_slot)
            parts.append("暂无关键事件")
            parts.append("不据此开仓")
        return "威科夫：" + " · ".join(parts) if parts else "威科夫：周线已算 · 暂无定论"

    code = str(info.get("code") or "—").strip() or "—"
    cn = str(info.get("cn_name") or "").strip()
    note = str(info.get("note") or "")
    meaning = _midline_meaning(code, cn, note, d)

    parts.append(phase_slot)
    if proto_box:
        parts.append(proto_box)
    # 灯：Spring（弹簧）—— 英文 + 中文括号，与短线状态行一致
    if cn and cn not in ("无", "不足", "无事件"):
        parts.append(f"{code}（{cn}）")
    else:
        parts.append(code)

    parts.append(meaning)
    rs_note = str(wyk.get("rs_note") or "").strip()
    rs_label = str(wyk.get("rs_label") or "neutral")
    if rs_note and rs_label in ("strong", "weak"):
        parts.append(rs_note)
    return "威科夫：" + " · ".join(parts)


def format_wyckoff_oneline(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
    show_phase: bool = False,
) -> str:
    """报告用威科夫一行人话（结论 + 白话，不拆第二行）。

    优先级与 fusion 主信号大致对齐：
      Spring > SOS > UT > BC > SOW > LPSY > SC > AR/ARE > ST > LPS > Compression >
      TrendPullback/TrendRally > 背离 > 无信号
    LPSY（最后供应点）在 SOW 之前：派发 D 阶段信号比 C 阶段更接近 breakdown。
    SC（卖力高潮）在 AR 之前：SC 是积累启动的原发事件，AR 是 SC 后的跟随反弹。
    ARE / TrendRally 为派发侧对称（BC 后回落 / 跌势中反抽不过均线）。

    Args:
        wyckoff: 威科夫分析结果 dict
        direction: 外部覆盖方向
        show_phase: 是否在输出中显示 phase_label

    Returns:
        如「威科夫：低位假跌破后收回，偏多（更像洗盘，缩量较可信）」
        如 show_phase=True：「积累期 C（测试：Spring）· 低位假跌破后收回，偏多」
    """
    wyk = _unwrap_wyckoff_dict(wyckoff)
    info = resolve_wyckoff_primary(wyk)

    if info["status"] == "insufficient":
        return "威科夫：周线不足 · 不参与定论"
    if info["status"] == "no_data":
        return "威科夫：数据不足 · 中性"
    if info["status"] == "none":
        _phase = info.get("phase_label") or ""
        _tf2 = "（日线）" if info.get("timeframe") == "daily_fallback" else ""
        if show_phase and _phase and "无明确阶段" not in _phase:
            return f"威科夫：{_phase} · 暂无事件 · 中性{_tf2}"
        return f"威科夫：暂无事件 · 中性{_tf2}"

    main = info["main"]
    note = info["note"]
    d = int(direction) if direction is not None else int(info["direction"])

    phase_prefix = ""
    if show_phase:
        _phase = info.get("phase_label") or ""
        if _phase and "无明确阶段" not in _phase:
            phase_prefix = f"{_phase} · "
    _tf_suffix = ""
    if info.get("timeframe") == "daily_fallback":
        _tf_suffix = "（日线）"
    return f"威科夫：{phase_prefix}{main} · {_wyckoff_dir_label(d)}（{note}）{_tf_suffix}"
