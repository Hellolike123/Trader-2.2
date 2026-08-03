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
    """SC+AR，无回测 ST：SC 后 lows 始终高于 sc_low×(1+prox≈0.045)。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC low=82；prox 上沿≈85.69
    for i in range(3):
        b = 86.2 + i * 0.2
        bars.append(_bar(b, b + 0.5, b - 0.3, b + 0.1, 150))  # low≥85.9，区外
    bars.append(_bar(86.5, 88.0, 86.0, 87.0, 200))  # AR
    return bars


def _sc_ar_st_bars() -> list[dict]:
    """SC + AR + 缩量回测 ST（窗宽通常 < MEASURE_MIN → L2）。ST 须在 AR+3 起。

    ST 用收复阳线，避免被 ``_find_sc_anchor`` 从近端误锚成新 SC。
    """
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC spread=3.0
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR（low 在 zone 上沿外）
    # AR+1 / AR+2：站在 zone 上，满足「AR 后至少 3 根才认 ST」
    bars.append(_bar(85.2, 85.6, 85.0, 85.3, 120))
    bars.append(_bar(85.1, 85.5, 84.9, 85.2, 120))
    # ST @ AR+3：low 回测 SC 区，收复阳线；波幅 1.4 ≤ 0.85×3
    bars.append(_bar(82.2, 83.2, 81.8, 82.9, 800))
    for i in range(2):
        bars.append(_bar(85.0 + i * 0.05, 85.4, 84.8, 85.2, 120))
    return bars


def _sc_ar_st_wide_bars() -> list[dict]:
    """M-R4：在 ST 箱上略加宽至 ≥ MEASURE_MIN_BARS，且 SC 仍在 climax 窗内。"""
    bars = _sc_ar_st_bars()
    for _ in range(2):
        bars.append(_bar(85.0, 85.4, 84.8, 85.1, 110))
    return bars


def _wide_spread_st_bars() -> list[dict]:
    """宽波幅+缩量回测：量弱但波幅不弱于 SC → 不得认 ST / L2。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC spread=3.0；cap≈2.55
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR
    bars.append(_bar(86.2, 86.6, 86.0, 86.3, 120))  # 区外（prox 上沿≈85.69）
    bars.append(_bar(86.1, 86.5, 85.9, 86.2, 120))
    # 收复阳线 + 宽波幅 4.0 > cap；后续棒不得进入 SC 区
    bars.append(_bar(82.0, 85.5, 81.5, 83.5, 800))
    for _ in range(2):
        bars.append(_bar(86.5, 87.0, 86.2, 86.7, 110))
    return bars


def _delayed_ar_bars() -> list[dict]:
    """SC 后第 10 根才 AR（>旧 anchor//2≈7，< WYCKOFF_AR_MAX_BARS=15）。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    for i in range(9):
        # 反弹不足 2%，不得提前亮 AR
        b = 83.0 + (i % 3) * 0.05
        bars.append(_bar(b, b + 0.3, b - 0.2, b + 0.05, 120))
    bars.append(_bar(83.5, 87.0, 83.2, 86.0, 150))  # AR @ SC+10
    return bars


def _st_before_ar_bars() -> list[dict]:
    """AR 前有缩量回测棒；有 AR 时不得把该棒当 ST。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(82.2, 83.2, 81.8, 82.9, 800))   # 缩量回测阳线（AR 前）
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR
    for _ in range(3):
        bars.append(_bar(86.5, 87.0, 86.2, 86.7, 110))  # 站在 zone 上，无合法 ST
    return bars


def _st_after_ar_bars() -> list[dict]:
    """AR 后合法缩量窄波幅 ST（AR+3 起算）。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(82.2, 83.2, 81.8, 82.9, 800))   # AR 前缩量棒（应忽略）
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR
    bars.append(_bar(85.2, 85.6, 85.0, 85.3, 120))   # AR+1
    bars.append(_bar(85.1, 85.5, 84.9, 85.2, 120))   # AR+2
    bars.append(_bar(82.3, 83.1, 81.9, 82.8, 700))   # 合法 ST @ AR+3
    for _ in range(2):
        bars.append(_bar(85.0, 85.4, 84.8, 85.1, 110))
    return bars


def _soft_confirm_bars() -> list[dict]:
    """M-R6：AR 后价格一直高于 sc_low×(1+prox≈0.045)，无回测。"""
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC；zone 上沿≈85.69
    bars.append(_bar(86.5, 88.0, 86.0, 87.0, 400))   # AR，low 高于 prox
    for i in range(8):
        b = 86.5 + (i % 3) * 0.2
        bars.append(_bar(b, b + 0.4, b - 0.2, b + 0.1, 120))
    return bars


def _percentile_tr_no_sc_bars() -> list[dict]:
    """M-R5：窄幅横盘，无 SC/ST 瀑布。"""
    return [_bar(10.0, 10.01, 9.99, 10.0, 30000) for _ in range(60)]


def _require_gate_fields(result: dict) -> None:
    assert "tr_maturity" in result
    assert "measure_allowed" in result
    assert "box_display_mode" in result


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
    daily_line = format_wyckoff_daily_phase_light(result)
    mid_line = format_wyckoff_midline_light(result)
    assert not _mature_box_phrase(daily_line)
    assert not _mature_box_phrase(mid_line)
    # L1 面板禁成熟「箱体」叙事（可写雏形）；禁量度数字
    assert "箱体" not in daily_line
    assert "箱体" not in mid_line
    assert "雏形" in box or "雏形" in daily_line or "雏形" in mid_line
    assert "量度目标" not in daily_line
    assert "量度目标" not in mid_line


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


def _sc_st_no_ar_bars() -> list[dict]:
    """§1.2：成功广义 ST，但全程无有效 AR（close 从未 > sc_close×1.02）。

    无 AR 时 ST 窗从 SC+3 起扫；缩量窄波幅回测阳线认 ST。
    """
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC close=83 → AR 阈≈84.66
    bars.append(_bar(83.2, 83.6, 83.0, 83.4, 120))   # SC+1：弱反弹，不开 AR
    bars.append(_bar(83.1, 83.5, 82.9, 83.2, 120))   # SC+2
    # ST @ SC+3：回测 SC 区 + 缩量 + 波幅≤0.85×3；close 仍 < AR 阈
    bars.append(_bar(82.2, 83.2, 81.8, 82.9, 800))
    for _ in range(2):
        bars.append(_bar(83.0, 83.4, 82.8, 83.1, 110))
    return bars


def test_m_r_st_without_ar_stays_l1() -> None:
    """§1.2：仅有成功 ST、无有效 ar_high → 停 L1；禁成熟箱体 / 量度。"""
    result = wyckoff_analysis(_pad_min(_sc_st_no_ar_bars()), use_persisted_phase=False)
    assert result.get("sc_signal") is True
    assert result.get("ar_signal") is not True
    assert result.get("ar_high") in (None, 0, 0.0)
    assert result.get("secondary_test_sc_signal") is True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L1"
    assert result["tr_maturity"] not in ("L2", "L3")
    assert result["box_display_mode"] != "box"
    assert result["box_display_mode"] == "proto"
    assert result["measure_allowed"] is False
    assert result.get("cause_effect_up_target") is None
    assert result.get("cause_effect_down_target") is None
    assert format_cause_effect_display(result) == ""
    box = _phase_a_box_phrase(result)
    assert not _mature_box_phrase(box)
    assert "箱体" not in box
    daily_line = format_wyckoff_daily_phase_light(result)
    mid_line = format_wyckoff_midline_light(result)
    assert not _mature_box_phrase(daily_line)
    assert not _mature_box_phrase(mid_line)
    assert "箱体" not in daily_line
    assert "箱体" not in mid_line


def test_m_r4_wide_enough_l3_measure() -> None:
    """M-R4：宽度足够 → L3 + 量度数字（上下目标均须有）。"""
    # 勿过度前插 pad：SC 须留在 climax 检测窗内
    result = wyckoff_analysis(_sc_ar_st_wide_bars(), use_persisted_phase=False)
    assert result["secondary_test_sc_signal"] is True
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L3"
    assert result["measure_allowed"] is True
    assert result["box_display_mode"] == "box"
    assert result.get("cause_effect_up_target") is not None
    assert result.get("cause_effect_down_target") is not None
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

    序列：SC(low=82) → 破位(low=75, close=76<82) → AR → 假「回测」区上方缩量棒。
    破位棒量比须 < SC 量阈（1.5），避免被松参后误锚成新 SC。
    """
    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(82.0, 82.5, 75.0, 76.0, 140))   # 有效跌破未收回（量比 1.4，非新 SC）
    bars.append(_bar(76.5, 87.0, 76.0, 86.0, 2000))  # AR
    bars.append(_bar(85.0, 86.5, 81.5, 86.0, 900))   # 若未整段失败会被误认 ST
    for _ in range(4):
        bars.append(_bar(86.5, 87.0, 86.2, 86.6, 110))  # 站区外，不得另找假 ST
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
    assert result["phase_a_status"] == "failed"
    assert result["phase_a_range"]["status"] == "failed"
    assert result["tr_maturity"] == "L0"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "none"
    assert result.get("cause_effect_up_target") is None
    assert not _mature_box_phrase(_phase_a_box_phrase(result))
    daily_line = format_wyckoff_daily_phase_light(result)
    assert not _mature_box_phrase(daily_line)
    # R-F2/R-F5：光杆日线 failed → Phase A 失效；禁「失败」
    assert daily_line == "Phase A 失效｜须重新寻底｜仅对照"
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in daily_line
    # sc_low SSOT：保持 SC 棒低点，不被后续棒覆盖
    assert result.get("sc_low") == result.get("sc_price")


def _sc_ar_deep_pierce_recover_st_bars() -> list[dict]:
    """W-DIFF-7：SC+AR 后深刺穿 floor 但 close≥sc_low 收回，且满足缩量窄波幅 ST。

    不改 MAX_PIERCE / VOL / SPREAD 阈值；只构造满足现合同的棒。
    SC low=82、spread=3 → floor≈81.016；ST low 低于 floor、close≥82、波幅≤2.55。
    """
    from trader_shared.config import WYCKOFF_ST_SC_MAX_PIERCE

    sc_low = 82.0
    floor = sc_low * (1.0 - WYCKOFF_ST_SC_MAX_PIERCE)
    deep_low = round(floor - 0.4, 2)  # e.g. ~80.62
    assert deep_low < floor

    bars = _decline_base(14, vol=100)
    bars.append(_bar(84.0, 85.0, sc_low, 83.0, 2500))  # SC spread=3.0
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR
    bars.append(_bar(85.2, 85.6, 85.0, 85.3, 120))   # AR+1
    bars.append(_bar(85.1, 85.5, 84.9, 85.2, 120))   # AR+2
    # ST @ AR+3：深刺穿 + 收盘收回 + 缩量 + 窄波幅（high-low=2.4 ≤ 0.85×3）
    bars.append(_bar(81.2, 83.0, deep_low, 82.4, 800))
    for i in range(2):
        bars.append(_bar(85.0 + i * 0.05, 85.4, 84.8, 85.2, 120))
    return bars


def test_w_diff7_deep_pierce_recover_allows_st() -> None:
    """W-DIFF-7：深刺穿但 close≥sc_low → 不算破位；满足既有 ST 条件时可认 ST。

    禁止写成「超刺穿一律否 ST」；本测不改阈值公式。
    """
    from trader_shared.config import WYCKOFF_ST_SC_MAX_PIERCE
    from trader_shared.wyckoff_events import _detect_secondary_test_sc, _phase_a_breakdown

    bars = _pad_min(_sc_ar_deep_pierce_recover_st_bars())
    result = wyckoff_analysis(bars, use_persisted_phase=False)
    sc_low = float(result.get("sc_low") or 82.0)
    floor = sc_low * (1.0 - WYCKOFF_ST_SC_MAX_PIERCE)
    st_idx = result.get("secondary_test_sc_bar_idx")
    assert st_idx is not None
    st_low = float(bars[int(st_idx)]["low"])
    st_close = float(bars[int(st_idx)]["close"])
    assert st_low < floor
    assert st_close >= sc_low

    assert _phase_a_breakdown(bars, int(result["phase_a_range"]["sc_bar_idx"]), sc_low) is None
    assert result["phase_a_status"] != "failed"
    assert result.get("secondary_test_sc_signal") is True
    _require_gate_fields(result)
    assert result["tr_maturity"] in ("L2", "L3")
    assert result["box_display_mode"] == "box"
    assert result["measure_allowed"] is (result["tr_maturity"] == "L3")

    st = _detect_secondary_test_sc(bars, phase_a_range=result.get("phase_a_range"))
    assert st.get("secondary_test_sc_signal") is True
    assert st.get("phase_a_failed") is not True


def test_sc_low_not_overwritten_by_st_refine() -> None:
    """成功 ST 更低时写 sc_low_refined，顶栏 sc_low 仍为 SC 棒价。"""
    result = wyckoff_analysis(_pad_min(_sc_ar_st_bars()), use_persisted_phase=False)
    assert result["secondary_test_sc_signal"] is True
    assert result["sc_low"] == 82.0
    assert result["sc_price"] == 82.0
    assert result.get("sc_low_refined") == 81.8 or result.get("st_sc_low") == 81.8
    assert float(result["tr_lower"]) == 81.8
    assert "箱体 81.80-" in _phase_a_box_phrase(result)


def test_st_wide_spread_no_st_no_l2() -> None:
    """宽波幅+缩量 → 无 ST / 不得 L2。"""
    from trader_shared.wyckoff_events import _detect_secondary_test_sc

    bars = _pad_min(_wide_spread_st_bars())
    # 先建 phase_a 以带 ar_bar_idx
    result = wyckoff_analysis(bars, use_persisted_phase=False)
    assert result.get("sc_signal") is True
    assert result.get("ar_signal") is True
    assert result.get("secondary_test_sc_signal") is not True
    reason = result.get("secondary_test_sc_reason") or ""
    assert "波幅" in reason
    _require_gate_fields(result)
    assert result["tr_maturity"] == "L1"
    assert result["measure_allowed"] is False
    assert result["box_display_mode"] == "proto"
    assert not _mature_box_phrase(_phase_a_box_phrase(result))

    st = _detect_secondary_test_sc(bars, phase_a_range=result.get("phase_a_range"))
    assert st.get("secondary_test_sc_signal") is not True
    assert "波幅" in (st.get("secondary_test_sc_reason") or "")


def test_st_scan_starts_after_ar_ignores_pre_ar() -> None:
    """有 AR 时：AR 前缩量棒不得当 ST；AR 后合法 ST 仍可。"""
    from trader_shared.wyckoff_events import _detect_secondary_test_sc

    pre = _pad_min(_st_before_ar_bars())
    r_pre = wyckoff_analysis(pre, use_persisted_phase=False)
    assert r_pre.get("ar_signal") is True
    assert r_pre.get("secondary_test_sc_signal") is not True
    assert r_pre["tr_maturity"] == "L1"

    post = _pad_min(_st_after_ar_bars())
    r_post = wyckoff_analysis(post, use_persisted_phase=False)
    assert r_post.get("ar_signal") is True
    assert r_post.get("secondary_test_sc_signal") is True
    assert r_post["tr_maturity"] in ("L2", "L3")
    # 合法 ST 须在 AR+3 起（phase-a §4.4.1）
    ar_i = r_post["phase_a_range"]["ar_bar_idx"]
    st_i = r_post.get("secondary_test_sc_bar_idx")
    assert st_i is not None and ar_i is not None and st_i >= ar_i + 3

    # 无 phase_a_range 时从 SC+3 扫（兼容单测直调）
    st_direct = _detect_secondary_test_sc(post)
    assert st_direct.get("secondary_test_sc_signal") is True


def test_delayed_ar_within_ar_max_bars() -> None:
    """延迟 AR（>7 根、< AR_MAX）仍亮 ar_signal + established。"""
    from trader_shared.wyckoff_events import _detect_ar

    bars = _pad_min(_delayed_ar_bars())
    ar = _detect_ar(bars)
    assert ar.get("ar_signal") is True
    assert ar.get("ar_bar_idx") is not None
    sc_i = ar.get("sc_bar_idx")
    assert sc_i is not None
    assert int(ar["ar_bar_idx"]) - int(sc_i) > 7

    result = wyckoff_analysis(bars, use_persisted_phase=False)
    assert result.get("sc_signal") is True
    assert result.get("ar_signal") is True
    assert result["phase_a_status"] == "established"
    assert result.get("ar_high") is not None


def test_is_index_relaxes_sc_vol_threshold() -> None:
    """同 bars：is_index=True 放宽 SC 量阈，与 False 行为可区分。"""
    from trader_shared.wyckoff_events import (
        _detect_selling_climax,
        _sc_detector_params,
        resolve_wyckoff_is_index,
    )

    assert resolve_wyckoff_is_index("000001.SH") is True
    assert resolve_wyckoff_is_index("000001.SZ") is False  # 平安银行
    assert resolve_wyckoff_is_index("000852.SH") is True
    assert resolve_wyckoff_is_index("399006.SZ") is True
    # 同裸码不同市场：指数在 .SH，个股在 .SZ 不得误判
    assert resolve_wyckoff_is_index("000300.SH") is True   # 沪深300
    assert resolve_wyckoff_is_index("000300.SZ") is False  # 维维股份
    assert resolve_wyckoff_is_index("000016.SH") is True   # 上证50
    assert resolve_wyckoff_is_index("000016.SZ") is False  # 深康佳A

    stock_th = float(_sc_detector_params("daily", is_index=False)["vol_ratio_threshold"])
    idx_th = float(_sc_detector_params("daily", is_index=True)["vol_ratio_threshold"])
    assert idx_th < stock_th
    assert idx_th <= 1.35

    # 量比落在 (idx_th, stock_th) 之间：仅指数路径亮 SC
    avg = 100.0
    mid_vol = int((idx_th + stock_th) / 2 * avg)  # e.g. ~157
    bars = _decline_base(14, vol=int(avg))
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, mid_vol))
    bars.append(_bar(83.2, 83.6, 83.0, 83.5, 120))

    sc_stock = _detect_selling_climax(bars, is_index=False)
    sc_idx = _detect_selling_climax(bars, is_index=True)
    assert sc_stock.get("sc_signal") is not True
    assert sc_idx.get("sc_signal") is True

    # 生产路径：指数码传入 is_index
    r_idx = wyckoff_analysis(bars, symbol="000001.SH", use_persisted_phase=False)
    r_stock = wyckoff_analysis(bars, symbol="600519.SH", use_persisted_phase=False)
    assert r_idx.get("sc_signal") is True
    assert r_stock.get("sc_signal") is not True


def test_view_exposes_tr_maturity_measure_fields() -> None:
    """View / cause_effect 透出 tr_maturity、measure_allowed、box_display_mode。"""
    from trader_shared.wyckoff_view import to_wyckoff_state_view

    result = wyckoff_analysis(_pad_min(_sc_ar_no_st_bars()), use_persisted_phase=False)
    view = to_wyckoff_state_view(result, symbol="TEST")
    assert view.get("tr_maturity") == "L1"
    assert view.get("measure_allowed") is False
    assert view.get("box_display_mode") == "proto"
    ce = view.get("cause_effect") or {}
    assert ce.get("tr_maturity") == "L1"
    assert ce.get("measure_allowed") is False
    assert ce.get("box_display_mode") == "proto"
    assert format_cause_effect_display(view) == ""

    # 缺省 measure_allowed 的裸目标 → 空
    assert format_cause_effect_display({
        "cause_effect_up_target": 10.0,
        "cause_effect_down_target": 8.0,
    }) == ""
