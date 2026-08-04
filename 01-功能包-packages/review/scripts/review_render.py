"""盘后复盘渲染（自 review/scripts/review_render 迁入）。"""
from __future__ import annotations

import json
from typing import Any

from trader_shared.review_core import pct_text, price_text, volume_wan_hands


def signed_pct(value: float | None) -> str:
    return "--" if value is None else f"{value:+.2f}%"


def _atr_level_note(level: str, atr14: float, atr14_2x: float) -> str:
    notes = {
        "波幅偏高": f"首仓不超过5%，止损设在你买入价下方约{atr14_2x:.2f}元",
        "波动偏大": "首仓5-7%，波动偏大时不追突破",
        "波动正常": "首仓不超过10%，正常操作",
        "波动较低": "首仓15-20%，可用上限仓位",
    }
    return notes.get(level, "按正常波动处理")


def model_summary(theory: dict[str, Any]) -> str:
    score = int(((theory.get("scores") or {}).get("total")) or 0)
    state = str(theory.get("state") or "")
    if state == "转强确认" or score >= 70:
        return "五层模型里，结构、量价和动能正在共振，但仍要看回踩确认。"
    if score >= 55:
        return "五层模型里，结构和量价有改善，筹码压力和中期趋势还没解除。"
    return "五层模型里，只有弱修复迹象，动能、筹码压力和中期趋势还没确认。"


def _short_verdict(text: str) -> str:
    """摘要短句：按标点切分取首分句；超长时在标点处截断，避免从词中间硬切（Bug M）。"""
    text = str(text).strip()
    if not text:
        return ""
    # 按标点切分（。，；：、）取有意义分句
    import re
    parts = [p.strip() for p in re.split(r"[。，；：、；,;:]", text) if p.strip()]
    if not parts:
        return text
    short = parts[0]
    if len(short) <= 12:
        return short
    for p in parts:
        if any(kw in p for kw in ("回调", "反弹", "修复", "调整", "震荡", "下跌", "上涨")):
            short = p
            break
    # 分句仍超长（无标点的长句）→ 保留前 24 字（中文语义基本完整），不再切词尾
    return short[:24]


def _atr_level_note_short(level: str, atr14: float) -> str:
    notes = {
        "波幅偏高": "首仓不超5%",
        "波动偏大": "首仓5-7%",
        "波动正常": "首仓不超10%",
        "波动较低": "首仓15-20%",
    }
    return notes.get(level, "")


def _load_historical_win_rate(symbol: str) -> dict | None:
    import json
    import os

    from trader_shared.trader_paths import path as trader_path

    signals_path = str(trader_path("signals"))
    if not os.path.exists(signals_path):
        return None
    normalized_symbol = symbol.replace(".SH", "").replace(".SZ", "").strip()
    try:
        from trader_shared.data_provider import get_provider
        provider = get_provider()
        sec = provider.resolve_security(normalized_symbol)
        daily = provider.fetch_qfq_daily(sec, days=300)
    except Exception:
        return None
    if not isinstance(daily, list):
        return None
    bar_dicts = [b for b in daily if isinstance(b, dict)]
    if not bar_dicts:
        return None
    sorted_bars = sorted(bar_dicts, key=lambda x: str(x.get("date", ""))[:10])
    dates = [str(b.get("date", ""))[:10] for b in sorted_bars if b.get("date")]
    close_map = {
        str(b.get("date", ""))[:10]: float(b["close"])
        for b in sorted_bars
        if b.get("date") and b.get("close")
    }
    buy_signals: list[float] = []
    sell_signals: list[float] = []
    try:
        with open(signals_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    sig = json.loads(line)
                except Exception:
                    continue
                sig_symbol = str(sig.get("symbol", "")).replace(".SH", "").replace(".SZ", "").strip()
                sig_name = str(sig.get("name", "")).strip()
                if normalized_symbol not in (sig_symbol, sig_name):
                    continue
                sig_type = str(sig.get("signal_type", ""))
                if sig_type not in ("review_result", "low_buy_triggered"):
                    continue
                analysis_time = str(sig.get("analysis_time") or "")
                time_part = analysis_time[11:].strip() if len(analysis_time) >= 16 else ""
                if not (time_part >= "15:00"):
                    continue
                trade_date = str(sig.get("trade_date") or analysis_time[:10])[:10]
                if trade_date not in close_map:
                    continue
                entry_price = close_map[trade_date]
                try:
                    idx = dates.index(trade_date)
                except ValueError:
                    continue
                # [P2 Fix] 硬编码 5 日持有期与信号实际持有周期不匹配
                # 改用信号记录中的持有期，fallback 到 3 日（更贴近 T0 实际持有周期）
                _holding = int(sig.get("holding_days") or 3)
                if idx + _holding >= len(dates):
                    continue
                exit_price = close_map[dates[idx + _holding]]
                return_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)
                direction = str(sig.get("direction", ""))
                if sig_type == "low_buy_triggered":
                    buy_signals.append(return_pct)
                elif direction in ("bullish", "bullish_lean"):
                    buy_signals.append(return_pct)
                elif direction in ("bearish", "bearish_lean"):
                    sell_signals.append(-return_pct)  # 取反：股价下跌=看空正确=正收益
    except Exception:
        return None
    total = len(buy_signals) + len(sell_signals)
    if total == 0:
        return None
    def _stats(signals: list[float]) -> dict | None:
        if not signals:
            return None
        wins = sum(1 for s in signals if s > 0)
        n = len(signals)
        win_rate = round((wins / n) * 100)
        avg = round(sum(signals) / n, 2)
        return {"count": n, "wins": wins, "win_rate": win_rate, "avg_pnl": avg}
    return {
        "total": total,
        "buy": _stats(buy_signals),
        "sell": _stats(sell_signals),
        "sample_warning": total < 5,
    }


def _format_intraday_narrative(intraday: dict[str, Any], big_order: dict[str, Any] | None = None) -> list[str]:
    """Build the intraday narrative without duplicating the same event twice."""
    result: list[str] = []
    lines = intraday.get("lines") or []

    if big_order and big_order.get("events"):
        result.append("大单回溯")
        for event in big_order["events"]:
            hands = event.get("hands")
            hands_text = f"{hands:.0f}手" if hands is not None else ""
            amount_wan = event.get("amount_wan")
            amount_text = f"{amount_wan:.0f}万" if amount_wan is not None else ""
            side = event.get("side", "")
            # 用自然语言替代术语
            if side == "主动买入":
                side_text = "买方扫货"
            elif side == "主动卖出":
                side_text = "卖方出货"
            else:
                side_text = "方向不明"
            # 盘口信号：用一句短语说明
            bs = event.get("book_signal")
            if bs == "盘口同向确认":
                trust = "盘口也同向，信号可信"
            elif bs == "盘口矛盾":
                trust = "但盘口挂单反向，信号打折"
            else:
                trust = ""
            # 拼接
            parts = [f"{event['time']}  {side_text} {amount_text}/{hands_text}"]
            if trust:
                parts.append(trust)
            result.append("，".join(parts))

        # 汇总：用一句话说清楚
        summary = big_order.get("summary", "")
        book_ctx = big_order.get("book_context")
        if book_ctx:
            result.append(f"结论：{book_ctx}")
        elif summary:
            # 精简 summary，去掉冗长的数字罗列
            result.append(f"结论：{summary}")
        validation = big_order.get("validation")
        if validation:
            verdict_icon = "✅" if validation["verdict"] == "有效" else "⚠️" if validation["verdict"] == "背离" else "ℹ️"
            result.append(f"走势验证：{verdict_icon} {validation['verdict']}。{validation['reason']}")
        result.append("")
    elif lines:
        for line in lines:
            line_str = str(line).strip()
            if not line_str:
                continue
            result.append(line_str)

    if not result:
        return ["分时数据不足，走势只按日线和收盘判断。"]

    if intraday.get("morning_ratio") is not None:
        mr = intraday["morning_ratio"] * 100
        followup = "跟进" if mr >= 55 else "没跟上"
        result.append(f"全天  上午成交占 {mr:.0f}%，量能 {followup}")
    if intraday.get("data_state") == "partial_close":
        end = intraday.get("coverage_end_time") or "--"
        result.append(f"数据覆盖不足  5分钟数据截至 {end}，尾盘判断降级")

    return result


def _build_levels_table(levels: dict[str, Any], is_midday: bool) -> list[str]:
    """Build the structured support/pressure list with action hints."""
    lines = []
    if is_midday:
        support_labels = {
            "今日收盘价": "午间现价",
            "今日低点": "上午低点",
            "今日高点，明日第一关": "上午高点，午后第一关",
        }
    else:
        support_labels = {}

    def apply_label(lbl):
        for old, new in support_labels.items():
            lbl = lbl.replace(old, new)
        return lbl

    support_lines = []
    action_hints_support = {
        "今日收盘价，守住偏强": "→ 震荡期观察线",
        "回撤第一防线": "→ 跌破减仓",
        "今日低点，跌破则止跌失败": "→ 跌破减仓",
        "前一交易日低点，双低点参考": "→ 双低点支撑",
    }
    for item in levels["support"][:3]:
        hint = ""
        for pattern, h in action_hints_support.items():
            if pattern in item["label"]:
                hint = h
                break
        support_lines.append(f"  {price_text(item['price'])}  {apply_label(item['label'])}{hint}")
    lines.extend(["下方支撑：", *support_lines])

    lines.append("上方压力：")
    pressure_lines = []
    action_hints_pressure = {
        "今日高点，明日第一关": "→ 冲高试压",
        "近20日成交密集压力": "→ 站上转强，可小仓位试错",
        "中期趋势压力参考": "→ 放量突破才确认转势",
    }
    for item in levels["pressure"][:3]:
        hint = ""
        for pattern, h in action_hints_pressure.items():
            if pattern in item["label"]:
                hint = h
                break
        pressure_lines.append(f"  {price_text(item['price'])}  {apply_label(item['label'])}{hint}")
    lines.extend(pressure_lines)
    return lines


def render_single(review: dict[str, Any]) -> str:
    q = review["quote"]
    levels = review["levels"]
    theory = review["theory"]
    stage = review.get("stage_result") or {}
    intraday = review["intraday"]
    is_midday = review.get("session") == "midday"
    close = q["close"]
    pressure = levels["key_pressure"]
    key_support = levels["key_support"]
    cost = review.get("cost")
    atr_data = review.get("atr") or {}
    name = review.get("name", "")
    code = str(review.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    change = q.get("change_pct")
    session_label = "午间复盘" if is_midday else "盘后复盘"

    major_stage = stage.get("major_stage", "")
    momentum = stage.get("momentum", "")
    stage_action = stage.get("action", "")
    stage_label = f"{major_stage} + {momentum} → {stage_action}" if major_stage else ""
    conclusion = str(review.get("conclusion_text") or "")
    if not conclusion:
        if is_midday:
            conclusion = "午间弱修复，午后还要看是否重新放量。" if theory["state"] == "弱修复观察" else "午间继续修复，但还没突破关键压力。" if theory["state"] != "转强确认" else "午间尝试转强，午后还要看站稳。"
        else:
            conclusion = "弱修复观察，还不能按反转处理。" if theory["state"] == "弱修复观察" else "短线止跌修复，但还不是反转。" if theory["state"] != "转强确认" else "正在尝试转强，仍要看回踩确认。"

    lines: list[str] = [
        f"{session_label} — {name}（{code}）",
        "",
        f"收盘：{price_text(close)}（{pct_text(change)}）",
        "",
    ]

    if stage_label:
        lines.append(f"📊 {stage_label}")
        lines.append("")

    lines.append(f"结论：{conclusion}")
    lines.append("")

    # 📊 关键价位
    lines.append("📊 关键价位")
    support_items = levels.get("support", [])
    pressure_items = levels.get("pressure", [])
    for item in support_items[:3]:
        lines.append(f"  {price_text(item['price'])}  ← {item['label']}")
    for item in pressure_items[:3]:
        lines.append(f"  {price_text(item['price'])}  ← {item['label']}")
    lines.append(f"站上 {price_text(pressure)} = 转强  跌破 {price_text(key_support)} = 修复失效")
    lines.append("")

    # 🔎 分时与大单
    lines.append("🔎 分时与大单")
    bo = review.get("big_order") or {}
    bo_events = bo.get("events") or []
    if bo_events:
        for event in bo_events[:4]:
            hands = event.get("hands")
            hands_text = f"{hands:.0f}手" if hands is not None else ""
            amount_wan = event.get("amount_wan")
            amount_text = f"{amount_wan:.0f}万" if amount_wan is not None else ""
            if hands_text:
                amount_text += f"/{hands_text}"
            meaning = event.get("meaning", "")
            side = event.get("side", "")
            lines.append(f"  {event['time']}  {side} {amount_text}（{meaning}）")
        lines.append(f"  回溯：{bo.get('summary', '')}")
    else:
        intraday_lines = intraday.get("lines") or []
        if intraday_lines:
            for line in intraday_lines[:3]:
                line_str = str(line).strip()
                if line_str:
                    lines.append(f"  {line_str}")
        else:
            lines.append("  分时数据不足")
    lines.append("")

    # 📈 五层打分
    scores = theory.get("scores", {})
    lines.append("📈 五层打分")
    lines.append(f"  结构 {scores.get('structure','--')}  量价 {scores.get('volume','--')}  筹码 {scores.get('chip','--')}  动能 {scores.get('momentum','--')}")
    chanlun = theory.get("chanlun", "")
    if chanlun:
        lines.append(f"  缠论  {_short_verdict(chanlun)}")
    wyckoff = theory.get("wyckoff", "")
    if wyckoff:
        lines.append(f"  威科夫  {_short_verdict(wyckoff)}")

    # MACD + RSI + ADX
    mr = theory.get("momentum_raw") or {}
    rsi_raw = mr.get("rsi") or {}
    adx_raw = mr.get("adx") or {}
    macd_params = review.get("macd_params") or {}
    macd_dir = "偏多" if macd_params.get("golden_cross") else "偏空" if macd_params.get("death_cross") else "中性"
    if macd_params.get("macd_line") is not None:
        mc = macd_params['macd_line']
        dea = macd_params['dea']
        hist = macd_params['histogram']
        if mc > dea:
            macd_dir = "偏多"
        elif mc < dea:
            macd_dir = "偏空"
        else:
            macd_dir = "中性"
        if abs(hist) < 0.01:
            macd_dir += "（不算强）"

    rsi_val = rsi_raw.get("last")
    rsi_label = ""
    if rsi_val is not None:
        if rsi_val < 30: rsi_label = "超卖"
        elif rsi_val > 70: rsi_label = "超买"
        elif rsi_val < 45: rsi_label = "偏弱"
        elif rsi_val > 55: rsi_label = "偏强"
        else: rsi_label = "中性"

    adx_val = adx_raw.get("value")
    adx_label = ""
    if adx_val is not None:
        adx_label = "趋势强" if adx_raw.get("strong_trend") else "无趋势"

    momentum_parts = [f"MACD {macd_dir}"]
    if rsi_val is not None:
        momentum_parts.append(f"RSI {rsi_val:.0f} {rsi_label}")
    if adx_val is not None:
        momentum_parts.append(f"ADX {adx_val:.0f} {adx_label}")
    if len(momentum_parts) > 1:
        lines.append(f"  {'  '.join(momentum_parts)}")

    if atr_data.get("available"):
        atr14 = atr_data['atr14']
        atr_ratio = atr_data['atr_ratio']
        note = _atr_level_note_short(atr_data['level'], atr14)
        lines.append(f"  ATR ±{atr14:.2f}（{atr_ratio*100:.1f}%）{note}")
    lines.append("")

    # 🎴 股性透视
    win_rate_data = _load_historical_win_rate(review.get("symbol", ""))
    if win_rate_data is not None:
        lines.append("🎴 股性透视")
        buy = win_rate_data.get("buy")
        sell = win_rate_data.get("sell")
        if buy:
            lines.append(f"  买入 {buy['count']}次 {buy['wins']}胜{buy['count']-buy['wins']}负 胜率{buy['win_rate']}% 平均{buy['avg_pnl']:+.2f}%")
        if sell:
            lines.append(f"  卖出 {sell['count']}次 {sell['wins']}胜{sell['count']-sell['wins']}负 胜率{sell['win_rate']}%")
        if win_rate_data.get("sample_warning"):
            lines.append("  ⚠️ 样本不足，仅供参考")
        lines.append("")

    # 💰 主力资金
    mf = review.get("main_force") or {}
    if mf and mf.get("stage") and mf["stage"] != "unknown":
        try:
            from trader_shared.main_force_output import format_flow_trend
            daily_5d = mf.get("daily_flow_5d", [])
            trend_str = format_flow_trend(daily_5d)
            cum_5 = mf.get("cum_flow_5d_wan", 0)
            con_in = mf.get("consecutive_inflow_days", 0)
            con_out = mf.get("consecutive_outflow_days", 0)
            relation = mf.get("flow_price_relation", "无数据")
            today_flow = daily_5d[-1] if daily_5d else 0

            lines.append("💰 主力资金")
            cum_line = f"  近5日 {cum_5:+.0f}万（{trend_str}）"
            if con_in >= 2:
                cum_line += f" 连续{con_in}日净流入"
            elif con_out >= 2:
                cum_line += f" 连续{con_out}日净流出"
            lines.append(cum_line)
            lines.append(f"  今日 {today_flow:+.0f}万  价资{relation}")
            lines.append("")
        except Exception:
            pass

    # 💰 筹码分布
    chip_dist = review.get("chip_distribution") or {}
    peaks = chip_dist.get("peaks", [])
    if peaks:
        lines.append("💰 筹码分布")
        max_share = max(p.get("share_of_total", 1.0) for p in peaks) if peaks else 1.0
        for p in peaks:
            price = p["price"]
            share = p["share_of_total"]
            level = p["support_level"]
            filled = max(1, min(6, round(share / max_share * 6))) if max_share > 0 else 1
            bar = "■" * filled + "□" * (6 - filled)
            emoji = "🟢" if "支撑" in level else "🔴"
            lines.append(f"  {price:.2f} [{bar}] {share:.1f}% {emoji}{level}")

        cm = review.get("chip_migration") or {}
        cm_text = cm.get("warning_text", "")
        if cm_text:
            lines.append(f"  {cm_text}")
        lines.append("")

    # 📍 明日
    lines.append("📍 明日")
    lines.append(f"  {price_text(pressure)} 站稳 → 加仓")
    lines.append(f"  {price_text(key_support)} 跌破 → 止损")

    return "\n".join(str(line) for line in lines)


def _signal_type_label(sig_type: str) -> str:
    labels = {
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
    return labels.get(sig_type, sig_type)


def _direction_label(direction: str) -> str:
    labels = {
        "bullish": "看多",
        "bearish": "看空",
        "neutral": "中性",
        "bullish_lean": "偏多",
        "bearish_lean": "偏空",
    }
    return labels.get(direction, direction)


def _confidence_label(confidence: str) -> str:
    labels = {
        "low": "低",
        "medium": "中等",
        "high": "高",
    }
    return labels.get(confidence, confidence)


def _signal_backtrack_lines(review: dict[str, Any]) -> list[str]:
    signals = review.get("historical_signals") or []
    if not signals:
        return ["📋 历史信号  暂无记录"]
    lines = ["📋 历史信号"]
    for sig in signals[:5]:
        date = sig.get("trade_date") or "?"
        sig_type = sig.get("signal_type") or "?"
        direction = sig.get("direction") or "?"
        source = sig.get("source_skill") or ""
        confidence = sig.get("confidence") or "?"

        # emoji prefix for t0 signals
        prefix = ""
        if source == "t0":
            if sig_type in ("low_buy_triggered", "low_buy_watch"):
                prefix = "🟢 T0低吸"
            elif sig_type in ("high_sell_triggered", "high_sell_watch"):
                prefix = "🔴 T0高抛"
            elif sig_type == "risk_stop":
                prefix = "⚠️ T0止损"

        if source == "review":
            prefix = "📋 复盘"

        if not prefix:
            label = _signal_type_label(sig_type)
            prefix = f"👁 {label}" if "观察" in label or "跟踪" in label else label

        conf_text = _confidence_label(confidence)
        dir_text = _direction_label(direction)
        lines.append(f"  {date}  {_signal_type_label(sig_type)} {dir_text}（{conf_text}）")
    return lines


def _build_signal_review_section(review: dict[str, Any]) -> list[str]:
    """构建 🔔 今日信号回顾 输出段落。

    检查今日触发的信号：
    - BC（购买高潮）
    - UTAD（上冲回落）
    - SOW（弱势信号）
    - 筹码搬家
    """
    lines: list[str] = []
    alerts: list[str] = []

    # 提取威科夫信号
    wyckoff = review.get("wyckoff") or {}
    if isinstance(wyckoff, dict):
        bc_signal = wyckoff.get("bc_signal", False)
        bc_reason = wyckoff.get("bc_reason", "")
        utad_signal = wyckoff.get("upthrust_signal", False)
        utad_reason = wyckoff.get("upthrust_reason", "")
        sow_signal = wyckoff.get("sow_signal", False)
        sow_reason = wyckoff.get("sow_reason", "")
        ar_signal = wyckoff.get("ar_signal", False)
        ar_reason = wyckoff.get("ar_reason", "")
        sos_signal = wyckoff.get("sos_signal", False)
        sos_reason = wyckoff.get("sos_reason", "")
        st_signal = wyckoff.get("st_signal", False)
        st_reason = wyckoff.get("st_reason", "")
        lps_signal = wyckoff.get("lps_signal", False)
        lps_reason = wyckoff.get("lps_reason", "")
        wyckoff_phase = wyckoff.get("phase_label", "")
    else:
        bc_signal = utad_signal = sow_signal = False
        ar_signal = sos_signal = st_signal = lps_signal = False
        bc_reason = utad_reason = sow_reason = ar_reason = sos_reason = st_reason = lps_reason = ""
        wyckoff_phase = ""

    # 提取筹码搬家数据
    chip_migration = review.get("chip_migration") or {}
    warning_level = chip_migration.get("warning_level", "none")
    warning_text = chip_migration.get("warning_text", "")

    # BC 信号
    if bc_signal:
        alerts.append(f"  🔴 购买高潮（BC）信号")
        alerts.append(f"    {bc_reason}")
        alerts.append(f"    建议：明天减仓 1/3")

    # UTAD 信号
    if utad_signal:
        alerts.append(f"  🔴 上冲回落（UTAD）信号")
        alerts.append(f"    {utad_reason}")
        alerts.append(f"    建议：明天立刻减仓")

    # SOW 信号
    if sow_signal:
        alerts.append(f"  ⚠️ 弱势信号（SOW）")
        alerts.append(f"    {sow_reason}")
        alerts.append(f"    建议：关注，准备减仓")

    # AR / SOS / ST / LPS（经典威科夫信号）
    if ar_signal:
        alerts.append(f"  🟢 自动反弹（AR）")
        alerts.append(f"    {ar_reason}")
    if sos_signal:
        alerts.append(f"  🟢 强势信号（SOS）")
        alerts.append(f"    {sos_reason}")
    if st_signal:
        alerts.append(f"  🟡 二次测试（ST）")
        alerts.append(f"    {st_reason}")
    if lps_signal:
        alerts.append(f"  🟢 最后支撑（LPS）")
        alerts.append(f"    {lps_reason}")

    # 阶段标签
    if wyckoff_phase and wyckoff_phase != "无明确阶段":
        alerts.append(f"  📊 威科夫阶段：{wyckoff_phase}")

    # 筹码搬家
    if warning_level == "critical":
        alerts.append(f"  🔴 筹码搬家清仓信号")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    建议：清仓")
    elif warning_level == "warning":
        alerts.append(f"  ⚠️ 筹码松动警告")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    建议：关注，随时准备减仓")

    if alerts:
        lines.append("🔔 今日信号回顾")
        lines.extend(alerts)
    else:
        lines.append("🔔 今日信号回顾")
        lines.append("  ✅ 未触发任何信号")

    return lines


def _build_tomorrow_action_section(review: dict[str, Any]) -> list[str]:
    """构建 🎯 明日行动 输出段落。

    基于当前阶段和关键价位，给出明天的操作建议。
    """
    q = review.get("quote") or {}
    levels = review.get("levels") or {}
    theory = review.get("theory") or {}

    close = float(q.get("close") or 0)
    pressure = levels.get("key_pressure") or 0
    key_support = levels.get("key_support") or 0
    # 提取阶段信息
    stage_result = review.get("stage_result") or {}
    major_stage = str(stage_result.get("major_stage") or "")
    momentum = str(stage_result.get("momentum") or "")
    stage_action = str(stage_result.get("action") or "")

    # 提取威科夫信号
    wyckoff = review.get("wyckoff") or {}
    bc_signal = isinstance(wyckoff, dict) and wyckoff.get("bc_signal", False)
    utad_signal = isinstance(wyckoff, dict) and wyckoff.get("upthrust_signal", False)
    sow_signal = isinstance(wyckoff, dict) and wyckoff.get("sow_signal", False)

    # 提取筹码搬家
    chip_migration = review.get("chip_migration") or {}
    warning_level = chip_migration.get("warning_level", "none")

    lines: list[str] = ["🎯 明日行动"]

    # 优先级判断
    if utad_signal or sow_signal or warning_level == "critical":
        lines.append("  动作：减仓或清仓")
        if utad_signal:
            lines.append(f"  理由：今日触发 UTAD 上冲回落信号")
        elif sow_signal:
            lines.append(f"  理由：今日触发 SOW 弱势信号")
        elif warning_level == "critical":
            lines.append(f"  理由：筹码搬家严重")
        if key_support > 0:
            lines.append(f"  如果反弹：逢高减仓")
            lines.append(f"  如果跌破 {key_support:.2f}：清仓")
    elif bc_signal or warning_level == "warning":
        lines.append("  动作：关注减仓机会")
        if bc_signal:
            lines.append(f"  理由：今日触发 BC 购买高潮信号")
        elif warning_level == "warning":
            lines.append(f"  理由：筹码松动警告")
        if pressure > 0:
            lines.append(f"  如果冲高到 {pressure:.2f}：减仓 1/3")
        if key_support > 0:
            lines.append(f"  如果跌破 {key_support:.2f}：止损")
    elif major_stage == "主升" and momentum == "走强":
        lines.append("  动作：持有")
        lines.append(f"  理由：主升期走强，让利润跑")
        if key_support > 0:
            lines.append(f"  如果跌破 {key_support:.2f}：减仓")
    elif major_stage == "衰退":
        lines.append("  动作：不碰")
        lines.append(f"  理由：衰退期，不参与")
    elif stage_action in ("逢高减磅", "逢反弹减仓"):
        lines.append(f"  动作：逢高减仓")
        lines.append(f"  理由：四阶段定位 {stage_action}")
        if pressure > 0:
            lines.append(f"  如果冲高到 {pressure:.2f}：减仓 1/3")
        if key_support > 0:
            lines.append(f"  如果跌破 {key_support:.2f}：止损")
    elif stage_action in ("清仓逃命", "跌破防线减仓", "空仓规避"):
        lines.append(f"  动作：减仓或清仓")
        lines.append(f"  理由：四阶段定位 {stage_action}")
        if key_support > 0:
            lines.append(f"  如果跌破 {key_support:.2f}：清仓")
    elif stage_action in ("回调低吸", "低吸试盘"):
        lines.append(f"  动作：低吸")
        lines.append(f"  理由：四阶段定位 {stage_action}")
        if key_support > 0:
            lines.append(f"  回踩 {key_support:.2f} 附近：试探买")
    elif stage_action in ("顺势加仓",):
        lines.append(f"  动作：加仓")
        lines.append(f"  理由：四阶段定位 {stage_action}")
        if pressure > 0:
            lines.append(f"  站稳 {pressure:.2f}：加仓")
    else:
        if pressure > 0:
            lines.append(f"  动作：关注 {pressure:.2f} 是否站稳")
            lines.append(f"  如果站稳：可以加仓")
            lines.append(f"  如果跌破 {key_support:.2f}：止损")
        else:
            lines.append(f"  动作：等待确认")
            lines.append(f"  理由：方向不明，等信号")

    return lines


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
