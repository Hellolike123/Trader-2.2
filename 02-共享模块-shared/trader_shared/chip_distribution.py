"""Chip distribution calculator — volume摊到日K价格区间上的动态时序衰减与空间去重筹码分布。

使用:
  from trader_shared.chip_distribution import calc_chip_distribution
  result = calc_chip_distribution(daily_bars, lookback=60)
"""

from __future__ import annotations

from typing import Any

from light_data import to_float


def calc_chip_distribution(
    daily: list[dict[str, Any]],
    lookback: int = 60,
    tick_size: float | None = None,
) -> dict[str, Any]:
    """计算动态时序衰减筹码分布并进行筹码峰空间去重。

    Parameters
    ----------
    daily : list[dict]
        日线 bar 列表，每个 bar 应包含 'high', 'low', 'volume', 'close' 字段，可选包含 'turnover_rate'。
    lookback : int
        回看天数，默认 60 日。内部自适应扩展以获得足够的衰减沉淀历史深度。
    tick_size : float | None
        自定义价格档位宽度。

    Returns
    -------
    dict with keys:
        peaks : list[dict]      去重后的独立峰值列表
        total_volume : float    总筹码量 (衰减后的累积值)
        current_pct : float     当前收盘价之上的筹码占比 (%)
        mid_price : float       筹码中位数价格 (50%分位, 线性插值)
        volume_above_pct : float  当前收盘价之上的筹码占比 (%)
        bin_width : float       箱宽
        effective_range : tuple (min_price, max_price)
    """
    # 动态拓宽回看天数，让 Decay 算法有足够的时序历史深度来进行折旧沉淀
    lookback_val = max(lookback, 120)
    bars = daily[-lookback_val:] if len(daily) >= lookback_val else daily
    
    valid: list[dict[str, Any]] = []
    for item in bars:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        volume = to_float(item.get("volume")) or 0.0
        if high is None or low is None or high == low or volume <= 0:
            continue
        if close is None:
            close = (high + low) / 2.0
            
        valid.append({
            "low": low,
            "high": high,
            "close": close,
            "volume": volume,
            "turnover_rate": to_float(item.get("turnover_rate"))
        })

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

    min_price = min(item["low"] for item in valid)
    max_price = max(item["high"] for item in valid)
    price_range = max_price - min_price

    # 自适应分箱宽度计算
    if tick_size is not None:
        tick = max(tick_size, 0.05)
    else:
        ideal_bins = 50
        ideal_tick = price_range / ideal_bins if price_range > 0 else 0.1
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

    # 时序迭代折旧与累加
    close_weight = 0.6
    spread_weight = 0.4
    
    for item in valid:
        low = item["low"]
        high = item["high"]
        close = item["close"]
        volume = item["volume"]
        tr_raw = item["turnover_rate"]
        
        # 1. 确定当日换手率衰减因子
        if tr_raw is not None:
            tr = tr_raw
            if tr > 100.0:
                tr = 100.0
            elif tr < 0.0:
                tr = 0.0
            decay_rate = (tr / 100.0) ** 0.5 * 0.3
        else:
            decay_rate = 0.03  # 无换手率时默认 3% 折旧率
            
        # 2. 衰减历史筹码量
        volume_map = [val * (1.0 - decay_rate) for val in volume_map]
        
        # 3. 将当日成交量分配到对应的价格区间
        lo_idx = max(0, int((low - min_price) / tick))
        hi_idx = min(num_bins - 1, int((high - min_price) / tick))
        if hi_idx == lo_idx:
            volume_map[lo_idx] += volume
        else:
            # Spread 部分：40% 均匀覆盖
            num_covered = hi_idx - lo_idx + 1
            segment = volume * spread_weight / num_covered
            for i in range(lo_idx, hi_idx + 1):
                volume_map[i] += segment
                
            # Close 锚定部分：60% 集中在 close ± 2 bins
            close_idx = min(num_bins - 1, max(0, int((close - min_price) / tick)))
            half = 2
            start = max(lo_idx, close_idx - half)
            end = min(hi_idx, close_idx + half)
            num_close = end - start + 1
            if num_close > 0:
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

    # 筹码峰检测与去重算法
    # A. 提取所有的局部极大值点 (Local Maxima)
    local_peaks = []
    for i in range(1, num_bins - 1):
        if volume_map[i] >= volume_map[i-1] and volume_map[i] >= volume_map[i+1]:
            if volume_map[i] > 0.0:
                local_peaks.append(i)
                
    # B. 按筹码量降序排列局部极大值
    sorted_peaks = sorted(local_peaks, key=lambda idx: volume_map[idx], reverse=True)
    
    # C. 价格与空间过滤：根据股价区间自适应最小间距
    avg_price = (min_price + max_price) / 2
    if avg_price < 10:
        min_gap_pct = 0.02
    elif avg_price < 50:
        min_gap_pct = 0.03
    else:
        min_gap_pct = 0.04
    selected_peaks: list[int] = []
    for idx in sorted_peaks:
        price = price_bins[idx]
        far_enough = True
        for sel_idx in selected_peaks:
            sel_price = price_bins[sel_idx]
            if abs(price - sel_price) / sel_price < min_gap_pct or abs(idx - sel_idx) < 4:
                far_enough = False
                break
        if far_enough:
            selected_peaks.append(idx)
            
    # D. 如果独立的局部极大值峰不足 3 个，使用普通 bins 进行补齐，同样遵守非邻近/去重过滤
    if len(selected_peaks) < 3:
        sorted_indices = sorted(range(num_bins), key=lambda i: volume_map[i], reverse=True)
        for idx in sorted_indices:
            if len(selected_peaks) >= 3:
                break
            price = price_bins[idx]
            far_enough = True
            for sel_idx in selected_peaks:
                sel_price = price_bins[sel_idx]
                if abs(price - sel_price) / sel_price < min_gap_pct or abs(idx - sel_idx) < 4:
                    far_enough = False
                    break
            if far_enough:
                selected_peaks.append(idx)

    # 计算去重后 peaks 的占比排名并输出
    peak_shares = [volume_map[idx] / total_chip * 100 for idx in selected_peaks[:3]]
    peak_shares_unique = sorted(list(set(peak_shares)), reverse=True) if peak_shares else [1.0]

    current_price = valid[-1]["close"]
    peaks: list[dict[str, Any]] = []
    for idx in selected_peaks[:3]:
        price = price_bins[idx]
        vol = volume_map[idx]
        share_pct = vol / total_chip * 100
        
        is_support = price < current_price
        share_rank = next((r for r, s in enumerate(peak_shares_unique) if abs(s - share_pct) < 1e-9), 0)
        if share_rank == 0 and share_pct > 3:
            level = "强支撑" if is_support else "强阻力"
        elif share_rank <= 1 and share_pct > 2:
            level = "支撑" if is_support else "阻力"
        else:
            level = "弱支撑" if is_support else "弱阻力"
            
        peaks.append({
            "price": round(price, 2),
            "volume": round(vol),
            "share_of_total": round(share_pct, 2),
            "support_level": level,
        })

    # BUG 15 FIX: 近端窗口 — 补齐现价附近的动态筹码峰（从已过滤去重的独立峰 selected_peaks 中提取）
    near_end_peaks: list[dict[str, Any]] = []
    for idx in selected_peaks:
        price = price_bins[idx]
        vol = volume_map[idx]
        share_pct = vol / total_chip * 100
        if abs(price - current_price) / current_price > 0.05:
            continue
        # 如果已经收录在 top 3 peaks 中，跳过
        already_in = any(p["price"] == round(price, 2) for p in peaks)
        if not already_in:
            is_support = price < current_price
            share_rank = next((r for r, s in enumerate(peak_shares_unique) if abs(s - share_pct) < 1e-9), 0)
            if share_rank == 0 and share_pct > 3:
                level = "强支撑" if is_support else "强阻力"
            elif share_rank <= 1 and share_pct > 2:
                level = "支撑" if is_support else "阻力"
            else:
                level = "弱支撑" if is_support else "弱阻力"
            near_end_peaks.append({
                "price": round(price, 2),
                "volume": round(vol),
                "share_of_total": round(share_pct, 2),
                "support_level": level,
            })
            
    if near_end_peaks:
        near_end_peaks.sort(key=lambda p: p["price"])
        all_peaks = peaks + near_end_peaks
    else:
        all_peaks = peaks

    # 筹码中位数价格 (50% 分位, 线性插值)
    cumulative = 0.0
    mid_price = None
    mid_price_cum_target = total_chip * 0.5
    for i, vol in enumerate(volume_map):
        if mid_price is None and cumulative + vol >= mid_price_cum_target:
            frac = (mid_price_cum_target - cumulative) / vol if vol > 0 else 0.0
            mid_price = price_bins[i] - tick * 0.5 + tick * frac
            break
        cumulative += vol

    # volume_above_pct: 当前价之上的筹码占比
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
