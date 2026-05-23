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

try:
    from config import MA_PERIODS
except Exception:  # pragma: no cover - optional per skill
    MA_PERIODS = (5, 10, 20, 30)

try:
    from config import MA_WEIGHTS
except Exception:  # pragma: no cover - optional per skill
    MA_WEIGHTS = {"ma5": 0.92, "ma10": 0.88, "ma20": 0.65, "ma30": 0.55}

try:
    from config import MIN_ZONE_WIDTH_PCT
except Exception:  # pragma: no cover - optional per skill
    MIN_ZONE_WIDTH_PCT = 0.005

try:
    from config import MAX_ZONE_WIDTH_PCT
except Exception:  # pragma: no cover - optional per skill
    MAX_ZONE_WIDTH_PCT = 0.020

try:
    from config import MIN_STOP_BUFFER_PCT
except Exception:  # pragma: no cover - optional per skill
    MIN_STOP_BUFFER_PCT = 0.008

try:
    from config import MAX_STOP_BUFFER_PCT
except Exception:  # pragma: no cover - optional per skill
    MAX_STOP_BUFFER_PCT = 0.025

try:
    from config import MIN_CONFIRM_SPACE_PCT
except Exception:  # pragma: no cover - optional per skill
    MIN_CONFIRM_SPACE_PCT = 0.005

try:
    from config import MAX_REASONABLE_MA_DISTANCE_PCT
except Exception:  # pragma: no cover - optional per skill
    MAX_REASONABLE_MA_DISTANCE_PCT = 0.12

try:
    from time_window_detector import check_time_windows as _check_time_windows_raw
except ImportError:
    def _check_time_windows_raw(bars, chan_result=None):
        return {"window_active": False, "window_type": "", "bars_since_pivot": 0, "tolerance": 0, "all_active": []}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _check_time_window(bars: list[BarData], chan_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """安全包装 time_window_detector，异常时静默降级。"""
    try:
        return _check_time_windows_raw(bars, chan_result)
    except Exception:
        return {"window_active": False, "window_type": "", "bars_since_pivot": 0, "tolerance": 0, "all_active": []}


def min_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def max_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def moving_average(bars: list[BarData], period: int) -> float | None:
    closes = [to_float(item.get("close")) for item in bars[-period:]]
    if len(closes) < period or None in closes:
        return None
    return sum(closes) / period


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


def average_atr_pct(bars: list[BarData], period: int | None = None) -> float | None:
    """计算近 period 根K线的平均真实波幅百分比 (ATR/close)。

    ATR 使用 True Range = max(high-low, |high-prev_close|, |low-prev_close|)，
    比简单振幅 (high-low) 更能捕捉跳空缺口的影响。
    先算 ATR 绝对值，再除以最新 close，避免逐根归一化后再平均导致的偏差。
    """
    period = period or STRUCTURE_WINDOW
    tr_values: list[float] = []
    last_close: float | None = None
    prev_close: float | None = None
    for item in bars[-period:]:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        if high is None or low is None or close is None or close <= 0 or high < low:
            continue
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
        prev_close = close
        last_close = close
    if not tr_values or last_close is None or last_close <= 0:
        return None
    atr = sum(tr_values) / len(tr_values)
    return atr / last_close


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


def _open_price(quote: dict[str, Any] | None) -> float | None:
    if quote is None:
        return None
    for key in ("open", "open_price", "today_open"):
        v = quote.get(key)
        if v is not None:
            return to_float(v)
    return None


def _gap_status(
    low_zone_lower: float,
    low_zone_upper: float,
    hard_stop: float,
    open_price: float | None,
    prev_close: float | None,
) -> dict[str, Any]:
    if open_price is None or prev_close is None or prev_close <= 0:
        return {"condition": "unknown", "text": "无开盘数据"}
    gap_up = open_price > prev_close * 1.003
    gap_down = open_price < prev_close * 0.997

    if gap_down and open_price < hard_stop:
        return {"condition": "gap_down_stop", "text": "跳空低开，跌破止损"}
    if gap_up and open_price > low_zone_upper:
        return {"condition": "gap_up", "text": "跳空高开，低吸区今日无效"}
    if gap_down and open_price < low_zone_lower:
        return {"condition": "gap_down", "text": "跳空低开，低开低于低吸区，关注止损"}
    if gap_up:
        return {"condition": "gap_up_low", "text": "跳空高开，但未超过低吸区上沿"}
    return {"condition": "normal", "text": "正常开盘"}


def zone_position(current: float, support: float, confirm: float) -> float:
    if confirm <= support:
        return 0.5  # 无有效区间，返回中间值
    return max(0.0, min(1.0, (current - support) / (confirm - support)))



def _theory_multipliers(fusion_result: dict[str, Any] | None) -> dict[str, float]:
    """根据融合层理论信号及大盘环境计算参数微调系数。

    返回 dict，每项默认1.0（不变）。理论信号好时积极放大，差时收窄。
    若 fusion_result 为 None 或信号不足，全部返回1.0，退化为纯数学计算。

    映射规则（详见 docs/buy-zone-accessibility-fix-plan.md P3）：
      缠论上攻笔/三买 → zone_width 放大 +15%
      缠论下跌笔未结束 → zone_width 缩小 -10%
      威科夫吸筹/Spring → confirm_buffer 收窄 -30%
      动量强势（bullish + score≥65）→ space_threshold 收窄 -20%
      动量弱势（bearish + score≤35）→ space_threshold 加宽 +30%
    """
    multipliers = {
        "zone_width": 1.0,
        "confirm_buffer": 1.0,
        "space_threshold": 1.0,
        "stop_buffer": 1.0,
    }

    # ── Regime Multipliers (大势参数自适应) ──
    regime = "正常"
    if fusion_result is not None:
        regime = fusion_result.get("regime", "正常")

    if regime in ("偏弱", "很差"):
        multipliers["stop_buffer"] = 0.8
        multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 1.3
    elif regime == "正常":
        multipliers["zone_width"] = multipliers["zone_width"] * 1.2
        multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 0.8

    if fusion_result is None:
        return multipliers

    # 从 fusion_result 中读取理论信号详情
    signals_detail = fusion_result.get("signals_detail", {})
    if not isinstance(signals_detail, dict):
        return multipliers

    # --- 缠论信号 ---
    chan = signals_detail.get("chan", {})
    if isinstance(chan, dict):
        reason = str(chan.get("reason", ""))
        direction = chan.get("direction", 0)
        confidence = float(chan.get("confidence", 0))
        # 上攻笔/三买/底背驰 → 低吸区更宽
        if direction == 1 and confidence >= 0.4:
            if any(kw in reason for kw in ("三类买", "二类买", "一类买", "拉升段", "底背驰")):
                multipliers["zone_width"] = multipliers["zone_width"] * 1.15
        # 下跌笔/回调段 → 低吸区收窄
        elif direction == -1 and confidence >= 0.4:
            if any(kw in reason for kw in ("回调段", "顶背驰")):
                multipliers["zone_width"] = multipliers["zone_width"] * 0.90

    # --- 威科夫信号 ---
    wyk = signals_detail.get("wyckoff", {})
    if isinstance(wyk, dict):
        reason = str(wyk.get("reason", ""))
        direction = wyk.get("direction", 1)
        confidence = float(wyk.get("confidence", 0))
        # Spring / 看多背离 → 突破更可信，确认缓冲收窄
        if direction == 1 and confidence >= 0.5:
            if "弹簧" in reason or "看多" in reason:
                multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 0.70  # 0.005 * 0.70 = 0.0035
        # 上冲回落/看空 → 不收窄
        elif direction == -1 and confidence >= 0.5:
            multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 1.0

    # --- 动量信号 ---
    mom = signals_detail.get("momentum", {})
    if isinstance(mom, dict):
        direction = mom.get("direction", 0)
        confidence = float(mom.get("confidence", 0))
        # 动量强势 → space阈值收窄（更激进，空间小也给进）
        if direction == 1 and confidence >= 0.5:
            multipliers["space_threshold"] = multipliers["space_threshold"] * 0.80
        # 动量弱势 → space阈值加宽（更保守）
        elif direction == -1 and confidence >= 0.5:
            multipliers["space_threshold"] = multipliers["space_threshold"] * 1.30

    return multipliers


def build_structure_context(current: float, bars: list[BarData], change_pct: Any = None, quote: QuoteData | None = None, fusion_result: dict[str, Any] | None = None, chan_result: dict[str, Any] | None = None) -> dict[str, Any]:
    recent5 = bars[-RECENT_WINDOW:] if len(bars) >= RECENT_WINDOW else bars
    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    if not recent5:
        raise RuntimeError("daily support/resistance unavailable")

    quote = quote or {}
    open_price = _open_price(quote)
    prev_close = to_float(quote.get("pre_close"))
    ma_values = moving_averages(bars)
    support_levels: list[dict[str, Any]] = []
    resistance_levels: list[dict[str, Any]] = []

    add_level(support_levels, "5日低点", min_price(recent5, "low"), 1.0)
    add_level(resistance_levels, "5日高点", max_price(recent5, "high"), 1.0)
    add_level(support_levels, "今日低点", to_float(quote.get("low")), 0.95)
    add_level(support_levels, "20日低点", min_price(recent20, "low"), 0.85)
    add_level(resistance_levels, "20日高点", max_price(recent20, "high"), 0.85)
    add_ma_levels(support_levels, current, ma_values, below=True)
    add_ma_levels(resistance_levels, current, ma_values, below=False)

    support = choose_level(support_levels, current, below=True)
    resistance = choose_level(resistance_levels, current, below=False)
    support_price = float(support["price"])

    # confirm_price: 需要放量站稳的启动确认价（阻力位 + 缓冲）
    # P3: 缓冲受威科夫吸筹信号影响，Spring/看多背离时收窄
    theory = _theory_multipliers(fusion_result)
    # P3 安全模式：THEORY_ADJUST_LOG_ONLY=true 时只记录不生效
    try:
        from config import THEORY_ADJUST_LOG_ONLY
    except Exception:
        THEORY_ADJUST_LOG_ONLY = False
    if THEORY_ADJUST_LOG_ONLY and any(v != 1.0 for v in theory.values()):
        print(f"THEORY-ADJUST-LOG: multipliers={theory} (suppressed by THEORY_ADJUST_LOG_ONLY)")
        theory = {"zone_width": 1.0, "confirm_buffer": 1.0, "space_threshold": 1.0, "stop_buffer": 1.0}
    effective_confirm_space = MIN_CONFIRM_SPACE_PCT * theory["confirm_buffer"]
    confirm_price = round(float(resistance["price"]) * (1 + effective_confirm_space), 2)
    # resistance: 实际阻力位，用于减仓参考
    resistance_price = float(resistance["price"])

    # 使用 ATR 替代振幅，ATR 能捕捉跳空缺口，对"买入位到不了"的跳空场景更敏感
    # P3: zone_width 受缠论信号影响，上攻笔/三买时放大，下跌笔时收窄
    atr_pct = average_atr_pct(recent20) or 0.02
    zone_width_pct = clamp(atr_pct * 0.25 * theory["zone_width"], MIN_ZONE_WIDTH_PCT, MAX_ZONE_WIDTH_PCT)
    stop_buffer_pct = clamp(atr_pct * 0.40 * theory.get("stop_buffer", 1.0), MIN_STOP_BUFFER_PCT, MAX_STOP_BUFFER_PCT)
    low_zone_lower = round(support_price, 2)
    low_zone_upper = round(support_price * (1 + zone_width_pct), 2)
    stop = round(support_price * (1 - stop_buffer_pct), 2)
    take = round(max(confirm_price, current) * TAKE_PROFIT_BUFFER, 2)
    position = zone_position(current, support_price, confirm_price)
    pressure_space_pct = (confirm_price - current) / current if current > 0 else 0
    below_ma = count_below_ma(current, ma_values)

    # keep compatibility for callers that expect status from structure payload
    from decision_core import status_for  # local import to avoid tighter module coupling

    # 基于ATR的动态"空间不足"阈值：高波幅票给更多容忍，低波幅票收紧
    # P3: 受动量信号影响，强势时收窄（更激进），弱势时加宽（更保守）
    dynamic_space_threshold = max(0.002, atr_pct * 0.35 * theory["space_threshold"])
    status = status_for(
        current=current,
        support=support_price,
        low_zone_upper=low_zone_upper,
        confirm=confirm_price,
        hard_stop=stop,
        position_ratio=position,
        change_pct=change_pct,
        ma_values=ma_values,
        pressure_space_pct=pressure_space_pct,
        bars=bars,
        space_threshold=dynamic_space_threshold,
        fusion_result=fusion_result,  # S-2 fix: 传入融合层结果
        chan_result=chan_result,
    )

    return {
        "main_support": round(support_price, 2),
        "support": round(support_price, 2),
        "support_source": support["name"],
        "resistance": round(resistance_price, 2),
        "resistance_source": resistance["name"],
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "ma_values": ma_values,
        "below_ma_count": below_ma,
        "atr_pct": round(atr_pct, 4),
        "zone_width_pct": round(zone_width_pct, 4),
        "stop_buffer_pct": round(stop_buffer_pct, 4),
        "low_zone_lower": low_zone_lower,
        "low_zone_upper": low_zone_upper,
        "low_zone": f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元",
        "open_price": open_price,
        "gap": _gap_status(low_zone_lower, low_zone_upper, stop, open_price, prev_close),
        "confirm_price": round(confirm_price, 2),
        "sell_observe_price": round(resistance_price, 2),
        "hard_stop": stop,
        "take": take,
        "upside_pct": round(pct_change(current, confirm_price), 2),
        "downside_pct": round(abs(pct_change(current, stop)), 2),
        "position_ratio": round(position, 3),
        "pressure_space_pct": round(pressure_space_pct, 4),
        "status": status,
        "theory_multipliers": theory,  # P3: 记录理论信号对参数的微调系数，便于调试
        "time_window": _check_time_window(bars, chan_result),  # P4: 江恩时间窗口
    }


def count_below_ma(current: float, ma_values: dict[str, float | None]) -> int:
    return sum(1 for value in ma_values.values() if value is not None and current < value)
