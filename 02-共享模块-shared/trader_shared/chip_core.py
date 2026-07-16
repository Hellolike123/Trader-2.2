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


def format_chip_position_light(
    current: float,
    peaks: list[dict[str, Any]] | None = None,
    migration: dict[str, Any] | None = None,
    profit_pct: float | None = None,
) -> str:
    """筹码灯（方案 C，极短，只展示不进 fusion）。

    固定三问 + 告警可选：
      筹码：支撑弱 · 阻力 44.4 · 套牢面大
      筹码：支撑 50.2 · 阻力 58.0 · 套牢面中性 · 底部松动
    无警报时不写「底部稳定/未搬家」。
    """
    cur = float(current or 0)
    if cur <= 0:
        return ""  # 调用方跳过空行

    clean: list[dict[str, Any]] = []
    for p in peaks or []:
        if not isinstance(p, dict):
            continue
        try:
            px = float(p.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        try:
            share = float(p.get("share_of_total") or 0)
        except (TypeError, ValueError):
            share = 0.0
        clean.append({"price": px, "share": share})

    # 无峰且无获利盘：不输出（避免「暂无数据」噪声）
    if not clean and profit_pct is None:
        return ""

    below = sorted([x for x in clean if x["price"] < cur], key=lambda x: x["price"])
    above = sorted([x for x in clean if x["price"] > cur], key=lambda x: x["price"])

    parts: list[str] = []

    # 1) 支撑
    if below:
        sup = below[-1]  # 最近下方
        dist_pct = abs(cur - sup["price"]) / cur * 100
        if dist_pct <= 3:
            parts.append(f"支撑 {sup['price']:.2f}")
        elif dist_pct <= 10:
            parts.append(f"支撑 {sup['price']:.2f}")
        else:
            # 太远：有峰但撑不住现价叙事 → 支撑弱
            parts.append("支撑弱")
    else:
        parts.append("支撑弱")

    # 2) 阻力
    if above:
        res = above[0]
        dist_pct = (res["price"] - cur) / cur * 100
        if dist_pct <= 12:
            parts.append(f"阻力 {res['price']:.2f}")
        else:
            parts.append(f"阻力远 {res['price']:.2f}")
    else:
        parts.append("阻力弱")

    # 3) 套牢面（由获利盘映射；中性也写短标签，保证三问齐全）
    if profit_pct is not None:
        try:
            pp = float(profit_pct)
            if pp < 20:
                parts.append("套牢面大")
            elif pp > 80:
                parts.append("套牢面小")
            else:
                parts.append("套牢面中性")
        except (TypeError, ValueError):
            pass

    # 4) 仅告警时追加
    mig = migration if isinstance(migration, dict) else {}
    if mig.get("has_history"):
        level = str(mig.get("warning_level") or "none")
        try:
            mp_f = float(mig.get("migration_pct") or 0)
        except (TypeError, ValueError):
            mp_f = 0.0
        if level in ("clear", "exit", "critical") or mp_f >= 50:
            parts.append("底部松动重")
        elif level in ("warning", "warn") or mp_f >= 40:
            parts.append("底部松动")

    return "筹码：" + " · ".join(parts)
