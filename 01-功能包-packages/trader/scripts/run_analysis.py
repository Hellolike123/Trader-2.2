#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# 确保 trader_shared 可导入（pack 后在 scripts/ 下，hermes 运行时 sys.path 可能不包含 scripts/）
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import argparse
import json
import traceback
from typing import Any

from trader_shared._logging import get_logger
_logger = get_logger(__name__)

SCRIPT_DIR = _SCRIPT_DIR
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
from trader_shared.stage_positioning import assess_stage, compute_exit_plan, compute_stage_stop, check_time_stop, evaluate_position_state, _detect_major_stage
from trader_shared.fetchers import TencentFetcher
from trader_shared.indicator_math import aggregate_5m_to_60m, calc_supertrend, calc_vwap

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
    ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS,
    KELLY_MAX_TOTAL_POSITIONS,
    KELLY_MIN_TRADES,
)
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

# ── Kelly cache: 读取 signal_results.jsonl 一次，按 market_env_level 缓存结果 ──
_kelly_cache: dict[str, dict[str, float]] = {}


def _get_kelly_data(market_env_level: str) -> dict[str, float]:
    """读取并缓存信号结果中的胜率数据，供 Kelly 仓位计算使用。

    返回 dict 包含: {"win_rate": float | None, "total": int}
    同一进程内只读取一次文件，后续直接读缓存。
    """
    if market_env_level in _kelly_cache:
        return _kelly_cache[market_env_level]

    result: dict[str, float] = {"win_rate": None, "total": 0}
    try:
        results_file = Path.home() / ".trader" / "signal_results.jsonl"
        if results_file.exists():
            wins, total = 0, 0
            with open(results_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rec_env = rec.get("market_env", "")
                    if rec_env and rec_env != market_env_level:
                        continue
                    if rec.get("status", "") == "filled":
                        total += 1
                        if float(rec.get("return_pct") or 0) > 0:
                            wins += 1
            if total >= KELLY_MIN_TRADES:
                result["win_rate"] = wins / total
            result["total"] = total
    except Exception:
        pass
    _kelly_cache[market_env_level] = result
    return result


def _get_major_stage(r: dict[str, Any]) -> str:
    major_stage = str(r.get("major_stage") or "")
    if not major_stage:
        old_stage = str(r.get("stage") or "")
        stage_map = {
            "修复": "蓄势",
            "走强": "主升",
            "震荡": "蓄势",
            "转弱": "衰退",
        }
        major_stage = stage_map.get(old_stage, old_stage)
    return major_stage

# ── 进程内 signals.jsonl 缓存（批量刷新时避免每票重读文件）──
_signals_cache_data: list[dict] | None = None
_signals_cache_mtime: float = 0
_signals_cache_path: str = ""


def _clear_signals_cache() -> None:
    """清除 signals.jsonl 缓存（用于测试或文件变动后）"""
    global _signals_cache_data, _signals_cache_mtime, _signals_cache_path
    _signals_cache_data = None
    _signals_cache_mtime = 0
    _signals_cache_path = ""


def _read_signals_for_report(target: str, daily_bars: list[dict[str, Any]]) -> tuple[float, dict | None]:
    """一次性读取 signals.jsonl，同时返回成本价和历史胜率。

    合并了原来的 _get_cost_from_signals + _load_historical_win_rate，
    避免对同一文件做两次 I/O。
    只读最近 100 条信号（足够覆盖成本推断和胜率统计）。

    Returns:
        (cost_price, win_rate_data)
        cost_price: 最近买入信号的价格，找不到返回 0.0
        win_rate_data: 历史胜率统计 dict 或 None
    """
    global _signals_cache_data, _signals_cache_mtime, _signals_cache_path

    signals_path = os.path.expanduser("~/.trader/signals.jsonl")

    # 进程内缓存：文件未修改则复用上次结果
    try:
        current_mtime = os.path.getmtime(signals_path)
    except OSError:
        current_mtime = 0

    if (_signals_cache_data is not None and
            _signals_cache_path == signals_path and
            _signals_cache_mtime == current_mtime):
        all_lines = _signals_cache_data
    else:
        if not os.path.exists(signals_path):
            _signals_cache_data = []
            _signals_cache_mtime = current_mtime
            _signals_cache_path = signals_path
            return 0.0, None
        with open(signals_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()[-100:]
        _signals_cache_data = all_lines
        _signals_cache_mtime = current_mtime
        _signals_cache_path = signals_path

    normalized_target = target.replace(".SH", "").replace(".SZ", "").strip()

    # 构建日期→收盘价的映射（用于计算收益率）
    sorted_bars = sorted(daily_bars, key=lambda x: str(x.get("date", ""))[:10])
    dates = [str(b.get("date", ""))[:10] for b in sorted_bars if b.get("date")]
    close_map: dict[str, float] = {}
    for b in sorted_bars:
        d = str(b.get("date", ""))[:10]
        if d and b.get("close") is not None:
            close_map[d] = float(b["close"])

    if not close_map:
        return 0.0, None

    # 日期索引（用于计算 5 日后收益率）
    date_to_idx: dict[str, int] = {d: i for i, d in enumerate(dates)}

    buy_signals: list[float] = []
    sell_signals: list[float] = []
    cost_price: float = 0.0

    try:
        for line in reversed(all_lines):  # 从新到旧遍历
                line = line.strip()
                if not line:
                    continue
                try:
                    sig = json.loads(line)
                except json.JSONDecodeError:
                    continue

                sig_symbol = str(sig.get("symbol", "")).replace(".SH", "").replace(".SZ", "").strip()
                sig_name = str(sig.get("name", "")).strip()
                if normalized_target not in (sig_symbol, sig_name):
                    continue

                sig_type = str(sig.get("signal_type", ""))
                trade_date = str(sig.get("trade_date") or "")[:10]
                analysis_time = str(sig.get("analysis_time") or "")
                time_part = analysis_time[11:].strip() if len(analysis_time) >= 16 else ""

                # ── 成本推断：从新到旧找第一个买入信号 ──
                if cost_price == 0.0:
                    if sig_type in ("low_buy_triggered", "track"):
                        trigger = sig.get("trigger", {})
                        price = trigger.get("price", 0)
                        if price > 0:
                            cost_price = float(price)
                            break  # 找到最近的买入信号，停止

                # ── 胜率统计：继续扫描 ──
                if sig_type not in ("review_result", "low_buy_triggered", "high_sell_triggered"):
                    continue
                if sig_type == "review_result" and not (time_part >= "15:00"):
                    continue
                if trade_date not in date_to_idx:
                    continue

                idx = date_to_idx[trade_date]
                if idx + 5 >= len(dates):
                    continue

                entry_price = close_map.get(trade_date, 0)
                if entry_price <= 0:
                    continue
                exit_price = close_map.get(dates[idx + 5], 0)
                if exit_price <= 0:
                    continue
                return_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)

                direction = str(sig.get("direction", ""))
                if sig_type == "low_buy_triggered":
                    buy_signals.append(return_pct)
                elif sig_type == "high_sell_triggered":
                    sell_signals.append(return_pct)
                elif direction in ("bullish", "bullish_lean"):
                    buy_signals.append(return_pct)
                elif direction in ("bearish", "bearish_lean"):
                    sell_signals.append(return_pct)
    except Exception:
        return cost_price, None

    # 构造胜率数据
    win_rate_data: dict | None = None
    total = len(buy_signals) + len(sell_signals)
    if total > 0:
        def _stats(signals: list[float]) -> dict | None:
            if not signals:
                return None
            wins = sum(1 for s in signals if s > 0)
            n = len(signals)
            win_rate = round((wins / n) * 100)
            avg = round(sum(signals) / n, 2)
            return {"count": n, "wins": wins, "win_rate": win_rate, "avg_pnl": avg}

        win_rate_data = {
            "total": total,
            "buy": _stats(buy_signals),
            "sell": _stats(sell_signals),
            "sample_warning": total < 5,
        }

    return cost_price, win_rate_data


def _load_historical_win_rate(target: str) -> dict | None:
    """兼容旧 API：内部取日线，返回胜率数据 dict 或 None。

    替代原来的独立 _load_historical_win_rate 函数，
    底层复用已缓存的 _read_signals_for_report。
    """
    _clear_signals_cache()  # 每次读取都重新读取文件（测试/独立调用场景）
    try:
        from trader_shared.data_provider import get_provider
        provider = get_provider()
        sec = provider.resolve_security(target)
        bars = provider.fetch_qfq_daily(sec)
    except Exception:
        bars = []
    _, win_rate_data = _read_signals_for_report(target, bars)
    return win_rate_data


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
    "no_entry": "不参与",
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

    for key, label in [("chan", "缠论"), ("momentum", "动量"), ("vpf", "价量资金")]:
        sig = signals.get(key, {})
        if not sig:
            continue
        d = sig.get("direction", 0)
        c = sig.get("confidence", 0)
        w = weights.get(key, 0)
        if c > 0:
            rows.append(f"    {label}：{_signal_direction_text(d)}（置信 {c:.0%}，权重 {w:.0%}）")

    # 量价背离警告
    vw = fusion.get("volume_warning", {})
    if vw and vw.get("warning_type") != "none":
        rows.append(f"    ⚠️ {vw.get('reason', '')}")

    if disagreement > 1:
        rows.append(f"  注意：多信号存在分歧（分歧度 {disagreement:.1f}），优先采纳缠论/威科夫方向")

    return rows


_FUSION_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "半仓试 (多方主导)": ("track", "bullish", "track"),
    "半仓试 (多方主导但有分歧)": ("track", "bullish", "track"),
    "增持": ("track", "bullish", "track"),
    "等转强观察": ("wait_for_confirmation", "bullish_lean", "observe"),  # Fix 3: 新增
    "持股观望": ("observe", "neutral", "observe"),
    "减仓": ("defensive", "bearish", "wait"),
    "空仓/止损": ("defensive", "bearish", "wait"),
    # T-11 fix: 补全 3 个缺失的融合层 Action 映射，避免决策被静默丢弃
    "空仓 (大盘很差, 一票否决)": ("risk_stop", "bearish", "stop"),
    "观望 (信号冲突)": ("observe", "neutral", "observe"),
    "等转强": ("wait_for_confirmation", "bullish_lean", "observe"),
    "回调观望": ("wait_for_confirmation", "neutral", "observe"),
    "高位观望": ("no_entry", "neutral", "observe"),
    # 卖点侧补强：减1/3 中间态映射
    "减1/3 (高位松动)": ("defensive", "bearish_lean", "wait"),
    "高位松动": ("defensive", "bearish_lean", "wait"),
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
    snapshot = provider.load_market_snapshot(target, days=LOOKBACK_DAYS, include_5m=True, include_weekly=True, include_monthly=True)
    if not snapshot.quote or not snapshot.daily_bars:
        detail = "; ".join(f"{key}: {value}" for key, value in snapshot.source_errors.items()) or "missing required market data"
        raise RuntimeError(detail)

    sec = snapshot.security
    quote = snapshot.quote
    bars = list(snapshot.daily_bars)  # copy to avoid mutating snapshot

    # ═══════ ST / 退市风险 / 新股 / 停牌 检测 ═══════
    stock_name = str(quote.get("name") or sec.name or target)
    is_st = "ST" in stock_name or "*ST" in stock_name
    # 停牌：现价等于昨收且成交量为 0（或极小）
    cp = to_float(quote.get("current_price"))
    pc = to_float(quote.get("pre_close"))
    vol = to_float(quote.get("volume"))
    is_suspended = cp is not None and pc is not None and vol is not None and cp > 0 and abs(cp - pc) < 1e-6 and vol < 1
    bar_count = len(bars)
    is_new_stock = bar_count < 60  # 上市不足 60 个交易日
    risk_flags: list[str] = []
    if is_st:
        risk_flags.append("ST")
    if is_suspended:
        risk_flags.append("停牌")
    if is_new_stock:
        risk_flags.append("新股")

    # 一次性读取 signals.jsonl：同时获取成本价和历史胜率（合并两次 I/O）
    _signal_cost_price, _signal_win_rate = _read_signals_for_report(target, bars)

    # 如果日线最新日期不是今天，追加今日 quote 作为当天 bar
    # （解决盘中分析时日线数据滞后导致阶段判定错误的问题）
    _today = str(quote.get("trade_date") or "")[:10]
    _last_date = str(bars[-1].get("date") or bars[-1].get("trade_date") or "")[:10] if bars else ""
    _cp = quote.get("current_price")
    if _today and _last_date != _today and _cp is not None and float(_cp) > 0:
        _chg = float(quote.get("current_change_pct") or 0)
        _prev_close = float(_cp) / (1 + _chg / 100) if _chg != 0 else float(_cp)
        _prev_bar = bars[-1] if bars else {}
        bars.append({
            "date": _today,
            "open": _prev_close,
            "close": float(_cp),
            "high": float(_cp),
            "low": float(_cp),
            "volume": 0,
            "data_source": "quote-today",
            "data_status": "full",
            "atr14": _prev_bar.get("atr14", 0),
            "atr_ratio": _prev_bar.get("atr_ratio", 0),
            "atr7": _prev_bar.get("atr7", 0),
            "tr": _prev_bar.get("tr", 0),
        })
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
    from trader_shared.chan_core import chanlun_strategy, chanlun_strategy_midline
    from trader_shared.wyckoff_core import wyckoff_strategy, wyckoff_strategy_midline
    from trader_shared.momentum_core import momentum_strategy

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
        """从 Tushare 获取板块数据（行业分类 + 板块涨跌幅）。"""
        try:
            from trader_shared.tushare_client import get_client
            client = get_client()
            if not client.available:
                return None

            # 1. 获取个股行业
            stock_info = client.query("stock_basic", ts_code=sec.ts_code, fields="ts_code,name,industry")
            if not stock_info:
                return None
            industry = stock_info[0].get("industry", "")
            if not industry:
                return None

            # 2. 找匹配的同花顺行业指数（优先精确匹配）
            ths_indices = client.query_ths_index("I")  # 'I' = 行业

            # 构建匹配关键词（如 "家用电器" → ["家电", "白色家电", "黑色家电", "小家电"]）
            _sector_keywords = {
                "家用电器": ["白色家电", "黑色家电", "小家电", "家电零部件"],
                "电子": ["电子零部件", "电子化学品"],
                "计算机": ["软件开发", "计算机设备"],
                "医药": ["化学制药", "中药", "生物制品"],
                "银行": ["国有大行", "股份制银行", "城商行"],
                "食品饮料": ["白酒", "乳品", "调味品"],
            }

            matched_sector = None
            # 优先：用关键词精确匹配
            for keyword in _sector_keywords.get(industry, []):
                for idx in ths_indices:
                    if str(idx.get("name", "")) == keyword:
                        matched_sector = idx
                        break
                if matched_sector:
                    break

            # 次选：行业名完全包含在板块名中
            if not matched_sector:
                for idx in ths_indices:
                    idx_name = str(idx.get("name", ""))
                    if industry == idx_name or industry in idx_name:
                        matched_sector = idx
                        break

            # 兜底：板块名包含行业关键词
            if not matched_sector:
                for idx in ths_indices:
                    idx_name = str(idx.get("name", ""))
                    if "家电" in idx_name and "家电" in industry:
                        matched_sector = idx
                        break

            if not matched_sector:
                return {"industry": industry, "status": "未匹配板块"}

            sector_code = matched_sector.get("ts_code", "")
            sector_name = matched_sector.get("name", "")

            # 3. 获取板块日线涨跌幅
            sector_daily = client.query_ths_daily(sector_code, start_date="", end_date="")
            if not sector_daily:
                return {"industry": industry, "sector_name": sector_name, "sector_code": sector_code, "status": "无日线"}

            latest = sector_daily[-1]
            sector_chg_pct = float(latest.get("pct_change", 0) or 0)

            return {
                "industry": industry,
                "sector_name": sector_name,
                "sector_code": sector_code,
                "sector_change_pct": sector_chg_pct,
                "status": "正常",
            }
        except Exception as e:
            _logger.debug(f"板块数据获取失败: {e}")
            return None

    # 复用全局共享线程池，避免嵌套 ThreadPoolExecutor 导致线程爆炸
    # cmd_refresh 内建 pool → build_report 内再建 pool → load_market_snapshot 内再建 pool
    # 现在三层共享同一个 max_workers=5 池
    pool = get_shared_build_pool()
    # 日线缠论：fusion / 短线专家（周线仅作 higher_trend）
    f_chan = pool.submit(chanlun_strategy, current, bars, change_pct_val, quote, weekly_bars=weekly_bars)
    # 中线缠论独立判断：优先周 K 完整笔段（与日线分离）
    f_chan_mid = pool.submit(
        chanlun_strategy_midline,
        current,
        weekly_bars,
        bars,
        change_pct_val,
        quote,
    )
    # 日线威科夫：仍供 fusion 短线侧兼容
    f_wyk = pool.submit(wyckoff_strategy, current, bars, change_pct_val, quote)
    # 中线威科夫独立判断：优先周 K（与日线 fusion 分离）
    f_wyk_mid = pool.submit(
        wyckoff_strategy_midline,
        current,
        weekly_bars,
        bars,
        change_pct_val,
        quote,
    )
    f_mom = pool.submit(momentum_strategy, current, bars, change_pct_val, quote)
    f_mf = pool.submit(_fetch_fund_flow)
    f_env = pool.submit(_fetch_market_env)
    f_sector = pool.submit(_fetch_sector_data)

    chan_result = f_chan.result() or {}  # 日线；_chan_to_signal 会自己剥
    chan_mid_result = f_chan_mid.result() or {}
    wyck_result = f_wyk.result() or {}
    wyck_mid_result = f_wyk_mid.result() or {}
    momentum_result = f_mom.result() or {}

    # ── ATR / Supertrend / VWAP 展示增强（方案 A+B）──
    # Supertrend 趋势带方向对动量做「只确认不否决」微调（方案 B）
    from trader_shared.plugins.momentum_plugin import apply_supertrend_nudge
    _st = calc_supertrend(bars)
    _st_dir = _st.get("direction")
    momentum_result = apply_supertrend_nudge(momentum_result, _st_dir)
    # VWAP：复用快照内 5 分钟 K 线，避免每次渲染重拉行情
    _vwap_res = calc_vwap(bars_5m, current_price=current)
    # 注入 5m 供 VwapPlugin 在 analyze_all 路径使用（与 build_report 直算结果一致）
    quote["_bars_5m"] = bars_5m

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

    # === 融合层 ===
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
        )
    except Exception as _e:
        _logger.warning(
            "merge_decisions 崩溃 (data_status=%s, symbol=%s):\n%s",
            snapshot.data_status, sec.ts_code if snapshot.security else "?",
            traceback.format_exc(),
        )
        report_fusion = {"action": "融合层异常", "confidence": 0, "weighted_score": 0,
                         "regime": "", "hmm_regime": "range", "disagreement": 0, "signals_detail": {}, "weights_used": {}}

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

    # 筹码数据：优先 Tushare cyq_perf（官方数据更准确），fallback 到内部算法
    chip = None
    try:
        from trader_shared.chip_data import get_cyq_perf
        _cyq = get_cyq_perf(sec.ts_code, start_date="", end_date="")
        if _cyq:
            _latest = _cyq[-1]
            _winner_rate = float(_latest.get("winner_rate", 0) or 0)
            _cost_50 = float(_latest.get("cost_50pct", 0) or 0)
            # 将 cost_5/15/50/85/95pct 转为 peaks 格式
            _peaks = []
            for _pct_key, _share in [("cost_5pct", 5), ("cost_15pct", 15), ("cost_50pct", 50), ("cost_85pct", 85), ("cost_95pct", 95)]:
                _price = float(_latest.get(_pct_key, 0) or 0)
                if _price > 0:
                    _peaks.append({"price": _price, "share_of_total": _share})
            chip = {
                "current_pct": _winner_rate,
                "mid_price": _cost_50,
                "peaks": _peaks,
                "source": "tushare_cyq_perf",
            }
    except Exception:
        pass
    if chip is None:
        chip = _calc_chip(bars, lookback=60)
        chip["source"] = "internal_calc"
    chip_peaks = sorted(chip.get("peaks", []) or [], key=lambda x: x["price"])

    # 筹码搬家监控：保存快照 + 对比历史
    chip_migration = {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}
    if _CHIP_MIGRATION_AVAILABLE and chip_peaks:
        try:
            chip_migration = check_chip_migration(target, chip, bars=bars)
            save_chip_snapshot(target, chip, trade_date=quote.get("trade_date"))
        except Exception:
            pass

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
            # 提取月线数据
            monthly_bars = snapshot.monthly_bars if hasattr(snapshot, "monthly_bars") else []
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

    # 60分钟卖点确认 → 提升融合层卖方置信度
    # 注：买方 timing 信号已通过 weighted_score 正值体现，此处仅对卖方补充置信度
    _sell_timing = resonance_result.get("sell_timing_score", 0)
    if _sell_timing >= 1 and report_fusion.get("weighted_score", 0) < 0:
        _boost = 0.05 * _sell_timing  # +0.05 per sell_timing point
        report_fusion["confidence"] = min(0.95, report_fusion.get("confidence", 0) + _boost)

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

    report = {
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
        "chip_peaks": chip_peaks,
        "chip_current_pct": chip.get("current_pct"),
        "chip_mid_price": chip.get("mid_price"),
        "fusion": report_fusion,
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
        # "extend_fundamental": snapshot.extend_fundamental,
        # "extend_sentiment": snapshot.extend_sentiment,
        # Phase 1 新增：资金面数据（仅展示，不参与评分）
        "extend_margin": snapshot.extend_margin,
        "extend_northbound": snapshot.extend_northbound,
        "extend_sector": _sector_data,
        # Phase 2 新增：概念板块数据（仅展示，不参与评分）
        "extend_concept": snapshot.extend_concept,
    }

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

    # 已有持仓模式：确定成本价和持仓状态
    # 必须在 compute_position_with_env() 之前，以便传入正确的 pnl_pct
    # 成本价已在 bars 获取后从 signals.jsonl 读取（与胜率合并为一次 I/O）
    if cost_price <= 0:
        cost_price = _signal_cost_price
    
    has_position = cost_price > 0
    report["has_position"] = has_position
    report["cost_price"] = cost_price
    
    # 如果有持仓，计算盈亏比例
    pnl_pct = 0.0
    if has_position and cost_price > 0:
        pnl_pct = (current - cost_price) / cost_price * 100
        report["pnl_pct"] = pnl_pct
        report["pnl_text"] = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"

    # 仓位计算（阶段 + 大盘环境）
    from trader_shared.stage_positioning import compute_position_with_env
    market_env_level = market_env_data.get("level", "震荡市")
    env_map = {"正常": "牛市", "偏弱": "震荡市", "很差": "熊市"}
    mapped_env = env_map.get(market_env_level, "震荡市")
    position_info = compute_position_with_env(
        stage=stage_result["major_stage"],
        momentum=stage_result["momentum"],
        market_env=mapped_env,
        pnl_pct=pnl_pct,
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
        high_zone_lower=float(levels.get("high_zone_lower") or 0),
        trailing_stop=levels.get("trailing_stop"),
        last_add_date=bars_date,
    )
    report["position_state"] = position_state

    # 阶段止损
    ma20_val = levels["ma_values"].get("ma20")
    stage_stop_info = compute_stage_stop(
        stage=stage_result["major_stage"],
        ma20=ma20_val,
        range_low=float(report.get("range_low") or 0),
        atr_pct=float(levels.get("atr_pct") or 0.02),
        expma20=expma20_val,
    )
    report["stage_stop"] = stage_stop_info
    
    # 补全 JSON 输出需要的字段
    report = sync_report_with_data(report, levels)

    # structure_note: 在 sync_report_with_data 之后计算，使用已修正的 scene
    structure_note = structure_view({
        "current": current, "confirm": confirm, "stage": stage,
        "base_status": base_status, "theory_status": theory_status,
        "scene": str(report.get("scene") or scene),
    })
    report["structure_note"] = structure_note

    # one_liner: 一句话总结
    _support = report.get("support")
    low_zone = str(report.get("low_zone") or (f"{_support*0.98:.2f}-{_support*1.02:.2f}元" if _support else "数据不足"))
    report["one_liner"] = one_sentence(report, low_zone)

    # t0_ref: T0 参考价位（high_sell 用阻力位而非 confirm，避免 T0 卖价高于报告显示的压力位）
    report["t0_ref"] = {
        "low_buy": float(report.get("support") or 0),
        "high_sell": float(report.get("resistance") or 0),
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

    # ── [2.5] 量能真空区检查 ──
    try:
        from trader_shared.volume_profile import check_volume_vacuum
        volume_vacuum = check_volume_vacuum(bars, current)
        report["volume_vacuum"] = volume_vacuum
    except Exception:
        report["volume_vacuum"] = {"vacuum_warning": False, "warning_text": ""}

    # 个股股性透视卡：历史胜率（与成本推断合并为一次 I/O，已在上面读取）
    report["win_rate_data"] = _signal_win_rate

    # ── 一致性仲裁：给 fusion action + suggested_pct 加持仓场景标签 ──
    # 四个字段（theory_status / fusion.action / suggested_pct / stop）来自独立模块，
    # 可能互斥（如 fusion 说「减仓」但 suggested_pct=0%）。
    # 通过 holding_hint + suggested_pct_context 消除互斥语义，让 AI 事实表不再打架。
    from trader_shared.stage_positioning import action_for_holding_state
    fusion_action_str = str((report_fusion or {}).get("action") or "").strip()
    holding_state = action_for_holding_state(fusion_action_str, has_position)
    report["fusion_holding_hint"] = holding_state.get("holding_hint", "待定")

    suggested = int((report.get("position_info") or {}).get("suggested_pct") or 0)
    _reduce_set = {"减仓", "空仓/止损", "空仓 (大盘很差, 一票否决)"}
    if suggested == 0:
        if fusion_action_str in _reduce_set:
            report["suggested_pct_context"] = "0%（未持仓者不参与；已有仓位者执行减仓）"
        else:
            report["suggested_pct_context"] = "0%（阶段建议空仓观望）"
    else:
        report["suggested_pct_context"] = f"{suggested}%（阶段×大盘环境建议）"

    # ── 短中线：关键价 + 纪律门控 + 结论块（只读，不改写 stage/fusion/stop）──
    # weekly_frame 在 mid_key_prices 算出后由 compute_weekly_frame 填充
    report["weekly_frame"] = None
    try:
        from trader_shared.key_prices import build_key_prices
        from trader_shared.mid_key_prices import build_mid_key_prices
        from trader_shared.mistery_gate import compute_mistery_gate
        from trader_shared.conclusion_block import build_conclusion_block, build_daily_ruling
        from trader_shared.config import MISTERY_MIN_RR
        from trader_shared.chan_discipline import (
            apply_chan_discipline,
            merge_discipline,
            compute_weekly_frame,
            compute_pivot_position,
        )

        _ma20 = None
        for _ma_src in (report.get("ma_raw"), report.get("ma"), report.get("mas")):
            if not isinstance(_ma_src, dict):
                continue
            try:
                _ma20 = float(_ma_src.get("ma20") or 0) or None
            except (TypeError, ValueError):
                _ma20 = None
            if _ma20:
                break

        key_prices = build_key_prices(
            current=current,
            support=float(report.get("support") or 0) or None,
            stop=float(report.get("stop") or 0) or None,
            confirm=float(report.get("confirm") or 0) or None,
            resistance=float(report.get("resistance") or 0) or None,
            ma20=_ma20,
            low_zone_lower=float(report.get("low_zone_lower") or 0) or None,
            low_zone_upper=float(report.get("low_zone_upper") or 0) or None,
            key_levels=report.get("key_levels") or {},
            take=float(report.get("take") or 0) or None,
        )
        # 场景/融合偏空时强制「不追」，避免 RR 好看但结论打架
        _sc = str(report.get("scene") or scene or "")
        _fa = str((report_fusion or {}).get("action") or "")
        _force_no_chase = any(k in _sc for k in ("冲高", "减仓", "高抛", "暂不碰")) or any(
            k in _fa for k in ("减仓", "空仓", "止损")
        )
        if _force_no_chase and key_prices.get("line_chase"):
            key_prices["chase_ok"] = False
            _lc = str(key_prices["line_chase"])
            if "→" in _lc:
                key_prices["line_chase"] = _lc.split("→")[0].rstrip() + " → 不追"
            else:
                key_prices["line_chase"] = _lc + " → 不追"
        report["key_prices"] = key_prices

        # 中线关键价（独立周线引擎；与短线 key_prices 分轨）
        # 禁止日 K key_levels 作 mid 主参（默认忽略；仅 MIDLINE_PRICE_DAILY_FALLBACK）
        mid_key_prices = build_mid_key_prices(
            current=current,
            weekly_bars=weekly_bars or [],
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
        )
        report["mid_key_prices"] = mid_key_prices

        # R9 weekly_frame + R6 中枢位置（周/日）
        _life = None
        try:
            _life = float(mid_key_prices.get("life_line") or 0) or None
        except (TypeError, ValueError):
            _life = None
        _zones_weekly = []
        _zones_daily = []
        try:
            _cmid = report.get("chanlun_midline") or {}
            if isinstance(_cmid, dict) and "chanlun" in _cmid:
                _cmid_inner = _cmid.get("chanlun") or {}
            else:
                _cmid_inner = _cmid if isinstance(_cmid, dict) else {}
            _zones_weekly = list(_cmid_inner.get("zones") or [])
            _st_weekly = str(_cmid_inner.get("structure_type") or "")
        except Exception:
            _st_weekly = ""
            _zones_weekly = []
        try:
            _cday0 = report.get("chanlun") or report.get("chan") or {}
            if isinstance(_cday0, dict) and "chanlun" in _cday0:
                _cday_inner0 = _cday0.get("chanlun") or {}
            else:
                _cday_inner0 = _cday0 if isinstance(_cday0, dict) else {}
            _zones_daily = list(_cday_inner0.get("zones") or [])
            _st_daily = str(
                _cday_inner0.get("structure_type")
                or report.get("chan_structure_type")
                or ""
            )
        except Exception:
            _st_daily = str(report.get("chan_structure_type") or "")
            _zones_daily = []
        _zh_bottom_w = None
        for _z in reversed(_zones_weekly):
            if isinstance(_z, dict) and _z.get("valid") is not False:
                try:
                    _zb = float(_z.get("zh_bottom") or 0) or None
                except (TypeError, ValueError):
                    _zb = None
                if _zb:
                    _zh_bottom_w = _zb
                    break
        report["weekly_frame"] = compute_weekly_frame(
            current, _life, zh_bottom=_zh_bottom_w, zones=_zones_weekly,
            weekly_bars=weekly_bars or [],
        )
        report["pivot_position_weekly"] = compute_pivot_position(current, _zones_weekly)
        report["pivot_position_daily"] = compute_pivot_position(current, _zones_daily)

        _regime = ""
        if isinstance(market_env_data, dict):
            _regime = str(market_env_data.get("level") or "")
        if not _regime:
            _regime = str((report_fusion or {}).get("regime") or "")

        # 中线看法文案（与 conclusion 同源）供纪律：偏空则禁止以短线买点主开仓
        from trader_shared.conclusion_block import _midline_view_from_theory
        _mid_view_txt = _midline_view_from_theory(
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
            weekly_frame=report.get("weekly_frame"),
        )
        _chan_u = report.get("chanlun_midline") or {}
        if isinstance(_chan_u, dict) and "chanlun" in _chan_u:
            _chan_inner = _chan_u.get("chanlun") or {}
        else:
            _chan_inner = _chan_u if isinstance(_chan_u, dict) else {}
        _mid_struct_conf = str(
            (_chan_inner or {}).get("structure_confidence")
            or (report.get("chanlun_midline") or {}).get("structure_confidence")
            or ""
        )
        _cm = report.get("chip_migration") if isinstance(report.get("chip_migration"), dict) else {}
        _chip_warn = str(_cm.get("warning_level") or "") not in ("", "none", "None")
        _fund_veto = bool((report_fusion or {}).get("fund_flow_outflow_veto"))
        try:
            _fusion_dis = (report_fusion or {}).get("disagreement")
            _fusion_dis = int(_fusion_dis) if _fusion_dis is not None else 0
        except (TypeError, ValueError):
            _fusion_dis = 0
        # 专家 conf 均值
        _fconf = None
        try:
            _sd = (report_fusion or {}).get("signals_detail") or {}
            _cs = []
            for _n in ("chan", "momentum", "wyckoff"):
                _s = _sd.get(_n) if isinstance(_sd.get(_n), dict) else {}
                if _s.get("confidence") is not None:
                    _cs.append(float(_s["confidence"]))
            if _cs:
                _fconf = sum(_cs) / len(_cs)
        except (TypeError, ValueError):
            _fconf = None

        # 通用门控（瘦身：无回踩/mid_view/筹码缠侧规则；weekly_frame 破坏由 chan 主裁）
        mistery_gate = compute_mistery_gate({
            "major_stage": stage_result["major_stage"],
            "short_term_momentum": stage_result["momentum"],
            "theory_status": theory_status,
            "scene": str(report.get("scene") or scene),
            "regime": _regime,
            "current": current,
            "support": report.get("support"),
            "stop": report.get("stop"),
            "confirm": report.get("confirm"),
            "suggested_pct": suggested,
            "ma20": _ma20,
            "buy_ref": key_prices.get("buy_ref"),
            "risk": key_prices.get("risk"),
            "reward_near": key_prices.get("reward_near"),
            "turnover_rate": report.get("turnover_rate"),
            "volume_ratio": report.get("volume_ratio"),
            "change_pct": report.get("change_pct"),
            "min_rr": MISTERY_MIN_RR,
            "weekly_frame": report.get("weekly_frame"),
            "data_status": report.get("data_status") or snapshot.data_status,
            "fusion_disagreement": _fusion_dis,
            "fusion_confidence": _fconf,
        })
        report["mistery_gate"] = mistery_gate

        # 日线买点类型（若有）供缠纪律冲突 notes
        _buy_point_types = []
        try:
            _chan_day = report.get("chanlun") or report.get("chan") or {}
            if isinstance(_chan_day, dict) and "chanlun" in _chan_day:
                _chan_day = _chan_day.get("chanlun") or {}
            for _bp in (_chan_day.get("buy_points") or []):
                if isinstance(_bp, dict) and _bp.get("type"):
                    _buy_point_types.append(str(_bp["type"]))
        except Exception:
            _buy_point_types = []

        chan_d = apply_chan_discipline({
            "current": current,
            "mid_pullback_low": mid_key_prices.get("pullback_low"),
            "mid_pullback_high": mid_key_prices.get("pullback_high"),
            "mid_view": _mid_view_txt,
            "mid_quality": mid_key_prices.get("quality"),
            "structure_confidence": _mid_struct_conf,
            "buy_point_types": _buy_point_types,
            "structure_type_daily": _st_daily,
            "structure_type_weekly": _st_weekly,
            "low_zone_lower": report.get("low_zone_lower"),
            "low_zone_upper": report.get("low_zone_upper"),
            "life_line": _life,
            "zh_bottom": _zh_bottom_w,
            "zones": _zones_weekly,
            "weekly_frame": report.get("weekly_frame"),
            "data_status": report.get("data_status") or snapshot.data_status,
            "fusion_disagreement": _fusion_dis,
            "fusion_confidence": _fconf,
            "major_stage": stage_result["major_stage"],
            "chip_migration_warning": _chip_warn,
            "fund_flow_outflow_veto": _fund_veto,
            "has_position": has_position,
            "suggested_pct": suggested,
            "max_position_pct": 50,
        })
        report["chan_discipline"] = chan_d

        discipline = merge_discipline(mistery_gate, chan_d, max_position_pct=50)
        report["discipline"] = discipline

        # 只收紧：禁止新开时裁 suggested_pct / 出手语义；R5 同步 position_info
        _disc_action = str(discipline.get("action") or mistery_gate.get("action") or "观望")
        _disc_cap = discipline.get("suggested_pct_cap")
        if _disc_cap is None:
            _disc_cap = discipline.get("position_cap_pct")
        try:
            _disc_cap_f = float(_disc_cap if _disc_cap is not None else 0)
        except (TypeError, ValueError):
            _disc_cap_f = 0.0
        try:
            _sug = float(report.get("suggested_pct") if report.get("suggested_pct") is not None else suggested or 0)
        except (TypeError, ValueError):
            _sug = float(suggested or 0) if suggested is not None else 0.0
        if not discipline.get("allow_new_entry", True):
            if has_position:
                _final_sug = min(_sug, _disc_cap_f) if _disc_cap_f > 0 else 0
            else:
                _final_sug = 0
            if _final_sug == 0:
                if has_position:
                    report["suggested_pct_context"] = "0%（纪律禁止加仓；持仓按减仓/观察）"
                else:
                    report["suggested_pct_context"] = "0%（纪律不新开）"
        else:
            if _disc_cap_f >= 0 and _sug > _disc_cap_f:
                _final_sug = _disc_cap_f
                report["suggested_pct_context"] = (
                    f"{int(_final_sug) if _final_sug == int(_final_sug) else _final_sug}%（纪律 cap 收紧）"
                )
            else:
                _final_sug = _sug
        if isinstance(_final_sug, float) and _final_sug == int(_final_sug):
            _final_sug = int(_final_sug)
        report["suggested_pct"] = _final_sug
        if isinstance(report.get("position_info"), dict):
            report["position_info"]["suggested_pct"] = _final_sug

        daily_ruling = build_daily_ruling(
            report_fusion,
            scene=str(report.get("scene") or scene),
            theory_status=theory_status,
            chase_ok=bool(key_prices.get("chase_ok")),
            gate_action=_disc_action,
        )
        # 结论块：优先读 merge 后的 discipline（兼容仍传 mistery_gate 字段）
        _gate_for_conclusion = dict(mistery_gate)
        _gate_for_conclusion["action"] = _disc_action
        _gate_for_conclusion["position_cap_pct"] = _disc_cap_f
        _gate_for_conclusion["notes"] = discipline.get("notes") or mistery_gate.get("notes") or ""
        _gate_for_conclusion["hard_block"] = discipline.get("hard_block") or mistery_gate.get("hard_block")
        _gate_for_conclusion["invalidation"] = discipline.get("invalidation") or mistery_gate.get("invalidation")

        conclusion = build_conclusion_block(
            major_stage=stage_result["major_stage"],
            short_term_momentum=stage_result["momentum"],
            scene=str(report.get("scene") or scene),
            theory_status=theory_status,
            regime=_regime,
            mistery_gate=_gate_for_conclusion,
            discipline=discipline,
            key_prices=key_prices,
            fusion=report_fusion,
            has_position=has_position,
            daily_ruling=daily_ruling,
            weekly_frame=report.get("weekly_frame"),
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
            chanlun_daily=report.get("chanlun_daily"),
            current_price=current,
            chip_migration=report.get("chip_migration"),
            chip_migration_warning=_chip_warn,
            fund_flow_outflow_veto=_fund_veto,
        )
        report["conclusion"] = conclusion
        report["daily_ruling"] = daily_ruling
    except Exception as _sm_exc:
        # 短中线组装失败不阻断主报告；保留原字段
        report.setdefault("key_prices", {})
        report.setdefault("mid_key_prices", {})
        report.setdefault("mistery_gate", {
            "hard_block": "none", "style": "不明", "action": "观望",
            "invalidation": "", "position_cap_pct": 0.0, "notes": f"gate_error:{_sm_exc}",
        })
        report.setdefault("chan_discipline", {
            "allow_new_entry": False, "entry_block_reason": f"gate_error:{_sm_exc}",
            "suggested_pct_cap": 0, "action_override": "观望",
            "discipline_notes": [], "rules_fired": [],
        })
        report.setdefault("discipline", {
            "allow_new_entry": False, "action": "观望", "suggested_pct_cap": 0,
            "position_cap_pct": 0.0, "entry_block_reason": f"gate_error:{_sm_exc}",
            "discipline_notes": [], "notes": f"gate_error:{_sm_exc}",
            "hard_block": "none", "invalidation": "",
        })
        report.setdefault("conclusion", {
            "midline": "数据组装异常", "stage_line": "", "shortline": "观察",
            "execution": "现价不买 · 不追", "reason": "门控组装失败",
            "this_week": "观察", "conflict": "", "daily_ruling": "中性，观望",
        })

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
        _zw = float(levels.get("zone_width_pct", 0.02) or 0.02)
        report["take"] = round(confirm * (1 + _zw), 2)
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
    elif stage in ("转弱", "衰退"):
        return f"趋势仍在弱区，结论：启动条件不足，先不做进攻判断。"
    elif stage == "派发":
        return f"派发期，动能减弱，结论：逢高减仓，暂不追涨。"
    elif current >= confirm - width * 0.25:
        return f"价格接近确认区但还未站稳，结论：属于预备启动，等待放量确认。"
    return f"价格还没贴近确认区，结论：动能仍是弱修复，暂不按启动处理。"


def _get_buy_label(change_pct: float, volume_ratio: float) -> str:
    """根据当日涨跌和量比动态生成试探买标签。"""
    is_shrink = volume_ratio > 0 and volume_ratio < 0.8
    is_expand = volume_ratio >= 1.2

    if is_expand:
        return "放量企稳"
    if is_shrink:
        if change_pct < -3:
            return "回踩缩量"
        elif change_pct > 3:
            return "上涨缩量"
        elif abs(change_pct) <= 1:
            return "横盘缩量"
        return "缩量整理"
    return "试探买入"


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


def render_markdown(r: dict, *, _kelly_cache_only: dict[str, float] | None = None) -> str:
    """渲染 Markdown 报告。

    生产入口已锁定为 trader_shared.report_core.render_single（final_report 使用）。
    本函数保留供历史测试 / 池内旧路径兼容；短中线默认模板请走 report_core，
    避免双源漂移。若 SHORT_MIDLINE_REPORT=true，直接委托 report_core。

    `_kelly_cache_only` 是内部参数，用于传入预计算的 Kelly 数据，
    避免在每只股票渲染时重复读取 signal_results.jsonl。
    """
    # 与 final_report 对齐：短中线模式共用 render_single，消除双模板
    try:
        from trader_shared.config import SHORT_MIDLINE_REPORT
        if SHORT_MIDLINE_REPORT:
            from trader_shared.report_core import render_single
            return render_single(r)
    except Exception:
        pass

    ma = r.get("ma") or {}
    ma_raw = r.get("ma_raw") or ma
    display_code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    name = str(r.get("name", ""))

    atr14 = float(r.get("atr14", 0) or 0)
    atr_ratio = float(r.get("atr_ratio", 0) or 0)
    atr_level = str(r.get("atr_level") or "")

    confirm = float(r.get("confirm") or 0)
    low_price = float(r.get("support") or 0)
    stop = float(r.get("stop") or 0)
    resistance_val = float(r.get("resistance") or 0)
    current_price = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    position_cap = int(r.get("position_cap") or 10)

    major_stage = str(r.get("major_stage") or "")
    if not major_stage:
        old_stage = str(r.get("stage") or "")
        stage_map = {
            "修复": "蓄势",
            "走强": "主升",
            "震荡": "蓄势",
            "转弱": "衰退",
        }
        major_stage = stage_map.get(old_stage, old_stage)
    momentum = str(r.get("short_term_momentum") or "")
    
    stage_action_map = {
        "蓄势": "低吸高抛",
        "主升": "持股待涨",
        "派发": "逢高减仓",
        "衰退": "不碰",
    }
    stage_action_text = stage_action_map.get(major_stage, major_stage)
    
    ma5_text = f"{ma_raw.get('ma5', 0):.2f}" if isinstance(ma_raw.get("ma5"), (int, float)) else "--"
    ma10_text = f"{ma_raw.get('ma10', 0):.2f}" if isinstance(ma_raw.get("ma10"), (int, float)) else "--"
    ma20_text = f"{ma_raw.get('ma20', 0):.2f}" if isinstance(ma_raw.get("ma20"), (int, float)) else "--"
    ma30_text = f"{ma_raw.get('ma30', 0):.2f}" if isinstance(ma_raw.get("ma30"), (int, float)) else "--"
    ma250_text = f"{ma_raw.get('ma250', 0):.2f}" if isinstance(ma_raw.get("ma250"), (int, float)) else "--"

    # 相对大盘强度（紧跟现价）
    market_env_data = r.get("market_env") or {}
    market_idx_chg = float(market_env_data.get("change_pct") or market_env_data.get("index_change_pct") or 0)
    rel_str = change_pct - market_idx_chg
    rel_label = "强于大盘" if rel_str > 0.5 else ("弱于大盘" if rel_str < -0.5 else "与大盘同步")

    lines: list[str] = [
        f"分析报告 — {name}（{display_code}）",
        "",
        f"现价 {current_price:.2f}（{change_pct:+.2f}%）{rel_label}",
    ]

    # 均线显示（冒号分隔 + 2 位小数，与 output-template 契约一致）
    # 必须包含 MA250 以通过 validate_output.py 的 MA20+MA250 同行验证
    ma_parts = []
    for ma_key in ("ma5", "ma10", "ma20", "ma30", "ma250"):
        if ma_raw.get(ma_key) and isinstance(ma_raw.get(ma_key), (int, float)) and ma_raw[ma_key] > 0:
            ma_num = int(ma_key[2:])
            ma_parts.append(f"MA{ma_num}：{ma_raw[ma_key]:.2f}")
    if ma_parts:
        lines.append(f"  {' ｜ '.join(ma_parts)}")

    # 量能 + 距高低点（合并为 1 行）
    volume_ratio_val = float(r.get("volume_ratio") or 0)
    turnover_val = float(r.get("turnover_rate") or 0)
    bars_for_range = r.get("daily_bars") or []
    dist_20h_str = "--"
    dist_20l_str = "--"
    if len(bars_for_range) >= 20 and current_price > 0:
        highs = [float(b.get("high") or 0) for b in bars_for_range[-20:] if float(b.get("high") or 0) > 0]
        lows = [float(b.get("low") or 0) for b in bars_for_range[-20:] if float(b.get("low") or 0) > 0]
        if highs:
            max20 = max(highs)
            dist_20h_str = f"{(current_price - max20) / max20 * 100:+.1f}%"
        if lows:
            min20 = min(lows)
            dist_20l_str = f"{(current_price - min20) / min20 * 100:+.1f}%"

    vol_parts = []
    if volume_ratio_val > 0:
        vol_label = "放量" if volume_ratio_val >= 1.5 else ("缩量" if volume_ratio_val <= 0.7 else "平量")
        vol_parts.append(f"量比{volume_ratio_val:.1f}（{vol_label}）")
    if turnover_val > 0:
        vol_parts.append(f"换手{turnover_val:.1f}%")
    if dist_20h_str != "--" and dist_20l_str != "--":
        dist_parts = []
        dist_num_h = float(dist_20h_str.replace("%", ""))
        dist_num_l = float(dist_20l_str.replace("%", ""))
        if dist_num_h >= 0:
            dist_parts.append(f"高{dist_20h_str}")
        elif dist_num_h > -5:
            dist_parts.append(f"距高{dist_20h_str}")
        else:
            dist_parts.append(f"距高{abs(dist_num_h):.1f}%")
        if dist_num_l <= 0:
            dist_parts.append(f"低{dist_20l_str}")
        elif dist_num_l < 5:
            dist_parts.append(f"距低{dist_20l_str}")
        else:
            dist_parts.append(f"距低+{dist_num_l:.1f}%")
        if dist_parts:
            vol_parts.append("｜".join(dist_parts))
    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # 年线警告（股价在250日均线下方时显示）
    ma250_warning = r.get("ma250_warning", False)
    ma250_val = r.get("ma250")
    if ma250_warning and ma250_val and ma250_val > 0:
        lines.append(f"  ⚠️ 股价在年线（{ma250_val:.2f}）下方运行，注意风险")

    lines.extend([
        "",
    ])

    # 数据完整性检查：仅当关键数据真正缺失时才提示
    # （data_status=partial 只是 quote 的 current_price 缺失，
    #  report 已有 fallback 现价；risk_reward/ 等是 AI 计算的衍生字段，非必需）
    current_val = r.get("current")
    stop_val = r.get("stop")
    support_val = r.get("support")
    if current_val is None or current_val == 0 or stop_val is None or stop_val == 0:
        lines.append("")
        lines.append("⚠️ 关键数据缺失，分析仅供参考")

    # 融合层输出 — 3 行：阶段+建议 ｜ 理论分析 ｜ 冲突比
    fusion_data = r.get("fusion") or {}
    fusion_action = str(fusion_data.get("action") or "未知")
    disagreement_count = int(fusion_data.get("disagreement", 0))
    fusion_signals = fusion_data.get("signals_detail") or {}
    _STAGE_LABELS = {
        "accumulation": "吸筹期", "testing": "试盘期", "markup": "拉升期",
        "distribution": "派发期", "markdown": "砸盘期",
    }

    # 1. 拆分动作词和理由
    _action_word = fusion_action
    _reason = ""
    if "（" in fusion_action:
        _action_word = fusion_action.split("（")[0].strip()
        _reason = fusion_action.split("（")[1].rstrip("）").strip()
    elif "(" in fusion_action:
        _action_word = fusion_action.split("(")[0].strip()
        _reason = fusion_action.split("(")[1].rstrip(")").strip()
    #  regime override 覆盖：一票否决时显示真实决策，不显示融合原始信号
    _real_status = str(r.get("base_status") or "")
    if _real_status in ("暂不碰", "风险回避", "空仓规避") and _real_status != _action_word:
        _action_word = _real_status

    # 2. 四阶段定位：蓄势/主升/派发/衰退 + 动能
    _major_stage = str(r.get("major_stage") or "")
    if _major_stage == "None":
        _major_stage = ""
    # momentum 可能是 dict 包含 direction/信号等
    _raw_mom = r.get("momentum")
    _momentum = ""
    if isinstance(_raw_mom, dict):
        _mom_dir = _raw_mom.get("momentum", {})
        if isinstance(_mom_dir, dict):
            _mom_val = _mom_dir.get("direction", "") or _mom_dir.get("label", "")
            # 英文 → 中文
            _MOM_MAP = {"bullish": "走强", "bearish": "转弱", "neutral": "震荡", "flat": "震荡"}
            _momentum = _MOM_MAP.get(_mom_val, _mom_val)
    elif isinstance(_raw_mom, str) and _raw_mom != "None":
        _momentum = _raw_mom
    _stage_str = _major_stage

    # 3. 第一行：四阶段 → 动作
    # 检查一票否决
    _veto = fusion_data.get("fund_flow_outflow_veto_msg") or ""
    _veto_part = f"（{_veto}）" if _veto else ""

    if _stage_str:
        lines.append(f"🎯 {_stage_str} → {_action_word}{_veto_part}")
    elif _reason:
        lines.append(f"🎯 {_reason} → {_action_word}{_veto_part}")
    else:
        lines.append(f"🎯 {_action_word}{_veto_part}")


    # 4. 理论状态 — 缠论/动量用 fusion reason；威科夫一行人话
    for _sig_key, _sig_label in (("chan", "缠论"), ("momentum", "动量")):
        if _sig_key not in fusion_signals:
            continue
        _sig = fusion_signals[_sig_key]
        if not isinstance(_sig, dict):
            continue
        _state = str(_sig.get("reason", "") or "").strip()
        _dir = _sig.get("direction", 0)
        _dir_label = "看涨" if _dir > 0 else ("看跌" if _dir < 0 else "中性")
        if not _state or _state == "无明确信号":
            _state = "无信号"
        _state = _state.replace(_sig_label, "").strip()
        if _state.startswith(":"):
            _state = _state[1:]
        lines.append(f"  {_sig_label}:{_state}·{_dir_label}")

    try:
        from trader_shared.wyckoff_core import format_wyckoff_oneline
        _w_sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
        _w_dir = _w_sig.get("direction") if _w_sig else None
        _wyk_raw = r.get("wyckoff")
        if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
            _wyk_raw = _wyk_raw.get("wyckoff")
        lines.append(
            f"  {format_wyckoff_oneline(_wyk_raw if isinstance(_wyk_raw, dict) else {}, direction=_w_dir)}"
        )
    except Exception:
        lines.append("  威科夫：暂无明确信号 · 中性")

    # 5. 冲突比（第三行，如有）
    if disagreement_count > 0 and fusion_signals:
        _bull_count = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) > 0)
        _bear_count = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) < 0)
        lines.append(f"  {_bull_count}方看多 vs {_bear_count}方看空")

    # 双状态行（仅两者不同时显示，避免与 🎯 行重复）
    bs = str(r.get("base_status") or "")
    ts = str(r.get("theory_status") or "")
    if bs and ts:
        lines.extend(["", f"  基础状态：{bs} ｜ 体系结论：{ts}"])

    # ── 📊 趋势轨道（参考，展示型，不进融合）──
    # #5: data_status=partial 时基础数据不完整，趋势带/VWAP 可能失准，加警告
    _data_partial = r.get("data_status") == "partial"

    _st_dir = r.get("supertrend_direction")
    if _st_dir:
        _st_emoji = "🟢" if _st_dir == "up" else ("🔴" if _st_dir == "down" else "⚪")
        _st_label = "多头" if _st_dir == "up" else ("空头" if _st_dir == "down" else "中性")
        _st_stop = r.get("supertrend_stop")
        _st_vol = r.get("supertrend_vol_level") or ""
        _st_atr = float(r.get("supertrend_atr") or r.get("atr14") or 0)
        lines.append("")
        lines.append("📊 趋势轨道（参考）")
        if _data_partial:
            lines.append("  ⚠️ 数据不完整，趋势带可能失准")
        if _st_atr and _st_atr > 0:
            lines.append(f"  ATR {_st_atr:.2f}元（{_st_vol}）")
        if _st_stop:
            _st_dist = (current_price - _st_stop) / _st_stop * 100 if _st_stop else 0
            lines.append(f"  轨道：{_st_emoji} {_st_label} {_st_stop:.2f}（距现价 {_st_dist:+.1f}%）— 仅趋势带参考，非止损")
        if ma250_warning and _st_dir == "up":
            lines.append("  ⚠️ 年线下方，趋势带信号谨慎")

    # ── 📈 主力成本（VWAP·当日，展示型，不进融合）──
    _vwap = r.get("vwap")
    if _vwap:
        _vwap_dev = float(r.get("vwap_dev") or 0)
        _vwap_pos = r.get("vwap_position")
        _vwap_emoji = "🟢" if _vwap_pos == "above" else "🔴"
        _vwap_sign = "+" if _vwap_dev >= 0 else ""
        _vwap_level = r.get("vwap_level") or ""
        lines.append("")
        lines.append("📈 主力成本（VWAP·当日）")
        if _data_partial:
            lines.append("  ⚠️ 数据不完整，VWAP 可能失准")
        lines.append(f"  今日VWAP：{_vwap:.2f}元")
        if _vwap_pos == "above":
            lines.append(f"  价格 {_vwap_emoji} 在VWAP之上（当日{_vwap_level}，{_vwap_sign}{_vwap_dev * 100:.1f}%）")
        else:
            lines.append(f"  价格 {_vwap_emoji} 在VWAP之下（当日{_vwap_level}，{_vwap_sign}{_vwap_dev * 100:.1f}%）")

    # 决策摘要（仅非限制状态时显示，避免与🎯和双状态行重复）
    _RESTRICTIVE = frozenset({"暂不碰", "风险回避", "空仓规避", "退场观察"})
    _pos_cap = int(r.get("position_cap") or 0)
    _stop_val = float(r.get("stop") or 0)
    _lz_low = float(r.get("low_zone_lower") or 0)
    _lz_high = float(r.get("low_zone_upper") or 0)
    _action_text = ""
    if not r.get("has_position"):
        if bs not in _RESTRICTIVE and _lz_low > 0 and _lz_high > 0:
            _action_text = f"空仓：在 {_lz_low:.2f}-{_lz_high:.2f}元 试探买 {_pos_cap}%，止损 {_stop_val:.2f}"
    else:
        if bs not in _RESTRICTIVE:
            _take_val = float(r.get("take") or 0)
            if _take_val > 0:
                _action_text = f"有底仓：反弹 {_take_val:.2f} 冲不动减"

    if _action_text:
        lines.extend([
            "",
            "📍 决策",
            f"  {_action_text}"
        ])
    else:
        lines.extend([
            "",
            "📍 决策"
        ])

    # 收集所有价格行，统一排序后输出（确保严格递增）
    all_price_lines: list[tuple[float, str]] = []

    # 止损（独立风控位，不与其他支撑合并）
    if stop > 0:
        all_price_lines.append((stop, f"  {stop:.2f} 止损（跌破支撑，趋势破坏）"))

    # 直接计算盈亏比（不依赖 AI 字段，避免直接运行时永远"数据不足"）
    take_price = float(r.get("take") or 0)
    downside = low_price - stop if stop < low_price else None
    risk_reward_val = None
    if downside and downside > 0 and take_price > low_price:
        risk_reward_val = round((take_price - low_price) / downside, 1)
    risk_reward_available = risk_reward_val is not None and risk_reward_val > 0

    # —— R1 + R2: 场景感知过滤闸门 + Kelly 仓位叠加 ——
    rr_filtered = False
    rr_threshold = 1.5
    min_win_rate = 0
    if risk_reward_available and risk_reward_val is not None and risk_reward_val > 0 and ENABLE_RISK_REWARD_FILTER:
        min_win_rate = round(1 / (1 + risk_reward_val) * 100)
        base_status = str(r.get("base_status") or "")
        market_env_level = market_env_data.get("level", "正常")
        rr_threshold = RISK_REWARD_THRESHOLDS.get(market_env_level, 1.5)
        # 突破场景不过滤
        if base_status in ("突破确认", "突破观察"):
            pass
        elif risk_reward_val < rr_threshold:
            rr_filtered = True
        # R2: Kelly 仓位叠加
        if position_cap > 0 and not rr_filtered:
            try:
                # 优先使用传入的缓存数据（由 main() 预计算），避免重复 I/O
                if _kelly_cache_only is not None:
                    _kdata = _kelly_cache_only
                else:
                    _kdata = _get_kelly_data(market_env_level)
                win_rate = _kdata.get("win_rate")
                total = int(_kdata.get("total", 0))
                if win_rate is not None:
                    R = risk_reward_val
                    kelly = (win_rate * R - (1 - win_rate)) / R
                    kelly = max(0, min(kelly, 0.5))
                    kelly_cap = int(kelly * 2 * KELLY_MAX_TOTAL_POSITIONS)
                    if kelly_cap > 0:
                        position_cap = min(position_cap, kelly_cap)
            except Exception:
                pass

    if low_price > 0 and risk_reward_available and not rr_filtered and risk_reward_val is not None:
        # 动态生成试探买标签
        _buy_label = _get_buy_label(change_pct, volume_ratio_val)
        all_price_lines.append((low_price, f"  {low_price:.2f} ← 试探买 {position_cap}%（{_buy_label}，盈亏比 {risk_reward_val:.1f}:1，{min_win_rate}% 胜率回本，止损 {stop:.2f}）"))
        # 加仓条件：站稳确认位可加仓至最大仓位
        _max_pos = int(r.get("max_position_pct") or 0)
        if _max_pos > position_cap and confirm > 0:
            all_price_lines.append((confirm, f"  {confirm:.2f} 站稳可加仓至 {_max_pos}%（突破阻力确认，趋势延续）"))
    elif low_price > 0 and risk_reward_val is not None and risk_reward_val > 0 and rr_filtered:
        # 盈亏比不足，不显示
        pass
    elif low_price > 0:
        all_price_lines.append((low_price, f"  {low_price:.2f} ← 试探买（等待确认）"))

    # 当前价格
    if current_price > 0:
        all_price_lines.append((current_price, f"  🌟 {current_price:.2f} 当前位置"))
    fib = r.get("fib_retrace") or {}
    golden_bid = fib.get("golden_bid")
    if golden_bid and golden_bid > 0 and golden_bid != low_price:
        level_map = {fib.get("retrace_618"): "61.8%", fib.get("retrace_500"): "50%", fib.get("retrace_382"): "38.2%"}
        label = level_map.get(golden_bid, "")
        lines.append(f"  {golden_bid:.2f} ← 黄金挂单（黄金分割{label}）")
    else:
        # 没有落在低吸区的回撤位，取最接近低吸区的那个作为参考
        low_zone_upper = r.get("low_zone_upper") or (low_price * 1.05 if low_price else 0)
        candidates = []
        for ratio_label, key in [("61.8%", "retrace_618"), ("50%", "retrace_500"), ("38.2%", "retrace_382")]:
            val = fib.get(key)
            if val and val > 0:
                candidates.append((abs(val - low_zone_upper), val, ratio_label))
        if candidates:
            candidates.sort()
            best_val, best_label = candidates[0][1], candidates[0][2]
            if best_val != low_price:
                lines.append(f"  {best_val:.2f} ← 黄金分割{best_label}回撤参考（潜在支撑位）")

    # P0-4: 多周期支撑压力阶梯
    key_levels = r.get("key_levels") or {}
    support_resonance: dict[float, list[str]] = {}
    resist_resonance: dict[float, list[str]] = {}
    if key_levels:
        # P0-5: 长线压力位动态动作
        weighted_score = r.get("weighted_score", 0) or 0
        vol_trend = r.get("vol_trend", "")

        if weighted_score >= 0.25:
            _long_resist_action = "持有关注 / 趋势强"
        elif weighted_score >= 0.1:
            _long_resist_action = "减仓 20%"
        else:
            _long_resist_action = "减仓 50% / 趋势弱"

        # 支撑位（现价下方）：长线 → 中线 → 短线
        for kl_key, label, pct in [
            ("long_support", "长线支撑", "加仓至 20%"),
            ("mid_support", "中线支撑", "首次建仓 10%"),
            ("short_support", "短线支撑", "试探买 5%"),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val < current_price:
                # 去重并收集「三线共振」标签：与已添加价位在 1.5% 容差内合并
                matched = next((ep for ep, _ in all_price_lines if abs(val - ep) / max(ep, 1) < 0.015), None)
                if matched is not None:
                    support_resonance.setdefault(matched, []).append(label)
                    continue
                support_resonance[val] = [label]
                all_price_lines.append((val, f"  {val:.2f} ← {label}（{pct}）"))

        # 压力位（现价上方）：短线 → 中线 → 长线
        for kl_key, label, pct in [
            ("short_resist", "短线压力", "卖 20%"),
            ("mid_resist", "中线压力", "减仓 30%"),
            ("long_resist", "长线压力", _long_resist_action),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val > current_price:
                matched = next((ep for ep, _ in all_price_lines if abs(val - ep) / max(ep, 1) < 0.015), None)
                if matched is not None:
                    resist_resonance.setdefault(matched, []).append(label)
                    continue
                resist_resonance[val] = [label]
                all_price_lines.append((val, f"  {val:.2f} → {label}（{pct}）"))

    exit_plan = r.get("exit_plan") or {}
    stage_exit = exit_plan.get("stage_exit")
    exit_plan_items = exit_plan.get("exit_plan") or []

    for item in exit_plan_items:
        p = item.get("price")
        if p is not None and p > 0:
            # 已过价位不显示为卖点
            if p < current_price:
                continue
            # 去重：与已有价位重复则跳过（容差 1.5%）
            is_dup = any(abs(p - ep) / max(ep, 1) < 0.015 for ep, _ in all_price_lines)
            if is_dup:
                continue
            ratio = item.get("ratio", 0)
            reason = item.get("reason", "")
            all_price_lines.append((p, f"  {p:.2f} → 卖 {ratio:.0%}（{reason}）"))

    if resistance_val > 0:
        pass  # 压力位已整合到卖出条件中，不再单独显示

    # Fibonacci 扩展目标位
    fib_ext_1382 = r.get("fib_ext_1382")
    fib_ext_1618 = r.get("fib_ext_1618")
    if fib_ext_1382 and fib_ext_1382 > resistance_val:
        all_price_lines.append((fib_ext_1382, f"  {fib_ext_1382:.2f} ← 黄金分割138.2%目标"))
    if fib_ext_1618 and fib_ext_1618 > resistance_val:
        all_price_lines.append((fib_ext_1618, f"  {fib_ext_1618:.2f} ← 黄金分割161.8%目标"))

    all_price_lines.sort(key=lambda x: x[0])
    # 「三线共振」标注：短/中/长线同类型算出同一价位（1.5% 容差）时，标注共振而非静默合并
    resonance_map: dict[float, list[str]] = {}
    for v, tags in support_resonance.items():
        if len(tags) >= 2:
            resonance_map[v] = tags
    for v, tags in resist_resonance.items():
        if len(tags) >= 2:
            resonance_map[v] = tags
    annotated_lines = []
    for val, line in all_price_lines:
        tags = resonance_map.get(val)
        if tags:
            suffix = "【三线共振】" if len(tags) >= 3 else "【双线共振】"
            line = line + suffix
        annotated_lines.append((val, line))
    all_price_lines = annotated_lines
    for _, line in all_price_lines:
        lines.append(line)

    if stage_exit and major_stage in ("主升", "拉升"):
        lines.append(f"  阶段转派发 → 清仓（主力出货，趋势结束）")

    # 回踩加仓条件（显示支撑位回踩时的加仓评分）
    _ps = r.get("position_state") or {}
    _pb_score = int(_ps.get("pullback_add_score") or 0)
    _support_val = float(r.get("support") or 0)
    if _support_val > 0:
        _dist_support = (current_price - _support_val) / current_price * 100
        # 列出加仓条件满足情况
        _pb_parts = []
        _pb_parts.append(f"距支撑{_dist_support:.1f}%")
        if _dist_support < 3:
            _pb_parts.append("到位")
        # 缩量
        if volume_ratio_val > 0 and volume_ratio_val < 0.8:
            _pb_parts.append("缩量")
        # RSI（从report的bars_for_range算）
        _bars_for_rsi = r.get("daily_bars") or []
        if _bars_for_rsi and len(_bars_for_rsi) >= 14:
            _closes = [float(b.get("close") or 0) for b in _bars_for_rsi[-14:] if b.get("close")]
            if len(_closes) >= 14:
                _gains = [max(0, _closes[i] - _closes[i-1]) for i in range(1, len(_closes))]
                _losses = [max(0, _closes[i-1] - _closes[i]) for i in range(1, len(_closes))]
                _avg_gain = sum(_gains) / len(_gains) if _gains else 0
                _avg_loss = sum(_losses) / len(_losses) if _losses else 0
                _rs = _avg_gain / max(_avg_loss, 0.01)
                _rsi = 100 - (100 / (1 + _rs))
                if _rsi < 40:
                    _pb_parts.append(f"RSI超卖({_rsi:.0f})")
        if _pb_score >= 3:
            lines.append(f"  {_support_val:.2f} 回踩加仓｜评分 {_pb_score}/5｜{'｜'.join(_pb_parts)}")
        # 支撑回踩观察已整合到试探买条件中，不再单独显示

    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)
    if has_position and cost_price > 0:
        pnl_pct = (current_price - cost_price) / cost_price * 100
        pnl_text = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"
        lines.extend([
            "",
            f"📌 如果你有持仓（成本 {cost_price:.2f}）"
        ])
        # 检查 fusion 层是否有减仓信号（避免忽略空方信号让用户"让利润跑"）
        fusion_action = str((r.get("fusion") or {}).get("action") or "")
        fusion_reduce = fusion_action in ("减仓", "空仓/止损", "减1/3 (高位松动)")

        if pnl_pct >= 0:
            if major_stage == "主升":
                if fusion_reduce:
                    lines.append(f"  现在：持有，但融合层提示{fusion_action}，注意风险（{pnl_text}）")
                else:
                    lines.append(f"  现在：持有，让利润跑（{pnl_text}）")
            elif major_stage == "派发":
                lines.append(f"  现在：减仓，锁定利润（{pnl_text}）")
            else:
                if fusion_reduce:
                    lines.append(f"  现在：融合层提示{fusion_action}，考虑减仓（{pnl_text}）")
                else:
                    lines.append(f"  现在：部分止盈，留底仓等突破（{pnl_text}）")
        else:
            if major_stage == "衰退":
                lines.append(f"  现在：止损，认亏走人（{pnl_text}）")
            elif major_stage == "主升":
                lines.append(f"  现在：持有，主升期大概率会回来（{pnl_text}）")
            else:
                lines.append(f"  现在：持有，不加仓（{pnl_text}）")

        # 成本参考：仅在现价低于成本时显示保本位（已盈时利润已在"现在"行显示）
        if cost_price > 0 and current_price <= cost_price:
            lines.append(f"  反弹到 {cost_price:.2f}：减 50%（保本）")

    chip_peaks = r.get("chip_peaks") or []
    chip_migration = r.get("chip_migration") or {}
    if chip_peaks:
        sorted_peaks = sorted(chip_peaks, key=lambda x: x.get("price", 0))
        peak_strs = []
        for peak in sorted_peaks[:3]:
            p = peak.get("price", 0)
            level = peak.get("support_level", "")
            if p > 0:
                label = f"{p:.2f}"
                if level:
                    label += f"({level})"
                peak_strs.append(label)
        chip_line_parts = [f"筹码：{' · '.join(peak_strs)}"]
        current_pct = r.get("chip_current_pct")
        if current_pct is not None and current_pct > 50:
            chip_line_parts.append(f"获利{current_pct:.0f}%")
        warning_text = chip_migration.get("warning_text", "")
        if "筹码在搬家" in warning_text:
            chip_line_parts.append("搬家")
            lines.append(f"  {' ｜ '.join(chip_line_parts)}")
            lines.append(f"  ⚠️ 筹码搬家：{warning_text}")
        elif "主力在吸筹" in warning_text:
            chip_line_parts.append("吸筹")
            lines.append(f"  {' ｜ '.join(chip_line_parts)}")
        else:
            lines.append(f"  {' ｜ '.join(chip_line_parts)}")

    # ── 个股股性透视卡（build_report 预计算存 report["win_rate_data"]）──
    # 如果缺失（极少见），由于 render 无法获取 bars 数据，只能跳过
    win_rate_data = r.get("win_rate_data")
    if win_rate_data is not None:
        lines.append("")
        lines.append("📊 股性与历史回测")
        buy = win_rate_data.get("buy")
        sell = win_rate_data.get("sell")
        if buy:
            avg_pnl = buy.get('avg_pnl')
            avg_pnl_str = f"{avg_pnl:+.2f}%" if isinstance(avg_pnl, (int, float)) else str(avg_pnl)
            lines.append(f"  买入信号 {buy['count']}次 ｜ {buy['wins']}胜{buy['count']-buy['wins']}负 ｜ 胜率 {buy['win_rate']}% ｜ 平均 {avg_pnl_str}")
        if sell:
            avg_pnl_s = sell.get('avg_pnl')
            avg_pnl_s_str = f"{avg_pnl_s:+.2f}%" if isinstance(avg_pnl_s, (int, float)) else str(avg_pnl_s)
            lines.append(f"  卖出信号 {sell['count']}次 ｜ {sell['wins']}胜{sell['count']-sell['wins']}负 ｜ 胜率 {sell['win_rate']}% ｜ 避坑 {avg_pnl_s_str}")
        if win_rate_data.get("sample_warning"):
            lines.append("  ⚠️ 样本不足，仅供参考")

    lines.append("")
    scene = str(r.get("scene") or "")

    # P0-7: 亮点与风险距离百分比量化
    _kl_highlight = r.get("key_levels") or {}
    _mid_support = float(_kl_highlight.get("mid_support") or 0)
    _short_resist = float(_kl_highlight.get("short_resist") or 0)

    # 亮点：当前价距离支撑的百分比
    if _mid_support > 0 and _mid_support < current_price:
        _dist_sup = (current_price - _mid_support) / current_price * 100
        lines.append(f"✅ 亮点：中线支撑 {_mid_support:.2f} 距当前价 {_dist_sup:.0f}%，下跌空间有限")
    elif current_price >= low_price * 1.005:
        # 兜底：没有 key_levels 时保留原逻辑
        lines.append(f"✅ 亮点：{current_price:.2f} 仍站在防守位 {low_price:.2f} 上方")
    elif current_price >= low_price:
        lines.append(f"⚠️ 现价逼近防守位 {low_price:.2f}，随时可能跌破")
    elif scene in ("破位下行", "风险回避"):
        lines.append(f"⚠️ 亮点：暂无亮点，价格已跌破防守位 {low_price:.2f}，等待企稳信号")
    else:
        lines.append(f"✅ 亮点：价格超跌，关注 {low_price:.2f} 附近企稳机会")

    # 风险：当前价距离压力的百分比
    if _short_resist > 0 and _short_resist > current_price:
        _dist_res = (_short_resist - current_price) / current_price * 100
        lines.append(f"⚠️ 风险：短线压力 {_short_resist:.2f} 距当前价仅 {_dist_res:.0f}%，追高风险大")
    elif "出货" in str(chip_migration.get("warning_text", "")):
        lines.append(f"⚠️ 风险：筹码在搬家，主力在出货，警惕继续下跌")
    elif major_stage == "主升":
        lines.append(f"⚠️ 风险：主升期主要风险是回踩 {low_price:.2f} 支撑未守住")
    elif major_stage == "蓄势":
        # E1: 修正文案歧义
        lines.append(f"⚠️ 风险：突破 {confirm:.2f} 失败将引发回踩，故突破前不宜提前介入")
    elif major_stage == "派发":
        lines.append(f"⚠️ 风险：派发期注意破位，跌破 {stop:.2f} 需离场")
    elif major_stage == "衰退":
        lines.append(f"⚠️ 风险：趋势向下，不宜介入")
    else:
        lines.append(f"⚠️ 风险：等信号确认，{confirm:.2f} 未站稳前不宜提前介入")

    # ── [2.5] 量能真空区预警 ──
    volume_vacuum = r.get("volume_vacuum") or {}
    if volume_vacuum.get("vacuum_warning"):
        lines.append(f"⚠️ 量能真空：{volume_vacuum.get('warning_text', '')}")

    # ── [2.6] 资金面数据（Phase 1: 融资融券 / 北向资金 / 板块） ──
    _margin = r.get("extend_margin") or {}
    _north = r.get("extend_northbound") or {}
    _sector = r.get("extend_sector") or {}

    # 只要有任意一路数据有效就展示
    _concept = r.get("extend_concept") or {}
    if (_margin.get("status") == "正常" or _north.get("status") == "正常"
            or _sector.get("status") == "正常" or _concept.get("status") == "正常"):
        lines.append("")
        lines.append("📊 资金面")

        # 融资融券
        if _margin.get("status") == "正常":
            _mb = _margin.get("margin_balance_wan", 0)
            _mb_yi = _mb / 10000 if _mb else 0
            parts = [f"融资余额 {_mb_yi:.1f}亿"]
            _mbuy = _margin.get("margin_buy_wan", 0)
            if _mbuy:
                parts.append(f"买入 {_mbuy:.0f}万")
            lines.append(f"  {'｜'.join(parts)}")

        # 北向资金
        if _north.get("status") == "正常":
            _nn = _north.get("north_net_flow_wan", 0)
            _n5 = _north.get("north_flow_5d_wan", 0)
            # 单位自适应：超过 10000 万显示为亿
            if abs(_nn) >= 10000:
                nn_str = f"{_nn / 10000:+.1f}亿"
            else:
                nn_str = f"{_nn:+.0f}万"
            if abs(_n5) >= 10000:
                n5_str = f"{_n5 / 10000:+.1f}亿"
            else:
                n5_str = f"{_n5:+.0f}万"
            lines.append(f"  北向资金 今日净流入 {nn_str}｜近5日 {n5_str}")

        # 板块数据
        if _sector.get("status") == "正常" and _sector.get("sector_name"):
            _sn = _sector["sector_name"]
            _sc = _sector.get("sector_change_pct", 0)
            _sr = _sector.get("sector_rank", 0)
            _st = _sector.get("sector_total", 0)
            sector_line = f"  所属板块：{_sn}｜今日 {_sc:+.2f}%"
            if _sr > 0 and _st > 0:
                sector_line += f"｜排名 {_sr}/{_st}"
            lines.append(sector_line)

            # 个股 vs 板块相对强弱
            _stock_chg = float(r.get("change_pct", 0) or 0)
            _vs = _stock_chg - _sc
            if _vs > 0:
                lines.append(f"  个股 vs 板块：跑赢 +{_vs:.1f}%")
            elif _vs < 0:
                lines.append(f"  个股 vs 板块：跑弱 {_vs:.1f}%")

        # 概念板块数据（Phase 2）
        _concept = r.get("extend_concept") or {}
        if _concept.get("status") == "正常" and _concept.get("concept_list"):
            _c_list = _concept["concept_list"]
            _c_chg = _concept.get("concept_change_pct", [])
            _c_parts = []
            for i, cname in enumerate(_c_list[:3]):  # 最多展示 3 个概念
                _c_chg_val = _c_chg[i] if i < len(_c_chg) else 0
                _c_parts.append(f"{cname}{_c_chg_val:+.1f}%")
            concept_line = "  概念板块：" + " · ".join(_c_parts)
            lines.append(concept_line)

    lines.append("")

    pool_count = _pool_count()
    if pool_count > 0:
        lines.append(f"当前池 {pool_count}/10，回复 1 入池")
    else:
        lines.append("回复 1 入池")
    
    return "\n".join(lines)

def _pool_count() -> int:
    from pathlib import Path
    path = Path.home() / ".trader" / "pool.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        # Fix 4: 门槛从 >0.2 提高到 >0.4，避免低质量灰区信号误覆盖基础决策
        if fc > 0.4 and has_signal:
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
        "data_status": "degraded" if r.get("data_status") is None else DATA_STATUS_MAP.get(str(r.get("data_status")), "degraded"),
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
    # Fix 7: 用 major_stage（四阶段模型）而非 stage（短期3帧 determine_stage 轻量函数）
    # stage 只看 current/weekly/monthly 三个收盘价，major_stage 是 stage_positioning 综合结论
    major_stage = _get_major_stage(r)
    scene = str(r.get("scene") or "")
    theory_status = str(r.get("theory_status") or r.get("state_label") or scene)
    current = float(r.get("current") or 0)
    confirm = float(r.get("confirm") or current)

    # 最高优先级：衰退/暂不碰 → 一票否决
    if major_stage == "衰退" or theory_status == "暂不碰":
        return "defensive", "bearish_lean", "wait", "low"

    # 突破确认优先于冲高减仓（已站上确认位应跟踪而非减仓）
    if current >= confirm or scene in {"突破确认", "突破观察"} or theory_status in {"突破确认", "突破观察"}:
        return "track", "bullish", "track", "medium"

    # 体系确认类
    if theory_status == "体系转强确认":
        return "track", "bullish", "track", "medium"
    if theory_status == "未确认转强":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "承接存在":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "转强不足":
        return "wait_for_confirmation", "neutral", "observe", "low"

    # 冲高减仓（突破确认已优先处理，此处为未突破时的减仓信号）
    if scene == "冲高减仓" or theory_status == "冲高减仓":
        return "reduce", "bearish_lean", "reduce", "medium"

    # 风险回避类
    if theory_status in {"风险回避", "数据不足"}:
        return "defensive", "bearish_lean", "wait", "low"

    # 观察等待类（覆盖所有 scene 和 theory_status 变体）
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎", "空间不足", "等转强"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status in {"防守观察", "修复观察", "低吸观察", "等转强", "观望", "中性整理",
                         "低位修复", "均线修复", "防守整理", "临近确认", "空间偏紧"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    return "observe", "neutral", "observe", "low"


def signal_max_total_pct(signal_type: str) -> int:
    if signal_type in ("defensive", "risk_stop"):
        return 0
    if signal_type in ("trigger_expired", "blocked"):
        return 0
    if signal_type == "no_entry":
        return 0
    if signal_type == "track":
        return 30
    if signal_type == "reduce":
        return 20
    return 30


def signal_risk_flags(r: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    # 前置风险标志（ST/停牌/新股）优先
    pre_flags = r.get("risk_flags", []) or []
    flags.extend(pre_flags)
    # Fix A2: 用 major_stage（四阶段）而非旧 stage（三帧轻量函数），与 Fix 7 保持一致
    if _get_major_stage(r) == "衰退":
        flags.append("structure_weak")
    if str(r.get("scene") or "") == "空间不足":
        flags.append("limited_upside_space")
    if "不足" in str(r.get("volume_text") or ""):
        flags.append("volume_confirmation_missing")
    return flags


def state_text(stage: str, theory_status: str) -> str:
    # Fix A3: 不再用旧 stage=="转弱"，统一依赖 theory_status
    # 旧 stage 来自 determine_stage()（三帧轻量函数），不代表四阶段模型结论
    if theory_status == "暂不碰":
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


def one_sentence(r: dict[str, Any], low_zone: str) -> str:
    major_stage = _get_major_stage(r)
    momentum = str(r.get("short_term_momentum") or "")
    confirm = float(r.get("confirm") or 0)
    if major_stage == "衰退":
        return "衰退期，不参与。等站上250日线再说。"
    if major_stage == "蓄势" and momentum == "转弱":
        return "蓄势期转弱，不碰。"
    if major_stage == "蓄势" and momentum == "修复":
        return f"蓄势期，不动手。等放量站稳 {confirm:.2f} 再说。"
    if major_stage == "蓄势" and momentum in ("走强", "震荡"):
        return f"蓄势期，等突破 {confirm:.2f} 确认后再动手。"
    if major_stage == "主升" and momentum == "走强":
        return "主升期走强，持有。"
    if major_stage == "主升" and momentum == "修复":
        return f"主升期修复，回踩可加仓。站稳 {confirm:.2f} 确认。"
    if major_stage == "主升" and momentum == "震荡":
        return "主升期震荡，持有底仓，回踩确认。"
    if major_stage == "主升" and momentum == "转弱":
        return "主升期转弱，风险信号，考虑减仓。"
    if major_stage == "派发":
        return "派发期，逢高减仓。"
    # fallback to old theory_status（仅当 major_stage 为空时）
    stage = r.get("stage") or ""
    scene = r.get("scene") or ""
    theory_status = str(r.get("theory_status") or r.get("state_label") or "")
    current = float(r.get("current", 0))
    support = float(r.get("support", 0))
    if stage == "转弱" or theory_status == "暂不碰":
        return f"现在先不参与；等重新站回 {support:.2f}元 上方并稳定后再看。"
    if theory_status == "体系转强确认":
        return f"已形成体系确认，放量站稳回踩不破可评估加仓。"
    if scene == "冲高减仓":
        return f"上方空间受限，有底仓的逢高减仓，空仓需等回调。"
    if current >= confirm:
        return f"已越过确认位，放量站稳回踩不破可评估加仓。"
    return f"现在还不是进攻点；先守纪律等确认，跌到 {low_zone} 止跌才轻试，站不上 {confirm:.2f}元 不加仓。"


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
    theory_status_text = str(report.get("theory_status") or state_label or scene)
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

        # 防护：trigger_price 和 invalidation.price 必须 > 0
        if trigger_price <= 0:
            lines.append("  ⚠️ 信号跳过：当前价无效")
            return "\n".join(lines)
        if stop <= 0:
            stop = None  # invalidation 会跳过

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
            "data_status": "degraded" if report.get("data_status") is None else DATA_STATUS_MAP.get(str(report.get("data_status")), "degraded"),
            "trigger": {"type": "price_level", "price": round(trigger_price, 2), "text": f"{trigger_price:.2f}元 触发{sig_type}"},
            "invalidation": {"type": "price_break", "price": round(stop, 2), "text": f"跌破 {stop:.2f}元"} if stop else None,
            "position": {
                "max_total_pct": signal_max_total_pct(sig_type),
                "max_single_move_pct": min(10, signal_max_total_pct(sig_type)),
            },
            "risk_flags": signal_risk_flags(report),
            "summary": ("  ".join(alerts_found[:2])) if alerts_found else "无触发",
        }
        try:
            assert_valid_signal(signal)
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
    parser.add_argument("--cost", type=float, default=0.0, help="持仓成本价（用于显示持仓建议和盈亏分析）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target, cost_price=args.cost)
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

    # 预计算 Kelly 数据（同一进程内只读一次文件，供 render_markdown 使用）
    market_env_data = report.get("market_env") or {}
    _kelly = _get_kelly_data(market_env_data.get("level", "正常"))

    if args.output == "json":
        markdown = render_markdown(report, _kelly_cache_only=_kelly)
        print(json.dumps({"full_markdown": markdown, "report": report, "signal": build_signal(report)}, ensure_ascii=False, indent=2, default=str))
    elif args.output == "signal-json":
        print(json.dumps(build_signal(report), ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(report, _kelly_cache_only=_kelly))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
