#!/usr/bin/env python3
"""贝叶斯概率决策融合网络单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATE = _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
if str(_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(_CANDIDATE))


class TestBayesianFusion:
    """贝叶斯融合网络正确性与鲁棒性测试。"""

    def setup_method(self):
        from bayesian_fusion import BayesianFusion, bayesian_merge, ACTIONS
        self.BF = BayesianFusion
        self.bayesian_merge = bayesian_merge
        self.ACTIONS = ACTIONS

    # ── 基础返回格式 ──────────────────────────────────────────────────────────

    def test_returns_required_keys(self):
        """merge 应返回包含必要键的字典。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1, "confidence": 0.8},
            {"direction": 0, "confidence": 0.3},
            {"direction": 1, "confidence": 0.7},
        )
        assert "action" in result
        assert "action_score" in result
        assert "posterior" in result
        assert "confidence" in result
        assert "regime" in result

    def test_action_is_valid_label(self):
        """action 应在预定义的动作标签列表中。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1, "confidence": 0.8},
            {"direction": 1, "confidence": 0.7},
            {"direction": 1, "confidence": 0.9},
            regime_state="bull",
        )
        assert result["action"] in self.ACTIONS

    def test_posterior_sums_to_one(self):
        """后验概率向量之和应接近 1.0。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": -1, "confidence": 0.6},
            {"direction": 0, "confidence": 0.4},
            {"direction": 1, "confidence": 0.5},
        )
        posterior_sum = sum(result["posterior"])
        assert abs(posterior_sum - 1.0) < 0.01, f"后验概率之和 {posterior_sum} 不等于 1"

    def test_posterior_length_is_five(self):
        """后验概率向量长度应为 5（对应 5 个动作）。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 0, "confidence": 0.5},
            {"direction": 0, "confidence": 0.5},
            {"direction": 0, "confidence": 0.5},
        )
        assert len(result["posterior"]) == 5

    def test_action_score_in_valid_range(self):
        """action_score 应在 [-1.0, 1.0] 之间。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1, "confidence": 0.9},
            {"direction": 1, "confidence": 0.8},
            {"direction": 1, "confidence": 0.9},
            regime_state="bull",
        )
        assert -1.0 <= result["action_score"] <= 1.0

    # ── 方向一致性 ────────────────────────────────────────────────────────────

    def test_all_bullish_signals_in_bull_regime_favors_buy(self):
        """牛市中三路均看多时，应倾向于买入动作。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1, "confidence": 0.85},
            {"direction": 1, "confidence": 0.80},
            {"direction": 1, "confidence": 0.90},
            regime_state="bull",
        )
        assert result["action_score"] > 0, f"全多信号应偏多，实际 action={result['action']}"

    def test_all_bearish_signals_in_bear_regime_favors_sell(self):
        """熊市中三路均看空时，应倾向于减仓或空仓动作。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": -1, "confidence": 0.85},
            {"direction": -1, "confidence": 0.80},
            {"direction": -1, "confidence": 0.90},
            regime_state="bear",
        )
        assert result["action_score"] < 0, f"全空信号应偏空，实际 action={result['action']}"

    def test_neutral_signals_stay_neutral(self):
        """三路均中性时，持仓观察应有较高后验概率。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 0, "confidence": 0.3},
            {"direction": 0, "confidence": 0.3},
            {"direction": 0, "confidence": 0.3},
        )
        # 中性状态下 action_score 绝对值不应过大
        assert abs(result["action_score"]) <= 0.5

    # ── 冲突信号处理 ──────────────────────────────────────────────────────────

    def test_conflict_signal_does_not_crash(self):
        """多空冲突信号下系统不应崩溃。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1, "confidence": 0.9},   # 缠论强多
            {"direction": -1, "confidence": 0.8},  # 动能强空
            {"direction": 0, "confidence": 0.3},   # 威科夫中性
            regime_state="range",
        )
        assert isinstance(result, dict)
        assert result["action"] in self.ACTIONS

    def test_high_confidence_expert_dominates(self):
        """高置信度专家应主导最终决策方向。"""
        bf = self.BF()
        # 缠论极高置信度看多，其余两路低置信度看空
        result_bullish = bf.merge(
            {"direction": 1, "confidence": 0.95},
            {"direction": -1, "confidence": 0.2},
            {"direction": -1, "confidence": 0.2},
            regime_state="bull",
        )
        # 看空高置信度主导
        result_bearish = bf.merge(
            {"direction": -1, "confidence": 0.95},
            {"direction": 1, "confidence": 0.2},
            {"direction": 1, "confidence": 0.2},
            regime_state="bear",
        )
        # 两者方向应相反
        assert result_bullish["action_score"] > result_bearish["action_score"]

    # ── 鲁棒性 ────────────────────────────────────────────────────────────────

    def test_empty_signal_dicts(self):
        """空信号字典应安全处理，不崩溃。"""
        bf = self.BF()
        result = bf.merge({}, {}, {})
        assert isinstance(result, dict)

    def test_missing_confidence_field(self):
        """缺少 confidence 字段时应使用默认值处理。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 1},
            {"direction": -1},
            {"direction": 0},
        )
        assert isinstance(result, dict)

    def test_invalid_direction_value(self):
        """非标准 direction 值（如 2 或 None）应安全处理。"""
        bf = self.BF()
        result = bf.merge(
            {"direction": 99, "confidence": 0.5},
            {"direction": None, "confidence": 0.5},
            {"direction": -99, "confidence": 0.5},
        )
        assert isinstance(result, dict)

    def test_convenience_function_bayesian_merge(self):
        """一站式 bayesian_merge 函数应正常工作。"""
        result = self.bayesian_merge(
            {"direction": 1, "confidence": 0.8},
            {"direction": 0, "confidence": 0.3},
            {"direction": 1, "confidence": 0.7},
            regime_state="bull",
        )
        assert "action" in result
        assert "method" in result
        assert result["method"] == "bayesian"

    # ── Regime 差异性验证 ─────────────────────────────────────────────────────

    def test_same_signals_different_regime_gives_different_scores(self):
        """相同信号在牛市和熊市下应产生不同的决策偏差。"""
        bf = self.BF()
        signals = (
            {"direction": 1, "confidence": 0.7},
            {"direction": 0, "confidence": 0.4},
            {"direction": 1, "confidence": 0.6},
        )
        result_bull = bf.merge(*signals, regime_state="bull")
        result_bear = bf.merge(*signals, regime_state="bear")
        # 牛市下应更倾向于买入
        assert result_bull["action_score"] >= result_bear["action_score"]
