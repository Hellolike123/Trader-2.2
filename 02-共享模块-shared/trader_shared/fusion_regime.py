#!/usr/bin/env python3
"""Regime 权重映射 + 决策阈值映射。

权重矩阵: [大盘状态] × [分析模块]
决策映射: 加权分数 → 动作字符串

设计文档: docs/designs/decision-fusion-layer.md

未来: 权重矩阵迁移到 yaml 配置文件。
"""

from __future__ import annotations

import math
from typing import Any

# ── Regime → 权重映射 ──

# 权重矩阵: 每个 Regime 是一组权重, 和为 1.0
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    # 大盘好 → 动量占优 (趋势延续靠动量)
    "正常": {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25},
    # 大盘弱 → 缠论占优 (结构更可靠)
    "偏弱": {"chan": 0.5, "momentum": 0.15, "wyckoff": 0.35},
    # 大盘很差 → 全员空仓
    "很差": {"chan": 0.0, "momentum": 0.0, "wyckoff": 0.0},
    # 未知 → fallback 到"正常" (保守)
    "未知": {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25},
}


def get_regime_weights(regime: str) -> dict[str, float]:
    """获取给定 Regime 的权重。

    Args:
        regime: "正常" | "偏弱" | "很差" | "未知"

    Returns:
        {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25}

    如果 Regime 不在字典中, fallback 到 "正常"。
    """
    return REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["正常"])


# ── 加权分数 → 动作映射 ──

# 正常映射: 加权分数 → 动作
ACTION_MAP_NORMAL: list[tuple[float, str]] = [
    (0.4, "半仓试 (多方主导)"),
    (0.1, "增持"),
    (-0.05, "持股观望"),
    (-0.2, "减仓"),
    (-0.4, "空仓/止损"),
]

# 分歧降级: weighted_score >= 阈值 → 动作 (降一档)
# 分歧 > 1 时的映射: 即使加权偏向多方, 也降档
ACTION_MAP_DISAGREE: list[tuple[float, str]] = [
    (0.4, "半仓试 (多方主导但有分歧)"),
    (0.0, "观望 (信号冲突)"),
    (-0.1, "等转强 (多方主导但有分歧)"),
]

# 冲突阈值: max(signals) - min(signals) > DISAGREEMENT_THRESHOLD 触发降级
DISAGREEMENT_THRESHOLD: int = 1  # max(方向) - min(方向) > 1 触发降级。方向取值 -1/0/1，差=1 即代表不一致


def score_to_action(
    weighted_score: float,
    disagreement: float,
    regime: str,
) -> str:
    """将加权分数 + 分歧度 + Regime 映射为最终决策动作。

    优先级:
      1. 大盘很差 → 一票否决空仓
      2. 分歧过大 → 降级动作
      3. 正常映射 → 查表

    Args:
        weighted_score: -1.35 ~ 1.35 之间的加权分
        disagreement:   0 (全一致) ~ 2 (完全相反)
        regime:         "正常" | "偏弱" | "很差" | "未知"
    """
    # 1. 一票否决
    if regime == "很差":
        return "空仓 (大盘很差, 一票否决)"

    # 2. 分歧检测
    if disagreement > DISAGREEMENT_THRESHOLD:
        actions = ACTION_MAP_DISAGREE
    else:
        actions = ACTION_MAP_NORMAL

    # 3. 查表 (从高到低)
    for threshold, action in actions:
        if weighted_score >= threshold:
            return action

    # 4. fallback 到低端
    return actions[-1][1] if actions else "观望 (数据不足)"


def compute_confidence(
    weighted_score: float,
    disagreement: float,
    weights: dict[str, float],
) -> float:
    """计算综合置信度 0-1。

    影响因素:
      - 加权分数绝对值越大, 置信度越高
      - 分歧越小, 置信度越高
      - 权重集中度越高 (某个模块主导), 置信度越高

    公式:
      base = min(|score| * 2, 0.9)  # 分数绝对值映射到 0-0.9
      disagree_penalty = disagreement / 2 * 0.3  # 0-2 → 0-0.3 惩罚
      concentration = 1 - sum(w^2) / (1 - 1/3)  # 集中度 0-1, 归一化
      concentration_bonus = concentration * 0.1

      confidence = max(0, min(0.95, base - disagree_penalty + concentration_bonus))
    """
    try:
        score = float(weighted_score)
    except (TypeError, ValueError):
        return 0.2

    # 基础置信度: 分数越大越有信心
    base = min(abs(score) * 2, 0.9)

    # 分歧惩罚
    try:
        disagree_penalty = (float(disagreement) / 2) * 0.3
    except (TypeError, ValueError):
        disagree_penalty = 0.3

    # 集中度 Bonus: 如果某模块权重占主导, 增加信心
    total_sq = sum(w ** 2 for w in weights.values())
    max_sq = 1.0
    min_sq = 1.0 / len(weights) if weights else 1
    max_range = max(max_sq - min_sq, 0.001)
    concentration = (total_sq - min_sq) / max_range  # 0=平等, 1=集中
    concentration_bonus = concentration * 0.1

    confidence = base - disagree_penalty + concentration_bonus

    return round(max(0.0, min(0.95, confidence)), 3)
