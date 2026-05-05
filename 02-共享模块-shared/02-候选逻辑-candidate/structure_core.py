from __future__ import annotations

from typing import Any

from light_data import pct_change, to_float

try:
    from models import BarData, CandidateLevels, MAValues, QuoteData
except ImportError:
    BarData = dict
    CandidateLevels = dict
    MAValues = dict
    QuoteData = dict

try:
    from config import RECENT_WINDOW
except Exception:  # pragma: no cover - optional per skill
    RECENT_WINDOW = 5

try:
    from config import STRUCTURE_WINDOW
except Exception:  # pragma: no cover - optional per skill
    STRUCTURE_WINDOW = 20

try:
    from config import TAKE_PROFIT_BUFFER
except Exception:  # pragma: no cover - optional per skill
    TAKE_PROFIT_BUFFER = 1.06

MA_PERIODS = (5, 10, 20, 30)
MIN_ZONE_WIDTH_PCT = 0.005
MAX_ZONE_WIDTH_PCT = 0.012
MIN_STOP_BUFFER_PCT = 0.008
MAX_STOP_BUFFER_PCT = 0.025
MIN_CONFIRM_SPACE_PCT = 0.008
MAX_REASONABLE_MA_DISTANCE_PCT = 0.12
MA_WEIGHTS = {"ma5": 0.92, "ma10": 0.88, "ma20": 0.65, "ma30": 0.55}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def min_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def max_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def moving_average(bars: list[BarData], period: int) -> float | None:
    closes = [to_float(item.get("close")) for item in bars]
    valid = [value for value in closes if value is not None]
    if len(valid) < period:
        return None
    return sum(valid[-period:]) / period


def moving_averages(bars: list[BarData]) -> dict[str, float | None]:
    return {f"ma{period}": moving_average(bars, period) for period in MA_PERIODS}


def average_amplitude_pct(bars: list[BarData]) -> float | None:
    values: list[float] = []
    for item in bars[-STRUCTURE_WINDOW:]:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        if high is None or low is None or close is None or close <= 0 or high < low:
            continue
        values.append((high - low) / close)
    return sum(values) / len(values) if values else None


def add_level(levels: list[dict[str, Any]], name: str, value: float | None, weight: float) -> None:
    if value is None or value <= 0:
        return
    levels.append({"name": name, "price": round(value, 2), "weight": weight})


def add_ma_levels(levels: list[dict[str, Any]], current: float, ma_values: dict[str, float | None], *, below: bool) -> None:
    for name, value in ma_values.items():
        if value is None or value <= 0:
            continue
        if abs(value - current) / max(current, 1) > MAX_REASONABLE_MA_DISTANCE_PCT:
            continue
        weight = MA_WEIGHTS.get(name, 0.5)
        if below and value <= current:
            add_level(levels, name.upper(), value, weight)
        elif not below and value >= current:
            add_level(levels, name.upper(), value, weight)


def choose_level(levels: list[dict[str, Any]], current: float, *, below: bool) -> dict[str, Any]:
    if not levels:
        raise RuntimeError("candidate price levels unavailable")
    directional = [item for item in levels if (item["price"] <= current if below else item["price"] >= current)]
    candidates = directional or sorted(levels, key=lambda item: abs(float(item["price"]) - current))[:3]

    def sort_key(item: dict[str, Any]) -> tuple[float, float]:
        distance = abs(float(item["price"]) - current) / max(current, 1)
        weight = float(item.get("weight") or 0)
        return (distance / max(weight, 0.1), distance)

    return sorted(candidates, key=sort_key)[0]


def zone_position(current: float, support: float, confirm: float) -> float:
    width = max(confirm - support, current * 0.01)
    return max(0.0, min(1.0, (current - support) / width))


def build_structure_context(current: float, bars: list[BarData], change_pct: Any = None, quote: QuoteData | None = None) -> dict[str, Any]:
    recent5 = bars[-RECENT_WINDOW:] if len(bars) >= RECENT_WINDOW else bars
    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    if not recent5:
        raise RuntimeError("daily support/resistance unavailable")

    quote = quote or {}
    ma_values = moving_averages(bars)
    support_levels: list[dict[str, Any]] = []
    resistance_levels: list[dict[str, Any]] = []

    add_level(support_levels, "5日低点", min_price(recent5, "low"), 1.0)
    add_level(resistance_levels, "5日高点", max_price(recent5, "high"), 1.0)
    add_level(support_levels, "今日低点", to_float(quote.get("low")), 0.95)
    add_level(resistance_levels, "今日高点", to_float(quote.get("high")), 0.95)
    add_level(support_levels, "20日低点", min_price(recent20, "low"), 0.85)
    add_level(resistance_levels, "20日高点", max_price(recent20, "high"), 0.85)
    add_ma_levels(support_levels, current, ma_values, below=True)
    add_ma_levels(resistance_levels, current, ma_values, below=False)

    support = choose_level(support_levels, current, below=True)
    resistance = choose_level(resistance_levels, current, below=False)
    support_price = float(support["price"])
    confirm = float(resistance["price"])

    amplitude = average_amplitude_pct(recent20) or 0.02
    zone_width_pct = clamp(amplitude * 0.28, MIN_ZONE_WIDTH_PCT, MAX_ZONE_WIDTH_PCT)
    stop_buffer_pct = clamp(amplitude * 0.45, MIN_STOP_BUFFER_PCT, MAX_STOP_BUFFER_PCT)
    low_zone_lower = round(support_price, 2)
    low_zone_upper = round(support_price * (1 + zone_width_pct), 2)
    stop = round(support_price * (1 - stop_buffer_pct), 2)
    take = round(max(confirm, current) * TAKE_PROFIT_BUFFER, 2)
    position = zone_position(current, support_price, confirm)
    pressure_space_pct = (confirm - current) / current if current > 0 else 0
    below_ma = count_below_ma(current, ma_values)

    return {
        "main_support": round(support_price, 2),
        "support": round(support_price, 2),
        "support_source": support["name"],
        "resistance": round(confirm, 2),
        "resistance_source": resistance["name"],
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "ma_values": ma_values,
        "below_ma_count": below_ma,
        "avg_amplitude_pct": round(amplitude, 4),
        "zone_width_pct": round(zone_width_pct, 4),
        "stop_buffer_pct": round(stop_buffer_pct, 4),
        "low_zone_lower": low_zone_lower,
        "low_zone_upper": low_zone_upper,
        "low_zone": f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元",
        "confirm_price": round(confirm, 2),
        "sell_observe_price": round(confirm, 2),
        "hard_stop": stop,
        "take": take,
        "upside_pct": round(pct_change(current, confirm), 2),
        "downside_pct": round(abs(pct_change(current, stop)), 2),
        "position_ratio": round(position, 3),
        "pressure_space_pct": round(pressure_space_pct, 4),
    }


def count_below_ma(current: float, ma_values: dict[str, float | None]) -> int:
    return sum(1 for value in ma_values.values() if value is not None and current < value)
