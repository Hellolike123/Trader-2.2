"""技术指标数学计算共享模块。

提供统一的技术指标计算实现，避免各模块各自实现导致的不一致问题。

主要函数：
  - calc_expma: 计算EXPMA值（SMA初始化 + 指数递推）
  - calc_expma_series: 计算完整的EXPMA序列
"""

from __future__ import annotations


def calc_expma(closes: list[float], period: int) -> float | None:
    """计算单个EXPMA值（使用SMA初始化）。

    必须传入完整历史数据（而非切片），否则会退化为SMA。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        最后一个EXPMA值，数据不足时返回None
    """
    if not closes or period <= 0 or len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
    return round(expma_val, 4)


def calc_expma_series(closes: list[float], period: int) -> list[float | None]:
    """计算完整的EXPMA序列。

    Args:
        closes: 收盘价序列（按时间升序）
        period: EXPMA周期

    Returns:
        EXPMA值序列，长度与closes相同，前period-1个值为None
    """
    if not closes or period <= 0:
        return [None] * len(closes)
    if len(closes) < period:
        return [None] * len(closes)
    k = 2.0 / (period + 1)
    result: list[float | None] = []
    # 前period-1个值为None
    for _ in range(period - 1):
        result.append(None)
    # SMA初始化：前period根的均值
    expma_val = sum(closes[:period]) / period
    result.append(round(expma_val, 4))
    # 指数递推
    for c in closes[period:]:
        expma_val = c * k + expma_val * (1 - k)
        result.append(round(expma_val, 4))
    return result


def calc_macd_series(closes: list[float | None]) -> dict[str, list]:
    """统一 MACD 计算（EMA12/26 → DIF → DEA(9) → histogram）。

    所有 MACD 消费方应调用此函数，避免重复计算和 SMA-seeding 差异。

    Args:
        closes: 收盘价序列（可含 None，None 位置跳过但保留占位）

    Returns:
        dict with keys: ema12, ema26, dif, dea, histogram
        每个值为长度与 closes 相同的列表，数据不足的位置为 None
    """
    n = len(closes)
    ema12_series: list[float | None] = [None] * n
    ema26_series: list[float | None] = [None] * n
    dif_series: list[float | None] = [None] * n
    dea_series: list[float | None] = [None] * n
    hist_series: list[float | None] = [None] * n

    # EMA12: SMA seed at index 11, then exponential
    ema12_val = None
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        if i == 11:
            vals = [x for x in closes[:12] if x is not None]
            if len(vals) == 12:
                ema12_val = sum(vals) / 12
        elif i > 11 and ema12_val is not None:
            ema12_val = ema12_val * 11 / 13 + c * 2 / 13
        if ema12_val is not None:
            ema12_series[i] = ema12_val

    # EMA26: SMA seed at index 25, then exponential
    ema26_val = None
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        if i == 25:
            vals = [x for x in closes[:26] if x is not None]
            if len(vals) == 26:
                ema26_val = sum(vals) / 26
        elif i > 25 and ema26_val is not None:
            ema26_val = ema26_val * 25 / 27 + c * 2 / 27
        if ema26_val is not None:
            ema26_series[i] = ema26_val

    # DIF = EMA12 - EMA26
    for i in range(n):
        if ema12_series[i] is not None and ema26_series[i] is not None:
            dif_series[i] = ema12_series[i] - ema26_series[i]

    # DEA: SMA of first 9 DIF values, then exponential
    dea_val = None
    dea_buffer: list[float] = []
    for i in range(n):
        d = dif_series[i]
        if d is None:
            continue
        dea_buffer.append(d)
        if len(dea_buffer) < 9:
            continue
        if dea_val is None:
            dea_val = sum(dea_buffer) / 9
        else:
            dea_val = dea_val * 8 / 10 + d * 2 / 10
        dea_series[i] = dea_val

    # Histogram = DIF - DEA (1x scale)
    for i in range(n):
        if dif_series[i] is not None and dea_series[i] is not None:
            hist_series[i] = round(dif_series[i] - dea_series[i], 4)

    return {
        "ema12": ema12_series,
        "ema26": ema26_series,
        "dif": dif_series,
        "dea": dea_series,
        "histogram": hist_series,
    }


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


def _bar_values(bar: dict) -> tuple[float, float, float]:
    """兼容 dict / 对象两种 bar 形态，提取 (high, low, close)。"""
    if not isinstance(bar, dict):
        return float(getattr(bar, "high", 0)), float(getattr(bar, "low", 0)), float(getattr(bar, "close", 0))
    return float(bar.get("high", 0) or 0), float(bar.get("low", 0) or 0), float(bar.get("close", 0) or 0)


def calc_atr_series(bars: list, period: int = 14) -> list[float | None]:
    """计算 ATR（真实波幅）序列（简单移动平均法）。

    Args:
        bars: K线序列，每根含 high/low/close
        period: ATR 周期

    Returns:
        与 bars 等长的序列，前 period-1 个为 None
    """
    if not bars or len(bars) < 2:
        return [None] * len(bars)

    tr_list: list[float] = []
    for i, bar in enumerate(bars):
        h, l, c = _bar_values(bar)
        if i == 0:
            tr = h - l
        else:
            hp, _, cp = _bar_values(bars[i - 1])
            tr = max(h - l, abs(h - cp), abs(l - cp))
        tr_list.append(tr)

    atr_list: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(tr_list)):
        window = tr_list[i - period + 1 : i + 1]
        atr_list.append(sum(window) / period)
    return atr_list


def calc_supertrend(bars: list, atr_period: int = 14, multiplier: float = 3.0) -> dict:
    """[re-export] 展示指标已迁入 display_indicators.py。

    保留此函数以兼容旧调用方，内部直接转发到新模块。
    新代码请居先使用：from trader_shared.display_indicators import calc_supertrend
    """
    from trader_shared.display_indicators import calc_supertrend as _calc_supertrend
    return _calc_supertrend(bars, atr_period=atr_period, multiplier=multiplier)


def calc_vwap(bars_5m: list, current_price: float | None = None) -> dict:
    """[re-export] 展示指标已迁入 display_indicators.py。

    保留此函数以兼容旧调用方，内部直接转发到新模块。
    新代码请居先使用：from trader_shared.display_indicators import calc_vwap
    """
    from trader_shared.display_indicators import calc_vwap as _calc_vwap
    return _calc_vwap(bars_5m, current_price)
