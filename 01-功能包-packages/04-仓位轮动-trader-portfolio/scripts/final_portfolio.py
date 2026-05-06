#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portfolio_run import build_portfolio, build_snapshot_portfolio, load_snapshot
from validate_output import validate

POSITIONS_PATH = Path.home() / ".trader" / "positions.json"


def load_positions() -> list[dict]:
    if POSITIONS_PATH.exists():
        try:
            data = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    POSITIONS_PATH.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_position(positions: list[dict], name: str) -> int | None:
    for i, p in enumerate(positions):
        if p.get("name") == name:
            return i
    return None


def record_buy(name: str, shares: int, cost: float) -> dict:
    positions = load_positions()
    idx = find_position(positions, name)
    if idx is not None:
        old = positions[idx]
        total_shares = old.get("shares", 0) + shares
        total_cost = old.get("cost", 0) * old.get("shares", 0) + cost * shares
        avg_cost = round(total_cost / total_shares, 2) if total_shares else cost
        positions[idx] = {
            "name": name,
            "shares": total_shares,
            "cost": avg_cost,
        }
    else:
        positions.append({"name": name, "shares": shares, "cost": cost})
    save_positions(positions)
    return {"name": name, "shares": shares, "cost": cost, "total_shares": positions[find_position(positions, name)]["shares"]}


def record_sell(name: str, shares: int) -> dict:
    positions = load_positions()
    idx = find_position(positions, name)
    if idx is None:
        return {"error": f"持仓中找不到 {name}"}
    old = positions[idx]
    remaining = old["shares"] - shares
    if remaining <= 0:
        positions.pop(idx)
        save_positions(positions)
        return {"name": name, "sold": old["shares"], "remaining": 0}
    positions[idx] = {"name": name, "shares": remaining, "cost": old["cost"]}
    save_positions(positions)
    return {"name": name, "sold": shares, "remaining": remaining}


def positions_to_snapshot(targets: list[str]) -> dict:
    positions = load_positions()
    holdings = [p for p in positions if p.get("name") in targets]
    candidates = [{"name": t} for t in targets if not any(p.get("name") == t for p in holdings)]
    return {
        "targets": targets,
        "holdings": holdings,
        "candidates": candidates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="仓位轮动 + 交易记录")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", nargs="+", help="股票名或代码")
    group.add_argument("--snapshot", help="JSON snapshot 文件路径")
    group.add_argument("--record", choices=["buy", "sell"], help="记录买入/卖出")
    parser.add_argument("--name", help="股票名")
    parser.add_argument("--shares", type=int, help="股数")
    parser.add_argument("--cost", type=float, help="成交价")
    parser.add_argument("--max-total", type=int, default=80)
    parser.add_argument("--cash-floor", type=int, default=20)
    parser.add_argument("--main-cap", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # --- record mode ---
    if args.record:
        if not args.name or not args.shares:
            print("--record 需要 --name 和 --shares", file=sys.stderr)
            return 1
        if args.record == "buy":
            cost = args.cost or 0
            result = record_buy(args.name, args.shares, cost)
            print(f"已记录：买入 {result['name']} {result['shares']} 股")
            print(f"总持仓：{result['total_shares']} 股")
        elif args.record == "sell":
            result = record_sell(args.name, args.shares)
            if "error" in result:
                print(result["error"], file=sys.stderr)
                return 1
            print(f"已记录：卖出 {result['name']} {result['sold']} 股")
            print(f"剩余：{result['remaining']} 股")
        return 0

    # --- build mode ---
    try:
        if args.snapshot:
            markdown = build_snapshot_portfolio(
                load_snapshot(args.snapshot),
                max_total=args.max_total,
                cash_floor=args.cash_floor,
            )["portfolio_markdown"]
        else:
            positions = load_positions()
            holdings = {p["name"]: p for p in positions if p.get("name") in args.targets}
            if holdings:
                markdown = build_portfolio(
                    args.targets,
                    holdings=holdings,
                    max_total=args.max_total,
                    cash_floor=args.cash_floor,
                    main_cap=args.main_cap,
                )["portfolio_markdown"]
            else:
                markdown = build_portfolio(
                    args.targets,
                    max_total=args.max_total,
                    cash_floor=args.cash_floor,
                    main_cap=args.main_cap,
                )["portfolio_markdown"]
    except Exception as exc:
        print(f"轮动仓位失败：{exc}", file=sys.stderr)
        return 1

    errors = validate(markdown)
    if errors:
        print("输出校验失败：", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
