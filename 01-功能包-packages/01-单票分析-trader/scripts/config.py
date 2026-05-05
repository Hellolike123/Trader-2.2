from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1] / "02-共享模块-shared"
if _SHARED.exists() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.config import (
    LOOKBACK_DAYS,
    RECENT_WINDOW,
    CONFIRM_BUFFER,
    STOP_BUFFER,
    TAKE_PROFIT_BUFFER,
)

STRUCTURE_WINDOW: int = 20
