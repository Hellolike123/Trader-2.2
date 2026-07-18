"""选股池汇总渲染。"""
from __future__ import annotations

from typing import Any

def render_pool_summary(pool_data: dict[str, Any]) -> str:
    """渲染选股池汇总/排序报告。"""
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


