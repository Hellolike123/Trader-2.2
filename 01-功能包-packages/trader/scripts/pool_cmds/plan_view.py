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
    # 「触发」对人话＝计划买点（站上才谈买）
    buy = price(item.get("trigger"))
    if item.get("status") == "执行":
        return f"放量站上计划买点 {buy} 才考虑"
    if item.get("status") == "观察":
        return f"只看计划买点 {buy} 是否站稳，不买"
    return "不参与，保留复盘记录"


def position_for(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
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


def _structure_weak_parts(item: dict[str, Any]) -> list[str]:
    """结构短板白话零件；无短板返回空。不过期/淘汰（另有专节）。"""
    from trader_shared.resonance import extract_resonance_grade

    parts: list[str] = []
    grade = extract_resonance_grade(item)
    if grade == "missing_structure":
        parts.append("还差缠论")
    elif grade == "missing_chip":
        parts.append("还差筹码")
    elif grade == "missing_background":
        parts.append("还差背景")
    elif grade == "momentum_veto":
        parts.append("动能唱反调")
    elif grade == "conflict":
        parts.append("结构与背景打架")
    elif grade not in ("aligned", "empty", ""):
        parts.append("共振未齐")

    chan = float(item.get("chanlun_score") or 0)
    # 共振已点名缠论时不再叠「缠偏弱」
    if chan < 25 and grade != "missing_structure":
        parts.append("缠偏弱")

    chip = float(item.get("chip_score") or 0)
    if chip < 15 and grade != "missing_chip":
        parts.append("筹偏弱")

    if item.get("status") == "执行":
        _, rr_weak = _rr_below_threshold(item)
        if rr_weak:
            parts.append("赔率偏弱")

    return parts


def _structure_weak_lines(items: list[dict[str, Any]]) -> list[str]:
    """仅列执行/观察且买点未过期、确有短板的票；无则空列表。"""
    lines: list[str] = []
    for item in items:
        if item.get("status") not in {"执行", "观察"}:
            continue
        if _is_trigger_stale(item):
            continue
        parts = _structure_weak_parts(item)
        if not parts:
            continue
        name = item.get("name") or "?"
        lines.append(f"  {name}  {' · '.join(parts)}")
    return lines


def render_plan(items: list[dict[str, Any]]) -> str:
    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    # 分离触发价过期的票（距现价 > 5%）
    active_plan_items = [it for it in sorted_items if not _is_trigger_stale(it)]
    stale_plan_items = [it for it in sorted_items if _is_trigger_stale(it)]
    count = counts(sorted_items)
    watchable_exec = [item for item in active_plan_items if item.get("status") == "执行"]
    execution_items = watchable_exec[:EXECUTION_LIMIT]
    top_items = execution_items + [
        item for item in active_plan_items if item.get("status") != "执行"
    ]

    lines = [
        f"选股池作战表 — {today_text()}",
        (
            f"池内 {len(sorted_items)}/{POOL_LIMIT}"
            f"｜明日可盯 {len(watchable_exec)}"
            f"｜观察 {count['观察']}"
            f"｜过期待刷 {len(stale_plan_items)}"
            f"｜淘汰 {count['淘汰']}"
        ),
        "",
    ]

    if top_items:
        lines.append("明日只盯")
        for i, item in enumerate(top_items[:3], 1):
            rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
            status = str(item.get("status") or "")
            res_plain = _plan_resonance_plain(item)
            lines.append(f"{rank_emoji} {item['name']} · {status} · {res_plain}")
            pos = position_for(item)
            lines.append(
                f"  现价{price(item.get('current'))}"
                f"｜计划买点{price(item.get('trigger'))}"
                f"｜防守{price(item.get('defense'))}"
                f"｜仓{pos}"
            )
            lines.append(f"  动作：{action_for(item)}")
            rr_val, rr_weak = _rr_below_threshold(item)
            if rr_weak:
                lines.append(f"  注意：盈亏比 {rr_val}R 偏弱 · 宁可不追")
            fw = _price_freshness_warning(item)
            if fw:
                lines.append(f"  {fw}")

        # 过期待刷：计划买点与现价差太远；只展差得最大的 3 只
        if stale_plan_items:
            n_stale = len(stale_plan_items)
            lines.append("")
            lines.append(f"过期待刷（{n_stale}只，计划买点与现价差太远）")
            ranked_stale = sorted(
                stale_plan_items,
                key=lambda it: abs(_trigger_dev_pct(it)),
                reverse=True,
            )
            for item in ranked_stale[:3]:
                lines.append(_stale_watch_line(item))
            if n_stale > 3:
                lines.append("  其余跑：final_pool.py refresh 重算买点")

        # 结构短板：只报拖后腿；过期→过期待刷，淘汰→池内警示，不在此重复
        weak_lines = _structure_weak_lines(sorted_items)
        if weak_lines:
            lines.append("")
            lines.append("结构短板")
            lines.extend(weak_lines)

        # 池内警示（待补/拒绝/淘汰一句原因）；无则省略
        warned = [
            item
            for item in sorted_items
            if item.get("admission_result") in {"待补", "拒绝"}
            or item.get("status") == "淘汰"
        ]
        if warned:
            lines.append("")
            lines.append("池内警示")
            for item in warned:
                reason = str(item.get("admission_reason") or item.get("status") or "").strip()
                lines.append(f"  {item.get('name')}：{reason or '需关注'}")

        lines.append("")
        lines.append("仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")
        lines.append(one_sentence(top_items))
    else:
        lines.append("当前选股池没有可盯对象，今天不主动处理。")
        if stale_plan_items:
            lines.append(f"过期待刷 {len(stale_plan_items)} 只，先跑 final_pool.py refresh")

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
    buy = price(item.get("trigger"))
    if item.get("_signal_triggered"):
        return f"信号已触发，按计划执行（防守{price(item.get('defense'))}元）"
    if item.get("_signal_downgrade"):
        return f"近期信号失败，暂不介入，等新信号"
    if item.get("status") == "执行":
        return f"放量站稳计划买点{buy}才买 → 回踩不破可加至3成"
    return f"计划买点{buy}站稳再看，防守{price(item.get('defense'))}元"


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
    "_plan_resonance_plain",
    "_structure_weak_lines",
    "_structure_weak_parts",
    "_refresh_pool_prices",
]
