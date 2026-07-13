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
            f"  {format_wyckoff_oneline(_wyk_raw if isinstance(_wyk_raw, dict) else {}, direction=_w_dir, show_phase=True)}"
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

    pool_count = get_pool_count()
    if pool_count > 0:
        lines.append(f"当前池 {pool_count}/10，回复 1 入池")
    else:
        lines.append("回复 1 入池")
    
    return "\n".join(lines)

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
