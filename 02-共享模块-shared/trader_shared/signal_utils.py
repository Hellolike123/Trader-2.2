"""Shared signal processing utilities.

Extracted from signal_tracker to break signal_store's dependency on
private (underscore-prefixed) symbols in signal_tracker.

Public API:
    normalize_signal_id — generate deterministic 16-hex signal ID
    normalize_date      — zero-pad YYYY-MM-DD dates
    normalize_signal_type — map legacy type names → v1 canonical names
    normalize_symbol     — bare 6-digit code → 6-digit.SH/SZ
    price_from_trigger   — extract price string from signal trigger dict
"""
from __future__ import annotations

import hashlib
from typing import Any

# ── Signal ID generation ───────────────────────────────────────────

def normalize_signal_id(symbol: str, date: str, signal_type: str, price: str | float | Any) -> str:
    """Generate unified signal ID (SHA256, 16 hex chars = 48 bits entropy).
    
    Ensures unicode and case normalization, symbol formatting, date formatting,
    and consistent price decimal representation.
    """
    import unicodedata
    # 1. Normalize symbol
    sym_norm = unicodedata.normalize("NFC", str(symbol or "")).strip().upper()
    sym_norm = normalize_symbol(sym_norm)

    # 2. Normalize date
    dt_norm = unicodedata.normalize("NFC", str(date or "")).strip()
    dt_norm = normalize_date(dt_norm)

    # 3. Normalize signal type
    st_norm = unicodedata.normalize("NFC", str(signal_type or "")).strip()
    st_norm = normalize_signal_type(st_norm)

    # 4. Normalize price to 2-decimal string
    p_val = _safe_price(price)
    price_norm = f"{p_val:.2f}"

    key = f"{sym_norm}|{dt_norm}|{st_norm}|{price_norm}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ── Type / date / symbol normalizers ───────────────────────────────

_SIGNAL_TYPE_MAP: dict[str, str] = {
    # Chinese legacy names
    "低吸观察": "low_buy_watch",
    "低吸已触发": "low_buy_triggered",
    "高抛已触发": "high_sell_triggered",
    "高抛观察": "high_sell_watch",
    "持股观望": "hold_observe",
    "增持": "add_position",
    "减仓": "reduce_position",
    "空仓/止损": "stop_loss",
    "防守观察": "defensive_watch",
    "等转强": "wait_for_strength",
    "持仓": "hold",
    "止损": "stop_loss",
    "追涨": "chase_rally",
    "背驰入场": "divergence_entry",
    # English legacy names
    "low_buy": "low_buy_watch",
    "high_sell": "high_sell_watch",
    "wait": "wait_for_confirmation",
    # English canonical names (pass-through)
    "low_buy_watch": "low_buy_watch",
    "low_buy_triggered": "low_buy_triggered",
    "high_sell_triggered": "high_sell_triggered",
    "high_sell_watch": "high_sell_watch",
    "trigger_expired": "trigger_expired",
    "blocked": "blocked",
    "hold_observe": "hold_observe",
    "add_position": "add_position",
    "reduce_position": "reduce_position",
    "stop_loss": "stop_loss",
    "defensive_watch": "defensive_watch",
    "wait_for_strength": "wait_for_strength",
    "hold": "hold",
    "chase_rally": "chase_rally",
    "divergence_entry": "divergence_entry",
    "track": "track",
    "risk_stop": "risk_stop",
    "reduce": "reduce",
    "observe": "observe",
    "defensive": "defensive",
    "review_result": "review_result",
    "high_sell_watch": "high_sell_watch",
    "low_sell_triggered": "low_sell_triggered",
    "low_sell_watch": "low_sell_watch",
    "completed_5m_confirm": "completed_5m_confirm",
    "price_confirm": "price_confirm",
}


def normalize_signal_type(raw_type: str) -> str:
    """Normalize signal type: map legacy names to v1 canonical names."""
    return _SIGNAL_TYPE_MAP.get(raw_type, raw_type)


def normalize_date(raw: str) -> str:
    """Normalize date strings to zero-padded YYYY-MM-DD.

    Handles non-zero-padded dates like '2025-5-2' -> '2025-05-02'.
    Handles datetime strings '2025-05-02T14:30:00' -> '2025-05-02'.
    """
    s = str(raw).split("T")[0].split(" ")[0]
    try:
        from datetime import datetime
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    return s[:10]


def normalize_symbol(symbol: str) -> str:
    """Ensure bare 6-digit codes get exchange suffix.

    688248 -> 688248.SH (shanghai), 000001 -> 000001.SZ (shenzhen)
    """
    if not symbol or "." in symbol:
        return symbol
    s = str(symbol).strip()
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9", "5")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


# ── Price extraction from signal dict ──────────────────────────────


def _safe_price(v: Any) -> float:
    """Safely extract a float price from various input types."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(v, dict):
        for key in ("price", "current", "value", "amount"):
            if key in v:
                try:
                    return float(v[key])
                except (ValueError, TypeError):
                    continue
    return 0.0


def price_from_trigger(sig: dict[str, Any]) -> str | None:
    """Extract formatted price string from a signal's trigger dict.

    Priority: trigger.price > current field.
    Returns two-decimal string or None if no valid price found.
    """
    tp = sig.get("trigger")
    if isinstance(tp, dict):
        p = tp.get("price")
        if p is not None and _safe_price(p) > 0:
            return f"{_safe_price(p):.2f}"
    curr = sig.get("current")
    if curr is not None and _safe_price(curr) > 0:
        return f"{_safe_price(curr):.2f}"
    return None


def build_signal_key(sig: dict[str, Any]) -> tuple[str, str, str, str]:
    """Generate canonical (symbol, date, type, price) key for matching.

    Matches the 4-key format used in signal_results.jsonl.
    """
    nk = normalize_symbol(str(sig.get("symbol") or ""))
    nd = normalize_date(str(sig.get("trade_date") or str(sig.get("analysis_time", "")).split("T")[0]))
    nt = str(sig.get("signal_type") or "unknown").strip()
    nt = normalize_signal_type(nt)
    ps = price_from_trigger(sig)
    return (nk, nd, nt, ps or "")
