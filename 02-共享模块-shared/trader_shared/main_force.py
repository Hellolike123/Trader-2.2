"""主力行为五阶段识别引擎。

基于资金流向特征、价格数据和筹码信息，识别当前主力行为所处阶段：
accumulation（吸筹）、testing（试盘）、markup（拉升）、distribution（派发）、markdown（砸盘）。

用法:
    from trader_shared.main_force import detect_main_force_stage
    result = detect_main_force_stage(features, bars)
"""

from __future__ import annotations

import math
from typing import Any


# ── 阶段名称中文映射 ──────────────────────────────────────────────

STAGE_LABELS = {
    "accumulation": "吸筹期",
    "testing": "试盘期",
    "markup": "拉升期",
    "distribution": "派发期",
    "markdown": "砸盘期",
    "unknown": "未知",
}


def detect_main_force_stage(
    features: dict[str, Any],
    bars: list[dict[str, Any]] | None = None,
    chip_info: dict[str, Any] | None = None,
    position_ratio: float = 0.5,
) -> dict[str, Any]:
    """主力行为五阶段识别主函数。

    Args:
        features: calc_fund_flow_features() 的返回值
        bars: 近期K线数据
        chip_info: 筹码分布信息（可选）
        position_ratio: 价格在近期区间的位置（0-1）

    Returns:
        {
            "stage": str,              # 阶段名称
            "confidence": float,       # 置信度 0-1
            "signals": list[str],      # 触发信号列表
            "flow_price_relation": str, # 价资关系
            "cum_flow_5d_wan": float,
            "cum_flow_10d_wan": float,
            "consecutive_inflow_days": int,
            "consecutive_outflow_days": int,
        }
    """
    cum_5 = features.get("cum_flow_5d_wan", 0)
    cum_10 = features.get("cum_flow_10d_wan", 0)
    con_in = features.get("consecutive_inflow_days", 0)
    con_out = features.get("consecutive_outflow_days", 0)
    net_pct = features.get("net_flow_pct", 0)
    relation = features.get("flow_price_relation", "无数据")
    daily_5d = features.get("daily_flow_5d", [])

    # 数据不足
    if not daily_5d or len(daily_5d) < 3:
        return _result("unknown", 0.0, [], relation, features)

    # 计算辅助指标
    vol_ratio = _calc_volume_ratio(bars)
    price_change_20d = _calc_price_change(bars, 20) or 0.0
    chip_concentrated = False
    chip_loose = False
    if chip_info:
        chip_concentrated = chip_info.get("concentration_trend") == "上升"
        chip_loose = chip_info.get("concentration_trend") == "下降"

    signals: list[str] = []
    scores: dict[str, float] = {
        "accumulation": 0.0,
        "testing": 0.0,
        "markup": 0.0,
        "distribution": 0.0,
        "markdown": 0.0,
    }

    # ── 吸筹期检测 ──
    if abs(price_change_20d) < 0.05 and cum_5 > 0:
        scores["accumulation"] += 0.3
        signals.append(f"20日横盘({price_change_20d*100:+.1f}%)+5日净流入{cum_5:+.0f}万")
        if chip_concentrated:
            scores["accumulation"] += 0.3
            signals.append("筹码集中度上升")
        if relation == "价跌资入":
            scores["accumulation"] += 0.2
            signals.append("价跌资入")
        if con_in >= 3:
            scores["accumulation"] += 0.2
            signals.append(f"连续{con_in}日净流入")

    # ── 试盘期检测 ──
    if bars and len(bars) >= 4:
        last3 = bars[-3:]
        max_change = max(
            (float(b.get("close") or 0) - float(bars[-4].get("close") or 0)) / max(float(bars[-4].get("close") or 1), 1)
            for b in last3
        ) if len(bars) >= 4 else 0
        if max_change > 0.03 and any(d > 500 for d in daily_5d[-3:]):
            # 检查是否有次日回落
            if len(bars) >= 3:
                peak_idx = None
                last3_closes = [float(bb.get("close") or 0) for bb in bars[-3:]]
                max_close = max(last3_closes)
                for i, b in enumerate(bars[-3:]):
                    if math.isclose(float(b.get("close") or 0), max_close, rel_tol=1e-9, abs_tol=1e-9):
                        peak_idx = i
                        break
                if peak_idx is not None and peak_idx < 2:
                    next_close = float(bars[-3 + peak_idx + 1].get("close") or 0)
                    peak_close = float(bars[-3 + peak_idx].get("close") or 0)
                    if peak_close > 0 and (peak_close - next_close) / peak_close > 0.015:
                        scores["testing"] += 0.5
                        signals.append("单日脉冲上涨后回落")
                        if daily_5d[-1] > 0:
                            scores["testing"] += 0.2
                            signals.append("次日资金回流")

    # ── 拉升期检测 ──
    if con_in >= 3 and cum_5 > 1000:
        scores["markup"] += 0.3
        signals.append(f"连续{con_in}日净流入+5日累计{cum_5:+.0f}万")
        if vol_ratio and vol_ratio > 1.3:
            scores["markup"] += 0.3
            signals.append(f"量比{vol_ratio:.1f}放量")
        if price_change_20d > 0.05:
            scores["markup"] += 0.2
            signals.append(f"20日涨{price_change_20d*100:.1f}%")

    # ── 派发期检测 ──
    if position_ratio > 0.7:
        if cum_5 < 0 or (con_in == 0 and cum_5 < cum_10 * 0.3):
            scores["distribution"] += 0.3
            signals.append("高位资金流入萎缩")
            if chip_loose:
                scores["distribution"] += 0.3
                signals.append("筹码松散化")
            if relation in ("价涨资出", "价平资出"):
                scores["distribution"] += 0.2
                signals.append(relation)

    # ── 砸盘期检测 ──
    if con_out >= 3 and cum_5 < -1000:
        scores["markdown"] += 0.3
        signals.append(f"连续{con_out}日净流出+5日累计{cum_5:+.0f}万")
        if vol_ratio and vol_ratio > 1.5:
            scores["markdown"] += 0.3
            signals.append(f"量比{vol_ratio:.1f}放量下跌")
        if price_change_20d < -0.08:
            scores["markdown"] += 0.2
            signals.append(f"20日跌{price_change_20d*100:.1f}%")

    # 选择最高分阶段（平局时按优先级：markup > accumulation > testing > distribution > markdown）
    _PRIORITY = {"markup": 0, "accumulation": 1, "testing": 2, "distribution": 3, "markdown": 4}
    best_stage = max(scores, key=lambda s: (scores[s], -_PRIORITY.get(s, 99)))  # type: ignore[arg-type]
    best_score = scores[best_stage]

    if best_score < 0.3:
        return _result("unknown", 0.0, [], relation, features)

    confidence = min(0.8, round(best_score, 2))
    return _result(best_stage, confidence, signals, relation, features)


def _result(
    stage: str,
    confidence: float,
    signals: list[str],
    relation: str,
    features: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "confidence": confidence,
        "signals": signals,
        "flow_price_relation": relation,
        "cum_flow_5d_wan": features.get("cum_flow_5d_wan", 0),
        "cum_flow_10d_wan": features.get("cum_flow_10d_wan", 0),
        "consecutive_inflow_days": features.get("consecutive_inflow_days", 0),
        "consecutive_outflow_days": features.get("consecutive_outflow_days", 0),
        "daily_flow_5d": features.get("daily_flow_5d", []),
    }


def _calc_volume_ratio(bars: list[dict[str, Any]] | None) -> float | None:
    """计算近5日量比（近5日均量 / 前5日均量）。"""
    if not bars or len(bars) < 10:
        return None
    recent5 = bars[-5:]
    prev5 = bars[-10:-5]
    vol_recent = sum(float(b.get("volume") or 0) for b in recent5) / 5
    vol_prev = sum(float(b.get("volume") or 0) for b in prev5) / 5
    if vol_prev <= 0:
        return None
    return round(vol_recent / vol_prev, 2)


def _calc_price_change(bars: list[dict[str, Any]] | None, period: int) -> float | None:
    """计算近N日价格变化幅度。数据不足返回 None。"""
    if not bars or len(bars) < period:
        return None
    start = float(bars[-period].get("close") or 0)
    end = float(bars[-1].get("close") or 0)
    if start <= 0:
        return 0.0
    return (end - start) / start
