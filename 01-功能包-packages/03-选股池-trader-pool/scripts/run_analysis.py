#!/usr/bin/env python3
"""Pool reuses trader's run_analysis.py for build_report + render_markdown."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRADER_DIR = ROOT / "01-功能包-packages" / "01-单票分析-trader" / "scripts"
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
SHARED_TRADER_SHARED = SHARED_ROOT / "trader_shared"
for _p in (TRADER_DIR, SHARED_CANDIDATE, SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT, SHARED_TRADER_SHARED):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_trader_path = str(TRADER_DIR / "run_analysis.py")
_trader_spec = importlib.util.spec_from_file_location("_trader_ra", _trader_path)
_trader_ra = importlib.util.module_from_spec(_trader_spec)
_trader_spec.loader.exec_module(_trader_ra)

build_report = _trader_ra.build_report
render_markdown = _trader_ra.render_markdown
