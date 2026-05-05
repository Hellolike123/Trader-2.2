from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
_SHARED_MARKET = _ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
_SHARED_CANDIDATE = _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
for _p in (_SHARED_MARKET, _SHARED_CANDIDATE):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from review_model import build_review, enrich_with_signal_backtrack, pct_text, price_text
from review_store import recent_reviews, review_summary, save_review


def rank_key(item: dict[str, Any]) -> tuple[float, float, float]:
    score = float(item.get("score") or 0)
    momentum = float(item.get("momentum_score") or 0)
    chip = float(item.get("chip_score") or 0)
    return (score, momentum, chip)


def classify(items: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    ranked = sorted(items, key=rank_key, reverse=True)
    main = ranked[0]
    deputy = ranked[1] if len(ranked) >= 2 else None
    rest = ranked[2:]
    return main, deputy, rest


def render_compare(
    items: list[dict[str, Any]],
    date: str | None = None,
    *,
    main: dict[str, Any] | None = None,
    deputy: dict[str, Any] | None = None,
    rest: list[dict[str, Any]] | None = None,
) -> str:
    if len(items) < 2:
        raise RuntimeError("至少需要2只已复盘股票才能做多股比较")
    if len(items) > 5:
        items = sorted(items, key=rank_key, reverse=True)[:5]
    compare_date = date or items[0].get("date") or "--"
    if main is None or deputy is None or rest is None:
        main, deputy, rest = classify(items)
    ranked = sorted(items, key=rank_key, reverse=True)
    lines = [
        f"📌 多股复盘比较｜{compare_date}",
        "",
        "结论：",
        f"明天主盯{main['name']}" + (f"，副盯{deputy['name']}。" if deputy else "。"),
        "排序依据是结构、量价、筹码压力、动能和持仓适配。",
        "",
        "排序：",
    ]
    ranked = sorted(items, key=rank_key, reverse=True)
    for index, item in enumerate(ranked, start=1):
        lines.append(f"{index}）{item['name']}｜{item['state']}｜总分 {item['score']}｜压力 {price_text(item.get('key_pressure'))}")
    lines.extend(
        [
            "",
            "主盯：",
            f"{main['name']}｜{main['state']}",
            "理由：",
            f"结构分 {main['structure_score']}，量价分 {main['volume_score']}，动能分 {main['momentum_score']}。",
            f"关键压力 {price_text(main.get('key_pressure'))}，关键支撑 {price_text(main.get('key_support'))}。",
            f"动作：{main['action']}",
        ]
    )
    if deputy:
        lines.extend(
            [
                "",
                "副盯：",
                f"{deputy['name']}｜{deputy['state']}",
                "理由：",
                f"结构分 {deputy['structure_score']}，量价分 {deputy['volume_score']}，动能分 {deputy['momentum_score']}。",
                f"关键压力 {price_text(deputy.get('key_pressure'))}，关键支撑 {price_text(deputy.get('key_support'))}。",
            ]
        )
    lines.extend(["", "只观察 / 先防守："])
    if rest:
        for item in rest:
            risk = "先防守" if (item.get("score") or 0) < 55 else "只观察"
            lines.append(f"{item['name']}｜{risk}｜{item['state']}｜{item['blocks'][0] if item.get('blocks') else '等待确认'}")
    else:
        lines.append("暂无。")
    lines.extend(["", "明日动作："])
    for item in ranked:
        if item is main:
            lines.append(f"{item['name']}：主盯 {price_text(item.get('key_pressure'))} 能否放量站稳。")
        elif item is deputy:
            lines.append(f"{item['name']}：副盯，不追高，守住 {price_text(item.get('key_support'))} 继续观察。")
        else:
            lines.append(f"{item['name']}：不主动加仓，等结构重新确认。")
    return "\n".join(lines)


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def run_compare(targets: list[str], costs: dict[str, float] | None = None, trade_date: str | None = None, output: str = "markdown") -> str:
    costs = costs or {}
    summaries: list[dict[str, Any]] = []
    for target in targets:
        review = build_review(target, cost=costs.get(target), trade_date=trade_date)
        enrich_with_signal_backtrack(review)
        save_review(review)
        summaries.append(review_summary(review))
    main, deputy, rest = classify(summaries)
    markdown = render_compare(summaries, main=main, deputy=deputy, rest=rest)
    if output == "json":
        return render_json({"contract": "review_trader_compare_v1", "items": summaries, "markdown": markdown})
    return markdown


def run_compare_recent(output: str = "markdown") -> str:
    reviews = recent_reviews(limit=5)
    if len(reviews) < 2:
        raise RuntimeError("最近同一交易日复盘少于2只股票，无法比较；请先复盘至少2只股票。")
    main, deputy, rest = classify(reviews)
    markdown = render_compare(reviews, main=main, deputy=deputy, rest=rest)
    if output == "json":
        return render_json({"contract": "review_trader_compare_v1", "items": reviews, "markdown": markdown})
    return markdown
