"""选股池 rank 渲染辅助。"""
from __future__ import annotations

from typing import Any

from pool_cmds.verify import *  # noqa: F403

def edge_reason(item: dict[str, Any], all_items: list[dict[str, Any]]) -> str:
    """返回排名的核心优势/劣势一句话。从 pool item 字段推导。"""
    confidences = [it.get("fusion_confidence", 0) or 0 for it in all_items]
    item_conf = float(item.get("fusion_confidence") or 0)
    top_conf = max(confidences) if confidences else 1

    # 优势：从得分最高的维度提取
    scores = {}
    for key, max_s in [("chanlun_score", 45), ("wyckoff_score", 30), ("chip_score", 25), ("momentum_score", 20)]:
        v = float(item.get(key) or 0)
        scores[key] = v
    best_dim = max(scores, key=scores.get)
    dim_labels = {"chanlun_score": "结构", "wyckoff_score": "量价", "chip_score": "筹码", "momentum_score": "动能"}
    ratio = scores[best_dim] / max(max(scores.values()), 0.01)
    if ratio >= 0.85:
        advantage = dim_labels.get(best_dim, best_dim) + "突出"
    else:
        advantage = ""

    # 置信度分位
    if top_conf > 0:
        conf_pct = item_conf / top_conf
    else:
        conf_pct = 1.0

    if conf_pct >= 0.9 and advantage:
        return f"置信最高｜{advantage}"
    elif conf_pct >= 0.7:
        return f"置信较高｜{advantage}" if advantage else "置信较高"
    elif conf_pct < 0.4:
        return "置信偏低"
    elif conf_pct < 0.6:
        return "置信中等"
    elif advantage:
        return advantage
    return ""


def render_rank(items: list[dict[str, Any]]) -> str:
    from trader_shared.candidate_core import atr_volatility_level
    from trader_shared.resonance import extract_resonance_grade, resonance_grade_label

    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    market_level = get_market_level()

    lines = [f"选股日报 — {today_text()}  ｜  {'大盘' + market_level + '，防守优先' if market_level else '持仓排序'}"]
    lines.append("")

    for i, item in enumerate(sorted_items):
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
        conf = float(item.get("fusion_confidence") or 0.5)
        final_cap = round(base_cap * stage_mult * conf)
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
        if conf < 0.4:
            cap_reason_parts.append(f"置信{conf:.1f}")
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
        stop_val = to_float(item.get("stop")) or to_float(item.get("defense")) or 0
        confirm = to_float(item.get("confirm")) or to_float(item.get("trigger")) or 0

        # 止损 > 现价时标记已破止损
        current_price_val = to_float(item.get("current")) or to_float(item.get("price")) or 0
        if stop_val > 0 and current_price_val > 0 and stop_val > current_price_val:
            item = dict(item)  # shallow copy to avoid mutating original
            item["_stop_broken"] = True

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
        lines.append(f"{medal}  {name}  {rs}  {current:.2f}  {atr_text}  共振{res_label}")
        if reason_line:
            lines.append(f"    {reason_line}")
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
