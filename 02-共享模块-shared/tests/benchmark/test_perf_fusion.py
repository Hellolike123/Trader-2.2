from trader_shared.fusion_core import merge_decisions
from .conftest import generate_bars, run_benchmark


def _make_input(bars):
    return (
        {"chanlun": {"buy_points": [{"type": "一类买", "price": 28.5, "confidence": 3}],
                      "divergence": {"bottom_divergence": True, "top_divergence": False}}},
        {"momentum": {"score": 72, "direction": "bullish", "signals": ["MACD金叉"]}},
        {"wyckoff": {"spring": True, "phase": "accumulation"}},
        "正常",
        30.0,
        bars,
    )


def test_merge_decisions_timing(capsys):
    results = run_benchmark(merge_decisions, lambda n: _make_input(generate_bars(n)))
    with capsys.disabled():
        print()
        print("| 模块 | 函数 | 100根 | 500根 | 1000根 | 增长模式 |")
        print("|------|------|-------|-------|--------|----------|")
        _100 = results.get(100, 0) * 1000
        _500 = results.get(500, 0) * 1000
        _1000 = results.get(1000, 0) * 1000
        ratio = round(_1000 / _100, 1) if _100 > 0 else 0
        growth = "O(n)" if ratio < 15 else "O(n²)" if ratio < 50 else "O(n²+)"
        print(f"| fusion | merge_decisions | {_100:.2f}ms | {_500:.2f}ms | {_1000:.2f}ms | {growth} |")
