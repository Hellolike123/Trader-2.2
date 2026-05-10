"""Chip distribution calculator — volume摊到日K价格区间上的粗算筹码分布。

标准公式:
  取近 N 日量价数据，将每日成交量按日K高低区间均匀分配到价格档上，
  累计得到价格→成交量分布。峰值即筹码密集区（支撑位）。

使用:
  from trader_shared.chip_distribution import calc_chip_distribution
  result = calc_chip_distribution(daily_bars, lookback=60)
  # → {"peaks": [...], "total_volume": 107649253, "current_pct": 37.0, "mid_price": 58.86,
  #    "volume_above_pct": 63.0, "bin_width": 0.12, "effective_range": (45.0, 85.0)}
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
        日线 bar 列表，每个 bar 应包含 'high', 'low', 'volume', 'close' 字段。
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
        current_pct : float | None  (已废弃，保留兼容性) 原来误用于中位 bin 位置
        mid_price : float | None      筹码中位数价格 (50%分位, 线性插值)
        volume_above_pct : float | None  当前收盘价之上的筹码占比 (%)
        bin_width : float               分箱宽度
        effective_range : tuple         (min_price, max_price)
    """
    bars = daily[-lookback:] if len(daily) >= lookback else daily
    valid: list[tuple[float, float, float, float]] = []
    for item in bars:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        volume = to_float(item.get("volume")) or 0
        if high is None or low is None or high == low or volume <= 0:
            continue
        if close is None:
            close = (high + low) / 2.0
        valid.append((low, high, close, volume))

    if not valid:
        return {
            "peaks": [],
            "total_volume": 0,
            "current_pct": None,
            "mid_price": None,
            "volume_above_pct": None,
            "bin_width": 0.0,
            "effective_range": (0.0, 0.0),
        }

    min_price = min(lo for lo, _, _, _ in valid)
    max_price = max(hi for _, hi, _, _ in valid)
    price_range = max_price - min_price

    # BUG 12 FIX: 自适应分箱 — 不用硬编码 0.1 下限
    if tick_size is not None:
        tick = max(tick_size, 0.05)
    else:
        # 目标 ~50 bins，但不过分细分窄区间
        ideal_bins = 50
        ideal_tick = price_range / ideal_bins if price_range > 0 else 0.1
        # 对于极窄区间（< 1元），用更小的 tick 保持分辨率
        if price_range < 1.0:
            tick = max(price_range / 30, 0.02)
        elif price_range < 5.0:
            tick = max(price_range / 50, 0.05)
        else:
            ideal_bins = max(int(price_range / ideal_tick) + 1, 30)
            tick = price_range / ideal_bins
            if tick < 0.05:
                tick = 0.05
    num_bins = max(int(price_range / tick) + 2, 5)

    price_bins = [min_price + (i + 0.5) * tick for i in range(num_bins)]
    volume_map: list[float] = [0.0] * num_bins

    # BUG 13 FIX: 收盘锚定分配 — close 是真实成交点，成交量应集中在 close 附近
    # 60% 量集中到 close 附近（最多 4 个 bin），40% 均匀覆盖 [low, high]
    # 这样 close 处形成自然筹码峰，同时用少量量覆盖高低区间
    close_weight = 0.6
    spread_weight = 0.4
    for low, high, close, volume in valid:
        lo_idx = max(0, int((low - min_price) / tick))
        hi_idx = min(num_bins - 1, int((high - min_price) / tick))
        if hi_idx == lo_idx:
            volume_map[lo_idx] += volume
        else:
            # Spread 部分：均匀分配覆盖整个 [low, high]
            num_covered = hi_idx - lo_idx + 1
            segment = volume * spread_weight / num_covered
            for i in range(lo_idx, hi_idx + 1):
                volume_map[i] += segment
            # Close 锚定部分：集中在 close ± 2 bins 范围内（最多 4 个 bin）
            close_idx = min(num_bins - 1, int((close - min_price) / tick))
            half = 2  # close 左右各 2 个 bin
            start = max(lo_idx, close_idx - half)
            end = min(hi_idx, close_idx + half)
            num_close = end - start + 1
            segment_close = volume * close_weight / num_close
            for i in range(start, end + 1):
                volume_map[i] += segment_close

    total_chip = sum(volume_map)
    if total_chip == 0:
        return {
            "peaks": [],
            "total_volume": 0,
            "current_pct": None,
            "mid_price": None,
            "volume_above_pct": None,
            "bin_width": 0.0,
            "effective_range": (min_price, max_price),
        }

    # BUG 14 FIX: 用排名去重，不再用 list.index() 查找
    sorted_indices = sorted(range(num_bins), key=lambda i: volume_map[i], reverse=True)
    peak_shares: list[float] = []
    for idx in sorted_indices[:3]:
        vol = volume_map[idx]
        share_pct = vol / total_chip * 100
        if share_pct > 0.5:
            peak_shares.append(share_pct)

    # 去重排名: 相同 share_pct 获得相同排名
    peak_shares_unique = sorted(set(peak_shares), reverse=True) if peak_shares else [1.0]

    peaks: list[dict[str, Any]] = []
    for idx in sorted_indices[:3]:
        price = price_bins[idx]
        vol = volume_map[idx]
        share_pct = vol / total_chip * 100
        if share_pct > 0.5:
            # 找这个 share_pct 的排名（去重后）
            share_rank = next((r for r, s in enumerate(peak_shares_unique) if abs(s - share_pct) < 1e-9), 0)
            if share_rank == 0 and share_pct > 3:
                level = "强支撑"
            elif share_rank <= 1 and share_pct > 2:
                level = "支撑"
            else:
                level = "弱支撑"
            peaks.append({
                "price": round(price, 2),
                "volume": round(vol),
                "share_of_total": round(share_pct, 2),
                "support_level": level,
            })
    # BUG 15 FIX: 近端窗口 — 如果 top 3 里没有现价附近的峰，加一个近端峰
    current_price = valid[-1][2]
    # 找到现价最近的峰（无论 share_pct），距离 < 3% 即收录
    near_end_peaks: list[dict[str, Any]] = []
    for idx in sorted_indices:
        price = price_bins[idx]
        vol = volume_map[idx]
        share_pct = vol / total_chip * 100
        if share_pct < 0.5:
            continue
        if abs(price - current_price) / current_price > 0.05:
            continue
        # 已在前3里，跳过
        already_in = any(p["price"] == price for p in peaks)
        if not already_in:
            share_rank = next((r for r, s in enumerate(peak_shares_unique) if abs(s - share_pct) < 1e-9), 0)
            if share_rank == 0 and share_pct > 3:
                level = "强支撑"
            elif share_rank <= 1 and share_pct > 2:
                level = "支撑"
            else:
                level = "弱支撑"
            near_end_peaks.append({
                "price": round(price, 2),
                "volume": round(vol),
                "share_of_total": round(share_pct, 2),
                "support_level": level,
            })
    if near_end_peaks:
        near_end_peaks.sort(key=lambda p: p["price"])
        # 合并: 优先保留 top 3, 近端峰加在后面
        all_peaks = peaks + near_end_peaks
    else:
        all_peaks = peaks

    # BUG 10: current_pct 改为"当前价之上的筹码占比"
    # BUG 11: mid_price 线性插值
    cumulative = 0.0
    mid_price = None
    mid_price_cum_target = total_chip * 0.5
    for i, vol in enumerate(volume_map):
        if mid_price is None and cumulative + vol >= mid_price_cum_target:
            frac = (mid_price_cum_target - cumulative) / vol if vol > 0 else 0.0
            mid_price = price_bins[i] - tick * 0.5 + tick * frac
            break
        cumulative += vol

    # current_pct = 当前价之上的筹码占比
    current_bin_idx = min(num_bins - 1, max(0, int((current_price - min_price) / tick)))
    current_bin_price = price_bins[current_bin_idx]
    current_bin_low = current_bin_price - tick * 0.5
    current_bin_high = current_bin_price + tick * 0.5
    vol_below = sum(volume_map[:current_bin_idx])
    if current_bin_high > current_bin_low:
        vol_above_current_bin = volume_map[current_bin_idx] * (
            (current_bin_high - current_price) / (current_bin_high - current_bin_low)
        )
    else:
        vol_above_current_bin = 0.0
    # volume_above = partial in current bin above price + all bins above current bin
    volume_above = vol_above_current_bin + (total_chip - vol_below - volume_map[current_bin_idx])
    volume_above_pct = round(max(0.0, min(100.0, (volume_above / total_chip) * 100)), 1)

    return {
        "peaks": all_peaks,
        "total_volume": round(total_chip),
        "current_pct": volume_above_pct,
        "mid_price": round(mid_price, 2) if mid_price is not None else None,
        "volume_above_pct": volume_above_pct,
        "bin_width": round(tick, 4),
        "effective_range": (round(min_price, 2), round(max_price, 2)),
    }
