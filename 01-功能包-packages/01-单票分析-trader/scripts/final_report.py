#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

from run_analysis import build_report, build_signal, render_markdown
from validate_output import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final Trader report.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    parser.add_argument("--output", choices=["markdown", "signal-json", "alert-text", "watch"], default="markdown")
    parser.add_argument("--write-signal", action="store_true", help="Write triggered signals to signals.jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target)
    except Exception as exc:
        print(f"Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "alert-text":
        from run_analysis import generate_alert
        alert = generate_alert(report)
        if alert:
            print(alert)
        return 0

    if args.output == "signal-json":
        markdown = render_markdown(report)
        print(json.dumps(build_signal(report), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.output == "watch":
        from run_analysis import build_watch_alert
        alert_text = build_watch_alert(report, args.write_signal)
        print(alert_text)
        return 0

    markdown = render_markdown(report)
    errors = validate(markdown)
    if errors:
        print("Trader generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)

    last_target_path = os.path.expanduser("~/.trader/last_target.txt")
    os.makedirs(os.path.dirname(last_target_path), exist_ok=True)
    with open(last_target_path, "w", encoding="utf-8") as f:
        f.write(args.target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
