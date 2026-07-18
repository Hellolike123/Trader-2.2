"""旧版单票报告渲染。"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from trader_shared.report_renderer._helpers import _short_midline_enabled

def render_single_legacy(r: dict[str, Any]) -> str:
    """旧版单票分析报告（SHORT_MIDLINE_REPORT=false 时回退）。"""
    name = r.get("name", "")
    code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    current = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    ma_raw = r.get("ma") or r.get("ma_raw") or {}
    low_price = float(r.get("support") or 0)
    stop = float(r.get("stop") or 0)
    confirm = float(r.get("confirm") or 0)
    resistance = float(r.get("resistance") or 0)
    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)

    lines: list[str] = [
        f"分析报告 — {name}（{code}）",
        "",
        f"现价 {current:.2f}（{change_pct:+.2f}%）",
    ]

    # ── 均线 ──
    ma_parts = []
    for k in ("ma5", "ma10", "ma20", "ma30", "ma250"):
        v = ma_raw.get(k)
        if v and isinstance(v, (int, float)) and v > 0:
            ma_parts.append(f"MA{int(k[2:])}：{v:.2f}")
    if ma_parts:
        lines.append(f"  {' ｜ '.join(ma_parts)}")

    # ── 量能 + 距高低 ──
    volume_ratio_val = float(r.get("volume_ratio") or 0)
    turnover_val = float(r.get("turnover_rate") or 0)
    bars_for_range = r.get("daily_bars") or []
    vol_parts = []
    if volume_ratio_val > 0:
        vol_label = "放量" if volume_ratio_val >= 1.5 else ("缩量" if volume_ratio_val <= 0.7 else "平量")
        vol_parts.append(f"量比{volume_ratio_val:.1f}（{vol_label}）")
    if turnover_val > 0:
        vol_parts.append(f"换手{turnover_val:.1f}%")
    if len(bars_for_range) >= 20 and current > 0:
        highs = [float(b.get("high") or 0) for b in bars_for_range[-20:] if float(b.get("high") or 0) > 0]
        lows = [float(b.get("low") or 0) for b in bars_for_range[-20:] if float(b.get("low") or 0) > 0]
        if highs:
            d = (current - max(highs)) / max(highs) * 100
            vol_parts.append(f"距高{d:+.1f}%" if d < 0 else f"高{d:+.1f}%")
        if lows:
            d = (current - min(lows)) / min(lows) * 100
            vol_parts.append(f"距低{d:+.1f}%" if d > 0 else f"低{d:+.1f}%")
    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # ── 年线警告 ──
    ma250_val = ma_raw.get("ma250")
    if current > 0 and ma250_val and isinstance(ma250_val, (int, float)) and current < ma250_val:
        lines.append(f"  ⚠️ 股价在年线（{ma250_val:.2f}）下方运行，注意风险")

    lines.append("")

    # ── 融合层：阶段 → 动作 ──
    fusion = r.get("fusion") or {}
    fusion_action = str(fusion.get("action") or r.get("fusion_action") or "未知")
    major_stage = str(r.get("major_stage") or "")
    veto = fusion.get("fund_flow_outflow_veto_msg") or ""
    veto_part = f"（{veto}）" if veto else ""

    _action_word = fusion_action.split("（")[0].split("(")[0].strip() if "（" in fusion_action or "(" in fusion_action else fusion_action
    _real_status = str(r.get("base_status") or "")
    if _real_status in ("暂不碰", "风险回避", "空仓规避"):
        _action_word = _real_status

    if major_stage and major_stage != "None":
        lines.append(f"🎯 {major_stage} → {_action_word}{veto_part}")
    else:
        lines.append(f"🎯 {_action_word}{veto_part}")

    # ── 理论信号行 ──
    fusion_signals = fusion.get("signals_detail") or {}
    for _key, _label in (("chan", "缠论"), ("momentum", "动量")):
        if _key not in fusion_signals:
            continue
        _sig = fusion_signals[_key]
        if not isinstance(_sig, dict):
            continue
        _state = str(_sig.get("reason", "") or "").replace(_label, "").strip().lstrip(":").strip()
        _dir = _sig.get("direction", 0)
        _dir_label = "看涨" if _dir > 0 else ("看跌" if _dir < 0 else "中性")
        if not _state or _state == "无明确信号":
            _state = "无信号"
        lines.append(f"  {_label}:{_state}·{_dir_label}")

    if "wyckoff" in fusion_signals or r.get("wyckoff"):
        try:
            from trader_shared.wyckoff_core import format_wyckoff_oneline
            _w_sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
            _w_dir = _w_sig.get("direction") if _w_sig else None
            _wyk_raw = r.get("wyckoff")
            if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
                _wyk_raw = _wyk_raw.get("wyckoff")
            lines.append(f"  {format_wyckoff_oneline(_wyk_raw if isinstance(_wyk_raw, dict) else {}, direction=_w_dir, show_phase=True)}")
        except Exception:
            _sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
            _dir = _sig.get("direction", 0) if _sig else 0
            _dl = "偏多" if _dir > 0 else ("偏空" if _dir < 0 else "中性")
            lines.append(f"  威科夫：暂无事件 · {_dl}")

    disagreement = int(fusion.get("disagreement", 0))
    if disagreement > 0 and fusion_signals:
        _bull = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) > 0)
        _bear = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) < 0)
        lines.append(f"  {_bull}方看多 vs {_bear}方看空")

    bs = str(r.get("base_status") or "")
    ts = str(r.get("theory_status") or "")
    if bs and ts and bs != ts:
        lines.extend(["", f"  基础状态：{bs} ｜ 体系结论：{ts}"])
    elif bs:
        lines.extend(["", f"  {bs}"])

    _RESTRICTIVE = frozenset({"暂不碰", "风险回避", "空仓规避", "退场观察"})
    _pos_cap = int(r.get("position_cap") or 0)
    _lz_low = float(r.get("low_zone_lower") or 0)
    _lz_high = float(r.get("low_zone_upper") or 0)
    _take_val = float(r.get("take") or 0)

    lines.append("")
    lines.append("📍 决策")

    if not has_position and bs not in _RESTRICTIVE and _lz_low > 0 and _lz_high > 0:
        lines.append(f"  空仓：在 {_lz_low:.2f}-{_lz_high:.2f}元 试探买 {_pos_cap}%，止损 {stop:.2f}")
    elif has_position and _take_val > 0:
        lines.append(f"  有底仓：反弹 {_take_val:.2f} 冲不动减")

    all_price_lines: list[tuple[float, str]] = []
    if stop > 0:
        all_price_lines.append((stop, f"  {stop:.2f} 止损（跌破支撑，趋势破坏）"))
    if low_price > 0:
        all_price_lines.append((low_price, f"  {low_price:.2f} ← 试探买"))
    if current > 0:
        all_price_lines.append((current, f"  🌟 {current:.2f} 当前位置"))

    key_levels = r.get("key_levels") or {}
    if key_levels:
        _weighted_score = float(r.get("weighted_score") or 0)
        if _weighted_score >= 0.25:
            _lr_action = "持有关注 / 趋势强"
        elif _weighted_score >= 0.1:
            _lr_action = "减仓 20%"
        else:
            _lr_action = "减仓 50% / 趋势弱"

        for kl_key, label, pct in [
            ("long_support", "长线支撑", "加仓至 20%"),
            ("mid_support", "中线支撑", "首次建仓 10%"),
            ("short_support", "短线支撑", "试探买 5%"),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val < current:
                all_price_lines.append((val, f"  {val:.2f} ← {label}（{pct}）"))

        for kl_key, label, pct in [
            ("short_resist", "短线压力", "卖 20%"),
            ("mid_resist", "中线压力", "减仓 30%"),
            ("long_resist", "长线压力", _lr_action),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val > current:
                all_price_lines.append((val, f"  {val:.2f} → {label}（{pct}）"))

    all_price_lines.sort(key=lambda x: x[0])
    for val, line in all_price_lines:
        lines.append(line)

    if has_position and cost_price > 0:
        pnl_pct = (current - cost_price) / cost_price * 100
        pnl_text = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"
        fusion_reduce = fusion_action in ("减仓", "空仓/止损", "减1/3 (高位松动)")
        lines.extend(["", f"📌 如果你有持仓（成本 {cost_price:.2f}）"])
        if pnl_pct >= 0:
            if major_stage == "主升":
                lines.append(f"  现在：持有，让利润跑（{pnl_text}）" if not fusion_reduce else f"  现在：持有，但融合层提示{fusion_action}，注意风险（{pnl_text}）")
            elif major_stage == "派发":
                lines.append(f"  现在：减仓，锁定利润（{pnl_text}）")
            else:
                lines.append(f"  现在：融合层提示{fusion_action}，考虑减仓（{pnl_text}）" if fusion_reduce else f"  现在：部分止盈，留底仓等突破（{pnl_text}）")
        else:
            if major_stage == "衰退":
                lines.append(f"  现在：止损，认亏走人（{pnl_text}）")
            elif major_stage == "主升":
                lines.append(f"  现在：持有，主升期大概率会回来（{pnl_text}）")
            else:
                lines.append(f"  现在：持有，不加仓（{pnl_text}）")

    chip_peaks = r.get("chip_peaks") or []
    chip_migration = r.get("chip_migration") or {}
    if chip_peaks:
        sorted_peaks = sorted(chip_peaks, key=lambda x: x.get("price", 0))
        peak_strs = [f"{p.get('price', 0):.2f}" for p in sorted_peaks[:3] if p.get("price", 0) > 0]
        chip_parts = [f"筹码：{' · '.join(peak_strs)}"]
        current_pct = r.get("chip_current_pct")
        if current_pct is not None and current_pct > 50:
            chip_parts.append(f"获利{current_pct:.0f}%")
        warning_text = chip_migration.get("warning_text", "")
        if "搬家" in warning_text:
            chip_parts.append("搬家")
        lines.append(f"  {' ｜ '.join(chip_parts)}")

    win_rate_data = r.get("win_rate_data")
    if win_rate_data:
        lines.extend(["", "📊 股性与历史回测"])
        buy = win_rate_data.get("buy")
        if buy:
            avg_pnl = buy.get("avg_pnl")
            avg_pnl_str = f"{avg_pnl:+.1f}%" if isinstance(avg_pnl, (int, float)) else str(avg_pnl)
            lines.append(f"  买入信号 {buy['count']}次 ｜ {buy['wins']}胜{buy['count'] - buy['wins']}负 ｜ 胜率 {buy['win_rate']}% ｜ 平均 {avg_pnl_str}")

    _mid_support = float(key_levels.get("mid_support") or 0)
    _short_resist = float(key_levels.get("short_resist") or 0)
    if _mid_support > 0 and _mid_support < current:
        _dist_sup = (current - _mid_support) / current * 100
        lines.append(f"\n✅ 亮点：中线支撑 {_mid_support:.2f} 距当前价 {_dist_sup:.0f}%，下跌空间有限")
    elif current > low_price * 1.005:
        lines.append(f"\n✅ 亮点：{current:.2f} 仍站在防守位 {low_price:.2f} 上方")
    else:
        lines.append(f"\n⚠️ 亮点：暂无亮点，价格已跌破防守位 {low_price:.2f}")

    if _short_resist > 0 and _short_resist > current:
        _dist_res = (_short_resist - current) / current * 100
        lines.append(f"⚠️ 风险：短线压力 {_short_resist:.2f} 距当前价仅 {_dist_res:.0f}%，追高风险大")
    elif major_stage == "衰退":
        lines.append("⚠️ 风险：趋势向下，不宜介入")
    else:
        lines.append(f"⚠️ 风险：等信号确认，{confirm:.2f} 未站稳前不宜提前介入")

    pool_count = r.get("pool_count")
    pool_cap = r.get("pool_cap")
    if pool_count is not None and pool_cap is not None:
        lines.append(f"\n当前池 {pool_count}/{pool_cap}，回复 1 入池")

    return "\n".join(lines)


