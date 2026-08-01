# -*- coding: utf-8 -*-
"""结构阶段。"""
from __future__ import annotations

from typing import Any

from trader_shared.report_pipeline._common import MarkFn, _noop_mark

def run_structure_stage(
    *,
    current: float,
    bars: list,
    bars_5m: list | None,
    quote: dict[str, Any],
    report_fusion: dict[str, Any],
    chan_result: dict[str, Any],
    wyck_result: dict[str, Any],
    momentum_result: dict[str, Any],
    mf_result: dict[str, Any] | None,
    main_force_env: str,
    fetcher: Any,
    big_order_result: dict[str, Any],
    order_book: Any = None,
    mark: MarkFn | None = None,
    prev_trailing_stop: float | None = None,
    trailing_ratchet_symbol: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """结构阶段：VP → pre_stage → build_structure_context → 合并理论字段 → 大单补全。

    自 build_report 抽出；返回 (levels, big_order_result, pre_stage)。
    """
    from trader_shared.candidate_core import build_structure_context
    from trader_shared.structure_core import find_key_levels
    from trader_shared.stage_positioning import _detect_major_stage

    _mark = mark or _noop_mark

    vp_result = None
    try:
        from trader_shared.volume_profile import compute_volume_profile
        from trader_shared.t0_price_point_engine import completed_5m_bars

        # 只用已收盘 5m，避免盘中未完成棒污染 POC/VA
        _vp_bars = completed_5m_bars(bars_5m) if bars_5m else []
        if _vp_bars and len(_vp_bars) >= 10:
            vp_result = compute_volume_profile(_vp_bars)
    except Exception:
        pass

    def _quick_ma(period: int) -> float | None:
        if len(bars) < period:
            return None
        valid_closes = [
            float(b.get("close") or 0) for b in bars[-period:] if float(b.get("close") or 0) > 0
        ]
        return sum(valid_closes) / len(valid_closes) if valid_closes else None

    _pre_ma = {
        "ma5": _quick_ma(5),
        "ma10": _quick_ma(10),
        "ma20": _quick_ma(20),
        "ma30": _quick_ma(30),
    }
    # fusion 仅仪表：不得用 action/weighted_score 微调 major_stage / 结构位
    _pre_stage, _pre_conf, _pre_reason, _pre_vp = _detect_major_stage(
        current,
        _pre_ma,
        bars,
        fusion_hint=None,
        wyckoff_result=wyck_result,
        chan_result=chan_result,
        main_force_result=mf_result,
    )
    _major_stage_seed = (_pre_stage, _pre_conf, _pre_reason, _pre_vp)
    levels = build_structure_context(
        current,
        bars,
        quote.get("current_change_pct"),
        quote,
        fusion_result=None,
        chan_result=chan_result,
        fetcher=fetcher,
        vp_result=vp_result,
        major_stage=_pre_stage,
        prev_trailing_stop=prev_trailing_stop,
        trailing_ratchet_symbol=trailing_ratchet_symbol,
    )
    _mark("structure")

    for key, val in {
        "chanlun": chan_result,
        "wyckoff": wyck_result,
        "momentum": momentum_result,
    }.items():
        if key not in levels:
            levels[key] = val

    chan_inner = (
        chan_result.get("chanlun", chan_result) if "chanlun" in chan_result else chan_result
    )
    levels["chan_trend_label"] = chan_inner.get("trend_label", "数据不足")
    levels["chan_buy_point_text"] = chan_inner.get("buy_point_text", "无")
    levels["chan_buy_points"] = chan_inner.get("buy_points", [])
    levels["chan_sell_point_text"] = chan_inner.get("sell_point_text", "无")
    levels["chan_sell_points"] = chan_inner.get("sell_points", [])
    levels["chan_strokes_count"] = chan_inner.get("strokes_count", 0)
    levels["chan_zone_last_price"] = chan_inner.get("last_valid_zone_last_price")
    levels["chan_zone_first_price"] = chan_inner.get("last_valid_zone_first_price")
    levels["chan_divergence"] = chan_inner.get("divergence", {})
    levels["chan_structure_type"] = chan_inner.get("structure_type", "")
    levels["chan_segments_count"] = chan_inner.get("segments_count", 0)

    _wyk = wyck_result.get("wyckoff", wyck_result) if isinstance(wyck_result, dict) else {}
    if not isinstance(_wyk, dict):
        _wyk = {}
    levels["wyckoff_spring_signal"] = _wyk.get("spring_signal", False)
    levels["wyckoff_summary"] = _wyk.get("wyckoff_summary", "无明显信号")
    levels["wyckoff_upthrust_signal"] = _wyk.get("upthrust_signal", False)
    levels["base_status"] = levels.get("base_status") or levels.get("status")
    levels["theory_status"] = levels.get("theory_status") or levels.get("status")
    levels["fusion_override_used"] = levels.get("fusion_override_used", False)
    levels["main_force"] = mf_result
    levels["main_force_env"] = main_force_env
    levels["pre_stage"] = _pre_stage
    levels["major_stage_seed"] = _major_stage_seed

    try:
        levels["key_levels"] = find_key_levels(bars)
    except Exception:
        levels["key_levels"] = {
            "short_support": 0.0,
            "mid_support": 0.0,
            "long_support": 0.0,
            "short_resist": 0.0,
            "mid_resist": 0.0,
            "long_resist": 0.0,
        }

    if big_order_result.get("events") is None or not big_order_result.get("events"):
        try:
            from trader_shared.big_order import analyze_big_orders

            if bars_5m:
                big_order_result = analyze_big_orders(
                    bars_5m,
                    focus_prices=levels.get("key_pressure"),
                    trade_date=quote.get("trade_date"),
                    order_book=order_book,
                )
        except Exception:
            pass

    return levels, big_order_result, _pre_stage


