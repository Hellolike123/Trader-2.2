"""威科夫 TR 成熟度 L0–L3 验收（M-R1…M-R8）。

规格：``docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`` §5。
合成 bars，禁全网抓数。
"""
from __future__ import annotations

import re

import pytest

from trader_shared.wyckoff_core import (
    _phase_a_box_phrase,
    format_wyckoff_daily_phase_light,
    format_wyckoff_midline_light,
    wyckoff_analysis,
)
from trader_shared.wyckoff_view import format_cause_effect_display


def _bar(o, h, l, c, v=1000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _decline_base(n: int = 14, vol: int = 100) -> list[dict]:
    return [_bar(90.0, 91.0, 89.0, 90.0, vol) for _ in range(n)]


def _pad_min(bars: list[dict], n: int = 25) -> list[dict]:
    out = list(bars)
    while len(out) < n:
        out.insert(0, _bar(90.0, 91.0, 89.0, 90.0, 100))
    return out


def _sc_only_bars() -> list[dict]:
    """仅 SC，无有效 AR/ST。"""
    bars = _decline_base(14)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))
    bars.append(_bar(83.2, 83.6, 83.0, 83.5, 120))
    return bars


def _sc_ar_no_st_bars() -> list[dict]:
    """SC+AR，无回测 ST：SC 后 lows 始终高于 sc_low×(1+prox≈0.03)。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC low=82；prox 上沿≈84.46
    for i in range(3):
        b = 85.0 + i * 0.2
        bars.append(_bar(b, b + 0.5, b - 0.3, b + 0.1, 150))  # low≥84.7
    bars.append(_bar(85.5, 88.0, 85.0, 87.0, 200))  # AR
    return bars


def _sc_ar_st_bars() -> list[dict]:
    """SC + 缩量回测 ST + AR（窗宽通常 < MEASURE_MIN → L2）。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(83.0, 83.4, 81.8, 82.5, 800))   # ST
    for i in range(3):
        bars.append(_bar(82.6 + i * 0.1, 83.0 + i * 0.1, 82.4 + i * 0.1, 82.7 + i * 0.1, 120))
    bars.append(_bar(83.0, 87.0, 82.8, 86.0, 130))  # AR
    return bars


def _sc_ar_st_wide_bars() -> list[dict]:
    """M-R4：在 ST 箱上略加宽至 ≥ MEASURE_MIN_BARS，且 SC 仍在 climax 窗内。"""
    bars = _sc_ar_st_bars()
    for _ in range(2):
        bars.append(_bar(84.0, 84.4, 83.7, 84.1, 110))
    return bars


def _soft_confirm_bars() -> list[dict]:
    """M-R6：AR 后价格一直高于 sc_low×(1+prox)，无回测。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(85.0, 88.0, 85.0, 87.0, 400))   # AR，low 高于 prox
    for i in range(8):
        b = 85.5 + (i % 3) * 0.2
        bars.append(_bar(b, b + 0.4, b - 0.2, b + 0.1, 120))
    return bars


def _percentile_tr_no_sc_bars() -> list[dict]:
    """M-R5：窄幅横盘，无 SC/ST 瀑布。"""
    return [_bar(10.0, 10.01, 9.99, 10.0, 30000) for _ in range(60)]


def _require_gate_fields(result: dict) -> None:
    if "tr_maturity" not in result:
        pytest.skip("depends on Gate: tr_maturity not yet in wyckoff_analysis")
    if "measure_allowed" not in result:
        pytest.skip("depends on Gate: measure_allowed not yet in wyckoff_analysis")
    if "box_display_mode" not in result:
        pytest.skip("depends on Gate: box_display_mode not yet in wyckoff_analysis")


def _mature_box_phrase(text: str) -> bool:
    """成熟「箱体 lo-hi」写法；排除「箱体未成形」。"""
    return bool(re.search(r"箱体\s+\d+\.\d+-\d+\.\d+", text or ""))


# ── 展示层（不依赖分析闸）─────────────────────────────────────


def test_box_phrase_proto_no_mature_box_word() -> None:
    phrase = _phase_a_box_phrase({
        "box_display_mode": "proto",
        "sc_low": 82.0,
        "ar_high": 87.0,
        "phase_a_status": "established",
    })
    assert "箱体" not in phrase
    assert "雏形" in phrase
    assert "待 ST" in phrase


def test_box_phrase_box_mode_writes_range() -> None:
    phrase = _phase_a_box_phrase({
        "box_display_mode": "box",
        "sc_low": 81.8,
        "ar_high": 87.0,
    })
    assert phrase == "箱体 81.80-87.00"


def test_box_phrase_none_empty() -> None:
    assert _phase_a_box_phrase({"box_display_mode": "none", "sc_low": 82.0}) == ""


def test_box_phrase_tr_maturity_l1_derives_proto() -> None:
    phrase = _phase_a_box_phrase({
        "tr_maturity": "L1",
        "sc_low": 82.0,
        "phase_a_status": "forming",
    })
    assert "雏形" in phrase
    assert "箱体" not in phrase


def test_midline_l1_proto_hint_even_when_tr_gated() -> None:
    """南网类：周线 L1 + phase_tr_gated(no_tr) + AR → 仍提示雏形，不写成熟箱体/量度。"""
    from trader_shared.wyckoff_core import format_wyckoff_midline_light

    line = format_wyckoff_midline_light(
        {
            "timeframe": "weekly",
            "phase": "none",
            "phase_label": "无明确阶段（无TR，阶段不参与定论）",
            "phase_a_status": "established",
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "no_tr",
            "tr_quality": None,
            "tr_maturity": "L1",
            "box_display_mode": "proto",
            "measure_allowed": False,
            "sc_signal": True,
            "ar_signal": True,
            "secondary_test_sc_signal": False,
            "sc_low": 37.8,
            "ar_high": 43.85,
            "ar_reason": "SC 后自动反弹",
        }
    )
    assert line.startswith("威科夫：")
    assert "雏形 37.80-43.85（待 ST）" in line
    assert "箱体 37" not in line
    assert "AR（自动反弹）" in line


# ── M-R1…M-R7 ─────────────────────────────────────────────────


def test_m_r1_sc_only_l1_no_measure() -> None:
    """M-R1：仅 SC → L1；无量度；无成熟箱体 lo-hi。"""
    result = wyckoff_analysis(_pad_min(_sc_only_bars()), use_persisted_phase=False)
    assert result["sc_signal"] is True
    assert result.get("ar_signal") is False
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L1"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "proto"
    assert result.get("cause_effect_up_target") is None
    assert result.get("cause_effect_down_target") is None
    assert format_cause_effect_display(result) == ""
    box = _phase_a_box_phrase(result)
    assert not _mature_box_phrase(box)
    assert "箱体" not in box
    assert "雏形" in box
    assert not _mature_box_phrase(format_wyckoff_daily_phase_light(result))


def test_m_r2_sc_ar_no_st_l1_forbid_box() -> None:
    """M-R2：SC+AR 无 ST → L1；禁止「箱体 lo-hi」；无量度。"""
    result = wyckoff_analysis(_pad_min(_sc_ar_no_st_bars()), use_persisted_phase=False)
    assert result["phase_a_status"] == "established"
    assert result.get("secondary_test_sc_signal") is not True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L1"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "proto"
    assert result.get("cause_effect_up_target") is None
    assert result.get("cause_effect_down_target") is None
    assert format_cause_effect_display(result) == ""
    box = _phase_a_box_phrase(result)
    assert not _mature_box_phrase(box)
    assert "箱体" not in box
    assert not _mature_box_phrase(format_wyckoff_daily_phase_light(result))
    assert not _mature_box_phrase(format_wyckoff_midline_light(result))


def test_m_r3_sc_ar_st_at_least_l2_box() -> None:
    """M-R3：SC+AR+缩量 ST → ≥L2；可写箱体 lo-hi。"""
    result = wyckoff_analysis(_pad_min(_sc_ar_st_bars()), use_persisted_phase=False)
    assert result["secondary_test_sc_signal"] is True
    assert result["ar_signal"] is True
    _require_gate_fields(result)
    assert result["tr_maturity"] in ("L2", "L3")
    assert result["box_display_mode"] == "box"
    assert _mature_box_phrase(_phase_a_box_phrase(result))
    if result["tr_maturity"] == "L2":
        assert result["measure_allowed"] is False
        assert format_cause_effect_display(result) == ""


def test_m_r4_wide_enough_l3_measure() -> None:
    """M-R4：宽度足够 → L3 + 量度（或至少 measure_allowed）。"""
    # 勿过度前插 pad：SC 须留在 climax 检测窗内
    result = wyckoff_analysis(_sc_ar_st_wide_bars(), use_persisted_phase=False)
    assert result["secondary_test_sc_signal"] is True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L3"
    assert result["measure_allowed"] is True
    assert result["box_display_mode"] == "box"
    has_targets = (
        result.get("cause_effect_up_target") is not None
        and result.get("cause_effect_down_target") is not None
    )
    assert has_targets or result["measure_allowed"] is True
    if has_targets:
        line = format_cause_effect_display(result)
        assert line.startswith("量度目标：")
        assert "非出手" in line


def test_m_r5_percentile_tr_no_sc_l0() -> None:
    """M-R5：仅分位/横盘、无 SC → L0；无量度。"""
    result = wyckoff_analysis(_percentile_tr_no_sc_bars(), use_persisted_phase=False)
    assert result.get("sc_signal") is not True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L0"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "none"
    assert result.get("cause_effect_up_target") is None
    assert result.get("cause_effect_down_target") is None
    assert format_cause_effect_display(result) == ""
    assert _phase_a_box_phrase(result) == ""


def test_m_r6_soft_confirm_no_st_l1() -> None:
    """M-R6：软确认（永不回测 SC 区）→ 无 ST；L1。"""
    result = wyckoff_analysis(_pad_min(_soft_confirm_bars()), use_persisted_phase=False)
    assert result.get("sc_signal") is True
    assert result.get("ar_signal") is True
    assert result.get("secondary_test_sc_signal") is not True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L1"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "proto"
    assert format_cause_effect_display(result) == ""
    assert "箱体" not in _phase_a_box_phrase(result)


def test_m_r7_height_1to1_label_not_pnf(monkeypatch) -> None:
    """M-R7：L3 + height_1to1_fallback → 面板不写 P&F。"""
    monkeypatch.setattr("trader_shared.wyckoff_pnf.WYCKOFF_PNF_ENABLED", False)
    result = wyckoff_analysis(_sc_ar_st_wide_bars(), use_persisted_phase=False)
    _require_gate_fields(result)
    if result["tr_maturity"] != "L3" or not result.get("measure_allowed"):
        pytest.skip("depends on Gate: L3 measure_allowed for wide ST fixture")
    assert result.get("pnf_method") == "height_1to1_fallback"
    up = result.get("cause_effect_up_target")
    down = result.get("cause_effect_down_target")
    if up is None or down is None:
        line = format_cause_effect_display({
            "cause_effect_up_target": 92.0,
            "cause_effect_down_target": 72.0,
            "pnf_method": "height_1to1_fallback",
            "measure_allowed": True,
        })
    else:
        line = format_cause_effect_display(result)
    assert "高度1:1" in line
    assert "P&F" not in line


def test_m_r8_related_pytest_smoke() -> None:
    """M-R8：触及路径冒烟（合成，不拉网）。"""
    r1 = wyckoff_analysis(_pad_min(_sc_only_bars()), use_persisted_phase=False)
    assert "phase_a_status" in r1
    assert "tr_maturity" in r1
    r2 = wyckoff_analysis(_pad_min(_sc_ar_st_bars()), use_persisted_phase=False)
    assert r2.get("secondary_test_sc_signal") is True
    assert isinstance(format_cause_effect_display(r2), str)
    assert isinstance(_phase_a_box_phrase(r2), str)


def _sc_breakdown_then_fake_st_bars() -> list[dict]:
    """南网日线类：SC 后有效跌破未收回，再反弹；禁止把后续缩量棒当 ST。

    序列：SC(low=82) → 破位(low=75, close=76<82) → AR → 假「回测」40 区上方缩量棒。
    """
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(82.0, 82.5, 75.0, 76.0, 1800))  # 有效跌破未收回
    bars.append(_bar(76.5, 87.0, 76.0, 86.0, 2000))  # AR
    bars.append(_bar(85.0, 86.5, 81.5, 86.0, 900))   # 若未整段失败会被误认 ST
    for _ in range(4):
        bars.append(_bar(84.0, 84.5, 83.5, 84.0, 110))
    return bars


def test_m_r9_breakdown_aborts_st_no_l2() -> None:
    """有效跌破未收回 → 禁止再认 ST；不得抬 L2/L3 / 成熟箱体 / 量度。"""
    from trader_shared.wyckoff_events import _detect_secondary_test_sc

    bars = _pad_min(_sc_breakdown_then_fake_st_bars())
    st = _detect_secondary_test_sc(bars)
    assert st.get("secondary_test_sc_signal") is not True
    assert "跌破" in (st.get("secondary_test_sc_reason") or "")

    result = wyckoff_analysis(bars, use_persisted_phase=False)
    assert result.get("sc_signal") is True
    assert result.get("secondary_test_sc_signal") is not True
    _require_gate_fields(result)
    assert result["tr_maturity"] in ("L0", "L1")
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] != "box"
    assert result.get("cause_effect_up_target") is None
    assert not _mature_box_phrase(_phase_a_box_phrase(result))
    assert not _mature_box_phrase(format_wyckoff_daily_phase_light(result))
    # sc_low SSOT：保持 SC 棒低点，不被后续棒覆盖
    assert result.get("sc_low") == result.get("sc_price")


def test_sc_low_not_overwritten_by_st_refine() -> None:
    """成功 ST 更低时写 sc_low_refined，顶栏 sc_low 仍为 SC 棒价。"""
    result = wyckoff_analysis(_pad_min(_sc_ar_st_bars()), use_persisted_phase=False)
    assert result["secondary_test_sc_signal"] is True
    assert result["sc_low"] == 82.0
    assert result["sc_price"] == 82.0
    assert result.get("sc_low_refined") == 81.8 or result.get("st_sc_low") == 81.8
    assert float(result["tr_lower"]) == 81.8
    assert "箱体 81.80-" in _phase_a_box_phrase(result)
