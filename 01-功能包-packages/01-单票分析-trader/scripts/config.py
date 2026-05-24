from __future__ import annotations

import sys
from pathlib import Path

# Add shared library to path if running directly in scripts
_SHARED = Path(__file__).resolve().parents[1] / "02-共享模块-shared"
if _SHARED.exists() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.config import (
    LOOKBACK_DAYS,
    RECENT_WINDOW,
    CONFIRM_BUFFER,
    STOP_BUFFER,
    TAKE_PROFIT_BUFFER,
    STATUS_SCORE,
    MA_PERIODS,
    MA_WEIGHTS,
    MIN_ZONE_WIDTH_PCT,
    MAX_ZONE_WIDTH_PCT,
    MIN_STOP_BUFFER_PCT,
    MAX_STOP_BUFFER_PCT,
    MIN_CONFIRM_SPACE_PCT,
    MAX_REASONABLE_MA_DISTANCE_PCT,
    STRUCTURE_WINDOW,
    CHANGE_THRESHOLD_STRONG,
    CHANGE_THRESHOLD_LARGE,
    CHANGE_THRESHOLD_LARGE_DROP,
    CHANGE_THRESHOLD_DROP,
    POSITION_RATIO_STRONG,
    POSITION_RATIO_CONFIRM,
    POSITION_RATIO_HIGH,
    ATR_HIGH_THRESHOLD,
    ATR_ELEVATED_THRESHOLD,
    ATR_NORMAL_THRESHOLD,
    PYRAMID_SCALES,
    BASE_WEIGHTS,
    ATRLV_INDEX,
)

# ── T0 Intraday parameters ──
MIN_5M_BARS: int = 20
MACD_WARMUP_BARS: int = 35
MIN_TRIGGER_MATCHES: int = 3
STRONG_TRIGGER_MATCHES: int = 5
MIN_T_AMPLITUDE_PCT: float = 0.015
GOOD_T_AMPLITUDE_PCT: float = 0.03
MIN_T_NET_SPACE_PCT: float = 0.006
MIN_SELL_NET_SPACE_PCT: float = 0.004
ZONE_MAX_WIDTH_PCT: float = 0.015
ZONE_AMPLITUDE_FACTOR: float = 0.15
DEFAULT_ZONE_WIDTH_PCT: float = 0.005
BUY_CONFIRM_FACTOR: float = 1.002
SELL_CONFIRM_FACTOR: float = 0.998
BUY_ACCEPT_FACTOR: float = 1.003
SELL_ACCEPT_FACTOR: float = 0.997
INVALID_BELOW_SUPPORT: float = 0.995
INVALID_ABOVE_RESISTANCE: float = 1.005
VOLUME_SHRINK_RATIO: float = 0.8
VOLUME_EXPAND_RATIO: float = 1.2
PRICE_TICK: float = 0.01
ENABLE_ICT_EXECUTION: bool = True
ICT_SWEEP_LOOKBACK: int = 8
ICT_RECENT_WINDOW: int = 6
ICT_STRUCTURE_LOOKBACK: int = 3
ATR_STOP_FACTOR: float = 2.0
ATR_STOP_MIN_PCT: float = 0.005
ATR_STOP_MAX_PCT: float = 0.025
ADX_STRONG_THRESHOLD: float = 25.0
ADX_WEAK_THRESHOLD: float = 20.0

# ── Left-side (aggressive entry) parameters ──
LEFT_TRIGGER_CORE: int = 1                # 1 个核心条件即可触发
LEFT_TRIGGER_AUX: int = 1                 # 1 个辅助条件即可触发
LEFT_NO_SUPPORT_BLOCK: bool = True        # 跌破主支撑不阻断（放量跌破仍阻断）
LEFT_FUSE_THRESHOLD: int = 2              # 熔断：当日 N 只标的同时止损 → 停止买入

# ── Frequency stop limit ──
FREQUENCY_STOP_LIMIT: int = 3             # 当日累计止损次数上限(任一 BUY_INVALIDATED)触发熔断

# ── Portfolio-specific constants ──
T0_POSITION_SPLIT: float = 0.55
DEFAULT_MAX_TOTAL: int = 80
DEFAULT_CASH_FLOOR: int = 20
DEFAULT_MAIN_CAP: int = 50

