#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from run_analysis import build_report, render_markdown
from validate_output import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final Trader report.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        markdown = render_markdown(build_report(args.target))
    except Exception as exc:
        print(f"Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    errors = validate(markdown)
    if errors:
        print("Trader generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
