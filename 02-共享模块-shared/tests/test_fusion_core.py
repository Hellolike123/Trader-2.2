#!/usr/bin/env python3
"""测试决策融合层 — 信号标准化、Regime权重、融合决策。

所有测试使用内联 mock 数据, 不依赖网络或外部 API。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Path setup for imports
_ROOT = Path(__file__).resolve().parents[2]
_SHARED_CANDIDATE = _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
_SHARED_MARKET = _ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
_SHARED_SCRIPTS = _ROOT / "02-共享模块-shared" / "scripts"
for _path in (_ROOT / "02-共享模块-shared", _SHARED_CANDIDATE, _SHARED_MARKET, _SHARED_SCRIPTS):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


class TestChanToSignal:
    """缠论信号标准化测试。"""

    def setup_method(self):
        from fusion_core import _chan_to_signal
        self._fn = _chan_to_signal

    def test_一类买(self):
        fn = self._fn
        result = fn({"chanlun": {"buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3}]}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.8
        assert result["raw_key"] == "chan"
        assert "底背驰" in result["reason"]

    def test_二类买(self):
        fn = self._fn
        result = fn({"chanlun": {"buy_points": [{"type": "二类买", "price": 27.8, "confidence": 2}]}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6

    def test_three_buy_points_priority(self):
        """多个 buy_points 时, 第一个匹配的类型优先。"""
        fn = self._fn
        result = fn({"chanlun": {
            "buy_points": [
                {"type": "二类买", "price": 27, "confidence": 2},
                {"type": "三类买", "price": 26, "confidence": 1},
            ]
        }})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # 二类买优先(列表中第一个)

    def test_底背驰(self):
        fn = self._fn
        result = fn({"chanlun": {
            "divergence": {"bottom_divergence": True, "top_divergence": False}
        }})
        assert result["direction"] == 1
        assert result["confidence"] == 0.5
        assert "底背驰" in result["reason"]

    def test_顶背驰(self):
        fn = self._fn
        result = fn({"chanlun": {
            "divergence": {"bottom_divergence": False, "top_divergence": True}
        }})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5

    def test_拉升段(self):
        fn = self._fn
        result = fn({"chanlun": {"trend_label": "拉升段"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.4

    def test_回调段(self):
        fn = self._fn
        result = fn({"chanlun": {"trend_label": "回调段"}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.4

    def test_无信号(self):
        fn = self._fn
        result = fn({"chanlun": {"buy_points": [], "divergence": {}, "trend_label": "数据不足"}})
        assert result["direction"] == 0
        assert result["confidence"] == 0.3

    def test_空输入(self):
        fn = self._fn
        result = fn({})
        assert result["direction"] == 0
        assert result["confidence"] == 0.3

    def test_priority_buy_points_over_divergence(self):
        """buy_points 存在时忽略 divergence。"""
        fn = self._fn
        result = fn({"chanlun": {
            "buy_points": [{"type": "二类买", "price": 27, "confidence": 2}],
            "divergence": {"top_divergence": True},
        }})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # 二类买, 不是顶背驰

    def test_priority_divergence_over_trend(self):
        """divergence 存在时忽略 trend_label。"""
        fn = self._fn
        result = fn({"chanlun": {
            "divergence": {"bottom_divergence": True},
            "trend_label": "回调段",
        }})
        assert result["direction"] == 1  # 底背驰优先, 不是回调段


class TestMomentumToSignal:
    """动量信号标准化测试。"""

    def setup_method(self):
        from fusion_core import _momentum_to_signal
        self._fn = _momentum_to_signal

    def test_bullish_strong(self):
        fn = self._fn
        result = fn({"momentum": {"score": 72, "direction": "bullish", "signals": ["MACD金叉", "ADX强趋势"]}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # score 72: >= 65 → 0.6, < 75 → not 0.8

    def test_bullish_medium(self):
        fn = self._fn
        result = fn({"momentum": {"score": 60, "direction": "neutral", "signals": ["MACD柱为正"]}})
        # direction_str="neutral" → 方向 = 0
        assert result["direction"] == 0
        # score 60: >= 60 → 0.5
        assert result["confidence"] == 0.5

    def test_bearish_strong(self):
        fn = self._fn
        result = fn({"momentum": {"score": 25, "direction": "bearish", "signals": ["MACD死叉"]}})
        assert result["direction"] == -1
        # score 25: <= 25 → 0.8, but direction="bearish" with score<=45 → min(0.8, 0.4) = 0.4
        assert result["confidence"] == 0.4

    def test_neutral(self):
        fn = self._fn
        result = fn({"momentum": {"score": 50, "direction": "neutral", "signals": []}})
        assert result["direction"] == 0
        # score 50 V-底部: 0.2
        assert result["confidence"] == 0.2

    def test_conflict_bullish_with_low_score(self):
        """direction=bullish 但 score 很低 → 降级置信度。"""
        fn = self._fn
        result = fn({"momentum": {"score": 35, "direction": "bullish", "signals": ["RSI回升"]}})
        assert result["direction"] == 1  # 方向仍由 direction_str 决定
        assert result["confidence"] <= 0.4  # 冲突时降为不超过 0.4

    def test_empty_input(self):
        fn = self._fn
        result = fn({})
        assert result["direction"] == 0
        assert result["reason"] == "动量中性"

    def test_signals_in_reason(self):
        fn = self._fn
        result = fn({"momentum": {"score": 65, "direction": "bullish", "signals": ["A", "B", "C"]}})
        assert "B" in result["reason"]
        assert "C" in result["reason"]  # 最后两个信号


class TestScoreToConfidence:
    """分数→置信度映射测试。"""

    def setup_method(self):
        from fusion_core import _score_to_confidence
        self._fn = _score_to_confidence

    def test_strong_bearish_25(self):
        assert self._fn(25) == 0.8

    def test_weak_bearish_35(self):
        assert self._fn(35) == 0.6

    def test_very_weak_40(self):
        assert self._fn(40) == 0.5

    def test_weak_gap_50(self):
        # V-底: score 50 → 0.2 (最低置信度)
        assert abs(self._fn(50) - 0.2) < 1e-10

    def test_gap_45(self):
        # V-左侧: score 45 → 0.2 + 5/10*0.3 = 0.35
        assert abs(self._fn(45) - 0.35) < 1e-10

    def test_gap_60(self):
        # score >= 60 → 0.5
        assert self._fn(60) == 0.5

    def test_medium_65(self):
        assert self._fn(65) == 0.6

    def test_strong_bullish_75(self):
        assert self._fn(75) == 0.8

    def test_very_strong_90(self):
        assert self._fn(90) == 0.8  # capped at 0.8

    def test_invalid_type(self):
        assert self._fn(None) == 0.2
        assert self._fn("abc") == 0.2


class TestWyckoffToSignal:
    """威科夫信号标准化测试。"""

    def setup_method(self):
        from fusion_core import _wyckoff_to_signal
        self._fn = _wyckoff_to_signal

    def test_spring(self):
        fn = self._fn
        result = fn({"wyckoff": {"spring_signal": True, "spring_reason": "跌破支撑后收回"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.7
        assert "弹簧" in result["reason"]

    def test_spring_with_bullish_div(self):
        fn = self._fn
        result = fn({"wyckoff": {"spring_signal": True, "spring_reason": "x", "bullish_volume_divergence": True}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.75  # Spring + bullish_div 叠加

    def test_bullish_divergence(self):
        fn = self._fn
        result = fn({"wyckoff": {"bullish_volume_divergence": True, "bearish_volume_divergence": False}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.5

    def test_bearish_divergence(self):
        fn = self._fn
        result = fn({"wyckoff": {"bullish_volume_divergence": False, "bearish_volume_divergence": True}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5

    def test_upthrust(self):
        fn = self._fn
        result = fn({"wyckoff": {"upthrust_signal": True, "upthrust_reason": "突破阻力后回落"}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.6

    def test_no_signal(self):
        fn = self._fn
        result = fn({"wyckoff": {}})
        assert result["direction"] == 0
        assert result["confidence"] == 0.2

    def test_empty_input(self):
        fn = self._fn
        result = fn({})
        assert result["direction"] == 0

    def test_spring_priority_over_divergence(self):
        """Spring 优先于背离信号。"""
        fn = self._fn
        result = fn({"wyckoff": {"spring_signal": True, "bearish_volume_divergence": True}})
        assert result["direction"] == 1  # Spring 决定方向


class TestRegimeWeights:
    """Regime 权重矩阵测试。"""

    def setup_method(self):
        from fusion_regime import get_regime_weights
        self._fn = get_regime_weights

    def test_normal(self):
        w = self._fn("正常")
        assert w["chan"] == 0.3
        assert w["momentum"] == 0.45
        assert w["wyckoff"] == 0.25
        assert sum(w.values()) == 1.0

    def test_weak(self):
        w = self._fn("偏弱")
        assert w["chan"] == 0.5
        assert w["momentum"] == 0.15
        assert w["wyckoff"] == 0.35
        assert sum(w.values()) == 1.0

    def test_very_bad(self):
        w = self._fn("很差")
        assert w["chan"] == 0.0
        assert w["momentum"] == 0.0
        assert w["wyckoff"] == 0.0

    def test_unknown_fallback(self):
        w = self._fn("未知")
        assert w["chan"] == 0.3
        assert w["momentum"] == 0.45
        assert w["wyckoff"] == 0.25

    def test_unknown_regime_fallback(self):
        """未知 Regime 应 fallback 到默认配置。"""
        from fusion_regime import get_regime_weights
        w = get_regime_weights("未知状态")
        assert w == get_regime_weights("正常")


class TestScoreToAction:
    """加权分数→动作映射测试。"""

    def setup_method(self):
        from fusion_regime import score_to_action
        self._fn = score_to_action

    def test_bear_reject(self):
        fn = self._fn
        result = fn(0.5, 0, "很差")
        assert "空仓" in result
        assert "一票否决" in result

    def test_high_bullish(self):
        fn = self._fn
        result = fn(0.8, 0, "正常")
        assert "半仓" in result

    def test_healthy_buy(self):
        fn = self._fn
        result = fn(0.3, 0, "正常")
        assert "增持" in result

    def test_neutral(self):
        fn = self._fn
        result = fn(0.0, 0, "正常")
        assert "观望" in result

    def test_moderate_bearish(self):
        fn = self._fn
        result = fn(-0.15, 0, "正常")
        assert "减仓" in result

    def test_very_bearish(self):
        fn = self._fn
        result = fn(-0.5, 0, "正常")
        assert "空仓" in result

    def test_disagreement_reduces_action(self):
        """分歧大时降档: 即使加权分高也降。"""
        fn = self._fn
        result = fn(0.6, 3, "正常")
        # 分歧 > 阈值 → 用分歧映射表, 0.6 >= 0.4 → "半仓试 (多方主导但有分歧)"
        assert "有分歧" in result


class TestComputeConfidence:
    """综合置信度计算测试。"""

    def setup_method(self):
        from fusion_regime import compute_confidence
        self._fn = compute_confidence

    def test_high_confidence(self):
        conf = self._fn(0.5, 0, {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25})
        assert conf > 0.5

    def test_zero_score(self):
        # score=0, 无分歧, 等权重 → base=0, 零惩罚, 零集中 = 0
        conf = self._fn(0.0, 0, {"chan": 0.333, "momentum": 0.333, "wyckoff": 0.334})
        assert conf >= 0.0  # 底线为 0, 不崩溃

    def test_high_disagreement(self):
        conf = self._fn(0.8, 2, {"chan": 0.3, "momentum": 0.45, "wyckoff": 0.25})
        # 全部分歧 (direction -1/0/1) → 0~2 → 惩罚最大
        assert conf < self._fn(0.8, 0, {"chan": 0.5, "momentum": 0.5, "wyckoff": 0.0})

    def test_clamped_at_095(self):
        conf = self._fn(1.0, 0, {"chan": 0.9, "momentum": 0.05, "wyckoff": 0.05})
        assert conf <= 0.95

    def test_clamped_at_0(self):
        conf = self._fn(-1.0, 2, {"chan": 0.0, "momentum": 0.0, "wyckoff": 0.0})
        assert conf >= 0.0


class TestMergeDecisions:
    """完整融合决策测试。"""

    def test_all_agree_bullish(self):
        from fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 72, "direction": "bullish", "signals": ["MACD金叉"]}}
        wyk = {"wyckoff": {"spring_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="正常")

        assert isinstance(result["action"], str)
        assert result["regime"] == "正常"
        assert result["disagreement"] == 0  # 全部看多
        assert "chan" in result["signals_detail"]
        assert "momentum" in result["signals_detail"]
        assert "wyckoff" in result["signals_detail"]

    def test_conflict(self):
        from fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 20, "direction": "bearish", "signals": ["MACD死叉"]}}
        wyk = {"wyckoff": {"upthrust_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="正常")

        # 缠论看多, 动量看空, 威科夫看空 → disagreement = 2
        assert result["disagreement"] == 2

    def test_bear_market_veto(self):
        from fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 80, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {"spring_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="很差")

        assert result["disagreement"] == 0

    def test_empty_inputs(self):
        from fusion_core import merge_decisions
        result = merge_decisions({}, {}, {}, regime="正常")
        assert isinstance(result["action"], str)

    def test_exception_handling_in_standardization(self):
        from fusion_core import merge_decisions
        # _chan_to_signal handles invalid input gracefully (type check, no exception)
        # so confidence stays 0.3 (default "no signal"), not 0.0
        result = merge_decisions("not_a_dict", {}, {}, regime="正常")
        assert result["signals_detail"]["chan"]["direction"] == 0
        assert result["signals_detail"]["chan"]["confidence"] == 0.3  # 无信号默认值

    def test_log_only_action(self):
        import os
        original = os.environ.get("FUSION_LOG_ONLY")

        # 默认 FUSION_LOG_ONLY=true
        os.environ["FUSION_LOG_ONLY"] = "true"
        # Reimport to pick up new env
        import importlib
        import fusion_core
        importlib.reload(fusion_core)
        from fusion_core import merge_decisions

        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 72, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {"spring_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="正常")

        # 日志模式下 action 被覆盖
        assert "日志模式" in result["action"]

        # 恢复
        if original is None:
            os.environ.pop("FUSION_LOG_ONLY", None)
        else:
            os.environ["FUSION_LOG_ONLY"] = original
        importlib.reload(fusion_core)


class TestIntegrationDataFlow:
    """测试融合层与现有代码的数据流兼容性。"""

    def test_chan_nested_structure(self):
        """levels["chanlun"] 是嵌套的: {"chanlun": {...}} → chanlun_strategy 返回的是 {"chanlun": {...}}"""
        from fusion_core import _chan_to_signal

        # 模拟 run_all() 返回的 levels["chanlun"] 结构
        levels_chanlun = {
            "chanlun": {
                "buy_points": [{"type": "二类买", "price": 27, "confidence": 2}],
                "trend_label": "拉升段",
                "divergence": {"bottom_divergence": False, "top_divergence": False},
            }
        }

        result = _chan_to_signal(levels_chanlun)
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # 二类买

    def test_momentum_nested_structure(self):
        from fusion_core import _momentum_to_signal

        levels_momentum = {"momentum": {"score": 72, "direction": "bullish", "signals": ["A"]}}
        result = _momentum_to_signal(levels_momentum)
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # score 72: >= 65, < 75

    def test_wyckoff_nested_structure(self):
        from fusion_core import _wyckoff_to_signal

        levels_wyckoff = {"wyckoff": {"spring_signal": True, "spring_reason": "test"}}
        result = _wyckoff_to_signal(levels_wyckoff)
        assert result["direction"] == 1
        assert result["confidence"] == 0.7


class TestPhase3Features:
    """Comprehensive unit tests for Phase 3: priority overrides, conflict resolutions, and adaptive parameters."""

    def test_scenario_priority_filter_bottom(self):
        """Under pos_pct <= 0.3, weights should dynamically adjust to {"chan": 0.45, "momentum": 0.20, "wyckoff": 0.35}."""
        from fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 50, "direction": "neutral", "signals": []}}
        wyk = {"wyckoff": {}}

        # Test low price in 20-day high-low range
        bars = [
            {"low": 10.0, "high": 20.0},
            {"low": 11.0, "high": 21.0},
        ]
        # pos_pct = (11.0 - 10.0) / (21.0 - 10.0) = 1.0 / 11.0 = 0.09 <= 0.3
        result = merge_decisions(chan, mom, wyk, regime="正常", current_price=11.0, bars=bars)
        assert result["weights_used"] == {"chan": 0.45, "momentum": 0.20, "wyckoff": 0.35}

    def test_scenario_priority_filter_top(self):
        """Under pos_pct >= 0.7, weights should dynamically adjust to {"chan": 0.20, "momentum": 0.55, "wyckoff": 0.25}."""
        from fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 50, "direction": "neutral", "signals": []}}
        wyk = {"wyckoff": {}}

        bars = [
            {"low": 10.0, "high": 20.0},
        ]
        # pos_pct = (18.0 - 10.0) / (20.0 - 10.0) = 8.0 / 10.0 = 0.8 >= 0.7
        result = merge_decisions(chan, mom, wyk, regime="正常", current_price=18.0, bars=bars)
        assert result["weights_used"] == {"chan": 0.20, "momentum": 0.55, "wyckoff": 0.25}

    def test_belief_priority_conflict_resolution_bullish_veto(self):
        """Strong bullish veto signal (Chanlun buy points / bottom divergence, Wyckoff Spring) overrides disagreement and vetos Momentum bearish noise."""
        from fusion_core import merge_decisions
        # Chan has a strong bullish signal: 一类买
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "数据不足"}}
        # Momentum has bearish noise: direction bearish, score 20
        mom = {"momentum": {"score": 20, "direction": "bearish", "signals": ["MACD死叉"]}}
        wyk = {"wyckoff": {}}

        # disagreement unmitigated is 2, but overridden to 0 by bullish veto
        result = merge_decisions(chan, mom, wyk, regime="正常")
        assert "半仓试" in result["action"] or "增持" in result["action"]
        assert result["action"] != "观望 (信号冲突)"

    def test_belief_priority_conflict_resolution_bearish_veto(self):
        """Strong bearish veto signal (Chanlun top divergence / 1st sell, Wyckoff Upthrust) overrides disagreement and vetos Momentum bullish noise."""
        from fusion_core import merge_decisions
        # Chan has a strong bearish signal: 顶背驰
        chan = {"chanlun": {"buy_points": [], "divergence": {"top_divergence": True}, "trend_label": "数据不足"}}
        # Momentum has bullish noise: direction bullish, score 80
        mom = {"momentum": {"score": 80, "direction": "bullish", "signals": ["MACD金叉"]}}
        wyk = {"wyckoff": {}}

        result = merge_decisions(chan, mom, wyk, regime="正常")
        assert "减仓" in result["action"] or "空仓" in result["action"]
        assert result["action"] != "观望 (信号冲突)"

    def test_regime_multipliers_adaptive(self):
        """Test multipliers adjustments based on Regime in structure_core."""
        from structure_core import _theory_multipliers

        # Test normal market (正常) → Widen low buy zone, Tighten breakout confirmation buffer
        mult_normal = _theory_multipliers({"regime": "正常"})
        assert mult_normal["zone_width"] == 1.2
        assert mult_normal["confirm_buffer"] == 0.8
        assert mult_normal["stop_buffer"] == 1.0

        # Test weak market (偏弱 / 很差) → Tighten stop loss buffer, Widen breakout confirmation buffer
        mult_weak = _theory_multipliers({"regime": "偏弱"})
        assert mult_weak["stop_buffer"] == 0.8
        assert mult_weak["confirm_buffer"] == 1.3
