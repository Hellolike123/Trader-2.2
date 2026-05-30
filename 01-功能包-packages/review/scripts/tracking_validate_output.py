#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import trader_shared
from trader_shared.schema.v1 import validate_review
validate = validate_review


def _read_text(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate review tracking output.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    markdown = _read_text(args.path)
    errors = validate(markdown)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("VALID_REVIEW_TRADER_OUTPUT=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
