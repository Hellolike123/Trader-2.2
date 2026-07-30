"""Pool commands — plan.py"""
from __future__ import annotations

import argparse
from typing import Any

from pool_cmds.common import *  # noqa: F403

def cmd_plan(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    # 衰退淘汰已在 refresh 中处理，plan 只读不写
    # P0 Fix: 检查疑似停牌
    stale_warnings = _check_stale_items(items)
    if stale_warnings:
        for w in stale_warnings:
            print(w)
    markdown = render_plan(items)
    execution = [
        item for item in sort_items_unified(items) if item.get("lane") == "ready"
    ][:EXECUTION_LIMIT]
    with DataManager.state_lock("last_plan"):
        DataManager.save_state("last_plan", {"contract_version": CONTRACT_VERSION, "date": today_text(), "execution_items": execution, "markdown": markdown})
    print(markdown)
    return 0

