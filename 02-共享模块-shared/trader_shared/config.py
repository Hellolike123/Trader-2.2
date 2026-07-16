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

LOOKBACK_DAYS: int = 370  # 300日历天≈200交易日不够MA250，370天保证≥250个交易日
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

# ---- Chan structure_confidence 门槛（段数只调 conf，不改主状态名）----
# 日线短线：趋势/盘整证据强弱
CHAN_DAILY_TREND_SEGS_HIGH: int = 8
CHAN_DAILY_TREND_SEGS_MID: int = 5
CHAN_DAILY_CONSOL_SEGS_HIGH: int = 5
CHAN_DAILY_CONSOL_SEGS_MID: int = 3
# 周线中线：门槛更低（禁止与日线共用 11 硬失败）
CHAN_WEEKLY_TREND_SEGS_HIGH: int = 5
CHAN_WEEKLY_TREND_SEGS_MID: int = 3
CHAN_WEEKLY_CONSOL_SEGS_HIGH: int = 3
CHAN_WEEKLY_CONSOL_SEGS_MID: int = 2

# ---- Chan Theory enhancement flags (区间套 / 中枢合并 / 信号id) ----
CHAN_MULTILEVEL_ENABLED: bool = True        # 多级别区间套确认（上级趋势过滤买卖点）
CHAN_MULTILEVEL_CHUNK: int = 5              # 粗K线聚合粒度（每 N 根合成一根上级别K线）
CHAN_MULTILEVEL_MIN_BARS: int = 15          # 粗K线最少根数（独立于 CHANLUN_MIN_BARS）
CHAN_ZONE_MERGE_ENABLED: bool = True        # 中枢相邻/重叠合并为 consolidated pivot
CHAN_SEGMENT_RELAX_OVERLAP: bool = True     # 线段启动放宽：取消三笔严格重叠门槛，从首笔起段（一键回退见 chan_core.build_segments）
CHAN_ZONE_MERGE_GAP_PCT: float = 0.015      # 中枢合并的相对间距阈值（按中枢中心价百分比）
CHAN_SIGNAL_ID_ENABLED: bool = True         # 买卖点写入 Signal Contract v2 强一致 signal_id
# 背驰 fallback（峰谷扫描）只扫最近 N 根，杜绝拿几年前的旧背离当现状污染买卖点信号。
# 笔级 MACD 面积背驰才是主路径；此处仅作为“无笔/无 index”时的近期兜底。
CHAN_DIVERGENCE_FALLBACK_WINDOW: int = 120
# P2：首笔从数据起点（无左支点）起算，属悬空不可信笔。按缠论标准丢弃，
# 从第一个完整支点起读。关闭则回退到保留首笔的旧行为。
CHAN_DROP_LEADING_DANGLING_STROKE: bool = True
# P3：背驰检测锚定「最后中枢」而非固定窗口——只比较最后中枢之后的趋势 legs
# （离开段 c 与其次级别同向段），避免把陈旧历史当现状。关闭则回退到 P0b 窗口逻辑。
CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT: bool = True
SIGNAL_RULES_ENABLED: bool = False          # 信号组合规则引擎（YAML 驱动，实验性，默认关闭）

# ---- ChanlunEngine 状态持久化目录（Phase 1 新增）----
CHANLUN_STATE_DIR: str = os.path.expanduser("~/.trader/chanlun_state")

# ---- T0 实时缠论开关（Phase 2 新增，opt-in 默认关）----
# 仅在盘中盯盘 `T0_REALTIME_CHAN=1` 时启用实时缠论增量 diff alert；
# 未设置时 monitor.run_once 走原批量路径，控制流零改动。
T0_REALTIME_CHAN_ENABLED: bool = os.environ.get("T0_REALTIME_CHAN") == "1"

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
WYCKOFF_BC_MIN_POS_PCT: float = 0.65            # BC 须处于近窗价格区间上沿（高位过滤，0=底 1=顶）

# SOW (Sign of Weakness) 弱势信号相关参数
WYCKOFF_SOW_SUPPORT_LOOKBACK: int = 10          # SOW 支撑查找回溯K线数
WYCKOFF_SOW_VOL_RATIO_THRESHOLD: float = 1.2    # SOW 放量判定阈值（恢复原值，收紧假阳性）
WYCKOFF_SOW_CONSECUTIVE_DAYS: int = 2           # SOW 确立连续跌破天数（恢复 2 日确认）

# Spring 弹簧洗盘相关参数
WYCKOFF_SPRING_SUPPORT_LOOKBACK: int = 10       # 弹簧支撑回溯K线数
WYCKOFF_SPRING_RECLAIM_RATIO: float = 0.985     # 刺穿深度比例，跌破 1.5% 即确认（原 0.97）
WYCKOFF_SPRING_ATR_MULTIPLE: float = 0.5        # ATR 动态刺穿深度（0.5 × ATR）
WYCKOFF_SPRING_BULLISH_VOL_RATIO: float = 1.3   # 弹簧放量反弹量比
WYCKOFF_SPRING_LOW_VOL_RATIO: float = 0.8       # 弹簧低量确认阈值（低量 = 供应耗尽，可靠）

# UTAD (Upthrust Action / Upthrust) 上冲回落相关参数
WYCKOFF_UTAD_BREAKOUT_RATIO: float = 1.005      # 假突破幅度，超出阻力 0.5% 即可（原 1.02）
WYCKOFF_UTAD_RECLAIM_RATIO: float = 0.995       # 假突破收回幅度（收回到阻力 99.5% 之下）
WYCKOFF_UT_VOL_RATIO: float = 1.2               # UT 放量确认阈值（派发需放量）

# ---- P0-4 Spring/Upthrust 真假分级 (Strength Grading) ----
# 分级三维：刺穿深度(%) / 量能比(vs TR基线量) / 收回收盘位置(相对TR中轴)
WYCKOFF_SPRING_STRONG_DEPTH_PCT: float = 2.5    # 深度刺穿阈值(%) → strong spring（>2.5% 才 strong，1.5%~2.5% 归 ordinary，因刺穿线本身即 1.5%）
WYCKOFF_SPRING_WEAK_DEPTH_PCT: float = 0.5      # 浅刺穿阈值(%) → weak spring
WYCKOFF_SPRING_STRONG_RECLAIM: float = 1.0      # 收回到TR中轴以上比例 → strong
WYCKOFF_UT_STRONG_DEPTH_PCT: float = 0.5        # UT 深度突破阈值(%) → strong
WYCKOFF_UT_WEAK_DEPTH_PCT: float = 0.1          # UT 浅突破阈值(%) → weak
WYCKOFF_UT_STRONG_RECLAIM: float = 1.0          # UT 跌回TR中轴以下比例 → strong

# ---- P0-5 事件簇确认 (Event Cluster Confirmation) ----
# 将孤立信号升级为可信的积累/派发事件簇：支撑测试(Spring/ST)→SOS 确认吸筹；
# 上冲(Upthrust)→SOW 确认派发；并校验事件先后顺序 + 用 P0-4 strength 定级。
WYCKOFF_CLUSTER_LOOKBACK: int = 60           # 事件簇扫描回溯窗口（与阶段机同量级）
WYCKOFF_CLUSTER_MIN_GAP: int = 5             # 支撑测试与 SOS 的最小间隔根数（防同根棒误判顺序）

# Wyckoff 阶段状态机
WYCKOFF_PHASE_LOOKBACK: int = 60                # 阶段序列回溯窗口（约 3 个月）

# VSA (Volume Spread Analysis) 量价幅度分析
WYCKOFF_VSA_AVG_SPREAD_PERIOD: int = 20         # VSA 平均波幅计算周期

# Divergence 量价背离相关参数
WYCKOFF_DIVERGENCE_BARS: int = 5                # 背离比对K线窗口
WYCKOFF_DIVERGENCE_RATIO: float = 0.85          # 背离量能萎缩比例由 80% 放宽至 85%

# Compression 压缩蓄势参数
WYCKOFF_COMPRESSION_LOOKBACK: int = 20          # 压缩检测回溯窗口
WYCKOFF_COMPRESSION_ATR_QUANTILE: float = 0.20  # ATR 分位数阈值（低于此值 = 压缩）
WYCKOFF_COMPRESSION_VOL_RATIO: float = 0.60     # 量能萎缩比例（近N日/参考窗口）
WYCKOFF_COMPRESSION_VOL_REF_WINDOW: int = 60    # 量能参考窗口

# Trend Pullback 趋势回踩参数
WYCKOFF_TREND_PB_LOOKBACK: int = 10             # 回踩检测回溯窗口
WYCKOFF_TREND_PB_MIN_PULLBACK: float = 5.0     # 最小回撤幅度 %
WYCKOFF_TREND_PB_MAX_PULLBACK: float = 20.0    # 最大回撤幅度 %
WYCKOFF_TREND_PB_VOL_SHRINK: float = 0.60      # 回落段缩量比例
WYCKOFF_TREND_PB_MA_WINDOW: int = 20           # 均线窗口

# ---- Wyckoff Score 独立打分权重常量（均衡型） ----
# 基准分数 0（raw=0 → score=50），各信号权重可正可负
# 原始权重理论最大绝对值 = 25+5+10+20+10+15+10+10+15+8+12 = 130
# 新增: AR(+10) SOS(+15) ST(+8) LPS(+12)；看空额外 -20
# 归一化分母取 130，留一定余量（P1-2 修复，之前 95 被新增权重饱和）
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
WYCKOFF_SCORE_LPSY: int = -12                    # Last Point of Supply 最后供应 — 反弹不过前高缩量
WYCKOFF_SCORE_COMPRESSION: int = 10              # Compression 压缩蓄势 — 振幅收窄+量能枯竭
WYCKOFF_SCORE_TREND_PB: int = 8                  # Trend Pullback 趋势回踩 — 回踩不破均线
# 原典补齐：PS/PSY/BU/UTAD（弱于主事件，避免淹没 Spring/SOS）
WYCKOFF_SCORE_PS: int = 8                       # Preliminary Support 初步止跌
WYCKOFF_SCORE_PSY: int = -8                     # Preliminary Supply 初步供应
WYCKOFF_SCORE_BU: int = 12                      # Backup 备份买（SOS 后缩量回踩）
WYCKOFF_SCORE_UTAD: int = -18                   # UTAD 派发末上冲（强于普通 UT）
# P0-5 事件簇确认打分权重（顺序确认的簇比孤立信号更可靠 → 池/复盘分）
WYCKOFF_SCORE_CLUSTER_CONFIRM: int = 15         # 积累确认(Spring→SOS 顺序) 额外加分
WYCKOFF_SCORE_CLUSTER_DISTRIB: int = -15        # 派发确认(Upthrust→SOW 顺序) 额外扣分
WYCKOFF_SCORE_CLUSTER_FAIL: int = -20           # 积累失败(Spring→SOW) 假突破实为派发，强看空
WYCKOFF_SCORE_MAX_ABS: int = 140                # 归一化分母（含 PS/BU/UTAD 后略抬）
# 五阶段机原典串联：Spring/Upthrust 必须在 Phase B（停止后建仓区）之后才有效。
# 孤立/早于 B 阶段的 Spring/UT 判为噪声（降权）：相位维持中性、打分减半。
WYCKOFF_PHASE_PREMATURE_SPRING_PENALTY: float = 0.0   # 过早 Spring 相位修正（噪声=中性，降权在 score 层做）
WYCKOFF_PHASE_PREMATURE_UT_PENALTY: float = 0.0       # 过早 UT 相位修正（噪声=中性，降权在 score 层做）
WYCKOFF_SCORE_PREMATURE_HALF: bool = True             # 过早信号打分减半开关

# ---- P0-3 Trading Range (TR) 识别层 ----
# 原典：TR 是吸筹/派发的「容器」，价格在区间内反复震荡、上下沿清晰、持续足够时长。
# 因果律：TR 越宽/越长，后续行情越大。以下常量驱动 _detect_trading_range。
WYCKOFF_TR_LOOKBACK: int = 120                  # TR 识别最大回溯根数（约半年日线）
WYCKOFF_TR_MIN_WIDTH: int = 20                  # TR 最小宽度（根数），过窄视为噪声非 TR
WYCKOFF_TR_AMPLITUDE_MAX: float = 30.0          # TR 最大振幅 %，超过即判定已进入趋势段，停止回溯
WYCKOFF_TR_AMPLITUDE_MIN: float = 6.0           # TR 最小振幅 %，过窄视为无意义的窄幅噪声
WYCKOFF_TR_QUALITY_WIDTH_REF: int = 60          # TR 质量评分的宽度参考（width/该值，封顶 1.0）
# TR 上下沿用「反复测试的清晰边界」而非绝对极值：取区间内 low/high 的分位带，
# 排除 Spring/Upthrust 的刺穿毛刺（原典：刺穿是事件，不是边界本身）。
WYCKOFF_TR_FLOOR_PCT: float = 0.15              # 下沿 = 区间 low 的 15 分位（过滤最深 ~15% 刺穿）
WYCKOFF_TR_CEIL_PCT: float = 0.85               # 上沿 = 区间 high 的 85 分位（过滤最高 ~15% 刺穿）
# ① TR 质量接打分：tr_quality(0~1) 越高=TR 越干净，信号越可信；越低=越像噪声，向中性回拉。
# 调整量 = (tr_quality - 中性点) * 2 * GAIN，封顶 ±GAIN。无 TR(tr_quality=None)不调整。
WYCKOFF_TR_QUALITY_NEUTRAL: float = 0.5         # tr_quality 中性点：高于此视为干净 TR，低于此视为可疑
WYCKOFF_SCORE_TR_QUALITY_GAIN: int = 20         # TR 质量对 raw 分的最大调整幅度（quality=1→+20，quality=0→-20）

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

# ---- 短中线报告 + Mistery 门控（2026-07-10）---------------------------------
# SHORT_MIDLINE_REPORT=true（默认）使用新模板；设 false/0 回退旧 render_single 模板
SHORT_MIDLINE_REPORT: bool = os.environ.get("SHORT_MIDLINE_REPORT", "true").lower() in ("true", "1", "yes")
# Mistery H5 盈亏比下限（reward_near >= min_rr * risk）；默认 1.0 与 subset「目标≤止损」一致
MISTERY_MIN_RR: float = float(os.environ.get("MISTERY_MIN_RR", "1.0"))

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

# ---- 展示指标阈值（display_indicators.py 消费，可通过 env 覆盖）-----------------
# VWAP 偏离度分级：低于 -1.5% 视为机构被套；高于 +1.5% 视为机构大幅盈利
VWAP_DEVIATION_BELOW_TRAPPED: float = float(os.environ.get("VWAP_DEVIATION_BELOW_TRAPPED", "-0.015"))
VWAP_DEVIATION_ABOVE_PROFIT: float = float(os.environ.get("VWAP_DEVIATION_ABOVE_PROFIT", "0.015"))
# Supertrend 参数（与 indicator_math.calc_supertrend 保持一致）
SUPERTREND_MULTIPLIER: float = float(os.environ.get("SUPERTREND_MULTIPLIER", "3.0"))
# ATR 通用周期（indicator_math.calc_atr_series、calc_supertrend 默认值）
ATR_PERIOD: int = int(os.environ.get("ATR_PERIOD", "14"))

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
    "WYCKOFF_BC_UPPER_SHADOW_RATIO", "WYCKOFF_BC_MIN_POS_PCT",
    "WYCKOFF_SOW_SUPPORT_LOOKBACK",
    "WYCKOFF_SOW_VOL_RATIO_THRESHOLD", "WYCKOFF_SOW_CONSECUTIVE_DAYS",
    "WYCKOFF_SPRING_SUPPORT_LOOKBACK", "WYCKOFF_UTAD_BREAKOUT_RATIO",
    "WYCKOFF_UTAD_RECLAIM_RATIO", "WYCKOFF_DIVERGENCE_RATIO",
    # P0-4 Spring/Upthrust 真假分级常量
    "WYCKOFF_SPRING_STRONG_DEPTH_PCT", "WYCKOFF_SPRING_WEAK_DEPTH_PCT", "WYCKOFF_SPRING_STRONG_RECLAIM",
    "WYCKOFF_UT_STRONG_DEPTH_PCT", "WYCKOFF_UT_WEAK_DEPTH_PCT", "WYCKOFF_UT_STRONG_RECLAIM",
    # P0-5 事件簇确认常量
    "WYCKOFF_CLUSTER_LOOKBACK", "WYCKOFF_CLUSTER_MIN_GAP",
    # 五阶段机原典串联：过早信号惩罚
    "WYCKOFF_PHASE_PREMATURE_SPRING_PENALTY", "WYCKOFF_PHASE_PREMATURE_UT_PENALTY",
    "WYCKOFF_SCORE_PREMATURE_HALF",
    # Wyckoff Score constants
    "WYCKOFF_SCORE_SPRING", "WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS",
    "WYCKOFF_SCORE_BULLISH_DIV", "WYCKOFF_SCORE_UT",
    "WYCKOFF_SCORE_BEARISH_DIV", "WYCKOFF_SCORE_BC",
    "WYCKOFF_SCORE_SOW", "WYCKOFF_SCORE_MAX_ABS",
    # 新增经典信号权重
    "WYCKOFF_SCORE_AR", "WYCKOFF_SCORE_SOS",
    "WYCKOFF_SCORE_ST", "WYCKOFF_SCORE_LPS", "WYCKOFF_SCORE_LPSY",
    "WYCKOFF_SCORE_COMPRESSION", "WYCKOFF_SCORE_TREND_PB",
    "WYCKOFF_SCORE_PS", "WYCKOFF_SCORE_PSY", "WYCKOFF_SCORE_BU", "WYCKOFF_SCORE_UTAD",
    "WYCKOFF_SCORE_CLUSTER_CONFIRM", "WYCKOFF_SCORE_CLUSTER_DISTRIB", "WYCKOFF_SCORE_CLUSTER_FAIL",
    # ① TR 质量接打分
    "WYCKOFF_TR_QUALITY_NEUTRAL", "WYCKOFF_SCORE_TR_QUALITY_GAIN",
    "WYCKOFF_COMPRESSION_LOOKBACK", "WYCKOFF_COMPRESSION_ATR_QUANTILE",
    "WYCKOFF_COMPRESSION_VOL_RATIO", "WYCKOFF_COMPRESSION_VOL_REF_WINDOW",
    "WYCKOFF_TREND_PB_LOOKBACK", "WYCKOFF_TREND_PB_MIN_PULLBACK",
    "WYCKOFF_TREND_PB_MAX_PULLBACK", "WYCKOFF_TREND_PB_VOL_SHRINK",
    "WYCKOFF_TREND_PB_MA_WINDOW",
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
    # 展示指标阈值
    "VWAP_DEVIATION_BELOW_TRAPPED", "VWAP_DEVIATION_ABOVE_PROFIT",
    "SUPERTREND_MULTIPLIER", "ATR_PERIOD",
]
