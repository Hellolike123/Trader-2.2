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
    """单票报告编排：单一 StageContext bag，阶段结果 ctx.update，禁止平行 locals。"""
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

    from trader_shared.report_pipeline import (
        StageContext,
        assemble_base_report,
        attach_short_midline_and_decision,
        attach_stage_position_pack,
        run_analysis_context_stage,
        run_chip_enrichment_stage,
        run_fusion_merge_stage,
        run_pre_cards_stage,
        run_stage_positioning_stage,
        run_structure_stage,
    )

    provider = get_provider()
    try:
        from trader_shared.light_data import ensure_market_direct_network
        ensure_market_direct_network()
    except Exception:
        pass
    # 月线/ tick 默认不进主路径：月线在共振块按需补拉；tick 本报告未消费。
    # 周线必须拉（中线缠/威 + mid_key_prices）。
    # 数据 SSOT = get_provider；不再构造死 DI TencentFetcher（下游 fetcher 形参可传 None）。
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
        missing = list(getattr(snapshot, "missing_sources", None) or [])
        if not snapshot.quote and "quote" not in missing:
            missing.append("quote")
        if not snapshot.daily_bars and "daily" not in missing:
            missing.append("daily")
        err_bits = [
            f"{key}: {value}"
            for key, value in (getattr(snapshot, "source_errors", None) or {}).items()
        ]
        detail = "; ".join(err_bits) if err_bits else "no source_errors"
        raise RuntimeError(
            "missing required market data"
            f" | missing={missing or ['quote/daily']}"
            f" | data_status={getattr(snapshot, 'data_status', '?')}"
            f" | detail={detail}"
        )

    sec = snapshot.security
    quote = snapshot.quote
    bars = list(snapshot.daily_bars)  # copy to avoid mutating snapshot

    # Holdings SSOT：显式 --cost 优先；否则用 holdings.json（非 signals track）
    try:
        from trader_shared.holdings import resolve_cost_price

        _hold_sym = str(
            quote.get("symbol") or getattr(sec, "ts_code", "") or ""
        ).strip()
        cost_price = resolve_cost_price(_hold_sym, explicit_cost=float(cost_price or 0))
    except Exception:
        pass

    # 单一 bag：各 stage 写入后不再爆炸成平行 locals
    ctx = StageContext(
        target=target,
        cost_price=float(cost_price or 0),
        fetcher=None,  # 兼容下游签名；禁止再构造死 DI
        provider=provider,
        snapshot=snapshot,
        sec=sec,
        quote=quote,
        bars=bars,
    )

    # === 上下文：信号/插件/区间套/资金环境 ===
    ctx.update(
        run_analysis_context_stage(
            target=ctx.target,
            snapshot=ctx.snapshot,
            bars=ctx.bars,
            quote=ctx.quote,
            sec=ctx.sec,
            provider=ctx.provider,
            mark=_mark,
        )
    )
    # 现价缺失等降级由 context 返回，不改 frozen snapshot
    ctx.data_status = str(
        ctx.get("data_status")
        or getattr(ctx.snapshot, "data_status", None)
        or "full"
    )
    ctx.atr_adjust = ctx.get("atr_adjust") or "unknown"
    ctx.atr_data_source = ctx.get("atr_data_source") or ""

    # === 预产分析卡（早；merge 在 stage_pack 后）===
    # 法源：resonance-and-orchestration.md §6 #5 — pre_cards early; merge after stage_pack
    pre_cards, volume_warning = run_pre_cards_stage(
        chan_result=ctx.chan_result,
        momentum_result=ctx.momentum_result,
        wyck_result=ctx.wyck_result,
        bars=ctx.bars,
        quote=ctx.quote,
        fund_flow_features=ctx.fund_flow_features,
        snapshot=ctx.snapshot,
        target=ctx.target,
        sector_data=ctx.sector_data if isinstance(ctx.sector_data, dict) else None,
        mark=_mark,
    )
    ctx.update(
        fusion_pre_cards=pre_cards or {},
        volume_warning=volume_warning,
        report_fusion=None,  # merge 前无仪表
    )

    # === 结构层 ===
    # 持仓票启用移动止损水位（只紧不松）；无持仓不落水位
    # M3：仅 resolved cost>0 才落水位；信号流不得冒充持仓
    _trail_sym = None
    if float(ctx.cost_price or 0) > 0:
        _trail_sym = (
            str(
                ctx.quote.get("symbol")
                or getattr(ctx.sec, "ts_code", "")
                or ""
            ).strip()
            or None
        )
    # signal_cost_price 胜率仍用；不得驱动 watermark
    # structure/chip/stage 不消费 fusion（仪表）
    levels, big_order_result, pre_stage = run_structure_stage(
        current=ctx.current,
        bars=ctx.bars,
        bars_5m=ctx.bars_5m,
        quote=ctx.quote,
        chan_result=ctx.chan_result,
        wyck_result=ctx.wyck_result,
        momentum_result=ctx.momentum_result,
        mf_result=ctx.mf_result,
        main_force_env=ctx.main_force_env,
        fetcher=ctx.fetcher,
        big_order_result=ctx.big_order_result,
        order_book=ctx.snapshot.order_book,
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
    # 约5/STRUCTURE_WINDOW 交易日前收盘作周/月近似（非真实周/月K）
    bars = ctx.bars
    if len(bars) >= 5:
        weekly_proxy_close = float(bars[-5]["close"])
    else:
        weekly_proxy_close = float(bars[0]["close"])
    monthly_proxy_close = float(
        bars[-STRUCTURE_WINDOW]["close"]
        if len(bars) >= STRUCTURE_WINDOW
        else bars[0]["close"]
    )
    scene = levels["status"]
    base_status = str(levels.get("base_status") or scene)
    theory_status = str(levels.get("theory_status") or scene)
    recent20 = ctx.recent20
    volume_text = volume_observation(recent20, ctx.bars_5m)
    buy_scenes = {"低吸观察", "防守观察", "等转强"}
    ctx.update(
        levels=levels,
        big_order_result=big_order_result,
        pre_stage=pre_stage,
        support=support,
        resistance=resistance,
        confirm=confirm,
        stop=stop,
        take=take,
        weekly_proxy_close=weekly_proxy_close,
        monthly_proxy_close=monthly_proxy_close,
        scene=scene,
        base_status=base_status,
        theory_status=theory_status,
        replay=structure_replay(recent20),
        volume_text=volume_text,
        high=max((to_float(b.get("high")) for b in recent20), default=ctx.current),
        low=min((to_float(b.get("low")) for b in recent20), default=ctx.current),
        analysis_time=f"{ctx.quote.get('trade_date')} {ctx.quote.get('trade_time') or ''}".strip(),
        state_label=state_text("", theory_status),
        volume_note=volume_view(volume_text),
        market_env_data=ctx.env,  # 复用并行块大盘环境
        position_cap=min(10, ctx.atr_cap) if scene in buy_scenes else 10,
    )

    # === 筹码/EXPMA/共振 ===
    ctx.update(
        run_chip_enrichment_stage(
            bars=ctx.bars,
            bars_5m=ctx.bars_5m,
            current=ctx.current,
            target=ctx.target,
            quote=ctx.quote,
            ts_code=ctx.sec.ts_code,
            support=ctx.support,
            resistance=ctx.resistance,
            weekly_bars=ctx.weekly_bars,
            weekly_proxy_close=ctx.weekly_proxy_close,
            mf_result=ctx.mf_result,
            big_order_result=ctx.big_order_result,
            levels=ctx.levels,
            provider=ctx.provider,
            snapshot=ctx.snapshot,
            mark=_mark,
        )
    )

    # === 四阶段定位 ===
    ctx.update(
        run_stage_positioning_stage(
            bars=ctx.bars,
            current=ctx.current,
            quote=ctx.quote,
            levels=ctx.levels,
            atr14_val=ctx.atr14_val,
            chip_migration=ctx.chip_migration,
            chip_support_lower=ctx.chip_support_lower,
            chip_resistance_lower=ctx.chip_resistance_lower,
            chip_resistance_upper=ctx.chip_resistance_upper,
            wyck_result=ctx.wyck_result,
            mf_result=ctx.mf_result,
            chan_result=ctx.chan_result,
            ts_code=ctx.sec.ts_code,
            extend_sector=ctx.snapshot.extend_sector,
            pre_stage=ctx.pre_stage,
            support=ctx.support,
            confirm=ctx.confirm,
        )
    )
    # 字段纪律：report["stage"] 在 assemble 内别名 short_term_momentum
    ctx.short_term_momentum = str((ctx.stage_result or {}).get("momentum") or "震荡")
    ctx.stage = ctx.short_term_momentum  # assemble/attach 兼容槽；assemble 仍以 momentum 为准

    # B2：assemble/attach 只收 StageContext（禁止 kwargs 爆炸）
    report = assemble_base_report(ctx)
    # context 降级覆盖 assemble 从 frozen snapshot 抄来的 data_status
    report["data_status"] = ctx.data_status
    # assemble 写 _fusion_pre_cards；fusion 占位，merge 后覆写

    report, cost_price, has_position, suggested = attach_stage_position_pack(
        report, ctx, mark=_mark
    )
    ctx.update(
        cost_price=cost_price,
        has_position=has_position,
        suggested=suggested,
    )

    # === 融合仪表 merge（stage_pack 后、短中线/决策栈前；不做 A2）===
    report_fusion = run_fusion_merge_stage(
        chan_result=ctx.chan_result,
        momentum_result=ctx.momentum_result,
        wyck_result=ctx.wyck_result,
        bars=ctx.bars,
        env=ctx.env if isinstance(ctx.env, dict) else {},
        quote=ctx.quote,
        current=float(ctx.current or 0),
        main_force_env=ctx.main_force_env,
        fetcher=ctx.fetcher,
        data_status=str(ctx.data_status or ""),
        fund_flow_features=ctx.fund_flow_features,
        snapshot=ctx.snapshot,
        volume_warning=ctx.volume_warning,
        analysis_cards=ctx.fusion_pre_cards if isinstance(ctx.fusion_pre_cards, dict) else {},
        mark=_mark,
    )
    report["fusion"] = report_fusion
    ctx.update(report_fusion=report_fusion)

    # 短中线 + 决策栈（纪律/策略仍见完整 fusion 仪表）
    attach_short_midline_and_decision(report, ctx, mark=_mark)

    _mark("assemble")
    if _prof and _marks:
        # 累计 + 段耗时（后一项减前一项），便于定位 assemble 内部大头
        prev = 0.0
        segs: list[str] = []
        for lab, elapsed in _marks:
            delta = elapsed - prev
            segs.append(f"{lab}=+{delta:.3f}s")
            prev = elapsed
        total = _time.perf_counter() - _t0
        line = f"[TRADER_PROFILE] {target} total={total:.3f}s " + " ".join(segs)
        _logger.info(line)
        print(line, file=sys.stderr)

    return report

def determine_stage(current: float, weekly: float, monthly: float) -> str:
    """轻量位置分类（走强/修复/震荡/转弱）。

    Deprecated for report payload：``report["stage"]`` 已别名 ``short_term_momentum``
    （EXPMA 路径）。本函数保留给外部/对照调用，勿再写入 assemble。
    """
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

