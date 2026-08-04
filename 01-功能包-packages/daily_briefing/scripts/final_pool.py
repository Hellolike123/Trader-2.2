#!/usr/bin/env python3
"""选股池 CLI 薄入口 — 实现见 pool_cmds/。"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _ensure_trader_shared() -> None:
    try:
        import trader_shared  # noqa: F401
        return
    except ImportError:
        pass
    _d = _SCRIPTS
    for _ in range(10):
        # Hermes pack: scripts/trader_shared
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            return
        # Repo layout: <root>/02-共享模块-shared/trader_shared
        shared = _d / "02-共享模块-shared"
        if (shared / "trader_shared").is_dir():
            if str(shared) not in sys.path:
                sys.path.insert(0, str(shared))
            return
        _d = _d.parent
    raise ImportError("trader_shared not found; set PYTHONPATH or pip install -e .")


_ensure_trader_shared()

from pool_cmds.cli import main
from pool_cmds.compare_view import _latest_signal_summary, render_compare  # noqa: F401 — 测试/兼容

if __name__ == "__main__":
    raise SystemExit(main())
