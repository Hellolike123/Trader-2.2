#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / "02-共享模块-shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from trader_shared.schema.v1 import validate_pool
validate = validate_pool


def _read_text(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Trader Pool markdown.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    markdown = _read_text(args.path)
    errors = validate(markdown)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("VALID_TRADER_POOL_OUTPUT=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
