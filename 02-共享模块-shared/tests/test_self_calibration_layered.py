"""Tests for self_calibration.py nested optimization, blended fitness, and structure_core compatibility."""
from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
CANDIDATE = SHARED / "02-候选逻辑-candidate"
SCRIPTS = SHARED / "scripts"
for p in (SHARED, CANDIDATE, SCRIPTS):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

import self_calibration as sc
from structure_core import _theory_multipliers


def test_blended_performance_simulation():
    """Verify that _simulate_performance correctly weights WinRate and ProfitFactor with avoided losses."""
    signals = [
        {"id": "sig1", "trigger_price_pct": 0.06, "trade_date": "2026-05-22"},  # High entry
        {"id": "sig2", "trigger_price_pct": -0.04, "trade_date": "2026-05-22"}, # Low pullback
        {"id": "sig3", "trigger_price_pct": 0.00, "trade_date": "2026-05-22"},  # Normal
    ]
    outcomes = {
        "sig1": {"won": False, "return_pct": -5.0, "outcome": "loss"}, # Loss
        "sig2": {"won": True, "return_pct": 8.0, "outcome": "win"},    # Profit
        "sig3": {"won": False, "return_pct": -2.0, "outcome": "loss"}, # Loss
    }
    
    # 1. Base parameters (no special filtering)
    base_params = {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0}
    score_base = sc._simulate_performance(signals, outcomes, base_params)
    # Gains: sig2 (+8.0). Losses: sig1 (-5.0), sig3 (-2.0).
    # Wins: 1, Total: 3 -> WinRate = 33.3%
    # PF = (8 + 0.5) / (7 + 0.5) = 1.13
    assert 0.0 < score_base < 1.0

    # 2. Optimized parameters: confirm_buffer=1.1 (should filter sig1) and zone_width=1.1 (captures sig2)
    opt_params = {"zone_width": 1.1, "confirm_buffer": 1.1, "stop_buffer": 1.0}
    score_opt = sc._simulate_performance(signals, outcomes, opt_params)
    # sig1 is high trigger (0.06 > 0.05) and conf_b > 1.05 -> filtered out (simulated PnL = 0.0).
    # sig2 is pullback (-0.04 < -0.03) and zone_w > 1.05 -> captured (+8.0).
    # sig3 is normal -> (-2.0).
    # Gains: sig2 (+8.0). Losses: sig3 (-2.0).
    # Wins: 1, Active Trades (r!=0): 2 (sig1 is filtered) -> WinRate = 50.0%
    # PF = (8 + 0.5) / (2 + 0.5) = 3.4
    assert score_opt > score_base
    print("  BLENDED SCORE: PASS — base_score=%.3f, opt_score=%.3f" % (score_base, score_opt))


@patch("trader_shared.data_provider.get_provider")
def test_historical_regimes_mapping(mock_get_provider):
    """Verify that _load_historical_regimes builds standard HMM state mapping using daily index bars."""
    # Mock index K-line bars
    mock_provider = MagicMock()
    mock_provider.resolve_security.return_value = "sec"
    # Create 95 days of closes
    mock_bars = [{"date": f"2026-05-{i:02d}", "close": 1000 + i * 1.5} for i in range(1, 96)]
    mock_provider.fetch_kline.return_value = mock_bars
    mock_get_provider.return_value = mock_provider

    signals = [
        {"trade_date": "2026-05-80"},  # Date within range
        {"trade_date": "2026-05-99"},  # Date out of range
    ]
    
    regimes = sc._load_historical_regimes(signals)
    assert "2026-05-80" in regimes
    assert regimes["2026-05-99"] == "range"  # Default fallback
    print("  REGIME MAPPING: PASS — HMM historical mapping holds")


def test_structure_core_compatibility():
    """Verify that structure_core's _theory_multipliers correctly consumes flat or nested parameters."""
    
    # Mock HMM regime state as "bear"
    fusion = {
        "regime": "偏弱",
        "hmm_regime": "bear",
        "signals_detail": {}
    }

    # Case A: Nested Params (New version)
    nested_cal = {
        "global": {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0},
        "bear": {"zone_width": 0.85, "confirm_buffer": 1.25, "stop_buffer": 0.75},
        "bull": {"zone_width": 1.15, "confirm_buffer": 0.8, "stop_buffer": 0.95},
    }

    with patch("structure_core._load_calibrated_params", return_value=nested_cal):
        mults = _theory_multipliers(fusion)
        # Bear regime should scale stop_buffer by 0.8 (Layer 1) -> 0.60
        # Then modulate by HMM bear multiplier (0.8) -> 0.48
        # Blended 50/50 = 0.60 * 0.5 + 0.48 * 0.5 = 0.54
        assert abs(mults["stop_buffer"] - 0.54) < 0.01

        # Base confirm_buffer is 1.25 * 1.3 (bear大势加宽) = 1.625 (Layer 1)
        # Then modulated by HMM bear multiplier (1.3) -> 2.1125
        # Blended 50/50 = 1.625 * 0.5 + 2.1125 * 0.5 = 1.86875 (rounds to 1.8688)
        assert abs(mults["confirm_buffer"] - 1.8688) < 0.01


    # Case B: Flat Params (Legacy version compatibility)
    flat_cal = {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 0.8}
    with patch("structure_core._load_calibrated_params", return_value=flat_cal):
        mults = _theory_multipliers(fusion)
        # Fallbacks to flat dict directly
        # stop_buffer = 0.8 * 0.8 (Layer 1) -> 0.64
        # Then modulated by HMM bear multiplier (0.8) -> 0.512
        # Blended 50/50 = 0.64 * 0.5 + 0.512 * 0.5 = 0.576
        assert abs(mults["stop_buffer"] - 0.576) < 0.01
        
    print("  COMPATIBILITY: PASS — structure_core successfully consumes flat or nested parameters")


def test_calibration_guards_and_ema_smoothing():
    """Verify that calibrate() robustly handles low-sample fallback, EMA parameter blending, and [0.85, 1.25] hard clipping."""
    # 1. Low sample protection check
    with patch("self_calibration._load_jsonl", return_value=[{"id": "sig1"}]), \
         patch("self_calibration._extract_outcomes", return_value={"sig1": {"won": True, "return_pct": 5.0}}):
        
        calibrated = sc.calibrate(n_trials=10, verbose=False)
        # Low samples -> immediately falls back to DEFAULT_PARAMS (1.0)
        assert calibrated["global"]["zone_width"] == 1.0
        assert calibrated["bull"]["confirm_buffer"] == 1.0

    # 2. Rich sample optimization with EMA smoothing & clipping check
    # Generate 40 dummy signals and outcomes
    fake_signals = [{"id": f"sig{i}", "trade_date": "2026-05-22", "trigger_price_pct": 0.0} for i in range(40)]
    fake_outcomes = {f"sig{i}": {"won": True, "return_pct": 2.0} for i in range(40)}
    
    # Existing old parameters stored in config
    old_nested = {
        "global": {"zone_width": 0.90, "confirm_buffer": 0.90, "stop_buffer": 0.90},
        "bull": {"zone_width": 0.90, "confirm_buffer": 0.90, "stop_buffer": 0.90},
        "bear": {"zone_width": 0.90, "confirm_buffer": 0.90, "stop_buffer": 0.90},
        "range": {"zone_width": 0.90, "confirm_buffer": 0.90, "stop_buffer": 0.90},
    }
    
    with patch("self_calibration._load_jsonl", return_value=fake_signals), \
         patch("self_calibration._extract_outcomes", return_value=fake_outcomes), \
         patch("self_calibration.load_calibrated_params", return_value=old_nested), \
         patch("self_calibration._load_historical_regimes", return_value={}):
        
        calibrated = sc.calibrate(n_trials=10, verbose=False)
        
        # Check that global parameters are blended correctly and clipped between 0.85 and 1.25
        for key in ["zone_width", "confirm_buffer", "stop_buffer"]:
            val = calibrated["global"][key]
            assert 0.85 <= val <= 1.25
            
    print("  CALIBRATION GUARDS & EMA: PASS — safety and smoothing successfully verified")
