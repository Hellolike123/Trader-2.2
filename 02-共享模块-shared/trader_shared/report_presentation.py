# -*- coding: utf-8 -*-
"""Presentation layer: render_markdown + view/format helpers.
Domain orchestration lives in report_builder.py (build_report)."""

from __future__ import annotations

import sys

from pathlib import Path

from typing import Any

from datetime import date

import os

import json

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

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

def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"

def pct(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"

def numeric_values(bars: list[dict[str, Any]], key: str) -> list[float]:
    return [value for value in (to_float(item.get(key)) for item in bars) if value is not None]

def ma_text(value: Any) -> str:
    return "--" if value is None else f"{float(value):.2f}"

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

def render_markdown(r: dict, *, _kelly_cache_only: dict[str, float] | None = None) -> str:
    """渲染 Markdown 报告。

    生产唯一路径：委托 ``report_core.render_single``（短中线）。
    `_kelly_cache_only` 保留签名兼容，已不再使用。
    """
    from trader_shared.report_core import render_single

    return render_single(r)


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
            from trader_shared.signal_core import decision_persist_fields

            signal.update(decision_persist_fields(report))
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
