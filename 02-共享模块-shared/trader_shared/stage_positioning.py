"""Stage positioning facade: re-export of all split submodules."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import numpy as np
from trader_shared._logging import get_logger
from trader_shared.safe_cast import safe_float
from trader_shared.config import (
    ACCUMULATION_DAYS_LIMIT, MARKUP_DAYS_LIMIT,
    RALLY_REDUCE_FULL_SCORE, RALLY_REDUCE_MIN_SCORE,
    RALLY_REDUCE_POSITION_PCT, RALLY_REDUCE_LITE_POSITION_PCT,
    CORRELATION_THRESHOLD, CORRELATION_LOOKBACK_DAYS,
)

from .stage_state import (
    _STATE_FILE,
    _load_stage_state,
    _logger,
    _save_stage_state,
    calc_portfolio_correlation
)

from .stage_detect import (
    _ADD_ACTIONS,
    _DECISION_MATRIX,
    _ENV_LIMITS,
    _REDUCE_ACTIONS,
    _assess_volume_price,
    _bearish_alignment,
    _detect_main_force_stage,
    _detect_major_stage,
    _detect_short_term_momentum,
    _downgrade_stage,
    _layer1_multi_day_confirm,
    _layer2_confidence_gate,
    _layer3_cross_validation,
    _layer4_stage_lock,
    _upgrade_stage,
    _volume_price_confirm,
    action_for_holding_state,
    assess_stage,
    compute_position_with_env
)

from .stage_stops import (
    check_time_stop,
    compute_exit_plan,
    compute_stage_stop,
    compute_stop_losses,
    compute_stop_summary
)

from .stage_position import (
    POSITION_STATES,
    _assess_resistance_strength,
    _calc_pullback_add_score,
    _calc_rally_reduce_score,
    _calc_reentry_score,
    _empty_position_state,
    _make_position_state,
    compute_conditional_take_profit,
    compute_take_profit,
    evaluate_position_state
)
