"""Shared constants common to all trader skills.

All calculation parameters are centralized here so they can be overridden
per skill via a local config.py or per deployment via environment/config files.

Usage (in skill scripts):
    from trader_shared.config import LOOKBACK_DAYS, RECENT_WINDOW, ...

WARNING: These values should NOT be mutated at runtime. They are constants.
Use environment variables or per-skill config.py for overrides.
"""
from __future__ import annotations

import os

LOOKBACK_DAYS: int = 300  # 250日均线需要至少300根日K线
RECENT_WINDOW: int = 5
CONFIRM_BUFFER: float = 0.02
STOP_BUFFER: float = 0.98
TAKE_PROFIT_BUFFER: float = 1.06

# ---- structure_core constants -----------------------------------------------
MA_PERIODS: tuple[int, ...] = (5, 10, 20, 30)
MA_WEIGHTS: dict[str, float] = {"ma5": 0.92, "ma10": 0.88, "ma20": 0.65, "ma30": 0.55}
MIN_ZONE_WIDTH_PCT: float = 0.005
MAX_ZONE_WIDTH_PCT: float = 0.020    # 放宽至2.0%（原1.2%），高波幅票低吸区不再被过度截断
MIN_STOP_BUFFER_PCT: float = 0.008
MAX_STOP_BUFFER_PCT: float = 0.025
MIN_CONFIRM_SPACE_PCT: float = 0.005  # 缩至0.5%（原0.8%），突破阻力位后更易触及确认价
MAX_REASONABLE_MA_DISTANCE_PCT: float = 0.12
STRUCTURE_WINDOW: int = 20

# ---- Stop-loss upgrade (P0) ----
ENABLE_TRAILING_STOP: bool = True       # 启用 ATR 移动止损
TRAILING_STOP_ATR_MULTIPLE: float = 3.0 # 移动止损跟随最高价，回撤 3 倍 ATR 触发
PULLBACK_CONFIRM_DAYS: int = 3          # 跌破支撑后 N 日内收回不算真破位
EXIT_PHASED_ENABLED: bool = True        # 分阶段退出：先减仓观察，再清仓

# ---- decision_core constants ------------------------------------------------
DEFENSE_STATUSES = {"防守观察", "防守观察，趋势下行谨慎"}

STATUS_SCORE: dict[str, int] = {
    "突破确认": 85,
    "突破观察": 75,
    "体系转强确认": 88,
    "未确认转强": 72,
    "转强不足": 62,
    "承接存在": 68,
    "修复观察": 65,
    "低吸观察": 80,
    "等转强": 70,
    "防守观察": 60,
    "防守观察，趋势下行谨慎": 50,
    "冲高减仓": 55,
    "空间不足": 30,  # 低于"防守观察"(60)，表示"空间不足+均线不配合"比纯防守观察更消极
    "暂不碰": 20,
    "数据失败": 0,
}
CHANGE_THRESHOLD_STRONG: float = 3.0
CHANGE_THRESHOLD_LARGE: float = 5.0
CHANGE_THRESHOLD_LARGE_DROP: float = -5.0
CHANGE_THRESHOLD_DROP: float = -7.0
HARD_STOP_SINGLE_DAY_DROP: float = -0.07  # P0-2: 单日跌幅超 7% 硬性熔断，跳过假跌破逻辑
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
CHANLUN_MIN_STROKES_PER_SEGMENT: int = 3   # 线段最少笔数

# ---- Chan Theory enhancement flags (区间套 / 中枢合并 / 信号id) ----
CHAN_MULTILEVEL_ENABLED: bool = True        # 多级别区间套确认（上级趋势过滤买卖点）
CHAN_MULTILEVEL_CHUNK: int = 5              # 粗K线聚合粒度（每 N 根合成一根上级别K线）
CHAN_MULTILEVEL_MIN_BARS: int = 15          # 粗K线最少根数（独立于 CHANLUN_MIN_BARS）
CHAN_ZONE_MERGE_ENABLED: bool = True        # 中枢相邻/重叠合并为 consolidated pivot
CHAN_ZONE_MERGE_GAP_PCT: float = 0.015      # 中枢合并的相对间距阈值（按中枢中心价百分比）
CHAN_SIGNAL_ID_ENABLED: bool = True         # 买卖点写入 Signal Contract v2 强一致 signal_id
SIGNAL_RULES_ENABLED: bool = False          # 信号组合规则引擎（YAML 驱动，实验性，默认关闭）

# ---- Market index ----
INDEX_CODE: str = "000852.SH"

# ---- Trend filter constants (long-term MA filter) ----
TREND_MA_SHORT: int = 30
TREND_MA_LONG: int = 250  # 年线，中长线生死线
TREND_FILTER_ENABLED: bool = True  # 默认开启趋势过滤
TREND_MA_LOOKBACK: int = 300  # 至少取 300 天数据才能算出可靠的 MA250

# ---- Wyckoff constants ----
# ⚠️ WYCKOFF_SPRING_RECLAIM_RATIO 每年年底需检查是否需要更新
WYCKOFF_MIN_BARS: int = 15

# BC (Buying Climax) 购买高潮相关参数
WYCKOFF_BC_VOL_RATIO_THRESHOLD: float = 1.8     # BC 购买高潮量比阈值（原 2.0，方案 B 调至 1.8）
WYCKOFF_BC_CHANGE_THRESHOLD: float = 1.0        # BC 滞涨涨幅门槛 (%)
WYCKOFF_BC_UPPER_SHADOW_RATIO: float = 0.02     # BC 上影线占波幅比例

# SOW (Sign of Weakness) 弱势信号相关参数
WYCKOFF_SOW_SUPPORT_LOOKBACK: int = 10          # SOW 支撑查找回溯K线数
WYCKOFF_SOW_VOL_RATIO_THRESHOLD: float = 1.0    # SOW 放量判定阈值（由 1.2 降为 1.0）
WYCKOFF_SOW_CONSECUTIVE_DAYS: int = 1           # SOW 确立连续跌破天数（由 2 降为 1，即单日确认）

# Spring 弹簧洗盘相关参数
WYCKOFF_SPRING_SUPPORT_LOOKBACK: int = 10       # 弹簧支撑回溯K线数
WYCKOFF_SPRING_RECLAIM_RATIO: float = 0.985     # 刺穿深度比例，跌破 1.5% 即确认（原 0.97）
WYCKOFF_SPRING_ATR_MULTIPLE: float = 0.5        # ATR 动态刺穿深度（0.5 × ATR）
WYCKOFF_SPRING_BULLISH_VOL_RATIO: float = 1.3   # 弹簧放量反弹量比

# UTAD (Upthrust Action / Upthrust) 上冲回落相关参数
WYCKOFF_UTAD_BREAKOUT_RATIO: float = 1.005      # 假突破幅度，超出阻力 0.5% 即可（原 1.02）
WYCKOFF_UTAD_RECLAIM_RATIO: float = 0.995       # 假突破收回幅度（收回到阻力 99.5% 之下）

# Divergence 量价背离相关参数
WYCKOFF_DIVERGENCE_BARS: int = 5                # 背离比对K线窗口
WYCKOFF_DIVERGENCE_RATIO: float = 0.85          # 背离量能萎缩比例由 80% 放宽至 85%

# ---- Wyckoff Score 独立打分权重常量（均衡型） ----
# 基准分数 0（raw=0 → score=50），各信号权重可正可负
# 原始权重理论最大绝对值 = 25+5+10+20+10+15+10+10+15+8+12 = 130
# 新增: AR(+10) SOS(+15) ST(+8) LPS(+12)；看空额外 -20
# 归一化分母取 95，留一定余量
WYCKOFF_SCORE_SPRING: int = 25                  # Spring 弹簧洗盘 — 最强看多信号
WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS: int = 5 # Spring + 看多背离 — 额外加分
WYCKOFF_SCORE_BULLISH_DIV: int = 10             # 看多量价背离 — 量能萎缩支撑止跌
WYCKOFF_SCORE_UT: int = -20                     # Upthrust 上冲回落 — 假突破派发
WYCKOFF_SCORE_BEARISH_DIV: int = -10            # 看空量价背离 — 量能萎缩见顶
WYCKOFF_SCORE_BC: int = -15                     # Buying Climax 购买高潮 — 天量滞涨
WYCKOFF_SCORE_SOW: int = -10                    # Sign of Weakness 弱势信号 — 放量跌破
# 新增经典威科夫信号权重
WYCKOFF_SCORE_AR: int = 10                      # Automatic Rally 自动反弹 — BC 后放量反弹
WYCKOFF_SCORE_SOS: int = 15                     # Sign of Strength 强势信号 — 连续放量突破
WYCKOFF_SCORE_ST: int = 8                       # Secondary Test 二次测试 — 缩量确认支撑
WYCKOFF_SCORE_LPS: int = 12                     # Last Point of Support 最后支撑 — SOS 后缩量回调
WYCKOFF_SCORE_MAX_ABS: int = 95                 # 归一化分母，raw 映射到 [-50, +50]

# ---- P3 Theory Adjustment ----
# THEORY_ADJUST_LOG_ONLY=true 时理论微调只记录日志不实际生效，用于首次上线观察
THEORY_ADJUST_LOG_ONLY: bool = os.environ.get("THEORY_ADJUST_LOG_ONLY", "false").lower() in ("true", "1", "yes")

# ---- S-2 Fusion Override (Phase 2) ----
# FUSION_OVERRIDE_ENABLED=true 时融合层覆盖 status_for() 的决策，默认开启
# 验证几个股票没问题后改为 False 即可关闭
FUSION_OVERRIDE_ENABLED: bool = os.environ.get("FUSION_OVERRIDE_ENABLED", "true").lower() in ("true", "1", "yes")
# 融合层置信度低于此值时降级回旧逻辑（0-1，建议 0.6）
FUSION_CONFIDENCE_THRESHOLD: float = float(os.environ.get("FUSION_CONFIDENCE_THRESHOLD", "0.6"))

# ---- Portfolio constants -----------------------------------------------------
DEFAULT_MAX_TOTAL: int = 80      # 总仓位上限 (%)
DEFAULT_CASH_FLOOR: int = 20     # 现金下限 (%)
DEFAULT_MAIN_CAP: int = 50       # 主仓上限 (%)

# ---- Portfolio Correlation (P2-1) -------------------------------------------
CORRELATION_THRESHOLD: float = 0.7         # 相关系数超过此值视为同一风险暴露
CORRELATION_LOOKBACK_DAYS: int = 20        # 相关性计算的收盘价回溯天数

# ---- Exit Strategy constants ------------------------------------------------
# 状态机 5 状态
POSITION_STATE_EMPTY: int = 0           # 空仓
POSITION_STATE_INIT: int = 1            # 初始建仓
POSITION_STATE_RESISTANCE: int = 2      # 阻力位分歧
POSITION_STATE_PULLBACK_ADD: int = 3    # 回踩加仓
POSITION_STATE_MARKUP: int = 4          # 主升浪跟踪
POSITION_STATE_EXIT_REENTRY: int = 5    # 退出再买

# 回踩加仓条件评分阈值
PULLBACK_ADD_MIN_SCORE: int = 3         # 最低加仓评分（3/5）
PULLBACK_ADD_FULL_SCORE: int = 5        # 满分加仓评分（5/5）

# 回踩加仓仓位
PULLBACK_ADD_POSITION_PCT: int = 10     # 满足最低条件加仓 10%
PULLBACK_ADD_FULL_POSITION_PCT: int = 15  # 满分条件加仓 15%

# 初始建仓仓位
INITIAL_POSITION_PCT: int = 10          # 初始建仓 10%

# 冲高减仓条件评分阈值
RALLY_REDUCE_MIN_SCORE: int = 3         # 最低减仓评分（3/5）
RALLY_REDUCE_FULL_SCORE: int = 5        # 满分减仓评分（5/5）

# 冲高减仓仓位（占当前仓位百分比，负数表示减仓）
RALLY_REDUCE_POSITION_PCT: int = -15    # 满分条件减仓 15%
RALLY_REDUCE_LITE_POSITION_PCT: int = -10  # 最低条件减仓 10%

# 置信度映射默认值（未校准时使用，校准后从 calibrated_params.json 覆盖）
CONFIDENCE_MAPPING_DEFAULTS: dict[str, float] = {
    "conf_extreme": 0.80,   # 极端信号置信度
    "conf_strong": 0.60,    # 强信号置信度
    "conf_medium": 0.50,    # 中等信号置信度
    "conf_floor": 0.20,     # 灰区最低置信度
    "high_extreme": 75,     # 极端看多分数阈值
    "high_strong": 65,      # 强看多分数阈值
    "low_extreme": 25,      # 极端看空分数阈值
    "low_strong": 35,       # 强看空分数阈值
}

# 条件止盈比例
EXIT_RATIO_BC: float = 0.33            # BC 信号减仓 1/3
EXIT_RATIO_1R: float = 0.33            # 1R 目标减仓 1/3
EXIT_RATIO_STAGE: float = 0.34         # 阶段变化清仓

# EXPMA 周期
EXPMA_FAST_PERIOD: int = 10            # 快速 EXPMA
EXPMA_SLOW_PERIOD: int = 20            # 慢速 EXPMA（替代 MA20 做移动止损）
EXPMA_TREND_FAST: int = 12             # 趋势确认快速线
EXPMA_TREND_SLOW: int = 50             # 趋势确认慢速线

# 时间止损天数限制
ACCUMULATION_DAYS_LIMIT: int = 30   # 蓄势期买入：30天不突破 → 走人
MARKUP_DAYS_LIMIT: int = 15         # 主升期买入：15天不创新高 → 减仓

# 筹码搬家阈值
CHIP_MIGRATION_WARNING_PCT: float = 40.0   # 筹码松动警告阈值
CHIP_MIGRATION_CRITICAL_PCT: float = 50.0  # 筹码搬家清仓阈值

# ---- Risk/Reward filter constants -------------------------------------------
ENABLE_RISK_REWARD_FILTER: bool = os.environ.get("ENABLE_RISK_REWARD_FILTER", "true").lower() in ("true", "1", "yes")
# 盈亏比最低阈值（按 market_env level 分场景）
RISK_REWARD_THRESHOLDS: dict[str, float] = {
    "正常": 2.0,    # 市场环境健康/偏多，要求较高盈亏比
    "偏弱": 1.5,    # 市场环境震荡/一般，中等盈亏比要求
    "很差": 1.2,    # 市场弱势/熊市，放宽盈亏比要求
}

# ---- T0 trade constants ----------------------------------------------------
T0_MIN_SPACE_PCT: float = 1.5  # T0 最小操作空间百分比（现价与确认位的间距下限）

# ---- Kelly position sizing constants ----------------------------------------
KELLY_MAX_TOTAL_POSITIONS: int = 10       # Kelly 公式中的总仓位上限（最大持仓数）
KELLY_MIN_TRADES: int = 10                # Kelly 计算所需的最小成交信号数

# ---- Big Order (大单) constants -----------------------------------------------
MIN_BIG_ORDER_HANDS: float = 2000.0         # 大单绝对阈值（手）
MIN_BIG_ORDER_AMOUNT_WAN: float = 300.0     # 大单绝对阈值（万元）
BIG_ORDER_HANDS_RATIO: float = 0.9          # P1-1: 动态比例阈值（20日最大成交量的 90%）

# ---- 大单连续流出一票否决 (P1-2) ------------------------------------------------
FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS: int = 3     # 连续流出天数阈值
FUND_FLOW_OUTFLOW_VETO_WAN: float = 500.0       # 每日主力净流出阈值（万元）

# ── Exports ──────────────────────────────────────────────────────────
__all__ = [
    "LOOKBACK_DAYS", "RECENT_WINDOW", "CONFIRM_BUFFER", "STOP_BUFFER", "TAKE_PROFIT_BUFFER",
    "MA_PERIODS", "MA_WEIGHTS", "MIN_ZONE_WIDTH_PCT", "MAX_ZONE_WIDTH_PCT",
    "MIN_STOP_BUFFER_PCT", "MAX_STOP_BUFFER_PCT", "MIN_CONFIRM_SPACE_PCT",
    "MAX_REASONABLE_MA_DISTANCE_PCT", "STRUCTURE_WINDOW",
    "ENABLE_TRAILING_STOP", "TRAILING_STOP_ATR_MULTIPLE",
    "PULLBACK_CONFIRM_DAYS", "EXIT_PHASED_ENABLED",
    "DEFENSE_STATUSES", "STATUS_SCORE",
    "CHANGE_THRESHOLD_STRONG", "CHANGE_THRESHOLD_LARGE",
    "CHANGE_THRESHOLD_LARGE_DROP", "CHANGE_THRESHOLD_DROP",
    "HARD_STOP_SINGLE_DAY_DROP",
    "POSITION_RATIO_STRONG", "POSITION_RATIO_CONFIRM", "POSITION_RATIO_HIGH",
    "ATR_HIGH_THRESHOLD", "ATR_ELEVATED_THRESHOLD", "ATR_NORMAL_THRESHOLD",
    "PYRAMID_SCALES", "BASE_WEIGHTS", "ATRLV_INDEX",
    "CHANLUN_MIN_BARS", "CHANLUN_MIN_BARS_PER_STROKE", "CHANLUN_MIN_STROKES_PER_SEGMENT",
    "INDEX_CODE",
    "TREND_MA_SHORT", "TREND_MA_LONG", "TREND_FILTER_ENABLED", "TREND_MA_LOOKBACK",
    "WYCKOFF_MIN_BARS", "WYCKOFF_SPRING_SUPPORT_LOOKBACK",
    "WYCKOFF_SPRING_RECLAIM_RATIO", "WYCKOFF_SPRING_ATR_MULTIPLE", "WYCKOFF_SPRING_BULLISH_VOL_RATIO",
    "WYCKOFF_DIVERGENCE_BARS",
    "WYCKOFF_BC_VOL_RATIO_THRESHOLD", "WYCKOFF_BC_CHANGE_THRESHOLD",
    "WYCKOFF_BC_UPPER_SHADOW_RATIO", "WYCKOFF_SOW_SUPPORT_LOOKBACK",
    "WYCKOFF_SOW_VOL_RATIO_THRESHOLD", "WYCKOFF_SOW_CONSECUTIVE_DAYS",
    "WYCKOFF_SPRING_SUPPORT_LOOKBACK", "WYCKOFF_UTAD_BREAKOUT_RATIO",
    "WYCKOFF_UTAD_RECLAIM_RATIO", "WYCKOFF_DIVERGENCE_RATIO",
    # Wyckoff Score constants
    "WYCKOFF_SCORE_SPRING", "WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS",
    "WYCKOFF_SCORE_BULLISH_DIV", "WYCKOFF_SCORE_UT",
    "WYCKOFF_SCORE_BEARISH_DIV", "WYCKOFF_SCORE_BC",
    "WYCKOFF_SCORE_SOW", "WYCKOFF_SCORE_MAX_ABS",
    # 新增经典信号权重
    "WYCKOFF_SCORE_AR", "WYCKOFF_SCORE_SOS",
    "WYCKOFF_SCORE_ST", "WYCKOFF_SCORE_LPS",
    "THEORY_ADJUST_LOG_ONLY",
    "FUSION_OVERRIDE_ENABLED", "FUSION_CONFIDENCE_THRESHOLD",
    "DEFAULT_MAX_TOTAL", "DEFAULT_CASH_FLOOR", "DEFAULT_MAIN_CAP",
    # Exit Strategy constants
    "POSITION_STATE_EMPTY", "POSITION_STATE_INIT", "POSITION_STATE_RESISTANCE",
    "POSITION_STATE_PULLBACK_ADD", "POSITION_STATE_MARKUP", "POSITION_STATE_EXIT_REENTRY",
    "PULLBACK_ADD_MIN_SCORE", "PULLBACK_ADD_FULL_SCORE",
    "PULLBACK_ADD_POSITION_PCT", "PULLBACK_ADD_FULL_POSITION_PCT",
    "INITIAL_POSITION_PCT",
    "EXIT_RATIO_BC", "EXIT_RATIO_1R", "EXIT_RATIO_STAGE",
    "EXPMA_FAST_PERIOD", "EXPMA_SLOW_PERIOD", "EXPMA_TREND_FAST", "EXPMA_TREND_SLOW",
    "ACCUMULATION_DAYS_LIMIT", "MARKUP_DAYS_LIMIT",
    "CHIP_MIGRATION_WARNING_PCT", "CHIP_MIGRATION_CRITICAL_PCT",
    "ENABLE_RISK_REWARD_FILTER", "RISK_REWARD_THRESHOLDS",
    "KELLY_MAX_TOTAL_POSITIONS", "KELLY_MIN_TRADES",
    "T0_MIN_SPACE_PCT",
    "MIN_BIG_ORDER_HANDS", "MIN_BIG_ORDER_AMOUNT_WAN", "BIG_ORDER_HANDS_RATIO",
    "FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS", "FUND_FLOW_OUTFLOW_VETO_WAN",
    "CORRELATION_THRESHOLD", "CORRELATION_LOOKBACK_DAYS",
]
