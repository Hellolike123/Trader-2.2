#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    import trader_shared  # noqa: F401
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            break
        if (_d / "02-共享模块-shared" / "trader_shared").is_dir():
            shared = str(_d / "02-共享模块-shared")
            if shared not in sys.path:
                sys.path.insert(0, shared)
            break
        _d = _d.parent
    else:
        raise

from trader_shared.chanlun_run import main


if __name__ == "__main__":
    raise SystemExit(main())
