"""技术指标数学计算共享模块。

提供统一的技术指标计算实现，避免各模块各自实现导致的不一致问题。

主要函数：
  - calc_expma / calc_expma_series
  - calc_macd_series / calc_atr_series
  - calc_rsi_series（Wilder 平滑 RSI）
  - aggregate_daily_to_weekly / weekly_bars_look_like_weekly
"""

from __future__ import annotations


def weekly_bars_look_like_weekly(
    bars: list[dict] | None,
    *,
    min_median_gap_days: int = 3,
    min_bars: int = 4,
) -> bool:
    """周 K 间距体检：中位数日历间隔过短则视为日线冒充周线。"""
    if not bars or len(bars) < min_bars:
        return False
    from datetime import datetime

    dates: list[datetime] = []
    for b in bars:
        raw = str((b or {}).get("date") or (b or {}).get("time") or "")[:10]
        if len(raw) < 10:
            continue
        try:
            dates.append(datetime.strptime(raw, "%Y-%m-%d"))
        except ValueError:
            continue
    if len(dates) < min_bars:
        return False
    dates.sort()
    gaps = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
    if not gaps:
        return False
    gaps_sorted = sorted(gaps)
    median = gaps_sorted[len(gaps_sorted) // 2]
    return median >= min_median_gap_days


def aggregate_daily_to_weekly(daily_bars: list[dict] | None) -> list[dict]:
    """日 K → 周 K（ISO 周；date=该周最后一根交易日）。

    用于 mootdx/sina 周线接口返回日线间距时的可靠回退。
    """
    if not daily_bars:
        return []
    from datetime import datetime

    groups: dict[tuple[int, int], list[dict]] = {}
    order: list[tuple[int, int]] = []
    for bar in daily_bars:
        if not isinstance(bar, dict):
            continue
        raw = str(bar.get("date") or bar.get("time") or "")[:10]
        if len(raw) < 10:
            continue
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            continue
        iso = dt.isocalendar()
        key = (int(iso[0]), int(iso[1]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(bar)

    out: list[dict] = []
    for key in order:
        chunk = sorted(
            groups[key],
            key=lambda b: str(b.get("date") or b.get("time") or "")[:10],
        )
        if not chunk:
            continue

        def _f(v: object, default: float = 0.0) -> float:
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return default

        highs = [_f(b.get("high")) for b in chunk]
        lows = [_f(b.get("low"), default=1e18) for b in chunk]
        vol = sum(_f(b.get("volume")) for b in chunk)
        amt_vals = []
        for b in chunk:
            if b.get("amount") is not None:
                amt_vals.append(_f(b.get("amount")))
        out.append({
            "date": str(chunk[-1].get("date") or chunk[-1].get("time") or "")[:10],
            "open": _f(chunk[0].get("open")),
            "high": max(highs) if highs else 0.0,
            "low": min(lows) if lows else 0.0,
            "close": _f(chunk[-1].get("close")),
            "volume": vol,
            "amount": sum(amt_vals) if amt_vals else None,
            "data_source": "daily_aggregate",
            "data_status": "full",
        })
    return out


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

    # EMA12: 攒满 12 个非 None 收盘再 SMA 播种（勿用绝对下标 i==11，空洞序列会错位）
    ema12_val = None
    ema12_seed: list[float] = []
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        if ema12_val is None:
            ema12_seed.append(c)
            if len(ema12_seed) == 12:
                ema12_val = sum(ema12_seed) / 12
                ema12_series[i] = ema12_val
        else:
            ema12_val = ema12_val * 11 / 13 + c * 2 / 13
            ema12_series[i] = ema12_val

    # EMA26: 攒满 26 个非 None 收盘再 SMA 播种
    ema26_val = None
    ema26_seed: list[float] = []
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        if ema26_val is None:
            ema26_seed.append(c)
            if len(ema26_seed) == 26:
                ema26_val = sum(ema26_seed) / 26
                ema26_series[i] = ema26_val
        else:
            ema26_val = ema26_val * 25 / 27 + c * 2 / 27
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

    # Histogram = DIF - DEA（×1）。通达信常见 2×(DIF−DEA)，符号/穿越一致，柱高约一半。
    # 预热不足处保持 None，禁止写 0.0（见 chan_geometry._calc_macd）。
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
        # 生产 5m：date=日、time/datetime=完整时间戳；优先读完整字段
        raw_dt = bar.get("datetime") or bar.get("time") or bar.get("date") or ""
        dt_str = str(raw_dt).strip()
        if not dt_str:
            continue
        # 仅日期（YYYY-MM-DD）无法分桶到小时，跳过
        if len(dt_str) <= 10 and " " not in dt_str and "T" not in dt_str:
            continue
        try:
            if "T" in dt_str or len(dt_str) > 16:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00").split("+")[0])
            else:
                # "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD HH:MM:SS"
                try:
                    dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
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
        # 组内按时间正序，保证 open=首根、close=末根（与分桶一致：优先完整时间戳）
        group = sorted(
            group,
            key=lambda b: str(b.get("datetime") or b.get("time") or b.get("date") or ""),
        )
        result.append({
            "date": key,
            "open": float(group[0].get("open", 0)),
            "high": max(float(b.get("high", 0)) for b in group),
            "low": min(float(b.get("low", float("inf"))) for b in group),
            "close": float(group[-1].get("close", 0)),
            "volume": sum(float(b.get("volume", 0)) for b in group),
        })
    return result


def _bar_values(bar: dict) -> tuple[float | None, float | None, float | None]:
    """兼容 dict / 对象两种 bar 形态，提取 (high, low, close)；缺失为 None。"""
    def _f(v: object) -> float | None:
        if v is None or v == "" or v == "--":
            return None
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return None if f != f else f

    if not isinstance(bar, dict):
        return _f(getattr(bar, "high", None)), _f(getattr(bar, "low", None)), _f(getattr(bar, "close", None))
    return _f(bar.get("high")), _f(bar.get("low")), _f(bar.get("close"))


def calc_rsi_series(closes: list[float | None], period: int = 14) -> list[float | None]:
    """统一 RSI（Wilder 平滑）。所有消费方应调用此函数。

    Args:
        closes: 收盘价序列（含 None 时整段不计算，返回全 None——Wilder 需连续序列）
        period: 默认 14

    Returns:
        与 closes 等长；前 ``period`` 个为 None（与历史 momentum_core 行为一致）
    """
    n = len(closes)
    if period <= 0 or n < period + 1:
        return [None] * n
    if any(c is None for c in closes):
        return [None] * n
    xs = [float(c) for c in closes]  # type: ignore[arg-type]
    diffs = [xs[i] - xs[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in diffs]
    losses = [abs(min(d, 0.0)) for d in diffs]
    result: list[float | None] = [None] * n
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, n):
        if i > period:
            avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
            avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        if avg_l < 1e-10 and avg_g < 1e-10:
            result[i] = 50.0
        elif avg_l < 1e-10:
            result[i] = 100.0
        else:
            result[i] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return result


def calc_atr_series(bars: list, period: int = 14) -> list[float | None]:
    """计算 ATR（真实波幅）序列（简单移动平均法）。

    Args:
        bars: K线序列，每根含 high/low/close
        period: ATR 周期

    Returns:
        与 bars 等长的序列；预热不足或 OHLC/TR 缺失处为 None（不用 0 冒充）。
    """
    if not bars or period <= 0:
        return [None] * len(bars)

    tr_list: list[float | None] = []
    for i, bar in enumerate(bars):
        h, l, _c = _bar_values(bar)
        if h is None or l is None or h < l:
            tr_list.append(None)
            continue
        if i == 0:
            tr_list.append(h - l)
            continue
        _ph, _pl, cp = _bar_values(bars[i - 1])
        if cp is None:
            tr_list.append(None)
            continue
        tr_list.append(max(h - l, abs(h - cp), abs(l - cp)))

    atr_list: list[float | None] = []
    for i in range(len(tr_list)):
        if i < period - 1:
            atr_list.append(None)
            continue
        window = tr_list[i - period + 1 : i + 1]
        if any(t is None for t in window):
            atr_list.append(None)
        else:
            atr_list.append(sum(float(t) for t in window) / period)
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
