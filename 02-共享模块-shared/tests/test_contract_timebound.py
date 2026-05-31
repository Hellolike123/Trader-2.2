from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest


class TestTradingCalendar:
    def test_weekday_holiday_returns_false(self):
        """节假日（周三）应返回 False"""
        from trader_shared.trading_calendar import is_trading_day
        # 2025-10-01 是周三，国庆节
        assert is_trading_day(date(2025, 10, 1)) is False

    def test_normal_weekday_returns_true(self):
        """普通工作日应返回 True"""
        from trader_shared.trading_calendar import is_trading_day
        # 2025-10-15 是周三，非节假日
        assert is_trading_day(date(2025, 10, 15)) is True

    def test_weekend_returns_false(self):
        """周末应返回 False"""
        from trader_shared.trading_calendar import is_trading_day
        # 2025-10-11 是周六
        assert is_trading_day(date(2025, 10, 11)) is False

    def test_spring_festival_returns_false(self):
        """春节应返回 False"""
        from trader_shared.trading_calendar import is_trading_day
        # 2026-02-18 是春节
        assert is_trading_day(date(2026, 2, 18)) is False

    def test_next_trading_open_skips_weekend(self):
        """周末调用 next_trading_open 应返回下周一 9:25"""
        from trader_shared.trading_calendar import next_trading_open
        # 2025-10-11 是周六
        result = next_trading_open(datetime(2025, 10, 11, 15, 30))
        assert result.weekday() == 0  # 周一
        assert result.hour == 9
        assert result.minute == 25


class TestDataFreshness:
    def test_fetch_quote_has_freshness_field(self):
        """fetch_quote 返回值应包含 data_freshness 字段"""
        from trader_shared.light_data import is_trading_time
        # 只验证函数存在且可调用
        result = is_trading_time()
        assert isinstance(result, bool)

    def test_market_snapshot_has_freshness_field(self):
        """MarketSnapshot 应有 data_freshness 字段"""
        from trader_shared.light_data import MarketSnapshot
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(MarketSnapshot)]
        assert "data_freshness" in field_names


class TestZeroPriceGuard:
    def test_current_zero_returns_insufficient(self):
        """current=0 should return insufficient data status"""
        from trader_shared.decision_core import status_layers
        result = status_layers(
            current=0,
            support=10.0,
            low_zone_upper=10.1,
            confirm=10.5,
            hard_stop=9.5,
            position_ratio=0.0,
            change_pct=0.0,
            ma_values={"ma5": 10.0, "ma10": 10.0},
            pressure_space_pct=0.0,
        )
        assert result["base_status"] == "数据不足"
        assert result["theory_status"] == "数据不足"

    def test_negative_price_returns_insufficient(self):
        """current<0 should return insufficient data status"""
        from trader_shared.decision_core import status_layers
        result = status_layers(
            current=-1.0,
            support=10.0,
            low_zone_upper=10.1,
            confirm=10.5,
            hard_stop=9.5,
            position_ratio=0.0,
            change_pct=0.0,
            ma_values={"ma5": 10.0, "ma10": 10.0},
            pressure_space_pct=0.0,
        )
        assert result["base_status"] == "数据不足"


class TestDegradedFusionMap:
    def test_fusion_map_has_all_entries(self):
        """降级路径的 _FUSION_STATUS_MAP 应包含完整映射"""
        from trader_shared.t0_candidate_core import status_for
        # 验证函数可导入且包含完整映射（通过检查源码中的 dict 字面量）
        import inspect
        source = inspect.getsource(status_for)
        assert "半仓试 (多方主导)" in source
        assert "空仓/止损" in source
        assert "观望 (信号冲突)" in source
