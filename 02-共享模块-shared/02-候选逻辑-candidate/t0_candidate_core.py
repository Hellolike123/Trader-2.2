from __future__ import annotations

from typing import Any

from light_data import pct_change, to_float

try:
    from config import CONFIRM_BUFFER
except Exception:  # pragma: no cover - optional per skill
    CONFIRM_BUFFER = 0.02

try:
    from config import RECENT_WINDOW
except Exception:  # pragma: no cover - optional per skill
    RECENT_WINDOW = 5

try:
    from config import STOP_BUFFER
except Exception:  # pragma: no cover - optional per skill
    STOP_BUFFER = 0.98

try:
    from config import TAKE_PROFIT_BUFFER
except Exception:  # pragma: no cover - optional per skill
    TAKE_PROFIT_BUFFER = 1.06

try:
    from config import T0_MIN_SPACE_PCT
except Exception:  # pragma: no cover - optional per skill
    T0_MIN_SPACE_PCT = 1.5


# ---- 可配置阈值常量 ----
MIN_ZONE_WIDTH_PCT = 0.01       # 最小区间宽度（当前价的 1%）
LOW_ZONE_UPPER_OFFSET = 1.01    # 低吸区上限 = support * 此值
HARD_STOP_BUFFER_PCT = 0.995    # 硬止损缓冲（support * 此值）
DROP_THRESHOLD_PCT = -7.0       # 大跌阈值（change_pct <= 此值 → 暂不碰）
STRONG_MOVE_THRESHOLD = 3.0     # 强势涨幅阈值（change_pct >= 此值 → 冲高减仓）
HIGH_POSITION_RATIO = 0.72      # 高仓位比例阈值（>= 此值 → 等转强）
T0_LOW_POSITION_THRESHOLD = 0.45 # T0低吸仓位阈值（<= 此值才触发低吸）
T0_HIGH_POSITION_THRESHOLD = 0.55 # T0高抛仓位阈值（>= 此值触发高抛）


T0_LOW = "等待低吸触发"
T0_HIGH = "等待高抛触发"
T0_NONE = "不做"

STATUS_SCORE = {
    "低吸观察": 80,
    "等转强": 70,
    "防守观察": 60,
    "冲高减仓": 55,
    "暂不碰": 20,
    "数据失败": 0,
}


def min_price(bars: list[dict[str, Any]], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def max_price(bars: list[dict[str, Any]], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def zone_position(current: float, support: float, confirm: float) -> float:
    width = max(confirm - support, current * MIN_ZONE_WIDTH_PCT)
    return max(0.0, min(1.0, (current - support) / width))


def build_candidate_levels(current: float, bars: list[dict[str, Any]], change_pct: Any = None) -> dict[str, Any]:
    recent = bars[-RECENT_WINDOW:] if len(bars) >= RECENT_WINDOW else bars
    support = min_price(recent, "low")
    resistance = max_price(recent, "high")
    if support is None or resistance is None:
        raise RuntimeError("daily support/resistance unavailable")

    confirm = max(resistance, round(current * (1 + CONFIRM_BUFFER), 2))
    stop = round(support * STOP_BUFFER, 2)
    low_zone_lower = round(support, 2)
    low_zone_upper = round(support * LOW_ZONE_UPPER_OFFSET, 2)
    sell_observe = round(confirm, 2)
    take = round(max(confirm, current) * TAKE_PROFIT_BUFFER, 2)
    position = zone_position(current, support, confirm)
    status = status_for(current, support, low_zone_upper, confirm, stop, position, change_pct)

    return {
        "main_support": round(support, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "low_zone_lower": low_zone_lower,
        "low_zone_upper": low_zone_upper,
        "low_zone": f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元",
        "confirm_price": round(confirm, 2),
        "sell_observe_price": sell_observe,
        "hard_stop": stop,
        "take": take,
        "upside_pct": round(pct_change(current, confirm), 2),
        "downside_pct": round(abs(pct_change(current, stop)), 2),
        "position_ratio": round(position, 3),
        "status": status,
        "t0_action": t0_action_for(status, current, support, confirm, position, change_pct),
    }


def status_for(current: float, support: float, low_zone_upper: float, confirm: float, hard_stop: float, position_ratio: float, change_pct: Any) -> str:
    change = to_float(change_pct) or 0.0
    if current <= hard_stop or current < support * HARD_STOP_BUFFER_PCT:
        return "暂不碰"
    if change <= DROP_THRESHOLD_PCT and current > low_zone_upper:
        return "暂不碰"
    if current <= low_zone_upper:
        return "低吸观察"
    if current >= confirm:
        return "冲高减仓" if change >= STRONG_MOVE_THRESHOLD else "等转强"
    if position_ratio >= HIGH_POSITION_RATIO:
        return "等转强"
    return "防守观察"


def t0_action_for(status: str, current: float, support: float, confirm: float, position_ratio: float, change_pct: Any) -> str:
    change = to_float(change_pct) or 0.0
    width = max(confirm - support, 0)
    if status in {"暂不碰", "数据失败"} or current <= 0 or width / current * 100 < T0_MIN_SPACE_PCT:
        return T0_NONE
    if status in {"低吸观察", "防守观察"} and position_ratio <= T0_LOW_POSITION_THRESHOLD:
        return T0_LOW
    if status in {"等转强", "冲高减仓"} or position_ratio >= T0_HIGH_POSITION_THRESHOLD or change >= STRONG_MOVE_THRESHOLD:
        return T0_HIGH
    return T0_NONE


def action_for(status: str, low: float, high: float, sell_observe: float, confirm: float) -> str:
    if status == "低吸观察":
        return f"等 {low:.2f}-{high:.2f}元 止跌，不追。"
    if status == "等转强":
        return f"不追，等站稳 {confirm:.2f}元 后再看。"
    if status == "冲高减仓":
        return f"冲高先看 {sell_observe:.2f}元 附近量能，不机械卖。"
    if status == "防守观察":
        return "先看防守是否稳定，低吸和高抛都等触发。"
    if status == "暂不碰":
        return "风险不清楚，先不参与。"
    return "数据失败，先不参与。"


def empty_position_reason_for(status: str, low: float, high: float, confirm: float, change_pct: Any) -> str:
    change = to_float(change_pct) or 0.0
    if status == "低吸观察":
        return f"接近 {low:.2f}-{high:.2f}元 观察区，但还没触发，适合等确认，不适合直接追。"
    if status == "等转强":
        return f"空仓不追，等放量站稳 {confirm:.2f}元 后再看。"
    if status == "防守观察":
        return "位置还不够主动，空仓只观察，不提前买。"
    if change >= 5:
        return "当日涨幅偏大，空仓不作为第一候选。"
    return "风险不够清楚，空仓先等。"


def holding_reason_for(status: str, low: float, high: float, sell_observe: float) -> str:
    if status in {"低吸观察", "防守观察"}:
        return f"有低吸观察区 {low:.2f}-{high:.2f}元 和高抛观察位 {sell_observe:.2f}元，具体盘中触发交给 t0-trader。"
    if status in {"等转强", "冲高减仓"}:
        return f"更适合盯 {sell_observe:.2f}元 附近冲高表现，量能不足再考虑T。"
    return "不适合做T，先控制风险。"


def risk_note_for(status: str, hard_stop: float) -> str:
    if status == "数据失败":
        return "数据失败，无法比较。"
    if status == "暂不碰":
        return "跌破或贴近关键防守，先不参与。"
    return f"跌破 {hard_stop:.2f}元 后，当前观察逻辑失效。"


def score_for(item: dict[str, Any]) -> float:
    status = str(item.get("status"))
    current = float(item.get("current") or 0)
    low_upper = float(item.get("low_zone_upper") or current)
    confirm = float(item.get("confirm_price") or current)
    hard_stop = float(item.get("hard_stop") or current)
    position_ratio = float(item.get("position_ratio") or 0)
    change = to_float(item.get("change_pct")) or 0.0

    score = float(STATUS_SCORE.get(status, 0))
    if status != "暂不碰" and current <= low_upper:
        score += 10
    if status != "暂不碰" and current >= confirm:
        score += 8
    if current <= hard_stop:
        score -= 40
    if abs(pct_change(current, hard_stop)) < 1.0:
        score -= 8
    if change <= -5 and status != "低吸观察":
        score -= 8
    if change >= 5 and position_ratio >= 0.65:
        score -= 10
    gap_pct = pct_change(current, confirm)
    gap_ratio = gap_pct / 100.0
    if gap_ratio <= 0:
        score -= 4
    else:
        score += min(max(int(gap_ratio * 250), 0), 5)
    if item.get("low_zone") and item.get("confirm_price"):
        score += 5
    return score
