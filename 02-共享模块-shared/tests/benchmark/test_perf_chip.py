from trader_shared.chip_distribution import calc_chip_distribution
from .conftest import generate_bars, run_benchmark


def test_calc_chip_distribution_timing(capsys):
    results = run_benchmark(calc_chip_distribution, lambda n: generate_bars(n))
    with capsys.disabled():
        print()
        print("| 模块 | 函数 | 100根 | 500根 | 1000根 | 增长模式 |")
        print("|------|------|-------|-------|--------|----------|")
        _100 = results.get(100, 0) * 1000
        _500 = results.get(500, 0) * 1000
        _1000 = results.get(1000, 0) * 1000
        ratio = round(_1000 / _100, 1) if _100 > 0 else 0
        growth = "O(n)" if ratio < 15 else "O(n²)" if ratio < 50 else "O(n²+)"
        print(f"| chip | calc_chip_distribution | {_100:.2f}ms | {_500:.2f}ms | {_1000:.2f}ms | {growth} |")
