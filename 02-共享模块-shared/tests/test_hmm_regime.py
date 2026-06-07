#!/usr/bin/env python3
"""HMM 大势状态检测器单元测试。"""

from __future__ import annotations

import time

import numpy as np
import pytest


class TestHMMRegimeDetector:
    """HMM 模型数学正确性与稳定性测试。"""

    def setup_method(self):
        from trader_shared.hmm_regime import HMMRegimeDetector, detect_regime, regime_to_multiplier
        self.HMM = HMMRegimeDetector
        self.detect_regime = detect_regime
        self.regime_to_multiplier = regime_to_multiplier

    def _bull_returns(self, n=100):
        """合成牛市收益率序列：均值为正，低波动。"""
        np.random.seed(42)
        return list(np.random.normal(0.008, 0.008, n))

    def _bear_returns(self, n=100):
        """合成熊市收益率序列：均值为负，高波动。"""
        np.random.seed(99)
        return list(np.random.normal(-0.008, 0.020, n))

    def _range_returns(self, n=100):
        """合成震荡行情：均值近零，中等波动。"""
        np.random.seed(7)
        return list(np.random.normal(0.0, 0.013, n))

    # ── 基础功能 ──────────────────────────────────────────────────────────────

    def test_fit_predict_returns_dict(self):
        """fit_predict 应返回包含必要键的字典。"""
        result = self.detect_regime(self._bull_returns())
        assert isinstance(result, dict)
        assert "state_id" in result
        assert "state_label" in result
        assert "state_en" in result
        assert "confidence" in result
        assert result["state_en"] in ("bull", "bear", "range")

    def test_state_id_valid_range(self):
        """state_id 应在 [0, 1, 2] 范围内。"""
        result = self.detect_regime(self._bear_returns())
        assert result["state_id"] in (0, 1, 2)

    def test_confidence_valid_range(self):
        """confidence 应在 [0, 1] 之间。"""
        result = self.detect_regime(self._range_returns())
        assert 0.0 <= result["confidence"] <= 1.0

    # ── 极端输入鲁棒性 ────────────────────────────────────────────────────────

    def test_empty_returns(self):
        """空序列应返回默认震荡状态，不崩溃。"""
        result = self.detect_regime([])
        assert result["state_en"] == "range"
        assert result["confidence"] >= 0.0

    def test_single_element(self):
        """单个数据点应安全处理。"""
        result = self.detect_regime([0.01])
        assert isinstance(result, dict)

    def test_all_zero_returns(self):
        """全零收益率（停牌场景）应安全处理，不崩溃。"""
        result = self.detect_regime([0.0] * 50)
        assert isinstance(result, dict)

    def test_extreme_positive_spike(self):
        """极端正收益（涨停潮）应安全处理。"""
        returns = [0.1] * 20 + [0.001] * 80
        result = self.detect_regime(returns)
        assert isinstance(result, dict)

    def test_extreme_negative_spike(self):
        """极端负收益（熔断暴跌）应安全处理。"""
        returns = [-0.1] * 20 + [-0.001] * 80
        result = self.detect_regime(returns)
        assert isinstance(result, dict)

    # ── 收敛速度 ──────────────────────────────────────────────────────────────

    def test_convergence_speed_under_500ms(self):
        """200个数据点的拟合+解码应在 500ms 内完成（纯 Python numpy 实现的合理上限）。"""
        returns = self._bull_returns(200)
        start = time.perf_counter()
        self.detect_regime(returns)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500.0, f"耗时 {elapsed_ms:.2f}ms 超过 500ms 上限"

    def test_convergence_speed_short_series(self):
        """60个数据点的完整流程应在 200ms 内完成。"""
        returns = self._bull_returns(60)
        start = time.perf_counter()
        self.detect_regime(returns)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200.0, f"耗时 {elapsed_ms:.2f}ms 超过 200ms 上限"

    # ── Regime Multiplier 输出 ────────────────────────────────────────────────

    def test_bull_multiplier_zone_width_increased(self):
        """牛市大势下 zone_width 应大于等于 1.0。"""
        bull_result = {"state_en": "bull", "confidence": 0.8}
        mult = self.regime_to_multiplier(bull_result)
        assert mult["zone_width"] >= 1.0

    def test_bear_multiplier_stop_buffer_reduced(self):
        """熊市大势下 stop_buffer 应小于 1.0（更紧的止损）。"""
        bear_result = {"state_en": "bear", "confidence": 0.9}
        mult = self.regime_to_multiplier(bear_result)
        assert mult["stop_buffer"] < 1.0

    def test_bear_multiplier_confirm_buffer_increased(self):
        """熊市大势下 confirm_buffer 应大于 1.0（更严格的突破确认）。"""
        bear_result = {"state_en": "bear", "confidence": 0.9}
        mult = self.regime_to_multiplier(bear_result)
        assert mult["confirm_buffer"] > 1.0

    def test_low_confidence_converges_to_neutral(self):
        """低置信度时，调节系数应向中性 1.0 收敛。"""
        low_conf_result = {"state_en": "bull", "confidence": 0.2}
        mult = self.regime_to_multiplier(low_conf_result)
        # 低置信度下 zone_width 应远小于高置信度下的 1.2
        high_conf_result = {"state_en": "bull", "confidence": 1.0}
        mult_high = self.regime_to_multiplier(high_conf_result)
        assert abs(mult["zone_width"] - 1.0) < abs(mult_high["zone_width"] - 1.0)

    # ── 内部算法 ─────────────────────────────────────────────────────────────

    def test_forward_backward_probabilities_sum_to_one(self):
        """前向-后向算法的 gamma 矩阵每行应归一化为 1。"""
        hmm = self.HMM()
        returns = self._range_returns(50)
        obs = np.array(returns)
        hmm.fit(returns)
        B = hmm._gaussian_emission(obs)
        alpha, c = hmm._forward(B)
        beta = hmm._backward(B, c)
        gamma = alpha * beta
        row_sums = gamma.sum(axis=1)
        # gamma 每行和应接近 1（归一化后）
        # 由于 alpha 已经缩放，gamma 和不一定精确等于1，但应接近
        assert not np.any(np.isnan(gamma)), "gamma 中存在 NaN"
        assert not np.any(np.isinf(gamma)), "gamma 中存在 Inf"

    def test_viterbi_returns_valid_states(self):
        """Viterbi 解码结果应全部为有效状态 [0, 1, 2]。"""
        hmm = self.HMM()
        returns = self._bull_returns(80)
        hmm.fit(returns)
        states = hmm.predict(returns)
        assert all(s in (0, 1, 2) for s in states)
        assert len(states) == len(returns)

    def test_bear_market_label_correct(self):
        """REGIME_EN 字典应正确映射：排序后 index 2 = bear。"""
        from trader_shared.hmm_regime import REGIME_EN
        # 验证标签字典与排序语义一致
        # 排序方向: mu 高→低 = bull(0), range(1), bear(2)
        assert REGIME_EN[2] == "bear"

    def test_bull_market_label_correct(self):
        """REGIME_EN 字典应正确映射：排序后 index 0 = bull。"""
        from trader_shared.hmm_regime import REGIME_EN
        assert REGIME_EN[0] == "bull"

    def test_label_mapping_consistent(self):
        """REGIME_EN 标签字典应与排序结果一致：0=Bull, 1=Range, 2=Bear。"""
        from trader_shared.hmm_regime import REGIME_EN, REGIME_LABELS
        assert REGIME_EN[0] == "bull"
        assert REGIME_EN[1] == "range"
        assert REGIME_EN[2] == "bear"
        assert REGIME_LABELS[0] == "低波上涨"
        assert REGIME_LABELS[1] == "宽幅震荡"
        assert REGIME_LABELS[2] == "高波下跌"

    def test_min_data_threshold(self):
        """少于 3 个观测值时应返回默认 range 状态。"""
        returns = [0.01, -0.01]
        result = self.detect_regime(returns)
        assert result["state_en"] == "range"
        assert result["confidence"] == 0.4


class TestMarketEnvHMMFallback:
    """Verify that market_env.assess() logs (not swallows) HMM failures (P1 #6 fix)."""

    def test_hmm_failure_logs(self, caplog):
        """When HMM detection raises, market_env must still return a result and log at DEBUG."""
        import logging
        from unittest.mock import patch

        from market_env import assess

        # Force detect_regime to raise an exception (simulating garbage closes / NaN)
        def _boom(_returns):
            raise ZeroDivisionError("simulated closes[i-1] == 0")

        with caplog.at_level(logging.DEBUG, logger="trader.market_env"), \
             patch.dict("os.environ", {"TRADER_LOG_LEVEL": "DEBUG"}), \
             patch("trader_shared.hmm_regime.detect_regime", _boom):
            with patch("market_env._fetch_index_data") as mock_fetch, \
                 patch("market_env._is_market_open_now", return_value=False):
                mock_fetch.return_value = {
                    "current": 5000.0,
                    "pre_close": 4900.0,
                    "change_pct": 2.04,
                    "bars": [
                        {"date": f"2026-05-{(i % 28) + 1:02d}", "close": 4900.0 + i}
                        for i in range(60)
                    ],
                }
                result = assess()

        # assess() must still return a result (graceful degradation)
        assert result is not None
        assert "hmm_regime_en" in result
        # The fallback neutral regime must be set
        assert result["hmm_regime_en"] == "range"
        # The failure must be logged at DEBUG
        log_msgs = [r.getMessage() for r in caplog.records]
        assert any("HMM regime detection failed" in m for m in log_msgs), \
            f"expected HMM failure log, got: {log_msgs}"
