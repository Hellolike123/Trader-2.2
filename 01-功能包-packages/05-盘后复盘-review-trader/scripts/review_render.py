from __future__ import annotations

import json
from typing import Any

from review_model import pct_text, price_text, volume_wan_hands


def signed_pct(value: float | None) -> str:
    return "--" if value is None else f"{value:+.2f}%"


def _atr_level_note(level: str, atr14: float) -> str:
    notes = {
        "波幅偏高": f"首仓建议≤5%，止损幅度约{atr14 * 2:.2f}元",
        "波动偏大": f"首仓5-7%，波幅偏大下不追突破",
        "波动正常": "首仓≤10%，正常操作",
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


def _format_intraday_narrative(intraday: dict[str, Any]) -> list[str]:
    """Build time-ordered narrative from intraday data."""
    lines = intraday.get("lines") or []
    if not lines:
        return ["分时数据不足，走势只按日线和收盘判断。"]
    result = []
    for line in lines:
        line = str(line).strip()
        if not line:
            continue
        # Check if line starts with time pattern like "09:30-10:00"
        if len(line) >= 5 and ":" in line[:6] and (line[5] in {"-", "："} or line[5].isdigit()):
            result.append(line)
        else:
            result.append(f"  {line}")
    if intraday.get("morning_ratio") is not None:
        mr = intraday["morning_ratio"] * 100
        followup = "跟进" if mr > 55 else "没跟上"
        result.append(f"全天  上午成交占{mr:.0f}%，量能{followup}")
    if intraday.get("data_state") == "partial_close":
        end = intraday.get("coverage_end_time") or "--"
        result.append(f"数据覆盖不足  5分钟数据截至{end}，尾盘判断降级")
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
    lines.append("结论 ")
    lines.append(conclusion)
    model_summary_text = str(review.get("model_summary_text") or model_summary(theory))
    lines.append(model_summary_text)
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
    lines.extend(_format_intraday_narrative(intraday))
    lines.append("")
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
        lines.append(f"ATR14日 {atr_data['atr14']:.2f}元（{atr_data['atr_ratio']*100:.2f}%）{atr_data['level']} - {_atr_level_note(atr_data['level'], atr_data['atr14'])}")
    else:
        lines.append("ATR数据不足（新股/停牌）")
    macd_params = review.get("macd_params") or {}
    if macd_params.get("macd_line") is not None:
        lines.append(f"MACD(D12/E26/S9): 线={macd_params['macd_line']:.4f} DEA={macd_params['dea']:.4f} 柱={macd_params['histogram']:+.4f}")
        if macd_params.get("golden_cross"):
            lines.append("MACD金叉信号：MACD线上穿DEA，短线偏多。")
        if macd_params.get("death_cross"):
            lines.append("MACD死叉信号：MACD线下穿DEA，短线偏空。")
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
        lines.append("💰 筹码分布（近60日量价粗算） ")
        for p in peaks:
            lines.append("  {:.2f}  {:.2f}%  {}".format(
                p["price"], p["share_of_total"], p["support_level"],
            ))
        lines.append("")
    # 📋 今日信号回溯 (no more monthly tracking — just backtrack)
    bt_lines = _signal_backtrack_lines(review)
    if bt_lines:
        lines.extend(bt_lines)
        lines.append("")
    return "\n".join(str(line) for line in lines)


def _signal_backtrack_lines(review: dict[str, Any]) -> list[str]:
    signals = review.get("historical_signals") or []
    if not signals:
        return []
    lines = ["📋 历史信号"]
    for sig in signals[:5]:
        date = sig.get("trade_date") or "?"
        sig_type = sig.get("signal_type") or "?"
        direction = sig.get("direction") or "?"
        action = sig.get("action") or "?"
        confidence = sig.get("confidence") or "?"
        source = sig.get("source_skill") or ""
        prefix = ""
        if source == "t0-trader":
            if sig_type in ("low_buy_triggered", "low_buy_watch"):
                prefix = "🟢 T0 "
            elif sig_type in ("high_sell_triggered", "high_sell_watch"):
                prefix = "🔴 T0 "
            elif sig_type == "risk_stop":
                prefix = "⚠️ T0 "
        if not prefix:
            if sig_type == "track":
                prefix = "👁 跟踪"
            elif sig_type == "reduce":
                prefix = "📉 减仓"
            elif sig_type == "risk_stop":
                prefix = "⚠️ 止损"
        lines.append(f"  {date}│{prefix}{sig_type}│{action}（{confidence}）")
    return lines if lines else ["暂无历史信号记录"]


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
