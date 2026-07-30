"""Wyckoff core facade: public API + re-export of split submodules."""
from __future__ import annotations

import json
import os
from typing import Any

from trader_shared.light_data import to_float

# ── Wyckoff 常量（唯一来源：trader_shared.config） ----
from trader_shared.config import (
    WYCKOFF_MIN_BARS,
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
    WYCKOFF_PHASE_LOOKBACK,
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
    WYCKOFF_SCORE_SOS,
    WYCKOFF_SCORE_ST,
    WYCKOFF_SCORE_LPS,
    WYCKOFF_SCORE_LPSY,
    WYCKOFF_SCORE_COMPRESSION,
    WYCKOFF_SCORE_TREND_PB,
    WYCKOFF_SCORE_PS,
    WYCKOFF_SCORE_PSY,
    WYCKOFF_SCORE_BU,
    WYCKOFF_SCORE_UTAD,
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

from .wyckoff_events import (
    _board_vol_scale,
    _compute_dynamic_support,
    _detect_ar,
    _detect_buying_climax,
    _detect_compression,
    _detect_effort_vs_result,
    _detect_lps,
    _detect_lpsy,
    _detect_selling_climax,
    _detect_sign_of_weakness,
    _detect_sos,
    _detect_spring,
    _detect_st,
    _detect_trend_pullback,
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
    _cause_effect_targets,
    _price_pos_pct,
    _spring_breach_level
)


def _resolve_score_conflicts(analysis: dict) -> set[str]:
    """同段反向极性互斥：返回应抑制打分的信号键，避免 SC+SOW 等对冲成假中性 50 分。

    规则（主叙事优先）：
    - SC vs SOW：有 AR/Spring/积累确认 → 抑 SOW；否则抑 SC（破位叙事）
    - Spring vs UT：premature 先抑；否则积累侧/SOS 抑 UT，派发侧/SOW 抑 Spring
    - LPS vs LPSY：有派发背景只计 LPSY，否则只计 LPS
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
        has_dist = any(
            analysis.get(k) for k in ("bc_signal", "upthrust_signal", "sow_signal", "utad_signal")
        )
        if has_dist:
            suppress.add("lps_signal")
        else:
            suppress.add("lpsy_signal")

    if bull and bear:
        suppress.add("bullish_volume_divergence")
        suppress.add("bearish_volume_divergence")

    if analysis.get("utad_signal") and ut:
        suppress.add("upthrust_signal")  # UTAD 已单独计分

    return suppress

def wyckoff_analysis(bars: list[dict], symbol: str = "", timeframe: str = "daily", use_persisted_phase: bool = True) -> dict:
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "spring_signal": False, "spring_reason": "数据不足", "spring_price": None,
            "upthrust_signal": False, "upthrust_reason": "数据不足", "upthrust_price": None,
            "bc_signal": False, "bc_reason": "数据不足", "bc_price": None,
            "sc_signal": False, "sc_reason": "数据不足", "sc_price": None,
            "sow_signal": False, "sow_intraday_warn": False,
            "sow_reason": "数据不足", "sow_price": None,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            # 新增信号
            "ar_signal": False, "ar_reason": "数据不足", "ar_price": None,
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
        }

    # P2-2: 动态支撑位计算（多源集成）— 仅用于 Spring 检测
    _weekly_scale = 0.2 if timeframe == "weekly" else 1.0
    _phase_lb = max(10, int(WYCKOFF_PHASE_LOOKBACK * _weekly_scale))
    _support_lb = max(3, int(10 * _weekly_scale))
    dynamic_support = _compute_dynamic_support(bars, lookback=_support_lb)

    # P0-3: TR 识别层 — 先定位当前交易区间，作为事件检测的语境
    tr_ctx = _detect_trading_range(bars)

    spring = _detect_spring(bars, _support=dynamic_support, symbol=symbol, tr_ctx=tr_ctx)
    upthrust = _detect_upthrust(bars, tr_ctx=tr_ctx)
    bc = _detect_buying_climax(bars, tr_ctx=tr_ctx)
    sc = _detect_selling_climax(bars, tr_ctx=tr_ctx)
    sow = _detect_sign_of_weakness(bars, tr_ctx=tr_ctx)  # SOW 使用自己的支撑位计算（处理 consecutive 逻辑）
    bearish_div, bullish_div = _detect_volume_divergence(bars)
    ar = _detect_ar(bars, tr_ctx=tr_ctx)
    sos = _detect_sos(bars, tr_ctx=tr_ctx)
    st = _detect_st(bars, tr_ctx=tr_ctx)
    lps = _detect_lps(bars, tr_ctx=tr_ctx)
    lpsy = _detect_lpsy(bars, tr_ctx=tr_ctx)
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
    ps = _detect_preliminary_support(bars, tr_ctx=tr_ctx)
    psy = _detect_preliminary_supply(bars, tr_ctx=tr_ctx)
    bu = _detect_backup(bars, tr_ctx=tr_ctx)
    utad = _detect_utad(
        bars,
        tr_ctx=tr_ctx,
        bc_signal=bool(bc.get("bc_signal")),
        sow_signal=bool(sow.get("sow_signal")),
        upthrust_signal=bool(upthrust.get("upthrust_signal")),
        upthrust_result=upthrust,
    )
    ce = _cause_effect_targets(tr_ctx, bars)
    # P2/P3: 新增信号
    compression = _detect_compression(bars)
    trend_pullback = _detect_trend_pullback(bars)
    # P0-5: 事件簇确认 — 将孤立信号升级为可信的积累/派发事件簇（校验先后顺序 + strength 定级）
    cluster = _detect_event_cluster(bars, tr_ctx=tr_ctx)

    # P1-1: 阶段状态机 — 基于信号序列推断积累/派发阶段
    signals_dict = {
        "spring_signal": spring["spring_signal"],
        "upthrust_signal": upthrust["upthrust_signal"],
        "bc_signal": bc["bc_signal"],
        "sc_signal": sc["sc_signal"],
        "sow_signal": sow["sow_signal"],
        "ar_signal": ar["ar_signal"],
        "sos_signal": sos["sos_signal"],
        "st_signal": st["st_signal"],
        "lps_signal": lps["lps_signal"],
        "lpsy_signal": lpsy["lpsy_signal"],
        "compression_signal": compression["compression_signal"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
        "bu_signal": bu.get("bu_signal"),
        "utad_signal": utad.get("utad_signal"),
        "ps_signal": ps.get("ps_signal"),
        "psy_signal": psy.get("psy_signal"),
        "tr_in_range": bool(tr_ctx.get("in_tr")) if tr_ctx else False,
        "tr_upper": tr_ctx.get("tr_upper") if tr_ctx else None,
        "last_close": to_float(bars[-1].get("close")) if bars else None,
    }
    phase = _detect_phase(bars, signals_dict, _phase_lookback=_phase_lb, tr_ctx=tr_ctx)

    # B: 跨日持久化状态机 — 加载旧状态、过渡、存储
    # use_persisted_phase=False 时（如中线威科夫）跳过持久化，直接返回本次
    # K 线的即时推断，避免「只进不退」状态机掩盖当前周期的真实阶段。
    if use_persisted_phase:
        old_state = _load_phase_state(symbol, timeframe)
        new_phase_state = _transition_phase(
            old_state,
            phase["phase"],
            phase["phase_label"],
            phase.get("phase_confidence_delta", 0.0),
        )
        _save_phase_state(symbol, timeframe, new_phase_state)
        # 用过渡后状态覆盖瞬时推断（phase 只进不退）
        phase = new_phase_state

    # P3-1: VSA 量价幅度分析
    vsa = _detect_effort_vs_result(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bc["bc_signal"]:
        parts.append(f"购买高潮: {bc['bc_reason']}")
    if sc["sc_signal"]:
        parts.append(f"卖力高潮: {sc['sc_reason']}")
    if sow["sow_signal"]:
        parts.append(f"弱势信号: {sow['sow_reason']}")
    elif sow.get("sow_intraday_warn"):
        parts.append(f"弱势警告(不计分): {sow['sow_reason']}")
    if ar["ar_signal"]:
        parts.append(f"自动反弹: {ar['ar_reason']}")
    if sos["sos_signal"]:
        parts.append(f"强势信号: {sos['sos_reason']}")
    if st["st_signal"]:
        parts.append(f"二次测试: {st['st_reason']}")
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
    if ce.get("cause_effect_up_target") is not None:
        parts.append(
            f"因果目标↑{ce['cause_effect_up_target']}/↓{ce['cause_effect_down_target']}"
        )
    if not parts:
        parts.append("无明显威科夫信号")

    return {
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
        "sc_price": round(sc["sc_price"], 2) if sc["sc_signal"] else None,
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        # 新增信号
        "ar_signal": ar["ar_signal"],
        "ar_reason": ar["ar_reason"],
        "ar_price": round(ar["ar_price"], 2) if ar["ar_signal"] else None,
        "sos_signal": sos["sos_signal"],
        "sos_reason": sos["sos_reason"],
        "sos_price": round(sos["sos_price"], 2) if sos["sos_signal"] else None,
        "st_signal": st["st_signal"],
        "st_reason": st["st_reason"],
        "st_price": round(st["st_price"], 2) if st["st_signal"] else None,
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
        "cause_effect_up_target": ce.get("cause_effect_up_target"),
        "cause_effect_down_target": ce.get("cause_effect_down_target"),
        "cause_effect_range": ce.get("cause_effect_range"),
        "cause_effect_note": ce.get("cause_effect_note"),
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
        # P0-3: TR 识别层透出
        "tr_upper": tr_ctx["tr_upper"] if tr_ctx else None,
        "tr_lower": tr_ctx["tr_lower"] if tr_ctx else None,
        "tr_baseline_volume": tr_ctx["tr_baseline_volume"] if tr_ctx else None,
        "tr_width": tr_ctx["tr_width"] if tr_ctx else None,
        "tr_amplitude_pct": tr_ctx["tr_amplitude_pct"] if tr_ctx else None,
        "tr_quality": tr_ctx["tr_quality"] if tr_ctx else None,
        "tr_in_range": tr_ctx["in_tr"] if tr_ctx else None,
        # P0-5: 事件簇确认透出
        "accumulation_confirmed": cluster["accumulation_confirmed"],
        "distribution_confirmed": cluster["distribution_confirmed"],
        "accumulation_failed": cluster["accumulation_failed"],
        "distribution_failed": cluster["distribution_failed"],
        "cluster_quality": cluster["cluster_quality"],
        "cluster_confidence": cluster["cluster_confidence"],
        "cluster_reason": cluster["cluster_reason"],
        "wyckoff_summary": "；".join(parts),
    }

def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None, symbol: str = "") -> dict:
    """日线威科夫（短线侧兼容 / 插件日线轨）。

    注意：短线 fusion 第三席已是 VPF，本结果**不**进入 ``merge_decisions`` 加权；
    日线威科夫主要用于 ``calculate_wyckoff_score``（池/复盘）与兼容导出字段。
    中线展示读 ``wyckoff_strategy_midline``（周线独占）。
    """
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

    # 8. AR (Automatic Rally) — SC 后自动反弹（⑥B）
    if analysis.get("ar_signal"):
        raw += WYCKOFF_SCORE_AR
        signals.append(f"AR 反弹 +{WYCKOFF_SCORE_AR}")

    # 9. SOS (Sign of Strength) — 强势突破
    if analysis.get("sos_signal"):
        raw += WYCKOFF_SCORE_SOS
        signals.append(f"SOS +{WYCKOFF_SCORE_SOS}")

    # 10. ST (Secondary Test) — 二次测试支撑
    if analysis.get("st_signal"):
        raw += WYCKOFF_SCORE_ST
        signals.append(f"ST +{WYCKOFF_SCORE_ST}")

    # 11. LPS (Last Point of Support) — 最后支撑点
    if lps_on:
        raw += WYCKOFF_SCORE_LPS
        signals.append(f"LPS +{WYCKOFF_SCORE_LPS}")

    # 12. P2: Compression — 压缩蓄势
    if analysis.get("compression_signal"):
        raw += WYCKOFF_SCORE_COMPRESSION
        signals.append(f"压缩蓄势 +{WYCKOFF_SCORE_COMPRESSION}")

    # 13. P3: Trend Pullback — 趋势回踩
    if analysis.get("trend_pullback_signal"):
        raw += WYCKOFF_SCORE_TREND_PB
        signals.append(f"趋势回踩 +{WYCKOFF_SCORE_TREND_PB}")

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
    code = cn = main = note = None
    d = 0

    if wyk.get("utad_signal"):
        code, cn, main, note, d = "UTAD", "派发末上冲", "派发末上冲回落", "警惕破位下行", -1
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
        code, cn, main, note, d = "AR", "自动反弹", "SC后快速反弹", "仅反弹，还不能当反转", 1
    elif wyk.get("sc_signal"):
        code, cn, main, note, d = "SC", "卖力高潮", "天量宽幅下跌", "卖力高潮，抛压宣泄后可能止跌", 1
    elif wyk.get("st_signal"):
        code, cn, main, note, d = "ST", "二次测试", "回踩支撑站住", "二次确认支撑有效", 1
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
        "LPS": "破了就不算",
        "BC": "不能当还能续涨",
        "UT": "不能当突破成功",
        "UTAD": "小心往下破",
        "SOW": "先防守",
        "LPSY": "反抽别追",
        "PSY": "还不能当见顶定论",
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


def format_wyckoff_midline_light(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
) -> str:
    """中线威科夫人话版（周线；不进短线评分）。

    三段式固定「阶段 · 事件 · 含义」（阶段不明用「无」，不跳段）：
      威科夫：还在吸筹中 · AR（自动反弹）· 不能当已经转强
      威科夫：无 · BullDiv（看多背离）· 不能当反转
      威科夫：周线不足 · 不参与定论
    """
    info = resolve_wyckoff_primary(wyckoff)
    if info["status"] == "insufficient":
        return "威科夫：周线不足 · 不参与定论"
    if info["status"] == "no_data":
        return "威科夫：数据不足 · 中性"

    phase_plain = _plain_phase_midline(str(info.get("phase_label") or ""))
    d = int(direction) if direction is not None else int(info["direction"] or 0)
    # 契约：中线威科夫始终「阶段 · 事件」；阶段定不出时用「无」，禁止直接跳到事件灯
    phase_slot = phase_plain or "无"
    parts: list[str] = []

    if info["status"] == "none":
        # 已跑周线引擎：不是「没算」，而是 TR/事件定不出阶段
        wyk = _unwrap_wyckoff_dict(wyckoff)
        tr_q = wyk.get("tr_quality")
        if tr_q is None and not wyk.get("tr_upper") and not wyk.get("tr_lower"):
            parts.append("周线已算")
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
    # 灯：Spring（弹簧）—— 英文 + 中文括号，与短线状态行一致
    if cn and cn not in ("无", "不足", "无事件"):
        parts.append(f"{code}（{cn}）")
    else:
        parts.append(code)

    parts.append(meaning)
    return "威科夫：" + " · ".join(parts)


def format_wyckoff_oneline(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
    show_phase: bool = False,
) -> str:
    """报告用威科夫一行人话（结论 + 白话，不拆第二行）。

    优先级与 fusion 主信号大致对齐：
      Spring > SOS > UT > BC > SOW > LPSY > SC > AR > ST > LPS > Compression > TrendPullback > 背离 > 无信号
    LPSY（最后供应点）在 SOW 之前：派发 D 阶段信号比 C 阶段更接近 breakdown。
    SC（卖力高潮）在 AR 之前：SC 是积累启动的原发事件，AR 是 SC 后的跟随反弹。

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
