# -*- coding: utf-8 -*-
"""Domain layer: build_report orchestration + analysis.
Presentation (render_markdown + helpers) is in report_renderer.py."""

from __future__ import annotations

import sys

from pathlib import Path

from typing import Any

from datetime import date

import os

import json

import traceback

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent

from trader_shared.light_data import to_float, pct_change

from trader_shared.stage_positioning import (
    assess_stage, compute_exit_plan, compute_stage_stop, check_time_stop,
    evaluate_position_state, _detect_major_stage,
)

from trader_shared.fetchers import TencentFetcher

from trader_shared.indicator_math import aggregate_5m_to_60m, calc_supertrend, calc_vwap

from trader_shared.chip_core import analyze_chips_and_migration

from trader_shared.config import (
    LOOKBACK_DAYS, STRUCTURE_WINDOW, ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS, KELLY_MAX_TOTAL_POSITIONS, KELLY_MIN_TRADES,
)

try:
    from trader_shared.models import DATA_STATUS_MAP
except ImportError:
    DATA_STATUS_MAP: dict[str, str] = {
        "complete": "full", "partial": "partial",
        "degraded": "degraded", "failed": "degraded",
    }

from trader_shared import (
    conflicting_signals, get_market_level, get_market_note,
    write_stock, log, stats_by_type,
)

from trader_shared import get_env_for_skill

from trader_shared.signal_contract import assert_valid_signal

from trader_shared.signal_core import (
    clear_signals_cache, read_signals_for_report, load_historical_win_rate,
    get_pool_count, build_signal, one_sentence, state_text, _map_fusion_to_signal,
)

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
        from trader_shared import candidate_core as core
        from trader_shared.candidate_core import build_structure_context, atr_volatility_level
        from trader_shared.structure_core import find_key_levels
        from trader_shared.data_provider import get_provider
        from trader_shared.strategy_protocol import run_all
        from trader_shared.cache_utils import get_shared_build_pool
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

    from trader_shared.report_pipeline import (
        build_live_bar_anchor,
        detect_risk_flags,
        tag_fusion_as_instrument,
    )

    stock_name = str(quote.get("name") or sec.name or target)
    risk_flags = detect_risk_flags(stock_name, quote, bars)

    # 一次性读取 signals.jsonl：同时获取成本价和历史胜率（合并两次 I/O）
    _signal_cost_price, _signal_win_rate = read_signals_for_report(target, bars)

    # 当日实时价锚点：仅展示用，绝不并入 bars（避免污染策略计算）
    live_bar, intraday_as_of = build_live_bar_anchor(quote, bars)
    bars_5m = snapshot.bars_5m
    weekly_bars = snapshot.weekly_bars if hasattr(snapshot, "weekly_bars") else []
    monthly_bars = snapshot.monthly_bars if hasattr(snapshot, "monthly_bars") else []
    last_bar = bars[-1] if bars else {}
    atr14_val = float(last_bar.get("atr14", 0) or 0)
    atr_ratio_val = float(last_bar.get("atr_ratio", 0) or 0)
    atr_level, atr_cap = atr_volatility_level(atr_ratio_val) if atr14_val > 0 else ("数据不足", 10)
    _cp = quote.get("current_price")
    current = _cp if _cp is not None else bars[-1]["close"]
    if current is None:
        raise RuntimeError("current price unavailable")
    current = float(current)
    # 当 quote 缺少 current_price 时，标记数据降级
    if _cp is None:
        snapshot.data_status = "partial"

    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars

    # 并行运行：主力资金 + 大盘环境 + 板块（策略分析经 PluginRegistry 组合点，见下文）
    change_pct_val = quote.get("current_change_pct")

    def _fetch_fund_flow():
        from trader_shared.cache_utils import fetch_fund_flow_cached
        from trader_shared.fund_flow_data import calc_fund_flow_features
        from trader_shared.main_force import detect_main_force_stage
        ff_data = fetch_fund_flow_cached(target)
        if ff_data:
            daily_flow = ff_data.get("daily_flow", [])
            features = ff_data.get("features", {})
        else:
            daily_flow = []
            features = {}
        # 始终调用 detect_main_force_stage：有 real flow 时用 real flow，无 real flow 时
        # detect_main_force_stage 内置 calc_fund_flow_features_from_bars K 线 fallback
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
        return get_env_for_skill("trader")

    def _fetch_sector_data():
        """个股行业 + 板块涨跌（日频缓存：当天复用、换日回源）。"""
        try:
            from trader_shared.sector_data import get_stock_sector_snapshot_cached
            return get_stock_sector_snapshot_cached(sec.ts_code)
        except Exception as e:
            _logger.debug(f"板块数据获取失败: {e}")
            return None

    # 复用全局共享线程池，避免嵌套 ThreadPoolExecutor 导致线程爆炸
    # cmd_refresh 内建 pool → build_report 内再建 pool → load_market_snapshot 内再建 pool
    # 现在三层共享同一个 max_workers=5 池
    pool = get_shared_build_pool()

    # 注入 5m 供 VwapPlugin 在 analyze_all 路径使用（与 build_report 直算结果一致）
    quote["_bars_5m"] = bars_5m

    # 主力资金 / 大盘环境 / 板块：与策略分析无依赖，尽早 submit，与 analyze_all 重叠
    f_mf = pool.submit(_fetch_fund_flow)
    f_env = pool.submit(_fetch_market_env)
    f_sector = pool.submit(_fetch_sector_data)

    # Supertrend 只算一次：方向给 momentum nudge，完整结果给展示
    _st = calc_supertrend(bars)
    _st_dir = _st.get("direction")

    # ── ADR-002：主路径分析统一经 PluginRegistry 组合点 ──
    # 日线三策略（chan/wyck/mom）+ 中线两策略（chan/wyck）经 analyze_all 组合；
    # weekly_bars 透传给 ChanlunPlugin，保证日线 chan 与直算等价（陷阱 #2 闸门）；
    # midline=True 才产出中线，避免 fusion_core / final_pool / review 的 analyze_all
    # 调用被波及（最小爆炸半径）。动量 nudge 由 analyze_all 内 MomentumPlugin 完成，
    # 此处不再重复（否则双重微调导致 weighted_score 漂移）。
    from trader_shared.plugin_registry import get_registry
    _registry = get_registry()
    _plugin_results = _registry.analyze_all(
        current, bars, change_pct_val, quote,
        weekly_bars=weekly_bars,
        midline=True,
        supertrend_direction=_st_dir,
    )
    _mark("plugins")
    chan_result = _plugin_results.get("chanlun") or {}        # 日线；_chan_to_signal 会自己剥

    # ── 区间套接入：日线买卖点经小级别（默认 30m，可扩 5m/1m 用于 T0）逐级确认 ──
    # 数据走 DataProvider.fetch_kline(sec, code, datalen)，生产环境本机 eastmoney/tdx 取数；
    # 异常（网络失败 / 门禁用 TRADER_CHAN_NESTING=0 禁用以保确定性）时跳过 →
    # chan_result 保持原样（等价性闸门：对未启用的环境零副作用）。
    # 层级由 TRADER_CHAN_NESTING_LEVELS 控制（逗号分隔，粗→细），默认 "30m"；
    # 设 "30m,5m,1m" 即开启 T0 精确定位。某级别取数失败仅该级别 skipped，不连累其它级别。
    # 批量 refresh 默认关 nesting（见 final_pool.cmd_refresh），单票精看可开。
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
                        _lb = provider.fetch_kline(snapshot.security, _code, _datalen)
                    except Exception as _fe:
                        _logger.debug(f"[nesting] 取 {_lv} 失败: {_fe}")
                        _lb = None
                    if _lb:
                        _series.append((_lv, _lb))
                if _series:
                    chan_result = confirm_nested_chain(chan_result, _series, symbol=target)
        except Exception as _nest_e:
            _logger.debug(f"[nesting] 区间套确认跳过: {_nest_e}")
    _mark("nesting")
    chan_mid_result = _plugin_results.get("chanlun_midline") or {}
    wyck_result = _plugin_results.get("wyckoff") or {}
    wyck_mid_result = _plugin_results.get("wyckoff_midline") or {}
    momentum_result = _plugin_results.get("momentum") or {}

    # VWAP：复用快照内 5 分钟 K 线，避免每次渲染重拉行情
    _vwap_res = calc_vwap(bars_5m, current_price=current)

    # 主力引擎结果（异常降级为 unknown）
    main_force_env = "unknown"
    mf_result = {}
    fund_flow_features = {}
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

    # 大单分析（初始空结果，稍后在 levels 计算后补全）
    big_order_result: dict[str, Any] = {"events": [], "summary": "暂无明显大单回溯。",
                                         "direction_summary": "暂无明显方向。",
                                         "total_hands": None, "total_amount_wan": None,
                                         "by_side": {"主动买入": None, "主动卖出": None},
                                         "validation": None}

    # 大盘环境结果（异常降级）
    try:
        env = f_env.result()
    except Exception:
        env = {"level": "未知", "hmm_regime_en": "range"}

    # 板块数据结果（snapshot 是不可变对象，用临时变量存储）
    _sector_data = None
    try:
        _sector_data = f_sector.result()
    except Exception:
        pass
    _mark("fund_env_sector")

    # === 融合层 ===
    # 预产卡先挂本地变量：report dict 更晚才组装，禁止在此写 report[...]
    _fusion_pre_cards_pending: dict[str, Any] = {}
    try:
        from trader_shared.fusion_core import merge_decisions
        from trader_shared.volume_price import detect_volume_divergence

        # 价量快照：始终传入（含平量），不再仅在有背离时塞入
        volume_warning = None
        try:
            from trader_shared.volume_price import volume_snapshot_dict
            vw = detect_volume_divergence(bars)
            if vw:
                volume_warning = volume_snapshot_dict(vw)
        except Exception:
            volume_warning = None

        # [Phase 2 - A1] 填充 stock_vs_sector（个股涨幅 - 板块涨幅）
        # extend_data 拿不到个股涨幅，故在 build_report 调用处补充到 extend_sector 字典。
        _stock_chg_pct = float(quote.get("current_change_pct") or 0)
        if _sector_data and isinstance(_sector_data, dict) and _sector_data.get("status") == "正常":
            _sector_chg_pct = float(_sector_data.get("sector_change_pct", 0) or 0)
            _vs = _stock_chg_pct - _sector_chg_pct
            if _vs > 0:
                _sector_data["stock_vs_sector"] = f"跑赢板块 +{_vs:.2f}%"
            elif _vs < 0:
                _sector_data["stock_vs_sector"] = f"跑弱板块 {_vs:.2f}%"
            else:
                _sector_data["stock_vs_sector"] = "与板块持平"

        # Arch C：融合前先产分析卡（策略/fusion 读卡入口）
        _pre_cards: dict = {}
        try:
            from trader_shared.analysis_cards import (
                build_chan_card,
                build_momentum_card,
                build_vpf_card,
                build_wyckoff_card,
            )
            from trader_shared.vpf_core import build_vpf_signal

            _pre_cards["chan"] = build_chan_card(chan_result, role="daily")
            _pre_cards["momentum"] = build_momentum_card(momentum_result, role="daily")
            _pre_cards["wyckoff"] = build_wyckoff_card(
                wyck_result, role="daily", symbol=str(getattr(sec, "ts_code", "") or target or ""),
            )
            # VPF 卡：与 merge 内 classic 路径同源输入，避免双源不一致
            _avg_to = None
            if bars and len(bars) >= 10:
                _amts = []
                for _b in bars[-20:]:
                    _a = _b.get("amount") if isinstance(_b, dict) else None
                    if _a is not None:
                        try:
                            _amts.append(float(str(_a).replace(",", "")))
                        except (TypeError, ValueError):
                            pass
                if _amts:
                    _avg_to = sum(_amts) / len(_amts) / 10000.0
            _vpf_raw = build_vpf_signal(
                volume_warning if isinstance(volume_warning, dict) else None,
                fund_flow_features if isinstance(fund_flow_features, dict) else None,
                bars=bars,
                avg_daily_turnover_wan=_avg_to,
            )
            _pre_cards["vpf"] = build_vpf_card(_vpf_raw, role="daily")
        except Exception as _pc_exc:
            _logger.debug("pre-fusion analysis_cards skip: %s", _pc_exc)
            _pre_cards = {}

        report_fusion = merge_decisions(
            chan_result=chan_result,
            momentum_result=momentum_result,
            wyckoff_result=wyck_result,
            regime=env.get("level", "正常"),
            current_price=current,
            bars=bars,
            hmm_regime=env.get("hmm_regime_en", "range"),
            main_force_env=main_force_env,
            fetcher=fetcher,
            data_status=snapshot.data_status,
            volume_warning=volume_warning,
            fund_flow_data=fund_flow_features,
            current_change_pct=_stock_chg_pct,
            extend_fundamental=snapshot.extend_fundamental,
            extend_sentiment=snapshot.extend_sentiment,
            extend_sector=snapshot.extend_sector,
            extend_concept=snapshot.extend_concept,
            extend_northbound=snapshot.extend_northbound,
            extend_margin=snapshot.extend_margin,
            analysis_cards=_pre_cards or None,
            # fusion 输入：缺省 cards（见 fusion_core._fusion_input_mode）；classic 强制回退
        )
        # 预产卡留给 ensure 合并（不污染 fusion 对外字段）
        if _pre_cards:
            _fusion_pre_cards_pending = _pre_cards
    except Exception as _e:
        _logger.warning(
            "merge_decisions 崩溃 (data_status=%s, symbol=%s):\n%s",
            snapshot.data_status, sec.ts_code if snapshot.security else "?",
            traceback.format_exc(),
        )
        report_fusion = {"action": "融合层异常", "confidence": 0, "weighted_score": 0,
                         "regime": "", "hmm_regime": "range", "disagreement": 0, "signals_detail": {}, "weights_used": {}}
    _mark("fusion")

    # 生成 fusion_verbatim（AI 原话直出，不可改写）
    try:
        _ws = float(report_fusion.get("weighted_score") or 0)
        _conf = float(report_fusion.get("confidence") or 0)
        _action = str(report_fusion.get("action") or "未知")
        _regime = str(report_fusion.get("regime") or "未知")
        _dis = float(report_fusion.get("disagreement") or 0)
        if _regime == "很差":
            _emoji = "🔴"
        elif _ws >= 0.25:
            _emoji = "🟢"
        elif _ws >= 0.1:
            _emoji = "🟡"      # 弱多
        elif _ws >= -0.05:
            _emoji = "⚪"
        elif _ws >= -0.12:
            _emoji = "🟡"      # 弱空
        elif _ws >= -0.2:
            _emoji = "🟠"      # 偏空
        else:
            _emoji = "🔴"
        _disclaimer = ""
        if _dis > 1:
            _disclaimer = "（信号冲突，建议等待）"
        elif _conf < 0.3:
            _disclaimer = "（信号弱，轻仓）"

        # 动作通俗解释
        _action_explain = {
            "高位观望": "不追高，等回调",
            "空仓/止损": "不买，有仓位要走",
            "减仓": "减仓锁定利润",
            "减1/3 (高位松动)": "减仓，高位有风险",
            "持股观望": "持有，等方向",
            "等转强观察": "等突破再买",
            "等转强": "等信号确认",
        }
        _explain = _action_explain.get(_action, "")

        _main_line = f"🎯 {_action}{_disclaimer}"
        if _explain:
            _main_line += f"\n  {_explain}"
        # 第二行：各维度状态（显示具体信号，不只方向）
        _sd = report_fusion.get("signals_detail") or {}
        _dim_parts = []
        for key, label in [("chan", "缠论"), ("momentum", "动量"), ("vpf", "价量资金")]:
            _sig = _sd.get(key)
            if isinstance(_sig, dict):
                _reason = str(_sig.get("reason", ""))
                # 去掉前缀，但保留冒号后的内容
                _short = _reason.replace("缠论", "").replace("威科夫", "").replace("动量", "").strip()
                if _short.startswith(":"):
                    _short = _short[1:]  # 去掉开头的冒号
                if not _short or _short == "无明确信号":
                    _dim_parts.append(f"{label}:无信号")
                elif key == "momentum" and "、" in _short:
                    # 动量信号可能很长，只取最后一个最重要的
                    _dim_parts.append(f"{label}:{_short.split('、')[-1]}")
                else:
                    _dim_parts.append(f"{label}:{_short}")
        _breakdown = f"  {'｜'.join(_dim_parts)}" if _dim_parts else ""
        report_fusion["fusion_verbatim"] = _main_line + ("\n" + _breakdown if _breakdown else "")
    except Exception:
        report_fusion["fusion_verbatim"] = "🎯 数据异常"

    # Volume Profile 计算
    vp_result = None
    try:
        from trader_shared.volume_profile import compute_volume_profile
        vp_result = compute_volume_profile(bars)
    except Exception:
        pass  # VP 可选，失败不影响主流程

    # C-7 fix: build_structure_context 现在在融合层之后调用，
    # 可以正确接收 fusion_result 和 chan_result
    # 快速阶段判定：传给 build_structure_context 用于止盈计算
    def _quick_ma(period: int) -> float | None:
        if len(bars) < period:
            return None
        valid_closes = [float(b.get("close") or 0) for b in bars[-period:] if float(b.get("close") or 0) > 0]
        return sum(valid_closes) / len(valid_closes) if valid_closes else None

    _pre_ma = {"ma5": _quick_ma(5), "ma10": _quick_ma(10),
               "ma20": _quick_ma(20), "ma30": _quick_ma(30)}
    _pre_stage, _, _, _ = _detect_major_stage(
        current, _pre_ma, bars,
        fusion_hint={"action": report_fusion.get("action"),
                     "confidence": report_fusion.get("confidence", 0),
                     "weighted_score": report_fusion.get("weighted_score", 0)},
        wyckoff_result=wyck_result,
        chan_result=chan_result,
        main_force_result=mf_result,
    )
    levels = build_structure_context(current, bars, quote.get("current_change_pct"), quote,
                                     fusion_result=report_fusion, chan_result=chan_result,
                                     fetcher=fetcher, vp_result=vp_result,
                                     major_stage=_pre_stage)
    _mark("structure")

    # 将理论策略结果合并到 levels（不覆盖 structure_core 的输出）
    for key, val in {"chanlun": chan_result, "wyckoff": wyck_result, "momentum": momentum_result}.items():
        if key not in levels:
            levels[key] = val

    # chan_result 带 chanlun 包装层，取内层用于 levels
    chan_inner = chan_result.get("chanlun", chan_result) if "chanlun" in chan_result else chan_result
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
    # wyckoff_strategy 返回 {"wyckoff": {...}}，需解包内层再取字段
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

    # P0-4: 多周期支撑压力阶梯
    try:
        levels["key_levels"] = find_key_levels(bars)
    except Exception:
        levels["key_levels"] = {
            "short_support": 0.0, "mid_support": 0.0, "long_support": 0.0,
            "short_resist": 0.0, "mid_resist": 0.0, "long_resist": 0.0,
        }

    # 大单分析（在 levels 计算后补全，使用 key_pressure 作为关注区）
    if big_order_result.get("events") is None or not big_order_result.get("events"):
        try:
            from trader_shared.big_order import analyze_big_orders
            big_order_result = analyze_big_orders(bars_5m, focus_prices=levels.get("key_pressure"),
                                                   trade_date=quote.get("trade_date"),
                                                   order_book=snapshot.order_book) if bars_5m else big_order_result
        except Exception:
            pass

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

    tushare_chip_data = None
    try:
        from trader_shared.chip_data import get_cyq_perf_cached
        # 日频：当天第一次拉网，同日再分析直接读缓存（换日失效）
        _cyq = get_cyq_perf_cached(sec.ts_code, start_date="", end_date="")
        if _cyq:
            # cyq_perf 接口按 trade_date 降序返回（最新在前）。须取最新交易日，
            # 不能取 _cyq[-1]（那是 2018 年的老数据，会导致获利盘数字完全失真）。
            _latest = max(_cyq, key=lambda x: str(x.get("trade_date", "")))
            _winner_rate = float(_latest.get("winner_rate", 0) or 0)
            _cost_50 = float(_latest.get("cost_50pct", 0) or 0)
            _peaks = []
            for _pct_key, _share in [("cost_5pct", 5), ("cost_15pct", 15), ("cost_50pct", 50), ("cost_85pct", 85), ("cost_95pct", 95)]:
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
        _logger.warning("Tushare cyq_perf fallback to internal calc: %s", e)

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

    # 主力行为独立评分（15分制）
    main_force_score_result: dict[str, Any] = {"total_score": 0, "flow_score": 0, "chip_score": 0,
                                                 "order_score": 0, "detail": {}, "label": "🔴无数据"}
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

    # EXPMA 计算（提前到 report 构造之前）
    expma10_val = None
    expma12_val = None
    expma20_val = None
    expma50_val = None
    expma_trend = "无数据"
    try:
        from trader_shared.indicator_math import calc_expma_series
        closes_for_expma = [float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0]
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
        # EXPMA 趋势判断
        if expma10_val and expma20_val and expma50_val:
            if expma10_val > expma20_val > expma50_val:
                expma_trend = "多头排列"
            elif expma10_val < expma20_val < expma50_val:
                expma_trend = "空头排列"
            else:
                expma_trend = "交叉震荡"
        elif expma10_val and expma20_val:
            if expma10_val > expma20_val:
                expma_trend = "短期偏多"
            else:
                expma_trend = "短期偏空"
    except Exception:
        pass

    # EXPMA 详细状态（10分制）
    expma_status_result: dict[str, Any] = {
        "total_score": 0, "alignment_score": 0, "slope_score": 0,
        "cross_score": 0, "deviation_score": 0,
        "expma_values": {}, "trend_label": "数据不足", "detail": {},
    }
    try:
        closes_for_expma = [float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0]
        if len(closes_for_expma) >= 10:
            from trader_shared.expma_status import calc_expma_status
            expma_status_result = calc_expma_status(closes_for_expma, current, bars)
    except Exception:
        pass

    # 多时间窗共振（13分制）
    resonance_result: dict[str, Any] = {
        "total_score": 0, "monthly_score": 0, "weekly_score": 0, "daily_score": 0,
        "timing_score": 0, "sell_timing_score": 0, "resonance_score": 0,
        "monthly_label": "无数据", "weekly_label": "无数据", "daily_label": "无数据",
        "timing_label": "无数据", "sell_timing_label": "无数据", "resonance_label": "无数据",
        "detail": {},
    }
    try:
        from trader_shared.multi_timeframe_resonance import calc_resonance
        res_d_closes = [float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0]
        _support_f = float(support) if support else 0
        _resistance_f = float(resistance) if resistance else 0
        if res_d_closes and len(res_d_closes) >= 10:
            # 将5分钟线聚合为60分钟线
            bars_60m = aggregate_5m_to_60m(bars_5m) if bars_5m else []
            # 月线按需：主 snapshot 默认不拉；共振需要时再补（失败则空，月分记无数据）
            monthly_bars = list(getattr(snapshot, "monthly_bars", None) or [])
            if not monthly_bars:
                try:
                    monthly_bars = list(provider.fetch_monthly(snapshot.security) or [])
                except Exception as _me:
                    _logger.debug("monthly fetch for resonance skipped: %s", _me)
                    monthly_bars = []
            resonance_result = calc_resonance(
                daily_closes=res_d_closes,
                current_price=current,
                weekly_bars=weekly_bars or [],  # 使用真实周线数据，fallback 到空列表
                weekly_close=weekly_proxy_close,  # 传入5日前收盘价作为周线代理
                bars_60m=bars_60m,  # 聚合后的60分钟线
                daily_support=_support_f,
                daily_resistance=_resistance_f,
                monthly_bars=monthly_bars or [],  # 月线K线数据
            )
    except Exception:
        pass
    _mark("resonance")

    # 60分钟卖点确认 → 提升融合层卖方置信度
    # 注：买方 timing 信号已通过 weighted_score 正值体现，此处仅对卖方补充置信度
    _sell_timing = resonance_result.get("sell_timing_score", 0)
    if _sell_timing >= 1 and report_fusion.get("weighted_score", 0) < 0:
        _boost = 0.05 * _sell_timing  # +0.05 per sell_timing point
        report_fusion["confidence"] = min(0.95, report_fusion.get("confidence", 0) + _boost)

    # Inject chip resistance into resistance levels
    if chip_resistance and chip_resistance > current:
        levels["resistance_levels"].append({"name": "筹码阻力", "price": round(chip_resistance, 2), "weight": 0.95})
        from trader_shared.structure_core import choose_level
        _new_res = choose_level(levels["resistance_levels"], current, below=False)
        levels["resistance"] = round(float(_new_res["price"]), 2)
        levels["resistance_source"] = _new_res["name"]
    levels["chip_resistance"] = chip_resistance

    # Inject chip support into support levels
    if chip_support and chip_support < current:
        levels["support_levels"].append({"name": "筹码支撑", "price": round(chip_support, 2), "weight": 0.95})
        from trader_shared.structure_core import choose_level
        _new_sup = choose_level(levels["support_levels"], current, below=True)
        levels["support"] = round(float(_new_sup["price"]), 2)
        levels["support_source"] = _new_sup["name"]
    levels["chip_support"] = chip_support

    # 四阶段定位
    ma_raw_v = levels.get("ma_values") or {}
    closes_250 = [to_float(b.get("close")) for b in bars[-250:] if to_float(b.get("close")) is not None]
    ma250 = sum(closes_250) / len(closes_250) if len(closes_250) >= 250 else None

    # C2 fix: extract trade_date from bars/quote for multi-day confirmation
    bars_date = ""
    if bars and len(bars) > 0:
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
        symbol=sec.ts_code,
        trade_date=bars_date,
        fusion_hint={
            "action": report_fusion.get("action"),
            "confidence": report_fusion.get("confidence", 0),
            "weighted_score": report_fusion.get("weighted_score", 0),
        },
        wyckoff_result=wyck_result,
        main_force_result=mf_result,
        chan_result=chan_result,
        extend_sector=snapshot.extend_sector,
        chip_support_lower=chip_support_lower or 0.0,
        chip_resistance_lower=chip_resistance_lower or 0.0,
        chip_resistance_upper=chip_resistance_upper or 0.0,
    )

    # 修复：止盈应使用保护后的阶段（与仓位/止损一致）
    protected_stage = stage_result["major_stage"]
    if protected_stage != _pre_stage:
        resistance_price = levels.get("resistance") or 0
        if protected_stage in ('蓄势', '蓄势偏强'):
            take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
        elif protected_stage == '主升':
            take = round(resistance_price, 2) if resistance_price else round(current * 1.10, 2)
        elif protected_stage == '派发':
            take = round(current, 2)
        elif protected_stage == '蓄势偏弱':
            take = round(resistance_price * 0.98, 2) if resistance_price else round(current, 2)
        elif protected_stage == '衰退':
            take = None
        else:
            take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
        if take is not None:
            take = max(take, current)
        levels["take"] = take

    # 用 major_stage 替代旧 stage 计算 upward_momentum（修复 P1-4）
    upward_momentum = upward_momentum_observation(stage_result["major_stage"], current, support, confirm)

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
        "data_note": None,  # None = 正常分析，有值 = 离线/降级占位
        "bars": bars,  # daily_bars 的别名，供 score_report 兼容
        "risk_flags": risk_flags,  # ST / 停牌 / 新股
        # ═══ 缠论/威科夫（computed/手动赋值，auto-sync 不覆盖） ═══
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
        "supertrend_direction": _st_dir,
        # 渲染契约「多头/空头轨道价」：按当前方向取活动轨道价，
        # 保证空头(direction=="down")时 stop_short 也能展示。
        "supertrend_stop": (
            _st.get("stop_long") if _st_dir == "up"
            else _st.get("stop_short") if _st_dir == "down"
            else None
        ),
        "supertrend_atr": _st.get("atr"),
        "supertrend_vol_level": _st.get("vol_level"),
        "vwap": _vwap_res.get("vwap"),
        "vwap_dev": _vwap_res.get("deviation_pct"),
        "vwap_position": _vwap_res.get("position"),
        "vwap_level": _vwap_res.get("level"),
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
            # assess_stage 不回传 ma_values，ma250 从本地 closes_250 重算
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
        # 中线理论：威科夫/缠论独立周K；日线另存供 fusion / 短线专家
        # 中线字段禁止静默回退日线（R3 / 规格 B 源隔离）
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
        "chanlun_midline": chan_mid_result if chan_mid_result else {
            "chanlun": {"timeframe": "insufficient", "structure_type": "", "divergence": {}}
        },
        "expma10": expma10_val,
        "expma12": expma12_val,
        "expma20": expma20_val,
        "expma50": expma50_val,
        "expma_trend": expma_trend,
        "expma_status": expma_status_result,
        "resonance": resonance_result,
        "extend_fundamental": snapshot.extend_fundamental,
        "extend_sentiment": snapshot.extend_sentiment,
        # Phase 1 新增：资金面数据（仅展示，不参与评分）
        "extend_margin": snapshot.extend_margin,
        "extend_northbound": snapshot.extend_northbound,
        "extend_sector": _sector_data,
        # Phase 2 新增：概念板块数据（仅展示，不参与评分）
        "extend_concept": snapshot.extend_concept,
    }
    # 融合前预产卡（ensure 阶段再 merge 进 analysis_cards）
    if _fusion_pre_cards_pending:
        report["_fusion_pre_cards"] = _fusion_pre_cards_pending

    # ═══ 自动同步：levels → report ═══
    # INTERNAL_LEVELS 只用于 build_report 内部计算，不应暴露给下游
    _INTERNAL_LEVELS = frozenset({
        # 原始中间值（已在 report 中用不同名字暴露）
        "status", "confirm_price", "hard_stop", "main_support", "main_resistance",
        "support_source", "resistance_source",
        # 内部计算列表
        "resistance_levels", "support_levels",
        # 原始结构数据（已在 report 中以简化形式暴露）
        "chan_buy_points", "chan_sell_points",
        "chan_zone_last_price", "chan_zone_first_price",
        # 详细区域（report 只暴露 low_zone 字符串）
        "low_zone_lower", "low_zone_upper",
        # 原始 MA 计算结果（已在 report 中以 "ma" 暴露）
        "ma_values",
        # 主力数据原始结果（已在 report 中暴露为 main_force_score）
        "main_force", "main_force_env",
        # 威科夫原始结果（已在 report 中暴露为 wyckoff + wyckoff_spring_signal）
        "wyckoff_summary",
        # 其他中间值
        "fus_score", "fus_disagree", "fus_override",
        "fus_override_used",
    })
    for _key, _val in levels.items():
        if _key not in _INTERNAL_LEVELS:
            report.setdefault(_key, _val)

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
    """从日K线计算量比（近N日均量 / 前N日均量）。"""
    if len(bars) < 2 * window:
        return 0.0

    # 切片：前半部分是旧数据，后半部分是新数据
    older = bars[-2 * window:-window]
    newer = bars[-window:]

    older_vols = []
    newer_vols = []
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

