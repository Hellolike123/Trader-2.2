from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def _valid_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for bar in bars:
        if all(_num(bar.get(key)) is not None for key in ("open", "high", "low", "close")):
            result.append(bar)
    return result


def detect_liquidity_sweep(bars: list[dict[str, Any]], lookback: int = 8, recent_window: int = 6) -> dict[str, Any]:
    valid = _valid_bars(bars)
    if len(valid) < lookback + 2:
        return {"sweep_type": "none", "swept_level": None, "bar_index": None, "confirmation_strength": "none"}

    start = max(lookback, len(valid) - recent_window)
    latest: dict[str, Any] | None = None
    for index in range(start, len(valid)):
        prior = valid[index - lookback : index]
        prior_lows = [_num(item.get("low")) for item in prior]
        prior_highs = [_num(item.get("high")) for item in prior]
        prior_lows = [item for item in prior_lows if item is not None]
        prior_highs = [item for item in prior_highs if item is not None]
        low = _num(valid[index].get("low"))
        high = _num(valid[index].get("high"))
        close = _num(valid[index].get("close"))
        if low is None or high is None or close is None or not prior_lows or not prior_highs:
            continue

        swept_low = min(prior_lows)
        swept_high = max(prior_highs)
        if low < swept_low and close > swept_low:
            latest = {
                "sweep_type": "downside_sweep",
                "swept_level": round(swept_low, 2),
                "bar_index": index,
                "confirmation_strength": _strength(valid[index], swept_low, downside=True),
            }
        if high > swept_high and close < swept_high:
            latest = {
                "sweep_type": "upside_sweep",
                "swept_level": round(swept_high, 2),
                "bar_index": index,
                "confirmation_strength": _strength(valid[index], swept_high, downside=False),
            }
    return latest or {"sweep_type": "none", "swept_level": None, "bar_index": None, "confirmation_strength": "none"}


def _strength(bar: dict[str, Any], level: float, *, downside: bool) -> str:
    high = _num(bar.get("high"))
    low = _num(bar.get("low"))
    close = _num(bar.get("close"))
    open_ = _num(bar.get("open"))
    if None in (high, low, close, open_) or high == low:
        return "weak"
    span = high - low
    if downside:
        reclaim = (close - level) / max(span, 0.01)
        wick = (min(open_, close) - low) / max(span, 0.01)
    else:
        reclaim = (level - close) / max(span, 0.01)
        wick = (high - max(open_, close)) / max(span, 0.01)
    score = int(reclaim >= 0.25) + int(wick >= 0.35)
    return "strong" if score == 2 else "medium" if score == 1 else "weak"


def detect_structure_shift(bars: list[dict[str, Any]], sweep: dict[str, Any], lookback: int = 3) -> dict[str, Any]:
    valid = _valid_bars(bars)
    index = sweep.get("bar_index")
    sweep_type = sweep.get("sweep_type")
    if index is None or sweep_type not in {"downside_sweep", "upside_sweep"}:
        return {"structure_shift": "none", "break_level": None}
    index = int(index)
    if index <= 0 or index >= len(valid):
        return {"structure_shift": "none", "break_level": None}

    prior = valid[max(0, index - lookback) : index]
    after = valid[index + 1 :] or [valid[index]]
    if not prior:
        return {"structure_shift": "none", "break_level": None}

    if sweep_type == "downside_sweep":
        prior_highs = [_num(item.get("high")) for item in prior]
        prior_highs = [item for item in prior_highs if item is not None]
        if not prior_highs:
            return {"structure_shift": "none", "break_level": None}
        break_level = max(prior_highs)
        shifted = any((_num(item.get("close")) or -10**9) > break_level for item in after)
        return {"structure_shift": "bullish_bos" if shifted else "none", "break_level": round(break_level, 2)}

    prior_lows = [_num(item.get("low")) for item in prior]
    prior_lows = [item for item in prior_lows if item is not None]
    if not prior_lows:
        return {"structure_shift": "none", "break_level": None}
    break_level = min(prior_lows)
    shifted = any((_num(item.get("close")) or 10**9) < break_level for item in after)
    return {"structure_shift": "bearish_choch" if shifted else "none", "break_level": round(break_level, 2)}


def build_ict_signal(bars: list[dict[str, Any]], *, sweep_lookback: int = 8, recent_window: int = 6, structure_lookback: int = 3) -> dict[str, Any]:
    sweep = detect_liquidity_sweep(bars, lookback=sweep_lookback, recent_window=recent_window)
    structure = detect_structure_shift(bars, sweep, lookback=structure_lookback)
    sweep_type = sweep.get("sweep_type")
    shift = structure.get("structure_shift")
    buy_confirmed = sweep_type == "downside_sweep" and shift == "bullish_bos"
    sell_confirmed = sweep_type == "upside_sweep" and shift == "bearish_choch"
    if buy_confirmed:
        grade = "A" if sweep.get("confirmation_strength") == "strong" else "B"
        summary = f"下扫 {_price(sweep.get('swept_level'))} 后收回，并出现5m结构转强，辅助低吸确认。"
    elif sell_confirmed:
        grade = "A" if sweep.get("confirmation_strength") == "strong" else "B"
        summary = f"上扫 {_price(sweep.get('swept_level'))} 后回落，并出现5m结构转弱，辅助高抛确认。"
    elif sweep_type == "downside_sweep":
        grade = "C"
        summary = f"下扫 {_price(sweep.get('swept_level'))} 后收回，但结构转强不足，只观察。"
    elif sweep_type == "upside_sweep":
        grade = "C"
        summary = f"上扫 {_price(sweep.get('swept_level'))} 后回落，但结构转弱不足，只观察。"
    else:
        grade = "无效"
        summary = "无有效扫流动性确认，不加分。"
    return {
        "sweep_type": sweep_type,
        "swept_level": sweep.get("swept_level"),
        "confirmation_strength": sweep.get("confirmation_strength"),
        "structure_shift": shift,
        "break_level": structure.get("break_level"),
        "buy_confirmed": buy_confirmed,
        "sell_confirmed": sell_confirmed,
        "signal_grade": grade,
        "summary": summary,
    }
