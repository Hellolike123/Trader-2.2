"""signal_core.build_signal：fusion action remap 须听 FUSION_OVERRIDE_ENABLED。

法源：docs/plans/signal-fusion-override-gate-handoff.md A1/A2；
对照 decision_core 同款闸门（enabled ∧ confidence > threshold）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.signal_core import build_signal, signal_state  # noqa: E402


def _bullish_vs_bearish_fusion_report() -> dict:
    """signal_state 偏多（bullish）；fusion.action 映射偏空且 conf 过默认阈值。"""
    return {
        "name": "测试",
        "symbol": "000001.SZ",
        "current": 10.5,
        "confirm": 10.0,
        "stop": 9.0,
        "support": 9.2,
        "resistance": 11.0,
        "scene": "突破确认",
        "major_stage": "主升",
        "theory_status": "突破确认",
        "data_status": "full",
        "analysis_time": "2026-08-02 10:00:00",
        "low_zone": "9.20元",
        "ma": {},
        "fusion": {
            "action": "减仓",
            "confidence": 0.7,
            "signals_detail": {
                "wyckoff": {"direction": -1},
                "chan": {"direction": -1},
            },
        },
    }


def test_a1_default_no_fusion_remap():
    """A1：默认 override=false → direction 等于 signal_state，无 fusion_override。"""
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    assert _cfg.FUSION_OVERRIDE_ENABLED is False
    assert sc.FUSION_OVERRIDE_ENABLED is False

    report = _bullish_vs_bearish_fusion_report()
    st_type, st_dir, st_action, _ = signal_state(report)
    assert st_dir == "bullish"

    sig = build_signal(report)
    assert sig["direction"] == st_dir == "bullish"
    assert sig["signal_type"] == st_type
    assert sig["action"] == st_action
    assert sig.get("fusion_override") is not True
    assert "fusion_override" not in sig


def test_a2_override_enabled_remaps(monkeypatch):
    """A2：显式开启 + 过阈值 → direction 被 remap，fusion_override is True。"""
    import trader_shared.config as _cfg
    import trader_shared.signal_core as sc

    monkeypatch.setattr(sc, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)

    report = _bullish_vs_bearish_fusion_report()
    _, st_dir, _, _ = signal_state(report)
    assert st_dir == "bullish"

    sig = build_signal(report)
    assert sig["direction"] == "bearish"
    assert sig["signal_type"] == "defensive"
    assert sig["action"] == "wait"
    assert sig.get("fusion_override") is True
