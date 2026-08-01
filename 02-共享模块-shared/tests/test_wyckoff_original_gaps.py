"""威科夫原典缺口补齐 + 打分互斥：单元测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader_shared.wyckoff_core import (
    _resolve_score_conflicts,
    calculate_wyckoff_score,
    format_wyckoff_oneline,
)
from trader_shared.wyckoff_events import (
    _cause_effect_targets,
    _detect_preliminary_support,
    _detect_preliminary_supply,
    _detect_utad,
)


def test_score_conflict_sc_sow_prefers_accumulation_when_ar():
    suppress = _resolve_score_conflicts(
        {"sc_signal": True, "sow_signal": True, "ar_signal": True}
    )
    assert "sow_signal" in suppress
    assert "sc_signal" not in suppress


def test_score_conflict_sc_sow_prefers_breakdown_without_ar():
    suppress = _resolve_score_conflicts(
        {"sc_signal": True, "sow_signal": True, "ar_signal": False}
    )
    assert "sc_signal" in suppress


def test_score_conflict_lps_lpsy_with_distribution():
    suppress = _resolve_score_conflicts(
        {"lps_signal": True, "lpsy_signal": True, "bc_signal": True}
    )
    assert "lps_signal" in suppress
    assert "lpsy_signal" not in suppress


def test_score_conflict_spring_ut_with_sos_keeps_spring():
    suppress = _resolve_score_conflicts(
        {
            "spring_signal": True,
            "upthrust_signal": True,
            "sos_signal": True,
            "spring_premature": False,
            "upthrust_premature": False,
        }
    )
    assert "upthrust_signal" in suppress


def test_score_conflict_ar_are_prefers_dist_when_bc():
    suppress = _resolve_score_conflicts(
        {"ar_signal": True, "are_signal": True, "bc_signal": True}
    )
    assert "ar_signal" in suppress
    assert "are_signal" not in suppress


def test_score_conflict_ar_are_prefers_acc_when_sc():
    suppress = _resolve_score_conflicts(
        {"ar_signal": True, "are_signal": True, "sc_signal": True}
    )
    assert "are_signal" in suppress
    assert "ar_signal" not in suppress


def test_score_conflict_trend_twins_ambiguous_suppress_both():
    suppress = _resolve_score_conflicts(
        {"trend_pullback_signal": True, "trend_rally_signal": True}
    )
    assert "trend_pullback_signal" in suppress
    assert "trend_rally_signal" in suppress


def test_calculate_score_applies_suppress():
    """SC+SOW+AR 时不应因 SOW 负分把 raw 抹平到接近 0。"""
    bars = [
        {
            "open": 10 + i * 0.01,
            "high": 11 + i * 0.01,
            "low": 9 + i * 0.01,
            "close": 10 + i * 0.01,
            "volume": 1000,
        }
        for i in range(40)
    ]
    analysis = {
        "sc_signal": True,
        "sow_signal": True,
        "ar_signal": True,
        "spring_signal": False,
        "upthrust_signal": False,
        "bc_signal": False,
        "bullish_volume_divergence": False,
        "bearish_volume_divergence": False,
        "spring_premature": False,
        "upthrust_premature": False,
        "tr_quality": None,
        "phase_confidence_delta": 0,
    }
    out = calculate_wyckoff_score(bars, analysis=analysis)
    assert any("互斥抑制" in s for s in out["signals"])
    assert out["raw"] > 0  # SC+AR 看多，SOW 被抑


def test_cause_effect_targets_1to1():
    """无 bars 时回退高度 1:1（数字与旧契约一致）。"""
    ce = _cause_effect_targets({"tr_upper": 20.0, "tr_lower": 10.0})
    assert ce["cause_effect_up_target"] == 30.0
    assert ce["cause_effect_down_target"] == 0.0
    assert ce["cause_effect_range"] == 10.0
    assert ce.get("pnf_method") == "height_1to1_fallback"


def test_utad_requires_distribution_background():
    bars = [
        {
            "open": 20,
            "high": 22,
            "low": 19,
            "close": 21,
            "volume": 1000 + i,
        }
        for i in range(30)
    ]
    no_bg = _detect_utad(bars, bc_signal=False, sow_signal=False, upthrust_signal=True)
    assert no_bg["utad_signal"] is False
    with_bg = _detect_utad(
        bars,
        bc_signal=True,
        sow_signal=False,
        upthrust_signal=True,
        upthrust_result={
            "upthrust_signal": True,
            "upthrust_price": 21.0,
            "upthrust_strength": "ordinary",
        },
    )
    assert with_bg["utad_signal"] is True


def test_format_utad_and_bu_oneline():
    assert "UTAD" in format_wyckoff_oneline({"utad_signal": True}) or "派发末" in format_wyckoff_oneline(
        {"utad_signal": True}
    )
    line = format_wyckoff_oneline({"bu_signal": True})
    assert "Backup" in line or "回踩" in line


def test_ps_psy_empty_on_short_bars():
    short = [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] * 5
    assert _detect_preliminary_support(short)["ps_signal"] is False
    assert _detect_preliminary_supply(short)["psy_signal"] is False
