# -*- coding: utf-8 -*-
"""筹码 / EXPMA / 共振 enrichment。"""
from __future__ import annotations

from typing import Any

from trader_shared.report_pipeline._common import MarkFn, _noop_mark

def run_chip_enrichment_stage(
    *,
    bars: list,
    bars_5m: list | None,
    current: float,
    target: str,
    quote: dict[str, Any],
    ts_code: str,
    support: Any,
    resistance: Any,
    weekly_bars: list | None,
    weekly_proxy_close: float,
    mf_result: dict[str, Any] | None,
    big_order_result: dict[str, Any],
    levels: dict[str, Any],
    report_fusion: dict[str, Any],
    provider: Any = None,
    snapshot: Any = None,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """筹码 + 主力评分 + EXPMA + 多周期共振，并回写 levels / fusion 置信。

    自 build_report 抽出；返回 enrichment dict（chip_* / expma_* / resonance_result 等）。
    """
    from trader_shared.chip_core import analyze_chips_and_migration
    from trader_shared.indicator_math import aggregate_5m_to_60m, calc_expma_series
    from trader_shared._logging import get_logger

    _log = get_logger(__name__)
    _mark = mark or _noop_mark

    tushare_chip_data = None
    try:
        from trader_shared.chip_data import get_cyq_perf_cached

        _cyq = get_cyq_perf_cached(ts_code, start_date="", end_date="")
        if _cyq:
            _latest = max(_cyq, key=lambda x: str(x.get("trade_date", "")))
            _winner_rate = float(_latest.get("winner_rate", 0) or 0)
            _cost_50 = float(_latest.get("cost_50pct", 0) or 0)
            _peaks = []
            for _pct_key, _share in [
                ("cost_5pct", 5),
                ("cost_15pct", 15),
                ("cost_50pct", 50),
                ("cost_85pct", 85),
                ("cost_95pct", 95),
            ]:
                _price = float(_latest.get(_pct_key, 0) or 0)
                if _price > 0:
                    _peaks.append({"price": _price, "share_of_total": _share})
            tushare_chip_data = {
                "current_pct": _winner_rate,
                "mid_price": _cost_50,
                "peaks": _peaks,
                "source": "tushare_cyq_perf",
            }
    except Exception as e:
        _log.warning("Tushare cyq_perf fallback to internal calc: %s", e)

    chip_res = analyze_chips_and_migration(
        bars=bars,
        current_price=current,
        target=target,
        trade_date=quote.get("trade_date"),
        tushare_chip_data=tushare_chip_data,
    )
    chip = chip_res["chip"]
    chip_peaks = chip_res["chip_peaks"]
    chip_migration = chip_res["chip_migration"]
    chip_support = chip_res["chip_support"]
    chip_resistance = chip_res["chip_resistance"]
    chip_support_lower = chip_res["chip_support_lower"]
    chip_support_upper = chip_res["chip_support_upper"]
    chip_resistance_lower = chip_res["chip_resistance_lower"]
    chip_resistance_upper = chip_res["chip_resistance_upper"]
    _mark("chip")

    main_force_score_result: dict[str, Any] = {
        "total_score": 0,
        "flow_score": 0,
        "chip_score": 0,
        "order_score": 0,
        "detail": {},
        "label": "🔴无数据",
    }
    mf_features = mf_result if mf_result else {}
    chip_has_history = chip_migration.get("has_history", False) if chip_migration else False
    if mf_features or big_order_result.get("events") or chip_has_history:
        try:
            from trader_shared.main_force_scoring import score_main_force

            main_force_score_result = score_main_force(
                features=mf_features,
                chip_migration=chip_migration,
                big_order=big_order_result,
                bars=bars,
            )
        except Exception:
            pass

    expma10_val = None
    expma12_val = None
    expma20_val = None
    expma50_val = None
    expma_trend = "无数据"
    try:
        closes_for_expma = [
            float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0
        ]
        if len(closes_for_expma) >= 10:
            expma_vals = calc_expma_series(closes_for_expma, 10)
            expma10_val = expma_vals[-1] if expma_vals else None
        if len(closes_for_expma) >= 12:
            expma12_vals = calc_expma_series(closes_for_expma, 12)
            expma12_val = expma12_vals[-1] if expma12_vals else None
        if len(closes_for_expma) >= 20:
            expma20_vals = calc_expma_series(closes_for_expma, 20)
            expma20_val = expma20_vals[-1] if expma20_vals else None
        if len(closes_for_expma) >= 50:
            expma50_vals = calc_expma_series(closes_for_expma, 50)
            expma50_val = expma50_vals[-1] if expma50_vals else None
        if expma10_val and expma20_val and expma50_val:
            if expma10_val > expma20_val > expma50_val:
                expma_trend = "多头排列"
            elif expma10_val < expma20_val < expma50_val:
                expma_trend = "空头排列"
            else:
                expma_trend = "交叉震荡"
        elif expma10_val and expma20_val:
            expma_trend = "短期偏多" if expma10_val > expma20_val else "短期偏空"
    except Exception:
        pass

    expma_status_result: dict[str, Any] = {
        "total_score": 0,
        "alignment_score": 0,
        "slope_score": 0,
        "cross_score": 0,
        "deviation_score": 0,
        "expma_values": {},
        "trend_label": "数据不足",
        "detail": {},
    }
    try:
        closes_for_expma = [
            float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0
        ]
        if len(closes_for_expma) >= 10:
            from trader_shared.expma_status import calc_expma_status

            expma_status_result = calc_expma_status(closes_for_expma, current, bars)
    except Exception:
        pass

    resonance_result: dict[str, Any] = {
        "total_score": 0,
        "monthly_score": 0,
        "weekly_score": 0,
        "daily_score": 0,
        "timing_score": 0,
        "sell_timing_score": 0,
        "resonance_score": 0,
        "monthly_label": "无数据",
        "weekly_label": "无数据",
        "daily_label": "无数据",
        "timing_label": "无数据",
        "sell_timing_label": "无数据",
        "resonance_label": "无数据",
        "detail": {},
    }
    try:
        from trader_shared.multi_timeframe_resonance import calc_resonance

        res_d_closes = [
            float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0
        ]
        _support_f = float(support) if support else 0
        _resistance_f = float(resistance) if resistance else 0
        if res_d_closes and len(res_d_closes) >= 10:
            # 60m 只用已收盘 5m，避免未完成棒抬高卖出 timing → fusion 置信
            _bars_5m_done = bars_5m or []
            try:
                from trader_shared.t0_price_point_engine import completed_5m_bars
                _bars_5m_done = completed_5m_bars(_bars_5m_done) if _bars_5m_done else []
            except Exception:
                pass
            bars_60m = aggregate_5m_to_60m(_bars_5m_done) if _bars_5m_done else []
            monthly_bars = list(getattr(snapshot, "monthly_bars", None) or []) if snapshot else []
            # 主路径 snapshot 默认 include_monthly=False；补拉走日缓存，避免每票打网
            if not monthly_bars and provider is not None and snapshot is not None:
                try:
                    from trader_shared.cache_utils import CACHE_MONTHLY, get_day_scoped_bars

                    _sec = snapshot.security
                    _mkey = getattr(_sec, "ts_code", None) or getattr(_sec, "code", "") or target
                    monthly_bars = list(
                        get_day_scoped_bars(
                            CACHE_MONTHLY,
                            str(_mkey),
                            lambda: list(provider.fetch_monthly(_sec) or []),
                            min_rows=1,
                        )
                        or []
                    )
                except Exception as _me:
                    _log.debug("monthly fetch for resonance skipped: %s", _me)
                    monthly_bars = []
            resonance_result = calc_resonance(
                daily_closes=res_d_closes,
                current_price=current,
                weekly_bars=weekly_bars or [],
                weekly_close=weekly_proxy_close,
                bars_60m=bars_60m,
                daily_support=_support_f,
                daily_resistance=_resistance_f,
                monthly_bars=monthly_bars or [],
            )
    except Exception:
        pass
    _mark("resonance")

    _sell_timing = resonance_result.get("sell_timing_score", 0)
    if _sell_timing >= 1 and report_fusion.get("weighted_score", 0) < 0:
        _boost = 0.05 * _sell_timing
        report_fusion["confidence"] = min(0.95, report_fusion.get("confidence", 0) + _boost)

    if chip_resistance and chip_resistance > current:
        levels.setdefault("resistance_levels", []).append(
            {"name": "筹码阻力", "price": round(chip_resistance, 2), "weight": 0.95}
        )
        from trader_shared.structure_core import choose_level

        _new_res = choose_level(levels["resistance_levels"], current, below=False)
        levels["resistance"] = round(float(_new_res["price"]), 2)
        levels["resistance_source"] = _new_res["name"]
    levels["chip_resistance"] = chip_resistance

    if chip_support and chip_support < current:
        levels.setdefault("support_levels", []).append(
            {"name": "筹码支撑", "price": round(chip_support, 2), "weight": 0.95}
        )
        from trader_shared.structure_core import choose_level

        _new_sup = choose_level(levels["support_levels"], current, below=True)
        levels["support"] = round(float(_new_sup["price"]), 2)
        levels["support_source"] = _new_sup["name"]
    levels["chip_support"] = chip_support

    return {
        "chip": chip,
        "chip_peaks": chip_peaks,
        "chip_migration": chip_migration,
        "chip_support": chip_support,
        "chip_resistance": chip_resistance,
        "chip_support_lower": chip_support_lower,
        "chip_support_upper": chip_support_upper,
        "chip_resistance_lower": chip_resistance_lower,
        "chip_resistance_upper": chip_resistance_upper,
        "main_force_score_result": main_force_score_result,
        "expma10_val": expma10_val,
        "expma12_val": expma12_val,
        "expma20_val": expma20_val,
        "expma50_val": expma50_val,
        "expma_trend": expma_trend,
        "expma_status_result": expma_status_result,
        "resonance_result": resonance_result,
    }


