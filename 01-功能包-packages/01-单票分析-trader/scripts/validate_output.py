#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 双模式路径发现：Hermes skill 包内 vs 仓库开发
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    ROOT = _SCRIPT_DIR.parent          # skill 模式
else:
    ROOT = _SCRIPT_DIR.parents[3]      # 仓库模式
SHARED = ROOT / "02-共享模块-shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from trader_shared.schema.v1 import validate_trader
validate = validate_trader


def _read_text(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Hermes Trader V2 markdown.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    markdown = _read_text(args.path)
    errors = validate(markdown)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("VALID_TRADER_OUTPUT=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
