"""技术指标数学计算共享模块。

提供统一的技术指标计算实现，避免各模块各自实现导致的不一致问题。

主要函数：
  - calc_expma: 计算EXPMA值（SMA初始化 + 指数递推）
  - calc_expma_series: 计算完整的EXPMA序列
"""

from __future__ import annotations


def calc_expma(closes: list[float], period: int) -> float:
    """计算单个EXPMA值（使用SMA初始化）。

    必须传入完整历史数据（而非切片），否则会退化为SMA。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        最后一个EXPMA值，数据不足时返回0.0
    """
    if not closes or period <= 0 or len(closes) < period:
        return 0.0
    k = 2.0 / (period + 1)
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
    return round(expma_val, 4)


def calc_expma_series(closes: list[float], period: int) -> list[float]:
    """计算完整的EXPMA序列。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        EXPMA值序列，长度与closes相同，前period-1个值为空列表
    """
    if not closes or period <= 0 or len(closes) < period:
        return []
    k = 2.0 / (period + 1)
    result = []
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    result.append(round(expma_val, 4))
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
        result.append(round(expma_val, 4))
    return result


def aggregate_5m_to_60m(bars_5m: list[dict]) -> list[dict]:
    """将5分钟K线聚合为60分钟K线。

    Args:
        bars_5m: 5分钟K线数据列表

    Returns:
        60分钟K线数据列表
    """
    if not bars_5m:
        return []

    from datetime import datetime

    groups: dict[str, list[dict]] = {}
    for bar in bars_5m:
        dt_str = str(bar.get("date") or bar.get("datetime") or "")
        if not dt_str:
            continue
        try:
            if len(dt_str) > 16:
                dt = datetime.fromisoformat(dt_str)
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            # 向下取整到60分钟边界
            hour_bucket = dt.replace(minute=0, second=0, microsecond=0)
            key = hour_bucket.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        groups.setdefault(key, []).append(bar)

    result = []
    for key in sorted(groups.keys()):
        group = groups[key]
        if not group:
            continue
        result.append({
            "date": key,
            "open": float(group[0].get("open", 0)),
            "high": max(float(b.get("high", 0)) for b in group),
            "low": min(float(b.get("low", float("inf"))) for b in group),
            "close": float(group[-1].get("close", 0)),
            "volume": sum(float(b.get("volume", 0)) for b in group),
        })
    return result
