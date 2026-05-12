from __future__ import annotations

from pathlib import Path
import sys


CONTRACT_DIR = Path(__file__).resolve().parent
if str(CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACT_DIR))

from signal_contract import assert_valid_signal, normalize_signal, validate_signal


def valid_signal() -> dict:
    return {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": "688248.SH",
        "name": "南网科技",
        "trade_date": "2026-05-01",
        "analysis_time": "2026-05-01 10:35",
        "signal_type": "wait_for_confirmation",
        "direction": "bullish_lean",
        "action": "observe",
        "confidence": "medium",
        "data_status": "degraded",
        "trigger": {"type": "price_confirm", "price": 57.6, "text": "放量站稳后再看"},
        "invalidation": {"type": "price_break", "price": 54.8, "text": "收盘跌破后停止低吸"},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "观察区止跌前不主动买。",
    }


def test_valid_minimum_signal_passes() -> None:
    assert validate_signal(valid_signal()) == []
    assert_valid_signal(valid_signal())


def test_missing_required_field_fails() -> None:
    signal = valid_signal()
    signal.pop("symbol")

    errors = validate_signal(signal)

    assert "missing required field: symbol" in errors


def test_invalid_enum_fails() -> None:
    signal = valid_signal()
    signal["signal_type"] = "auto_order"

    errors = validate_signal(signal)

    assert "invalid signal_type: auto_order" in errors


def test_position_percentages_must_be_in_range() -> None:
    signal = valid_signal()
    signal["position"]["max_total_pct"] = 120

    errors = validate_signal(signal)

    assert "position.max_total_pct must be between 0 and 100" in errors


def test_triggered_t0_signal_does_not_require_broker_order_fields() -> None:
    signal = valid_signal()
    signal.update(
        {
            "source_skill": "t0-trader",
            "signal_type": "low_buy_triggered",
            "action": "low_buy",
            "confidence": "high",
            "data_status": "full",
            "trigger": {"type": "completed_5m_confirm", "price": 11.94, "text": "5m 止跌触发"},
        }
    )

    assert validate_signal(signal) == []
    assert "broker_order_id" not in normalize_signal(signal)


def run_tests() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run_tests()
