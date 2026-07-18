"""回测结果渲染。"""
from __future__ import annotations

from typing import Any

def render_backtest(results: list[dict[str, Any]] | dict[str, Any]) -> str:
    """渲染回测报告。支持单个 dict 或 list[dict] 输入。"""
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
            lines.append(f"  {icon} {stype}: {s['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%  最差{min_r:+.1f}%  止损率{stop_r}%")

    if len(results) > 1:
        type_stats: dict[str, dict] = {}
        for r in results:
            for stype, s in r.get("by_type", {}).items():
                if stype not in type_stats:
                    type_stats[stype] = {"count": 0, "wins": 0, "returns": []}
                type_stats[stype]["count"] += s["count"]
                type_stats[stype]["wins"] += int(s["count"] * s["win_rate"] / 100)
                type_stats[stype]["returns"].append(s["avg_return_pct"])
        lines.extend(["", f"{'─' * 30}", "  汇总"])
        for stype in sorted(type_stats.keys()):
            ts = type_stats[stype]
            wr = round(ts["wins"] / ts["count"] * 100, 1) if ts["count"] > 0 else 0
            avg_r = round(sum(ts["returns"]) / len(ts["returns"]), 2) if ts["returns"] else 0
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            lines.append(f"  {icon} {stype}: {ts['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%")

    return "\n".join(lines)
