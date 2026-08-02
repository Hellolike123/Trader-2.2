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


def _make_report_with_fusion(fusion_action, confidence=0.7):
    """默认 conf 过 FUSION_CONFIDENCE_THRESHOLD(0.6)；是否 remap 仍听 FUSION_OVERRIDE_ENABLED。"""
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


def test_fusion_default_no_override():
    """默认 FUSION_OVERRIDE_ENABLED=false：高 conf 也不 remap。"""
    r = _make_report_with_fusion("增持", confidence=0.7)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_confident_when_override_enabled(monkeypatch):
    """显式开启 + conf 过阈值 → 保留旧 remap。"""
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("增持", confidence=0.7)
    sig = build_signal(r)
    assert sig["signal_type"] == "track"
    assert sig["direction"] == "bullish"
    assert sig.get("fusion_override") is True


def test_fusion_low_confidence(monkeypatch):
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("增持", confidence=0.1)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_threshold_boundary(monkeypatch):
    """严格 > threshold：等于阈值不 remap。"""
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(sc, "FUSION_CONFIDENCE_THRESHOLD", 0.6)
    monkeypatch.setattr(_cfg, "FUSION_CONFIDENCE_THRESHOLD", 0.6)

    r = _make_report_with_fusion("增持", confidence=0.6)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_no_key(monkeypatch):
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("增持", confidence=0.7)
    del r["fusion"]
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_all_zeros(monkeypatch):
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("增持", confidence=0.7)
    for k in ("chan", "momentum", "wyckoff"):
        r["fusion"]["signals_detail"][k]["direction"] = 0
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_unmapped_action(monkeypatch):
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("UNKNOWN_ACTION", confidence=0.7)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None


def test_fusion_same_direction(monkeypatch):
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    r = _make_report_with_fusion("增持", confidence=0.7)
    r["stage"] = "走强"
    r["scene"] = "突破确认"
    r["theory_status"] = "突破确认"
    r["major_stage"] = "主升"
    sig = build_signal(r)
    assert sig.get("fusion_override") is None
