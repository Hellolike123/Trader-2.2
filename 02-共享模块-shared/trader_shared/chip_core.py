from __future__ import annotations
from typing import Any
import logging
from trader_shared.light_data import to_float

_logger = logging.getLogger(__name__)

try:
    from trader_shared.chip_distribution import calc_chip_distribution
except ImportError:
    def calc_chip_distribution(daily, lookback=60):
        return {"peaks": [], "total_volume": 0, "current_pct": None, "mid_price": None}

try:
    from trader_shared.chip_migration_monitor import save_chip_snapshot, check_chip_migration
    _CHIP_MIGRATION_AVAILABLE = True
except ImportError:
    _CHIP_MIGRATION_AVAILABLE = False
    def save_chip_snapshot(target, chip_result, trade_date=None): pass
    def check_chip_migration(target, chip_result, bars=None):
        return {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}

def analyze_chips_and_migration(
    bars: list[dict[str, Any]],
    current_price: float,
    target: str,
    trade_date: str | None = None,
    tushare_chip_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """计算筹码分布、识别多周期支撑/阻力价格带以及计算筹码搬家监控结果。"""
    chip = None
    if tushare_chip_data:
        chip = tushare_chip_data
    else:
        try:
            chip = calc_chip_distribution(bars, lookback=60)
            chip["source"] = "internal_calc"
        except Exception as e:
            _logger.debug("Failed to calculate chip distribution: %s", e)

    if not chip:
        chip = {
            "peaks": [],
            "total_volume": 0,
            "current_pct": None,
            "mid_price": None,
            "volume_above_pct": None,
            "bin_width": 0.0,
            "effective_range": (0.0, 0.0),
            "source": "empty_fallback",
        }

    chip_peaks = sorted(chip.get("peaks", []) or [], key=lambda x: x["price"])

    # 筹码搬家监控
    chip_migration = {"migration_pct": 0, "warning_level": "none", "warning_text": "", "has_history": False}
    if _CHIP_MIGRATION_AVAILABLE and chip_peaks:
        try:
            chip_migration = check_chip_migration(target, chip, bars=bars)
            save_chip_snapshot(target, chip, trade_date=trade_date)
        except Exception as e:
            _logger.debug("Failed to check chip migration: %s", e)

    # 支撑/阻力峰值匹配
    chip_support = None
    chip_resistance = None
    if chip_peaks:
        support_peaks = [p for p in chip_peaks if p["price"] < current_price]
        if support_peaks:
            strong_near = sorted(
                [p for p in support_peaks if current_price > 0 and (current_price - p["price"]) / current_price <= 0.03],
                key=lambda p: float(p.get("share_of_total") or 0),
                reverse=True,
            )
            all_by_strong = sorted(support_peaks, key=lambda p: float(p.get("share_of_total") or 0), reverse=True)
            if all_by_strong and float(all_by_strong[0].get("share_of_total") or 0) > 2:
                chip_support = all_by_strong[0]["price"]
            elif strong_near:
                chip_support = strong_near[0]["price"]
            else:
                chip_support = support_peaks[-1]["price"]

        resistance_peaks = [p for p in chip_peaks if p["price"] > current_price]
        if resistance_peaks:
            strong_near = sorted(
                [p for p in resistance_peaks if current_price > 0 and (p["price"] - current_price) / current_price <= 0.03],
                key=lambda p: float(p.get("share_of_total") or 0),
                reverse=True,
            )
            all_by_strong = sorted(resistance_peaks, key=lambda p: float(p.get("share_of_total") or 0), reverse=True)
            if all_by_strong and float(all_by_strong[0].get("share_of_total") or 0) > 2:
                chip_resistance = all_by_strong[0]["price"]
            elif strong_near:
                chip_resistance = strong_near[0]["price"]
            else:
                chip_resistance = resistance_peaks[0]["price"]

    # 区间边界匹配
    chip_support_lower = None
    chip_support_upper = None
    chip_resistance_lower = None
    chip_resistance_upper = None

    if chip_support is not None and chip_peaks:
        matching_sup = next((p for p in chip_peaks if p["price"] == chip_support), None)
        if matching_sup and "price_lower" in matching_sup and "price_upper" in matching_sup:
            chip_support_lower = matching_sup["price_lower"]
            chip_support_upper = matching_sup["price_upper"]
        else:
            chip_support_lower = chip_support
            chip_support_upper = chip_support

    if chip_resistance is not None and chip_peaks:
        matching_res = next((p for p in chip_peaks if p["price"] == chip_resistance), None)
        if matching_res and "price_lower" in matching_res and "price_upper" in matching_res:
            chip_resistance_lower = matching_res["price_lower"]
            chip_resistance_upper = matching_res["price_upper"]
        else:
            chip_resistance_lower = chip_resistance
            chip_resistance_upper = chip_resistance

    return {
        "chip": chip,
        "chip_peaks": chip_peaks,
        "chip_support": chip_support,
        "chip_resistance": chip_resistance,
        "chip_support_lower": chip_support_lower,
        "chip_support_upper": chip_support_upper,
        "chip_resistance_lower": chip_resistance_lower,
        "chip_resistance_upper": chip_resistance_upper,
        "chip_migration": chip_migration,
    }
