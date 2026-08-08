"""T0 运行时配置（自 t0/scripts/t0_config 迁入）。"""
from __future__ import annotations

LOOKBACK_DAYS: int = 120
STRUCTURE_WINDOW: int = 20
MIN_5M_BARS: int = 20
MACD_WARMUP_BARS: int = 35
MIN_TRIGGER_MATCHES: int = 3
STRONG_TRIGGER_MATCHES: int = 5
MIN_T_AMPLITUDE_PCT: float = 0.015
GOOD_T_AMPLITUDE_PCT: float = 0.03
MIN_T_NET_SPACE_PCT: float = 0.003
MIN_SELL_NET_SPACE_PCT: float = 0.004
ZONE_MAX_WIDTH_PCT: float = 0.008
ZONE_AMPLITUDE_FACTOR: float = 0.10
ZONE_MIN_WIDTH_PCT: float = 0.005        # 区间宽度下限，防止低价股区间过窄
DEFAULT_ZONE_WIDTH_PCT: float = 0.005
BUY_CONFIRM_FACTOR: float = 0.998
SELL_CONFIRM_FACTOR: float = 1.002
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
ATR_STOP_FACTOR: float = 0.5            # 止损距离 = 日内 5m ATR × 0.5（handoff §5，非日线 ATR）
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

# ── 日线威科夫阶段词表 → T0 方向（handoff §1：日线定基调）──
# 与 wyckoff_phase._PHASE_ORDER 的 11 个 phase 对齐
ACCUM_PHASES = frozenset({
    "accumulation_a", "accumulation_b", "accumulation_c", "accumulation_d",
    "markup",
})
DIST_PHASES = frozenset({
    "distribution_a", "distribution_b", "distribution_c", "distribution_d",
    "markdown",
})

# ── 关键位信号阈值（handoff §2：关键位 + 量价，单信号即出手）──
VWAP_REGRESSION_DEV_PCT: float = 0.015   # 偏离 VWAP 超过该比例视为回归机会
VWAP_REGRESSION_VOL_RATIO: float = 0.9   # 回归需缩量（量比低于该值）
BREAKOUT_VOL_RATIO: float = 1.5          # 放量突破阈值
FAKE_BREAK_NEAR_PCT: float = 0.003       # 缩量到前高/前低（未破）判定假突破反向的距离
OPEN_RECLAIM_EPS_PCT: float = 0.002      # 站稳/失守开盘价阈值
OPEN_RECLAIM_MIN_BARS: int = 6           # 开盘 30 分钟（6 根 5m bar）后才看开盘价
KEY_SIGNAL_STRONG_QUALITY: bool = True   # AB 信号棒仅 strong 质量才进关键位快速通道
AB_SIGNAL_SCORE_MIN: float = 0.8         # AB 信号棒 score 下限（strong 里更强一档，控频）

# ── 选股前置筛选（handoff §4）──
SKIP_MIN_DAILY_AMPLITUDE: float = 0.03   # 日均振幅 < 3% → 不做（日内没空间）
SKIP_MIN_DAILY_AMOUNT: float = 3e8       # 日均成交额 < 3 亿 → 不做（滑点大）
SKIP_LOOKBACK_DAYS: int = 20             # 日均值回看窗口

