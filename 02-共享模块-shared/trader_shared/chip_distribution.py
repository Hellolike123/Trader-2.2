"""Chip distribution calculator — volume摊到日K价格区间上的粗算筹码分布。

标准公式:
  取近 N 日量价数据，将每日成交量按日K高低区间均匀分配到价格档上，
  累计得到价格→成交量分布。峰值即筹码密集区（支撑位）。

使用:
  from trader_shared.chip_distribution import calc_chip_distribution
  result = calc_chip_distribution(daily_bars, lookback=60)
  # → {"peaks": [...], "total_volume": 107649253, "current_pct": 37.0, "mid_price": 58.86}
"""

from __future__ import annotations

from typing import Any, Literal

from light_data import to_float


def calc_chip_distribution(
    daily: list[dict[str, Any]],
    lookback: int = 60,
    tick_size: float | None = None,
) -> dict[str, Any]:
    """粗算筹码分布。

    Parameters
    ----------
    daily : list[dict]
        日线 bar 列表，每个 bar 应包含 'high', 'low', 'volume' 字段。
    lookback : int
        回看天数，默认 60 日。
    tick_size : float | None
        自定义 tick（价格档宽），默认自动计算 ~50 bins。
        越小越精细，推荐 0.1~0.3 元。

    Returns
    -------
    dict with keys:
        peaks : list[dict]      前 3个峰值, [{price, volume, share_of_total, support_level}]
        total_volume : float    总筹码量
        current_pct : float | None  当前收盘价在筹码中的累计百分位 (0~100)
        mid_price : float | None      筹码中位数价格 (50%分位)
    """
    bars = daily[-lookback:] if len(daily) >= lookback else daily
    valid: list[tuple[float, float, float]] = []
    for item in bars:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        volume = to_float(item.get("volume")) or 0
        if high is None or low is None or high == low or volume <= 0:
            continue
        valid.append((low, high, volume))

    if not valid:
        return {"peaks": [], "total_volume": 0, "current_pct": None, "mid_price": None}

    min_price = min(lo for lo, _, _ in valid)
    max_price = max(hi for _, hi, _ in valid)
    price_range = max_price - min_price

    # 分档参数
    if tick_size is not None:
        tick = max(tick_size, 0.05)
        num_bins = int(price_range / tick) + 2
    else:
        num_bins = max(int(price_range / 0.3) + 1, 50)
        tick = price_range / num_bins
        if tick < 0.1:
            tick = 0.1
            num_bins = int((max_price - min_price) / tick) + 2

    price_bins = [min_price + (i + 0.5) * tick for i in range(num_bins)]
    volume_map: list[float] = [0.0] * num_bins

    # 核心分配: 每天量按日K价格区间均匀摊到格子上
    for low, high, volume in valid:
        lo_idx = max(0, int((low - min_price) / tick))
        hi_idx = min(num_bins - 1, int((high - min_price) / tick))
        if hi_idx == lo_idx:
            volume_map[lo_idx] += volume
        else:
            num_covered = hi_idx - lo_idx + 1  # +1 确保总量守恒
            segment = volume / num_covered
            for i in range(lo_idx, hi_idx + 1):
                volume_map[i] += segment

    total_chip = sum(volume_map)
    if total_chip == 0:
        return {"peaks": [], "total_volume": 0, "current_pct": None, "mid_price": None}

    # Top 3 筹码峰值
    sorted_indices = sorted(range(num_bins), key=lambda i: volume_map[i], reverse=True)
    peaks: list[dict[str, Any]] = []
    peak_shares: list[float] = []
    for idx in sorted_indices[:3]:
        price = price_bins[idx]
        volume = volume_map[idx]
        share_pct = volume / total_chip * 100
        if share_pct > 0.5:
            peak_shares.append(share_pct)

    peak_shares_sorted = sorted(peak_shares, reverse=True) if peak_shares else [1, 1, 1]

    for idx in sorted_indices[:3]:
        price = price_bins[idx]
        volume = volume_map[idx]
        share_pct = volume / total_chip * 100
        if share_pct > 0.5:
            share_rank = peak_shares_sorted.index(share_pct)
            if share_rank == 0 and share_pct > 3:
                level = "强支撑"
            elif share_rank <= 1 and share_pct > 2:
                level = "支撑"
            else:
                level = "弱支撑"
            peaks.append({
                "price": round(price, 2),
                "volume": round(volume),
                "share_of_total": round(share_pct, 2),
                "support_level": level,
            })
    peaks.sort(key=lambda p: p["price"])

    # 百分位 & 中位数
    cumulative = 0.0
    current_pct = None
    for i, vol in enumerate(volume_map):
        cumulative += vol
        if cumulative / total_chip >= 0.5:
            current_pct = round((i / num_bins) * 100, 1)
            break

    mid_price = None
    cumulative = 0.0
    for i, vol in enumerate(volume_map):
        cumulative += vol
        if cumulative / total_chip >= 0.5:
            mid_price = price_bins[i]
            break

    return {
        "peaks": peaks,
        "total_volume": round(total_chip),
        "current_pct": current_pct,
        "mid_price": mid_price,
    }
