"""WyckoffStateView 薄适配：不重算检测，只映射字段。"""
from __future__ import annotations

from trader_shared.wyckoff_view import to_wyckoff_state_view


def test_empty_dict_view():
    v = to_wyckoff_state_view({})
    assert v["schema_version"] == "wyckoff_state_v1"
    assert v["bias"] == "neutral"
    assert v["active_events"] == []
    assert "威科夫" in v["summary_oneline"] or "暂无" in v["summary_oneline"] or v["summary_oneline"]


def test_unwrap_strategy_wrapper():
    raw = {
        "wyckoff": {
            "spring_signal": True,
            "spring_reason": "假跌破收回",
            "spring_price": 10.5,
            "spring_premature": False,
            "phase": "accumulation",
            "phase_label": "积累",
            "timeframe": "weekly",
            "tr_lower": 10.0,
            "tr_upper": 12.0,
            "tr_quality": 0.7,
            "tr_in_range": True,
        }
    }
    v = to_wyckoff_state_view(raw, symbol="000988", timeframe="weekly")
    assert v["symbol"] == "000988"
    assert v["timeframe"] == "weekly"
    assert "spring" in v["active_events"]
    assert v["event_detail"]["spring"]["price"] == 10.5
    assert v["bias"] == "bull"
    assert v["premature"]["spring"] is False
    assert v["tr"]["lower"] == 10.0
    assert "10.00" in v["invalidation_hint"] or "下沿" in v["invalidation_hint"]


def test_premature_spring_neutral_bias():
    v = to_wyckoff_state_view(
        {
            "spring_signal": True,
            "spring_reason": "孤立",
            "spring_premature": True,
            "phase": "none",
        }
    )
    assert v["bias"] == "neutral"
    assert v["premature"]["spring"] is True


def test_insufficient_timeframe():
    v = to_wyckoff_state_view({"timeframe": "insufficient"})
    assert v["timeframe"] == "insufficient"
    assert v["confidence"] == 0.0
    assert "周线不足" in v["summary_oneline"]


def test_bear_utad():
    v = to_wyckoff_state_view(
        {
            "utad_signal": True,
            "utad_reason": "派发后上冲",
            "phase": "distribution",
            "tr_upper": 20.0,
        }
    )
    assert v["bias"] == "bear"
    assert "utad" in v["active_events"]
