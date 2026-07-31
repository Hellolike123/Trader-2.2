"""选股池 rank 渲染辅助。"""
from __future__ import annotations

from typing import Any

from pool_cmds.verify import *  # noqa: F403

def edge_reason(item: dict[str, Any], all_items: list[dict[str, Any]]) -> str:
    """排名近因：分道 + 共振 + 买点有效/失效 + 威科夫链（fusion 不参与）。"""
    from pool_cmds.classify import ensure_lane
    from pool_cmds.wyckoff_rank import format_rs_plain, format_wyckoff_chain_plain
    from trader_shared.resonance import extract_resonance_grade, resonance_grade_label

    it = ensure_lane(item)
    parts: list[str] = []
    lane_zh = it.get("lane_zh")
    if lane_zh:
        parts.append(str(lane_zh))
    grade = extract_resonance_grade(it)
    if grade == "aligned":
        parts.append("共振齐")
    elif grade not in ("empty", ""):
        parts.append(f"共振{resonance_grade_label(grade)}")
    bp = it.get("buy_point_valid")
    if bp is True:
        parts.append("买点有效")
    elif bp is False:
        parts.append("买点失效")
    wyk_plain = format_wyckoff_chain_plain(it)
    if wyk_plain:
        parts.append(wyk_plain)
    rs_plain = format_rs_plain(it) or str(it.get("rs_plain") or "")
    if rs_plain:
        parts.append(rs_plain)
    reason = str(it.get("lane_reason") or "").strip()
    joined = "｜".join(parts)
    if reason and reason not in joined:
        parts.append(reason)
    return "｜".join(parts) if parts else ""


def render_rank(items: list[dict[str, Any]]) -> str:
    from trader_shared.candidate_core import atr_volatility_level
    from trader_shared.resonance import extract_resonance_grade, resonance_grade_label

    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    market_level = get_market_level()

    lines = [f"选股日报 — {today_text()}  ｜  {'大盘' + market_level + '，防守优先' if market_level else '持仓排序'}"]
    lines.append("")

    for i, item in enumerate(sorted_items):
        # 止损 > 现价时须先于 rank_status（其读取 _stop_broken）
        current_price_val = to_float(item.get("current")) or to_float(item.get("price")) or 0
        stop_val = to_float(item.get("stop")) or to_float(item.get("defense")) or 0
        if stop_val > 0 and current_price_val > 0 and stop_val > current_price_val:
            item = dict(item)  # shallow copy to avoid mutating original
            item["_stop_broken"] = True
            sorted_items[i] = item

        rs = rank_status(item)
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f" {i+1}."
        reason = edge_reason(item, sorted_items)
        reason_line = f"    {reason}" if reason else ""

        name = item.get("name", "?")
        current = to_float(item.get("current")) or 0
        atr_ratio = to_float(item.get("atr_ratio")) or 0
        atr_level, base_cap = atr_volatility_level(atr_ratio) if atr_ratio > 0 else ("数据不足", 10)
        # 按阶段 × ATR × 置信度差异化仓位
        major_stage = str(item.get("major_stage") or "蓄势")
        stage_mult = STAGE_STRENGTH.get(major_stage, 0.5)
        final_cap = round(base_cap * stage_mult)
        final_cap = max(2, min(final_cap, 25))  # 夹在 2%-25%
        # 仓位理由
        cap_reason_parts = []
        if major_stage in ("主升", "拉升"):
            cap_reason_parts.append("主升期")
        elif major_stage in ("蓄势偏强",):
            cap_reason_parts.append("蓄势偏强")
        elif major_stage in ("蓄势偏弱", "派发"):
            cap_reason_parts.append(major_stage)
        if atr_ratio >= 0.03:
            cap_reason_parts.append("波幅偏高")
        res_grade = extract_resonance_grade(item)
        if res_grade in ("conflict", "momentum_veto"):
            cap_reason_parts.append(resonance_grade_label(res_grade))
        cap_reason = " × ".join(cap_reason_parts) if cap_reason_parts else ""
        atr_pct = (atr_ratio or 0) * 100

        if atr_ratio >= 0.03:
            atr_text = f"波幅偏高({atr_pct:.0f}%)" if atr_pct >= 1 else "波幅偏高"
        elif atr_ratio >= 0.02:
            atr_text = f"波动偏大({atr_pct:.0f}%)"
        elif atr_ratio > 0:
            atr_text = f"波动正常({atr_pct:.0f}%)" if atr_pct >= 1 else "波动正常"
        else:
            atr_text = "数据不足"

        buy_low = to_float(item.get("buy_low")) or to_float(item.get("support")) or 0
        buy_high = to_float(item.get("buy_high")) or (buy_low * 1.01 if buy_low else 0)
        confirm = to_float(item.get("confirm")) or to_float(item.get("trigger")) or 0

        if buy_low and buy_high:
            buy_text = f"买(观察区)  {buy_low:.2f}-{buy_high:.2f} 止跌确认"
        elif buy_low:
            buy_text = f"买(观察区)  {buy_low:.2f} 止跌确认"
        else:
            buy_text = "买  暂无"

        # 买入区过期检查
        if buy_low > 0 and current_price_val > 0 and buy_low > current_price_val * 1.05:
            buy_text = f"买入区已过期（{buy_low:.2f}）"

        res_label = resonance_grade_label(extract_resonance_grade(item))
        lines.append(f"{medal}  {name}  {rs}  {current:.2f}  {atr_text}  {res_label}")
        if reason_line:
            lines.append(reason_line)
        cap_display = f"仓位 {final_cap}%"
        if cap_reason:
            cap_display += f"（{cap_reason}）"
        # R4: 盈亏比显示
        rr_val = to_float(item.get("risk_reward")) or 0
        if rr_val > 0 and ENABLE_RISK_REWARD_FILTER:
            market_env_level_s = get_market_level()
            rr_th = RISK_REWARD_THRESHOLDS.get(market_env_level_s, 1.5)
            rr_ok = rr_val >= rr_th
            rr_sym = "✓" if rr_ok else "✗"
            cap_display += f" 盈亏比 {rr_val}R {rr_sym}"
        lines.append(f"    {buy_text}  ｜  {cap_display}  ｜  止损 {stop_val:.2f}")
        # 价格过期 & 触发价偏离警告
        fw = _price_freshness_warning(item)
        if fw:
            lines.append(f"    {fw}")
        tw = _trigger_distance_warning(item)
        if tw:
            lines.append(f"    {tw}")
        lines.append("")

    first = sorted_items[0] if sorted_items else None
    second = sorted_items[1] if len(sorted_items) > 1 else None
    third = sorted_items[2] if len(sorted_items) > 2 else None

    lines.append("👉  ")

    if first:
        fname = first.get("name", "?")
        fs = rank_status(first)
        lines.append(f"    首选{fname}。{fs}信号最强，优先关注。")

    if second:
        sname = second.get("name", "?")
        ss = rank_status(second)
        lines.append(f"    {sname}{ss}差一档，做备选。")

    if third:
        tname = third.get("name", "?")
        lines.append(f"    {tname}再等等。")

    lines.extend([
        "",
        "    不抢跑，等止跌确认再动手。",
    ])

    if any(float(it.get("fusion_confidence") or 0) > 0 for it in sorted_items):
        lines.append("")
        lines.append("    fusion 分仅参考，不参与仓位与排序。")

    # 信号回测段
    verifications, summary = _pool_signal_verifications(sorted_items)
    if verifications:
        lines.append("")
        lines.append("📊 信号回测")
        lines.append("")
        lines.append(f"  {'名称':<8}{'信号':<12}  验证结果")
        lines.append(f"  {'-'*6:<8}{'-'*10:<12}  {'-'*10}")
        for v in verifications:
            lines.append(f"  {v['name']:<8}{v['sig_text']:<12}  {v['verify_status']}")

        total_verified = summary.get("已验证", 0)
        total_wrong = summary.get("信号错了", 0)
        total_unverified = summary.get("未验证", 0)
        total_none = summary.get("暂无信号", 0)
        total_with_signal = total_verified + total_wrong
        if total_with_signal > 0:
            accuracy_val = total_verified / total_with_signal
            accuracy = f"{accuracy_val * 100:.0f}%"
            lines.append("")
            lines.append(f"  合计：本月已验证 {total_with_signal} 次，对了 {total_verified} 次，准确率 {accuracy}。未验证 {total_unverified} 次，暂无信号 {total_none} 条。")
            # 低胜率警告
            if total_with_signal >= 5 and accuracy_val < 0.3:
                lines.append("  ⚠️ 策略近期胜率偏低（<30%），建议暂停实盘，仅保持观察")
        else:
            lines.append("")
            lines.append(f"  合计：本月无已验证信号记录（未验证 {total_unverified} 次，暂无信号 {total_none} 条）。")

    return "\n".join(lines)


def rank_action(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return f"等 {price_yuan(item.get('trigger'))} 放量站稳，不提前追。"
    if item.get("status") == "观察":
        return f"只观察 {price_yuan(item.get('trigger'))} 是否站稳，不主动买。"
    return "淘汰或风险不清，先不参与。"


def empty_reason(item: dict[str, Any] | None) -> str:
    if not item:
        return "池内没有适合空仓优先跟踪的候选。"
    return f"{item.get('name')} 排名靠前，但仍要等触发位确认。"


def holding_reason(item: dict[str, Any] | None) -> str:
    if not item:
        return "池内没有适合做T的候选，先不动底仓。"
    return f"{item.get('name')} 有明确触发和防守，具体盘中触发交给 t0。"


def rank_sentence(actionable: list[dict[str, Any]]) -> str:
    if not actionable:
        return "今天池内没有明确优先对象，先不主动参与。"
    first = actionable[0]
    return f"今天优先盯{first.get('name')}，只按触发位和防守位执行，不把观察区当操作价。"

__all__ = [
    "edge_reason",
    "empty_reason",
    "holding_reason",
    "rank_action",
    "rank_sentence",
    "render_rank",
]
