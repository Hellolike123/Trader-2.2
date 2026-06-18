from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest
from run_analysis import build_signal, _map_fusion_to_signal


def test_map_fusion_buy():
    assert _map_fusion_to_signal("半仓试 (多方主导)") == ("track", "bullish", "track")
    assert _map_fusion_to_signal("增持") == ("track", "bullish", "track")

def test_map_fusion_hold():
    assert _map_fusion_to_signal("持股观望") == ("observe", "neutral", "observe")

def test_map_fusion_sell():
    assert _map_fusion_to_signal("减仓") == ("defensive", "bearish", "wait")
    assert _map_fusion_to_signal("空仓/止损") == ("defensive", "bearish", "wait")

def test_map_fusion_unmapped():
    assert _map_fusion_to_signal("未知动作") is None
    assert _map_fusion_to_signal("") is None


def _make_report_with_fusion(fusion_action, confidence=0.5):
    return {
        "name": "测试", "symbol": "688248.SH",
        "analysis_time": "2026-05-12",
        "current": 100,
        "support": 90, "resistance": 110, "confirm": 105,
        "stop": 85, "take": 120, "stage": "震荡",
        "scene": "低吸观察",
        "market_env": {"level": "正常"},
        "fusion": {
            "action": fusion_action,
            "confidence": confidence,
            "weighted_score": 0.6,
            "regime": "正常",
            "disagreement": 0,
            "signals_detail": {
                "chan": {"direction": 1, "confidence": 0.6},
                "momentum": {"direction": 1, "confidence": 0.5},
                "wyckoff": {"direction": 1, "confidence": 0.4},
            },
        },
    }

def test_fusion_confident():
    r = _make_report_with_fusion("增持", confidence=0.5)
    sig = build_signal(r)
    assert sig["signal_type"] == "track"
    assert sig["direction"] == "bullish"
    assert sig.get("fusion_override") is True

def test_fusion_low_confidence():
    r = _make_report_with_fusion("增持", confidence=0.1)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_fusion_threshold():
    r = _make_report_with_fusion("增持", confidence=0.2)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_fusion_no_key():
    r = _make_report_with_fusion("增持", confidence=0.5)
    del r["fusion"]
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_fusion_all_zeros():
    r = _make_report_with_fusion("增持", confidence=0.5)
    for k in ("chan", "momentum", "wyckoff"):
        r["fusion"]["signals_detail"][k]["direction"] = 0
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_fusion_unmapped_action():
    r = _make_report_with_fusion("UNKNOWN_ACTION", confidence=0.5)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_fusion_same_direction():
    r = _make_report_with_fusion("增持", confidence=0.5)
    r["stage"] = "走强"
    r["scene"] = "突破确认"
    sig = build_signal(r)
    assert sig.get("fusion_override") is None
