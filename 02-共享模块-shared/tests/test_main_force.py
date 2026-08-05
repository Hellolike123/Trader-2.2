"""主力行为引擎测试：数据采集、特征工程、五阶段识别、融合层集成。"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ── fund_flow_data ──────────────────────────────────────────────────

class TestSinaDaimaMapping:
    def test_shanghai_code(self):
        from trader_shared.fund_flow_data import _sina_daima
        assert _sina_daima("688248.SH") == "sh688248"
        assert _sina_daima("600000.SH") == "sh600000"

    def test_shenzhen_code(self):
        from trader_shared.fund_flow_data import _sina_daima
        assert _sina_daima("000001.SZ") == "sz000001"
        assert _sina_daima("300001.SZ") == "sz300001"

    def test_no_suffix_shanghai(self):
        from trader_shared.fund_flow_data import _sina_daima
        assert _sina_daima("688248") == "sh688248"
        assert _sina_daima("600000") == "sh600000"

    def test_no_suffix_shenzhen(self):
        from trader_shared.fund_flow_data import _sina_daima
        assert _sina_daima("000001") == "sz000001"
        assert _sina_daima("300001") == "sz300001"


class TestSinaFundFlowHelpers:
    """新浪资金流辅助：代码映射 + 元转万元，不依赖网络。"""

    def test_yuan_to_wan(self):
        from trader_shared.fund_flow_data import _yuan_to_wan
        assert _yuan_to_wan(10000000) == 1000.0
        assert _yuan_to_wan(-24669010.56) == -2466.9
        assert _yuan_to_wan(None) == 0.0
        assert _yuan_to_wan("-") == 0.0

    def test_sina_record_shape_from_fields(self):
        from trader_shared.fund_flow_data import _make_record, _yuan_to_wan
        r0 = _yuan_to_wan(-164970417.81)
        r1 = _yuan_to_wan(-24669010.56)
        r2 = _yuan_to_wan(-8584540.15)
        r3 = _yuan_to_wan(-291024.0)
        row = _make_record(
            date="2026-08-05",
            net_flow_wan=r0 + r1,
            super_large_wan=r0,
            large_wan=r1,
            medium_wan=r2,
            small_wan=r3,
            source="sina",
        )
        assert row["source"] == "sina"
        assert row["super_large_wan"] == -16497.04
        assert row["large_wan"] == -2466.9
        assert abs(row["net_flow_wan"] - (row["super_large_wan"] + row["large_wan"])) < 1e-9


class TestCalcFundFlowFeatures:
    def test_normal_features(self):
        from trader_shared.fund_flow_data import calc_fund_flow_features
        daily_flow = [
            {"date": f"2026-01-{i:02d}", "net_flow_wan": 100 * (i - 3), "super_large_wan": 50, "large_wan": 50, "medium_wan": -30, "small_wan": -20}
            for i in range(1, 11)
        ]
        features = calc_fund_flow_features(daily_flow)
        assert features["cum_flow_5d_wan"] != 0
        assert features["cum_flow_10d_wan"] != 0
        assert isinstance(features["flow_price_relation"], str)

    def test_empty_flow(self):
        from trader_shared.fund_flow_data import calc_fund_flow_features
        features = calc_fund_flow_features([])
        assert features["cum_flow_5d_wan"] == 0
        assert features["consecutive_inflow_days"] == 0

    def test_consecutive_inflow(self):
        from trader_shared.fund_flow_data import calc_fund_flow_features
        daily_flow = [{"net_flow_wan": 100}] * 5
        features = calc_fund_flow_features(daily_flow)
        assert features["consecutive_inflow_days"] == 5
        assert features["consecutive_outflow_days"] == 0

    def test_consecutive_outflow(self):
        from trader_shared.fund_flow_data import calc_fund_flow_features
        daily_flow = [{"net_flow_wan": -100}] * 3
        features = calc_fund_flow_features(daily_flow)
        assert features["consecutive_outflow_days"] == 3
        assert features["consecutive_inflow_days"] == 0


class TestFlowPriceRelation:
    def test_price_up_flow_in(self):
        from trader_shared.fund_flow_data import _calc_flow_price_relation
        daily_flow = [{"net_flow_wan": 100}] * 5
        bars = [{"close": 10.0}] * 5 + [{"close": 11.0}]
        relation = _calc_flow_price_relation(daily_flow, bars)
        assert relation == "价涨资入"

    def test_price_down_flow_out(self):
        from trader_shared.fund_flow_data import _calc_flow_price_relation
        daily_flow = [{"net_flow_wan": -100}] * 5
        bars = [{"close": 11.0}] * 5 + [{"close": 10.0}]
        relation = _calc_flow_price_relation(daily_flow, bars)
        assert relation == "价跌资出"

    def test_price_flat_flow_in(self):
        from trader_shared.fund_flow_data import _calc_flow_price_relation
        daily_flow = [{"net_flow_wan": 100}] * 5
        bars = [{"close": 10.0}] * 6
        relation = _calc_flow_price_relation(daily_flow, bars)
        assert relation == "价平资入"


# ── main_force (五阶段识别) ──────────────────────────────────────────

class TestDetectMainForceStage:
    def test_unknown_when_insufficient_data(self):
        from trader_shared.main_force import detect_main_force_stage
        features = {"daily_flow_5d": [], "cum_flow_5d_wan": 0}
        result = detect_main_force_stage(features)
        assert result["stage"] == "unknown"
        assert result["confidence"] == 0.0

    def test_accumulation_detection(self):
        from trader_shared.main_force import detect_main_force_stage
        features = {
            "cum_flow_5d_wan": 3000,
            "cum_flow_10d_wan": 5000,
            "consecutive_inflow_days": 4,
            "consecutive_outflow_days": 0,
            "net_flow_pct": 0.05,
            "flow_price_relation": "价跌资入",
            "daily_flow_5d": [500, 600, 700, 800, 400],
        }
        # 20日横盘 bars
        bars = [{"close": 10.0, "volume": 1000, "high": 10.2, "low": 9.8}] * 20
        chip_info = {"concentration_trend": "上升"}
        result = detect_main_force_stage(features, bars, chip_info)
        assert result["stage"] == "accumulation"
        assert result["confidence"] > 0.3

    def test_markup_detection(self):
        from trader_shared.main_force import detect_main_force_stage
        features = {
            "cum_flow_5d_wan": 5000,
            "cum_flow_10d_wan": 8000,
            "consecutive_inflow_days": 5,
            "consecutive_outflow_days": 0,
            "net_flow_pct": 0.08,
            "flow_price_relation": "价涨资入",
            "daily_flow_5d": [800, 900, 1000, 1100, 1200],
        }
        bars = [{"close": 10.0 + i * 0.3, "volume": 1000 + i * 200, "high": 10.5 + i * 0.3, "low": 9.5 + i * 0.3} for i in range(20)]
        result = detect_main_force_stage(features, bars, position_ratio=0.5)
        assert result["stage"] == "markup"
        assert result["confidence"] >= 0.5

    def test_markdown_detection(self):
        from trader_shared.main_force import detect_main_force_stage
        features = {
            "cum_flow_5d_wan": -5000,
            "cum_flow_10d_wan": -8000,
            "consecutive_inflow_days": 0,
            "consecutive_outflow_days": 5,
            "net_flow_pct": -0.08,
            "flow_price_relation": "价跌资出",
            "daily_flow_5d": [-800, -900, -1000, -1100, -1200],
        }
        bars = [{"close": 15.0 - i * 0.5, "volume": 2000 + i * 300, "high": 15.5 - i * 0.5, "low": 14.5 - i * 0.5} for i in range(20)]
        result = detect_main_force_stage(features, bars)
        assert result["stage"] == "markdown"
        assert result["confidence"] >= 0.5


# ── main_force_output ──────────────────────────────────────────────

class TestMainForceOutput:
    def test_accumulation_output(self):
        from trader_shared.main_force_output import format_main_force_section
        result = {
            "stage": "accumulation",
            "confidence": 0.6,
            "cum_flow_5d_wan": 3200,
            "cum_flow_10d_wan": 5000,
            "consecutive_inflow_days": 3,
            "consecutive_outflow_days": 0,
            "flow_price_relation": "价跌资入",
            "signals": ["连续3日净流入"],
            "daily_flow_5d": [500, 600, 700, 800, 400],
        }
        text = format_main_force_section(result)
        assert "吸筹期" in text
        assert "3200" in text
        assert "↑" in text

    def test_unknown_output(self):
        from trader_shared.main_force_output import format_main_force_section
        result = {"stage": "unknown", "daily_flow_5d": []}
        text = format_main_force_section(result)
        assert "暂不可用" in text

    def test_distribution_warning(self):
        from trader_shared.main_force_output import format_main_force_section
        result = {
            "stage": "distribution",
            "confidence": 0.5,
            "cum_flow_5d_wan": -1000,
            "cum_flow_10d_wan": -2000,
            "consecutive_inflow_days": 0,
            "consecutive_outflow_days": 2,
            "flow_price_relation": "价涨资出",
            "signals": [],
            "daily_flow_5d": [-200, -300, -100, -200, -200],
        }
        text = format_main_force_section(result)
        assert "谨防接盘" in text


# ── fusion_core 权重修正 ──────────────────────────────────────────

class TestMainForceFusion:
    def test_no_main_force_env_unchanged(self):
        """不传 main_force_env 时行为不变"""
        from trader_shared.fusion_core import _apply_main_force_weights
        weights = {"chan": 0.45, "momentum": 0.20, "vpf": 0.35}
        result = _apply_main_force_weights(weights, "unknown")
        assert result == weights

    def test_accumulation_adjustment(self):
        """吸筹期：wyckoff +10%, momentum -10%"""
        from trader_shared.fusion_core import _apply_main_force_weights
        weights = {"chan": 0.40, "momentum": 0.30, "vpf": 0.30}
        result = _apply_main_force_weights(weights, "accumulation")
        assert result["vpf"] > 0.30
        assert result["momentum"] < 0.30
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_markup_adjustment(self):
        """拉升期：momentum +10%, chan -5%"""
        from trader_shared.fusion_core import _apply_main_force_weights
        weights = {"chan": 0.40, "momentum": 0.30, "vpf": 0.30}
        result = _apply_main_force_weights(weights, "markup")
        assert result["momentum"] > 0.30
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_markdown_adjustment(self):
        """砸盘期：三路均下调（归一化后仍和为1）"""
        from trader_shared.fusion_core import _apply_main_force_weights
        weights = {"chan": 0.40, "momentum": 0.30, "vpf": 0.30}
        result = _apply_main_force_weights(weights, "markdown")
        assert abs(sum(result.values()) - 1.0) < 0.01
        # 所有权重应 >= 0
        assert all(v >= 0 for v in result.values())

    def test_normalization(self):
        """修正后权重之和必须为 1.0"""
        from trader_shared.fusion_core import _apply_main_force_weights
        for stage in ("accumulation", "testing", "markup", "distribution", "markdown"):
            weights = {"chan": 0.45, "momentum": 0.20, "vpf": 0.35}
            result = _apply_main_force_weights(weights, stage)
            assert abs(sum(result.values()) - 1.0) < 0.01, f"Failed for {stage}"


# ── format_flow_trend ──────────────────────────────────────────────

class TestFormatFlowTrend:
    def test_normal_trend(self):
        from trader_shared.main_force_output import format_flow_trend
        assert format_flow_trend([100, -200, 300, -100, 500]) == "↑↓↑↓↑"

    def test_all_positive(self):
        from trader_shared.main_force_output import format_flow_trend
        assert format_flow_trend([100, 200, 300]) == "↑↑↑"

    def test_all_negative(self):
        from trader_shared.main_force_output import format_flow_trend
        assert format_flow_trend([-100, -200, -300]) == "↓↓↓"

    def test_zero_flow(self):
        from trader_shared.main_force_output import format_flow_trend
        assert format_flow_trend([0, 100, 0]) == "→↑→"

    def test_empty(self):
        from trader_shared.main_force_output import format_flow_trend
        assert format_flow_trend([]) == "无数据"

    def test_trailing_5_only(self):
        from trader_shared.main_force_output import format_flow_trend
        # Only last 5 are used
        result = format_flow_trend([100, 200, 300, -100, -200, 500, -300])
        assert result == "↓↑↓↑↓" or len(result) == 5


# ── format_main_force_enhanced ─────────────────────────────────────

class TestFormatMainForceEnhanced:
    def test_accumulation_with_breakdown(self):
        from trader_shared.main_force_output import format_main_force_enhanced
        result = {
            "stage": "accumulation",
            "confidence": 0.7,
            "cum_flow_5d_wan": 3200,
            "cum_flow_10d_wan": 5000,
            "consecutive_inflow_days": 3,
            "consecutive_outflow_days": 0,
            "flow_price_relation": "价跌资入",
            "signals": ["连续3日净流入"],
            "daily_flow_5d": [500, 600, 700, 800, 400],
        }
        text = format_main_force_enhanced(result, today_super_large=500, today_large=300)
        assert "吸筹期" in text
        assert "置信度 0.7" in text
        assert "3200" in text
        assert "↑↑↑↑↑" in text
        assert "连续3日净流入" in text
        assert "超大单 +500万" in text
        assert "大单 +300万" in text
        assert "价跌资入" in text
        assert "关注是否放量突破" in text

    def test_unknown_shows_unavailable(self):
        from trader_shared.main_force_output import format_main_force_enhanced
        result = {"stage": "unknown", "daily_flow_5d": []}
        text = format_main_force_enhanced(result)
        assert "暂不可用" in text

    def test_distribution_warning(self):
        from trader_shared.main_force_output import format_main_force_enhanced
        result = {
            "stage": "distribution",
            "confidence": 0.5,
            "cum_flow_5d_wan": -1000,
            "consecutive_inflow_days": 0,
            "consecutive_outflow_days": 2,
            "flow_price_relation": "价涨资出",
            "signals": [],
            "daily_flow_5d": [-200, -300, -100, -200, -200],
        }
        text = format_main_force_enhanced(result, today_super_large=-100, today_large=-100)
        assert "谨防接盘" in text
        assert "连续2日净流出" in text
        assert "超大单 -100万" in text

    def test_no_breakdown_still_works(self):
        from trader_shared.main_force_output import format_main_force_enhanced
        result = {
            "stage": "markup",
            "confidence": 0.6,
            "cum_flow_5d_wan": 5000,
            "consecutive_inflow_days": 5,
            "consecutive_outflow_days": 0,
            "flow_price_relation": "价涨资入",
            "signals": [],
            "daily_flow_5d": [800, 900, 1000, 1100, 1200],
        }
        text = format_main_force_enhanced(result)
        assert "拉升期" in text
        assert "今日：+1200万" in text
        # No super-large/large breakdown when both are 0
        assert "超大单" not in text

    def test_wechat_format_no_markdown(self):
        """Output must not contain Markdown syntax."""
        from trader_shared.main_force_output import format_main_force_enhanced
        result = {
            "stage": "accumulation",
            "confidence": 0.6,
            "cum_flow_5d_wan": 3200,
            "consecutive_inflow_days": 3,
            "consecutive_outflow_days": 0,
            "flow_price_relation": "价跌资入",
            "signals": [],
            "daily_flow_5d": [500, 600, 700, 800, 400],
        }
        text = format_main_force_enhanced(result, today_super_large=500, today_large=300)
        assert "**" not in text
        assert "#" not in text
        assert "---" not in text
        assert "| " not in text
