from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

try:
    from models import DATA_STATUS_MAP, map_data_status_to_signal
except ImportError:
    DATA_STATUS_MAP: dict[str, str] = {
        "complete": "full",
        "partial": "partial",
        "degraded": "degraded",
        "failed": "degraded",
    }

    def map_data_status_to_signal(
        raw_status: str,
        is_trading_time: bool = True,
        is_trading_day: bool = True,
    ) -> str:
        if not is_trading_time:
            return "partial"
        return DATA_STATUS_MAP.get(raw_status, "degraded")


CONTRACT_VERSION = "trader_signal_v1"

# ── Date/time pattern helpers ──────────────────────────────────────
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$")

# ── Required fields ───────────────────────────────────────────────
REQUIRED_FIELDS = {
    "contract",
    "source_skill",
    "symbol",
    "name",
    "trade_date",
    "analysis_time",
    "signal_type",
    "direction",
    "action",
    "confidence",
    "data_status",
    "trigger",
    "invalidation",
    "position",
    "risk_flags",
    "summary",
}

# ── Source skills — strict (no legacy aliases) ────────────────────
ALLOWED_SOURCE_SKILLS = {
    "trader",
    "t0-trader",
    "trader-compare",
    "trader-portfolio",
    "review-trader",
    "trader-pool",
}

# ── Main protocol signal types ────────────────────────────────────
# Only canonical names live in the main set.  Legacy aliases are
# tracked separately so they can produce warnings rather than silent
# acceptance.
_STRICT_SIGNAL_TYPES: set[str] = {
    "observe",
    "wait_for_confirmation",
    "track",
    "low_buy_watch",
    "low_buy_triggered",
    "high_sell_watch",
    "high_sell_triggered",
    "reduce",
    "defensive",
    "risk_stop",
    "trigger_expired",
    "blocked",
    "review_result",
    # Additional canonical types used across skills.
    "add_position",
    "reduce_position",
    "hold_observe",
    "defensive_watch",
    "wait_for_strength",
    "hold",
    "chase_rally",
    "divergence_entry",
    "completed_5m_confirm",
    "price_confirm",
    "watch_price",
    "price_break",
    "stop_loss",
    "low_sell_triggered",
    "low_sell_watch",
}

# Legacy / deprecated aliases that still pass for backward compat.
# These should produce a deprecation warning when encountered.
LEGACY_SIGNAL_TYPES: set[str] = {
    "low_buy",          # → low_buy_watch
    "high_sell",        # → high_sell_watch
    "wait",             # → wait_for_confirmation
    "pilot_entry",
    "stop_low_buy",
    "stop_high_sell",
    # These pass-through values are from test data but not canonical.
    "review_result",    # duplicate — already in strict
}

# Convenience: main protocol + legacy for full backward compatibility.
ALLOWED_SIGNAL_TYPES = _STRICT_SIGNAL_TYPES | LEGACY_SIGNAL_TYPES

# ── Main protocol directions ──────────────────────────────────────
ALLOWED_DIRECTIONS = {
    "bullish",
    "bearish",
    "neutral",
    "bullish_lean",
    "bearish_lean",
}

# ── Main protocol actions ─────────────────────────────────────────
ALLOWED_ACTIONS = {
    "no_action",
    "observe",
    "wait",
    "track",
    "pilot_entry",
    "low_buy",
    "high_sell",
    "reduce",
    "stop_low_buy",
    "stop_high_sell",
}

# ── Confidence / data status ──────────────────────────────────────
ALLOWED_CONFIDENCE = {"low", "medium", "high"}

# Strict (main protocol only) — the four canonical states.
_STRICT_DATA_STATUS: set[str] = {
    "full",
    "partial",
    "degraded",
    "failed",
}

# Legacy — kept for backward compat but should not be written by
# new code.  "fresh" and "stale" were informal additions that never
# made it into the formal protocol.
LEGACY_DATA_STATUS: set[str] = {
    "fresh",
    "stale",
}

ALLOWED_DATA_STATUS = _STRICT_DATA_STATUS | LEGACY_DATA_STATUS


# ── Normalization ─────────────────────────────────────────────────

def normalize_signal(signal: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(signal)
    normalized.setdefault("contract", CONTRACT_VERSION)
    normalized.setdefault("confidence", "low")
    # Main protocol default data_status is "degraded".
    normalized.setdefault("data_status", "degraded")
    normalized.setdefault("direction", "neutral")
    normalized.setdefault("action", "observe")
    normalized.setdefault("risk_flags", [])
    normalized.setdefault("trigger", {})
    normalized.setdefault("invalidation", {})
    normalized.setdefault("position", {})
    return normalized


# ── Validation ────────────────────────────────────────────────────

def validate_signal(signal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(signal, dict):
        return ["signal must be an object"]

    normalized = normalize_signal(signal)
    for field in sorted(REQUIRED_FIELDS):
        if field not in normalized:
            errors.append(f"missing required field: {field}")

    if normalized.get("contract") != CONTRACT_VERSION:
        errors.append(f"invalid contract: {normalized.get('contract')}")

    _validate_enum(errors, normalized, "source_skill", ALLOWED_SOURCE_SKILLS)
    _validate_enum(errors, normalized, "signal_type", ALLOWED_SIGNAL_TYPES)
    _validate_enum(errors, normalized, "direction", ALLOWED_DIRECTIONS)
    _validate_enum(errors, normalized, "action", ALLOWED_ACTIONS)
    _validate_enum(errors, normalized, "confidence", ALLOWED_CONFIDENCE)
    _validate_enum(errors, normalized, "data_status", ALLOWED_DATA_STATUS)

    _validate_text(errors, normalized, "symbol")
    _validate_text(errors, normalized, "name")
    _validate_date(errors, normalized, "trade_date")
    _validate_text(errors, normalized, "analysis_time")
    _validate_text(errors, normalized, "summary")

    if not isinstance(normalized.get("risk_flags"), list):
        errors.append("risk_flags must be a list")
    else:
        _validate_risk_flags(errors, normalized.get("risk_flags"))

    _validate_condition(errors, normalized, "trigger")
    _validate_condition(errors, normalized, "invalidation")
    _validate_position(errors, normalized.get("position"))
    _validate_triggered_signal(errors, normalized)
    return errors


def assert_valid_signal(signal: dict[str, Any]) -> None:
    errors = validate_signal(signal)
    if errors:
        raise ValueError("; ".join(errors))


# ── Internal validators ───────────────────────────────────────────

def _validate_enum(errors: list[str], signal: dict[str, Any], field: str, allowed: set[str]) -> None:
    value = signal.get(field)
    if value is not None and value not in allowed:
        errors.append(f"invalid {field}: {value}")


def _validate_text(errors: list[str], signal: dict[str, Any], field: str) -> None:
    value = signal.get(field)
    if value is not None and not str(value).strip():
        errors.append(f"{field} must not be empty")


def _validate_date(errors: list[str], signal: dict[str, Any], field: str) -> None:
    value = signal.get(field)
    if value is not None and not _DATE_RE.match(str(value)):
        errors.append(f"{field} must be in YYYY-MM-DD format, got: {value}")


def _validate_risk_flags(errors: list[str], risk_flags: list[Any]) -> None:
    for i, flag in enumerate(risk_flags):
        if not isinstance(flag, str):
            errors.append(f"risk_flags[{i}] must be a string, got {type(flag).__name__}")


def _validate_condition(errors: list[str], signal: dict[str, Any], field: str) -> None:
    value = signal.get(field)
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return
    text = value.get("text")
    if text is not None and not str(text).strip():
        errors.append(f"{field}.text must not be empty")
    price = value.get("price")
    if price is not None:
        if not isinstance(price, (int, float)):
            errors.append(f"{field}.price must be numeric")
        elif price <= 0:
            errors.append(f"{field}.price must be positive, got {price}")


def _validate_position(errors: list[str], position: Any) -> None:
    if not isinstance(position, dict):
        errors.append("position must be an object")
        return
    max_total = position.get("max_total_pct")
    max_single = position.get("max_single_move_pct")
    for field in ("max_total_pct", "max_single_move_pct"):
        value = position.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"position.{field} must be numeric")
        elif value < 0 or value > 100:
            errors.append(f"position.{field} must be between 0 and 100")
    if (
        max_total is not None
        and max_single is not None
        and isinstance(max_total, (int, float))
        and isinstance(max_single, (int, float))
        and max_total < max_single
    ):
        errors.append("position.max_total_pct must be >= position.max_single_move_pct")


def _validate_triggered_signal(errors: list[str], signal: dict[str, Any]) -> None:
    if signal.get("signal_type") not in {"low_buy_triggered", "high_sell_triggered"}:
        return
    trigger = signal.get("trigger")
    if not isinstance(trigger, dict):
        return
    if trigger.get("price") is None:
        errors.append("trigger.price is required for triggered T0 signals")
    if not str(trigger.get("text") or "").strip():
        errors.append("trigger.text is required for triggered T0 signals")
