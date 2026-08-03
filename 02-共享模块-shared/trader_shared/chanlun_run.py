"""缠论 Skill 编排：共用行情快照并调用既有缠论引擎。

法源：
- B·中剪：docs/plans/chanlun-skill-slim-b-handoff.md
- 旧薄卡：docs/plans/done/chanlun-cd-followup-handoff.md §2.3 / §3
本模块只编排和构建薄 view，不复制分型、笔、段、中枢或买卖点算法。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from trader_shared.chanlun_render import (
    build_chanlun_light_snapshot_entry,
    format_chanlun_light_change,
    render_chanlun_card,
    render_chanlun_slim,
)


def _unwrap(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    nested = result.get("chanlun")
    return nested if isinstance(nested, dict) else result


def build_chanlun_view(result: Any, *, current: float | None = None) -> dict[str, Any]:
    """从引擎结果提取可核字段；不在展示层重算结构。

    C-D4e：现价相对末笔终点反向大幅离开时，写入 tip_leave，供渲染降级文案
    （不在此推进笔几何，只禁止旧笔「拉升/当前向上」假叙事）。
    """
    chan = _unwrap(result)
    strokes = [s for s in (chan.get("strokes") or []) if isinstance(s, dict)]
    directions = [
        str(stroke.get("direction"))
        for stroke in strokes
        if stroke.get("direction") in ("up", "down")
    ]
    buy_points = [dict(p) for p in (chan.get("buy_points") or []) if isinstance(p, dict)]
    sell_points = [dict(p) for p in (chan.get("sell_points") or []) if isinstance(p, dict)]
    zones = [z for z in (chan.get("zones") or []) if isinstance(z, dict)]
    segments = [s for s in (chan.get("segments") or []) if isinstance(s, dict)]
    timeframe = str(chan.get("timeframe") or "insufficient")
    current_dir = (
        str(strokes[-1].get("direction"))
        if strokes and strokes[-1].get("direction") in ("up", "down")
        else ""
    )

    tip_leave = ""
    try:
        from trader_shared.conclusion_block import _stroke_tip_left_against

        price = float(current) if current is not None else 0.0
        tip_leave = _stroke_tip_left_against(strokes, price) or ""
    except Exception:
        tip_leave = ""

    # G-K3 / C-DIFF-5：zones_count=引擎 raw 窗；pivot_count=合并后中枢
    raw_zones = chan.get("zones_count")
    try:
        zones_count = int(raw_zones) if raw_zones is not None else len(zones)
    except (TypeError, ValueError):
        zones_count = len(zones)
    merged_pivots = chan.get("pivot_count")
    try:
        pivot_count = int(merged_pivots) if merged_pivots is not None else len(zones)
    except (TypeError, ValueError):
        pivot_count = len(zones)

    return {
        "timeframe": timeframe,
        "data_ok": timeframe != "insufficient" and bool(chan),
        "structure_type": str(chan.get("structure_type") or ""),
        "trend_label": str(chan.get("trend_label") or ""),
        "stroke_count": len(strokes),
        "current_stroke_direction": current_dir,
        "recent_stroke_directions": directions[-5:],
        "tip_leave": tip_leave,
        "zones_count": zones_count,
        "pivot_count": pivot_count,
        "segments_count": len(segments),
        # 买卖点只复制引擎数组；不读 fusion reason，也不从汇总文案反推。
        "buy_points": buy_points,
        "sell_points": sell_points,
    }


def _bar_adjust_mode(bars: list[dict[str, Any]]) -> str | None:
    if not bars:
        return None
    values = {
        str(bar.get("adjust") or bar.get("adjust_mode") or "").strip().lower()
        for bar in bars
        if isinstance(bar, dict)
        and str(bar.get("adjust") or bar.get("adjust_mode") or "").strip()
    }
    if not values:
        return "unknown"
    if len(values) > 1:
        return "mixed"
    return next(iter(values))


def _resolve_adjust_mode(
    daily_bars: list[dict[str, Any]],
    weekly_bars: list[dict[str, Any]],
) -> str:
    modes = [
        mode
        for mode in (_bar_adjust_mode(daily_bars), _bar_adjust_mode(weekly_bars))
        if mode is not None
    ]
    if not modes:
        return "unknown"
    if len(set(modes)) == 1:
        return modes[0]
    if "unknown" in modes:
        return "mixed/unknown"
    return "mixed"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def build_chanlun_plan(target: str) -> dict[str, Any]:
    """取同一份日/周快照，分别运行短线与中线缠论。"""
    from trader_shared.chan_core import chanlun_strategy, chanlun_strategy_midline
    from trader_shared.config import CHANLUN_MIN_BARS, LOOKBACK_DAYS
    from trader_shared.light_data import load_market_snapshot

    target = str(target or "").strip()
    if not target:
        return {
            "target": target,
            "name": "未知",
            "data_ok": False,
            "data_bars_daily": 0,
            "data_bars_weekly": 0,
            "adjust_mode": "unknown",
            "data_note": "未指定标的",
            "error": "未指定标的",
        }

    try:
        snapshot = load_market_snapshot(
            target,
            days=LOOKBACK_DAYS,
            include_5m=False,
            include_weekly=True,
            include_monthly=False,
            include_ticks=False,
        )
    except Exception as exc:
        message = f"取数失败：{exc}"
        return {
            "target": target,
            "name": target,
            "data_ok": False,
            "data_bars_daily": 0,
            "data_bars_weekly": 0,
            "adjust_mode": "unknown",
            "data_note": message,
            "error": message,
        }

    daily_bars = list(snapshot.daily_bars or [])
    weekly_bars = list(snapshot.weekly_bars or [])
    quote = dict(snapshot.quote) if isinstance(snapshot.quote, dict) else {}
    security = snapshot.security
    name = str(getattr(security, "name", "") or quote.get("name") or target)
    code = str(getattr(security, "code", "") or "")
    current = _number(quote.get("current_price"))
    if current is None and daily_bars:
        current = _number(daily_bars[-1].get("close"))
    current_for_engine = current or 0.0
    analysis_date = quote.get("trade_date")
    if not analysis_date and daily_bars:
        analysis_date = daily_bars[-1].get("date") or daily_bars[-1].get("time")

    daily_count = len(daily_bars)
    weekly_count = len(weekly_bars)
    if daily_count < CHANLUN_MIN_BARS:
        short_result: dict[str, Any] = {
            "chanlun": {
                "timeframe": "insufficient",
                "structure_type": "",
                "trend_label": "数据不足",
                "strokes": [],
                "segments": [],
                "zones": [],
                "buy_points": [],
                "sell_points": [],
            }
        }
    else:
        short_result = chanlun_strategy(
            current_for_engine,
            daily_bars,
            change_pct=quote.get("change_pct"),
            quote=quote,
            symbol=code or target,
            analysis_date=str(analysis_date) if analysis_date else None,
            weekly_bars=weekly_bars,
        )

    midline_result = chanlun_strategy_midline(
        current_for_engine,
        weekly_bars=weekly_bars,
        daily_bars=daily_bars,
        change_pct=quote.get("change_pct"),
        quote=quote,
        symbol=code or target,
        analysis_date=str(analysis_date) if analysis_date else None,
    )

    data_ok = daily_count >= CHANLUN_MIN_BARS
    if not data_ok:
        data_note = f"日线不足（{daily_count}/{CHANLUN_MIN_BARS}根）"
    elif weekly_count < CHANLUN_MIN_BARS:
        data_note = f"周线不足（{weekly_count}/{CHANLUN_MIN_BARS}根），中线副读回退日线"
    else:
        data_note = "日周数据齐"

    return {
        "target": target,
        "name": name,
        "code": code,
        "price": current,
        "data_ok": data_ok,
        "data_bars_daily": daily_count,
        "data_bars_weekly": weekly_count,
        "data_bars_lower": None,
        "adjust_mode": _resolve_adjust_mode(daily_bars, weekly_bars),
        "data_note": data_note,
        "data_status": str(getattr(snapshot, "data_status", "") or ""),
        "daily_analysis": _unwrap(short_result),
        "midline_analysis": _unwrap(midline_result),
        "short_view": build_chanlun_view(short_result, current=current),
        "midline_view": build_chanlun_view(midline_result, current=current),
        "error": None if data_ok else data_note,
    }


def _card_ok(plan: dict[str, Any]) -> bool:
    return bool(plan.get("data_ok")) and not plan.get("error")


def _snapshot_key(plan: dict[str, Any]) -> str:
    return str(plan.get("code") or plan.get("target") or "").strip()


def attach_change_and_persist_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """对比灯快照 → 写入 plan['change_line'] → 写回该票快照。"""
    from trader_shared.trader_paths import load_json, rmw_json

    key = _snapshot_key(plan)
    curr = build_chanlun_light_snapshot_entry(plan)
    prev: dict[str, Any] | None = None
    if key:
        try:
            store = load_json("chanlun_light_snapshot")
            entry = store.get(key)
            if isinstance(entry, dict):
                prev = entry
        except Exception:
            prev = None

    plan = dict(plan)
    plan["change_line"] = format_chanlun_light_change(prev, curr)
    plan["light_snapshot"] = curr

    if key:

        def _mutate(data: dict[str, Any]) -> dict[str, Any]:
            out = dict(data) if isinstance(data, dict) else {}
            out[key] = curr
            return out

        try:
            rmw_json("chanlun_light_snapshot", _mutate)
        except Exception:
            pass
    return plan


def run_card(
    target: str,
    *,
    output: str = "markdown",
    brief: bool = False,
) -> tuple[str, bool]:
    plan = build_chanlun_plan(target)
    if output == "json":
        slim = {
            key: value
            for key, value in plan.items()
            if key not in ("daily_analysis", "midline_analysis")
        }
        return json.dumps(slim, ensure_ascii=False, indent=2, default=str), _card_ok(plan)

    if brief:
        return render_chanlun_card(plan), _card_ok(plan)

    if plan.get("data_ok") and not plan.get("error"):
        plan = attach_change_and_persist_snapshot(plan)
    else:
        plan = dict(plan)
        plan.setdefault("change_line", "首次记录，暂无对比")
    return render_chanlun_slim(plan), _card_ok(plan)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chanlun B·中剪 / 旧薄结构卡.")
    parser.add_argument("--target", help="A-share name or code")
    parser.add_argument(
        "--brief",
        action="store_true",
        help="输出旧版薄卡（render_chanlun_card）；默认 B·中剪 slim 卡",
    )
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target:
        print("需要 --target <NAME>", file=sys.stderr)
        return 2
    try:
        text, ok = run_card(args.target, output=args.output, brief=bool(args.brief))
        print(text)
        return 0 if ok else 1
    except Exception as exc:
        print(f"Chanlun skill cannot run: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "attach_change_and_persist_snapshot",
    "build_chanlun_plan",
    "build_chanlun_view",
    "main",
    "parse_args",
    "run_card",
]


if __name__ == "__main__":
    raise SystemExit(main())
