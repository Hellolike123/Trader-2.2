import sys
from pathlib import Path
import pytest

# Ensure candidates directory and shared modules are in python path
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
CANDIDATE = SHARED / "02-候选逻辑-candidate"
MARKET = SHARED / "01-行情数据-market-data"
CONTRACTS = SHARED / "03-输出校验-contracts"
TRADER_SCRIPTS = Path(__file__).resolve().parents[2] / "01-功能包-packages/01-单票分析-trader/scripts"

for p in (SHARED, CANDIDATE, MARKET, CONTRACTS, TRADER_SCRIPTS):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

from structure_core import build_structure_context

def test_fibonacci_golden_levels_calculation():
    # Prepare dummy BarData and MA/ATR mock structures
    dummy_bars = [{"close": 10.0, "high": 10.5, "low": 9.5, "open": 10.0} for _ in range(30)]
    
    # Mock a chan_result with strokes
    # We'll create a swing from 8.00 to 12.00
    # Retracements:
    # 38.2% = 12.00 - 4.00 * 0.382 = 10.47
    # 50.0% = 12.00 - 4.00 * 0.500 = 10.00
    # 61.8% = 12.00 - 4.00 * 0.618 = 9.53
    chan_result_up = {
        "strokes": [
            {"direction": "up", "start_price": 8.00, "end_price": 12.00}
        ]
    }
    
    quote = {"low": 9.80, "high": 10.20, "current": 10.10, "pre_close": 10.00}
    
    # Run build_structure_context
    result = build_structure_context(
        current=10.10,
        bars=dummy_bars,
        change_pct=1.0,
        quote=quote,
        fusion_result=None,
        chan_result=chan_result_up
    )
    
    # Verify fib_retrace calculations
    fib = result.get("fib_retrace")
    assert fib is not None
    assert fib["swing_low"] == 8.00
    assert fib["swing_high"] == 12.00
    assert fib["retrace_382"] == 10.47
    assert fib["retrace_500"] == 10.00
    assert fib["retrace_618"] == 9.53
    
    low_zone_lower = result["low_zone_lower"]
    low_zone_upper = result["low_zone_upper"]
    
    # Assert golden_bid matches the expected level in range or is None if none matches
    if low_zone_lower <= 10.00 <= low_zone_upper:
        assert fib["golden_bid"] == 10.00
    elif low_zone_lower <= 9.53 <= low_zone_upper:
        assert fib["golden_bid"] == 9.53
    elif low_zone_lower <= 10.47 <= low_zone_upper:
        assert fib["golden_bid"] == 10.47
    else:
        assert fib["golden_bid"] is None

def test_markdown_report_displays_golden_bid():
    from run_analysis import render_markdown
    
    # Create a test report dict
    report = {
        "name": "测试股票",
        "symbol": "000001.SZ",
        "current": 10.00,
        "change_pct": 1.5,
        "support": 9.50,
        "resistance": 11.00,
        "confirm": 10.50,
        "stop": 9.20,
        "scene": "低吸观察",
        "position_cap": 15,
        "low_zone": "9.50-9.80元",
        "fib_retrace": {
            "golden_bid": 9.65
        },
        "ma": {"ma5": "10.10", "ma10": "10.05", "ma20": "9.90", "ma30": "9.80"},
        "state_label": "低吸已触发"
    }
    
    markdown = render_markdown(report)
    assert "黄金挂单位: 9.65" in markdown
