"""Backward-compatible hub: re-export pool command API for cli.py."""
from __future__ import annotations

from pool_cmds.common import *  # noqa: F403
from pool_cmds.add import (  # noqa: F401
    cmd_add,
    cmd_add_last,
    cmd_add_pending,
    cmd_analyze,
    cmd_archive_exited,
    cmd_confirm_to_pool,
    cmd_remove,
    cmd_review,
    cmd_show_pending,
    quick_add,
)
from pool_cmds.list_cmd import cmd_list  # noqa: F401
from pool_cmds.rank import cmd_rank  # noqa: F401
from pool_cmds.plan import cmd_plan  # noqa: F401
from pool_cmds.refresh import cmd_refresh  # noqa: F401
from pool_cmds.watch import cmd_compare, cmd_reconcile, cmd_watch  # noqa: F401
