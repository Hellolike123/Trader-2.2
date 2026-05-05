#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _p in (
    _ROOT / "01-功能包-packages" / "05-盘后复盘-review-trader" / "scripts",
    _ROOT / "02-共享模块-shared" / "01-行情数据-market-data",
    _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate",
    _ROOT / "02-共享模块-shared",
    _ROOT / "02-共享模块-shared" / "trader_shared",
    _ROOT / "02-共享模块-shared" / "03-输出校验-contracts",
    _ROOT / "02-共享模块-shared" / "scripts",
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from review_compare import run_compare, run_compare_recent
from review_single import run_single
from validate_output import validate


def parse_holding(value: str) -> tuple[str, float]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("--holding must use 股票:成本价")
    name, cost_text = value.split(":", 1)
    try:
        cost = float(cost_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--holding cost must be numeric") from exc
    return name, cost


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate review-trader single review or multi-stock comparison.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", help="A-share name or code for single-stock review")
    group.add_argument("--compare", nargs="+", help="Compare 2-5 A-share names/codes")
    group.add_argument("--compare-recent", action="store_true", help="Compare recently reviewed stocks from cache")
    parser.add_argument("--cost", type=float, help="Optional cost for --target")
    parser.add_argument("--holding", action="append", type=parse_holding, default=[], help="Optional compare holding: 股票:成本价")
    parser.add_argument("--date", help="Optional trade date YYYY-MM-DD")
    parser.add_argument("--session", choices=["close", "midday"], default="close", help="Review session for --target; close is after-close, midday is noon review")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.target:
            text = run_single(args.target, cost=args.cost, trade_date=args.date, output=args.output, session=args.session)
        elif args.compare:
            if not 2 <= len(args.compare) <= 5:
                raise RuntimeError("--compare requires 2-5 stocks")
            costs = {name: cost for name, cost in args.holding}
            text = run_compare(args.compare, costs=costs, trade_date=args.date, output=args.output)
        else:
            text = run_compare_recent(output=args.output)
    except Exception as exc:
        print(f"Review Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "markdown":
        errors = validate(text)
        if errors:
            print("Review Trader generated invalid output:", file=sys.stderr)
            for error in errors:
                print(error, file=sys.stderr)
            return 2
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
