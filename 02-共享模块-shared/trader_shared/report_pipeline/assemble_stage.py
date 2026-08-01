# -*- coding: utf-8 -*-
"""四阶段定位 + 基础报告组装。"""
from __future__ import annotations

from typing import Any

from trader_shared.report_pipeline._common import MarkFn, _noop_mark  # noqa: F401
from trader_shared.report_pipeline.prelude import tag_fusion_as_instrument

def _calc_volume_ratio_from_bars(bars: list[dict], window: int = 5) -> float:
    """从日K线计算量比（近N日均量 / 前N日均量）。"""
    if len(bars) < 2 * window:
        return 0.0
    older = bars[-2 * window : -window]
    newer = bars[-window:]
    older_vols: list[float] = []
    newer_vols: list[float] = []
    for b in older:
        try:
            v = float(str(b.get("volume", 0)).replace(",", ""))
            if v > 0:
                older_vols.append(v)
        except (ValueError, TypeError):
            pass
    for b in newer:
        try:
            v = float(str(b.get("volume", 0)).replace(",", ""))
            if v > 0:
                newer_vols.append(v)
        except (ValueError, TypeError):
            pass
    if not newer_vols or not older_vols:
        return 0.0
    avg_recent = sum(newer_vols) / len(newer_vols)
    avg_prev = sum(older_vols) / len(older_vols)
    return avg_recent / avg_prev if avg_prev > 0 else 0.0


def run_stage_positioning_stage(
    *,
    bars: list,
    current: float,
    quote: dict[str, Any],
    levels: dict[str, Any],
    atr14_val: float,
    chip_migration: dict[str, Any] | None,
    chip_support_lower: Any,
    chip_resistance_lower: Any,
    chip_resistance_upper: Any,
    report_fusion: dict[str, Any],
    wyck_result: dict[str, Any],
    mf_result: dict[str, Any] | None,
    chan_result: dict[str, Any],
    ts_code: str,
    extend_sector: Any,
    pre_stage: Any,
    support: Any,
    confirm: Any,
) -> dict[str, Any]:
    """四阶段定位 + 保护后止盈回写 + upward_momentum。

    自 build_report 抽出；可能改写 levels['take']。
    返回 stage_result / ma250 / bars_date / upward_momentum / take。
    """
    from trader_shared.light_data import to_float
    from trader_shared.report_presentation import upward_momentum_observation
    from trader_shared.stage_positioning import assess_stage

    ma_raw_v = levels.get("ma_values") or {}
    closes_250 = [
        to_float(b.get("close")) for b in bars[-250:] if to_float(b.get("close")) is not None
    ]
    ma250 = sum(closes_250) / len(closes_250) if len(closes_250) >= 250 else None

    bars_date = ""
    if bars:
        last_bar = bars[-1]
        bars_date = str(last_bar.get("trade_date") or last_bar.get("date") or "")
    if not bars_date:
        bars_date = str(quote.get("trade_date") or quote.get("date") or "")

    stage_result = assess_stage(
        current=current,
        ma_values={**ma_raw_v, "ma250": ma250},
        change_pct=float(quote.get("current_change_pct") or 0),
        bars=bars,
        position_ratio=levels.get("position_ratio", 0.5),
        atr14=atr14_val,
        chip_migration=chip_migration,
        fib_retrace=levels.get("fib_retrace"),
        symbol=ts_code,
        trade_date=bars_date,
        fusion_hint={
            "action": report_fusion.get("action"),
            "confidence": report_fusion.get("confidence", 0),
            "weighted_score": report_fusion.get("weighted_score", 0),
        },
        wyckoff_result=wyck_result,
        main_force_result=mf_result,
        chan_result=chan_result,
        extend_sector=extend_sector,
        chip_support_lower=chip_support_lower or 0.0,
        chip_resistance_lower=chip_resistance_lower or 0.0,
        chip_resistance_upper=chip_resistance_upper or 0.0,
        major_stage_seed=levels.get("major_stage_seed"),
    )

    take = levels.get("take")
    protected_stage = stage_result["major_stage"]
    if protected_stage != pre_stage:
        resistance_price = levels.get("resistance") or 0
        if protected_stage in ("蓄势", "蓄势偏强"):
            take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
        elif protected_stage == "主升":
            take = round(resistance_price, 2) if resistance_price else round(current * 1.10, 2)
        elif protected_stage == "派发":
            take = round(current, 2)
        elif protected_stage == "蓄势偏弱":
            take = round(resistance_price * 0.98, 2) if resistance_price else round(current, 2)
        elif protected_stage == "衰退":
            take = None
        else:
            take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
        if take is not None:
            take = max(take, current)
        levels["take"] = take

    upward_momentum = upward_momentum_observation(
        stage_result["major_stage"], current, support, confirm
    )

    return {
        "stage_result": stage_result,
        "ma250": ma250,
        "bars_date": bars_date,
        "upward_momentum": upward_momentum,
        "take": take,
    }


def assemble_base_report(
    *,
    intraday_as_of: Any,
    quote: dict[str, Any],
    sec: Any,
    analysis_time: str,
    current: float,
    weekly_proxy_close: float,
    monthly_proxy_close: float,
    support: Any,
    resistance: Any,
    confirm: Any,
    stop: Any,
    take: Any,
    stage: str,
    scene: str,
    levels: dict[str, Any],
    replay: str,
    volume_text: str,
    upward_momentum: str,
    low: Any,
    high: Any,
    snapshot: Any,
    bars: list,
    risk_flags: list,
    atr14_val: float,
    atr_ratio_val: float,
    atr_level: Any,
    atr_cap: Any,
    st: dict[str, Any],
    st_dir: Any,
    vwap_res: dict[str, Any],
    base_status: str,
    theory_status: str,
    state_label: str,
    volume_note: str,
    market_env_data: Any,
    position_cap: Any,
    ma250: Any,
    chip: dict[str, Any],
    chip_peaks: Any,
    chip_support: Any,
    chip_resistance: Any,
    chip_support_lower: Any,
    chip_support_upper: Any,
    chip_resistance_lower: Any,
    chip_resistance_upper: Any,
    report_fusion: dict[str, Any],
    main_force_score_result: dict[str, Any],
    big_order_result: dict[str, Any],
    stage_result: dict[str, Any],
    wyck_result: dict[str, Any],
    wyck_mid_result: dict[str, Any] | None,
    chan_result: dict[str, Any],
    chan_mid_result: dict[str, Any] | None,
    expma10_val: Any,
    expma12_val: Any,
    expma20_val: Any,
    expma50_val: Any,
    expma_trend: Any,
    expma_status_result: dict[str, Any],
    resonance_result: dict[str, Any],
    sector_data: Any,
    atr_adjust: str = "unknown",
    atr_data_source: str = "",
    fusion_pre_cards: Any = None,
) -> dict[str, Any]:
    """组装 build_report 基础 dict，并 sync 非内部 levels 字段。"""
    from trader_shared.report_presentation import ma_text

    report: dict[str, Any] = {
        "intraday_as_of": intraday_as_of,
        "name": quote.get("name") or sec.name,
        "symbol": quote.get("symbol") or sec.ts_code,
        "analysis_time": analysis_time,
        "current": current,
        "change_pct": quote.get("current_change_pct"),
        "weekly_close": weekly_proxy_close,
        "monthly_close": monthly_proxy_close,
        "support": support,
        "resistance": resistance,
        "confirm": confirm,
        "stop": stop,
        "trailing_stop": levels.get("trailing_stop"),
        "effective_stop": levels.get("effective_stop") or stop,
        "take": take,
        "stage": stage,
        "scene": scene,
        "low_zone": levels["low_zone"],
        "low_zone_lower": levels["low_zone_lower"],
        "low_zone_upper": levels["low_zone_upper"],
        "support_source": levels.get("support_source"),
        "resistance_source": levels.get("resistance_source"),
        "atr_pct": levels.get("atr_pct"),
        "zone_width_pct": levels.get("zone_width_pct"),
        "stop_buffer_pct": levels.get("stop_buffer_pct"),
        "pressure_space_pct": levels.get("pressure_space_pct"),
        "replay": replay,
        "volume_text": volume_text,
        "upward_momentum": upward_momentum,
        "range_low": low,
        "range_high": high,
        "data_status": snapshot.data_status,
        "data_freshness": getattr(snapshot, "data_freshness", "live"),
        "data_note": None,
        "bars": bars,
        "risk_flags": risk_flags,
        "chan_buy_point_text": levels.get("chan_buy_point_text", "无"),
        "chan_trend_label": levels.get("chan_trend_label", "数据不足"),
        "chan_buy_point_types": [bp.get("type", "") for bp in levels.get("chan_buy_points", [])],
        "chan_sell_point_types": [sp.get("type", "") for sp in levels.get("chan_sell_points", [])],
        "missing_sources": snapshot.missing_sources,
        "source_errors": snapshot.source_errors,
        "fetched_at": snapshot.fetched_at,
        "volume_ratio": _calc_volume_ratio_from_bars(bars),
        "turnover_rate": quote.get("turnover_rate"),
        "daily_bars": bars,
        "ma": {
            "ma5": ma_text(levels["ma_values"].get("ma5")),
            "ma10": ma_text(levels["ma_values"].get("ma10")),
            "ma20": ma_text(levels["ma_values"].get("ma20")),
            "ma30": ma_text(levels["ma_values"].get("ma30")),
            "ma250": ma_text(levels["ma_values"].get("ma250")),
        },
        "atr14": atr14_val,
        "atr_ratio": atr_ratio_val,
        "atr_level": atr_level,
        "atr_cap": atr_cap,
        "atr_adjust": atr_adjust,
        "atr_data_source": atr_data_source,
        "supertrend_direction": st_dir,
        "supertrend_stop": (
            st.get("stop_long")
            if st_dir == "up"
            else st.get("stop_short")
            if st_dir == "down"
            else None
        ),
        "supertrend_atr": st.get("atr"),
        "supertrend_vol_level": st.get("vol_level"),
        "vwap": vwap_res.get("vwap"),
        "vwap_dev": vwap_res.get("deviation_pct"),
        "vwap_position": vwap_res.get("position"),
        "vwap_level": vwap_res.get("level"),
        "base_status": base_status,
        "theory_status": theory_status,
        "fusion_override_used": levels.get("fusion_override_used", False),
        "theory_fusion_conflict": levels.get("theory_fusion_conflict", False),
        "state_label": state_label,
        "volume_note": volume_note,
        "market_env": market_env_data,
        "position_cap": position_cap,
        "ma250": round(ma250, 2) if ma250 is not None else None,
        "ma250_warning": current < ma250 if (current is not None and ma250 is not None) else False,
        "ma_raw": {
            "ma5": levels["ma_values"].get("ma5"),
            "ma10": levels["ma_values"].get("ma10"),
            "ma20": levels["ma_values"].get("ma20"),
            "ma30": levels["ma_values"].get("ma30"),
            "ma250": round(ma250, 2) if ma250 is not None else None,
        },
        "chip_support": chip_support,
        "chip_resistance": chip_resistance,
        "chip_support_lower": chip_support_lower,
        "chip_support_upper": chip_support_upper,
        "chip_resistance_lower": chip_resistance_lower,
        "chip_resistance_upper": chip_resistance_upper,
        "chip_peaks": chip_peaks,
        "chip_current_pct": chip.get("current_pct"),
        "chip_mid_price": chip.get("mid_price"),
        "fusion": tag_fusion_as_instrument(
            report_fusion if isinstance(report_fusion, dict) else {}
        ),
        "gap": levels.get("gap"),
        "time_window": levels.get("time_window"),
        "fib_retrace": levels.get("fib_retrace"),
        "high_zone": levels.get("high_zone"),
        "high_zone_lower": levels.get("high_zone_lower"),
        "high_zone_upper": levels.get("high_zone_upper"),
        "fib_ext_1382": levels.get("fib_ext_1382"),
        "fib_ext_1618": levels.get("fib_ext_1618"),
        "main_force_score": main_force_score_result,
        "big_order_summary": big_order_result.get("summary"),
        "big_order_direction": big_order_result.get("direction_summary"),
        "major_stage": stage_result["major_stage"],
        "major_reason": stage_result["major_reason"],
        "short_term_momentum": stage_result["momentum"],
        "momentum_reason": stage_result["momentum_reason"],
        "stage_action": stage_result["action"],
        "max_position_pct": stage_result["max_position_pct"],
        "stage_label": stage_result["stage_label"],
        "confidence": stage_result.get("confidence", 0),
        "protection_notes": stage_result.get("protection_notes", []),
        "stop_losses": stage_result.get("stop_losses", {}),
        "wyckoff": (wyck_mid_result.get("wyckoff") if isinstance(wyck_mid_result, dict) else None)
        or wyck_result.get("wyckoff", wyck_result),
        "wyckoff_daily": wyck_result.get("wyckoff", wyck_result),
        "wyckoff_midline": (
            (wyck_mid_result.get("wyckoff") if isinstance(wyck_mid_result, dict) else None)
            or {
                "timeframe": "insufficient",
                "phase": "none",
                "wyckoff_summary": "中线数据不足",
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "sos_signal": False,
            }
        ),
        "chanlun_daily": chan_result,
        "chanlun_midline": chan_mid_result
        if chan_mid_result
        else {"chanlun": {"timeframe": "insufficient", "structure_type": "", "divergence": {}}},
        "expma10": expma10_val,
        "expma12": expma12_val,
        "expma20": expma20_val,
        "expma50": expma50_val,
        "expma_trend": expma_trend,
        "expma_status": expma_status_result,
        # 多周期打分（MTF）；与岗位共振 report["resonance"]=pullback_probe 隔离
        # 法源：docs/designs/resonance-and-orchestration.md
        "mtf_resonance": resonance_result,
        "extend_fundamental": snapshot.extend_fundamental,
        "extend_sentiment": snapshot.extend_sentiment,
        "extend_margin": snapshot.extend_margin,
        "extend_northbound": snapshot.extend_northbound,
        "extend_sector": sector_data,
        "extend_concept": snapshot.extend_concept,
    }
    if fusion_pre_cards:
        report["_fusion_pre_cards"] = fusion_pre_cards

    _INTERNAL_LEVELS = frozenset(
        {
            "status",
            "confirm_price",
            "hard_stop",
            "main_support",
            "main_resistance",
            "support_source",
            "resistance_source",
            "resistance_levels",
            "support_levels",
            "chan_buy_points",
            "chan_sell_points",
            "chan_zone_last_price",
            "chan_zone_first_price",
            "low_zone_lower",
            "low_zone_upper",
            "ma_values",
            "main_force",
            "main_force_env",
            "wyckoff_summary",
            "fus_score",
            "fus_disagree",
            "fus_override",
            "fus_override_used",
        }
    )
    for _key, _val in levels.items():
        if _key not in _INTERNAL_LEVELS:
            report.setdefault(_key, _val)
    return report

