#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OBSOLETE — classic vs cards fusion 对账 CLI 已退役。

法源：docs/plans/retire-classic-fusion-handoff.md
classic / compare 热路径已删除；生产一律 cards。
本脚本保留入口仅打印退役说明后退出。
"""
from __future__ import annotations

import sys


_MSG = (
    "compare_fusion_paths.py is obsolete: classic/compare fusion paths have been retired.\n"
    "Production always uses cards (FUSION_FROM_CARDS classic/compare → cards + DeprecationWarning).\n"
    "See docs/plans/retire-classic-fusion-handoff.md / BUSINESS.md §2.7."
)


def main(argv: list[str] | None = None) -> int:
    print(_MSG, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
