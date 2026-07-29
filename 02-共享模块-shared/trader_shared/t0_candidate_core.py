from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.light_data import pct_change, to_float
from trader_shared.safe_cast import safe_float

_logger = get_logger(__name__)

try:
    from trader_shared.config import CONFIRM_BUFFER
except Exception:  # pragma: no cover - optional per skill
    CONFIRM_BUFFER = 0.02

try:
    from trader_shared.config import RECENT_WINDOW
except Exception:  # pragma: no cover - optional per skill
    RECENT_WINDOW = 5

try:
    from trader_shared.config import STOP_BUFFER
except Exception:  # pragma: no cover - optional per skill
    STOP_BUFFER = 0.98

try:
    from trader_shared.config import TAKE_PROFIT_BUFFER
except Exception:  # pragma: no cover - optional per skill
    TAKE_PROFIT_BUFFER = 1.06

from trader_shared.config import T0_MIN_SPACE_PCT

try:
    from trader_shared.config import FUSION_OVERRIDE_ENABLED, FUSION_CONFIDENCE_THRESHOLD
except Exception:
    FUSION_OVERRIDE_ENABLED = False
    FUSION_CONFIDENCE_THRESHOLD = 0.6


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

from trader_shared.config import STATUS_SCORE, DEFENSE_STATUSES as _DEFENSE_STATUSES


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


def build_candidate_levels(current: float, bars: list[dict[str, Any]], change_pct: Any = None, structure_result: dict[str, Any] | None = None, fusion_result: dict[str, Any] | None = None) -> dict[str, Any]:
    # 优先复用 trader 的 structure_core 结果，消除两套价位体系不一致的问题
    if structure_result is not None:
        support = safe_float(structure_result, "support")
        low_zone_lower = safe_float(structure_result, "low_zone_lower", default=support)
        low_zone_upper = safe_float(structure_result, "low_zone_upper", default=support)
        confirm = safe_float(structure_result, "confirm_price")
        stop = safe_float(structure_result, "hard_stop")
        resistance = safe_float(structure_result, "resistance")
        sell_observe = safe_float(structure_result, "sell_observe_price", default=confirm)
        take = safe_float(structure_result, "take", default=max(confirm, current) * 1.06)
        # 直接复用 structure_core 算好的 position_ratio，避免 zone_position() 两套实现不一致
        position = safe_float(structure_result, "position_ratio", default=zone_position(current, support, confirm))
        status = status_for(current, support, low_zone_upper, confirm, stop, position, change_pct, fusion_result=fusion_result)
        low_zone_display = structure_result.get("low_zone", f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元")
    else:
        recent = bars[-RECENT_WINDOW:] if len(bars) >= RECENT_WINDOW else bars
        support = min_price(recent, "low")
        resistance = max_price(recent, "high")
        if support is None or resistance is None:
            raise RuntimeError("daily support/resistance unavailable")
        # Bug D fix: fallback 路径也使用 ATR 动态参数，与 structure_core 一致
        # 避免旧硬编码参数 (CONFIRM_BUFFER=0.02, STOP_BUFFER=0.98, LOW_ZONE_UPPER_OFFSET=1.01)
        # 导致价位与 trader 差距过大
        try:
            from trader_shared.structure_core import average_atr_pct
            atr_pct = average_atr_pct(bars) or 0.02
        except ImportError:
            atr_pct = 0.02
        try:
            from trader_shared.config import MIN_ZONE_WIDTH_PCT as _MIN_ZONE, MAX_ZONE_WIDTH_PCT as _MAX_ZONE
            from trader_shared.config import MIN_STOP_BUFFER_PCT as _MIN_STOP, MAX_STOP_BUFFER_PCT as _MAX_STOP
            from trader_shared.config import MIN_CONFIRM_SPACE_PCT as _MIN_CONFIRM
        except ImportError:
            _MIN_ZONE = 0.005; _MAX_ZONE = 0.020
            _MIN_STOP = 0.008; _MAX_STOP = 0.025
            _MIN_CONFIRM = 0.005
        zone_width_pct = max(_MIN_ZONE, min(atr_pct * 0.25, _MAX_ZONE))
        stop_buffer_pct = max(_MIN_STOP, min(atr_pct * 0.40, _MAX_STOP))
        confirm = round(float(resistance) * (1 + _MIN_CONFIRM), 2)
        stop = round(float(support) * (1 - stop_buffer_pct), 2)
        low_zone_lower = round(float(support), 2)
        low_zone_upper = round(float(support) * (1 + zone_width_pct), 2)
        sell_observe = round(confirm, 2)
        take = round(max(confirm, current) * TAKE_PROFIT_BUFFER, 2)
        position = zone_position(current, float(support), confirm)
        status = status_for(current, float(support), low_zone_upper, confirm, stop, position, change_pct, fusion_result=fusion_result)
        low_zone_display = f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元"

    return {
        "main_support": round(support, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "low_zone_lower": low_zone_lower,
        "low_zone_upper": low_zone_upper,
        "low_zone": low_zone_display,
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


def status_for(current: float, support: float, low_zone_upper: float, confirm: float, hard_stop: float, position_ratio: float, change_pct: Any, fusion_result: dict[str, Any] | None = None, ma_values: dict[str, float | None] | None = None, pressure_space_pct: float = 0.0, bars: list[dict[str, Any]] | None = None, vp_result: dict[str, Any] | None = None) -> str:
    # Delegate to decision_core to keep a single status judgment logic
    try:
        from trader_shared.decision_core import status_for as _dec_status
        return _dec_status(
            current=current, support=support, low_zone_upper=low_zone_upper,
            confirm=confirm, hard_stop=hard_stop, position_ratio=position_ratio,
            change_pct=change_pct, ma_values=ma_values or {},
            pressure_space_pct=pressure_space_pct, bars=bars,
            fusion_result=fusion_result,
            vp_result=vp_result,
        )
    except ImportError:
        import logging
        _logger.debug("decision_core unavailable, using T0 fallback status_for")
    # Fallback: original T0-only logic (T0 skill may lack decision_core)
    _FUSION_STATUS_MAP: dict[str, str] = {
        "半仓试 (多方主导)": "低吸观察",
        "半仓试 (多方主导但有分歧)": "等转强",
        "增持": "低吸观察",
        "持股观望": "等转强",
        "减仓": "冲高减仓",
        "空仓/止损": "暂不碰",
        "空仓 (大盘很差, 一票否决)": "暂不碰",
        "观望 (信号冲突)": "防守观察",
        "等转强": "等转强",
        "回调观望": "防守观察",
        "高位观望": "暂不碰",
    }
    if FUSION_OVERRIDE_ENABLED and isinstance(fusion_result, dict):
        fc = safe_float(fusion_result, "confidence")
        if fc >= FUSION_CONFIDENCE_THRESHOLD:
            fusion_action = str(fusion_result.get("action") or "").strip()
            mapped_status = _FUSION_STATUS_MAP.get(fusion_action)
            if mapped_status is not None:
                if current <= hard_stop or current < support * HARD_STOP_BUFFER_PCT:
                    return "暂不碰"
                if mapped_status == "暂不碰":
                    return "防守观察"
                return mapped_status

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
    if status in _DEFENSE_STATUSES and position_ratio <= T0_LOW_POSITION_THRESHOLD:
        return T0_LOW
    if status in {"等转强", "冲高减仓", *_DEFENSE_STATUSES} or position_ratio >= T0_HIGH_POSITION_THRESHOLD or change >= STRONG_MOVE_THRESHOLD:
        return T0_HIGH
    return T0_NONE


def action_for(status: str, low: float, high: float, sell_observe: float, confirm: float) -> str:
    if status == "低吸观察":
        return f"等 {low:.2f}-{high:.2f}元 止跌，不追。"
    if status == "等转强":
        return f"不追，等站稳 {confirm:.2f}元 后再看。"
    if status == "冲高减仓":
        return f"冲高先看 {sell_observe:.2f}元 附近量能，不机械卖。"
    if status in _DEFENSE_STATUSES:
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
    if status in _DEFENSE_STATUSES:
        return "位置还不够主动，空仓只观察，不提前买。"
    if change >= 5:
        return "当日涨幅偏大，空仓不作为第一候选。"
    return "风险不够清楚，空仓先等。"


def holding_reason_for(status: str, low: float, high: float, sell_observe: float) -> str:
    if status in {"低吸观察"} | _DEFENSE_STATUSES:
        return f"有低吸观察区 {low:.2f}-{high:.2f}元 和高抛观察位 {sell_observe:.2f}元，具体盘中触发交给 t0。"
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
    # Delegate to decision_core for a single scoring logic
    try:
        from trader_shared.decision_core import score_for as _dec_score
        return _dec_score(item)
    except ImportError:
        # Fallback for T0 install without decision_core
        pass
    status = item.get("status") or ""
    current = safe_float(item, "current")
    low_upper = safe_float(item, "low_zone_upper", default=current)
    confirm = safe_float(item, "confirm_price", default=current)
    hard_stop = safe_float(item, "hard_stop", default=current)
    position_ratio = safe_float(item, "position_ratio")
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
    gap_ratio = gap_pct / 100.0 if gap_pct > 0 else 0.0
    if gap_ratio <= 0:
        score -= 4
    else:
        score += min(max(int(gap_ratio * 250), 0), 5)
    if item.get("low_zone") and item.get("confirm_price"):
        score += 5
    return score
