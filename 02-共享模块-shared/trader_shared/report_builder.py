# -*- coding: utf-8 -*-
"""Domain layer: build_report orchestration + analysis.
Presentation (render_markdown + helpers) is in report_renderer.py."""

from __future__ import annotations

import sys

from pathlib import Path

from typing import Any

import os

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent

from trader_shared.light_data import to_float, pct_change

from trader_shared.fetchers import TencentFetcher

from trader_shared.config import LOOKBACK_DAYS, STRUCTURE_WINDOW

from trader_shared.signal_core import state_text


def _degraded_quote_report(target: str) -> dict[str, Any]:
    """计算依赖缺失时的降级报告：仅返回行情数据。"""
    try:
        from trader_shared.data_provider import get_provider
        provider = get_provider()
        sec = provider.resolve_security(target)
        quote = provider.fetch_quote(sec)
        daily = provider.fetch_qfq_daily(sec, days=10)
    except Exception as exc:
        return {"error": str(exc), "name": target, "symbol": target}

    current = quote.get("current_price")
    chg = quote.get("current_change_pct")
    return {
        "name": quote.get("name", target),
        "symbol": quote.get("symbol", target),
        "current_price": current,
        "current_change_pct": chg,
        "high": quote.get("high"),
        "low": quote.get("low"),
        "pre_close": quote.get("pre_close"),
        "volume": quote.get("volume"),
        "turnover_rate": quote.get("turnover_rate"),
        "trade_date": quote.get("trade_date"),
        "data_source": quote.get("data_source"),
        "_degraded": True,
        "daily_bars": daily,
    }

def _profile_enabled() -> bool:
    return os.environ.get("TRADER_PROFILE", "").strip() in ("1", "true", "True", "yes")


def build_report(target: str, cost_price: float = 0.0) -> dict[str, Any]:
    import time as _time
    _prof = _profile_enabled()
    _t0 = _time.perf_counter()
    _marks: list[tuple[str, float]] = []

    def _mark(label: str) -> None:
        if _prof:
            _marks.append((label, _time.perf_counter() - _t0))

    try:
        from trader_shared.data_provider import get_provider
        from trader_shared.candidate_core import atr_volatility_level  # noqa: F401 — 依赖探测
    except (ModuleNotFoundError, ImportError) as _ex:
        # 缺少 numpy/pandas 等计算依赖时降级为行情报告
        import warnings
        warnings.warn(f"[trader] 计算依赖缺失，降级为行情模式: {_ex}")
        return _degraded_quote_report(target)
    
    # DI: 注入 TencentFetcher 供下游模块使用
    fetcher = TencentFetcher()
    provider = get_provider()
    # 月线/ tick 默认不进主路径：月线在共振块按需补拉；tick 本报告未消费。
    # 周线必须拉（中线缠/威 + mid_key_prices）。
    snapshot = provider.load_market_snapshot(
        target,
        days=LOOKBACK_DAYS,
        include_5m=True,
        include_weekly=True,
        include_monthly=False,
        include_ticks=False,
    )
    _mark("snapshot")
    if not snapshot.quote or not snapshot.daily_bars:
        detail = "; ".join(f"{key}: {value}" for key, value in snapshot.source_errors.items()) or "missing required market data"
        raise RuntimeError(detail)

    sec = snapshot.security
    quote = snapshot.quote
    bars = list(snapshot.daily_bars)  # copy to avoid mutating snapshot

    # === 上下文：信号/插件/区间套/资金环境（report_pipeline.run_analysis_context_stage）===
    from trader_shared.report_pipeline import StageContext, run_analysis_context_stage

    _ctx = StageContext.from_mapping(
        run_analysis_context_stage(
            target=target,
            snapshot=snapshot,
            bars=bars,
            quote=quote,
            sec=sec,
            provider=provider,
            mark=_mark,
        )
    )
    risk_flags = _ctx.risk_flags
    _signal_cost_price = _ctx.signal_cost_price
    _signal_win_rate = _ctx.signal_win_rate
    live_bar = _ctx.live_bar
    intraday_as_of = _ctx.intraday_as_of
    bars_5m = _ctx.bars_5m
    weekly_bars = _ctx.weekly_bars
    monthly_bars = _ctx.monthly_bars
    atr14_val = _ctx.atr14_val
    atr_ratio_val = _ctx.atr_ratio_val
    atr_level = _ctx.atr_level
    atr_cap = _ctx.atr_cap
    atr_adjust = getattr(_ctx, "atr_adjust", None) or "unknown"
    atr_data_source = getattr(_ctx, "atr_data_source", None) or ""
    current = _ctx.current
    recent20 = _ctx.recent20
    change_pct_val = _ctx.change_pct_val
    _st = _ctx.st
    _st_dir = _ctx.st_dir
    chan_result = _ctx.chan_result
    chan_mid_result = _ctx.chan_mid_result
    wyck_result = _ctx.wyck_result
    wyck_mid_result = _ctx.wyck_mid_result
    momentum_result = _ctx.momentum_result
    _vwap_res = _ctx.vwap_res
    main_force_env = _ctx.main_force_env
    mf_result = _ctx.mf_result
    fund_flow_features = _ctx.fund_flow_features
    big_order_result = _ctx.big_order_result
    env = _ctx.env
    _sector_data = _ctx.sector_data

    # === 融合层（阶段函数：report_pipeline.run_fusion_stage）===
    from trader_shared.report_pipeline import run_fusion_stage

    report_fusion, _pre_cards, volume_warning = run_fusion_stage(
        chan_result=chan_result,
        momentum_result=momentum_result,
        wyck_result=wyck_result,
        bars=bars,
        env=env,
        quote=quote,
        current=current,
        main_force_env=main_force_env,
        fetcher=fetcher,
        data_status=snapshot.data_status,
        fund_flow_features=fund_flow_features,
        snapshot=snapshot,
        target=target,
        sector_data=_sector_data if isinstance(_sector_data, dict) else None,
        mark=_mark,
    )
    _fusion_pre_cards_pending: dict[str, Any] = _pre_cards or {}

    # === 结构层（阶段函数：report_pipeline.run_structure_stage）===
    from trader_shared.report_pipeline import run_structure_stage

    # 持仓票启用移动止损水位（只紧不松）；无持仓不落水位，避免无仓误抬止损
    _trail_sym = None
    if float(cost_price or 0) > 0 or float(_signal_cost_price or 0) > 0:
        _trail_sym = str(quote.get("symbol") or getattr(sec, "ts_code", "") or "").strip() or None
    levels, big_order_result, _pre_stage = run_structure_stage(
        current=current,
        bars=bars,
        bars_5m=bars_5m,
        quote=quote,
        report_fusion=report_fusion,
        chan_result=chan_result,
        wyck_result=wyck_result,
        momentum_result=momentum_result,
        mf_result=mf_result,
        main_force_env=main_force_env,
        fetcher=fetcher,
        big_order_result=big_order_result,
        order_book=snapshot.order_book,
        mark=_mark,
        trailing_ratchet_symbol=_trail_sym,
    )

    support = levels["main_support"]
    resistance = levels["resistance"]
    confirm = levels["confirm_price"]
    stop = levels["hard_stop"]
    take = levels["take"]
    # key_pressure 为大单分析提供关注价位（确认位优先，次选阻力位）
    levels["key_pressure"] = confirm if confirm > 0 else resistance
    # 使用约5个交易日前的收盘价作为周收盘价的近似
    # 注意：这是5/20个交易日前的日线收盘价，非真实周/月K线
    if len(bars) >= 5:
        weekly_proxy_close = float(bars[-5]["close"])
    else:
        weekly_proxy_close = float(bars[0]["close"])
    monthly_proxy_close = float(bars[-STRUCTURE_WINDOW]["close"] if len(bars) >= STRUCTURE_WINDOW else bars[0]["close"])
    stage = determine_stage(current, weekly_proxy_close, monthly_proxy_close)
    scene = levels["status"]
    base_status = str(levels.get("base_status") or scene)
    theory_status = str(levels.get("theory_status") or scene)
    replay = structure_replay(recent20)
    volume_text = volume_observation(recent20, bars_5m)
    high = max((to_float(b.get("high")) for b in recent20), default=current)
    low = min((to_float(b.get("low")) for b in recent20), default=current)
    analysis_time = f"{quote.get('trade_date')} {quote.get('trade_time') or ''}".strip()

    state_label = state_text(stage, theory_status)
    volume_note = volume_view(volume_text)
    market_env_data = env  # 复用并行块已抓取的大盘环境，避免重复请求
    buy_scenes = {"低吸观察", "防守观察", "等转强"}
    position_cap = min(10, atr_cap) if scene in buy_scenes else 10

    # === 筹码/EXPMA/共振（阶段函数：report_pipeline.run_chip_enrichment_stage）===
    from trader_shared.report_pipeline import StageContext, run_chip_enrichment_stage

    _enrich = StageContext.from_mapping(
        run_chip_enrichment_stage(
            bars=bars,
            bars_5m=bars_5m,
            current=current,
            target=target,
            quote=quote,
            ts_code=sec.ts_code,
            support=support,
            resistance=resistance,
            weekly_bars=weekly_bars,
            weekly_proxy_close=weekly_proxy_close,
            mf_result=mf_result,
            big_order_result=big_order_result,
            levels=levels,
            report_fusion=report_fusion,
            provider=provider,
            snapshot=snapshot,
            mark=_mark,
        )
    )
    chip = _enrich.chip
    chip_peaks = _enrich.chip_peaks
    chip_migration = _enrich.chip_migration
    chip_support = _enrich.chip_support
    chip_resistance = _enrich.chip_resistance
    chip_support_lower = _enrich.chip_support_lower
    chip_support_upper = _enrich.chip_support_upper
    chip_resistance_lower = _enrich.chip_resistance_lower
    chip_resistance_upper = _enrich.chip_resistance_upper
    main_force_score_result = _enrich.main_force_score_result
    expma10_val = _enrich.expma10_val
    expma12_val = _enrich.expma12_val
    expma20_val = _enrich.expma20_val
    expma50_val = _enrich.expma50_val
    expma_trend = _enrich.expma_trend
    expma_status_result = _enrich.expma_status_result
    resonance_result = _enrich.resonance_result

    # === 四阶段定位（阶段函数：report_pipeline.run_stage_positioning_stage）===
    from trader_shared.report_pipeline import (
        assemble_base_report,
        run_stage_positioning_stage,
    )

    _stage_pack = StageContext.from_mapping(
        run_stage_positioning_stage(
            bars=bars,
            current=current,
            quote=quote,
            levels=levels,
            atr14_val=atr14_val,
            chip_migration=chip_migration,
            chip_support_lower=chip_support_lower,
            chip_resistance_lower=chip_resistance_lower,
            chip_resistance_upper=chip_resistance_upper,
            report_fusion=report_fusion,
            wyck_result=wyck_result,
            mf_result=mf_result,
            chan_result=chan_result,
            ts_code=sec.ts_code,
            extend_sector=snapshot.extend_sector,
            pre_stage=_pre_stage,
            support=support,
            confirm=confirm,
        )
    )
    stage_result = _stage_pack.stage_result
    ma250 = _stage_pack.ma250
    bars_date = _stage_pack.bars_date
    upward_momentum = _stage_pack.upward_momentum
    take = _stage_pack.take

    report = assemble_base_report(
        intraday_as_of=intraday_as_of,
        quote=quote,
        sec=sec,
        analysis_time=analysis_time,
        current=current,
        weekly_proxy_close=weekly_proxy_close,
        monthly_proxy_close=monthly_proxy_close,
        support=support,
        resistance=resistance,
        confirm=confirm,
        stop=stop,
        take=take,
        stage=stage,
        scene=scene,
        levels=levels,
        replay=replay,
        volume_text=volume_text,
        upward_momentum=upward_momentum,
        low=low,
        high=high,
        snapshot=snapshot,
        bars=bars,
        risk_flags=risk_flags,
        atr14_val=atr14_val,
        atr_ratio_val=atr_ratio_val,
        atr_level=atr_level,
        atr_cap=atr_cap,
        atr_adjust=atr_adjust,
        atr_data_source=atr_data_source,
        st=_st,
        st_dir=_st_dir,
        vwap_res=_vwap_res,
        base_status=base_status,
        theory_status=theory_status,
        state_label=state_label,
        volume_note=volume_note,
        market_env_data=market_env_data,
        position_cap=position_cap,
        ma250=ma250,
        chip=chip,
        chip_peaks=chip_peaks,
        chip_support=chip_support,
        chip_resistance=chip_resistance,
        chip_support_lower=chip_support_lower,
        chip_support_upper=chip_support_upper,
        chip_resistance_lower=chip_resistance_lower,
        chip_resistance_upper=chip_resistance_upper,
        report_fusion=report_fusion,
        main_force_score_result=main_force_score_result,
        big_order_result=big_order_result,
        stage_result=stage_result,
        wyck_result=wyck_result,
        wyck_mid_result=wyck_mid_result,
        chan_result=chan_result,
        chan_mid_result=chan_mid_result,
        expma10_val=expma10_val,
        expma12_val=expma12_val,
        expma20_val=expma20_val,
        expma50_val=expma50_val,
        expma_trend=expma_trend,
        expma_status_result=expma_status_result,
        resonance_result=resonance_result,
        sector_data=_sector_data,
        fusion_pre_cards=_fusion_pre_cards_pending,
    )

    from trader_shared.report_pipeline import attach_stage_position_pack

    report, cost_price, has_position, suggested = attach_stage_position_pack(
        report,
        cost_price=float(cost_price or 0),
        current=float(current or 0),
        market_env_data=market_env_data if isinstance(market_env_data, dict) else {},
        stage_result=stage_result,
        atr14_val=atr14_val,
        bars=bars,
        wyck_result=wyck_result,
        support=support,
        confirm=confirm,
        expma10_val=expma10_val,
        expma20_val=expma20_val,
        chip_migration=chip_migration,
        levels=levels,
        bars_date=bars_date,
        base_status=str(base_status or ""),
        theory_status=str(theory_status or ""),
        scene=str(scene or ""),
        report_fusion=report_fusion if isinstance(report_fusion, dict) else {},
        signal_win_rate=_signal_win_rate,
        signal_cost_price=float(_signal_cost_price or 0),
        stage=str(stage or ""),
        mark=_mark,
    )


    from trader_shared.report_pipeline import attach_short_midline_and_decision

    # 短中线 + 决策栈（pipeline）
    attach_short_midline_and_decision(
        report,
        current=current,
        scene=str(scene or ""),
        report_fusion=report_fusion if isinstance(report_fusion, dict) else {},
        stage_result=stage_result,
        weekly_bars=weekly_bars or [],
        suggested=suggested,
        theory_status=str(theory_status or ""),
        market_env_data=market_env_data if isinstance(market_env_data, dict) else {},
        has_position=has_position,
        data_status=str(getattr(snapshot, "data_status", None) or report.get("data_status") or ""),
        chip_resistance_lower=chip_resistance_lower,
        chip_resistance_upper=chip_resistance_upper,
        stage=str(stage or ""),
        mark=_mark,
    )

    _mark("assemble")
    if _prof and _marks:
        # 累计 + 段耗时（后一项减前一项），便于定位 assemble 内部大头
        prev = 0.0
        segs: list[str] = []
        for lab, sec in _marks:
            delta = sec - prev
            segs.append(f"{lab}=+{delta:.3f}s")
            prev = sec
        total = _time.perf_counter() - _t0
        line = f"[TRADER_PROFILE] {target} total={total:.3f}s " + " ".join(segs)
        _logger.info(line)
        print(line, file=sys.stderr)

    return report

def determine_stage(current: float, weekly: float, monthly: float) -> str:
    if current > weekly > monthly:
        return "走强"
    if current >= weekly and weekly <= monthly:
        return "修复"
    if current >= monthly * 0.98:
        return "震荡"
    return "转弱"

def structure_replay(bars: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks(bars, 5):
        if not chunk:
            continue
        start = float(chunk[0].get("close", 0) or 0)
        end = float(chunk[-1].get("close", 0) or 0)
        change = pct_change(start, end)
        if change >= 4:
            label = "拉升窗口"
        elif change <= -4:
            label = "下跌窗口"
        elif change >= 1:
            label = "反弹窗口"
        elif change <= -1:
            label = "回踩窗口"
        else:
            label = "震荡窗口"
        start_date = short_date(chunk[0].get("date", ""))
        end_date = short_date(chunk[-1].get("date", ""))
        parts.append(f"{start_date}-{end_date} {label}（{change:+.2f}%）")
    return "；".join(parts[:4])

def sync_report_with_data(report: dict, levels: dict) -> dict:
    """兼容 re-export：实现已迁至 report_pipeline。"""
    from trader_shared.report_pipeline import sync_report_with_data as _sync
    return _sync(report, levels)



def _calc_volume_ratio_from_bars(bars: list[dict], window: int = 5) -> float:
    """兼容 re-export：实现已迁至 report_pipeline。"""
    from trader_shared.report_pipeline import _calc_volume_ratio_from_bars as _impl
    return _impl(bars, window=window)

# Re-export presentation API so external consumers (run_analysis.py) are unaffected.
from .report_presentation import (
    _fusion_breakdown,
    _get_buy_label,
    _get_kelly_data,
    _get_major_stage,
    _signal_direction_text,
    _signal_type_label,
    action_text_for_scene,
    build_watch_alert,
    chunks,
    generate_alert,
    ma_text,
    numeric_values,
    pct,
    price,
    render_markdown,
    short_date,
    signal_max_total_pct,
    signal_risk_flags,
    signal_state,
    structure_view,
    today_text,
    upward_momentum_observation,
    volume_observation,
    volume_view,
)

