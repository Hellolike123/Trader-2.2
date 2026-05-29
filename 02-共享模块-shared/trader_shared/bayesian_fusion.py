#!/usr/bin/env python3
"""贝叶斯信念融合网络 (Bayesian Belief Fusion)

用贝叶斯后验概率替代硬编码经验权重，
从四维专家方向信号（缠论/威科夫/动能/筹码）计算最优交易动作的条件联合概率。

架构定位：
    当 BAYESIAN_FUSION=true 时，接管 fusion_core.py 中的加权决策路径。
    默认关闭，保持 Trader 2.2 的场景优先级权重行为，安全过渡。

用法:
    from bayesian_fusion import BayesianFusion, bayesian_merge

    result = bayesian_merge(
        chan_signal={"direction": 1, "confidence": 0.8},
        momentum_signal={"direction": -1, "confidence": 0.6},
        wyckoff_signal={"direction": 1, "confidence": 0.7},
        regime_state="bull",   # 来自 hmm_regime.detect_regime()
    )
"""

from __future__ import annotations

import os
import numpy as np
from typing import Dict, Any

# ── 安全开关：默认关闭，BAYESIAN_FUSION=true 才激活 ──────────────────────
BAYESIAN_FUSION = os.environ.get("BAYESIAN_FUSION", "false").lower() in ("true", "1", "yes")

# ── 动作标签 ─────────────────────────────────────────────────────────────────
ACTIONS = ["空仓观望", "减仓/防守", "持仓观察", "半仓试多", "加仓做多"]
ACTION_SCORES = [-1.0, -0.5, 0.0, 0.5, 1.0]   # 对应连续分数


class BayesianFusion:
    """轻量级贝叶斯多专家融合网络。

    条件概率矩阵结构：
        P(action | expert_direction, regime)

    expert_direction ∈ {-1, 0, 1}
    regime ∈ {"bull", "bear", "range"}
    action ∈ 5 个动作标签

    通过历史信号胜率初始化先验，乘积规则融合多专家证据。
    """

    def __init__(self):
        # ── 各大势环境下各专家各方向对应动作的先验概率矩阵 ──────────────────
        # 维度: [regime(3)] [expert_dir(3: -1,0,1)] [action(5)]
        # 初始先验来自领域知识，后续可离线从 signals.jsonl 自适应更新
        self._prior = self._build_prior()

    def _build_prior(self) -> Dict[str, np.ndarray]:
        """构建各 Regime 下专家信号的条件概率先验矩阵。

        行索引: expert_direction (-1=0, 0=1, 1=2)
        列索引: action (空仓, 减仓, 持仓, 半仓试多, 加仓做多)
        """
        # 牛市先验：看多信号应映射到更高仓位动作
        bull = np.array([
            [0.35, 0.30, 0.20, 0.10, 0.05],  # direction=-1 (看空噪音)
            [0.10, 0.15, 0.45, 0.20, 0.10],  # direction=0  (中性)
            [0.02, 0.05, 0.15, 0.40, 0.38],  # direction=+1 (看多)
        ])

        # 熊市先验：看空信号权重更高，防守优先
        bear = np.array([
            [0.40, 0.35, 0.15, 0.07, 0.03],  # direction=-1 (看空强信号)
            [0.20, 0.25, 0.40, 0.10, 0.05],  # direction=0  (中性)
            [0.05, 0.10, 0.30, 0.35, 0.20],  # direction=+1 (看多但谨慎)
        ])

        # 震荡先验：持仓观察权重最高，避免频繁换手
        rang = np.array([
            [0.20, 0.30, 0.30, 0.15, 0.05],  # direction=-1
            [0.05, 0.10, 0.60, 0.15, 0.10],  # direction=0
            [0.03, 0.07, 0.30, 0.40, 0.20],  # direction=+1
        ])

        # 归一化确保每行概率和为 1
        for m in [bull, bear, rang]:
            m /= m.sum(axis=1, keepdims=True)

        return {"bull": bull, "bear": bear, "range": rang}

    def _dir_to_idx(self, direction: int) -> int:
        """方向值转矩阵行索引。"""
        return {-1: 0, 0: 1, 1: 2}.get(int(direction), 1)

    def _get_prior(self, regime: str) -> np.ndarray:
        """获取对应 Regime 的先验矩阵。"""
        return self._prior.get(regime, self._prior["range"])

    def _expert_likelihood(
        self,
        signal: Dict[str, Any],
        regime: str,
        expert_weight: float = 1.0,
    ) -> np.ndarray:
        """计算单个专家信号对各动作的似然向量。

        Args:
            signal: {"direction": int, "confidence": float}
            regime: 当前大势状态 ("bull"/"bear"/"range")
            expert_weight: 该专家的先验相对权重

        Returns:
            长度为 5 的概率向量
        """
        raw_dir = signal.get("direction", 0)
        direction = int(raw_dir) if raw_dir is not None else 0
        confidence = float(signal.get("confidence", 0.3))
        confidence = np.clip(confidence, 0.05, 0.95)

        prior_matrix = self._get_prior(regime)
        row_idx = self._dir_to_idx(direction)
        base_prob = prior_matrix[row_idx].copy()

        # 用置信度对先验进行调节：高置信度时向该方向的极端动作靠拢
        uniform = np.ones(len(ACTIONS)) / len(ACTIONS)
        blended = confidence * base_prob + (1 - confidence) * uniform

        # 加权并归一化
        weighted = blended ** expert_weight
        return weighted / (weighted.sum() + 1e-10)

    def merge(
        self,
        chan_signal: Dict[str, Any],
        momentum_signal: Dict[str, Any],
        wyckoff_signal: Dict[str, Any],
        regime_state: str = "range",
        chan_weight: float = 1.2,
        momentum_weight: float = 0.8,
        wyckoff_weight: float = 1.1,
    ) -> Dict[str, Any]:
        """贝叶斯乘积规则融合三路专家似然，返回最优动作及后验概率。

        Args:
            chan_signal:      缠论专家信号 {"direction": int, "confidence": float}
            momentum_signal:  动能专家信号
            wyckoff_signal:   威科夫专家信号
            regime_state:     HMM 大势状态 ("bull"/"bear"/"range")
            *_weight:         各专家的相对权重（指数幂），默认均等

        Returns:
            {
                "action": str,
                "action_score": float,   # -1.0 ~ 1.0
                "posterior": list,       # 5个动作的后验概率
                "top_action": str,
                "confidence": float,
                "regime": str,
            }
        """
        # 各专家独立似然
        l_chan = self._expert_likelihood(chan_signal, regime_state, chan_weight)
        l_mom  = self._expert_likelihood(momentum_signal, regime_state, momentum_weight)
        l_wyk  = self._expert_likelihood(wyckoff_signal, regime_state, wyckoff_weight)

        # 贝叶斯乘积规则：后验 ∝ L_chan × L_mom × L_wyk × 均匀先验
        posterior = l_chan * l_mom * l_wyk
        posterior /= (posterior.sum() + 1e-10)

        # 最优动作
        best_idx = int(np.argmax(posterior))
        action = ACTIONS[best_idx]
        action_score = ACTION_SCORES[best_idx]
        confidence = float(posterior[best_idx])

        return {
            "action": action,
            "action_score": round(action_score, 3),
            "posterior": [round(float(p), 4) for p in posterior],
            "top_action": action,
            "confidence": round(confidence, 4),
            "regime": regime_state,
            "method": "bayesian",
        }


# ── 单例（避免每次调用重建对象）────────────────────────────────────────────
_FUSION = BayesianFusion()


def bayesian_merge(
    chan_signal: Dict[str, Any],
    momentum_signal: Dict[str, Any],
    wyckoff_signal: Dict[str, Any],
    regime_state: str = "range",
) -> Dict[str, Any]:
    """一站式贝叶斯融合函数，供 fusion_core.py 直接调用。"""
    return _FUSION.merge(
        chan_signal=chan_signal,
        momentum_signal=momentum_signal,
        wyckoff_signal=wyckoff_signal,
        regime_state=regime_state,
    )


def is_enabled() -> bool:
    """检查贝叶斯融合模式是否已启用。"""
    return BAYESIAN_FUSION
