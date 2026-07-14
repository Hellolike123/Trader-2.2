#!/usr/bin/env python3
"""Regime 权重映射 + 决策阈值映射。

权重矩阵: [大盘状态] × [分析模块]
决策映射: 加权分数 → 动作字符串

设计文档: docs/designs/decision-fusion-layer.md

权重矩阵已外置到 config/fusion_regime_weights.yaml（yaml 缺失/损坏自动回退内置兜底）。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Regime → 权重映射 ──

# 权重矩阵: 每个 Regime 是一组权重, 和为 1.0
#
# 已外置到 config/fusion_regime_weights.yaml（复用 rule_engine 的 yaml 加载约定）。
# 修改 yaml 即可调参, 无需改代码、无需重新打包（覆盖同名文件热更新）。
# yaml 缺失 / 格式错误 / pyyaml 未装时, 自动回退到下方 _FALLBACK_REGIME_WEIGHTS,
# 行为与历史硬编码完全一致。

# 内置兜底（= 历史硬编码默认值，禁止删除，作为安全网）
_FALLBACK_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    # 短线三席：缠论 / 动能 / 价量资金(vpf)；日线威科夫已退出融合
    # 大盘好 → 动量占优 (趋势延续靠动量)
    "正常": {"chan": 0.3, "momentum": 0.45, "vpf": 0.25},
    # 大盘弱 → 缠论占优 (结构更可靠)
    "偏弱": {"chan": 0.5, "momentum": 0.15, "vpf": 0.35},
    # 大盘很差 → 全员空仓
    "很差": {"chan": 0.0, "momentum": 0.0, "vpf": 0.0},
    # 未知 → fallback 到"正常" (保守)
    "未知": {"chan": 0.3, "momentum": 0.45, "vpf": 0.25},
}

# yaml 配置文件路径（相对本模块，兼容 editable 安装与打包副本两种布局）
_YAML_PATH = Path(__file__).parent / "config" / "fusion_regime_weights.yaml"


def _load_regime_weights() -> dict[str, dict[str, float]]:
    """从 yaml 加载 Regime 权重；yaml 不可用时回退内置默认值。

    以 _FALLBACK_REGIME_WEIGHTS 为基底，再用 yaml 中合法条目覆盖（merge）。
    任一 regime 若缺少 chan/momentum/vpf 三键或值非数字，则跳过该条保留兜底。
    整个过程被 try 包裹，任何异常（文件缺失 / 损坏 / pyyaml 未装）都静默回退兜底。
    """
    weights: dict[str, dict[str, float]] = {
        k: dict(v) for k, v in _FALLBACK_REGIME_WEIGHTS.items()
    }
    try:
        import yaml  # 懒加载：环境无 pyyaml 时不影响模块导入

        with open(_YAML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        yaml_weights = data.get("regime_weights") if isinstance(data, dict) else None
        if not isinstance(yaml_weights, dict):
            logger.debug("fusion_regime: yaml 无 regime_weights 段，使用内置兜底权重")
            return weights
        for regime, w in yaml_weights.items():
            if not isinstance(w, dict) or not all(
                k in w for k in ("chan", "momentum", "vpf")
            ):
                continue
            try:
                weights[regime] = {
                    "chan": float(w["chan"]),
                    "momentum": float(w["momentum"]),
                    "vpf": float(w["vpf"]),
                }
            except (TypeError, ValueError):
                continue
    except Exception as exc:  # 文件缺失 / 损坏 / pyyaml 未装 → 兜底
        logger.debug("fusion_regime: 权重 yaml 加载失败，回退内置兜底: %s", exc)
    return weights


# 运行时权重（模块加载时确定一次；测试可 monkeypatch _YAML_PATH 后重跑本函数验证回退）
REGIME_WEIGHTS: dict[str, dict[str, float]] = _load_regime_weights()


def get_regime_weights(regime: str) -> dict[str, float]:
    """获取给定 Regime 的权重。

    Args:
        regime: "正常" | "偏弱" | "很差" | "未知"

    Returns:
        {"chan": 0.3, "momentum": 0.45, "vpf": 0.25}

    如果 Regime 不在字典中, fallback 到 "正常"。
    """
    return REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["正常"])


# ── 加权分数 → 动作映射 ──

# 正常映射: 加权分数 → 动作
# Fix 3: 增设 [0.1, 0.25) 的"等转强观察"，将"增持"门槛提高到 0.25
# 原"增持"阈值(0.1)低于"半仓试"(0.4)但语义更重，逻辑矛盾
ACTION_MAP_NORMAL: list[tuple[float, str]] = [
    (0.4, "半仓试 (多方主导)"),
    (0.25, "增持"),
    (0.1, "等转强观察"),
    (-0.05, "持股观望"),
    (-0.15, "减1/3 (高位松动)"),
    (-0.3, "减仓"),
    (-0.5, "空仓/止损"),
]

# 分歧降级: weighted_score >= 阈值 → 动作 (降一档)
# 分歧 > 1 时的映射: 即使加权偏向多方, 也降档
ACTION_MAP_DISAGREE: list[tuple[float, str]] = [
    (0.4, "半仓试 (多方主导但有分歧)"),
    (0.1, "观望 (信号冲突)"),
    (-0.1, "回调观望"),
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
      1. 分歧过大 → 降级动作
      2. 正常映射 → 查表

    注：regime="很差" 时，所有模块权重为 0，weighted_score 自然为 0，
    映射到"持股观望"。不再一票否决（已移除，见 test_fusion_core.py:308）。

    Regime 影响：在"偏弱"大势下，各正阈值右移 +0.10，
    要求更强信号才确认做多，减少弱势市场中的假信号入场。

    Args:
        weighted_score: -1.35 ~ 1.35 之间的加权分
        disagreement:   0 (全一致) ~ 2 (完全相反)
        regime:         "正常" | "偏弱" | "很差" | "未知"
    """
    # 1. 分歧检测
    if disagreement > DISAGREEMENT_THRESHOLD:
        actions = ACTION_MAP_DISAGREE
    else:
        actions = ACTION_MAP_NORMAL

    # 1b. Regime 阈值调节：偏弱大势下正阈值右移 +0.10
    # 即比正常时要求更高分才触发做多动作，减少弱势假信号。
    _offset = 0.0
    if regime == "偏弱":
        _offset = 0.10

    # 3. 查表 (从高到低)
    for threshold, action in actions:
        # 仅正阈值偏移（负阈值不改 — 弱势下该止损照样止损）
        effective = threshold + (_offset if threshold > 0 else 0.0)
        if weighted_score >= effective:
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
