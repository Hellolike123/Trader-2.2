#!/usr/bin/env python3
"""隐马尔可夫模型大势状态检测器 (HMM Regime Detector)

完全基于 numpy 实现，零重量级依赖。
用于将大盘指数收益率与波动率序列映射为三种隐藏市场状态：
  - 状态 0: 低波上涨 (Bull)
  - 状态 1: 高波下跌 (Bear)
  - 状态 2: 宽幅震荡 (Range)

用法:
    from hmm_regime import HMMRegimeDetector

    detector = HMMRegimeDetector()
    returns = [0.01, -0.02, 0.005, ...]   # 日收益率序列
    state = detector.fit_predict(returns)  # 返回当前最可能的隐状态
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple

# 状态标签映射
REGIME_LABELS = {0: "低波上涨", 1: "高波下跌", 2: "宽幅震荡"}
REGIME_EN = {0: "bull", 1: "bear", 2: "range"}

# 最小数值精度保护，防止 log(0) 或除零
_EPS = 1e-10


class HMMRegimeDetector:
    """轻量级隐马尔可夫模型大势状态检测器。

    使用 Baum-Welch 算法（EM 迭代）学习模型参数，
    使用 Viterbi 算法解码当前最可能的隐状态序列。

    默认 3 个隐状态，高斯观测分布（均值 + 标准差）。
    """

    def __init__(self, n_states: int = 3, max_iter: int = 50, tol: float = 1e-4):
        self.n_states = n_states
        self.max_iter = max_iter
        self.tol = tol

        # 模型参数（随机初始化，fit 后更新）
        self._init_params()

    def _init_params(self) -> None:
        """随机初始化模型参数。"""
        n = self.n_states
        # 初始状态分布 π
        self.pi = np.ones(n) / n
        # 状态转移矩阵 A (n×n)
        self.A = np.full((n, n), 1.0 / n)
        # 观测高斯分布参数: 均值 μ 与标准差 σ
        # 先验: 牛 > 震荡 > 熊
        self.mu = np.array([0.008, -0.008, 0.001])
        self.sigma = np.array([0.01, 0.02, 0.015])

    # ─── 核心算法 ────────────────────────────────────────────────────────────

    def _gaussian_emission(self, obs: np.ndarray) -> np.ndarray:
        """计算所有观测对所有状态的高斯概率密度矩阵 B[t, k]。"""
        T = len(obs)
        B = np.zeros((T, self.n_states))
        for k in range(self.n_states):
            diff = obs - self.mu[k]
            sigma_k = max(self.sigma[k], _EPS)
            B[:, k] = (1.0 / (sigma_k * np.sqrt(2 * np.pi))) * np.exp(
                -0.5 * (diff / sigma_k) ** 2
            )
        return np.clip(B, _EPS, None)

    def _forward(self, B: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """前向算法，返回 alpha 矩阵与每步缩放因子 c。"""
        T = B.shape[0]
        alpha = np.zeros((T, self.n_states))
        c = np.zeros(T)

        alpha[0] = self.pi * B[0]
        c[0] = alpha[0].sum()
        alpha[0] /= max(c[0], _EPS)

        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ self.A) * B[t]
            c[t] = alpha[t].sum()
            alpha[t] /= max(c[t], _EPS)

        return alpha, c

    def _backward(self, B: np.ndarray, c: np.ndarray) -> np.ndarray:
        """后向算法，返回 beta 矩阵。"""
        T = B.shape[0]
        beta = np.zeros((T, self.n_states))
        beta[-1] = 1.0

        for t in range(T - 2, -1, -1):
            beta[t] = (self.A @ (B[t + 1] * beta[t + 1]))
            beta[t] /= max(c[t + 1], _EPS)

        return beta

    def _baum_welch(self, obs: np.ndarray) -> float:
        """单次 Baum-Welch EM 迭代，返回对数似然增量。"""
        T = len(obs)
        B = self._gaussian_emission(obs)
        alpha, c = self._forward(B)
        beta = self._backward(B, c)

        # gamma[t, k] = P(state=k at t | obs)
        gamma = alpha * beta
        gamma /= np.clip(gamma.sum(axis=1, keepdims=True), _EPS, None)

        # xi[t, i, j] = P(state=i at t, state=j at t+1 | obs)
        xi = np.zeros((T - 1, self.n_states, self.n_states))
        for t in range(T - 1):
            xi[t] = (
                alpha[t][:, None]
                * self.A
                * B[t + 1][None, :]
                * beta[t + 1][None, :]
            )
            xi[t] /= max(xi[t].sum(), _EPS)

        # 更新参数
        self.pi = gamma[0] / max(gamma[0].sum(), _EPS)
        self.A = xi.sum(axis=0)
        self.A /= np.clip(self.A.sum(axis=1, keepdims=True), _EPS, None)

        for k in range(self.n_states):
            g_k = gamma[:, k]
            g_sum = max(g_k.sum(), _EPS)
            self.mu[k] = (g_k * obs).sum() / g_sum
            diff = obs - self.mu[k]
            self.sigma[k] = max(np.sqrt((g_k * diff**2).sum() / g_sum), _EPS)

        log_likelihood = np.sum(np.log(np.clip(c, _EPS, None)))
        return log_likelihood

    def _viterbi(self, obs: np.ndarray) -> np.ndarray:
        """Viterbi 解码，返回最可能的隐状态序列。"""
        T = len(obs)
        B = self._gaussian_emission(obs)
        log_A = np.log(np.clip(self.A, _EPS, None))
        log_pi = np.log(np.clip(self.pi, _EPS, None))
        log_B = np.log(np.clip(B, _EPS, None))

        delta = np.full((T, self.n_states), -np.inf)
        psi = np.zeros((T, self.n_states), dtype=int)

        delta[0] = log_pi + log_B[0]

        for t in range(1, T):
            for j in range(self.n_states):
                trans = delta[t - 1] + log_A[:, j]
                psi[t, j] = np.argmax(trans)
                delta[t, j] = trans[psi[t, j]] + log_B[t, j]

        # 回溯
        states = np.zeros(T, dtype=int)
        states[-1] = np.argmax(delta[-1])
        for t in range(T - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]

        return states

    # ─── 公开接口 ─────────────────────────────────────────────────────────────

    def fit(self, returns: List[float]) -> "HMMRegimeDetector":
        """使用 Baum-Welch 算法拟合模型参数。

        Args:
            returns: 日收益率序列（浮点数列表，如 [0.01, -0.02, ...]）

        Returns:
            self（链式调用）
        """
        obs = np.array(returns, dtype=float)
        if len(obs) < 10:
            return self  # 数据不足，保持先验参数

        prev_ll = -np.inf
        for _ in range(self.max_iter):
            ll = self._baum_welch(obs)
            if abs(ll - prev_ll) < self.tol:
                break
            prev_ll = ll

        # 排序状态确保一致性：按均值排序（低→高对应 bull/range/bear 逆序）
        order = np.argsort(self.mu)[::-1]  # 均值从高到低: bull(0), range(2), bear(1)
        self.mu = self.mu[order]
        self.sigma = self.sigma[order]
        self.pi = self.pi[order]
        self.A = self.A[order][:, order]

        return self

    def predict(self, returns: List[float]) -> np.ndarray:
        """用 Viterbi 解码最可能的隐状态序列。

        Returns:
            整数数组，每个元素为 0(Bull) / 1(Bear) / 2(Range)
        """
        obs = np.array(returns, dtype=float)
        if len(obs) < 3:
            return np.zeros(len(obs), dtype=int)
        return self._viterbi(obs)

    def fit_predict(self, returns: List[float]) -> dict:
        """拟合并返回当前大势状态判定结果。

        Returns:
            {
                "state_id": int,          # 0=Bull, 1=Bear, 2=Range
                "state_label": str,       # "低波上涨" / "高波下跌" / "宽幅震荡"
                "state_en": str,          # "bull" / "bear" / "range"
                "confidence": float,      # 当前状态的后验概率置信度
                "mu": float,              # 当前状态均值
                "sigma": float,           # 当前状态波动率
            }
        """
        self._init_params()  # 重置，保证每次独立
        self.fit(returns)

        obs = np.array(returns, dtype=float)
        if len(obs) < 3:
            return {
                "state_id": 2, "state_label": "宽幅震荡",
                "state_en": "range", "confidence": 0.4,
                "mu": 0.0, "sigma": 0.015,
            }

        states = self.predict(returns)
        current_state = int(states[-1])

        # 计算当前状态置信度（最近5个状态的一致度）
        recent = states[-5:]
        confidence = float(np.mean(recent == current_state))

        return {
            "state_id": current_state,
            "state_label": REGIME_LABELS.get(current_state, "宽幅震荡"),
            "state_en": REGIME_EN.get(current_state, "range"),
            "confidence": round(confidence, 3),
            "mu": round(float(self.mu[current_state]), 5),
            "sigma": round(float(self.sigma[current_state]), 5),
        }


# ─── 便捷函数 ─────────────────────────────────────────────────────────────────

def detect_regime(returns: List[float]) -> dict:
    """一站式大势状态检测函数。

    Args:
        returns: 最近 N 日的指数日收益率序列（建议 60~200 个交易日）

    Returns:
        与 HMMRegimeDetector.fit_predict() 相同的结果字典
    """
    detector = HMMRegimeDetector()
    return detector.fit_predict(returns)


def regime_to_multiplier(regime_result: dict) -> dict:
    """将 HMM 检测结果转换为结构参数调节系数。

    补充 market_env.py 中基于均线的 Regime 判定，
    使自适应参数具备前瞻性。

    Returns:
        {
            "zone_width": float,      # 低吸区宽度倍率
            "confirm_buffer": float,  # 突破确认缓冲倍率
            "stop_buffer": float,     # 止损缓冲倍率
        }
    """
    state_en = regime_result.get("state_en", "range")
    confidence = regime_result.get("confidence", 0.5)

    base = {
        "bull":  {"zone_width": 1.2,  "confirm_buffer": 0.8, "stop_buffer": 1.0},
        "bear":  {"zone_width": 1.0,  "confirm_buffer": 1.3, "stop_buffer": 0.8},
        "range": {"zone_width": 1.0,  "confirm_buffer": 1.0, "stop_buffer": 1.0},
    }

    mult = base.get(state_en, base["range"]).copy()

    # 低置信度时，向中性系数收敛（防止模型噪音放大错误）
    if confidence < 0.6:
        for k in mult:
            mult[k] = 1.0 + (mult[k] - 1.0) * confidence

    return mult
