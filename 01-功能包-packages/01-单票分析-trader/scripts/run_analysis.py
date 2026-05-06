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

ROOT = Path(__file__).resolve().parents[3]
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
for _path in (SHARED_CANDIDATE, SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.append(str(_path))

import candidate_core as core
from candidate_core import build_structure_context, atr_volatility_level

try:
    from review_core import calc_chip_distribution as _calc_chip
except ImportError:
    def _calc_chip(daily, lookback=60):
        return {"peaks": [], "chip_at_price": None}
from config import (
    LOOKBACK_DAYS,
    STRUCTURE_WINDOW,
)
from trader_shared.data_provider import get_provider
from trader_shared.strategy_protocol import run_all
from light_data import to_float, pct_change

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

CONTRACTS = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "03-输出校验-contracts"
if CONTRACTS.exists() and str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from signal_contract import assert_valid_signal
from datetime import date

def today_text() -> str:
    return date.today().isoformat()


CONTRACT_VERSION = "trader_single_action_v3"


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def pct(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"


def build_report(target: str) -> dict[str, Any]:
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
    current = quote.get("current_price") or bars[-1]["close"]
    if current is None:
        raise RuntimeError("current price unavailable")
    current = float(current)

    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    from chan_core import chanlun_strategy
    from wyckoff_core import wyckoff_strategy
    from momentum_core import momentum_strategy
    strategies = [build_structure_context, chanlun_strategy, wyckoff_strategy, momentum_strategy]
    levels = run_all(current, bars, quote.get("current_change_pct"), quote, *strategies)
    chan_result = levels.get("chanlun", {})
    wyck_result = levels.get("wyckoff", {})
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
    support = levels["main_support"]
    resistance = levels["resistance"]
    confirm = levels["confirm_price"]
    stop = levels["hard_stop"]
    take = levels["take"]
    weekly_close = float(bars[-1]["close"])
    monthly_close = float(bars[-STRUCTURE_WINDOW]["close"] if len(bars) >= STRUCTURE_WINDOW else bars[0]["close"])
    stage = determine_stage(current, weekly_close, monthly_close)
    scene = levels["status"]
    replay = structure_replay(recent20)
    volume_text = volume_observation(recent20, bars_5m)
    upward_momentum = upward_momentum_observation(stage, current, support, confirm)
    highs = numeric_values(recent20, "high")
    lows = numeric_values(recent20, "low")
    high = max(highs) if highs else current
    low = min(lows) if lows else current
    analysis_time = f"{quote.get('trade_date')} {quote.get('trade_time') or ''}".strip()

    state_label = state_text(stage, scene)
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

    return {
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
        "take": take,
        "stage": stage,
        "scene": scene,
        "low_zone": levels["low_zone"],
        "low_zone_lower": levels["low_zone_lower"],
        "low_zone_upper": levels["low_zone_upper"],
        "support_source": levels.get("support_source"),
        "resistance_source": levels.get("resistance_source"),
        "avg_amplitude_pct": levels.get("avg_amplitude_pct"),
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
        "state_label": state_label,
        "structure_note": structure_note,
        "volume_note": volume_note,
        "market_env": market_env_data,
        "position_cap": position_cap,
    }


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


def _render_block_header(trader: str, code: str, name: str) -> str:
    return f"#{' '}{trader}#{' '} {name}（{code}）"


def render_markdown(r: dict[str, Any]) -> str:
    ma = r.get("ma") or {}
    low_zone = str(r.get("low_zone") or f"{r['support']:.2f}-{r['support'] * 1.01:.2f}元")
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

    atr_header = f"｜ATR {atr14:.2f}（{atr_ratio*100:.0f}%）{atr_level}" if atr14 > 0 else ""
    gap = r.get("gap") or {}
    gap_text = gap.get("text", "") if isinstance(gap, dict) else ""
    gap_condition = gap.get("condition", "normal") if isinstance(gap, dict) else "normal"
    lines: list[str] = [
        f"分析报告 — {name}（{display_code}）",
        "",
        f"现价：{price(r['current'])}（{pct(r['change_pct'])}）",
        f"MA5：{ma.get('ma5', '--')}|MA10：{ma.get('ma10', '--')}|MA20：{ma.get('ma20', '--')}|MA30：{ma.get('ma30', '--')}{atr_header}",
    ]
    if gap_text and gap_condition not in ("normal", "unknown"):
        lines.append(f"提示：{gap_text}")
        lines.append("")

    market_env = r.get("market_env") or {}
    env_level = market_env.get("level", "")
    skill_note = market_env.get("skill_note", "")
    trend_5d = market_env.get("trend_5d", "")
    change_pct = market_env.get("change_pct", 0.0)
    has_env = env_level and env_level not in ("未知", "")

    status_text = str(r.get("state_label") or "")

    if has_env:
        trend_str = "五条线上方" if trend_5d == "up" else "五条线下方"
        price_dir = "涨" if change_pct >= 0 else "跌"
        change_abs = abs(change_pct)
        lines.extend([
            "",
            "🌍 中证1000",
            "",
            f"趋势：{trend_str}｜今日{price_dir}{change_abs:.1f}% | 建议：{skill_note}",
        ])
    else:
        lines.extend([
            "",
            "🌍 中证1000",
            "",
            "趋势：数据不足｜今日--｜建议：市场环境数据暂不可用（回退到个股结构判断）",
        ])

    lines.extend([
        "",
        "📍 决策",
        "",
        f"状态：{status_text}",
        f"  · 空仓 → 在 {low_zone} 止跌才试，{position_cap}% 仓位上限",
        f"  · 有底仓 → 反弹 {confirm:.2f} 冲不动就减 10-20%",
        f"  · 加仓 → 放量站稳 {confirm:.2f} 且回踩不破，才评估",
    ])

    lines.extend([
        "",
        "T0 参考",
        "",
        f"  · 低吸：{low_price:.2f}（{low_zone} 支撑区承接，止跌确认）",
        f"  · 高抛：{confirm:.2f}（均线压力附近，最多 {position_cap}% 仓位）",
        f"  · 止损：跌破 {low_price:.2f} T0 失效，跌破 {stop:.2f} 退出全部",
    ])

    lines.extend([
        "",
        "❗ 关键价位",
        "",
        f"止损：{stop:.2f}元｜减仓：{confirm:.2f}元｜止跌：{low_zone}｜支撑：{low_price:.2f}元",
    ])

    lines.extend([
        "",
        "🧭 简要分析",
        "",
        f"  结构：{r.get('structure_note') or ''}",
        f"  量价：{r.get('volume_note') or ''} ｜ 筹码：{confirm:.2f} 压力 ｜ 动能：不进攻",
    ])

    pool_count = _pool_count()
    pool_line = f"当前池 {pool_count}/10，回复 1 入池" if pool_count > 0 else "回复 1 入池"
    lines.append(f"\n{pool_line}")

    return "\n".join(lines)


def _pool_count() -> int:
    import json
    import os
    path = os.path.expanduser("~/.trader/pool.json")
    try:
        data = json.loads(open(path).read())
        items = data.get("items", [])
        return sum(1 for i in items if i.get("status") not in {"淘汰", "已退出"})
    except Exception:
        return 0


def build_signal(r: dict[str, Any]) -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state(r)
    trade_date = str(r.get("analysis_time") or "").split(" ")[0] or "--"
    trigger_price = float(r.get("confirm") or r.get("resistance") or r.get("current"))
    invalid_price = float(r.get("stop") or r.get("support") or r.get("current"))
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": str(r.get("symbol") or ""),
        "name": str(r.get("name") or ""),
        "trade_date": trade_date,
        "analysis_time": str(r.get("analysis_time") or trade_date),
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": confidence,
        "data_status": str(r.get("data_status") or "degraded"),
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
    assert_valid_signal(signal)
    return signal


def signal_state(r: dict[str, Any]) -> tuple[str, str, str, str]:
    stage = str(r.get("stage") or "")
    scene = str(r.get("scene") or "")
    current = float(r.get("current") or 0)
    confirm = float(r.get("confirm") or current)
    if stage == "转弱":
        return "defensive", "bearish_lean", "wait", "low"
    if scene == "冲高减仓":
        return "reduce", "neutral", "reduce", "medium"
    if current >= confirm or scene in {"突破确认", "等转强"}:
        return "track", "bullish", "track", "medium"
    if scene in {"低吸观察", "防守观察", "空间不足"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    return "observe", "neutral", "observe", "low"


def signal_max_total_pct(signal_type: str) -> int:
    if signal_type == "track":
        return 30
    if signal_type == "reduce":
        return 20
    if signal_type == "defensive":
        return 0
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


def state_text(stage: str, scene: str) -> str:
    if stage == "转弱":
        return "暂不碰"
    if scene in {"低吸观察", "防守观察"}:
        return "修复观察，未确认转强"
    if scene == "空间不足":
        return "空间不足，先观察"
    if scene in {"突破确认", "突破观察", "等转强", "冲高减仓"}:
        return "转强确认中"
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
    if r["current"] >= r["confirm"]:
        return "转强确认中，等回踩验证"
    if r["stage"] == "转弱":
        return "结构偏弱，先退出观察"
    ma = r.get("ma") or {}
    ma_values = [float(value) for value in ma.values() if value != "--"]
    below_count = sum(1 for value in ma_values if r["current"] < value)
    if below_count >= 3:
        return "弱修复，还没确认转强"
    if r.get("scene") == "空间不足":
        return "上方空间太近，先观察"
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
    if r["stage"] == "转弱":
        return f"现在先不参与；等重新站回 {r['support']:.2f}元 上方并稳定后再看。"
    if r.get("scene") == "空间不足":
        return f"现在上方空间不够舒服；先不追，等回到 {low_zone} 止跌，或放量越过 {r['confirm']:.2f}元 后再评估。"
    return f"现在还不是进攻点；先守纪律等确认，跌到 {low_zone} 止跌才轻试，站不上 {r['confirm']:.2f}元 不加仓。"


def generate_alert(report: dict[str, Any]) -> str | None:
    current = float(report["current"])
    support = float(report.get("support") or 0)
    low_zone = str(report.get("low_zone") or "")
    stop = float(report.get("stop") or 0)
    confirm = float(report.get("confirm") or 0)
    resistance = float(report.get("resistance") or 0)
    scene = str(report.get("scene") or "")
    name = str(report["name"])
    atr14 = float(report.get("atr14", 0) or 0)
    thresh = max(atr14 * 0.4, current * 0.008) if atr14 > 0 else current * 0.01

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

    if confirm > 0 and abs(current - confirm) <= thresh and scene not in {"冲高减仓", "突破确认", "突破观察"}:
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
        action = f"当前{state_label}，{action_text_for_scene(scene)}"
        state_summary = state_label

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
            sig_type, direction, action_sig, confidence = "risk_stop", "bearish", "stop", "high"
        elif is_at_support:
            sig_type, direction, action_sig, confidence = "low_buy_triggered", "bullish_lean", "low_buy", "medium"
        elif is_near_confirm:
            sig_type, direction, action_sig, confidence = "low_buy_triggered", "bullish", "track", "medium"
        elif is_near_resistance:
            sig_type, direction, action_sig, confidence = "reduce", "neutral", "reduce", "medium"
        else:
            sig_type, direction, action_sig, confidence = "observe", "neutral", "observe", "low"

        from signal_store import append_signal
        trade_date = analysis_time.split(" ")[0] if analysis_time else today_text()
        signal = {
            "contract": "trader_signal_v1",
            "source_skill": "trader",
            "symbol": symbol,
            "name": name,
            "trade_date": trade_date,
            "analysis_time": analysis_time,
            "signal_type": sig_type,
            "direction": direction,
            "action": action_sig,
            "confidence": confidence,
            "data_status": str(report.get("data_status") or "full"),
            "trigger": {"type": "price_level", "price": round(current, 2), "text": alerts_found[0]},
            "invalidation": {"type": "price_break", "price": round(stop, 2), "text": f"跌破 {stop:.2f}元"},
            "position": {
                "max_total_pct": signal_max_total_pct(sig_type),
                "max_single_move_pct": min(10, signal_max_total_pct(sig_type)),
            },
            "risk_flags": signal_risk_flags(report),
            "summary": alerts_found[0],
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
    if scene in {"防守观察"}:
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
        from candidate_core import STATUS_SCORE
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
