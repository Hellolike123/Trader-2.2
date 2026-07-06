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

import hashlib
from datetime import date
import numpy as np
from typing import List, Tuple

# 状态标签映射
REGIME_LABELS = {0: "低波上涨", 1: "宽幅震荡", 2: "高波下跌"}
REGIME_EN = {0: "bull", 1: "range", 2: "bear"}

# 最小数值精度保护，防止 log(0) 或除零
_EPS = 1e-10


def _clean_floats(values: List[float]) -> List[float]:
    """P2 Fix: 过滤 None/NaN/非数值，返回纯浮点列表。

    numpy 2.x 遇 None 抛 ValueError；NaN 全链路透传导致 argmax 返回未定义状态。
    """
    out: List[float] = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(fv):
            continue
        out.append(fv)
    return out


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
        self.obs_dim: int = 1  # fit() 中根据 volume_ratio 自动切换

        # 模型参数（随机初始化，fit 后更新）
        self._init_params()

    def _init_params(self) -> None:
        """随机初始化模型参数（自适应 1D / 2D）。"""
        n = self.n_states
        # 初始状态分布 π
        self.pi = np.ones(n) / n
        # 状态转移矩阵 A (n×n)
        self.A = np.full((n, n), 1.0 / n)

        # 观测高斯分布参数
        # P1 Fix: 先验正序: [bull=高收益低波动, range=近零中等波动, bear=负收益高波动]
        if self.obs_dim == 2:
            # mu[k] = [returns_mean, volume_ratio_mean]
            # 先验: 牛市放量(1.3) / 震荡平量(1.0) / 熊市缩量(0.7)
            self.mu = np.array([
                [0.008, 1.3],
                [0.001, 1.0],
                [-0.008, 0.7],
            ])
            # 协方差矩阵（每状态 2×2）
            self.cov = np.zeros((n, self.obs_dim, self.obs_dim))
            for k in range(n):
                self.cov[k] = np.eye(self.obs_dim)
            self.cov[0][0, 0] = 0.01 ** 2   # bull 收益率方差
            self.cov[0][1, 1] = 0.15 ** 2   # 成交量比率方差
            self.cov[1][0, 0] = 0.015 ** 2
            self.cov[1][1, 1] = 0.10 ** 2
            self.cov[2][0, 0] = 0.02 ** 2
            self.cov[2][1, 1] = 0.12 ** 2
            self.sigma = None  # 2D 模式不使用
        else:
            # 1D: 均值 μ 与标准差 σ
            self.mu = np.array([0.008, 0.001, -0.008])
            self.sigma = np.array([0.01, 0.015, 0.02])
            self.cov = None  # 1D 模式不使用

    # ─── 核心算法 ────────────────────────────────────────────────────────────

    def _gaussian_emission(self, obs: np.ndarray) -> np.ndarray:
        """计算所有观测对所有状态的高斯概率密度矩阵 B[t, k]。

        支持 1D（标量 mu/sigma）和 2D（向量 mu + 协方差矩阵）。
        """
        T = len(obs)
        B = np.zeros((T, self.n_states))

        if self.obs_dim == 2:
            for k in range(self.n_states):
                diff = obs - self.mu[k]  # (T, 2)
                cov_k = self.cov[k]  # (2, 2)
                # Explicit 2×2 inverse (pure numpy, zero extra dependencies)
                a, b = cov_k[0, 0], cov_k[0, 1]
                c, d = cov_k[1, 0], cov_k[1, 1]
                det = a * d - b * c
                det = max(det, _EPS)
                inv00, inv01 = d / det, -b / det
                inv10, inv11 = -c / det, a / det
                # Mahalanobis distance² = diff @ inv_cov @ diff.T
                mahal_sq = (
                    diff[:, 0] * (inv00 * diff[:, 0] + inv01 * diff[:, 1])
                    + diff[:, 1] * (inv10 * diff[:, 0] + inv11 * diff[:, 1])
                )
                norm = 1.0 / (2.0 * np.pi * np.sqrt(det))
                B[:, k] = norm * np.exp(-0.5 * mahal_sq)
        else:
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
        """单次 Baum-Welch EM 迭代，返回对数似然（参数更新后重新计算）。"""
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
            if self.obs_dim == 2:
                self.mu[k] = (g_k[:, None] * obs).sum(axis=0) / g_sum
                diff = obs - self.mu[k]
                self.cov[k] = (
                    (diff * g_k[:, None]).T @ diff / g_sum
                    + np.eye(self.obs_dim) * _EPS
                )
            else:
                self.mu[k] = (g_k * obs).sum() / g_sum
                diff = obs - self.mu[k]
                self.sigma[k] = max(np.sqrt((g_k * diff**2).sum() / g_sum), _EPS)

        # 参数更新后重新计算对数似然（避免 off-by-one：用旧参数的 c 检查收敛）
        B_new = self._gaussian_emission(obs)
        _, c_new = self._forward(B_new)
        log_likelihood = np.sum(np.log(np.clip(c_new, _EPS, None)))
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

    def fit(
        self,
        returns: List[float],
        volume_ratio: float | None = None,
    ) -> "HMMRegimeDetector":
        """使用 Baum-Welch 算法拟合模型参数。

        Args:
            returns: 日收益率序列（浮点数列表，如 [0.01, -0.02, ...]）
            volume_ratio: 近 5 日均成交额 / 前 5 日均成交额。
                          提供时切换为 2D 模型；None 时保持 1D（向后兼容）。

        Returns:
            self（链式调用）
        """
        if volume_ratio is not None:
            self.obs_dim = 2
            self._init_params()  # 以 2D 先验重新初始化
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.column_stack([
                np.array(returns, dtype=float),
                np.full(len(returns), float(volume_ratio)),
            ])
        else:
            self.obs_dim = 1
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.array(returns, dtype=float)
        if len(obs) < 30:
            return self  # 数据不足，保持先验参数

        prev_ll = -np.inf
        for _ in range(self.max_iter):
            ll = self._baum_welch(obs)
            if abs(ll - prev_ll) < self.tol:
                break
            prev_ll = ll

        # 排序状态确保一致性：按收益率均值排序（高→低: bull, range, bear）
        mu_col = self.mu[:, 0] if self.obs_dim == 2 else self.mu
        order = np.argsort(mu_col)[::-1]
        self.mu = self.mu[order]
        if self.obs_dim == 2:
            self.cov = self.cov[order]
        else:
            self.sigma = self.sigma[order]
        self.pi = self.pi[order]
        self.A = self.A[order][:, order]

        return self

    def predict(
        self,
        returns: List[float],
        volume_ratio: float | None = None,
    ) -> np.ndarray:
        """用 Viterbi 解码最可能的隐状态序列。

        Args:
            returns: 日收益率序列
            volume_ratio: 成交量比率（与 fit 保持一致）。

        Returns:
            整数数组，每个元素为 0(Bull) / 1(Range) / 2(Bear)
        """
        if self.obs_dim == 2 and volume_ratio is not None:
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.column_stack([
                np.array(returns, dtype=float),
                np.full(len(returns), float(volume_ratio)),
            ])
        else:
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.array(returns, dtype=float)
        if len(obs) < 3:
            return np.zeros(len(obs), dtype=int)
        return self._viterbi(obs)

    def fit_predict(
        self,
        returns: List[float],
        volume_ratio: float | None = None,
    ) -> dict:
        """拟合并返回当前大势状态判定结果。

        Args:
            returns: 日收益率序列
            volume_ratio: 近 5 日均成交额 / 前 5 日均成交额。
                          None 时回退到 1D 模型（向后兼容）。

        Returns:
            {
                "state_id": int,          # 0=Bull, 1=Range, 2=Bear
                "state_label": str,       # "低波上涨" / "宽幅震荡" / "高波下跌"
                "state_en": str,          # "bull" / "range" / "bear"
                "confidence": float,      # 当前状态的后验概率置信度
                "mu": float,              # 当前状态均值（收益率维度）
                "sigma": float,           # 当前状态波动率（收益率维度）
                "volume_ratio": float|None, # 当前状态成交量比率均值（2D时）
            }
        """
        self._init_params()  # 重置，保证每次独立
        self.fit(returns, volume_ratio=volume_ratio)

        if self.obs_dim == 2 and volume_ratio is not None:
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.column_stack([
                np.array(returns, dtype=float),
                np.full(len(returns), float(volume_ratio)),
            ])
        else:
            returns = _clean_floats(returns)  # P2 Fix: None/NaN 清洗
            obs = np.array(returns, dtype=float)

        if len(obs) < 3:
            return {
                "state_id": 1, "state_label": "宽幅震荡",
                "state_en": "range", "confidence": 0.4,
                "mu": 0.0, "sigma": 0.015,
                "volume_ratio": volume_ratio,
            }

        states = self.predict(returns, volume_ratio=volume_ratio)
        current_state = int(states[-1])

        # 计算当前状态置信度（最近5个状态的一致度）
        recent = states[-5:]
        confidence = float(np.mean(recent == current_state))

        # 提取收益率维度的 mu / sigma
        vr_out: float | None = None
        if self.obs_dim == 2:
            mu_ret = float(self.mu[current_state, 0])
            cov_k = self.cov[current_state]
            sig_ret = float(np.sqrt(max(cov_k[0, 0], _EPS)))
            vr_out = round(float(self.mu[current_state, 1]), 4)
        else:
            mu_ret = float(self.mu[current_state])
            sig_ret = float(max(self.sigma[current_state], _EPS))

        return {
            "state_id": current_state,
            "state_label": REGIME_LABELS.get(current_state, "宽幅震荡"),
            "state_en": REGIME_EN.get(current_state, "range"),
            "confidence": round(confidence, 3),
            "mu": round(mu_ret, 5),
            "sigma": round(sig_ret, 5),
            "volume_ratio": vr_out,
        }


# ─── 便捷函数 ─────────────────────────────────────────────────────────────────

# P1 Fix: HMM 结果内存缓存，同一交易日内相同输入不重复计算
_HMM_CACHE: dict[str, dict] = {}
_HMM_CACHE_DATE: str = ""


def detect_regime(
    returns: List[float],
    volume_ratio: float | None = None,
) -> dict:
    """一站式大势状态检测函数。

    P1 Fix: 增加内存缓存，key = (data_hash, date)，
    同一交易日内相同输入不重复计算。
    P1-3: 支持 2D 输入 (returns + volume_ratio)。

    Args:
        returns: 最近 N 日的指数日收益率序列（建议 60~200 个交易日）
        volume_ratio: 近 5 日均成交额 / 前 5 日均成交额（>1 放量，<1 缩量）。
                      None 时回退到 1D 模型（向后兼容）。

    Returns:
        与 HMMRegimeDetector.fit_predict() 相同的结果字典
    """
    global _HMM_CACHE, _HMM_CACHE_DATE

    # P2 Fix: 入口清洗 None/NaN，避免缓存 key 格式化与 np.array 双重崩溃
    returns = _clean_floats(returns)

    today_str = date.today().isoformat()
    # 跨日清缓存
    if _HMM_CACHE_DATE != today_str:
        _HMM_CACHE.clear()
        _HMM_CACHE_DATE = today_str

    # 计算缓存 key
    # P2 Fix: 缓存 key 增加 len(returns)，避免不同长度/不同标的(末50日相同)串缓存
    # P1-3: volume_ratio 进入 key，避免不同成交量输入串缓存
    vr_prefix = (
        f"vr{volume_ratio:.4f}:" if volume_ratio is not None else "vr-:"
    )
    data_hash = hashlib.md5(
        f"{len(returns)}:{vr_prefix}".encode("utf-8")
        + ",".join(f"{r:.6f}" for r in returns[-50:]).encode("utf-8")
    ).hexdigest()[:12]
    cache_key = f"{data_hash}"

    if cache_key in _HMM_CACHE:
        return _HMM_CACHE[cache_key]

    detector = HMMRegimeDetector()
    result = detector.fit_predict(returns, volume_ratio=volume_ratio)
    _HMM_CACHE[cache_key] = result
    return result


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
