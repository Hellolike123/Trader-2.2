from __future__ import annotations

from pathlib import Path
from typing import Any

from light_data import to_float
from trader_shared.modifier_rule_engine import apply_score_modifiers, apply_livermore_scale

_engine: Any = None
_engine_loaded: bool = False


def _get_engine() -> Any:
    global _engine, _engine_loaded
    if _engine_loaded:
        return _engine
    _engine_loaded = True

    # Search multiple candidate paths so this works both from the source tree
    # and when installed into a skill bundle (the shared module gets copied
    # into <skill>/scripts/ via pack_all.py).
    _base = Path(__file__).resolve().parent
    candidates = [
        # Source tree: candidate/ ← ../trader_shared/status_rules.yml
        _base.parent.parent / "trader_shared" / "status_rules.yml",
        # Installed: <skill>/scripts/ directly (pack_all copies shared files there)
        _base.parent / "trader_shared" / "status_rules.yml",
    ]
    for rules_path in candidates:
        if rules_path.exists():
            try:
                from trader_shared.rule_engine import RuleEngine
                _engine = RuleEngine.from_yaml(str(rules_path))
                return _engine
            except Exception:
                pass

    _engine = None
    return None

try:
    from config import STATUS_SCORE
except Exception:  # pragma: no cover - optional per skill
    STATUS_SCORE = {
        "低吸观察": 80,
        "等转强": 70,
        "防守观察": 60,
        "冲高减仓": 55,
        "空间不足": 45,
        "暂不碰": 20,
        "数据失败": 0,
    }

try:
    from config import CHANGE_THRESHOLD_STRONG
except Exception:  # pragma: no cover - optional per skill
    CHANGE_THRESHOLD_STRONG = 3.0

try:
    from config import CHANGE_THRESHOLD_LARGE
except Exception:  # pragma: no cover - optional per skill
    CHANGE_THRESHOLD_LARGE = 5.0

try:
    from config import CHANGE_THRESHOLD_LARGE_DROP
except Exception:  # pragma: no cover - optional per skill
    CHANGE_THRESHOLD_LARGE_DROP = -5.0

try:
    from config import CHANGE_THRESHOLD_DROP
except Exception:  # pragma: no cover - optional per skill
    CHANGE_THRESHOLD_DROP = -7.0

try:
    from config import POSITION_RATIO_STRONG
except Exception:  # pragma: no cover - optional per skill
    POSITION_RATIO_STRONG = 0.60

try:
    from config import POSITION_RATIO_CONFIRM
except Exception:  # pragma: no cover - optional per skill
    POSITION_RATIO_CONFIRM = 0.72

try:
    from config import POSITION_RATIO_HIGH
except Exception:  # pragma: no cover - optional per skill
    POSITION_RATIO_HIGH = 0.65


def status_for(
    current: float,
    support: float,
    low_zone_upper: float,
    confirm: float,
    hard_stop: float,
    position_ratio: float,
    change_pct: Any,
    ma_values: dict[str, float | None],
    pressure_space_pct: float,
) -> str:
    change = to_float(change_pct) or 0.0
    below_ma_count = sum(1 for value in ma_values.values() if value is not None and current < value)
    above_ma5_ma10 = all(current >= (ma_values.get(name) or float("inf")) for name in ("ma5", "ma10"))

    engine = _get_engine()
    if engine:
        ctx = {
            "current": current, "support": support, "low_zone_upper": low_zone_upper,
            "confirm": confirm, "stop": hard_stop, "change": change,
            "change_pct": change, "position_ratio": position_ratio,
            "pressure_space_pct": pressure_space_pct,
            "above_ma5_ma10": above_ma5_ma10, "below_ma_count": below_ma_count,
        }
        result = engine.evaluate(ctx)
        if result is not None:
            return str(result)
    if current <= hard_stop or current < support * 0.995:
        return "暂不碰"
    if change <= CHANGE_THRESHOLD_DROP and current > low_zone_upper:
        return "暂不碰"
    if current <= low_zone_upper:
        return "低吸观察"
    if current >= confirm:
        return "冲高减仓" if change >= CHANGE_THRESHOLD_STRONG else "等转强"
    if 0 <= pressure_space_pct < 0.008:
        return "空间不足"
    if above_ma5_ma10 and position_ratio >= POSITION_RATIO_STRONG:
        return "等转强"
    if below_ma_count >= 3:
        return "防守观察"
    if position_ratio >= POSITION_RATIO_CONFIRM:
        return "等转强"
    return "防守观察"


def action_for(status: str, low: float, high: float, sell_observe: float, confirm: float) -> str:
    if status == "低吸观察":
        return f"等 {low:.2f}-{high:.2f}元 止跌，不追。"
    if status == "等转强":
        return f"不追，等站稳 {confirm:.2f}元 后再看。"
    if status == "冲高减仓":
        return f"冲高先看 {sell_observe:.2f}元 附近量能，不机械卖。"
    if status == "空间不足":
        return "上方空间太近，先观察，不追。"
    if status == "防守观察":
        return "先看防守是否稳定，低吸和减仓都等确认。"
    if status == "暂不碰":
        return "风险不清楚，先不参与。"
    return "数据失败，先不参与。"


def score_for(item: dict[str, Any]) -> float:
    status = str(item.get("status"))
    current = float(item.get("current") or 0)
    low_upper = float(item.get("low_zone_upper") or current)
    confirm = float(item.get("confirm_price") or current)
    hard_stop = float(item.get("hard_stop") or current)
    position_ratio = float(item.get("position_ratio") or 0)
    change = to_float(item.get("change_pct")) or 0.0
    below_ma_count = int(item.get("below_ma_count") or 0)

    rule_mod = apply_score_modifiers(item)
    if rule_mod is None:
        # Fallback to hardcoded logic
        score = float(STATUS_SCORE.get(status, 0))
        if status != "暂不碰" and current <= low_upper:
            score += 10
        if status != "暂不碰" and current >= confirm:
            score += 8
        if current <= hard_stop:
            score -= 40
        if abs((current - hard_stop) / max(current, 1)) < 0.01:
            score -= 8
        if change <= CHANGE_THRESHOLD_LARGE_DROP and status != "低吸观察":
            score -= 8
        if change >= CHANGE_THRESHOLD_LARGE and position_ratio >= POSITION_RATIO_HIGH:
            score -= 10
        gap_pct = (confirm - current) / max(current, 1)
        if gap_pct <= 0:
            score -= 4
        else:
            score += min(max(int(gap_pct * 250), 0), 5)
        if item.get("low_zone") and item.get("confirm_price"):
            score += 5
        score -= below_ma_count * 2
        return score

    score = float(STATUS_SCORE.get(status, 0)) + rule_mod
    score -= below_ma_count * 2
    return score


def atr_volatility_level(atr_ratio: float) -> tuple[str, int]:
    if atr_ratio <= 0:
        return ("数据不足", 10)
    if atr_ratio >= ATR_HIGH_THRESHOLD:
        return ("波幅偏高", 5)
    if atr_ratio >= ATR_ELEVATED_THRESHOLD:
        return ("波动偏大", 7)
    if atr_ratio >= ATR_NORMAL_THRESHOLD:
        return ("波动正常", 10)
    return ("波动较低", 20)


def atr_stop_buffer(atr_ratio: float, atr14: float) -> tuple[float, str]:
    if atr14 <= 0:
        return (0, "ATR数据不足")
    distance = round(atr14 * 2, 2)
    level, _ = atr_volatility_level(atr_ratio)
    if atr_ratio >= ATR_ELEVATED_THRESHOLD:
        return (distance, f"{level} | ATR×2={distance:.2f}元")
    return (distance, f"ATR×2={distance:.2f}元")


try:
    from config import PYRAMID_SCALES
except Exception:  # pragma: no cover - optional per skill
    PYRAMID_SCALES = {0: 0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.85, 5: 1.0}

try:
    from config import BASE_WEIGHTS
except Exception:  # pragma: no cover - optional per skill
    BASE_WEIGHTS = {0: 15, 1: 10, 2: 7, 3: 4}

try:
    from config import ATRLV_INDEX
except Exception:  # pragma: no cover - optional per skill
    ATRLV_INDEX = {"数据不足": 0, "波幅偏高": 3, "波动偏大": 2, "波动正常": 1, "波动较低": 0}

try:
    from config import ATR_HIGH_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_HIGH_THRESHOLD = 0.03

try:
    from config import ATR_ELEVATED_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_ELEVATED_THRESHOLD = 0.02

try:
    from config import ATR_NORMAL_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_NORMAL_THRESHOLD = 0.01


def livermore_scale(status: str, score: float) -> int:
    tier = apply_livermore_scale(status, score)
    if tier is not None:
        return tier
    # Fallback to hardcoded logic
    tier = 0
    if status in {"优先候选", "低吸观察"}:
        tier = 1
        if score >= 90:
            tier = 4
        elif score >= 80:
            tier = 3
        elif score >= 65:
            tier = 2
    elif status in {"等转强", "防守观察"}:
        tier = 2
    elif status == "冲高减仓":
        tier = 0
    return min(tier, 5)


def base_weight(atr_level: str) -> int:
    idx = ATRLV_INDEX.get(atr_level, 1)
    return BASE_WEIGHTS.get(idx, 10)
