"""Stop loss / exit computation."""
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

def compute_stop_losses(
    stage: str,
    current: float,
    support: float,
    ma20: float | None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
    chip_support_lower: float = 0.0,
) -> dict[str, Any]:
    """三层止损体系（ATR + 筹码驱动）。

    第一层：技术止损（支撑位 - 1.5×ATR，牛市防洗盘）
    第二层：阶段止损（随阶段变化）
    第三层：时间止损（买入后 N 天不涨走人）

    筹码驱动移动止损：
      底部筹码峰没松动 → 止损跟 MA10
      底部筹码峰松动 > 40% → 止损收紧到 MA20
      底部筹码峰搬家 > 50% → 清仓

    Args:
        stage: 当前阶段
        current: 当前价
        support: 支撑位
        ma20: 20 日均线
        bars: K线数据
        atr14: 14日ATR值
        chip_migration: 筹码搬家监控结果
        chip_support_lower: 筹码最强支撑区下沿价格

    Returns:
        {
            "technical": {"price": float, "reason": str},
            "stage_based": {"price": float, "reason": str},
            "time_limit": {"days": int, "reason": str},
            "chip_trailing": {"price": float, "reason": str} | None,
        }
    """
    # 第一层：技术止损（ATR-based）
    _chip_support_lower = chip_support_lower if chip_support_lower is not None else 0.0
    _atr14 = atr14 if atr14 is not None else 0.0
    _support = support if support is not None else 0.0

    if _chip_support_lower > 0 and _atr14 > 0:
        tech_stop = round(max(0.01, _chip_support_lower - 0.5 * _atr14), 2)
        tech_reason = f"筹码下沿 {_chip_support_lower:.2f} - 0.5×ATR({_atr14:.2f})"
    elif _support > 0 and _atr14 > 0:
        # 支撑位 - 1.5×ATR，确保止损价为正
        tech_stop = round(max(0.01, _support - 1.5 * _atr14), 2)
        tech_reason = f"支撑 {_support:.2f} - 1.5×ATR({_atr14:.2f})"
    elif support > 0:
        # 无 ATR 数据，退回旧逻辑
        tech_stop = round(support * 0.975, 2)
        tech_reason = f"关键支撑 {support:.2f} 下方2.5%"
    else:
        tech_stop = round(current * 0.95, 2)
        tech_reason = "无明确支撑，当前价下方5%"

    # 第二层：阶段止损
    if stage == "蓄势":
        if support > 0 and atr14 > 0:
            stage_stop = round(max(0.01, support - 1.5 * atr14), 2)
            stage_reason = f"蓄势期保护本金，支撑 - 1.5×ATR"
        elif support > 0:
            stage_stop = round(support * 0.98, 2)
            stage_reason = f"蓄势区间下沿 {support:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "蓄势期保护本金"
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 附近
            stage_reason = f"主升期保护利润，MA20 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.92, 2)
            stage_reason = "主升期保护利润"
    elif stage == "派发":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 下方锁定收益
            stage_reason = f"派发期锁定收益，MA20上方 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "派发期锁定收益"
    else:  # 衰退
        stage_stop = 0.0  # 衰退阶段不设阶段止损，由技术止损兜底
        stage_reason = "衰退期技术止损兜底"

    # 第三层：时间止损
    if stage == "蓄势":
        time_days = 30
        time_reason = "蓄势期30天内不突破走人"
    elif stage == "主升":
        time_days = 15
        time_reason = "主升期15天内不创新高减仓"
    elif stage == "派发":
        time_days = 0
        time_reason = "派发期不建议买入"
    else:
        time_days = 0
        time_reason = "衰退期不持有"

    # 筹码驱动移动止损
    chip_trailing: dict[str, Any] | None = None
    if isinstance(chip_migration, dict) and chip_migration.get("has_history"):
        migration_pct = chip_migration.get("migration_pct", 0)
        warning_level = chip_migration.get("warning_level", "none")

        if warning_level == "critical":
            # 底部筹码峰搬家 > 50% → 清仓
            chip_trailing = {
                "price": 0.0,
                "reason": f"底部筹码搬家 {migration_pct:.0f}%，清仓信号",
                "action": "清仓",
            }
        elif warning_level == "warning":
            # 底部筹码峰松动 > 40% → 止损收紧到 MA20
            if ma20 is not None and ma20 > 0:
                chip_trailing = {
                    "price": round(ma20, 2),
                    "reason": f"筹码松动 {migration_pct:.0f}%，止损收紧到 MA20",
                    "action": "减仓",
                }
        else:
            # 底部筹码峰没松动 → 止损跟 MA10（如果有的话）
            # 这里返回 None，表示使用默认止损
            pass

    return {
        "technical": {"price": tech_stop, "reason": tech_reason},
        "stage_based": {"price": stage_stop, "reason": stage_reason},
        "time_limit": {"days": time_days, "reason": time_reason},
        "chip_trailing": chip_trailing,
    }

def compute_exit_plan(
    entry_price: float,
    stop_price: float,
    resistance_price: float | None,
    current_stage: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """计算分批止盈计划（条件止盈，威科夫信号驱动）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓

    Args:
        entry_price: 买入价
        stop_price: 止损价
        resistance_price: 最近阻力位（可选）
        current_stage: 当前阶段（蓄势/主升/派发/衰退）
        bars: K线数据（用于计算动态阻力位）
        wyckoff_result: 威科夫分析结果（包含 BC/UTAD 信号）
        atr14: 14日ATR值

    Returns:
        止盈计划字典
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "resistance_exit": None,
            "stage_exit": current_stage,
            "exit_plan": [],
            "already_exited": [],
            "wyckoff_signals": {},
        }

    # 1R 计算：ATR 自适应（tp=0.5atr / sl=0.5atr）
    if atr14 > 0:
        risk_r = round(atr14 * 0.5, 2)
    else:
        risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 阻力位退出价
    resistance_exit: float | None = None
    # 过滤阈值：阻力位超过入场价 20% 视为无效（T0 日内交易不需要太远的目标）
    _max_resistance_ratio = 1.2
    if resistance_price is not None and resistance_price > entry_price:
        if resistance_price <= entry_price * _max_resistance_ratio:
            resistance_exit = round(resistance_price, 2)
    elif bars and len(bars) >= 20:
        # 动态计算阻力位：近 20 日最高价
        # #24 修复：过滤 None/0 值，避免 max 选到 0.0 而非真实最高价
        highs = [float(b["high"]) for b in bars[-20:] if b.get("high") is not None and float(b["high"]) > 0]
        max_high = max(highs, default=0)
        if max_high > entry_price and max_high <= entry_price * _max_resistance_ratio:
            resistance_exit = round(max_high, 2)

    # 阶段退出条件
    stage_exit = "派发"  # 主升转派发时清仓

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

    # 构建退出计划（条件止盈），确保总比例为1.0
    exit_plan: list[dict[str, Any]] = []
    has_resistance_exit = resistance_exit is not None and resistance_exit > entry_price

    # 根据是否有阻力位退出，动态分配比例
    if has_resistance_exit:
        # 四笔退出：各25%
        ratios = [0.25, 0.25, 0.25, 0.25]
    else:
        # 三笔退出：各1/3
        ratios = [0.33, 0.33, 0.34]

    # 第一笔：BC 信号（购买高潮）
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": ratios[0],
            "reason": "购买高潮（BC），减仓",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": ratios[0],
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：阻力位止盈（如果有效）
    if has_resistance_exit:
        exit_plan.append({
            "price": resistance_exit,
            "ratio": ratios[1],
            "reason": "阻力位",
            "condition": "触及阻力位",
            "triggered": False,
        })

    # 第三笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": ratios[2] if has_resistance_exit else ratios[1],
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": False,
    })

    # 第四笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": ratios[3] if has_resistance_exit else ratios[2],
        "reason": "阶段转派发，清仓",
        "condition": "阶段转派发",
        "triggered": False,
    })

    # 突破跟进逻辑
    breakout_followup: dict[str, Any] | None = None
    if resistance_exit is not None and atr14 > 0:
        # 突破阻力位后的新止损和新目标
        new_stop = resistance_exit  # 旧阻力位 → 新支撑位
        # 新目标：下一个阻力位或 2R
        next_resistance = None
        if bars and len(bars) >= 40:
            all_highs = [float(b.get("high") or 0) for b in bars[-40:]]
            above_resistance = [h for h in all_highs if h > resistance_exit * 1.01]
            if above_resistance:
                next_resistance = round(min(above_resistance), 2)
        if next_resistance is None:
            next_resistance = round(entry_price + risk_r * 2, 2)

        breakout_followup = {
            "new_stop": round(new_stop, 2),
            "new_target": next_resistance,
            "add_on_pullback": True,
            "note": "突破阻力位后止损上移，回踩新支撑不破可加仓",
        }

    # UTAD 假突破信号
    utad_action: dict[str, Any] | None = None
    if utad_signal:
        utad_action = {
            "signal": "UTAD",
            "reason": utad_reason,
            "action": "立刻减仓",
            "note": "上冲回落假突破，止损下移回原支撑位",
        }

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "resistance_exit": resistance_exit,
        "stage_exit": stage_exit,
        "exit_plan": exit_plan,
        "already_exited": [False, False, False],
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
        "breakout_followup": breakout_followup,
        "utad_action": utad_action,
    }

def compute_stage_stop(
    stage: str,
    ma20: float | None,
    range_low: float | None = None,
    atr_pct: float = 0.02,
    expma20: float | None = None,
) -> dict[str, Any]:
    """根据阶段计算止损位。

    蓄势期：蓄势区间下沿（保护本金）
    主升期：MA20（保护利润）
    派发期：EXPMA(20) 上方（锁定收益）
    衰退期：不持有

    Args:
        stage: 当前阶段
        ma20: 20 日均线
        range_low: 蓄势区间下沿（可选）
        atr_pct: ATR 占比
        expma20: 20 日 EXPMA（可选，派发期优先使用）

    Returns:
        {"price": float, "reason": str}
    """
    if stage == "蓄势":
        if range_low is not None and range_low > 0:
            return {"price": round(range_low, 2), "reason": f"蓄势区间下沿 {range_low:.2f}"}
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20 * 0.95, 2), "reason": f"蓄势期保护本金，MA20下方5%"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20, 2), "reason": f"主升期保护利润，MA20 {ma20:.2f}"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "派发":
        # 派发期优先使用 EXPMA(20)，fallback 到 MA20
        ref_price = expma20 if (expma20 is not None and expma20 > 0) else ma20
        ref_name = "EXPMA(20)" if (expma20 is not None and expma20 > 0) else "MA20"
        if ref_price is not None and ref_price > 0:
            return {"price": round(ref_price * (1 + atr_pct * 0.5), 2), "reason": f"派发期锁定收益，{ref_name}上方"}
        return {"price": 0.0, "reason": "数据不足"}
    else:  # 衰退
        return {"price": 0.0, "reason": "衰退期不持有"}

def check_time_stop(
    entry_date: str | None,
    current_stage: str,
    days_held: int,
    made_new_high: bool,
    has_position: bool = True,
) -> dict[str, Any]:
    """检查时间止损。

    蓄势期买入：30 天不突破 → 走人
    主升期买入：15 天不创新高 → 减仓
    派发期买入：不建议

    Args:
        entry_date: 买入日期（YYYY-MM-DD）
        current_stage: 当前阶段
        days_held: 已持有天数
        made_new_high: 是否创新高
        has_position: 是否有持仓（空仓时不触发清仓）

    Returns:
        {"triggered": bool, "action": str, "days_left": int}
    """
    if not has_position:
        return {"triggered": False, "action": "空仓不触发时间止损", "days_left": 0}

    if current_stage == "蓄势":
        limit = ACCUMULATION_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"蓄势期{limit}天不突破，走人", "days_left": 0}
        return {"triggered": False, "action": "等待突破", "days_left": max(0, limit - days_held)}
    elif current_stage == "主升":
        limit = MARKUP_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"主升期{limit}天不创新高，减仓", "days_left": 0}
        return {"triggered": False, "action": "等待创新高", "days_left": max(0, limit - days_held)}
    elif current_stage == "派发":
        return {"triggered": False, "action": "派发期不建议买入", "days_left": 0}
    else:  # 衰退
        return {"triggered": True, "action": "衰退期清仓", "days_left": 0}

def compute_stop_summary(
    technical_stop: float,
    stage_stop: float,
    time_stop: dict[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """汇总三层止损，取最近的作为最终止损。

    Args:
        technical_stop: 技术止损价
        stage_stop: 阶段止损价
        time_stop: 时间止损结果
        current_price: 当前价

    Returns:
        {"final_stop": float, "stops": dict, "time_stop": dict}
    """
    stops: dict[str, float] = {}
    if technical_stop > 0:
        stops["技术止损"] = technical_stop
    if stage_stop > 0:
        stops["阶段止损"] = stage_stop

    # 取最高的止损价（最近当前价的）
    final_stop = max(stops.values()) if stops else 0.0

    return {
        "final_stop": final_stop,
        "stops": stops,
        "time_stop": time_stop,
    }
