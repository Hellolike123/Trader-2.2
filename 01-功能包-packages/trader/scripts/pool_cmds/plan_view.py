"""选股池 plan / refresh 渲染辅助。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pool_cmds.verify import *  # noqa: F403

def _match_item(items: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    """按 target/name/symbol 任一字段匹配池内项（与 cmd_add 的匹配口径一致）。"""
    for item in items:
        if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}:
            return item
    return None


def priority_block(items: list[dict[str, Any]]) -> list[str]:
    """兼容旧调用：节名改为明日只盯。"""
    labels = ["第一优先", "第二优先", "第三优先"]
    lines = ["明日只盯", ""]
    for label, item in zip(labels, items[:3]):
        lines.extend(
            [
                f"{label}：{item.get('name')}",
                f"状态：{item.get('status')}",
                f"结构：{item.get('structure_summary')}",
                f"动能：{item.get('momentum_state')}",
                f"动作：{action_for(item)}",
                f"破位看：收盘跌破 {price(item.get('defense'))} 转淘汰",
                f"仓位：{position_for(item)}",
                "",
            ]
        )
    return lines


def action_for(item: dict[str, Any]) -> str:
    from pool_cmds.classify import ensure_lane

    it = ensure_lane(item)
    buy = price(it.get("trigger"))
    lane = str(it.get("lane") or "")
    if lane == "ready":
        return f"放量站上计划买点 {buy} 才考虑"
    if lane == "wait":
        return f"只看计划买点 {buy} 是否站稳，条件未齐不买"
    if lane == "stale":
        return "计划过时，先 refresh 重算再看"
    return "先别碰，保留复盘记录"


def position_for(item: dict[str, Any]) -> str:
    from pool_cmds.classify import ensure_lane

    if ensure_lane(item).get("lane") == "ready":
        return "1→3成"
    return "0"


def _trigger_dev_pct(item: dict[str, Any]) -> float:
    """计划买点相对现价：正=买点还在上方，负=现价已涨过买点；无效返回 0。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return 0.0
    return (trigger - current) / current * 100


def _stale_watch_line(item: dict[str, Any]) -> str:
    """过期待刷一行白话：现价｜计划买点｜涨过了/还差多远。"""
    name = item.get("name") or "?"
    cur = price(item.get("current"))
    buy = price(item.get("trigger"))
    pct = _trigger_dev_pct(item)
    if pct <= -5:
        # 现价已明显高于计划买点 → 旧买点失效，要重算
        return f"  {name}  现价{cur}｜计划买点{buy}｜已涨过约{abs(pct):.0f}% · 需重算"
    if pct >= 5:
        # 计划买点还在上方很远 → 短期够不着，也需刷新计划
        return f"  {name}  现价{cur}｜计划买点{buy}｜买点还高约{pct:.0f}% · 需重算"
    return f"  {name}  现价{cur}｜计划买点{buy}"


def _plan_resonance_plain(item: dict[str, Any]) -> str:
    """池计划页共振白话：禁止「共振缠论未点亮」硬拼。"""
    from trader_shared.resonance import extract_resonance_grade

    grade = extract_resonance_grade(item)
    if grade == "aligned":
        return "共振齐"
    if grade == "missing_structure":
        return "共振未齐（还差缠论）"
    if grade == "missing_chip":
        return "共振未齐（还差筹码）"
    if grade == "missing_background":
        return "共振未齐（还差背景）"
    if grade == "momentum_veto":
        return "动能唱反调"
    if grade == "conflict":
        return "结构与背景打架"
    return "共振条件不足"


def _rr_below_threshold(item: dict[str, Any]) -> tuple[float, bool]:
    """返回 (rr_val, below)。rr<=0 或未开过滤 → below=False。"""
    rr_val = to_float(item.get("risk_reward")) or 0.0
    if rr_val <= 0 or not ENABLE_RISK_REWARD_FILTER:
        return rr_val, False
    th = RISK_REWARD_THRESHOLDS.get(get_market_level(), 1.5)
    return rr_val, rr_val < th


def _status_sort_key(item: dict[str, Any]) -> int:
    st = str(item.get("status") or "")
    return {"执行": 0, "观察": 1, "淘汰": 2}.get(st, 9)


def _lane_fold_lines(items: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    """折叠短列表：名 · 近因。"""
    lines: list[str] = []
    for item in items[:limit]:
        name = item.get("name") or "?"
        reason = str(item.get("lane_reason") or _plan_resonance_plain(item) or "").strip()
        if reason:
            lines.append(f"  {name}  {reason}")
        else:
            lines.append(f"  {name}")
    if len(items) > limit:
        lines.append(f"  其余 {len(items) - limit} 只略")
    return lines


def _bp_plain(item: dict[str, Any]) -> str:
    v = item.get("buy_point_valid")
    if v is True:
        return "买点有效"
    if v is False:
        return "买点失效"
    return ""


def render_plan(items: list[dict[str, Any]]) -> str:
    from pool_cmds.classify import ensure_lane

    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    ready = [it for it in sorted_items if it.get("lane") == "ready"]
    wait = [it for it in sorted_items if it.get("lane") == "wait"]
    avoid = [it for it in sorted_items if it.get("lane") == "avoid"]
    stale = [it for it in sorted_items if it.get("lane") == "stale"]
    # 无 lane 的旧票：按计划过时拆分
    for it in sorted_items:
        if it.get("lane") in {"ready", "wait", "avoid", "stale"}:
            continue
        it2 = ensure_lane(it)
        if it2.get("lane") == "stale":
            stale.append(it2)
        elif it2.get("lane") == "ready":
            ready.append(it2)
        elif it2.get("lane") == "avoid":
            avoid.append(it2)
        else:
            wait.append(it2)

    top_ready = ready[:EXECUTION_LIMIT]

    lines = [
        f"选股池作战表 — {today_text()}",
        (
            f"池内 {len(sorted_items)}/{POOL_LIMIT}"
            f"｜可盯 {len(ready)}"
            f"｜等齐 {len(wait)}"
            f"｜先别碰 {len(avoid)}"
            f"｜计划过时 {len(stale)}"
        ),
        "",
    ]

    if top_ready:
        from pool_cmds.wyckoff_rank import format_wyckoff_chain_plain

        lines.append("明日只盯")
        for i, item in enumerate(top_ready, 1):
            rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
            res_plain = _plan_resonance_plain(item)
            bp = _bp_plain(item)
            wyk_plain = format_wyckoff_chain_plain(item)
            tags = " · ".join(
                x for x in (res_plain, bp, wyk_plain, str(item.get("lane_reason") or "")) if x
            )
            # 避免近因与共振完全重复
            if item.get("lane_reason") and res_plain and res_plain in str(item.get("lane_reason")):
                tags = " · ".join(
                    x for x in (str(item.get("lane_reason")), bp, wyk_plain) if x
                )
            lines.append(f"{rank_emoji} {item['name']} · 可盯 · {tags}" if tags else f"{rank_emoji} {item['name']} · 可盯")
            lines.append(
                f"  现价{price(item.get('current'))}"
                f"｜计划买点{price(item.get('trigger'))}"
                f"｜防守{price(item.get('defense'))}"
                f"｜仓{position_for(item)}"
            )
            lines.append(f"  动作：{action_for(item)}")
            rr_val, rr_weak = _rr_below_threshold(item)
            if rr_weak:
                lines.append(f"  注意：盈亏比 {rr_val}R 偏弱 · 宁可不追")
            fw = _price_freshness_warning(item)
            if fw:
                lines.append(f"  {fw}")
    else:
        lines.append("明日只盯")
        lines.append("  暂无可盯，先看等齐或跑 refresh")

    if wait:
        lines.append("")
        lines.append(f"等齐（{len(wait)}只）")
        lines.extend(_lane_fold_lines(wait))

    if avoid:
        lines.append("")
        lines.append(f"先别碰（{len(avoid)}只）")
        lines.extend(_lane_fold_lines(avoid))

    if stale:
        lines.append("")
        lines.append(f"计划过时（{len(stale)}只，计划买点与现价差太远）")
        ranked_stale = sorted(stale, key=lambda it: abs(_trigger_dev_pct(it)), reverse=True)
        for item in ranked_stale[:3]:
            lines.append(_stale_watch_line(item))
        if len(stale) > 3:
            lines.append("  其余跑：final_pool.py refresh 重算买点")

    # 评分参考：诊断附录，不决定盯谁
    lines.append("")
    lines.append("评分参考（缠/威/筹/动 · 不决定盯谁）")
    for item in sorted(
        sorted_items,
        key=lambda it: (
            {"ready": 0, "wait": 1, "avoid": 2, "stale": 3}.get(str(it.get("lane")), 9),
            -float(it.get("total_score") or 0),
        ),
    ):
        lane_zh = item.get("lane_zh") or item.get("lane") or item.get("status") or "?"
        lines.append(f"  {item.get('name')}  {score_summary(item)}  {lane_zh}")

    warned = [
        item
        for item in sorted_items
        if item.get("admission_diag") in {"待补", "拒绝"}
        or item.get("status") == "淘汰"
        or item.get("lane") == "avoid"
    ]
    if warned:
        lines.append("")
        lines.append("池内警示")
        for item in warned[:6]:
            reason = str(
                item.get("lane_reason") or item.get("admission_reason") or item.get("status") or ""
            ).strip()
            lines.append(f"  {item.get('name')}：{reason or '需关注'}")

    lines.append("")
    lines.append("仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")
    lines.append(one_sentence(top_ready))

    return "\n".join(lines)


def score_summary(item: dict[str, Any]) -> str:
    """人话评分：总82  缠33 威14 筹25 动10"""
    chan = float(item.get("chanlun_score") or 0)
    wyk = float(item.get("wyckoff_score") or 0)
    chip = float(item.get("chip_score") or 0)
    mom = float(item.get("momentum_score") or 0)
    total = float(item.get("total_score") or 0)
    return f"总{total:.0f}  缠{chan:.0f} 威{wyk:.0f} 筹{chip:.0f} 动{mom:.0f}"


def trade_hint(item: dict[str, Any]) -> str:
    """保留给其它调用方；plan 页已不再单独输出交易指导段。"""
    from pool_cmds.classify import ensure_lane

    buy = price(item.get("trigger"))
    if item.get("_signal_triggered"):
        return f"信号已触发，按计划执行（防守{price(item.get('defense'))}元）"
    if item.get("_signal_downgrade"):
        return f"近期信号失败，暂不介入，等新信号"
    if ensure_lane(item).get("lane") == "ready":
        return f"放量站稳计划买点{buy}才买 → 回踩不破可加至3成"
    return f"计划买点{buy}站稳再看，防守{price(item.get('defense'))}元"


def one_sentence(items: list[dict[str, Any]]) -> str:
    top = [str(item.get("name")) for item in items[:2]]
    if not top:
        return "当前选股池没有可盯对象，明天不主动处理。"
    return f"明天只重点盯 {' 和 '.join(top)}；不触发不买，其他只盘后更新。"


def _refresh_pool_prices(items: list[dict[str, Any]], pool: dict[str, Any]) -> list[dict[str, Any]]:
    """批量拉取实时行情，刷新 pool item 的 current / change_pct，写回 pool.json。

    在 list / rank / plan 等只读视图中调用，确保显示的现价不超过 1 分钟。
    """
    try:
        from trader_shared.light_data import fetch_quote, HttpClient, resolve_security
    except ImportError:
        return items

    client = HttpClient()
    now_iso = datetime.now().isoformat()
    refreshed = 0

    for item in items:
        name = item.get("name", "")
        if not name:
            continue
        try:
            sec = resolve_security(name)
            q = fetch_quote(sec, client)
        except Exception:
            continue
        if not q:
            continue
        current_val = to_float(q.get("current_price"))
        if current_val is None or current_val <= 0:
            continue
        item["current"] = round(current_val, 2)
        item["change_pct"] = round(to_float(q.get("current_change_pct") or 0), 2)
        item["price_fetched_at"] = now_iso
        refreshed += 1

    if refreshed > 0:
        save_pool(pool)
    return items


def _check_stale_items(items: list[dict[str, Any]]) -> list[str]:
    """P0 Fix: 检查交易时间内数据过期的票，标记为疑似停牌。

    Returns:
        list of warning strings for stale items
    """
    try:
        from trader_shared.light_data import is_trading_time
        if not is_trading_time():
            return []
    except ImportError:
        return []

    warnings = []
    for item in items:
        freshness = str(item.get("data_freshness", "live"))
        if freshness == "stale":
            name = item.get("name") or item.get("target", "?")
            warnings.append(f"⚠️ {name} 数据过期（data_freshness=stale），疑似停牌")
    return warnings

__all__ = [
    "action_for",
    "one_sentence",
    "position_for",
    "priority_block",
    "render_plan",
    "score_summary",
    "trade_hint",
    "_check_stale_items",
    "_match_item",
    "_plan_resonance_plain",
    "_lane_fold_lines",
    "_refresh_pool_prices",
]
