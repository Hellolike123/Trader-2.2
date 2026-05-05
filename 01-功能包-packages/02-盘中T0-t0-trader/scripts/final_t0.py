#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from monitor import recent_history, run_monitor
from t0_run import build_plan, render_markdown
from validate_output import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final T0 card.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    parser.add_argument("--monitor", action="store_true", help="Run monitor mode and only alert on state changes")
    parser.add_argument("--once", action="store_true", help="Run one monitor check for Hermes scheduled calls")
    parser.add_argument("--interval", type=int, default=3, help="Monitor interval in minutes for long-running mode")
    parser.add_argument("--cost", type=float, default=None, help="Optional holding cost for personalized alerts")
    parser.add_argument("--position", type=int, default=None, help="Optional base position shares for T-share sizing")
    parser.add_argument("--max-alerts", type=int, default=20, help="Stop long-running monitor after this many alerts")
    parser.add_argument("--verbose", action="store_true", help="Print no-alert status in monitor mode")
    parser.add_argument("--reset-cache", action="store_true", help="Clear cached state for this target before checking")
    parser.add_argument("--scale", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.monitor:
        try:
            return run_monitor(
                args.target,
                interval=args.interval,
                cost=args.cost,
                position=args.position,
                once=args.once,
                max_alerts=args.max_alerts,
                verbose=args.verbose,
                reset_cache=args.reset_cache,
            )
        except Exception as exc:
            print(f"T0 monitor cannot run in this environment: {exc}", file=sys.stderr)
            return 1

    try:
        plan = build_plan(args.target)
        markdown = render_markdown(plan, history=recent_history(str(plan.get("symbol") or args.target)))
    except Exception as exc:
        print(f"T0 skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    errors = validate(markdown)
    if errors:
        print("T0 generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
