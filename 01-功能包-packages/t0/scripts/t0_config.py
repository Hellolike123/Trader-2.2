from __future__ import annotations

LOOKBACK_DAYS: int = 30
STRUCTURE_WINDOW: int = 20
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
ZONE_MIN_WIDTH_PCT: float = 0.005        # 区间宽度下限，防止低价股区间过窄
DEFAULT_ZONE_WIDTH_PCT: float = 0.005
BUY_CONFIRM_FACTOR: float = 1.002
SELL_CONFIRM_FACTOR: float = 0.998
BUY_ACCEPT_FACTOR: float = 1.003
SELL_ACCEPT_FACTOR: float = 0.997
# 动态滑点：低量比时收窄，高量比时放宽
SLIPPAGE_LOW_VOLUME_RATIO: float = 0.8   # 量比<0.8时用保守因子
SLIPPAGE_HIGH_VOLUME_RATIO: float = 1.5  # 量比>1.5时用激进因子
BUY_ACCEPT_FACTOR_CONSERVATIVE: float = 1.005
BUY_ACCEPT_FACTOR_AGGRESSIVE: float = 1.002
SELL_ACCEPT_FACTOR_CONSERVATIVE: float = 0.995
SELL_ACCEPT_FACTOR_AGGRESSIVE: float = 0.998
INVALID_BELOW_SUPPORT: float = 0.995
INVALID_ABOVE_RESISTANCE: float = 1.005
VOLUME_SHRINK_RATIO: float = 0.8
VOLUME_EXPAND_RATIO: float = 1.2
PRICE_TICK: float = 0.01
ENABLE_ICT_EXECUTION: bool = True
ICT_SWEEP_LOOKBACK: int = 8
ICT_RECENT_WINDOW: int = 6
ICT_STRUCTURE_LOOKBACK: int = 3
ICT_MIN_STRENGTH: str = "medium"         # ICT确认最低强度：weak不计分
ATR_STOP_FACTOR: float = 2.0
ATR_STOP_MIN_PCT: float = 0.005
ATR_STOP_MAX_PCT: float = 0.025
ADX_STRONG_THRESHOLD: float = 25.0
ADX_WEAK_THRESHOLD: float = 20.0

# ── Left-side (aggressive entry) parameters ──
LEFT_TRIGGER_CORE: int = 1                # 1 个核心条件即可触发
LEFT_TRIGGER_AUX: int = 1                 # 1 个辅助条件即可触发
LEFT_NO_SUPPORT_BLOCK: bool = True        # 跌破主支撑不阻断（放量跌破仍阻断）

# ── 趋势过滤器（T0专用，比日线级别更宽松）──
TREND_FILTER_ENABLED: bool = True         # 是否启用趋势过滤
TREND_FILTER_EXTREME_ONLY: bool = True    # True=仅极端下行才阻断；False=任何下行都阻断
TREND_FILTER_DAYS: int = 5               # 短期均线天数
TREND_FILTER_EXTREME_DROP_PCT: float = -0.08  # 极端下行阈值：N日累计跌幅超此值才阻断

# ── Frequency stop limit ──
FREQUENCY_STOP_LIMIT: int = 3             # 当日累计止损次数上限(任一 BUY_INVALIDATED)触发熔断
