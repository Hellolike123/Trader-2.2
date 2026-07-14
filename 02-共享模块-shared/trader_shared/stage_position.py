"""Position evaluation + scoring + take-profit."""
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

POSITION_STATES = {
    "空仓": 0,
    "初始建仓": 1,
    "阻力位分歧": 2,
    "回踩加仓": 3,
    "主升浪跟踪": 4,
    "退出再买": 5,
}

def evaluate_position_state(
    current_price: float,
    support: float,
    resistance: float,
    stop_price: float,
    confirm_price: float,
    atr14: float,
    major_stage: str,
    momentum: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    holding_days: int = 0,
    has_position: bool = False,
    entry_price: float = 0.0,
    highest_close: float = 0.0,
    expma10: float | None = None,
    chip_migration: dict[str, Any] | None = None,
    high_zone_lower: float = 0.0,
    trailing_stop: float | None = None,
    last_add_date: str | None = None,
) -> dict[str, Any]:
    """五状态仓位管理状态机。

    状态流转：
      空仓 → 初始建仓（支撑位买 10%，止损支撑位-1.5×ATR）
      初始建仓 → 阻力位分歧（到达阻力位，弱→卖1/3，强→不卖）
      初始建仓 → 回踩加仓（回踩支撑位，条件满足加仓）
      阻力位分歧 → 回踩加仓（回踩后条件满足）
      回踩加仓 → 主升浪跟踪（筹码没搬家+EXPMA(10)上→拿着）
      主升浪跟踪 → 退出再买（跌破止损/阶段转衰退）
      退出再买 → 初始建仓（回到支撑位+止跌信号+阶段没变）

    Returns:
        {
            "state": str,               # 当前状态
            "state_code": int,          # 状态代码 0-5
            "action": str,              # 建议动作
            "position_pct": int,        # 建议仓位 %
            "stop_price": float,        # 止损价
            "take_profit_price": float, # 止盈价（条件止盈）
            "conditions": dict,         # 各条件检查结果
            "transition_reason": str,   # 状态转移原因
        }
    """
    # 基础检查
    if current_price <= 0:
        return _empty_position_state("空仓", "数据不足")

    # ATR 止损计算，确保止损价为正
    atr_stop = round(max(0.01, support - 1.5 * atr14), 2) if support > 0 and atr14 > 0 else round(current_price * 0.95, 2)

    # 提取威科夫信号
    bc_signal = False
    utad_signal = False
    sow_signal = False
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            utad_signal = wyk.get("upthrust_signal", False)
            sow_signal = wyk.get("sow_signal", False)

    # 筹码搬家检查
    chip_warning = "none"
    if isinstance(chip_migration, dict):
        chip_warning = chip_migration.get("warning_level", "none")

    # 条件检查
    # 统一止损：取 hard_stop / atr_stop / trailing_stop 三者最高（只紧不松）
    effective_stop = max(
        stop_price if stop_price > 0 else 0,
        atr_stop if atr_stop > 0 else 0,
        trailing_stop if trailing_stop and trailing_stop > 0 else 0,
    )

    conditions = {
        "at_support": support > 0 and abs(current_price - support) / max(support, 1) < 0.03,
        "at_resistance": resistance > 0 and abs(current_price - resistance) / max(resistance, 1) < 0.03,
        "in_high_zone": high_zone_lower > 0 and high_zone_lower <= current_price <= resistance,
        "above_stop": stop_price <= 0 or current_price > stop_price,
        "above_atr_stop": current_price > atr_stop,
        "above_trailing_stop": trailing_stop is None or trailing_stop <= 0 or current_price > trailing_stop,
        "above_effective_stop": effective_stop <= 0 or current_price > effective_stop,
        "breakout_confirmed": confirm_price > 0 and current_price >= confirm_price,
        "pullback_to_support": support > 0 and current_price <= support * 1.02 and current_price >= support * 0.98,
        "chip_stable": chip_warning not in ("critical", "warning"),
        "expma10_up": expma10 is not None and current_price > expma10,
        "bc_signal": bc_signal,
        "utad_signal": utad_signal,
        "sow_signal": sow_signal,
        "stage_accumulation": major_stage == "蓄势",
        "stage_markup": major_stage == "主升",
        "stage_distribution": major_stage == "派发",
        "stage_decline": major_stage == "衰退",
        "momentum_strong": momentum in ("走强", "修复"),
        "momentum_weak": momentum in ("转弱",),
    }

    # 状态判定
    if not has_position:
        # 空仓状态
        if conditions["stage_decline"]:
            return _make_position_state("空仓", "衰退期不碰", 0, conditions)
        if conditions["at_support"] and conditions["momentum_strong"] and not conditions["stage_decline"]:
            return _make_position_state(
                "初始建仓", "到达支撑位+短期走强，试探买10%",
                10, conditions, stop_price=atr_stop,
            )
        return _make_position_state("空仓", "等待到达支撑位", 0, conditions)

    # 有持仓的状态流转
    # 检查统一止损（hard_stop / atr_stop / trailing_stop 取最高）
    if not conditions["above_effective_stop"]:
        return _make_position_state(
            "退出再买", "跌破止损，清仓等待",
            0, conditions, stop_price=0,
        )

    # 检查 UTAD / SOW / 筹码搬家 → 退出
    if conditions["utad_signal"] or conditions["sow_signal"] or chip_warning == "critical":
        reason = "UTAD上冲回落" if conditions["utad_signal"] else "SOW弱势信号" if conditions["sow_signal"] else "筹码搬家清仓"
        return _make_position_state(
            "退出再买", f"{reason}，清仓等待",
            0, conditions, stop_price=0,
        )

    # 衰退期 → 退出
    if conditions["stage_decline"]:
        return _make_position_state(
            "退出再买", "阶段转衰退，清仓",
            0, conditions, stop_price=0,
        )

    # 派发期 → 阻力位分歧（用多因子评分决定减仓力度）
    if conditions["stage_distribution"]:
        rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)
        if conditions["at_resistance"]:
            if bc_signal:
                return _make_position_state(
                    "阻力位分歧", "派发期+BC信号，减仓1/3",
                    0, conditions, stop_price=atr_stop,
                )
            if rally_score >= RALLY_REDUCE_FULL_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"派发期+冲高条件充分（{rally_score}/5），减仓15%",
                    RALLY_REDUCE_POSITION_PCT, conditions, stop_price=atr_stop,
                )
            if rally_score >= RALLY_REDUCE_MIN_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"派发期+冲高条件部分满足（{rally_score}/5），减仓10%",
                    RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=atr_stop,
                )
            return _make_position_state(
                "阻力位分歧", f"派发期到达阻力位（{rally_score}/5），观察是否突破",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", "派发期，逢高减仓",
            0, conditions, stop_price=atr_stop,
        )

    # 主升浪跟踪
    if conditions["stage_markup"]:
        # 底仓止损：上移到阻力位（更宽的止损）
        base_stop = round(resistance * 0.98, 2) if resistance > 0 else atr_stop

        # 进入高抛区间时，用评分决定是否提前减仓
        if conditions["in_high_zone"]:
            rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)
            if rally_score >= RALLY_REDUCE_FULL_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"主升期进入高抛区+冲高条件充分（{rally_score}/5），减仓15%",
                    RALLY_REDUCE_POSITION_PCT, conditions, stop_price=expma10 if expma10 else base_stop,
                )
            if rally_score >= RALLY_REDUCE_MIN_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"主升期进入高抛区+冲高条件部分满足（{rally_score}/5），减仓10%",
                    RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=expma10 if expma10 else base_stop,
                )

        if conditions["chip_stable"] and conditions["expma10_up"]:
            return _make_position_state(
                "主升浪跟踪", "主升期+筹码稳定+EXPMA(10)支撑，持有",
                0, conditions, stop_price=expma10 if expma10 else base_stop,
            )
        if not conditions["chip_stable"]:
            return _make_position_state(
                "主升浪跟踪", "主升期但筹码松动，收紧止损",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "主升浪跟踪", "主升期，持有观察",
            0, conditions, stop_price=base_stop,
        )

    # 回踩加仓（蓄势期+回踩支撑+条件满足）
    if conditions["stage_accumulation"] and conditions["pullback_to_support"]:
        # T+1 隔离锁：当天已加仓则冷却，不重复加仓
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        if last_add_date is not None and last_add_date == today:
            return _make_position_state(
                "持仓观察", "T+1冷却，今日已加仓，等待明日再评估",
                0, conditions,
            )

        # 必要条件 + 加分条件评分
        add_score = _calc_pullback_add_score(
            conditions, bars, current_price, support, atr14,
        )
        
        # 加仓独立止损：设在回踩支撑位下方（比底仓止损更窄）
        # 使用 1.0×ATR 作为止损距离（可配置）
        _ADD_ON_STOP_ATR_MULTIPLE = 1.0
        add_on_stop = round(support - _ADD_ON_STOP_ATR_MULTIPLE * atr14, 2) if support > 0 and atr14 > 0 else round(current_price * 0.97, 2)
        
        if add_score >= 5:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+条件满足（{add_score}/5），加仓15%",
                15, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
            )
        if add_score >= 3:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+部分条件满足（{add_score}/5），加仓10%",
                10, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
            )
        return _make_position_state(
            "回踩加仓", f"回踩支撑但条件不足（{add_score}/5），观望",
            0, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
        )

    # 阻力位分歧（到达阻力位，用多因子评分决定减仓力度）
    if conditions["at_resistance"]:
        rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)

        if bc_signal:
            return _make_position_state(
                "阻力位分歧", "到达阻力位+BC信号，减仓1/3",
                0, conditions, stop_price=atr_stop,
            )
        if conditions["breakout_confirmed"]:
            return _make_position_state(
                "阻力位分歧", "突破阻力位确认，继续持有",
                0, conditions, stop_price=atr_stop,
            )
        if rally_score >= RALLY_REDUCE_FULL_SCORE:
            return _make_position_state(
                "阻力位分歧", f"冲高条件充分（{rally_score}/5），减仓15%",
                RALLY_REDUCE_POSITION_PCT, conditions, stop_price=atr_stop,
            )
        if rally_score >= RALLY_REDUCE_MIN_SCORE:
            return _make_position_state(
                "阻力位分歧", f"冲高条件部分满足（{rally_score}/5），减仓10%",
                RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", f"到达阻力位（{rally_score}/5），观察量能",
            0, conditions, stop_price=atr_stop,
        )

    # 默认：持有观察
    return _make_position_state(
        "初始建仓", "持仓观察中",
        0, conditions, stop_price=atr_stop,
    )

def _calc_pullback_add_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    atr14: float,
) -> int:
    """计算回踩加仓条件评分（满分5分）。

    必要条件（2分）：
      1. 到达支撑位附近（1分）
      2. 出现止跌信号（1分）

    加分条件（3分）：
      3. 缩量回踩（1分）
      4. RSI 超卖区反弹（1分）
      5. MACD 底背离或金叉（1分）
    """
    score = 0

    # 必要条件1：到达支撑位附近（1分）
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1

    # 必要条件2：出现止跌信号（1分）— 价格企稳（近3天未创新低）
    if bars and len(bars) >= 3:
        recent_lows = [float(b.get("low") or 0) for b in bars[-3:]]
        if min(recent_lows) >= support * 0.98:
            score += 1

    # 加分条件3：缩量回踩（1分）
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1

    # 加分条件4：RSI 超卖区反弹（1分）
    if bars and len(bars) >= 14:
        closes = [float(b.get("close") or 0) for b in bars[-14:] if b.get("close")]
        if len(closes) >= 14:
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / max(avg_loss, 0.01)
            rsi = 100 - (100 / (1 + rs))
            if rsi < 40:
                score += 1

    # 加分条件5：MACD 金叉（1分）— 使用真正的 EMA
    if bars and len(bars) >= 26:
        from trader_shared.indicator_math import calc_expma
        closes = [float(b.get("close") or 0) for b in bars if b.get("close")]
        if len(closes) >= 26:
            ema12 = calc_expma(closes, 12)
            ema26 = calc_expma(closes, 26)
            if ema12 is not None and ema26 is not None and ema12 > ema26:
                score += 1

    return score

def _calc_reentry_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    expma10: float | None,
) -> int:
    """计算退出再买条件评分（满分4分）。

    必要条件（1分）：
      1. 价格回到支撑位附近

    加分条件（3分）：
      2. 缩量止跌（1分）
      3. 价格站上 EXPMA(10)（1分）
      4. 阶段没变坏（1分）
    """
    score = 0
    
    # 必要条件：价格回到支撑位附近
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1
    
    # 加分条件：缩量止跌
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1
    
    # 加分条件：价格站上 EXPMA(10)
    if expma10 and current_price > expma10:
        score += 1
    
    # 加分条件：阶段没变坏（不是衰退期）
    if not conditions.get("stage_decline", False):
        score += 1
    
    return score

def _calc_rally_reduce_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    resistance: float,
    atr14: float,
) -> int:
    """计算冲高减仓条件评分（满分5分，对称 _calc_pullback_add_score）。

    必要条件（2分）：
      1. 接近阻力位（距阻力 < 3%）
      2. 创新高后回落（近5日高点 > 前期高点，且当前 < 高点×0.98）

    加分条件（3分）：
      3. 放量滞涨（近3日均量 > 7日均量×1.2 且涨幅 < 3%）
      4. RSI 超买（RSI14 > 70）
      5. MACD 死叉（EMA12 < EMA26）
    """
    from trader_shared.indicator_math import calc_expma

    score = 0

    # 必要条件1：接近阻力位（1分）
    if resistance > 0 and abs(current_price - resistance) / max(resistance, 1) < 0.03:
        score += 1

    # 必要条件2：创新高后回落（1分）
    if bars and len(bars) >= 10:
        highs = [float(b.get("high") or 0) for b in bars if float(b.get("high") or 0) > 0]
        recent_5_high = max(highs[-5:]) if len(highs) >= 5 else 0
        earlier_high = max(highs[:-5]) if len(highs) > 5 else 0
        if recent_5_high > earlier_high and earlier_high > 0:
            if current_price < recent_5_high * 0.98:
                score += 1

    # 加分条件3：放量滞涨（1分）— 量增但价不涨（允许下跌）
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        recent_change = 0
        if len(bars) >= 4:
            prev_close = float(bars[-4].get("close") or 0)
            if prev_close > 0:
                recent_change = (current_price - prev_close) / prev_close
        if earlier_vol > 0 and recent_vol > earlier_vol * 1.2 and recent_change < 0.03:
            score += 1

    # 加分条件4：RSI 超买（1分）
    if bars and len(bars) >= 14:
        closes = [float(b.get("close") or 0) for b in bars[-14:] if b.get("close")]
        if len(closes) >= 14:
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / max(avg_loss, 0.01)
            rsi = 100 - (100 / (1 + rs))
            if rsi > 70:
                score += 1

    # 加分条件5：MACD 死叉（1分）— 使用真正的 EMA
    if bars and len(bars) >= 26:
        closes = [float(b.get("close") or 0) for b in bars if b.get("close")]
        if len(closes) >= 26:
            ema12 = calc_expma(closes, 12)
            ema26 = calc_expma(closes, 26)
            if ema12 is not None and ema26 is not None and ema12 < ema26:
                score += 1

    return score

def _assess_resistance_strength(
    bars: list[dict[str, Any]] | None,
    current_price: float,
    resistance: float,
) -> str:
    """评估阻力位强度。

    弱阻力（可以止盈）：
      - 连续2日缩量
      - 价格在阻力位附近震荡

    强阻力（等回踩加仓）：
      - 放量突破
      - 大阳线突破

    Returns:
        "weak" 或 "strong"
    """
    if not bars or len(bars) < 10 or resistance <= 0:
        return "strong"  # 默认认为强阻力
    
    recent3 = bars[-3:]
    
    # 检查是否缩量
    recent_vol = sum(float(b.get("volume") or 0) for b in recent3) / 3
    earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
    is_low_volume = earlier_vol > 0 and recent_vol < earlier_vol * 0.8
    
    # 检查是否在阻力位附近震荡
    near_resistance = abs(current_price - resistance) / max(resistance, 1) < 0.02
    
    # 检查是否有大阳线突破（含涨停板特殊处理）
    has_big_green = False
    has_limit_up = False
    for bar in recent3:
        open_p = float(bar.get("open") or 0)
        close_p = float(bar.get("close") or 0)
        high_p = float(bar.get("high") or 0)
        if open_p > 0 and close_p > open_p * 1.03:  # 涨幅 > 3%
            has_big_green = True
        # 涨停板判断：收盘价 = 最高价，且涨幅 > 9%
        if open_p > 0 and close_p == high_p and close_p > open_p * 1.09:
            has_limit_up = True
    
    # 弱阻力：缩量 + 在阻力位附近震荡 + 没有大阳线突破 + 没有涨停板
    if is_low_volume and near_resistance and not has_big_green and not has_limit_up:
        return "weak"
    
    return "strong"

def _make_position_state(
    state: str,
    reason: str,
    position_pct: int,
    conditions: dict[str, bool],
    stop_price: float = 0.0,
    take_profit_price: float = 0.0,
    pullback_add_score: int = 0,
) -> dict[str, Any]:
    """构建状态机返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": position_pct,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "conditions": conditions,
        "transition_reason": reason,
        "pullback_add_score": pullback_add_score,
    }

def _empty_position_state(state: str, reason: str) -> dict[str, Any]:
    """空状态返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": 0,
        "stop_price": 0.0,
        "take_profit_price": 0.0,
        "conditions": {},
        "transition_reason": reason,
    }

def compute_conditional_take_profit(
    current_price: float,
    entry_price: float,
    stop_price: float,
    resistance_price: float,
    major_stage: str,
    wyckoff_result: dict[str, Any] | None = None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """条件止盈（威科夫信号驱动，不是机械止盈）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "exit_plan": [],
            "wyckoff_signals": {},
        }

    # 1R 计算
    risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 提取威科夫信号
    bc_signal = False
    bc_reason = ""
    utad_signal = False
    utad_reason = ""
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            bc_reason = wyk.get("bc_reason", "")
            utad_signal = wyk.get("upthrust_signal", False)
            utad_reason = wyk.get("upthrust_reason", "")

    # 构建三批退出计划
    exit_plan: list[dict[str, Any]] = []

    # 第一笔：BC 信号 → 卖 1/3
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "购买高潮（BC），减仓1/3",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": 0.33,
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": current_price >= target_1r,
    })

    # 第三笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": 0.34,
        "reason": "阶段转派发，清仓",
        "condition": "阶段变化",
        "triggered": major_stage == "派发",
    })

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "exit_plan": exit_plan,
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
    }

def compute_take_profit(
    stage: str,
    current: float,
    highest_close: float,
    atr_pct: float,
    market_env: str = "震荡市",
) -> dict[str, Any]:
    """止盈规则：不主动止盈，只在趋势反转时退出。

    移动止损（保护利润）:
      主升期不看止损，只看阶段
      阶段转派发后，移动止损生效
      移动止损 = 最高收盘价 × (1 - ATR% × 倍数)

    大盘环境决定参数:
      牛市: ATR×4.0，不主动止盈
      震荡市: ATR×3.0，阻力位减仓
      熊市: ATR×2.0，快止盈
    """
    # ATR 倍数根据大盘环境
    env_multipliers = {"牛市": 4.0, "震荡市": 3.0, "熊市": 2.0}
    mult = env_multipliers.get(market_env, 3.0)

    if stage == "主升":
        # 主升期不看止损，只看阶段
        trailing_stop = None
        action = "让利润跑，阶段转派发再减仓"
    elif stage == "派发":
        # 派发期移动止损生效
        trailing_stop = round(highest_close * (1 - atr_pct * mult), 2)
        action = f"移动止损 {trailing_stop:.2f}，跌破减仓"
    elif stage == "衰退":
        # 衰退期清仓
        trailing_stop = round(highest_close * (1 - atr_pct * 2.0), 2)
        action = "衰退期清仓"
    else:
        # 蓄势期用技术止损
        trailing_stop = None
        action = "蓄势期用技术止损"

    return {
        "trailing_stop": trailing_stop,
        "action": action,
        "atr_multiplier": mult,
        "market_env": market_env,
    }
