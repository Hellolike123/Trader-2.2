"""Pool commands — rank.py"""
from __future__ import annotations

import argparse
from typing import Any

from pool_cmds.common import *  # noqa: F403

def cmd_rank(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    print(render_rank(items))
    return 0

