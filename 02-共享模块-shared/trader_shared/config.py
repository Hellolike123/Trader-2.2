"""Shared constants common to all trader skills.

All calculation parameters are centralized here so they can be overridden
per skill via a local config.py or per deployment via environment/config files.

Usage (in skill scripts):
    from trader_shared.config import LOOKBACK_DAYS, RECENT_WINDOW, ...
"""
from __future__ import annotations

LOOKBACK_DAYS: int = 30
RECENT_WINDOW: int = 5
CONFIRM_BUFFER: float = 0.02
STOP_BUFFER: float = 0.98
TAKE_PROFIT_BUFFER: float = 1.06

# ---- structure_core constants -----------------------------------------------
MA_PERIODS: tuple[int, ...] = (5, 10, 20, 30)
MA_WEIGHTS: dict[str, float] = {"ma5": 0.92, "ma10": 0.88, "ma20": 0.65, "ma30": 0.55}
MIN_ZONE_WIDTH_PCT: float = 0.005
MAX_ZONE_WIDTH_PCT: float = 0.012
MIN_STOP_BUFFER_PCT: float = 0.008
MAX_STOP_BUFFER_PCT: float = 0.025
MIN_CONFIRM_SPACE_PCT: float = 0.008
MAX_REASONABLE_MA_DISTANCE_PCT: float = 0.12
STRUCTURE_WINDOW: int = 20

# ---- decision_core constants ------------------------------------------------
DEFENSE_STATUSES = {"防守观察", "防守观察，趋势下行谨慎"}

STATUS_SCORE: dict[str, int] = {
    "低吸观察": 80,
    "等转强": 70,
    "防守观察": 60,
    "冲高减仓": 55,
    "空间不足": 45,
    "暂不碰": 20,
    "数据失败": 0,
}
CHANGE_THRESHOLD_STRONG: float = 3.0
CHANGE_THRESHOLD_LARGE: float = 5.0
CHANGE_THRESHOLD_LARGE_DROP: float = -5.0
CHANGE_THRESHOLD_DROP: float = -7.0
POSITION_RATIO_STRONG: float = 0.60
POSITION_RATIO_CONFIRM: float = 0.72
POSITION_RATIO_HIGH: float = 0.65

# ---- ATR & Livermore constants ----------------------------------------------
ATR_HIGH_THRESHOLD: float = 0.03
ATR_ELEVATED_THRESHOLD: float = 0.02
ATR_NORMAL_THRESHOLD: float = 0.01
PYRAMID_SCALES: dict[int, float] = {0: 0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.85, 5: 1.0}
BASE_WEIGHTS: dict[int, int] = {0: 15, 1: 10, 2: 7, 3: 4}
ATRLV_INDEX: dict[str, int] = {"数据不足": 0, "波幅偏高": 3, "波动偏大": 2, "波动正常": 1, "波动较低": 0}

# ---- Chan Theory (缠论) constants ----
CHANLUN_MIN_BARS: int = 20
CHANLUN_MIN_BARS_PER_STROKE: int = 5

# ---- Market index ----
INDEX_CODE: str = "000852.SH"

# ---- Trend filter constants (long-term MA filter) ----
TREND_MA_SHORT: int = 30
TREND_MA_LONG: int = 900
TREND_FILTER_ENABLED: bool = True  # 默认开启趋势过滤

# ---- Wyckoff constants ----
WYCKOFF_MIN_BARS: int = 15
WYCKOFF_SPRING_SUPPORT_LOOKBACK: int = 10
WYCKOFF_SPRING_RECLAIM_RATIO: float = 0.92
WYCKOFF_SPRING_BULLISH_VOL_RATIO: float = 1.3
WYCKOFF_DIVERGENCE_BARS: int = 5
