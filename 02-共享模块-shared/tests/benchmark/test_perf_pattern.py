from trader_shared.pattern_core import detect_pattern
from .conftest import generate_bars, run_benchmark


def test_detect_pattern_timing(capsys):
    results = run_benchmark(detect_pattern, lambda n: _to_args(generate_bars(n)))
    with capsys.disabled():
        print()
        print("| 模块 | 函数 | 100根 | 500根 | 1000根 | 增长模式 |")
        print("|------|------|-------|-------|--------|----------|")
        _100 = results.get(100, 0) * 1000
        _500 = results.get(500, 0) * 1000
        _1000 = results.get(1000, 0) * 1000
        ratio = round(_1000 / _100, 1) if _100 > 0 else 0
        growth = "O(n)" if ratio < 15 else "O(n²)" if ratio < 50 else "O(n²+)"
        print(f"| pattern | detect_pattern | {_100:.2f}ms | {_500:.2f}ms | {_1000:.2f}ms | {growth} |")


def _to_args(bars):
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]
    return (closes, highs, lows, volumes)
