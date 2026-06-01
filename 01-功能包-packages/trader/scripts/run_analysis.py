#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.light_data import to_float, pct_change
from trader_shared.stage_positioning import assess_stage, compute_exit_plan, compute_stage_stop, check_time_stop, evaluate_position_state
from trader_shared.fetchers import TencentFetcher

try:
    from trader_shared.chip_distribution import calc_chip_distribution as _calc_chip
except ImportError:
    def _calc_chip(daily, lookback=60):
        return {"peaks": [], "total_volume": 0, "current_pct": None, "mid_price": None}

try:
    from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
    _CHIP_MIGRATION_AVAILABLE = True
except ImportError:
    _CHIP_MIGRATION_AVAILABLE = False
    def save_chip_snapshot(target, chip_result, trade_date=None): pass
    def check_chip_migration(target, chip_result): return {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}
from config import (
    LOOKBACK_DAYS,
    STRUCTURE_WINDOW,
)
from trader_shared.light_data import to_float, pct_change
try:
    from trader_shared.models import DATA_STATUS_MAP
except ImportError:
    DATA_STATUS_MAP: dict[str, str] = {
        "complete": "full",
        "partial": "partial",
        "degraded": "degraded",
        "failed": "degraded",
    }

_run_analysis_shared_failed = False

try:
    from trader_shared import conflicting_signals, get_market_level, get_market_note, write_stock, log, stats_by_type
    from trader_shared import get_env_for_skill
    track_log = log
except ImportError:
    import warnings
    if not _run_analysis_shared_failed:
        _run_analysis_shared_failed = True
        warnings.warn(
            "[trader] shared module not available — market status, signal tracking, and pool operations are disabled. "
            "The report will still be generated but may lack market context and pool integration.",
            stacklevel=2,
        )

    def _empty_str(*a, **k): return ""
    def _empty_list(*a, **k): return []
    def _empty_dict(*a, **k): return {}
    def _empty_fn(*a, **k): return None
    conflicting_signals = _empty_list
    get_market_level = _empty_str
    get_market_note = _empty_str
    get_env_for_skill = _empty_dict
    write_stock = _empty_fn
    track_log = _empty_fn
    stats_by_type = _empty_dict



from trader_shared.signal_contract import assert_valid_signal
from datetime import date
import os

def _get_cost_from_signals(target: str) -> float:
    """从 signals.jsonl 中获取买入成本价（只读最近100条）。"""
    try:
        signals_path = os.path.expanduser("~/.trader/signals.jsonl")
        if not os.path.exists(signals_path):
            return 0.0
        
        # 标准化 target 用于匹配
        normalized_target = target.replace(".SH", "").replace(".SZ", "").strip()
        
        # 只读最近100条，避免大文件性能问题
        with open(signals_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-100:]
            for line in lines:
                try:
                    signal = json.loads(line.strip())
                    symbol = str(signal.get("symbol", "")).replace(".SH", "").replace(".SZ", "").strip()
                    name = str(signal.get("name", "")).strip()
                    
                    # 匹配股票代码或名称
                    if symbol == normalized_target or name == normalized_target:
                        signal_type = signal.get("signal_type", "")
                        # 查找买入信号
                        if signal_type in ("low_buy_triggered", "track"):
                            trigger = signal.get("trigger", {})
                            price = trigger.get("price", 0)
                            if price > 0:
                                return float(price)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        pass
    return 0.0


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
        "data_source": quote.get("data_source"),
        "_degraded": True,
        "daily_bars": daily,
    }


def today_text() -> str:
    return date.today().isoformat()


CONTRACT_VERSION = "trader_single_action_v3"


_SIGNAL_TYPE_LABELS = {
    "observe": "观察",
    "wait_for_confirmation": "等待确认",
    "track": "跟踪",
    "low_buy_watch": "低吸观察",
    "low_buy_triggered": "低吸触发",
    "high_sell_watch": "高抛观察",
    "high_sell_triggered": "高抛触发",
    "reduce": "减仓",
    "defensive": "防守",
    "risk_stop": "止损",
    "trigger_expired": "信号过期",
    "blocked": "受压",
    "review_result": "复盘",
}


def _signal_type_label(sig_type: str) -> str:
    return _SIGNAL_TYPE_LABELS.get(sig_type, sig_type)


def _signal_direction_text(direction: int) -> str:
    if direction > 0:
        return "看多"
    if direction < 0:
        return "看空"
    return "中性"


def _fusion_breakdown(fusion: dict) -> list[str]:
    """生成融合层决策分解文本。"""
    rows = []
    action = fusion.get("action", "")
    score = fusion.get("weighted_score", 0)
    confidence = fusion.get("confidence", 0)
    regime = fusion.get("regime", "")
    hmm = fusion.get("hmm_regime", "")
    signals = fusion.get("signals_detail", {})
    weights = fusion.get("weights_used", {})
    disagreement = fusion.get("disagreement", 0)

    rows.append("")
    rows.append(f"  融合层：{action}（评分 {score:+.2f}，置信度 {confidence:.0%}）")

    if regime:
        hmm_cn = {"bull": "多头", "bear": "空头", "range": "震荡"}.get(hmm, hmm)
        rows.append(f"  大盘环境：{regime}（HMM: {hmm_cn}）")

    for key, label in [("chan", "缠论"), ("momentum", "动量"), ("wyckoff", "威科夫")]:
        sig = signals.get(key, {})
        if not sig:
            continue
        d = sig.get("direction", 0)
        c = sig.get("confidence", 0)
        w = weights.get(key, 0)
        rows.append(f"    {label}：{_signal_direction_text(d)}（置信 {c:.0%}，权重 {w:.0%}）")

    if disagreement > 1:
        rows.append(f"  注意：多信号存在分歧（分歧度 {disagreement:.1f}），优先采纳缠论/威科夫方向")

    return rows


_FUSION_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "半仓试 (多方主导)": ("track", "bullish", "track"),
    "半仓试 (多方主导但有分歧)": ("track", "bullish", "track"),
    "增持": ("track", "bullish", "track"),
    "持股观望": ("wait_for_confirmation", "bullish_lean", "observe"),
    "减仓": ("defensive", "bearish", "wait"),
    "空仓/止损": ("defensive", "bearish", "wait"),
    # T-11 fix: 补全 3 个缺失的融合层 Action 映射，避免决策被静默丢弃
    "空仓 (大盘很差, 一票否决)": ("risk_stop", "bearish", "stop"),
    "观望 (信号冲突)": ("observe", "neutral", "observe"),
    "等转强 (多方主导但有分歧)": ("wait_for_confirmation", "bullish_lean", "observe"),
}


def _map_fusion_to_signal(fusion_action: str) -> tuple[str, str, str] | None:
    if not fusion_action:
        return None
    return _FUSION_ACTION_MAP.get(fusion_action.strip())


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def pct(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"


def build_report(target: str, cost_price: float = 0.0) -> dict[str, Any]:
    try:
        import candidate_core as core
        from trader_shared.candidate_core import build_structure_context, atr_volatility_level
        from trader_shared.data_provider import get_provider
        from trader_shared.strategy_protocol import run_all
    except (ModuleNotFoundError, ImportError) as _ex:
        # 缺少 numpy/pandas 等计算依赖时降级为行情报告
        import warnings
        warnings.warn(f"[trader] 计算依赖缺失，降级为行情模式: {_ex}")
        return _degraded_quote_report(target)
    
    # DI: 注入 TencentFetcher 供下游模块使用
    fetcher = TencentFetcher()
    provider = get_provider()
    snapshot = provider.load_market_snapshot(target, days=LOOKBACK_DAYS, include_5m=True)
    if not snapshot.quote or not snapshot.daily_bars:
        detail = "; ".join(f"{key}: {value}" for key, value in snapshot.source_errors.items()) or "missing required market data"
        raise RuntimeError(detail)

    sec = snapshot.security
    quote = snapshot.quote
    bars = snapshot.daily_bars
    bars_5m = snapshot.bars_5m
    last_bar = bars[-1] if bars else {}
    atr14_val = float(last_bar.get("atr14", 0) or 0)
    atr_ratio_val = float(last_bar.get("atr_ratio", 0) or 0)
    atr_level, atr_cap = atr_volatility_level(atr_ratio_val) if atr14_val > 0 else ("数据不足", 10)
    _cp = quote.get("current_price")
    current = _cp if _cp is not None else bars[-1]["close"]
    if current is None:
        raise RuntimeError("current price unavailable")
    current = float(current)

    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    from trader_shared.chan_core import chanlun_strategy
    from trader_shared.wyckoff_core import wyckoff_strategy
    from trader_shared.momentum_core import momentum_strategy
    from concurrent.futures import ThreadPoolExecutor

    # 并行运行五个独立任务：三策略 + 主力资金 + 大盘环境
    change_pct_val = quote.get("current_change_pct")

    def _fetch_fund_flow():
        from trader_shared.cache_utils import fetch_fund_flow_cached
        from trader_shared.fund_flow_data import calc_fund_flow_features
        from trader_shared.main_force import detect_main_force_stage
        ff_data = fetch_fund_flow_cached(target)
        if ff_data:
            daily_flow = ff_data.get("daily_flow", [])
            features = ff_data.get("features", {})
            if daily_flow:
                mf = detect_main_force_stage(features, bars)
                # 今日超大单/大单明细
                today_record = daily_flow[-1] if daily_flow else {}
                mf["today_super_large_wan"] = float(today_record.get("super_large_wan", 0) or 0)
                mf["today_large_wan"] = float(today_record.get("large_wan", 0) or 0)
                return mf
        return {}

    def _fetch_market_env():
        return get_env_for_skill("trader")

    with ThreadPoolExecutor(max_workers=5) as executor:
        f_chan = executor.submit(chanlun_strategy, current, bars, change_pct_val, quote)
        f_wyk = executor.submit(wyckoff_strategy, current, bars, change_pct_val, quote)
        f_mom = executor.submit(momentum_strategy, current, bars, change_pct_val, quote)
        f_mf = executor.submit(_fetch_fund_flow)
        f_env = executor.submit(_fetch_market_env)

        chan_result = f_chan.result() or {}
        wyck_result = f_wyk.result() or {}
        momentum_result = f_mom.result() or {}

    # 主力引擎结果（异常降级为 unknown）
    main_force_env = "unknown"
    mf_result = {}
    try:
        mf_result = f_mf.result() or {}
        main_force_env = mf_result.get("stage", "unknown")
    except Exception:
        pass

    # 大盘环境结果（异常降级）
    try:
        env = f_env.result()
    except Exception:
        env = {"level": "未知", "hmm_regime_en": "range"}

    # === 融合层 ===
    try:
        from trader_shared.fusion_core import merge_decisions
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
        )
    except Exception:
        report_fusion = {"action": "融合层异常", "confidence": 0, "weighted_score": 0,
                         "regime": "", "hmm_regime": "range", "disagreement": 0, "signals_detail": {}, "weights_used": {}}

    # C-7 fix: build_structure_context 现在在融合层之后调用，
    # 可以正确接收 fusion_result 和 chan_result
    levels = build_structure_context(current, bars, quote.get("current_change_pct"), quote,
                                     fusion_result=report_fusion, chan_result=chan_result,
                                     fetcher=fetcher)

    # 将理论策略结果合并到 levels（不覆盖 structure_core 的输出）
    for key, val in {"chanlun": chan_result, "wyckoff": wyck_result, "momentum": momentum_result}.items():
        if key not in levels:
            levels[key] = val

    levels["chan_trend_label"] = chan_result.get("trend_label", "数据不足")
    levels["chan_buy_point_text"] = chan_result.get("buy_point_text", "无")
    levels["chan_buy_points"] = chan_result.get("buy_points", [])
    levels["chan_strokes_count"] = chan_result.get("strokes_count", 0)
    levels["chan_zone_last_price"] = chan_result.get("last_valid_zone_last_price")
    levels["chan_zone_first_price"] = chan_result.get("last_valid_zone_first_price")
    levels["chan_divergence"] = chan_result.get("divergence", {})
    levels["wyckoff_spring_signal"] = wyck_result.get("spring_signal", False)
    levels["wyckoff_summary"] = wyck_result.get("wyckoff_summary", "无明显信号")
    levels["wyckoff_upthrust_signal"] = wyck_result.get("upthrust_signal", False)
    levels["base_status"] = levels.get("base_status") or levels.get("status")
    levels["theory_status"] = levels.get("theory_status") or levels.get("status")
    levels["main_force"] = mf_result
    levels["main_force_env"] = main_force_env

    support = levels["main_support"]
    resistance = levels["resistance"]
    confirm = levels["confirm_price"]
    stop = levels["hard_stop"]
    take = levels["take"]
    weekly_close = float(bars[-1]["close"])
    monthly_close = float(bars[-STRUCTURE_WINDOW]["close"] if len(bars) >= STRUCTURE_WINDOW else bars[0]["close"])
    stage = determine_stage(current, weekly_close, monthly_close)
    scene = levels["status"]
    base_status = str(levels.get("base_status") or scene)
    theory_status = str(levels.get("theory_status") or scene)
    replay = structure_replay(recent20)
    volume_text = volume_observation(recent20, bars_5m)
    upward_momentum = upward_momentum_observation(stage, current, support, confirm)
    highs = numeric_values(recent20, "high")
    lows = numeric_values(recent20, "low")
    high = max(highs) if highs else current
    low = min(lows) if lows else current
    analysis_time = f"{quote.get('trade_date')} {quote.get('trade_time') or ''}".strip()

    state_label = state_text(stage, theory_status)
    structure_note = structure_view({
        "current": current, "confirm": confirm, "stage": stage,
        "ma": {"ma5": ma_text(levels["ma_values"].get("ma5")),
               "ma10": ma_text(levels["ma_values"].get("ma10")),
               "ma20": ma_text(levels["ma_values"].get("ma20")),
               "ma30": ma_text(levels["ma_values"].get("ma30"))},
        "scene": scene,
    })
    volume_note = volume_view(volume_text)
    market_env_data = get_env_for_skill("trader")
    buy_scenes = {"低吸观察", "防守观察", "等转强"}
    position_cap = min(10, atr_cap) if scene in buy_scenes else 10

    chip = _calc_chip(bars, lookback=60)
    chip_peaks = sorted(chip.get("peaks", []) or [], key=lambda x: x["price"])

    # 筹码搬家监控：保存快照 + 对比历史
    chip_migration = {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}
    if _CHIP_MIGRATION_AVAILABLE and chip_peaks:
        try:
            save_chip_snapshot(name, chip, trade_date=quote.get("trade_date"))
            chip_migration = check_chip_migration(name, chip)
        except Exception:
            pass

    chip_support: float | None = None
    chip_resistance: float | None = None
    if chip_peaks:
        support_peaks = [p for p in chip_peaks if p["price"] < current]
        if support_peaks:
            strong_near = sorted(
                [p for p in support_peaks if (current - p["price"]) / current <= 0.03],
                key=lambda p: float(p.get("share_of_total") or 0),
                reverse=True,
            )
            all_by_strong = sorted(support_peaks, key=lambda p: float(p.get("share_of_total") or 0), reverse=True)
            # If strongest > 2%, use it regardless of distance
            # Otherwise prefer strongest within 3%
            if all_by_strong and float(all_by_strong[0].get("share_of_total") or 0) > 2:
                chip_support = all_by_strong[0]["price"]
            elif strong_near:
                chip_support = strong_near[0]["price"]
            else:
                chip_support = support_peaks[-1]["price"]
        resistance_peaks = [p for p in chip_peaks if p["price"] > current]
        if resistance_peaks:
            strong_near = sorted(
                [p for p in resistance_peaks if (p["price"] - current) / current <= 0.03],
                key=lambda p: float(p.get("share_of_total") or 0),
                reverse=True,
            )
            all_by_strong = sorted(resistance_peaks, key=lambda p: float(p.get("share_of_total") or 0), reverse=True)
            if all_by_strong and float(all_by_strong[0].get("share_of_total") or 0) > 2:
                chip_resistance = all_by_strong[0]["price"]
            elif strong_near:
                chip_resistance = strong_near[0]["price"]
            else:
                chip_resistance = resistance_peaks[0]["price"]

    # 四阶段定位
    ma_raw_v = levels.get("ma_values") or {}
    closes_250 = [to_float(b.get("close")) for b in bars[-250:] if to_float(b.get("close")) is not None]
    ma250 = sum(closes_250) / len(closes_250) if len(closes_250) >= 250 else None

    stage_result = assess_stage(
        current=current,
        ma_values={**ma_raw_v, "ma250": ma250},
        change_pct=float(quote.get("current_change_pct") or 0),
        bars=bars,
        position_ratio=levels.get("position_ratio", 0.5),
        atr14=atr14_val,
        chip_migration=chip_migration,
    )

    report = {
        "name": quote.get("name") or sec.name,
        "symbol": quote.get("symbol") or sec.ts_code,
        "analysis_time": analysis_time,
        "current": current,
        "change_pct": quote.get("current_change_pct"),
        "weekly_close": weekly_close,
        "monthly_close": monthly_close,
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
        "missing_sources": snapshot.missing_sources,
        "source_errors": snapshot.source_errors,
        "fetched_at": snapshot.fetched_at,
        "ma": {
            "ma5": ma_text(levels["ma_values"].get("ma5")),
            "ma10": ma_text(levels["ma_values"].get("ma10")),
            "ma20": ma_text(levels["ma_values"].get("ma20")),
            "ma30": ma_text(levels["ma_values"].get("ma30")),
        },
        "atr14": atr14_val,
        "atr_ratio": atr_ratio_val,
        "atr_level": atr_level,
        "atr_cap": atr_cap,
        "base_status": base_status,
        "theory_status": theory_status,
        "state_label": state_label,
        "structure_note": structure_note,
        "volume_note": volume_note,
        "market_env": market_env_data,
        "position_cap": position_cap,
        "ma_raw": {
            "ma5": levels["ma_values"].get("ma5"),
            "ma10": levels["ma_values"].get("ma10"),
            "ma20": levels["ma_values"].get("ma20"),
            "ma30": levels["ma_values"].get("ma30"),
        },
        "chip_support": chip_support,
        "chip_resistance": chip_resistance,
        "fusion": report_fusion,
        "gap": levels.get("gap"),
        "time_window": levels.get("time_window"),
        "fib_retrace": levels.get("fib_retrace"),
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
        "wyckoff": wyck_result.get("wyckoff", wyck_result),
        "expma10": expma10_val,
        "expma12": expma12_val,
        "expma50": expma50_val,
        "expma_trend": expma_trend,
        # "extend_fundamental": snapshot.extend_fundamental,
        # "extend_sentiment": snapshot.extend_sentiment,
    }

    # 仓位计算（阶段 + 大盘环境）
    from trader_shared.stage_positioning import compute_position_with_env
    market_env_level = market_env_data.get("level", "震荡市")
    env_map = {"正常": "牛市", "偏弱": "震荡市", "很差": "熊市"}
    mapped_env = env_map.get(market_env_level, "震荡市")
    position_info = compute_position_with_env(
        stage=stage_result["major_stage"],
        momentum=stage_result["momentum"],
        market_env=mapped_env,
        pnl_pct=0.0,
        total_position_pct=0.0,
    )
    report["position_info"] = position_info

    # 分批止盈计划（仅在有持仓参考价时计算）
    entry_price = float(report.get("support") or current)  # 默认用支撑位作为参考买入价
    stop_price = float(report.get("stop") or 0)
    resistance_val = float(report.get("resistance") or 0)
    exit_plan = compute_exit_plan(
        entry_price=entry_price,
        stop_price=stop_price,
        resistance_price=resistance_val if resistance_val > 0 else None,
        current_stage=stage_result["major_stage"],
        bars=bars,
        wyckoff_result=wyck_result,
        atr14=atr14_val,
    )
    report["exit_plan"] = exit_plan
    report["chip_migration"] = chip_migration

    # 五状态仓位管理状态机 + EXPMA 计算
    expma10_val = None
    expma12_val = None
    expma50_val = None
    try:
        from trader_shared.momentum_core import calc_expma
        closes_for_expma = [float(b.get("close") or 0) for b in bars if float(b.get("close") or 0) > 0]
        if len(closes_for_expma) >= 10:
            expma_vals = calc_expma(closes_for_expma, 10)
            expma10_val = expma_vals[-1] if expma_vals else None
        if len(closes_for_expma) >= 12:
            expma12_vals = calc_expma(closes_for_expma, 12)
            expma12_val = expma12_vals[-1] if expma12_vals else None
        if len(closes_for_expma) >= 50:
            expma50_vals = calc_expma(closes_for_expma, 50)
            expma50_val = expma50_vals[-1] if expma50_vals else None
    except Exception:
        pass
    
    # EXPMA 趋势确认（金叉/死叉）
    expma_trend = "neutral"
    if expma12_val is not None and expma50_val is not None:
        if expma12_val > expma50_val:
            expma_trend = "bullish"  # EXPMA(12) 金叉 EXPMA(50) → 趋势转强
        elif expma12_val < expma50_val:
            expma_trend = "bearish"  # EXPMA(12) 死叉 EXPMA(50) → 趋势转弱

    # 已有持仓模式：确定成本价和持仓状态
    # 必须在 evaluate_position_state() 之前，以便传入正确的 has_position 和 entry_price
    if cost_price <= 0:
        # 从 signals.jsonl 中自动推断成本
        cost_price = _get_cost_from_signals(target)
    
    has_position = cost_price > 0
    report["has_position"] = has_position
    report["cost_price"] = cost_price
    
    # 如果有持仓，计算盈亏比例
    if has_position and cost_price > 0:
        pnl_pct = (current - cost_price) / cost_price * 100
        report["pnl_pct"] = pnl_pct
        report["pnl_text"] = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"

    # 使用成本价作为 entry_price（有持仓时），否则用支撑位
    entry_price_for_state = cost_price if has_position else float(report.get("support") or current)

    position_state = evaluate_position_state(
        current_price=current,
        support=support,
        resistance=float(report.get("resistance") or 0),
        stop_price=float(report.get("stop") or 0),
        confirm_price=confirm,
        atr14=atr14_val,
        major_stage=stage_result["major_stage"],
        momentum=stage_result["momentum"],
        bars=bars,
        wyckoff_result=wyck_result,
        has_position=has_position,
        entry_price=entry_price_for_state,
        highest_close=max([float(b.get("close") or 0) for b in bars[-20:]]) if bars else current,
        expma10=expma10_val,
        chip_migration=chip_migration,
    )
    report["position_state"] = position_state

    # 阶段止损
    ma20_val = levels["ma_values"].get("ma20")
    stage_stop_info = compute_stage_stop(
        stage=stage_result["major_stage"],
        ma20=ma20_val,
        range_low=float(report.get("range_low") or 0),
        atr_pct=float(levels.get("atr_pct") or 0.02),
    )
    report["stage_stop"] = stage_stop_info
    
    # 补全 JSON 输出需要的字段
    report = sync_report_with_data(report, levels)

    # one_liner: 一句话总结
    low_zone = str(report.get("low_zone") or f"{float(report.get('support', 0)):.2f}-{float(report.get('support', 0)) * 1.01:.2f}元")
    report["one_liner"] = one_sentence(report, low_zone)

    # t0_ref: T0 参考价位
    report["t0_ref"] = {
        "low_buy": float(report.get("support") or 0),
        "high_sell": float(report.get("confirm") or 0),
        "stop": float(report.get("stop") or 0),
    }

    # macd_status: MACD 方向
    mom = levels.get("momentum", {})
    if isinstance(mom, dict):
        macd = mom.get("macd", {})
        if isinstance(macd, dict):
            report["macd_status"] = {
                "histogram": macd.get("histogram"),
                "golden_cross": macd.get("golden_cross", False),
                "death_cross": macd.get("death_cross", False),
                "positive": macd.get("positive", False),
            }

    return report


def numeric_values(bars: list[dict[str, Any]], key: str) -> list[float]:
    return [value for value in (to_float(item.get(key)) for item in bars) if value is not None]


def ma_text(value: Any) -> str:
    return "--" if value is None else f"{float(value):.2f}"


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
        start = float(chunk[0]["close"])
        end = float(chunk[-1]["close"])
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
        parts.append(f"{short_date(chunk[0]['date'])}-{short_date(chunk[-1]['date'])} {label}（{change:+.2f}%）")
    return "；".join(parts[:4])


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def short_date(value: Any) -> str:
    text = str(value or "")
    return text[5:10] if len(text) >= 10 else text


def sync_report_with_data(report: dict, levels: dict) -> dict:
    """脚本自洽校验：修正数据与文字标签的矛盾"""
    current  = float(report.get("current") or 0)
    support  = float(report.get("support") or 0)
    resistance = float(report.get("resistance") or 0)
    confirm  = float(report.get("confirm") or 0)
    stop     = float(report.get("stop") or 0)
    take     = float(report.get("take") or 0)
    scene    = str(report.get("scene") or "")
    state_label  = str(report.get("state_label") or "")
    ma5  = to_float(levels.get("ma_values", {}).get("ma5"))
    ma10 = to_float(levels.get("ma_values", {}).get("ma10"))
    # MA 趋势与文字标签
    if ma5 is not None and ma10 is not None and current > 0:
        if ma5 > ma10 and "空头" in state_label:
            report["state_label"] = state_label.replace("空头", "多头")
        elif ma5 < ma10 and "多头" in state_label:
            report["state_label"] = state_label.replace("多头", "空头")
    # support > resistance → 筹码与 ATR 模块打架
    if support > 0 and resistance > 0 and support >= resistance:
        report["resistance"] = support * 1.03
        report["support"]    = resistance * 0.97
    # stop < support（止损永远在支撑下方）
    if stop > 0 and support > 0 and stop >= support:
        report["stop"] = round(support * 0.97, 2)
    # take < confirm（止盈永远高于确认位）
    if take > 0 and confirm > 0 and take <= confirm:
        report["take"] = max(current * 1.05, confirm * 1.03)
    # 场景与数值的逻辑一致性
    if scene in ("突破确认", "突破观察") and round(current, 2) < round(confirm, 2):
        report["scene"]        = "观望"
        report["state_label"]  = "未确认"
    elif scene in ("低吸观察", "防守观察") and current < support and support > 0:
        report["scene"]        = "破位下行"
        report["state_label"]  = "破位下行"
    elif scene == "冲高减仓" and current < support and support > 0:
        report["scene"]        = "低吸观察"
        report["state_label"]  = "低吸观察"
    elif scene == "突破观察" and current >= confirm and confirm > 0:
        report["scene"]        = "突破确认"
        report["state_label"]  = "趋势走强"
    elif scene in ("空间不足",) and current < support and support > 0:
        report["scene"]        = "修复观察"
        report["state_label"]  = "修复观察"
    return report


def volume_observation(daily: list[dict[str, Any]], bars_5m: list[dict[str, Any]]) -> str:
    if bars_5m and len(bars_5m) >= 12:
        recent = numeric_values(bars_5m[-6:], "volume")
        prior = numeric_values(bars_5m[-18:-6], "volume")
        prior_avg = sum(prior) / len(prior) if prior else 0
        recent_avg = sum(recent) / len(recent) if recent else 0
        if prior_avg > 0 and recent_avg / prior_avg >= 1.3:
            return "分时量能放大，冲高和破位都要等确认。"
        if prior_avg > 0 and recent_avg / prior_avg <= 0.75:
            return "分时量能收缩，更适合等缩量回踩后的承接。"
    if not daily:
        return "量能材料不足，先按关键价位执行。"
    max_day = max(daily, key=lambda item: to_float(item.get("volume")) or 0)
    close = to_float(max_day.get("close"))
    open_ = to_float(max_day.get("open"))
    direction = "收涨" if close is not None and open_ is not None and close >= open_ else "收跌"
    return f"近20根K线最大量能日在 {max_day.get('date')}，当天{direction}。"


def upward_momentum_observation(stage: str, current: float, support: float, confirm: float) -> str:
    width = max(confirm - support, current * 0.02)
    if current >= confirm:
        return f"价格已经触及启动确认区，结论：有启动迹象，但还要看放量站稳后的延续。"
    elif stage == "转弱":
        return f"趋势仍在弱区，结论：启动条件不足，先不做进攻判断。"
    elif current >= confirm - width * 0.25:
        return f"价格接近确认区但还未站稳，结论：属于预备启动，等待放量确认。"
    return f"价格还没贴近确认区，结论：动能仍是弱修复，暂不按启动处理。"


def render_markdown(r: dict[str, Any]) -> str:
    ma = r.get("ma") or {}
    display_code = str(r["symbol"]).replace(".SH", "").replace(".SZ", "")
    name = str(r["name"])

    atr14 = float(r.get("atr14", 0) or 0)
    atr_ratio = float(r.get("atr_ratio", 0) or 0)
    atr_level = str(r.get("atr_level") or "")
    atr_cap = int(r.get("atr_cap") or 10)

    confirm = float(r.get("confirm") or 0)
    low_price = float(r.get("support") or 0)
    stop = float(r.get("stop") or 0)
    scene = str(r.get("scene") or "")
    position_cap = int(r.get("position_cap") or 10)
    low_zone = str(r.get("low_zone") or f"{low_price:.2f}-{low_price * 1.01:.2f}元")

    fib_retrace = r.get("fib_retrace") or {}
    golden_bid = fib_retrace.get("golden_bid") if isinstance(fib_retrace, dict) else None
    golden_text = f" (黄金挂单位: {golden_bid:.2f})" if golden_bid else ""

    atr_header = f"｜ATR {atr14:.2f}（{atr_ratio*100:.0f}%）{atr_level}" if atr14 > 0 else ""
    gap = r.get("gap") or {}
    gap_text = gap.get("text", "") if isinstance(gap, dict) else ""
    gap_condition = gap.get("condition", "normal") if isinstance(gap, dict) else "normal"

    # 提取解禁一票否决信息
    fusion = r.get("fusion") or {}
    unlock_veto_msg = fusion.get("unlock_veto_msg") if isinstance(fusion, dict) else None

    major_stage = str(r.get("major_stage") or "")
    major_reason = str(r.get("major_reason") or "")
    momentum = str(r.get("short_term_momentum") or "")
    momentum_reason = str(r.get("momentum_reason") or "")
    stage_action = str(r.get("stage_action") or "")
    max_position_pct = int(r.get("max_position_pct") or 0)
    stage_label = str(r.get("stage_label") or "")

    # EXPMA 显示
    expma10 = r.get("expma10")
    expma12 = r.get("expma12")
    expma50 = r.get("expma50")
    expma_trend = r.get("expma_trend", "neutral")
    expma_text = ""
    if expma10 is not None:
        expma_text = f"EXPMA(10)：{expma10:.2f}"
        if expma12 is not None and expma50 is not None:
            trend_text = "金叉" if expma_trend == "bullish" else "死叉" if expma_trend == "bearish" else "震荡"
            expma_text += f"｜EXPMA(12/50)：{trend_text}"
    
    lines: list[str] = [
        f"分析报告 — {name}（{display_code}）",
        "",
        f"现价：{price(r['current'])}（{pct(r['change_pct'])}）",
        f"MA5：{ma.get('ma5', '--')}｜MA10：{ma.get('ma10', '--')}｜MA20：{ma.get('ma20', '--')}｜MA30：{ma.get('ma30', '--')}",
        f"ATR {atr14:.2f}（{atr_ratio*100:.0f}%）{atr_level}" if atr14 > 0 else "",
        expma_text if expma_text else "",
    ]
    if major_stage == "衰退":
        lines.append("")
        lines.append("⚠️ 250日线下方，一票否决，建议不参与")
        lines.append("（以下供参考，如有看好的票可忽略此提醒）")
    if unlock_veto_msg:
        lines.append(f"提示：⚠️ {unlock_veto_msg}，已被决策融合层一票否决")
        lines.append("")
    elif gap_text and gap_condition not in ("normal", "unknown"):
        lines.append(f"提示：{gap_text}")
        lines.append("")

    market_env = r.get("market_env") or {}
    env_level = market_env.get("level", "")
    skill_note = market_env.get("skill_note", "")
    trend_5d = market_env.get("trend_5d", "")
    change_pct = market_env.get("change_pct", 0.0)
    has_env = env_level and env_level not in ("未知", "")

    status_text = str(r.get("state_label") or "")
    base_status_text = str(r.get("base_status") or "")
    theory_status_text = str(r.get("theory_status") or status_text)

    if has_env:
        price_dir = "涨" if change_pct >= 0 else "跌"
        change_abs = abs(change_pct)
        lines.extend([
            "",
            "🌍 大盘",
            "",
            f"中证1000｜{env_level}｜今日{price_dir}{change_abs:.1f}%｜{skill_note}",
        ])
    else:
        lines.extend([
            "",
            "🌍 大盘",
            "",
            "中证1000｜数据不足",
        ])

    structure_note = str(r.get("structure_note") or "")
    volume_note = str(r.get("volume_note") or "")
    lines.extend([
        "",
        "🧭 阶段判断",
        "",
        f"大阶段：{major_stage}期",
        f"  {major_reason}",
        f"短期动能：{momentum}",
        f"  {momentum_reason}",
    ])

    # ✅ 趋势强势提示
    ma_raw = r.get("ma_raw") or {}
    ma5 = ma_raw.get("ma5")
    ma10 = ma_raw.get("ma10")
    ma20 = ma_raw.get("ma20")
    ma30 = ma_raw.get("ma30")
    ma250_val = r.get("ma250")
    try:
        current_price = float(r.get("current") or 0)
    except (TypeError, ValueError):
        current_price = 0.0
    if (ma250_val and current_price > 0 and current_price > ma250_val and
        ma5 and ma10 and ma20 and ma30 and ma250_val and
        ma5 > ma10 > ma20 > ma30 > ma250_val):
        lines.append("")
        lines.append("✅ 趋势强势：价格在 250 日线上方，均线多头排列")

    # 💰 主力资金（阶段判断之后、决策之前）
    mf = r.get("main_force") or {}
    if mf and mf.get("stage") and mf["stage"] != "unknown":
        try:
            from trader_shared.main_force_output import format_main_force_enhanced
            lines.append("")
            lines.append(format_main_force_enhanced(
                mf,
                today_super_large=float(mf.get("today_super_large_wan", 0) or 0),
                today_large=float(mf.get("today_large_wan", 0) or 0),
            ))
        except Exception:
            pass

    lines.extend([
        "",
        "📍 决策",
        "",
        f"{stage_label} → {stage_action}",
        f"  空仓 → 在 {low_zone} 试探买 {position_cap}%, 止损 {stop:.2f}{golden_text}",
        f"  有底仓 → 反弹 {confirm:.2f} 冲不动就减 10-20%, 跌破 {stop:.2f} 止损",
        f"  加仓 → 放量站稳 {confirm:.2f} 且回踩不破，才评估",
    ])

    # 止盈计划（仅在有持仓时显示，Bug fix: 空仓不显示止盈计划）
    exit_plan = r.get("exit_plan") or {}
    exit_plan_items = exit_plan.get("exit_plan") or []
    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)
    
    # 只有有持仓时才显示止盈计划
    if has_position and exit_plan_items and exit_plan.get("risk_r", 0) > 0:
        ep_entry = cost_price if cost_price > 0 else float(r.get("support") or current)
        lines.append("")
        lines.append(f"  止盈计划（参考买入价 {ep_entry:.2f}）")
        for idx, item in enumerate(exit_plan_items, 1):
            p = item.get("price")
            ratio = item.get("ratio", 0)
            reason = item.get("reason", "")
            # Bug fix: 第1笔也要显示具体价格（阻力位或1R目标）
            if p is not None:
                lines.append(f"    第{idx}笔：{p:.2f} 卖 {ratio:.0%}（{reason}）")
            else:
                # 如果没有价格，使用阻力位或1R目标作为参考
                resistance_val = float(r.get("resistance") or 0)
                target_1r = exit_plan.get("target_1r", 0)
                fallback_price = resistance_val if resistance_val > 0 else target_1r
                if fallback_price > 0:
                    lines.append(f"    第{idx}笔：{fallback_price:.2f} 卖 {ratio:.0%}（{reason}）")
                else:
                    lines.append(f"    第{idx}笔：{reason}")

    # 三层止损
    stage_stop = r.get("stage_stop") or {}
    stage_stop_price = stage_stop.get("price", 0)
    stage_stop_reason = stage_stop.get("reason", "")
    stop_losses = r.get("stop_losses") or {}
    tech_stop = stop_losses.get("technical", {}).get("price", 0)
    time_limit = stop_losses.get("time_limit", {})
    time_days = time_limit.get("days", 0)
    if tech_stop > 0 or stage_stop_price > 0:
        lines.append("")
        lines.append("  三层止损")
        parts = []
        if tech_stop > 0:
            parts.append(f"技术止损：{tech_stop:.2f}")
        if stage_stop_price > 0:
            parts.append(f"阶段止损：{stage_stop_price:.2f}")
        if time_days > 0:
            parts.append(f"时间止损：{time_days}天")
        lines.append(f"    {'｜'.join(parts)}")
        # 取最近的止损
        nearest_stop = max(tech_stop, stage_stop_price)
        if nearest_stop > 0:
            lines.append(f"    → 跌破 {nearest_stop:.2f} 减仓")

    # 仓位计算过程
    position_info = r.get("position_info") or {}
    if position_info:
        stage_pct = position_info.get("stage_position_pct", 0)
        env_limit = position_info.get("env_limit_pct", 0)
        env_name = position_info.get("market_env", "震荡市")
        suggested = position_info.get("suggested_pct", 0)
        blocked = position_info.get("hard_rule_blocked", False)
        block_reason = position_info.get("hard_rule_reason", "")

        lines.extend([
            f"  四阶段仓位：{stage_pct}%",
            f"  大盘环境：{env_name}",
            f"  单票上限：{env_limit}%",
        ])
        if blocked:
            lines.append(f"  → ❌ 硬规则阻止：{block_reason}")
        else:
            lines.append(f"  → 建议仓位：{suggested}%")
    if isinstance(fusion, dict) and fusion.get("action"):
        lines.extend(_fusion_breakdown(fusion))

    # 🎯 今日行动
    action_section = _build_today_action_section(r)
    if action_section:
        lines.extend(action_section)

    # 📊 已有持仓评估（如果有持仓）
    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)
    if has_position and cost_price > 0:
        position_section = _build_existing_position_section(r, cost_price)
        if position_section:
            lines.extend(position_section)

    # 🔔 信号提醒
    signal_section = _build_signal_alert_section(r)
    if signal_section:
        lines.extend(signal_section)

    # T0 参考
    lines.extend([
        "",
        "T0 参考",
        "",
        f"  低吸：{low_zone} ｜ 高抛：{confirm:.2f} ｜ 止损：{stop:.2f}",
    ])

    resistance_val = float(r.get("resistance", 0))
    chip_support = r.get("chip_support")
    chip_resistance = r.get("chip_resistance")
    ma_raw_v = r.get("ma_raw") or {}
    groups: dict[int, list[tuple[float, str]]] = {}
    trailing_stop_val = r.get("trailing_stop")
    if trailing_stop_val is not None and trailing_stop_val != stop:
        groups.setdefault(0, []).append((trailing_stop_val, "移动止损（ATR）"))
    if stop > 0:
        groups.setdefault(1, []).append((stop, "止损位（ATR）"))
    if low_price > 0 and abs(low_price - stop) > 0.01:
        groups.setdefault(1, []).append((low_price, "防守位（ATR）"))
    cost_v = None
    for v in sorted(filter(None, [ma_raw_v.get("ma10"), ma_raw_v.get("ma20"), ma_raw_v.get("ma30")])):
        if low_price < v < r["current"]:
            cost_v = v
            break
    if cost_v:
        groups.setdefault(2, []).append((cost_v, "成本密集区"))
    if chip_support is not None and chip_support > stop:
        g = 1 if chip_support < low_price else 2
        groups.setdefault(g, []).append((chip_support, "有量支撑"))
    groups.setdefault(3, []).append((r["current"], "当前位置"))
    if confirm > 0 and abs(confirm - r["current"]) > 0.01:
        groups.setdefault(3, []).append((confirm, "确认位（ATR）"))
    if resistance_val > 0 and resistance_val > confirm:
        groups.setdefault(4, []).append((resistance_val, "减仓位（ATR）"))
    if chip_resistance is not None and chip_resistance > r["current"]:
        g = 3 if chip_resistance < confirm else 4
        groups.setdefault(g, []).append((chip_resistance, "套牢压力区"))
    key_lines = ["", "❗ 关键价位", ""]
    last_group = 0
    for g in sorted(groups):
        items = sorted(groups[g], key=lambda x: x[0])
        for p, label in items:
            sep = "+ ←" if "套牢压力" in label else "  ←"
            if last_group and g != last_group:
                key_lines.append("  ┆")
            key_lines.append(f"{p:.2f}{sep} {label}")
            last_group = g
    lines.extend(key_lines)

    stage = str(r.get("stage") or "")

    if stage == "转弱" or scene in ("空间不足",):
        lines.extend([
            "",
            "⚠️ 风险",
            "",
            f"趋势已转弱不可恋战，反弹是减仓机会。若跌破 {low_price:.2f} 必须执行止损",
        ])
    elif scene in ("突破确认", "突破观察"):
        lines.extend([
            "",
            "✨ 亮点",
            "",
            f"现价 {r['current']:.2f} 已站上确认位 {confirm:.2f}，方向偏多 → 放量站稳继续持有",
            "",
            "⚠️ 风险",
            "",
            f"突破后回踩 {confirm:.2f} 不破才算确认，缩量冲高先不减",
        ])
    elif scene in ("低吸观察", "防守观察", "防守观察，趋势下行谨慎"):
        lines.extend([
            "",
            "✨ 亮点",
            "",
            f"价格回到支撑区 {low_price:.2f} 附近，观察止跌信号",
            "",
            "⚠️ 风险",
            "",
            f"趋势尚未确认，跌破 {low_price:.2f} 要止损，不提前抄底",
        ])
    elif scene == "冲高减仓":
        lines.extend([
            "",
            "✨ 亮点",
            "",
            "现价接近压力区，有反弹机会",
            "",
            "⚠️ 风险",
            "",
            f"冲高缩量先减仓，放量突破 {confirm:.2f} 再接回",
        ])
    else:
        lines.extend([
            "",
            "✨ 亮点",
            "",
            f"当前 {r['current']:.2f} 仍站在防守位 {low_price:.2f} 上方，结构在修复 → 等站稳 {confirm:.2f} 确认转强",
            "",
            "⚠️ 风险",
            "",
            f"最大风险不是没反弹，而是 {confirm:.2f} 未确认前提前追入。若跌破 {low_price:.2f} 防守位，预期要先收回来",
        ])

    pool_count = _pool_count()
    pool_line = f"当前池 {pool_count}/10，回复 1 入池" if pool_count > 0 else "回复 1 入池"

    one_line = one_sentence(r, low_zone)
    lines.extend([
        "",
        "👉 一句话",
        "",
        f"{stage_label}，{stage_action}。{one_line}",
    ])

    lines.append(f"\n{pool_line}")

    return "\n".join(lines)


def _pool_count() -> int:
    import json
    import os
    path = os.path.expanduser("~/.trader/pool.json")
    try:
        # C-12 fix: path 是 str 类型不能调 .read_text()，需用 Path 或 open
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", [])
        return sum(1 for i in items if i.get("status") not in {"淘汰", "已退出"})
    except Exception:
        return 0


def build_signal(r: dict[str, Any]) -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state(r)
    
    # 融合层介入: 置信度高且有明确信号时覆盖 scene 决策
    fusion_override = False
    fusion = r.get("fusion")
    if isinstance(fusion, dict):
        fc = fusion.get("confidence", 0)
        sd = fusion.get("signals_detail", {})
        has_signal = isinstance(sd, dict) and any(
            isinstance(v, dict) and v.get("direction") != 0
            for v in sd.values()
        )
        if fc > 0.2 and has_signal:
            mapped = _map_fusion_to_signal(fusion.get("action", ""))
            if mapped is not None:
                ft, fd, fa = mapped
                if fd != direction:
                    signal_type, direction, action = ft, fd, fa
                    fusion_override = True
    
    raw_time = str(r.get("analysis_time") or "") or today_text()
    trade_date = raw_time.split(" ")[0]
    if signal_type == "reduce":
        trigger_price = float(r.get("resistance") or r.get("confirm") or r.get("current"))
        invalid_price = float(r.get("stop") or r.get("support") or r.get("current"))
    else:
        trigger_price = float(r.get("confirm") or r.get("resistance") or r.get("current"))
        invalid_price = float(r.get("stop") or r.get("support") or r.get("current"))
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": str(r.get("symbol") or ""),
        "name": str(r.get("name") or ""),
        "trade_date": trade_date,
        "analysis_time": raw_time,
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": confidence,
        "data_status": DATA_STATUS_MAP.get(str(r.get("data_status")), "degraded"),
        "trigger": {
            "type": "price_confirm",
            "price": round(trigger_price, 2),
            "text": f"{trigger_price:.2f}元 放量站稳并回踩不破后再评估",
        },
        "invalidation": {
            "type": "price_break",
            "price": round(invalid_price, 2),
            "text": f"跌破 {invalid_price:.2f}元 后停止低吸",
        },
        "position": {
            "max_total_pct": signal_max_total_pct(signal_type),
            "max_single_move_pct": min(10, signal_max_total_pct(signal_type)),
        },
        "risk_flags": signal_risk_flags(r),
        "summary": one_sentence(r, str(r.get("low_zone") or f"{float(r.get('support') or 0):.2f}元")),
    }
    if fusion_override:
        signal["fusion_override"] = True
    assert_valid_signal(signal)
    return signal


def signal_state(r: dict[str, Any]) -> tuple[str, str, str, str]:
    stage = str(r.get("stage") or "")
    scene = str(r.get("scene") or "")
    theory_status = str(r.get("theory_status") or r.get("state_label") or scene)
    current = float(r.get("current") or 0)
    confirm = float(r.get("confirm") or current)
    if stage == "转弱" or theory_status == "暂不碰":
        return "defensive", "bearish_lean", "wait", "low"
    if theory_status == "体系转强确认":
        return "track", "bullish", "track", "medium"
    if theory_status == "未确认转强":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "承接存在":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "转强不足":
        return "wait_for_confirmation", "neutral", "observe", "low"
    if scene == "冲高减仓" or theory_status == "冲高减仓":
        return "reduce", "neutral", "reduce", "medium"
    if current >= confirm or scene in {"突破确认", "突破观察"} or theory_status in {"突破确认", "突破观察"}:
        return "track", "bullish", "track", "medium"
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎", "空间不足", "等转强"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    return "observe", "neutral", "observe", "low"


def signal_max_total_pct(signal_type: str) -> int:
    if signal_type in ("defensive", "risk_stop"):
        return 0
    if signal_type in ("trigger_expired", "blocked"):
        return 0
    if signal_type == "track":
        return 30
    if signal_type == "reduce":
        return 20
    return 30


def signal_risk_flags(r: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if str(r.get("stage") or "") == "转弱":
        flags.append("structure_weak")
    if str(r.get("scene") or "") == "空间不足":
        flags.append("limited_upside_space")
    if "不足" in str(r.get("volume_text") or ""):
        flags.append("volume_confirmation_missing")
    return flags


def state_text(stage: str, theory_status: str) -> str:
    if stage == "转弱" or theory_status == "暂不碰":
        return "暂不碰"
    if theory_status == "体系转强确认":
        return "体系转强确认"
    if theory_status == "未确认转强":
        return "未确认转强"
    if theory_status == "承接存在":
        return "承接存在"
    if theory_status == "转强不足":
        return "转强不足"
    if theory_status == "修复观察":
        return "修复观察"
    if theory_status:
        return theory_status
    return "震荡观察"


def current_action_text(stage: str, scene: str) -> str:
    if stage == "转弱":
        return "暂不碰"
    if scene == "低吸观察":
        return "低吸观察，等止跌确认"
    if scene == "空间不足":
        return "等待，不追"
    if scene in {"突破确认", "等转强", "冲高减仓"}:
        return "持有观察，不急卖"
    return "等待，不主动追"


def structure_view(r: dict[str, Any]) -> str:
    base_status = str(r.get("base_status") or "")
    theory_status = str(r.get("theory_status") or r.get("state_label") or "")
    scene = str(r.get("scene") or "")
    if theory_status == "体系转强确认":
        return "突破确认中，回踩不破加分"
    if theory_status == "未确认转强":
        return "转强苗头出现，但还没到体系确认"
    if theory_status == "承接存在":
        return "下方有承接，但还不是转强"
    if theory_status == "转强不足":
        return "有修复迹象，但强度还不够"
    if theory_status == "修复观察":
        return "修复阶段，等进一步确认"
    if base_status == "风险回避" or scene == "转弱":
        return "结构偏弱，先退出观察"
    if base_status in {"低位修复", "均线修复", "防守整理", "临近确认", "空间偏紧", "中性整理"}:
        return "修复观察，等理论确认"
    return "修复观察，不是主升"


def volume_view(text: str) -> str:
    if "收涨" in text or "收缩" in text:
        return "承接存在，转强不足"
    if "收跌" in text:
        return "供应仍需消化"
    return "量价确认不足"


def momentum_view(text: str) -> str:
    if "启动迹象" in text or "预备启动" in text:
        return "动能改善，等确认延续"
    if "弱修复" in text or "启动条件不足" in text:
        return "启动不足，等确认"
    return "动能未确认"


def one_sentence(r: dict[str, Any], low_zone: str) -> str:
    major_stage = str(r.get("major_stage") or "")
    momentum = str(r.get("short_term_momentum") or "")
    confirm = float(r.get("confirm") or 0)
    if major_stage == "衰退":
        return "衰退期，不参与。等站上250日线再说。"
    if major_stage == "蓄势" and momentum == "转弱":
        return "蓄势期转弱，不碰。"
    if major_stage == "蓄势" and momentum == "修复":
        return f"蓄势期，不动手。等放量站稳 {confirm:.2f} 再说。"
    if major_stage == "主升" and momentum == "走强":
        return "主升期走强，持有。"
    if major_stage == "派发":
        return "派发期，逢高减仓。"
    # fallback to old logic
    stage = r["stage"]
    scene = r.get("scene") or ""
    theory_status = str(r.get("theory_status") or r.get("state_label") or "")
    current = float(r.get("current", 0))
    support = float(r.get("support", 0))
    if stage == "转弱" or theory_status == "暂不碰":
        return f"现在先不参与；等重新站回 {support:.2f}元 上方并稳定后再看。"
    if theory_status == "体系转强确认":
        return f"已形成体系确认，放量站稳回踩不破可评估加仓。"
    if scene == "冲高减仓":
        return f"上方空间受限，有底仓的逢高减仓，空仓不追。"
    if current >= confirm:
        return f"已越过确认位，放量站稳回踩不破可评估加仓。"
    return f"现在还不是进攻点；先守纪律等确认，跌到 {low_zone} 止跌才轻试，站不上 {confirm:.2f}元 不加仓。"


def _build_existing_position_section(r: dict[str, Any], cost_price: float) -> list[str]:
    """构建 📊 已有持仓评估 输出段落。

    根据盈亏状态和阶段给出具体建议：
      - 赚钱 + 主升期 → 持有，止盈计划从现在开始
      - 赚钱 + 派发期 → 减仓，锁定利润
      - 亏钱 + 蓄势期 → 持有，等反弹到成本价减仓
      - 亏钱 + 衰退期 → 止损，认亏走人
      - 赚钱 + 蓄势期 → 部分止盈，留底仓等突破
      - 亏钱 + 主升期 → 持有，主升期大概率会回来
    """
    current = float(r.get("current") or 0)
    support = float(r.get("support") or 0)
    resistance = float(r.get("resistance") or 0)
    confirm = float(r.get("confirm") or 0)
    stop = float(r.get("stop") or 0)
    major_stage = str(r.get("major_stage") or "")
    momentum = str(r.get("short_term_momentum") or "")
    
    if current <= 0 or cost_price <= 0:
        return []
    
    pnl_pct = (current - cost_price) / cost_price * 100
    is_profit = pnl_pct >= 0
    
    lines: list[str] = ["", "📊 已有持仓评估", ""]
    lines.append(f"  你的成本：{cost_price:.2f}")
    lines.append(f"  现价：{current:.2f}（{'盈' if is_profit else '亏'} {abs(pnl_pct):.1f}%）")
    lines.append(f"  阶段：{major_stage}期 + {momentum}")
    lines.append("")
    
    # 根据盈亏+阶段给出建议
    if is_profit:
        if major_stage == "主升":
            lines.append("  建议：持有，让利润跑")
            lines.append("")
            if resistance > 0:
                lines.append(f"  如果反弹到 {resistance:.2f}（阻力位）→ 观察是否突破")
            if confirm > 0:
                lines.append(f"  如果站稳 {confirm:.2f}（确认位）→ 继续持有")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 减仓")
        elif major_stage == "派发":
            lines.append("  建议：减仓，锁定利润")
            lines.append("")
            if resistance > 0:
                lines.append(f"  如果反弹到 {resistance:.2f}（阻力位）→ 减仓 50%")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 清仓")
        elif major_stage == "蓄势":
            lines.append("  建议：部分止盈，留底仓等突破")
            lines.append("")
            if resistance > 0:
                lines.append(f"  如果反弹到 {resistance:.2f}（阻力位）→ 减仓 30%")
            if confirm > 0:
                lines.append(f"  如果站稳 {confirm:.2f}（确认位）→ 继续持有")
        else:  # 衰退
            lines.append("  建议：减仓，趋势转弱")
            lines.append("")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 清仓")
    else:  # 亏损
        if major_stage == "蓄势":
            lines.append("  建议：持有，等反弹到成本价减仓")
            lines.append("")
            lines.append(f"  如果反弹到 {cost_price:.2f}（成本价）→ 减仓 50%，保本走人")
            if support > 0:
                lines.append(f"  如果跌破 {support:.2f}（支撑位）→ 止损，认亏走人")
            if confirm > 0:
                lines.append(f"  如果站稳 {confirm:.2f}（确认位）→ 继续持有，等突破")
        elif major_stage == "主升":
            lines.append("  建议：持有，主升期大概率会回来")
            lines.append("")
            lines.append(f"  如果反弹到 {cost_price:.2f}（成本价）→ 观察是否继续上涨")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 止损")
        elif major_stage == "衰退":
            lines.append("  建议：止损，认亏走人")
            lines.append("")
            lines.append(f"  现价 {current:.2f} 已亏损 {abs(pnl_pct):.1f}%，趋势转弱")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 立刻止损")
        else:  # 派发
            lines.append("  建议：减仓，减少损失")
            lines.append("")
            lines.append(f"  如果反弹到 {cost_price:.2f}（成本价）→ 减仓 50%")
            if stop > 0:
                lines.append(f"  如果跌破 {stop:.2f}（止损位）→ 清仓")
    
    return lines


def _analyze_buy_conditions(
    r: dict[str, Any],
    current: float,
    support: float,
    confirm: float,
    stop: float,
    low_zone: str,
) -> list[str]:
    """分析买入条件（简化买点逻辑）。

    必要条件：价格到支撑位 → 买 10%
    加分条件（满足越多仓位越大）：
      1. 缩量回踩（量比 < 0.8）
      2. RSI 偏低（RSI < 50）
      3. MACD 金叉或柱状线转正
      4. 价格在 EXPMA(10) 上
      5. 威科夫 LPS 确认

    仓位规则：
      - 必要条件 + 3/5 加分 → 加 10%
      - 必要条件 + 5/5 加分 → 加 15%
      - 必要条件 + 0/5 加分 → 不加
    """
    lines: list[str] = []
    
    # 必要条件：价格在支撑位附近
    at_support = support > 0 and abs(current - support) / max(support, 1) < 0.03
    
    if not at_support:
        lines.append("  动作：等待")
        lines.append(f"  理由：价格未到支撑位 {support:.2f}")
        return lines
    
    # 加分条件检查
    bonus_conditions = []
    
    # 1. 缩量回踩（量比 < 0.8）
    bars = r.get("bars", [])
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            bonus_conditions.append("缩量回踩")
    
    # 2. RSI 偏低（RSI < 50）
    momentum_data = r.get("momentum", {})
    if isinstance(momentum_data, dict):
        rsi = momentum_data.get("rsi", 50)
        if rsi < 50:
            bonus_conditions.append("RSI偏低")
    
    # 3. MACD 金叉或柱状线转正
    macd_data = r.get("macd_status", {})
    if isinstance(macd_data, dict):
        if macd_data.get("golden_cross") or macd_data.get("positive"):
            bonus_conditions.append("MACD转正")
    
    # 4. 价格在 EXPMA(10) 上
    expma10 = r.get("expma10")
    if expma10 and current > expma10:
        bonus_conditions.append("站上EXPMA(10)")
    
    # 5. 威科夫 LPS 确认
    wyckoff = r.get("wyckoff", {})
    if isinstance(wyckoff, dict) and wyckoff.get("lps_signal"):
        bonus_conditions.append("威科夫LPS确认")
    
    # 计算仓位
    bonus_count = len(bonus_conditions)
    if bonus_count >= 5:
        position_pct = 15
    elif bonus_count >= 3:
        position_pct = 10
    else:
        position_pct = 0
    
    # 输出
    if position_pct > 0:
        lines.append(f"  动作：可以试探买 {position_pct}%")
        lines.append(f"  理由：到达支撑位 + {bonus_count}/5 加分条件满足")
        if bonus_conditions:
            lines.append(f"  加分项：{'、'.join(bonus_conditions)}")
        lines.append(f"  如果买：在 {low_zone} 试探买 {position_pct}%, 止损 {stop:.2f}")
        if confirm > 0:
            lines.append(f"  关注：站稳 {confirm:.2f} 可加仓")
    else:
        lines.append("  动作：等待")
        lines.append(f"  理由：到达支撑位但加分条件不足（{bonus_count}/5）")
        if bonus_conditions:
            lines.append(f"  已满足：{'、'.join(bonus_conditions)}")
        lines.append(f"  建议：等条件满足后再买")
    
    return lines


def _build_today_action_section(r: dict[str, Any]) -> list[str]:
    """构建 🎯 今日行动 输出段落。

    优先级从高到低：
      1. 🔴 止损信号 → "今天必须止损"
      2. 🔴 减仓信号 → "今天反弹就卖"
      3. 🟢 买入信号 → "今天可以买"
      4. ⏳ 等待信号 → "今天不操作，关注明天"
      5. ❌ 不碰信号 → "今天不碰"
    """
    current = float(r.get("current") or 0)
    support = float(r.get("support") or 0)
    confirm = float(r.get("confirm") or 0)
    stop = float(r.get("stop") or 0)
    low_zone = str(r.get("low_zone") or f"{support:.2f}-{support * 1.01:.2f}元")
    major_stage = str(r.get("major_stage") or "")
    momentum = str(r.get("short_term_momentum") or "")
    stage_action = str(r.get("stage_action") or "")
    scene = str(r.get("scene") or "")

    # 五状态仓位管理
    position_state = r.get("position_state") or {}
    ps_state = str(position_state.get("state") or "")
    ps_action = str(position_state.get("action") or "")
    ps_position_pct = int(position_state.get("position_pct") or 0)
    ps_stop = float(position_state.get("stop_price") or 0)

    lines: list[str] = ["", "🎯 今日行动", ""]

    # 判断动作优先级
    if stop > 0 and current < stop:
        # 止损信号
        lines.append("  动作：止损退出")
        lines.append(f"  理由：现价 {current:.2f} 已跌破止损 {stop:.2f}")
        lines.append(f"  如果有底仓：立刻止损，不找理由")
    elif major_stage == "衰退":
        # 不碰信号
        lines.append("  动作：不碰")
        lines.append("  理由：衰退期，不参与")
        lines.append("  如果非要关注：等站上250日线再说")
    elif stage_action in ("清仓", "减仓") or scene == "冲高减仓":
        # 减仓信号
        lines.append("  动作：反弹减仓")
        lines.append(f"  理由：{major_stage}期{momentum}，逢高减仓")
        if confirm > 0:
            lines.append(f"  如果有底仓：反弹到 {confirm:.2f} 冲不动就减 10-20%")
        lines.append(f"  如果跌破 {stop:.2f}：止损")
    elif ps_state == "回踩加仓" and ps_position_pct > 0:
        # 回踩加仓信号（状态机）
        lines.append("  动作：回踩加仓")
        lines.append(f"  理由：{ps_action}")
        lines.append(f"  加仓比例：{ps_position_pct}%")
        if ps_stop > 0:
            lines.append(f"  止损：{ps_stop:.2f}")
    elif ps_state == "阻力位分歧":
        # 阻力位分歧信号（状态机）
        lines.append("  动作：阻力位观察")
        lines.append(f"  理由：{ps_action}")
        if ps_stop > 0:
            lines.append(f"  止损：{ps_stop:.2f}")
    elif stage_action in ("试探买", "加仓") and momentum in ("走强", "修复"):
        # 买入信号（简化买点逻辑）
        buy_analysis = _analyze_buy_conditions(r, current, support, confirm, stop, low_zone)
        lines.extend(buy_analysis)
    elif support > 0 and low_zone and current >= float(low_zone.split("-")[0]) and current <= float(low_zone.split("-")[1].replace("元", "")):
        # Bug fix: 价格在买入区间内时，显示"可以试探买"
        buy_analysis = _analyze_buy_conditions(r, current, support, confirm, stop, low_zone)
        lines.extend(buy_analysis)
    elif major_stage == "主升" and momentum == "走强":
        # 持有信号
        lines.append("  动作：持有")
        lines.append(f"  理由：主升期走强，让利润跑")
        lines.append(f"  如果跌破 {stop:.2f}：减仓")
    else:
        # 等待信号
        lines.append("  动作：不买")
        lines.append(f"  理由：{major_stage}期{momentum}，方向不明")
        if support > 0:
            lines.append(f"  如果非要买：{low_zone} 不破买 5%, 止损 {stop:.2f}")
        if confirm > 0:
            lines.append(f"  关注明天：站稳 {confirm:.2f} 可以加仓")

    # 状态机补充信息
    if ps_state and ps_state not in ("空仓",):
        lines.append(f"  仓位状态：{ps_state}")

    return lines


def _check_wyckoff_bc_confirmation(r: dict[str, Any]) -> dict[str, Any]:
    """检查 BC（购买高潮）信号的共振确认。

    BC 确认指标（3/5 确认 = 信号可信）：
      1. RSI > 70（超买）
      2. MACD 顶背离
      3. 量比 > 2.0（天量）
      4. 涨幅 < 1%（滞涨）
      5. 价格跌破 EXPMA(10)（趋势转弱）
    """
    confirmed_count = 0
    reasons = []
    
    # 1. RSI > 70（超买）
    momentum_data = r.get("momentum", {})
    if isinstance(momentum_data, dict):
        rsi = momentum_data.get("rsi", 50)
        if rsi > 70:
            confirmed_count += 1
            reasons.append(f"RSI超买({rsi:.0f})")
    
    # 2. MACD 顶背离
    macd_data = r.get("macd_status", {})
    if isinstance(macd_data, dict):
        if macd_data.get("death_cross") or not macd_data.get("positive"):
            confirmed_count += 1
            reasons.append("MACD转弱")
    
    # 3. 量比 > 2.0（天量）— 用数值判断，不用字符串
    atr_ratio = float(r.get("atr_ratio") or 0)
    if atr_ratio > 2.0:
        confirmed_count += 1
        reasons.append("天量")
    
    # 4. 涨幅 < 1%（滞涨）
    change_pct = float(r.get("change_pct") or 0)
    if abs(change_pct) < 1.0:
        confirmed_count += 1
        reasons.append("滞涨")
    
    # 5. 价格跌破 EXPMA(10)（趋势转弱）
    expma10 = r.get("expma10")
    current = float(r.get("current") or 0)
    if expma10 and current < expma10:
        confirmed_count += 1
        reasons.append("跌破EXPMA(10)")
    
    return {
        "confirmed": confirmed_count >= 3,
        "count": confirmed_count,
        "reason": "、".join(reasons) if reasons else "无共振确认",
    }


def _check_wyckoff_utad_confirmation(r: dict[str, Any]) -> dict[str, Any]:
    """检查 UTAD（上冲回落）信号的共振确认。

    UTAD 确认指标（3/3 确认 = 信号可信）：
      1. 价格突破后跌回
      2. 量比 > 1.5（放量）
      3. 价格跌回 EXPMA(10) 下方
    """
    confirmed_count = 0
    reasons = []
    
    # 1. 价格突破后跌回（检查是否从高位回落）— 用 ATR 而非硬编码 2%
    current = float(r.get("current") or 0)
    resistance = float(r.get("resistance") or 0)
    atr14 = float(r.get("atr14") or 0)
    atr_threshold = atr14 * 0.5 if atr14 > 0 else resistance * 0.02  # 半个ATR或2%
    if resistance > 0 and current < resistance - atr_threshold:
        confirmed_count += 1
        reasons.append("价格回落")
    
    # 2. 量比 > 1.5（放量）— 用数值判断
    atr_ratio = float(r.get("atr_ratio") or 0)
    if atr_ratio > 1.5:
        confirmed_count += 1
        reasons.append("放量")
    
    # 3. 价格跌回 EXPMA(10) 下方
    expma10 = r.get("expma10")
    if expma10 and current < expma10:
        confirmed_count += 1
        reasons.append("跌破EXPMA(10)")
    
    return {
        "confirmed": confirmed_count >= 3,
        "count": confirmed_count,
        "reason": "、".join(reasons) if reasons else "无共振确认",
    }


def _build_signal_alert_section(r: dict[str, Any]) -> list[str]:
    """构建 🔔 信号提醒 输出段落。

    检查以下信号：
    - BC（购买高潮）→ 减仓 1/3
    - UTAD（上冲回落）→ 立刻减仓
    - SOW（弱势信号）→ 关注
    - 筹码搬家 → 警告/清仓
    - 突破确认 → 止损上移
    """
    lines: list[str] = []
    alerts: list[str] = []

    # 提取威科夫信号
    exit_plan = r.get("exit_plan") or {}
    wyk_signals = exit_plan.get("wyckoff_signals") or {}
    utad_action = exit_plan.get("utad_action")

    bc_signal = wyk_signals.get("bc_signal", False)
    bc_reason = wyk_signals.get("bc_reason", "")
    utad_signal = wyk_signals.get("utad_signal", False)
    utad_reason = wyk_signals.get("utad_reason", "")

    # 提取威科夫分析结果（从 report 的 wyckoff 字段）
    wyckoff = r.get("wyckoff") or {}
    if isinstance(wyckoff, dict):
        sow_signal = wyckoff.get("sow_signal", False)
        sow_reason = wyckoff.get("sow_reason", "")
    else:
        sow_signal = False
        sow_reason = ""

    # 提取筹码搬家数据
    chip_migration = r.get("chip_migration") or {}
    migration_pct = chip_migration.get("migration_pct", 0)
    warning_level = chip_migration.get("warning_level", "none")
    warning_text = chip_migration.get("warning_text", "")

    # BC 信号（威科夫共振确认）
    if bc_signal:
        bc_confirmation = _check_wyckoff_bc_confirmation(r)
        if bc_confirmation["confirmed"]:
            alerts.append(f"  🔴 购买高潮（BC）信号 - 已确认")
            alerts.append(f"    {bc_reason}")
            alerts.append(f"    共振确认：{bc_confirmation['reason']}")
            alerts.append(f"    动作：减仓 1/3")
        else:
            alerts.append(f"  ⚠️ 购买高潮（BC）信号 - 待确认")
            alerts.append(f"    {bc_reason}")
            alerts.append(f"    需要更多指标确认：{bc_confirmation['reason']}")
            alerts.append(f"    动作：关注，准备减仓")

    # UTAD 信号（威科夫共振确认）
    if utad_signal:
        utad_confirmation = _check_wyckoff_utad_confirmation(r)
        if utad_confirmation["confirmed"]:
            alerts.append(f"  🔴 上冲回落（UTAD）信号 - 已确认")
            alerts.append(f"    {utad_reason}")
            alerts.append(f"    共振确认：{utad_confirmation['reason']}")
            alerts.append(f"    动作：立刻减仓")
        else:
            alerts.append(f"  ⚠️ 上冲回落（UTAD）信号 - 待确认")
            alerts.append(f"    {utad_reason}")
            alerts.append(f"    需要更多指标确认：{utad_confirmation['reason']}")
            alerts.append(f"    动作：关注，准备减仓")

    # SOW 信号
    if sow_signal:
        alerts.append(f"  ⚠️ 弱势信号（SOW）")
        alerts.append(f"    {sow_reason}")
        alerts.append(f"    动作：关注，准备减仓")

    # 筹码搬家
    if warning_level == "critical":
        alerts.append(f"  🔴 筹码搬家清仓信号")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    动作：清仓")
    elif warning_level == "warning":
        alerts.append(f"  ⚠️ 筹码松动警告")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    动作：关注，随时准备减仓")

    # 突破确认（从 exit_plan 的 breakout_followup 检查）
    breakout = exit_plan.get("breakout_followup")
    if breakout and breakout.get("add_on_pullback"):
        current = float(r.get("current") or 0)
        confirm = float(r.get("confirm") or 0)
        # Bug fix: 改为严格判断 current >= confirm，不再使用 0.98 容差
        if confirm > 0 and current >= confirm:
            alerts.append(f"  🟢 突破确认")
            alerts.append(f"    价格站稳确认位 {confirm:.2f}")
            alerts.append(f"    止损上移到 {breakout.get('new_stop', 0):.2f}")

    if alerts:
        lines.extend(["", "🔔 信号提醒", ""])
        lines.extend(alerts)

    return lines


def generate_alert(report: dict[str, Any]) -> str | None:
    current = float(report["current"])
    support = float(report.get("support") or 0)
    low_zone = str(report.get("low_zone") or "")
    stop = float(report.get("stop") or 0)
    confirm = float(report.get("confirm") or 0)
    resistance = float(report.get("resistance") or 0)
    scene = str(report.get("scene") or "")
    theory_status = str(report.get("theory_status") or report.get("state_label") or scene)
    name = str(report["name"])
    atr14 = float(report.get("atr14", 0) or 0)
    thresh = max(atr14 * 0.35, current * 0.006) if atr14 > 0 else current * 0.008

    if stop > 0:
        if current <= stop:
            return f"⚠️ {name}｜现价{current:.2f}元 跌破止损 {stop:.2f}元 注意控制风险"
        if current <= stop + thresh:
            return f"⚠️ {name}｜现价{current:.2f}元 接近止损 {stop:.2f}元 留意防守"

    if support > 0 and abs(current - support) <= thresh:
        if stop > 0 and abs(current - stop) <= abs(current - support):
            pass
        elif current <= support:
            zone_text = low_zone if low_zone else f"{support:.2f}元"
            return f"📍 {name}｜现价{current:.2f}元 进入支撑区 {zone_text} 止跌确认中"
        else:
            return f"📍 {name}｜现价{current:.2f}元 接近支撑 {support:.2f}元 止跌确认中"

    if confirm > 0 and abs(current - confirm) <= thresh and scene not in {"冲高减仓", "突破确认", "突破观察"} and theory_status != "体系转强确认":
        if current >= confirm:
            return f"📈 {name}｜现价{current:.2f}元 已越过确认价 {confirm:.2f} 放量站稳加仓评估"
        return f"📈 {name}｜现价{current:.2f}元 触及确认区 {confirm:.2f} 放量站稳加仓评估"

    if resistance > 0 and abs(current - resistance) <= thresh:
        if current >= resistance:
            return f"📉 {name}｜现价{current:.2f}元 已突破减仓位 {resistance:.2f} 冲高减仓"
        return f"📉 {name}｜现价{current:.2f}元 触及减仓位 {resistance:.2f} 冲高减仓"

    return None


def build_watch_alert(report: dict[str, Any], write_signal: bool = False) -> str:
    """One-screen view: status + action + key levels + triggered signals."""
    name = str(report["name"])
    symbol = str(report.get("symbol", ""))
    current = float(report["current"])
    stop = float(report.get("stop") or 0)
    support = float(report.get("support") or 0)
    low_zone = str(report.get("low_zone") or f"{support:.2f}-{support * 1.01:.2f}元")
    confirm = float(report.get("confirm") or 0)
    resistance = float(report.get("resistance") or 0)
    take = float(report.get("take") or 0)
    change_pct = float(report.get("change_pct") or 0)
    scene = str(report.get("scene") or "")
    atr14 = float(report.get("atr14", 0) or 0)
    atr_cap = int(report.get("atr_cap") or 10)
    state_label = str(report.get("state_label") or "")
    analysis_time = str(report.get("analysis_time") or "")

    lines: list[str] = []
    alerts_found: list[str] = []

    # Tolerance for "at level" checks (ATR-based or fixed)
    thresh = max(atr14 * 0.35, current * 0.006) if atr14 > 0 else current * 0.008

    # === DETERMINE ACTION CATEGORY ===
    # 1. 硬止损破位（最优先）
    is_stop_broken = stop > 0 and current < stop
    # 2. 接近止损线
    is_near_stop = not is_stop_broken and stop > 0 and (current - stop) < thresh * 3
    # 3. 进入止跌区
    is_at_support = support > 0 and abs(current - support) <= thresh * 2 and current <= support
    # 4. 接近启动确认价
    is_near_confirm = confirm > 0 and abs(current - confirm) <= thresh * 2 and current >= confirm
    # 5. 接近减仓位
    is_near_resistance = resistance > 0 and abs(current - resistance) <= thresh * 2 and current >= resistance
    # 6. 接近止盈位
    is_near_take = take > 0 and abs(current - take) <= thresh * 2 and take > confirm

    # === BUILD ALERT TEXT ===
    if is_stop_broken:
        break_pct = (current - stop) / stop * 100 if stop > 0 else 0
        alerts_found.append(f"已破防守位 {stop:.2f}")
    elif is_near_stop:
        dist = (current - stop) / stop * 100
        alerts_found.append(f"距止损仅 {dist:.1f}%")

    if is_at_support:
        dist = (support - current) / support * 100
        alerts_found.append(f"进入止跌区 {low_zone} ({dist:.1f}%)")
    elif support > 0 and abs(current - support) <= thresh * 2 and current > support:
        dist = (current - support) / support * 100
        alerts_found.append(f"距支撑 {support:.2f} 仅 {dist:.1f}%")

    if is_near_confirm:
        alerts_found.append(f"已到启动确认价 {confirm:.2f}")
    elif confirm > 0 and confirm - current > 0 and (confirm - current) / confirm * 100 <= 3:
        dist = (confirm - current) / confirm * 100
        alerts_found.append(f"距启动确认价 {confirm:.2f} 仅 {dist:.1f}%")

    if is_near_resistance:
        alerts_found.append(f"已过减仓位 {resistance:.2f}")
    elif resistance > 0 and resistance - current > 0 and (resistance - current) / resistance * 100 <= 3:
        dist = (resistance - current) / resistance * 100
        alerts_found.append(f"距减仓位 {resistance:.2f} 仅 {dist:.1f}%")

    if is_near_take:
        dist = (take - current) / take * 100
        alerts_found.append(f"距止盈位 {take:.2f} 仅 {dist:.1f}%")

    # === DETERMINE ACTION + STATEMENT ===
    if is_stop_broken:
        action = "止损退出，不找理由"
        state_summary = "防守失败，止损执行"
    elif is_at_support and not is_stop_broken:
        action = "不抄底，等止跌确认"
        state_summary = "止跌确认中，等待承接"
    elif is_near_confirm:
        action = "放量站稳才加，不放量不动"
        state_summary = "启动确认中"
    elif is_near_resistance:
        action = "冲高减仓，不追"
        state_summary = "冲高减仓"
    elif is_near_stop:
        action = "盯紧止损线，跌破就退"
        state_summary = "接近风险线"
    else:
        action = f"当前{theory_status_text}，{action_text_for_scene(scene)}"
        state_summary = theory_status_text

    # === BUILD OUTPUT ===
    lines.append(f"盯盘 — {name}  {current:.2f}（{change_pct:+.2f}%）  {state_summary}")
    lines.append(f"  👉 当前应对：{action}")

    # Show key levels reference
    lines.append("")
    lines.append(f"  防守 {stop:.2f}  |  支撑 {support:.2f}  |  启动 {confirm:.2f}  |  减仓 {resistance:.2f}  |  止盈 {take:.2f}")

    # ATR + position cap
    if atr14 > 0:
        lines.append(f"  ATR {atr14:.2f}（{atr14/current*100:.0f}%）  仓位上限 {atr_cap}%")

    # Triggered alerts
    if alerts_found:
        lines.append("")
        lines.append("  触发：")
        for idx, alert in enumerate(alerts_found, 1):
            lines.append(f"    [{idx}] {alert}")

    # Write signal if triggered
    if alerts_found and write_signal:
        if is_stop_broken:
            sig_type, direction, action_sig, confidence, trigger_price = "risk_stop", "bearish", "stop", "high", stop
        elif is_at_support:
            sig_type, direction, action_sig, confidence, trigger_price = "low_buy_triggered", "bullish_lean", "low_buy", "medium", support
        elif is_near_confirm:
            sig_type, direction, action_sig, confidence, trigger_price = "track", "bullish", "track", "medium", confirm
        elif is_near_resistance:
            sig_type, direction, action_sig, confidence, trigger_price = "reduce", "neutral", "reduce", "medium", resistance
        else:
            sig_type, direction, action_sig, confidence, trigger_price = "observe", "neutral", "observe", "low", current

        from trader_shared.signal_store import append_signal
        raw_time = analysis_time or today_text()
        trade_date = raw_time.split(" ")[0]
        signal = {
            "contract": "trader_signal_v1",
            "source_skill": "trader",
            "symbol": symbol,
            "name": name,
            "trade_date": trade_date,
            "analysis_time": raw_time,
            "signal_type": sig_type,
            "direction": direction,
            "action": action_sig,
            "confidence": confidence,
            "data_status": DATA_STATUS_MAP.get(str(report.get("data_status")), "full"),
            "trigger": {"type": "price_level", "price": round(trigger_price, 2), "text": f"{trigger_price:.2f}元 触发{sig_type}"},
            "invalidation": {"type": "price_break", "price": round(stop, 2), "text": f"跌破 {stop:.2f}元"},
            "position": {
                "max_total_pct": signal_max_total_pct(sig_type),
                "max_single_move_pct": min(10, signal_max_total_pct(sig_type)),
            },
            "risk_flags": signal_risk_flags(report),
            "summary": ("  ".join(alerts_found[:2])) if alerts_found else "无触发",
        }
        try:
            append_signal(signal)
            lines.append(f"  信号已记录：{_signal_type_label(sig_type)}（置信度{confidence}）")
        except Exception:
            pass

    return "\n".join(lines)


def action_text_for_scene(scene: str) -> str:
    """One-line action advice based on scene."""
    if scene in {"低吸观察"}:
        return "等止跌确认再动手"
    if scene in {"防守观察", "防守观察，趋势下行谨慎"}:
        return "守纪律不追"
    if scene in {"等转强"}:
        return "等放量确认"
    if scene in {"冲高减仓"}:
        return "冲高减仓，不追"
    if scene in {"突破确认", "突破观察"}:
        return "持有观察，不急操作"
    if scene in {"空间不足"}:
        return "上方空间不够，先不追"
    return "等待，不主动追"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes-compatible Trader report renderer.")
    parser.add_argument("--mode", choices=["http-single"], required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", choices=["markdown", "json", "signal-json", "alert-text"], default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target)
    except Exception as exc:
        print(f"Trader数据获取失败：{exc}", file=sys.stderr)
        return 1

    try:
        from trader_shared.candidate_core import STATUS_SCORE
        write_stock(
            report["name"],
            report["scene"],
            int(STATUS_SCORE.get(report["scene"], 0)),
            "trader",
        )
    except Exception:
        pass

    try:
        track_log(
            "trader",
            report["name"],
            str(report.get("symbol") or ""),
            report["scene"],
            float(report.get("current") or 0),
            get_market_level(),
            get_market_note(),
        )
    except Exception:
        pass

    if args.output == "json":
        markdown = render_markdown(report)
        print(json.dumps({"full_markdown": markdown, "report": report, "signal": build_signal(report)}, ensure_ascii=False, indent=2, default=str))
    elif args.output == "signal-json":
        print(json.dumps(build_signal(report), ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
