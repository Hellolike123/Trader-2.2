#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from portfolio_run import build_portfolio, build_snapshot_portfolio, load_snapshot
from validate_output import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final Trader Portfolio output.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", nargs="+", help="A-share names or codes")
    group.add_argument("--snapshot", help="JSON portfolio snapshot path")
    parser.add_argument("--max-total", type=int, default=80)
    parser.add_argument("--cash-floor", type=int, default=20)
    parser.add_argument("--main-cap", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.snapshot:
            markdown = build_snapshot_portfolio(
                load_snapshot(args.snapshot),
                max_total=args.max_total,
                cash_floor=args.cash_floor,
            )["portfolio_markdown"]
        else:
            markdown = build_portfolio(
                args.targets,
                max_total=args.max_total,
                cash_floor=args.cash_floor,
                main_cap=args.main_cap,
            )["portfolio_markdown"]
    except Exception as exc:
        print(f"Trader Portfolio skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    errors = validate(markdown)
    if errors:
        print("Trader Portfolio generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
