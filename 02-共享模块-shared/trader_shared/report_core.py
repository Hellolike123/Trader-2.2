"""统一报告渲染模块

提供 3 个公共渲染函数，输出严格遵守微信端格式红线：
- 禁用 # 标题、--- 水平线、** 粗体、| 表格、> 块引用、* / - 列表符
- 首行必须以固定 emoji + 标题开头
- 分节用 emoji + 文本，不用 Markdown 语法
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def render_single(report: dict[str, Any]) -> str:
    """渲染单票分析报告。

    Args:
        report: build_report() 返回的 dict，需包含:
            - name, symbol, current, change_pct
            - ma (dict with ma5/ma10/ma20/ma30/ma250)
            - scene, state_label, fusion_action
            - support, stop, confirm, resistance
            - buy_points_text, sell_points_text (缠论买卖点)
            - highlight, risk (亮点/风险描述)
    """
    name = report.get("name", "")
    code = str(report.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    current = float(report.get("current") or 0)
    change_pct = float(report.get("change_pct") or 0)
    ma = report.get("ma") or {}
    scene = report.get("scene") or report.get("state_label") or ""
    fusion_action = report.get("fusion_action") or ""
    support = float(report.get("support") or 0)
    stop = float(report.get("stop") or 0)
    confirm = float(report.get("confirm") or 0)
    resistance = float(report.get("resistance") or 0)

    lines = [
        f"分析报告 — {name}（{code}）",
        "",
        f"现价 {current:.2f}（{change_pct:+.2f}%）",
    ]

    # 均线
    ma_parts = []
    for k in ("ma5", "ma10", "ma20", "ma30", "ma250"):
        v = ma.get(k)
        if v and isinstance(v, (int, float)) and v > 0:
            num = int(k[2:])
            ma_parts.append(f"MA{num}：{v:.2f}")
    if ma_parts:
        lines.append(f"  {' ｜ '.join(ma_parts)}")

    # 趋势与动作
    lines.append("")
    lines.append(f"🎯 {scene} → {fusion_action}")

    # 缠论信号
    buy_text = report.get("buy_points_text") or "无"
    sell_text = report.get("sell_points_text") or "无"
    if buy_text != "无" or sell_text != "无":
        lines.append(f"  缠论买点: {buy_text} ｜ 卖点: {sell_text}")

    # 决策区间
    lines.append("")
    lines.append("📍 决策")
    if support > 0:
        lines.append(f"  {support:.2f} ← 支撑位")
    if stop > 0:
        lines.append(f"  {stop:.2f} 止损（跌破支撑，趋势破坏）")
    lines.append(f"  🌟 {current:.2f} 当前位置")
    if confirm > 0:
        lines.append(f"  {confirm:.2f} → 确认位")
    if resistance > 0:
        lines.append(f"  {resistance:.2f} → 压力位")

    # 亮点与风险
    highlight = report.get("highlight")
    risk = report.get("risk")
    if highlight:
        lines.append("")
        lines.append(f"✅ 亮点：{highlight}")
    if risk:
        lines.append(f"⚠️ 风险：{risk}")

    return "\n".join(lines)


def render_pool_summary(pool_data: dict[str, Any]) -> str:
    """渲染选股池汇总/排序报告。

    Args:
        pool_data: 选股池数据 dict，需包含:
            - items: list[dict]，每项含 name, code, status, score, current
            - market_level: 大盘环境（可选）
            - updated_at: 更新时间（可选）
    """
    items = pool_data.get("items") or []
    market_level = pool_data.get("market_level") or "未知"
    updated = pool_data.get("updated_at") or datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"选股池 ｜ 大盘{market_level}",
        f"容量 {len(items)}/10 ｜ {updated}",
        "",
    ]

    if not items:
        lines.append("池子为空")
        return "\n".join(lines)

    # 按 score 降序
    sorted_items = sorted(items, key=lambda x: float(x.get("score") or 0), reverse=True)

    medals = ["🥇", "🥈", "🥉"]
    for i, item in enumerate(sorted_items):
        name = item.get("name", "")
        code = item.get("code", "")
        score = item.get("score", 0)
        status = item.get("status", "")
        current = item.get("current", 0)
        medal = medals[i] if i < 3 else f" {i + 1}."

        lines.append(f"{medal} {name}（{code}）｜ 评分：{score}")
        lines.append(f"    {status} 现价 {current}")

    return "\n".join(lines)


def render_backtest(results: list[dict[str, Any]] | dict[str, Any]) -> str:
    """渲染回测报告。支持单个 dict 或 list[dict] 输入。

    Args:
        results: 单个回测结果 dict 或多个结果的 list。每个 dict 需包含:
            - target: 股票代码
            - total_signals: 总信号数
            - by_type: dict，每个 key 是信号类型，value 含 count/win_rate/avg_return_pct
    """
    # 兼容单个 dict 输入
    if isinstance(results, dict):
        results = [results]

    if not results:
        return "回测无数据"

    lines = [
        "缠论买卖点回测",
        f"回测日期: {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    for r in results:
        target = r.get("target", "?")
        total = r.get("total_signals", 0)
        error = r.get("error")
        if error:
            lines.append(f"  {target}: {error}")
            continue

        by_type = r.get("by_type", {})
        if not by_type:
            lines.append(f"  {target}: 无信号")
            continue

        lines.append(f"{'─' * 30}")
        lines.append(f"  {target}  |  总信号: {total}")

        for stype in sorted(by_type.keys()):
            s = by_type[stype]
            wr = s.get("win_rate", 0)
            avg_r = s.get("avg_return_pct", 0)
            min_r = s.get("min_return_pct", 0)
            stop_r = s.get("stop_rate", 0)
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            lines.append(
                f"  {icon} {stype}: {s['count']}次  胜率{wr}%  "
                f"均收益{avg_r:+.1f}%  最差{min_r:+.1f}%  止损率{stop_r}%"
            )

    # 多票汇总
    if len(results) > 1:
        type_stats: dict[str, dict] = {}
        for r in results:
            for stype, s in r.get("by_type", {}).items():
                if stype not in type_stats:
                    type_stats[stype] = {"count": 0, "wins": 0, "returns": []}
                type_stats[stype]["count"] += s["count"]
                type_stats[stype]["wins"] += int(s["count"] * s["win_rate"] / 100)
                type_stats[stype]["returns"].append(s["avg_return_pct"])

        lines.append("")
        lines.append(f"{'─' * 30}")
        lines.append("  汇总")
        for stype in sorted(type_stats.keys()):
            ts = type_stats[stype]
            wr = round(ts["wins"] / ts["count"] * 100, 1) if ts["count"] > 0 else 0
            avg_r = round(sum(ts["returns"]) / len(ts["returns"]), 2) if ts["returns"] else 0
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            lines.append(f"  {icon} {stype}: {ts['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%")

    return "\n".join(lines)
