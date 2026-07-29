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
    labels = ["第一优先", "第二优先", "第三优先"]
    lines = ["明日优先级", ""]
    for label, item in zip(labels, items[:3]):
        lines.extend(
            [
                f"{label}：{item.get('name')}",
                f"状态：{item.get('status')}",
                f"结构：{item.get('structure_summary')}",
                f"动能：{item.get('momentum_state')}",
                f"动作：{action_for(item)}",
                f"失效：收盘跌破 {price(item.get('defense'))} 转淘汰",
                f"仓位：{position_for(item)}",
                "",
            ]
        )
    return lines


def action_for(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return f"放量站上 {price(item.get('trigger'))} 才考虑"
    if item.get("status") == "观察":
        return f"只看 {price(item.get('trigger'))} 是否站稳，不买"
    return "不参与，保留复盘记录"


def position_for(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return "1成试错，确认后最多3成"
    return "0"


def render_plan(items: list[dict[str, Any]]) -> str:
    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    # 分离触发价过期的票（距现价 > 5%）
    active_plan_items = [it for it in sorted_items if not _is_trigger_stale(it)]
    stale_plan_items = [it for it in sorted_items if _is_trigger_stale(it)]
    count = counts(sorted_items)
    execution_items = [item for item in active_plan_items if item.get("status") == "执行"][:EXECUTION_LIMIT]
    top_items = execution_items + [item for item in active_plan_items if item.get("status") != "执行"]

    lines = [
        f"选股池盘后分析 — {today_text()}",
        f"容量 {len(sorted_items)}/{POOL_LIMIT}｜执行{count['执行']}｜观察{count['观察']}｜淘汰{count['淘汰']}｜明日只盯Top2",
        "",
    ]

    if top_items:
        lines.append("明日优先级")
        for i, item in enumerate(top_items[:3], 1):
            rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
            stage_str = str(item.get("stage_status") or item.get("major_stage", "蓄势") + "+" + item.get("momentum", "震荡"))
            lines.append(f"{rank_emoji} {item['name']}（{stage_str} {item['status']}）")
            lines.append(f"  {action_for(item)}")
            # R4: 计划页显示盈亏比
            rr_val = to_float(item.get("risk_reward")) or 0
            if rr_val > 0 and ENABLE_RISK_REWARD_FILTER:
                market_env_level_s = get_market_level()
                rr_th = RISK_REWARD_THRESHOLDS.get(market_env_level_s, 1.5)
                rr_ok = rr_val >= rr_th
                rr_sym = "✓" if rr_ok else "✗"
                plan_rr_text = f"  盈亏比 {rr_val}R {rr_sym}"
            else:
                plan_rr_text = ""
            lines.append(f"  触发{price(item.get('trigger'))}元  防守{price(item.get('defense'))}元  仓位{position_for(item)}{plan_rr_text}")
            fw = _price_freshness_warning(item)
            if fw:
                lines.append(f"  {fw}")

        # 远期观察（触发价过期 > 5%）
        if stale_plan_items:
            lines.append("")
            lines.append("远期观察（触发价偏离现价 > 5%，等刷新后再看）")
            for item in stale_plan_items:
                tw = _trigger_distance_warning(item)
                note = f" — {tw}" if tw else ""
                lines.append(f"  {item.get('name')}  触发{price(item.get('trigger'))}元  现价{price(item.get('current'))}元{note}")

        lines.append("")
        lines.append("评分总览")
        for item in sorted_items:
            _rr = to_float(item.get("risk_reward")) or 0
            _rr_suffix = ""
            if _rr > 0 and ENABLE_RISK_REWARD_FILTER:
                _rr_s = get_market_level()
                _rr_th = RISK_REWARD_THRESHOLDS.get(_rr_s, 1.5)
                _rr_sym = "✓" if _rr >= _rr_th else "✗"
                _rr_suffix = f" 盈亏比 {_rr}R {_rr_sym}"
            lines.append(
                f"  {item.get('name')}  {score_summary(item)}  {item['status']}{_rr_suffix}"
            )

        lines.append("")
        lines.append("交易指导")
        for item in top_items[:3]:
            lines.append(f"  {item['name']}: {trade_hint(item)}")

        lines.append("")
        lines.append("待补与拒绝")
        rejected = [item for item in sorted_items if item.get("admission_result") in {"待补", "拒绝"} or item.get("status") == "淘汰"]
        if rejected:
            for item in rejected:
                lines.append(f"  {item.get('name')}：{item['admission_reason']}")
        else:
            lines.append("  无")

        lines.append("")
        lines.append("仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")
        lines.append(one_sentence(top_items))
    else:
        lines.append("当前选股池没有可执行对象，今天不主动处理。")

    return "\n".join(lines)


def score_summary(item: dict[str, Any]) -> str:
    """返回压缩后的评分摘要，如：45/45 35/30 40/25 85/20 总88"""
    parts = []
    for key, max_s in [("chanlun_score", 45), ("wyckoff_score", 30), ("chip_score", 25), ("momentum_score", 20)]:
        v = float(item.get(key) or 0)
        parts.append(f"{v:.0f}/{max_s}")
    total = float(item.get("total_score") or 0)
    return "  ".join(parts) + f"  总{total:.0f}"


def trade_hint(item: dict[str, Any]) -> str:
    if item.get("_signal_triggered"):
        return f"信号已触发，按计划执行（防守{price(item.get('defense'))}元）"
    if item.get("_signal_downgrade"):
        return f"近期信号失败，暂不介入，等新信号"
    if item.get("status") == "执行":
        return f"放量站稳{price(item['trigger'])}元才买 → 回踩不破可加至3成"
    return f"{price(item['trigger'])}元站稳再看，防守{price(item.get('defense'))}元"


def one_sentence(items: list[dict[str, Any]]) -> str:
    top = [str(item.get("name")) for item in items[:2]]
    if not top:
        return "当前选股池没有可执行对象，明天不主动处理。"
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
    "_refresh_pool_prices",
]
