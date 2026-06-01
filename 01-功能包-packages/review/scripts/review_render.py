from __future__ import annotations

import json
from typing import Any

from review_model import pct_text, price_text, volume_wan_hands


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


def _format_intraday_narrative(intraday: dict[str, Any], big_order: dict[str, Any] | None = None) -> list[str]:
    """Build the intraday narrative without duplicating the same event twice."""
    result: list[str] = []
    lines = intraday.get("lines") or []

    if big_order and big_order.get("events"):
        result.append("今日大单回溯")
        for event in big_order["events"]:
            hands = event.get("hands")
            hands_text = f"{hands:.0f} 手" if hands is not None else "手数不足"
            amount_wan = event.get("amount_wan")
            amount_text = f"{amount_wan:.0f} 万" if amount_wan is not None else "金额不足"
            focus_note = f"，贴近{event['focus_label']}" if event.get("near_focus") and event.get("focus_label") else ""
            result.append(f"{event['time']}  {event['side']}  {amount_text} / {hands_text}，{event['meaning']}{focus_note}。")
        result.append(f"回溯总结：{big_order.get('summary')}")
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
        followup = "跟进" if mr > 55 else "没跟上"
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
    intraday = review["intraday"]
    levels = review["levels"]
    theory = review["theory"]
    cost = review.get("cost")
    pnl = review.get("pnl_pct")
    pressure = levels["key_pressure"]
    first_support = levels["first_support"]
    key_support = levels["key_support"]
    close = q["close"]
    atr_data = review.get("atr") or {}
    is_midday = review.get("session") == "midday"
    review_label = "午间复盘" if is_midday else "盘后复盘"
    data_time = review.get("data_time")

    header_cost = f"成本 {cost:.2f}｜浮盈亏 {signed_pct(pnl)}" if cost else "未输入持仓成本｜按观察票复盘"
    conclusion = str(review.get("conclusion_text") or "")
    if not conclusion:
        if is_midday:
            conclusion = "午间弱修复，午后还要看是否重新放量。" if theory["state"] == "弱修复观察" else "午间继续修复，但还没突破关键压力。" if theory["state"] != "转强确认" else "午间尝试转强，午后还要看站稳。"
        else:
            conclusion = "弱修复观察，还不能按反转处理。" if theory["state"] == "弱修复观察" else "短线止跌修复，但还不是反转。" if theory["state"] != "转强确认" else "正在尝试转强，仍要看回踩确认。"

    lines: list[str] = [
        f"📌 {review['name']}｜{review['date']}{review_label}",
        f"收盘 {price_text(close)}（{pct_text(q.get('change_pct'))}）",
        header_cost,
    ]
    if data_time:
        lines.append(f"数据时间：{data_time}")
    if is_midday:
        lines.append("注意午间复盘以数据时间快照为准")
    lines.append("")
    model_summary_text = str(review.get("model_summary_text") or model_summary(theory))
    lines.append("结论 " + conclusion + model_summary_text)
    lines.append("")
    # 📊 关键价位 (consolidated: supports + pressures + risk)
    lines.append("📊 关键价位 ")
    lines.extend(_build_levels_table(levels, is_midday))
    lines.append("")
    lines.append(f"站上 {price_text(pressure)} = 转强    跌破{price_text(key_support)} = 修复失效")
    lines.append("")
    lines.append("⚠️ 最大风险 ")
    lines.append(f"放量跌破 {price_text(key_support)}")
    lines.append(f"含义：关键支撑失败，短线修复假设失效。")
    lines.append("")
    # 🔎 分时走势
    lines.append("🔎 分时走势 ")
    lines.extend(_format_intraday_narrative(intraday, review.get("big_order")))
    lines.append("")

    # 💰 主力资金复盘
    mf = review.get("main_force") or {}
    if mf and mf.get("stage") and mf["stage"] != "unknown":
        try:
            from trader_shared.main_force_output import (
                format_main_force_enhanced,
                format_flow_trend,
            )
            from trader_shared.main_force import STAGE_LABELS

            stage_cn = STAGE_LABELS.get(mf.get("stage", ""), "未知")
            confidence = mf.get("confidence", 0)
            daily_5d = mf.get("daily_flow_5d", [])
            trend_str = format_flow_trend(daily_5d)
            cum_5 = mf.get("cum_flow_5d_wan", 0)
            con_in = mf.get("consecutive_inflow_days", 0)
            con_out = mf.get("consecutive_outflow_days", 0)
            relation = mf.get("flow_price_relation", "无数据")
            today_super_large = float(mf.get("today_super_large_wan", 0) or 0)
            today_large = float(mf.get("today_large_wan", 0) or 0)
            today_flow = daily_5d[-1] if daily_5d else 0

            lines.append("💰 主力资金复盘")
            lines.append(f"阶段：{stage_cn}（置信度 {confidence:.1f}）")

            # 今日大单回溯
            bo = review.get("big_order") or {}
            bo_events = bo.get("events") or []
            if bo_events:
                lines.append("今日大单回溯：")
                for event in bo_events[:5]:
                    amt = event.get("amount_wan") or 0
                    order_type = "超大单" if amt >= 500 else "大单"
                    direction = "买入" if "买入" in str(event.get("side", "")) else "卖出"
                    sign = "+" if "买入" in str(event.get("side", "")) else "-"
                    meaning = str(event.get("meaning") or "")
                    lines.append(f"  {event.get('time')} {order_type}{direction} {sign}{amt:.0f}万（{meaning}）")
                lines.append(f"回溯总结：{bo.get('summary', '暂无')}")

            # 近5日累计 + 趋势
            cum_line = f"近5日累计：{cum_5:+.0f}万（{trend_str}）"
            if con_in >= 2:
                cum_line += f" 连续{con_in}日净流入"
            elif con_out >= 2:
                cum_line += f" 连续{con_out}日净流出"
            lines.append(cum_line)

            # 今日超大单/大单明细
            today_line = f"今日：{today_flow:+.0f}万"
            if today_super_large != 0 or today_large != 0:
                today_line += f"（超大单 {today_super_large:+.0f}万｜大单 {today_large:+.0f}万）"
            lines.append(today_line)

            lines.append(f"价资关系：{relation}")
            lines.append("")
        except Exception:
            pass

    # 📈 五层打分
    scores = theory.get("scores", {})
    lines.append("📈 五层打分 ")
    lines.append("结构{}/量价{}｜筹码{}｜动能{}".format(
        scores.get("structure", "--"), scores.get("volume", "--"),
        scores.get("chip", "--"), scores.get("momentum", "--"),
    ))
    lines.append(f"缠论：{theory.get('chanlun', '--')}")
    lines.append(f"威科夫：{theory.get('wyckoff', '--')}")
    lines.append(f"筹码：{theory.get('chip', '--')}")
    lines.append(f"资金行为：{theory.get('fund', '--')}")
    if atr_data.get("available"):
        atr14 = atr_data['atr14']
        atr_ratio = atr_data['atr_ratio']
        note = _atr_level_note(atr_data['level'], atr14, atr14 * 2)
        lines.append(f"💡 参考信息  日均波动约 ±{atr14:.2f}元（占总价{atr_ratio*100:.1f}%），{note}")
    else:
        lines.append("ATR数据不足（新股/停牌）")
    macd_params = review.get("macd_params") or {}
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
        strength = "不算强" if abs(hist) < 0.01 else ""
        cross_note = ""
        if macd_params.get("golden_cross"):
            cross_note = "（金叉状态）"
        elif macd_params.get("death_cross"):
            cross_note = "（死叉状态）"
        lines.append(f"MACD（判断大方向）：目前{macd_dir}{cross_note}{strength}。")
    lines.append("")
    # 🎯 信号判断
    lines.append("🎯 信号判断 ")
    lines.append("偏多：")
    for s in theory.get("supports", [])[:3]:
        lines.append(f"  ✓ {s}")
    lines.append("  警惕：")
    for b in theory.get("blocks", [])[:3]:
        lines.append(f"  ! {b}")
    lines.append("")
    # 👉 一句话
    one_liner = str(review.get("one_liner_text") or "")
    if not one_liner:
        if is_midday:
            one_liner = "午间有修复，还没过成本区。" if cost and close < cost else "午间方向不明，看午后确认。"
        elif cost and close < cost:
            one_liner = "现在不适合割肉，也不适合提前加仓。"
        else:
            one_liner = "现在不适合追高，先等关键位确认。"
    lines.append("👉 一句话 ")
    lines.append(one_liner)
    lines.append(f"明天只有放量站稳 {price_text(pressure)} 才算确认；否则继续按短线修复看。")
    lines.append(f"如果放量跌破 {price_text(key_support)}，这次修复判断失效。")
    lines.append("")
    # 💰 筹码分布
    chip_dist = review.get("chip_distribution") or {}
    peaks = chip_dist.get("peaks", [])
    if peaks:
        lines.append("💰 筹码分布 (高清时序衰减图)")
        max_share = max(p.get("share_of_total", 1.0) for p in peaks) if peaks else 1.0
        for p in peaks:
            price = p["price"]
            share = p["share_of_total"]
            level = p["support_level"]
            
            # WeChat-friendly 6-character full-width progress bar
            filled = max(1, min(6, round(share / max_share * 6))) if max_share > 0 else 1
            bar = "■" * filled + "□" * (6 - filled)
            
            # Emoji prefix based on support vs resistance
            emoji = "🟢" if "支撑" in level else "🔴"
            
            lines.append(f"  {price:.2f}元 [{bar}] {share:.1f}% {emoji}{level}")
        lines.append("")
    # 🔔 今日信号回顾
    signal_review_lines = _build_signal_review_section(review)
    if signal_review_lines:
        lines.extend(signal_review_lines)
        lines.append("")

    # 🎯 明日行动
    tomorrow_action_lines = _build_tomorrow_action_section(review)
    if tomorrow_action_lines:
        lines.extend(tomorrow_action_lines)
        lines.append("")

    # 📋 今日信号回溯 (no more monthly tracking — just backtrack)
    bt_lines = _signal_backtrack_lines(review)
    if bt_lines:
        lines.extend(bt_lines)
        lines.append("")

    # 📍 止盈进度（如有）
    exit_plan = review.get("exit_plan") or {}
    exit_items = exit_plan.get("exit_plan") or []
    if exit_items and exit_plan.get("risk_r", 0) > 0:
        lines.append("📍 止盈进度")
        already_exited = exit_plan.get("already_exited") or [False, False, False]
        for idx, item in enumerate(exit_items):
            p = item.get("price")
            reason = item.get("reason", "")
            exited = already_exited[idx] if idx < len(already_exited) else False
            if exited:
                lines.append(f"  ✅ 第{idx+1}笔 已执行")
            elif p is not None:
                dist = abs(close - p) / p * 100 if p > 0 else 0
                status = "已触发" if close >= p else f"未触发（当前 {close:.2f}，距 {dist:.1f}%）"
                lines.append(f"  {'✅' if close >= p else '⏳'} 第{idx+1}笔 {p:.2f} {status}")
            else:
                lines.append(f"  ⏳ 第{idx+1}笔 {reason} 未触发")
        lines.append("")

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
    else:
        bc_signal = utad_signal = sow_signal = False
        bc_reason = utad_reason = sow_reason = ""

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
    first_support = levels.get("first_support") or 0

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
