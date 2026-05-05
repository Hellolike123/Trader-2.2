"""
Trader 统一数据模型层
定义所有中间数据结构，替代 dict[str, Any] 的随意传递。

约定：
- 所有 TypedDict 的 total=False，因为数据可能部分缺失（行情源降级）
- BarData/QuoteData 等基础类型直接用于数据获取层
- CandidateLevels/CandidateSignal 用于候选逻辑层
- TheoryVerdict 用于复盘层
"""
from __future__ import annotations

from typing import Literal, TypedDict

# ── 从 light_data 引入已定义的类型 ──
# Security, DataStatus, MarketSnapshot 已在 light_data.py 中定义


class BarData(TypedDict, total=False):
    """统一 K 线数据行（可跨周期）"""
    time: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None
    amount: float | None
    tr: float
    tr14: float
    atr7: float
    atr14: float
    atr_ratio: float


class QuoteData(TypedDict, total=False):
    """实时行情快照"""
    name: str
    symbol: str
    trade_date: str
    trade_time: str | None
    current_price: float | None
    pre_close: float | None
    open: float | None
    high: float | None
    low: float | None
    volume: float | None
    amount: float | None
    turnover_rate: float | None
    current_change_pct: float | None


class MAValues(TypedDict, total=False):
    """多周期均线集合"""
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma30: float | None
    ma60: float | None


class CandidateLevels(TypedDict, total=False):
    """候选交易区间与信号
    这是 candidate_core.py 的核心输出，统一各 skill 的字段命名
    """
    # 核心价位
    main_support: float          # 核心支撑
    support: float | None        # 次级支撑
    resistance: float | None     # 关键阻力
    confirm_price: float | None  # 确认价（站稳/突破价）
    hard_stop: float | None      # 止损价
    max_profit: float | None     # 目标止盈价

    # 来源标识
    support_source: str | None       # e.g. "low_5d", "low_20d", "ma10"
    resistance_source: str | None    # e.g. "high_5d", "high_20d", "pivot_61.8"

    # 均线集合
    ma_values: MAValues

    # 空间计算
    support_gap_pct: float | None      # 现价到支撑百分比
    resistance_gap_pct: float | None   # 现价到阻力百分比
    profit_space_pct: float | None     # 支撑到阻力盈亏比空间


class TradeStage(TypedDict):
    """结构阶段分类"""
    stage: Literal["启动", "上升", "回调", "震荡", "下跌", "不确定"]
    reason: str


class SignalDirection(TypedDict):
    """信号方向"""
    direction: Literal["bullish", "bearish", "neutral", "bullish_lean", "bearish_lean"]
    reasoning: str


class VolumeProfile(TypedDict, total=False):
    """量能分析"""
    volume_status: str          # "放量", "缩量", "平均"
    volume_ratio: float | None  # 成交量比（相对近期均值）
    amount_ratio: float | None  # 成交额比


class PriceAction(TypedDict, total=False):
    """价格行为分析"""
    trend_direction: str       # "up", "down", "flat"
    amplitude_pct: float | None
    daily_range_pct: float | None


class TheoryScore(TypedDict, total=False):
    """单一理论打分（复盘用）"""
    theory_name: str
    score: float        # 0-10
    verdict: str        # "符合/违背/待确认"
    details: str


class CandidateSignal(TypedDict):
    """候选信号 —— 候选逻辑层到渲染层的核心数据结构"""
    levels: CandidateLevels
    structure: TradeStage
    momentum: SignalDirection
    volume: VolumeProfile
    support_strength: str          # "强/中/弱"
    key_risks: list[str]
    action: Literal["观察", "买入", "减仓", "清仓", "观望"]
    confidence: float              # 0-100


class TheoryVerdict(TypedDict):
    """理论判断集合（复盘用）"""
    chandelier: TheoryScore | None  # 缠论
    wyckoff: TheoryScore | None     # 威科夫
    chips: TheoryScore | None       # 筹码
    money: TheoryScore | None       # 资金


# ── 信号合同类型 ──

class SignalTrigger(TypedDict, total=False):
    """信号触发信息"""
    price: float | None
    text: str | None
    type: str | None     # "buy", "sell", "observe"
    zone: str | None     # 价格区间描述


class Position(TypedDict):
    """仓位管理"""
    max_total_pct: float | None          # 最大总仓位 %
    max_single_move_pct: float | None    # 单次变动最大 %
    current_action: str | None            # "加仓/减仓/持有/空仓"


class SignalRecord(TypedDict, total=False):
    """信号协议 v1 记录（替代 signal_contract.py 中的 dict 自由组装）"""
    contract: str                   # always "trader_signal_v1"
    source_skill: str               # "trader" | "t0-trader" | ...
    symbol: str                     # ts_code, e.g. "688248.SH"
    name: str                       # 股票名
    trade_date: str                 # yyyy-MM-dd
    analysis_time: str              # ISO timestamp
    signal_type: str                # e.g. "observe", "low_buy_triggered", ...
    direction: str                  # bullsh/bearish/neutral/bullish_lean/bearish_lean
    action: str                     # e.g. "hold_observe", "reduce", ...

    confidence: str                 # "high/medium/low"
    data_status: str                # "full/degraded/partial/insufficient/fresh/stale/non_trading"

    trigger: SignalTrigger
    invalidation: str | None        # 失效条件
    position: Position
    risk_flags: list[str]           # e.g. ["near_resistance", "low_volume"]
    summary: str                    # 一句话总结
    details: str | None             # 补充说明


# ── 数据状态映射 ──

DATA_STATUS_MAP: dict[str, str] = {
    # light_data.DataStatus -> signal_contract 生态
    "complete": "full",
    "partial": "partial",
    "degraded": "degraded",
    "failed": "insufficient",
}


def map_data_status_to_signal(
    raw_status: str,
    is_trading_time: bool = True,
    is_trading_day: bool = True,
) -> str:
    """将 light_data 的 DataStatus 映射为 signal_contract 标准状态"""
    if not is_trading_time:
        return "non_trading"
    return DATA_STATUS_MAP.get(raw_status, "degraded")


class ChanlunSignal(TypedDict, total=False):
    trend_label: str
    buy_point_text: str
    buy_points: list[dict]
    last_valid_zone_last_price: float | None
    last_valid_zone_first_price: float | None
    strokes_count: int
    divergence: dict
    zones_count: int


class WyckoffSignal(TypedDict, total=False):
    spring_signal: bool
    spring_price: float | None
    spring_reason: str
    upthrust_signal: bool
    upthrust_price: float | None
    upthrust_reason: str
    bearish_volume_divergence: bool
    bullish_volume_divergence: bool
    wyckoff_summary: str
