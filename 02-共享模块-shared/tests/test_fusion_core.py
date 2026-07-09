#!/usr/bin/env python3
"""测试决策融合层 — 信号标准化、Regime权重、融合决策。

所有测试使用内联 mock 数据, 不依赖网络或外部 API。
"""

from __future__ import annotations

import os


class TestChanToSignal:
    """缠论信号标准化测试。"""

    def setup_method(self):
        from trader_shared.fusion_core import _chan_to_signal
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
        assert result["confidence"] == 0.55  # conf=2 → 0.55 映射

    def test_three_buy_points_priority(self):
        """多个 buy_points 时按类型真优先级（一类>二类>三类），不依赖 list 顺序。"""
        fn = self._fn
        # 列表故意把三类放前、一类放后
        result = fn({"chanlun": {
            "buy_points": [
                {"type": "三类买", "price": 26, "confidence": 1},
                {"type": "二类买", "price": 27, "confidence": 2},
                {"type": "一类买", "price": 28, "confidence": 3},
            ]
        }})
        assert result["direction"] == 1
        assert result["confidence"] == 0.8  # 一类买
        assert "一类买" in result["reason"]

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

    def test_priority_top_divergence_over_weak_buy(self):
        """粘滞二/三类买不得压过顶背驰；一类买仍优先于顶背驰。"""
        fn = self._fn
        # 二类买 + 顶背驰 → 顶背驰
        result = fn({"chanlun": {
            "buy_points": [{"type": "二类买", "price": 27, "confidence": 2}],
            "divergence": {"top_divergence": True},
        }})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5
        assert "顶背驰" in result["reason"]
        # 一类买 + 顶背驰 → 一类买
        result2 = fn({"chanlun": {
            "buy_points": [{"type": "一类买", "price": 27, "confidence": 3}],
            "divergence": {"top_divergence": True},
        }})
        assert result2["direction"] == 1
        assert result2["confidence"] == 0.8

    def test_priority_divergence_over_trend(self):
        """divergence 存在时忽略 trend_label。"""
        fn = self._fn
        result = fn({"chanlun": {
            "divergence": {"bottom_divergence": True},
            "trend_label": "回调段",
        }})
        assert result["direction"] == 1  # 底背驰优先, 不是回调段

    def test_signal_id_propagated(self):
        """E4: 买点的 signal_id 应透传到统一信号。"""
        fn = self._fn
        result = fn({"chanlun": {
            "buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3,
                            "signal_id": "abc1234567890def"}],
        }})
        assert result["signal_id"] == "abc1234567890def"

    def test_signal_id_none_when_absent(self):
        """无 signal_id 的买点，统一信号的 signal_id 应为 None。"""
        fn = self._fn
        result = fn({"chanlun": {
            "buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3}],
        }})
        assert result.get("signal_id") is None


class TestMomentumToSignal:
    """动量信号标准化测试。"""

    def setup_method(self):
        from trader_shared.fusion_core import _momentum_to_signal
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
        from trader_shared.fusion_core import _score_to_confidence
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
        # V-左侧: score 45 → 0.2 + (50-45)/10*(0.5-0.2) = 0.35 (parameterized gray zone)
        assert abs(self._fn(45) - 0.35) < 0.01

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
        from trader_shared.fusion_core import _wyckoff_to_signal
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

    def test_high_vol_spring_confidence_reduced(self):
        """高量 Spring：confidence 从 0.7 降至 0.45"""
        fn = self._fn
        result = fn({
            "wyckoff": {
                "spring_signal": True,
                "spring_reason": "放量弹簧",
                "spring_vol_class": "high_vol_warning",
            }
        })
        assert result["direction"] == 1
        assert result["confidence"] == 0.45

    def test_high_vol_spring_with_bullish_div(self):
        """高量 Spring + 看多背离：confidence ≈ 0.5"""
        fn = self._fn
        result = fn({
            "wyckoff": {
                "spring_signal": True,
                "spring_reason": "放量弹簧",
                "spring_vol_class": "high_vol_warning",
                "bullish_volume_divergence": True,
            }
        })
        assert result["direction"] == 1
        assert result["confidence"] == 0.5

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

    def test_bc_signal_bearish(self):
        """P1: BC 进入 fusion 主链，看空 conf=0.55"""
        fn = self._fn
        result = fn({"wyckoff": {"bc_signal": True, "bc_reason": "天量滞涨"}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.55
        assert "购买高潮" in result["reason"] or "天量" in result["reason"]

    def test_sow_signal_bearish(self):
        """P1: SOW 进入 fusion 主链，看空 conf=0.5"""
        fn = self._fn
        result = fn({"wyckoff": {"sow_signal": True, "sow_reason": "放量跌破支撑"}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5

    def test_bc_priority_over_ar(self):
        """BC+AR 同时时 BC 优先（净偏空，与打分一致）"""
        fn = self._fn
        result = fn({
            "wyckoff": {
                "bc_signal": True,
                "bc_reason": "购买高潮",
                "ar_signal": True,
                "ar_reason": "自动反弹",
            }
        })
        assert result["direction"] == -1
        assert result["confidence"] == 0.55

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

    # ── 新增经典信号测试 ──

    def test_ar_signal_mapping(self):
        """AR (Automatic Rally) 信号映射。"""
        fn = self._fn
        result = fn({"wyckoff": {"ar_signal": True, "ar_reason": "BC 后自动反弹，放量+3.1%"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6
        assert "自动反弹" in result["reason"]

    def test_sos_signal_mapping(self):
        """SOS (Sign of Strength) 信号映射。"""
        fn = self._fn
        result = fn({"wyckoff": {"sos_signal": True, "sos_reason": "强势突破，5连阳累计涨5.2%"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.7
        assert "强势突破" in result["reason"]

    def test_st_signal_mapping(self):
        """ST (Secondary Test) 信号映射。"""
        fn = self._fn
        result = fn({"wyckoff": {"st_signal": True, "st_reason": "Spring 支撑二次测试，缩量确认"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.5
        assert "二次测试" in result["reason"]

    def test_lps_signal_mapping(self):
        """LPS (Last Point of Support) 信号映射。"""
        fn = self._fn
        result = fn({"wyckoff": {"lps_signal": True, "lps_reason": "SOS 后缩量回调，不破前低"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.5
        assert "缩量回调" in result["reason"] or "最后支撑" in result["reason"]

    def test_sos_priority_over_ar(self):
        """SOS 优先于 AR（置信度更高）。"""
        fn = self._fn
        result = fn({"wyckoff": {"ar_signal": True, "ar_reason": "x", "sos_signal": True, "sos_reason": "y"}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.7  # SOS 的置信度

    def test_ar_priority_over_st(self):
        """AR 优先于 ST（置信度更高）。"""
        fn = self._fn
        result = fn({"wyckoff": {"st_signal": True, "ar_signal": True}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # AR 的置信度

    def test_lps_priority_over_bullish_div(self):
        """LPS 优先于看多背离。"""
        fn = self._fn
        result = fn({"wyckoff": {"lps_signal": True, "lps_reason": "SOS 后缩量回调，不破前低", "bullish_volume_divergence": True}})
        assert result["direction"] == 1
        assert result["confidence"] == 0.5  # LPS
        assert "缩量回调" in result["reason"]


class TestRegimeWeights:
    """Regime 权重矩阵测试。"""

    def setup_method(self):
        from trader_shared.fusion_regime import get_regime_weights
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
        from trader_shared.fusion_regime import get_regime_weights
        w = get_regime_weights("未知状态")
        assert w == get_regime_weights("正常")


class TestScoreToAction:
    """加权分数→动作映射测试。"""

    def setup_method(self):
        from trader_shared.fusion_regime import score_to_action
        self._fn = score_to_action

    def test_bear_reject(self):
        fn = self._fn
        # regime="很差"不再一票否决，走正常分数路径
        result = fn(0.5, 0, "很差")
        assert "半仓" in result

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
        assert "减1/3" in result

    def test_moderate_bearish_deeper(self):
        """-0.3 应该触发减仓。"""
        fn = self._fn
        result = fn(-0.3, 0, "正常")
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
        from trader_shared.fusion_regime import compute_confidence
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
        from trader_shared.fusion_core import merge_decisions
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
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 20, "direction": "bearish", "signals": ["MACD死叉"]}}
        wyk = {"wyckoff": {"upthrust_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="正常")

        # 缠论看多, 动量看空, 威科夫看空 → disagreement = 2
        assert result["disagreement"] == 2

    def test_bear_market_veto(self):
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 80, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {"spring_signal": True}}
        result = merge_decisions(chan, mom, wyk, regime="很差")

        assert result["disagreement"] == 0

    def test_empty_inputs(self):
        from trader_shared.fusion_core import merge_decisions
        result = merge_decisions({}, {}, {}, regime="正常")
        assert isinstance(result["action"], str)

    def test_signature_accepts_all_extend_kwargs(self):
        """回归：run_analysis.build_report 传给 merge_decisions 的全部 extend_* 参数
        必须在签名中存在，否则会抛 TypeError 被 except 吞掉 → 融合层异常。
        复现 Phase 2 bug: extend_northbound / extend_margin 漏加到签名。"""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 50, "direction": "neutral", "signals": []}}
        wyk = {"wyckoff": {}}
        # 与 run_analysis.py:698-703 调用点完全一致的全部 kwargs
        result = merge_decisions(
            chan, mom, wyk, regime="正常",
            extend_fundamental={"shareholder": {"status": "数据不足"}},
            extend_sentiment={"unlocks": []},
            extend_sector={"status": "无数据"},
            extend_concept={"status": "无数据"},
            extend_northbound={"status": "接口不可用"},
            extend_margin={"status": "接口不可用"},
        )
        assert isinstance(result["action"], str)
        assert "weighted_score" in result

    def test_sector_relative_strength_boost(self):
        """A3: 个股涨+板块跌 → 相对走强 → 置信度提升"""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 60, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {}}
        extend_sector = {
            "sector_name": "半导体", "sector_change_pct": -1.5,  # 板块跌
            "sector_rank": 50, "sector_total": 100, "status": "正常",
        }
        base = merge_decisions(chan, mom, wyk, regime="正常", current_change_pct=2.0)
        boosted = merge_decisions(chan, mom, wyk, regime="正常", current_change_pct=2.0,
                                 extend_sector=extend_sector)
        # 板块相对走强 → 置信度应更高
        assert boosted["confidence"] > base["confidence"]
        assert boosted["confidence"] <= 1.0

    def test_concept_hotspot_boost(self):
        """B7: 个股命中概念热点 → 置信度提升"""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 55, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {}}
        extend_concept = {
            "concept_list": ["人工智能", "芯片"], "concept_change_pct": [3.5, 2.1],
            "concept_rank": {"人工智能": {"rank": 1, "total": 300}}, "concept_total": 300,
            "status": "正常",
        }
        base = merge_decisions(chan, mom, wyk, regime="正常")
        boosted = merge_decisions(chan, mom, wyk, regime="正常", extend_concept=extend_concept)
        assert boosted["confidence"] > base["confidence"]

    def test_sector_concept_missing_degrades_gracefully(self):
        """板块/概念数据缺失时退化为原行为（不崩溃、不影响基线）"""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 55, "direction": "bullish", "signals": []}}
        wyk = {"wyckoff": {}}
        base = merge_decisions(chan, mom, wyk, regime="正常")
        with_sector_none = merge_decisions(chan, mom, wyk, regime="正常",
                                        extend_sector=None, extend_concept=None)
        assert with_sector_none["action"] == base["action"]
        assert abs(with_sector_none["confidence"] - base["confidence"]) < 1e-9

    def test_exception_handling_in_standardization(self):
        from trader_shared.fusion_core import merge_decisions
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
        import trader_shared.fusion_core
        importlib.reload(trader_shared.fusion_core)
        from trader_shared.fusion_core import merge_decisions

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
        importlib.reload(trader_shared.fusion_core)


class TestIntegrationDataFlow:
    """测试融合层与现有代码的数据流兼容性。"""

    def test_chan_nested_structure(self):
        """levels["chanlun"] 是嵌套的: {"chanlun": {...}} → chanlun_strategy 返回的是 {"chanlun": {...}}"""
        from trader_shared.fusion_core import _chan_to_signal

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
        assert result["confidence"] == 0.55  # 二类买 conf=2

    def test_momentum_nested_structure(self):
        from trader_shared.fusion_core import _momentum_to_signal

        levels_momentum = {"momentum": {"score": 72, "direction": "bullish", "signals": ["A"]}}
        result = _momentum_to_signal(levels_momentum)
        assert result["direction"] == 1
        assert result["confidence"] == 0.6  # score 72: >= 65, < 75

    def test_wyckoff_nested_structure(self):
        from trader_shared.fusion_core import _wyckoff_to_signal

        levels_wyckoff = {"wyckoff": {"spring_signal": True, "spring_reason": "test"}}
        result = _wyckoff_to_signal(levels_wyckoff)
        assert result["direction"] == 1
        assert result["confidence"] == 0.7


class TestPhase3Features:
    """Comprehensive unit tests for Phase 3: priority overrides, conflict resolutions, and adaptive parameters."""

    def test_scenario_priority_filter_bottom(self):
        """Under pos_pct <= 0.3, weights should dynamically adjust to {"chan": 0.45, "momentum": 0.20, "wyckoff": 0.35}."""
        from trader_shared.fusion_core import merge_decisions
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
        assert result["weights_used"] == {"chan": 0.44, "momentum": 0.20, "wyckoff": 0.36}

    def test_scenario_priority_filter_top(self):
        """Under pos_pct >= 0.7 AND mom_score >= 80, weights should dynamically adjust."""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 85, "direction": "bullish", "signals": ["多指标共振(强烈看多)"]}}
        wyk = {"wyckoff": {}}

        bars = [
            {"low": 10.0, "high": 20.0},
        ]
        # pos_pct = (18.0 - 10.0) / (20.0 - 10.0) = 8.0 / 10.0 = 0.8 >= 0.7
        result = merge_decisions(chan, mom, wyk, regime="正常", current_price=18.0, bars=bars)
        assert result["weights_used"] == {"chan": 0.20, "momentum": 0.56, "wyckoff": 0.24}

    def test_belief_priority_conflict_resolution_bullish_veto(self):
        """Strong bullish veto signal (Chanlun buy points / bottom divergence, Wyckoff Spring) overrides disagreement and vetos Momentum bearish noise."""
        from trader_shared.fusion_core import merge_decisions
        # Chan has a strong bullish signal: 一类买
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "数据不足"}}
        # Momentum has bearish noise: direction bearish, score 20
        mom = {"momentum": {"score": 20, "direction": "bearish", "signals": ["MACD死叉"]}}
        wyk = {"wyckoff": {}}

        # disagreement unmitigated is 2, but overridden to 0 by bullish veto
        result = merge_decisions(chan, mom, wyk, regime="正常")
        # Fix 3 后"增持"门槛提高到0.25，得分0.24落在"等转强观察"区间属正常
        # 核心断言：偏多方向（不是"观望 (信号冲突)"），且不是空仓/止损
        BULLISH_ACTIONS = {"半仓试 (多方主导)", "增持", "等转强观察", "持股观望"}
        assert result["action"] in BULLISH_ACTIONS or "半仓" in result["action"] or "增持" in result["action"] or "等转强" in result["action"]
        assert result["action"] != "观望 (信号冲突)"

    def test_belief_priority_conflict_resolution_bearish_veto(self):
        """Strong bearish veto signal (Chanlun top divergence / 1st sell, Wyckoff Upthrust) overrides disagreement and vetos Momentum bullish noise."""
        from trader_shared.fusion_core import merge_decisions
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
        from trader_shared.structure_core import _theory_multipliers

        # Test normal market (正常) → Widen low buy zone, Tighten breakout confirmation buffer
        mult_normal = _theory_multipliers({"regime": "正常"})
        assert mult_normal["zone_width"] == 1.2
        assert mult_normal["confirm_buffer"] == 0.8
        assert mult_normal["stop_buffer"] == 1.0

        # Test weak market (偏弱 / 很差) → Tighten stop loss buffer, Widen breakout confirmation buffer
        mult_weak = _theory_multipliers({"regime": "偏弱"})
        assert mult_weak["stop_buffer"] == 0.8
        assert mult_weak["confirm_buffer"] == 1.3


class TestP0Regression:
    """P0 回归测试 — 覆盖关键 bug 修复路径。"""

    def test_sell_points_一类卖(self):
        """一类卖信号应返回 direction=-1, confidence=0.8"""
        from trader_shared.fusion_core import _chan_to_signal
        result = _chan_to_signal({"chanlun": {"sell_points": [{"type": "一类卖", "price": 30}]}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.8

    def test_sell_points_二类卖(self):
        from trader_shared.fusion_core import _chan_to_signal
        result = _chan_to_signal({"chanlun": {"sell_points": [{"type": "二类卖", "price": 28}]}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5

    def test_sell_points_三类卖(self):
        from trader_shared.fusion_core import _chan_to_signal
        result = _chan_to_signal({"chanlun": {"sell_points": [{"type": "三类卖", "price": 25}]}})
        assert result["direction"] == -1
        assert result["confidence"] == 0.5

    def test_data_status_degradation(self):
        """data_status=partial 应降级 action"""
        from trader_shared.fusion_core import merge_decisions
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 80, "direction": "bullish", "signals": ["多指标共振"]}}
        wyk = {"wyckoff": {}}
        result = merge_decisions(chan, mom, wyk, regime="正常", data_status="partial")
        # partial 数据应降级 action，不应触发积极买入
        assert result["action"] not in {"半仓试 (多方主导)", "增持"}

    def test_take_profit蓄势(self):
        """蓄势期止盈应为阻力位"""
        from trader_shared.structure_core import build_structure_context
        bars = [{"close": 50, "high": 51, "low": 49, "open": 50, "volume": 1000} for _ in range(30)]
        result = build_structure_context(50.0, bars, major_stage="蓄势")
        assert result["take"] >= 50.0

    def test_take_profit衰退(self):
        """衰退期不设止盈，只靠止损退出"""
        from trader_shared.structure_core import build_structure_context
        bars = [{"close": 50, "high": 51, "low": 49, "open": 50, "volume": 1000} for _ in range(30)]
        result = build_structure_context(50.0, bars, major_stage="衰退")
        assert result["take"] is None  # 衰退期不设止盈


class TestWyckoffScoreToDirection:
    """wyckoff_score_to_direction 单元测试"""

    def setup_method(self):
        from trader_shared.fusion_core import wyckoff_score_to_direction
        self._fn = wyckoff_score_to_direction

    def test_bullish_strong(self):
        """score >= 65 → 看多"""
        fn = self._fn
        result = fn(75)
        assert result["direction"] == 1
        assert result["confidence"] == 0.75
        assert "看多" in result["reason"]
        assert result["raw_key"] == "wyckoff"

    def test_bullish_boundary(self):
        """score = 65 → 看多边界"""
        fn = self._fn
        result = fn(65)
        assert result["direction"] == 1
        assert result["confidence"] == 0.65

    def test_neutral_high(self):
        """score = 60 → 中性"""
        fn = self._fn
        result = fn(60)
        assert result["direction"] == 0
        assert result["confidence"] == 0.3
        assert "中性" in result["reason"]

    def test_neutral_mid(self):
        """score = 50 → 中性"""
        fn = self._fn
        result = fn(50)
        assert result["direction"] == 0
        assert result["confidence"] == 0.3

    def test_neutral_low(self):
        """score = 36 → 中性下边界 (35 是看空边界)"""
        fn = self._fn
        result = fn(36)
        assert result["direction"] == 0
        assert result["confidence"] == 0.3

    def test_bearish_boundary(self):
        """score = 34 → 看空边界"""
        fn = self._fn
        result = fn(34)
        assert result["direction"] == -1
        assert result["confidence"] == 0.66
        assert "看空" in result["reason"]

    def test_bearish_strong(self):
        """score = 20 → 看空"""
        fn = self._fn
        result = fn(20)
        assert result["direction"] == -1
        assert result["confidence"] == 0.80
        assert result["raw_key"] == "wyckoff"

    def test_confidence_capped_at_0_95(self):
        """confidence 上限 0.95"""
        fn = self._fn
        result_bull = fn(96)
        result_bear = fn(4)
        assert result_bull["confidence"] == 0.95
        assert result_bear["confidence"] == 0.95


class TestFundFlowOutflowVeto:
    """P1-2: 大单连续流出一票否决测试。"""

    def _bullish_inputs(self):
        """返回一组看多信号输入（所有三路均看多）。"""
        chan = {"chanlun": {"buy_points": [{"type": "一类买", "price": 28}], "divergence": {}, "trend_label": "拉升段"}}
        mom = {"momentum": {"score": 72, "direction": "bullish", "signals": ["MACD金叉"]}}
        wyk = {"wyckoff": {"spring_signal": True}}
        return chan, mom, wyk

    def test_consecutive_outflow_triggers_veto(self):
        """连续3日净流出超阈值 → 覆盖看多 action 为减仓观望。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        fund_flow = {
            "consecutive_outflow_days": 3,
            "daily_flow_5d": [-600.0, -700.0, -800.0, -550.0, -650.0],
            "cum_flow_5d_wan": -3300.0,
        }
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=fund_flow)
        assert result["action"] == "资金流出，减仓观望"
        assert result.get("fund_flow_outflow_veto") is True
        assert "连续 3 日" in result.get("fund_flow_outflow_veto_msg", "")
        assert result["confidence"] <= 0.35

    def test_outflow_below_threshold_no_veto(self):
        """连续3日流出但金额未超阈值 → 不触发否决。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        fund_flow = {
            "consecutive_outflow_days": 3,
            "daily_flow_5d": [-200.0, -300.0, -100.0],
            "cum_flow_5d_wan": -600.0,
        }
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=fund_flow)
        # 每日流出 < 500万阈值，不触发否决
        assert result["action"] != "资金流出，减仓观望"
        assert result.get("fund_flow_outflow_veto") is not True

    def test_outflow_only_2_days_no_veto(self):
        """连续2日流出（不足3日）→ 不触发否决。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        fund_flow = {
            "consecutive_outflow_days": 2,
            "daily_flow_5d": [100.0, -600.0, -700.0],
            "cum_flow_5d_wan": -1200.0,
        }
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=fund_flow)
        assert result["action"] != "资金流出，减仓观望"
        assert result.get("fund_flow_outflow_veto") is not True

    def test_no_fund_flow_data_no_veto(self):
        """fund_flow_data=None 时静默跳过，不崩溃。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=None)
        assert result.get("fund_flow_outflow_veto") is not True
        # 看多 action 正常
        assert result["action"] != "资金流出，减仓观望"

    def test_empty_fund_flow_dict_no_veto(self):
        """fund_flow_data={} 空字典时静默跳过。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data={})
        assert result.get("fund_flow_outflow_veto") is not True

    def test_mixed_flow_no_veto(self):
        """近3日中有一日流入 → 不满足全部流出条件，不触发否决。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        fund_flow = {
            "consecutive_outflow_days": 3,
            "daily_flow_5d": [-700.0, -800.0, -600.0, 200.0, -700.0],
            "cum_flow_5d_wan": -1600.0,
        }
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=fund_flow)
        # 最近3日 = [-600, 200, -700]，有一日流入，不全是流出
        assert result["action"] != "资金流出，减仓观望"
        assert result.get("fund_flow_outflow_veto") is not True

    def test_already_bearish_action_not_overridden(self):
        """如果 action 已是看空类（如"空仓"），不重复覆盖。"""
        from trader_shared.fusion_core import merge_decisions
        # 全部看空
        chan = {"chanlun": {"divergence": {"top_divergence": True}, "trend_label": "数据不足"}}
        mom = {"momentum": {"score": 20, "direction": "bearish", "signals": ["MACD死叉"]}}
        wyk = {"wyckoff": {"upthrust_signal": True}}
        fund_flow = {
            "consecutive_outflow_days": 3,
            "daily_flow_5d": [-600.0, -700.0, -800.0],
            "cum_flow_5d_wan": -2100.0,
        }
        result = merge_decisions(chan, mom, wyk, regime="正常", fund_flow_data=fund_flow)
        # 空仓 action 不在 positive_actions 中，不会被覆盖
        assert result["action"] != "资金流出，减仓观望"
        # 但 veto 标记仍应为 True（因为满足条件）
        assert result.get("fund_flow_outflow_veto") is True

    def test_backward_compatible_no_fund_flow_param(self):
        """不传 fund_flow_data 参数（向后兼容）不影响行为。"""
        from trader_shared.fusion_core import merge_decisions
        chan, mom, wyk = self._bullish_inputs()
        # 不传 fund_flow_data，使用默认值 None
        result = merge_decisions(chan, mom, wyk, regime="正常")
        assert isinstance(result["action"], str)
        assert result.get("fund_flow_outflow_veto") is not True
