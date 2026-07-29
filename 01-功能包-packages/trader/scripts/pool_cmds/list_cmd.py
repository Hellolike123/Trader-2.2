"""Pool commands — list_cmd.py"""
from __future__ import annotations

import argparse
from typing import Any

from pool_cmds.common import *  # noqa: F403

def cmd_list(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = sort_items(active_items(pool))
    items = _refresh_pool_prices(items, pool)
    count = counts(items)
    print(f"选股池 {len(items)}/{POOL_LIMIT}")
    # P0 Fix: 检查疑似停牌
    stale_warnings = _check_stale_items(items)
    if stale_warnings:
        for w in stale_warnings:
            print(w)
    print("")
    for item in items:
        stage_str = str(item.get("stage_status") or item.get("major_stage", "蓄势") + "+" + item.get("momentum", "震荡"))
        name = item.get("name", "?")
        status = item.get("status", "?")
        trigger = price(item.get("trigger"))
        defense = price(item.get("defense"))
        print(f"{name}  {stage_str}  {status}  触发{trigger}  防守{defense}")
    return 0

