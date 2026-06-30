from trader_shared.momentum_core import calc_rsi, calc_macd
from .conftest import generate_bars, run_benchmark


def _closes(n):
    return [b["close"] for b in generate_bars(n)]


def test_calc_rsi_timing(capsys):
    results = run_benchmark(calc_rsi, lambda n: _closes(n))
    with capsys.disabled():
        print()
        print("| 模块 | 函数 | 100根 | 500根 | 1000根 | 增长模式 |")
        print("|------|------|-------|-------|--------|----------|")
        _100 = results.get(100, 0) * 1000
        _500 = results.get(500, 0) * 1000
        _1000 = results.get(1000, 0) * 1000
        ratio = round(_1000 / _100, 1) if _100 > 0 else 0
        growth = "O(n)" if ratio < 15 else "O(n²)" if ratio < 50 else "O(n²+)"
        print(f"| momentum | calc_rsi | {_100:.2f}ms | {_500:.2f}ms | {_1000:.2f}ms | {growth} |")


def test_calc_macd_timing(capsys):
    results = run_benchmark(calc_macd, lambda n: _closes(n))
    with capsys.disabled():
        print()
        print("| 模块 | 函数 | 100根 | 500根 | 1000根 | 增长模式 |")
        print("|------|------|-------|-------|--------|----------|")
        _100 = results.get(100, 0) * 1000
        _500 = results.get(500, 0) * 1000
        _1000 = results.get(1000, 0) * 1000
        ratio = round(_1000 / _100, 1) if _100 > 0 else 0
        growth = "O(n)" if ratio < 15 else "O(n²)" if ratio < 50 else "O(n²+)"
        print(f"| momentum | calc_macd | {_100:.2f}ms | {_500:.2f}ms | {_1000:.2f}ms | {growth} |")
