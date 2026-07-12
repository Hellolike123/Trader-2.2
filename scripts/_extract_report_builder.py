#!/usr/bin/env python3
"""One-shot extractor: pull build_report + its helper closure out of
run_analysis.py into trader_shared/report_builder.py (ADR-003).

Keeps run_analysis.py as a thin CLI + render shell that re-exports the
shared helpers build_report needs. Deterministic line-slice; safe because
the golden test guards behavior afterwards.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path("/Users/like/Documents/Opencode/Trader3.0")
SRC = REPO / "01-功能包-packages/trader/scripts/run_analysis.py"
DST = REPO / "02-共享模块-shared/trader_shared/report_builder.py"

text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")

# Boundaries (1-indexed line numbers, confirmed by reading the file):
#   line 117  -> _kelly_cache (first line of moved block)
#   line 1801 -> def volume_observation (first line of render/CLI layer)
KEPT_END = 115      # keep lines[0:115]  (1..115)
MOVED_START = 115   # lines[115] = line 116 (kelly comment); line 117 = _kelly_cache
MOVED_END = 2953    # lines[2953] = line 2954 (start of parse_args); keep only CLI

kept = lines[0:KEPT_END]
moved = lines[MOVED_START:MOVED_END]

# Collect top-level def names in the moved block for the re-export statement.
moved_names = []
for ln in moved:
    m = re.match(r"^def (\w+)\b", ln)
    if m:
        moved_names.append(m.group(1))

HEADER = '''from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from datetime import date
import os
import json

from trader_shared._logging import get_logger
_logger = get_logger(__name__)
SCRIPT_DIR = Path(__file__).resolve().parent

from trader_shared.light_data import to_float, pct_change
from trader_shared.stage_positioning import (
    assess_stage, compute_exit_plan, compute_stage_stop, check_time_stop,
    evaluate_position_state, _detect_major_stage,
)
from trader_shared.fetchers import TencentFetcher
from trader_shared.indicator_math import aggregate_5m_to_60m, calc_supertrend, calc_vwap
from trader_shared.chip_core import analyze_chips_and_migration
from trader_shared.config import (
    LOOKBACK_DAYS, STRUCTURE_WINDOW, ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS, KELLY_MAX_TOTAL_POSITIONS, KELLY_MIN_TRADES,
)
try:
    from trader_shared.models import DATA_STATUS_MAP
except ImportError:
    DATA_STATUS_MAP: dict[str, str] = {
        "complete": "full", "partial": "partial",
        "degraded": "degraded", "failed": "degraded",
    }
from trader_shared import (
    conflicting_signals, get_market_level, get_market_note,
    write_stock, log, stats_by_type,
)
from trader_shared import get_env_for_skill
from trader_shared.signal_contract import assert_valid_signal
from trader_shared.signal_core import (
    clear_signals_cache, read_signals_for_report, load_historical_win_rate,
    get_pool_count, build_signal, one_sentence, state_text, _map_fusion_to_signal,
)

'''

report_builder = HEADER + "\n".join(moved) + "\n"
DST.write_text(report_builder, encoding="utf-8")

# Re-export statement inserted into run_analysis.py
re_export = "from trader_shared.report_builder import (\n    " + ",\n    ".join(moved_names) + ",\n)"
new_run = "\n".join(kept) + "\n\n" + re_export + "\n\n" + "\n".join(lines[MOVED_END:]) + "\n"
SRC.write_text(new_run, encoding="utf-8")

print("MOVED_NAMES:", moved_names)
print("report_builder lines:", len(moved))
print("run_analysis kept head:", len(kept), "tail:", len(lines[MOVED_END:]))
print("DONE")
