# -*- coding: utf-8 -*-
"""快照后上下文：信号/ATR/并行资金环境/插件分析/区间套/VWAP。"""
from __future__ import annotations

import os
from typing import Any

from trader_shared._logging import get_logger
from trader_shared.report_pipeline._common import MarkFn, _noop_mark
from trader_shared.report_pipeline.prelude import build_live_bar_anchor, detect_risk_flags

_logger = get_logger(__name__)


def run_analysis_context_stage(
    *,
    target: str,
    snapshot: Any,
    bars: list,
    quote: dict[str, Any],
    sec: Any,
    provider: Any,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """自 snapshot 就绪后至融合前的上下文打包。

    会就地改 quote（注入 _bars_5m）。
    现价缺失时在返回字段 ``data_status='partial'``（不改 frozen MarketSnapshot）。
    返回供融合/结构/组装使用的上下文字段。
    """
    from trader_shared import get_env_for_skill
    from trader_shared.cache_utils import get_shared_build_pool
    from trader_shared.candidate_core import atr_volatility_level
    from trader_shared.config import STRUCTURE_WINDOW
    from trader_shared.indicator_math import calc_supertrend, calc_vwap
    from trader_shared.signal_core import read_signals_for_report

    _mark = mark or _noop_mark

    stock_name = str(quote.get("name") or sec.name or target)
    risk_flags = detect_risk_flags(stock_name, quote, bars)
    _signal_cost_price, _signal_win_rate = read_signals_for_report(target, bars)
    live_bar, intraday_as_of = build_live_bar_anchor(quote, bars)

    bars_5m = snapshot.bars_5m
    weekly_bars = snapshot.weekly_bars if hasattr(snapshot, "weekly_bars") else []
    monthly_bars = snapshot.monthly_bars if hasattr(snapshot, "monthly_bars") else []
    last_bar = bars[-1] if bars else {}
    _atr14_raw = last_bar.get("atr14")
    _atr_ratio_raw = last_bar.get("atr_ratio")
    try:
        atr14_val = float(_atr14_raw) if _atr14_raw is not None else 0.0
    except (TypeError, ValueError):
        atr14_val = 0.0
    try:
        atr_ratio_val = float(_atr_ratio_raw) if _atr_ratio_raw is not None else 0.0
    except (TypeError, ValueError):
        atr_ratio_val = 0.0
    atr_level, atr_cap = atr_volatility_level(atr_ratio_val) if atr14_val > 0 else ("数据不足", 10)
    atr_adjust = str(last_bar.get("adjust") or "unknown")
    atr_data_source = str(last_bar.get("data_source") or "")
    _cp = quote.get("current_price")
    current = _cp if _cp is not None else (bars[-1]["close"] if bars else None)
    if current is None:
        raise RuntimeError("current price unavailable")
    current = float(current)
    # MarketSnapshot 为 frozen，禁止赋值；降级状态走返回字段
    data_status = str(getattr(snapshot, "data_status", None) or "full")
    if _cp is None:
        data_status = "partial"

    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    change_pct_val = quote.get("current_change_pct")

    def _fetch_fund_flow():
        from trader_shared.cache_utils import fetch_fund_flow_cached
        from trader_shared.main_force import detect_main_force_stage

        # 必须用代码/ts_code；中文名会让资金流接口空返回 → 主力阶段退化合成
        _ff_key = (
            getattr(sec, "ts_code", None)
            or getattr(sec, "code", None)
            or quote.get("symbol")
            or target
        )
        ff_data = fetch_fund_flow_cached(str(_ff_key))
        if ff_data:
            daily_flow = ff_data.get("daily_flow", [])
            features = ff_data.get("features", {})
        else:
            daily_flow = []
            features = {}
        mf = detect_main_force_stage(features, bars)
        if daily_flow:
            today_record = daily_flow[-1] if daily_flow else {}
            mf["today_super_large_wan"] = float(today_record.get("super_large_wan", 0) or 0)
            mf["today_large_wan"] = float(today_record.get("large_wan", 0) or 0)
        else:
            mf["today_super_large_wan"] = 0.0
            mf["today_large_wan"] = 0.0
        mf["net_flow_pct"] = features.get("net_flow_pct", 0)
        return mf, features

    def _fetch_market_env():
        from trader_shared.market_env import resolve_board_index

        idx_code, _idx_label = resolve_board_index(sec)
        return get_env_for_skill("trader", index_code=idx_code)

    def _fetch_sector_data():
        # enrich 已写入 extend_sector（同源 tushare 快照）时直接复用，避免同票双拉
        ext = getattr(snapshot, "extend_sector", None)
        if isinstance(ext, dict) and ext.get("status") == "正常":
            return {
                "industry": ext.get("industry") or "",
                "sector_name": ext.get("sector_name") or "",
                "sector_code": ext.get("sector_code") or "",
                "sector_change_pct": float(ext.get("sector_change_pct") or 0),
                "status": "正常",
                "stock_vs_sector": ext.get("stock_vs_sector") or "",
            }
        try:
            from trader_shared.sector_data import get_stock_sector_snapshot_cached

            return get_stock_sector_snapshot_cached(sec.ts_code)
        except Exception as e:
            _logger.debug("板块数据获取失败: %s", e)
            return None

    pool = get_shared_build_pool()
    quote["_bars_5m"] = bars_5m
    f_mf = pool.submit(_fetch_fund_flow)
    f_env = pool.submit(_fetch_market_env)
    f_sector = pool.submit(_fetch_sector_data)

    _st = calc_supertrend(bars)
    _st_dir = _st.get("direction")

    from trader_shared.plugin_registry import get_registry

    _registry = get_registry()
    # VWAP/Supertrend 已在本 stage 直算写入报告；跳过 display_only 插件避免双算
    _plugin_results = _registry.analyze_all(
        current,
        bars,
        change_pct_val,
        quote,
        weekly_bars=weekly_bars,
        midline=True,
        supertrend_direction=_st_dir,
        include_display=False,
    )
    _mark("plugins")
    chan_result = _plugin_results.get("chanlun") or {}

    if os.environ.get("TRADER_CHAN_NESTING") != "0":
        try:
            from trader_shared.chan_nesting import confirm_nested_chain

            if isinstance(chan_result, dict) and provider is not None:
                _levels = os.environ.get("TRADER_CHAN_NESTING_LEVELS", "30m").split(",")
                _levels = [lv.strip() for lv in _levels if lv.strip()]
                _code_map = {"30m": "30", "5m": "5", "1m": "1"}
                _datalen_map = {"30m": 800, "5m": 1000, "1m": 1200}
                _series = []
                for _lv in _levels:
                    _code = _code_map.get(_lv, _lv)
                    _datalen = _datalen_map.get(_lv, 800)
                    try:
                        # 快照已有 5m 时复用，少一次分钟线请求
                        if _lv == "5m" and bars_5m:
                            _lb = list(bars_5m)
                        else:
                            _lb = provider.fetch_kline(snapshot.security, _code, _datalen)
                    except Exception as _fe:
                        _logger.debug("[nesting] 取 %s 失败: %s", _lv, _fe)
                        _lb = None
                    if _lb:
                        # 区间套只用已收盘分钟棒，避免 forming OHLC 假确认/假否决
                        try:
                            from trader_shared.t0_price_point_engine import completed_bars

                            _mins = {"30m": 30, "5m": 5, "1m": 1}.get(_lv, 5)
                            _lb = completed_bars(_lb, _mins)
                        except Exception as _ce:
                            _logger.debug("[nesting] 完成棒过滤跳过 %s: %s", _lv, _ce)
                        if _lb:
                            _series.append((_lv, _lb))
                if _series:
                    chan_result = confirm_nested_chain(chan_result, _series, symbol=target)
        except Exception as _nest_e:
            _logger.debug("[nesting] 区间套确认跳过: %s", _nest_e)
    _mark("nesting")

    chan_mid_result = _plugin_results.get("chanlun_midline") or {}
    wyck_result = _plugin_results.get("wyckoff") or {}
    wyck_mid_result = _plugin_results.get("wyckoff_midline") or {}
    momentum_result = _plugin_results.get("momentum") or {}
    _vwap_res = calc_vwap(bars_5m, current_price=current)

    main_force_env = "unknown"
    mf_result: dict[str, Any] = {}
    fund_flow_features: dict[str, Any] = {}
    try:
        mf_raw = f_mf.result()
        if isinstance(mf_raw, tuple) and len(mf_raw) == 2:
            mf_result = mf_raw[0] or {}
            fund_flow_features = mf_raw[1] or {}
        else:
            mf_result = mf_raw or {}
        main_force_env = mf_result.get("stage", "unknown")
    except Exception:
        pass

    big_order_result: dict[str, Any] = {
        "events": [],
        "summary": "暂无明显大单回溯。",
        "direction_summary": "暂无明显方向。",
        "total_hands": None,
        "total_amount_wan": None,
        "by_side": {"主动买入": None, "主动卖出": None},
        "validation": None,
    }

    try:
        env = f_env.result()
    except Exception:
        env = {"level": "未知", "hmm_regime_en": "range"}

    sector_data = None
    try:
        sector_data = f_sector.result()
    except Exception:
        pass
    _mark("fund_env_sector")

    return {
        "risk_flags": risk_flags,
        "signal_cost_price": _signal_cost_price,
        "signal_win_rate": _signal_win_rate,
        "live_bar": live_bar,
        "intraday_as_of": intraday_as_of,
        "bars_5m": bars_5m,
        "weekly_bars": weekly_bars,
        "monthly_bars": monthly_bars,
        "atr14_val": atr14_val,
        "atr_ratio_val": atr_ratio_val,
        "atr_level": atr_level,
        "atr_cap": atr_cap,
        "atr_adjust": atr_adjust,
        "atr_data_source": atr_data_source,
        "data_status": data_status,
        "current": current,
        "recent20": recent20,
        "change_pct_val": change_pct_val,
        "st": _st,
        "st_dir": _st_dir,
        "chan_result": chan_result,
        "chan_mid_result": chan_mid_result,
        "wyck_result": wyck_result,
        "wyck_mid_result": wyck_mid_result,
        "momentum_result": momentum_result,
        "vwap_res": _vwap_res,
        "main_force_env": main_force_env,
        "mf_result": mf_result,
        "fund_flow_features": fund_flow_features,
        "big_order_result": big_order_result,
        "env": env,
        "sector_data": sector_data,
    }
