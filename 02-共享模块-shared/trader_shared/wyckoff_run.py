"""威科夫 Skill 引擎：取数 + analysis + view；渲染见 wyckoff_render。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from trader_shared.wyckoff_chain import (
    attach_wyckoff_chain_fields,
    format_wyckoff_chain_plain,
    wyckoff_chain_rank,
)
from trader_shared.wyckoff_render import render_wyckoff_card, render_wyckoff_rank


def _pool_path() -> Path:
    return Path.home() / ".trader" / "pool.json"


def load_pool_items(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or _pool_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def build_wyckoff_plan(target: str) -> dict[str, Any]:
    """单票：轻量快照 + 日/周 wyckoff_analysis → View + 链。"""
    from trader_shared.light_data import load_market_snapshot
    from trader_shared.wyckoff_core import format_wyckoff_event_light, wyckoff_analysis
    from trader_shared.wyckoff_view import to_wyckoff_state_view

    target = str(target or "").strip()
    if not target:
        return {"error": "未指定标的", "target": target, "data_ok": False}

    try:
        snap = load_market_snapshot(
            target,
            days=300,
            include_5m=False,
            include_weekly=True,
            include_monthly=False,
            include_ticks=False,
        )
    except Exception as exc:
        return {
            "error": f"取数失败：{exc}",
            "target": target,
            "name": target,
            "data_ok": False,
        }

    sec = snap.security
    name = str(getattr(sec, "name", None) or snap.quote.get("name") or target)
    code = str(getattr(sec, "code", None) or "")
    price = snap.quote.get("current_price") if isinstance(snap.quote, dict) else None

    daily_bars = list(snap.daily_bars or [])
    weekly_bars = list(snap.weekly_bars or [])

    if len(daily_bars) < 30:
        return {
            "target": target,
            "name": name,
            "code": code,
            "price": price,
            "data_ok": False,
            "error": "日线不足，无法做威科夫结构卡",
        }

    daily_raw = wyckoff_analysis(
        daily_bars, symbol=code or target, timeframe="daily", use_persisted_phase=False
    )
    daily_view = to_wyckoff_state_view(daily_raw, symbol=code or target, timeframe="daily")

    weekly_view: dict[str, Any] = {}
    weekly_raw: dict[str, Any] = {}
    if len(weekly_bars) >= 20:
        weekly_raw = wyckoff_analysis(
            weekly_bars, symbol=code or target, timeframe="weekly", use_persisted_phase=False
        )
        weekly_view = dict(
            to_wyckoff_state_view(weekly_raw, symbol=code or target, timeframe="weekly")
        )

    chain_plain = format_wyckoff_chain_plain(daily_raw)
    event_line = format_wyckoff_event_light(daily_raw if isinstance(daily_raw, dict) else {})

    return {
        "target": target,
        "name": name,
        "code": code,
        "price": price,
        "data_ok": True,
        "daily_raw": daily_raw,
        "weekly_raw": weekly_raw,
        "daily_view": daily_view,
        "weekly_view": weekly_view,
        "chain_plain": chain_plain,
        "chain_rank": wyckoff_chain_rank(daily_raw),
        "event_line": event_line,
    }


def build_wyckoff_rank_rows(
    items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """从 pool 缓存构建链排序行（不改分道；缺缓存则链显示未成型）。"""
    src = items if items is not None else load_pool_items()
    rows: list[dict[str, Any]] = []
    for item in src:
        rec = dict(item)
        attach_wyckoff_chain_fields(rec)
        name = str(rec.get("name") or rec.get("target") or "?")
        wyk = rec.get("wyckoff") if isinstance(rec.get("wyckoff"), dict) else {}
        phase = str(
            rec.get("wyckoff_phase_label")
            or wyk.get("phase_label")
            or rec.get("phase_label")
            or "—"
        )
        rows.append(
            {
                "name": name,
                "target": rec.get("target") or name,
                "chain_plain": format_wyckoff_chain_plain(rec),
                "chain_rank": wyckoff_chain_rank(rec),
                "phase": phase,
                "phase_label": phase,
                "current": rec.get("current") or rec.get("current_price"),
            }
        )
    rows.sort(
        key=lambda r: (
            -int(r.get("chain_rank") or 0),
            str(r.get("name") or ""),
        )
    )
    return rows


def _card_ok(plan: dict[str, Any]) -> bool:
    """取数/日线不足等降级卡：仍打印面板，但对 CLI 视为失败。"""
    return bool(plan.get("data_ok")) and not plan.get("error")


def run_card(target: str, *, output: str = "markdown") -> tuple[str, bool]:
    plan = build_wyckoff_plan(target)
    if output == "json":
        # 去掉过大 raw，便于调试
        slim = {k: v for k, v in plan.items() if k not in ("daily_raw", "weekly_raw")}
        text = json.dumps(slim, ensure_ascii=False, indent=2, default=str)
    else:
        text = render_wyckoff_card(plan)
    return text, _card_ok(plan)


def run_rank(*, output: str = "markdown") -> str:
    rows = build_wyckoff_rank_rows()
    if output == "json":
        return json.dumps({"rows": rows}, ensure_ascii=False, indent=2, default=str)
    hint = None
    if not rows:
        hint = "池空；可先用 trader final_pool add，再 refresh"
    return render_wyckoff_rank(rows, empty_hint=hint)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wyckoff structure card / pool chain rank.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["rank"],
        default=None,
        help="rank = 池内吸筹链排序（读 ~/.trader/pool.json）",
    )
    parser.add_argument("--target", help="A-share name or code for single-stock card")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "rank":
            text = run_rank(output=args.output)
            print(text)
            return 0
        if args.target:
            text, ok = run_card(args.target, output=args.output)
            print(text)
            return 0 if ok else 1
        print("需要 --target <NAME> 或子命令 rank", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Wyckoff skill cannot run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
