"""威科夫原典缺口补齐 + 打分互斥：单元测试。

含 P3 有界落地：JAC / Stopping Volume / CM mode / AR 量能 P2-C。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader_shared.wyckoff_core import (
    _resolve_score_conflicts,
    calculate_wyckoff_score,
    format_wyckoff_event_light,
    format_wyckoff_oneline,
    wyckoff_analysis,
)
from trader_shared.wyckoff_events import (
    _cause_effect_targets,
    _classify_cm_mode,
    _detect_ar,
    _detect_jump_across_creek,
    _detect_preliminary_support,
    _detect_preliminary_supply,
    _detect_stopping_volume,
    _detect_utad,
)
from trader_shared.wyckoff_view import to_wyckoff_state_view


def _bar(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


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


# ── A) Jump Across the Creek ───────────────────────────────────────


def test_jac_signal_true_when_jump_and_hold():
    """合成越过 creek 站稳 → jac_signal True。"""
    creek = 100.0
    bars = [_bar(98, 99, 97, 98.5, 120) for _ in range(18)]
    # 跳溪阳线
    bars.append(_bar(99.0, 102.5, 98.8, 102.0, 200))
    # 站稳 2 根
    bars.append(_bar(101.5, 103.0, 100.5, 101.8, 150))
    bars.append(_bar(101.6, 102.8, 100.8, 102.2, 140))
    out = _detect_jump_across_creek(
        bars,
        tr_ctx={"tr_upper": creek},
        sos_signal=True,
    )
    assert out["jac_signal"] is True
    assert out["jac_price"] is not None
    assert "跳溪" in (out["jac_reason"] or "") or "JAC" in (out["jac_reason"] or "")


def test_jac_signal_false_when_not_held():
    """越过 creek 后跌回溪下 → jac_signal False。"""
    creek = 100.0
    bars = [_bar(98, 99, 97, 98.5, 120) for _ in range(18)]
    bars.append(_bar(99.0, 102.5, 98.8, 102.0, 200))
    bars.append(_bar(101.0, 101.5, 98.0, 98.5, 150))  # 跌回溪下
    out = _detect_jump_across_creek(
        bars,
        tr_ctx={"tr_upper": creek},
        sos_signal=True,
    )
    assert out["jac_signal"] is False


def test_jac_event_light_and_active_events():
    line = format_wyckoff_event_light({"jac_signal": True, "timeframe": "daily"})
    assert "JAC" in line or "跳溪" in line
    view = to_wyckoff_state_view({"jac_signal": True, "jac_reason": "越过溪", "jac_price": 10.0})
    assert "jac" in view["active_events"]


# ── B) Stopping Volume ─────────────────────────────────────────────


def test_stopping_volume_typical_bar():
    """下跌末段放量宽幅、收盘上半 → 止跌量亮。"""
    bars = []
    for i in range(20):
        p = 120 - i * 1.5
        bars.append(_bar(p, p + 0.8, p - 0.8, p - 0.3, 100))
    # 止跌量棒：放量、宽幅、收上半
    bars.append(_bar(88.0, 92.0, 86.0, 91.0, 400))
    out = _detect_stopping_volume(bars)
    assert out["stopping_volume_signal"] is True
    assert out["stopping_volume_price"] == 91.0


def test_stopping_volume_ordinary_bear_veto():
    """普通阴线贴地收 → 否决。"""
    bars = []
    for i in range(20):
        p = 120 - i * 1.5
        bars.append(_bar(p, p + 0.8, p - 0.8, p - 0.3, 100))
    bars.append(_bar(90.0, 90.5, 86.0, 86.2, 400))  # 放量但收下半
    out = _detect_stopping_volume(bars)
    assert out["stopping_volume_signal"] is False


def test_stopping_volume_no_double_score_with_sc():
    """与 SC 同亮时止跌量不计分。"""
    bars = [_bar(10, 11, 9, 10, 1000) for _ in range(40)]
    with_sc = calculate_wyckoff_score(
        bars,
        analysis={
            "sc_signal": True,
            "stopping_volume_signal": True,
            "spring_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "bullish_volume_divergence": False,
            "bearish_volume_divergence": False,
            "tr_quality": None,
            "phase_confidence_delta": 0,
        },
    )
    assert not any("止跌量" in s for s in with_sc["signals"])
    no_sc = calculate_wyckoff_score(
        bars,
        analysis={
            "sc_signal": False,
            "stopping_volume_signal": True,
            "spring_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "bullish_volume_divergence": False,
            "bearish_volume_divergence": False,
            "tr_quality": None,
            "phase_confidence_delta": 0,
        },
    )
    assert any("止跌量" in s for s in no_sc["signals"])


# ── C) CM 行为模式 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phase,events,expected",
    [
        ("accumulation_a", {"sc_signal": True}, "markdown_absorption"),
        ("accumulation_c", {"spring_signal": True}, "markdown_absorption"),
        ("markup", {"sos_signal": True}, "rally_absorption"),
        ("accumulation_d", {"bu_signal": True}, "rally_absorption"),
        ("accumulation_b", {"compression_signal": True}, "range_absorption"),
        ("distribution_a", {"bc_signal": True}, "rally_distribution"),
        ("distribution_b", {"sow_signal": True}, "range_distribution"),
        ("distribution_c", {"utad_signal": True}, "shakeout_distribution"),
        ("none", {}, "none"),
    ],
)
def test_cm_mode_mapping(phase, events, expected):
    out = _classify_cm_mode(phase=phase, signals=events)
    assert out["cm_mode"] == expected


def test_cm_mode_on_analysis_and_view():
    bars = [_bar(90, 91, 89, 90, 100) for _ in range(14)]
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))
    bars.append(_bar(83.5, 87.0, 83.0, 86.0, 130))
    r = wyckoff_analysis(bars, use_persisted_phase=False)
    assert "cm_mode" in r
    assert r["cm_mode"] in {
        "markdown_absorption",
        "rally_absorption",
        "range_absorption",
        "rally_distribution",
        "range_distribution",
        "shakeout_distribution",
        "none",
    }
    view = to_wyckoff_state_view(r)
    assert view.get("cm_mode") == r["cm_mode"]


# ── D) AR 量能 P2-C ────────────────────────────────────────────────


def _sc_base_then(*extra):
    # MIN_BARS+3=18；基底须够长才能进 AR 扫描
    bars = [_bar(90, 91, 89, 90, 100) for _ in range(16)]
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.extend(extra)
    return bars


def test_ar_prefer_selects_weak_volume_bar(monkeypatch):
    """多候选时 prefer 弱于 SC 的反弹棒。"""
    import trader_shared.config as cfg

    monkeypatch.setattr(cfg, "WYCKOFF_AR_PREFER_WEAK_VS_SC", True)
    monkeypatch.setattr(cfg, "WYCKOFF_AR_REQUIRE_WEAK_VS_SC", False)
    bars = _sc_base_then(
        _bar(83.2, 86.5, 83.0, 85.5, 3000),  # 强量候选（先出现）
        _bar(85.0, 87.5, 84.5, 87.0, 200),  # 弱量候选（prefer）
    )
    ar = _detect_ar(bars)
    assert ar["ar_signal"] is True, ar.get("ar_reason")
    assert ar["ar_volume_soft"] is False
    assert ar["ar_bar_idx"] == len(bars) - 1
    assert ar["ar_high"] == 87.5


def test_ar_require_rejects_strong_vs_sc(monkeypatch):
    """REQUIRE=True 时放量相对 SC 的 AR 被否。"""
    import trader_shared.config as cfg

    monkeypatch.setattr(cfg, "WYCKOFF_AR_REQUIRE_WEAK_VS_SC", True)
    monkeypatch.setattr(cfg, "WYCKOFF_AR_PREFER_WEAK_VS_SC", True)
    bars = _sc_base_then(_bar(83.2, 87.0, 83.0, 86.0, 3000))
    ar = _detect_ar(bars)
    assert ar["ar_signal"] is False
    assert "REQUIRE" in (ar["ar_reason"] or "") or "否决" in (ar["ar_reason"] or "")


def test_ar_default_nanwang_delayed_weak_still_established():
    """默认 flag：南网类延迟弱量 AR 仍可 established。"""
    bars = [_bar(90, 91, 89, 90, 100) for _ in range(14)]
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))
    for i in range(4):
        bars.append(_bar(83.2 + i * 0.1, 83.6 + i * 0.1, 82.8 + i * 0.1, 83.3 + i * 0.1, 120))
    bars.append(_bar(83.5, 87.0, 83.0, 86.0, 130))
    r = wyckoff_analysis(bars, use_persisted_phase=False)
    assert r["sc_signal"] is True
    assert r["ar_signal"] is True
    assert r["phase_a_status"] == "established"
    assert r["ar_volume_soft"] is False


def test_jac_not_in_score():
    """JAC 不计分。"""
    bars = [_bar(10, 11, 9, 10, 1000) for _ in range(40)]
    out = calculate_wyckoff_score(
        bars,
        analysis={
            "jac_signal": True,
            "sc_signal": False,
            "spring_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "bullish_volume_divergence": False,
            "bearish_volume_divergence": False,
            "tr_quality": None,
            "phase_confidence_delta": 0,
        },
    )
    assert not any("JAC" in s or "跳溪" in s for s in out["signals"])
    assert out["raw"] == 0
