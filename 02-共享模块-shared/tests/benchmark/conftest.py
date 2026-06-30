import random
import time
from functools import wraps


def timer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        return result, elapsed
    return wrapper


def generate_bars(n: int, seed: int = 42) -> list[dict]:
    random.seed(seed)
    price = 50.0
    bars = []
    for _ in range(n):
        change = random.uniform(-0.03, 0.03)
        price *= (1 + change)
        high = price * (1 + random.uniform(0, 0.02))
        low = price * (1 - random.uniform(0, 0.02))
        high = max(high, price, low)
        low = min(low, price, high)
        bars.append({
            "open": price * (1 + random.uniform(-0.01, 0.01)),
            "high": high,
            "low": low,
            "close": price,
            "volume": int(random.uniform(100000, 5000000)),
        })
    return bars


def generate_double_bottom_bars() -> list[dict]:
    closes = [
        12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 8.5,
        9, 9.5, 10, 9.5, 9, 8.5, 8.2, 8.5, 9, 9.5,
        10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5,
    ]
    return [{
        "open": c - 0.1,
        "high": c + 0.3,
        "low": c - 0.3,
        "close": c,
        "volume": 1000000,
    } for c in closes]


def generate_double_top_bars() -> list[dict]:
    closes = [
        12, 12.5, 13, 13.5, 14, 14.5, 14.8, 14.5, 14, 13.5,
        13, 12.5, 12, 12.5, 13, 13.5, 14.5, 14.8, 14.5, 14,
        13.5, 13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9,
    ]
    return [{
        "open": c - 0.1,
        "high": c + 0.3,
        "low": c - 0.3,
        "close": c,
        "volume": 1000000,
    } for c in closes]


SIZES = [100, 500, 1000]


def run_benchmark(fn, data_factory, sizes=None):
    if sizes is None:
        sizes = SIZES
    results = {}
    for n in sizes:
        if callable(data_factory):
            args = data_factory(n)
        else:
            args = data_factory
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            fn(*args) if isinstance(args, tuple) else fn(args)
            elapsed = time.perf_counter() - start
            if elapsed < best:
                best = elapsed
        results[n] = best
    return results
