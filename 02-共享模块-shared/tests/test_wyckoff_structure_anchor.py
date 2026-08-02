"""威科夫结构锚点搜索验收（S-A1…S-A7）。

法源：docs/plans/wyckoff-structure-anchor-handoff.md。
合成 bars，禁全网抓数。
"""
from __future__ import annotations

from trader_shared.config import (
    WYCKOFF_SC_COLD_START_BARS_DAILY,
    WYCKOFF_SC_COLD_START_BARS_WEEKLY,
)
from trader_shared.wyckoff_core import (
    format_wyckoff_daily_phase_light,
    format_wyckoff_midline_light,
    wyckoff_analysis,
)
from trader_shared.wyckoff_events import _find_sc_anchor, _sc_detector_params
from trader_shared.wyckoff_chain import format_wyckoff_chain_plain


def _bar(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _neutral(price: float = 90.0, vol: int = 100) -> dict:
    return _bar(price, price + 1.0, price - 1.0, price, vol)


def _with_sc_at(total: int, sc_idx: int, *, ar: bool = True) -> list[dict]:
    bars = [_neutral() for _ in range(total)]
    bars[sc_idx] = _bar(84.0, 85.0, 82.0, 83.0, 2500)
    if ar and sc_idx + 1 < total:
        bars[sc_idx + 1] = _bar(83.5, 87.0, 85.0, 86.0, 160)
    for i in range(sc_idx + 2, total):
        bars[i] = _bar(85.0, 86.0, 84.8, 85.2, 120)
    return bars


def _weekly_with_sc_at(total: int, sc_idx: int) -> list[dict]:
    bars = [_neutral(100.0, 100) for _ in range(total)]
    bars[sc_idx] = _bar(93.0, 94.0, 90.0, 91.0, 180)
    if sc_idx + 1 < total:
        bars[sc_idx + 1] = _bar(91.5, 96.0, 93.0, 95.0, 120)
    for i in range(sc_idx + 2, total):
        bars[i] = _bar(95.0, 96.0, 94.0, 95.2, 100)
    return bars


def _breakdown_then_fake_st_bars() -> list[dict]:
    bars = [_neutral(90.0, 100) for _ in range(14)]
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(82.0, 82.5, 75.0, 76.0, 1800))  # 有效破位未收回
    bars.append(_bar(76.5, 87.0, 76.0, 86.0, 2000))
    bars.append(_bar(85.0, 86.5, 81.5, 86.0, 900))   # 未收口时容易误认 ST
    for _ in range(4):
        bars.append(_bar(84.0, 84.5, 83.5, 84.0, 110))
    while len(bars) < 30:
        bars.insert(0, _neutral(90.0, 100))
    return bars


def test_s_a1_alive_anchor_pins_search_beyond_daily_cap() -> None:
    total = 130
    sc_idx = total - WYCKOFF_SC_COLD_START_BARS_DAILY - 10
    bars = _with_sc_at(total, sc_idx)

    result = wyckoff_analysis(
        bars,
        use_persisted_phase=False,
        phase_a_range={"status": "established", "sc_bar_idx": sc_idx, "sc_low": 82.0},
    )

    assert sc_idx < len(bars) - WYCKOFF_SC_COLD_START_BARS_DAILY
    assert result["sc_signal"] is True
    assert result["phase_a_range"]["sc_bar_idx"] == sc_idx
    assert result["phase_a_range"]["status"] in {"forming", "established"}
    assert result["phase_a_range"]["search_mode"] == "pinned"


def test_s_a2_daily_cold_start_caps_at_90_without_anchor() -> None:
    total = 130
    old_sc_idx = total - WYCKOFF_SC_COLD_START_BARS_DAILY - 10
    old_only = _with_sc_at(total, old_sc_idx)

    cold = wyckoff_analysis(old_only, use_persisted_phase=False)
    assert cold.get("sc_signal") is not True
    assert cold["phase_a_status"] == "none"

    cap_sc_idx = total - 20
    in_cap = _with_sc_at(total, cap_sc_idx)
    found = wyckoff_analysis(in_cap, use_persisted_phase=False)
    assert found["sc_signal"] is True
    assert found["phase_a_range"]["sc_bar_idx"] >= len(in_cap) - WYCKOFF_SC_COLD_START_BARS_DAILY
    assert found["phase_a_range"]["search_mode"] == "cold_start"


def test_s_a3_weekly_cold_start_caps_at_39_without_anchor() -> None:
    total = 70
    old_sc_idx = total - WYCKOFF_SC_COLD_START_BARS_WEEKLY - 5
    old_only = _weekly_with_sc_at(total, old_sc_idx)

    cold = wyckoff_analysis(old_only, timeframe="weekly", use_persisted_phase=False)
    assert cold.get("sc_signal") is not True
    assert cold["phase_a_status"] == "none"

    cap_sc_idx = total - 10
    in_cap = _weekly_with_sc_at(total, cap_sc_idx)
    found = wyckoff_analysis(in_cap, timeframe="weekly", use_persisted_phase=False)
    assert found["sc_signal"] is True
    assert found["phase_a_range"]["sc_bar_idx"] >= len(in_cap) - WYCKOFF_SC_COLD_START_BARS_WEEKLY
    assert found["phase_a_range"]["anchor_bars"] == WYCKOFF_SC_COLD_START_BARS_WEEKLY


def test_s_a4_s_a5_breakdown_fails_phase_a_and_forbids_st() -> None:
    bars = _breakdown_then_fake_st_bars()
    result = wyckoff_analysis(bars, use_persisted_phase=False)

    assert result.get("sc_signal") is True
    assert result.get("secondary_test_sc_signal") is not True
    assert "跌破" in (result.get("secondary_test_sc_reason") or "")
    assert result["phase_a_status"] == "failed"
    assert result["phase_a_range"]["status"] == "failed"
    assert result["tr_maturity"] == "L0"
    assert result["box_display_mode"] == "none"
    assert result["measure_allowed"] is False
    assert result.get("cause_effect_up_target") is None
    assert result.get("cause_effect_down_target") is None

    daily_line = format_wyckoff_daily_phase_light(result)
    midline = format_wyckoff_midline_light(result)
    # R-F1/R-F2/R-F3/R-F5：报告光杆 failed → 失效｜须重新寻底；禁「失败」
    assert daily_line == "Phase A 失效｜须重新寻底｜仅对照"
    assert midline == "威科夫：Phase A 失效｜须重新寻底｜不据此开仓"
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in daily_line
        assert bad not in midline
    assert "停止：SC+AR" not in result.get("phase_label", "")
    assert "雏形" not in daily_line
    assert "雏形" not in midline
    chain = format_wyckoff_chain_plain(result)
    assert chain.startswith("威：SC")
    assert chain.endswith("（Phase A 失效）")
    assert "还差" not in chain


def test_r_f_light_format_failed_ban_words() -> None:
    """R-F1…R-F5 / M-R1：光杆 format failed fixture 禁「失败」，含失效｜须重新寻底。"""
    failed = {
        "phase_a_status": "failed",
        "phase": "none",
        "phase_label": "无明确阶段（Phase A 失败，破位未收回）",
        "phase_tr_gated": True,
        "phase_tr_gate_reason": "phase_a_failed",
        "tr_maturity": "L0",
        "box_display_mode": "none",
        "measure_allowed": False,
        "sc_signal": True,
        "sc_price": 10.0,
        "sc_low": 10.0,
        "timeframe": "daily",
    }
    daily = format_wyckoff_daily_phase_light(failed)
    mid = format_wyckoff_midline_light(failed)
    assert daily == "Phase A 失效｜须重新寻底｜仅对照"
    assert mid == "威科夫：Phase A 失效｜须重新寻底｜不据此开仓"
    for text in (daily, mid):
        assert "Phase A 失效" in text
        assert "须重新寻底" in text
        for bad in ("Phase A失败", "Phase A 失败"):
            assert bad not in text


def test_s_a6_daily_weekly_caps_are_separate() -> None:
    daily = _sc_detector_params("daily")["anchor_bars"]
    weekly = _sc_detector_params("weekly")["anchor_bars"]
    assert daily == WYCKOFF_SC_COLD_START_BARS_DAILY
    assert weekly == WYCKOFF_SC_COLD_START_BARS_WEEKLY
    assert daily != weekly


def test_find_sc_anchor_direct_path_a_path_b_modes() -> None:
    total = 130
    sc_idx = total - WYCKOFF_SC_COLD_START_BARS_DAILY - 10
    bars = _with_sc_at(total, sc_idx)

    assert _find_sc_anchor(bars) is None
    pinned = _find_sc_anchor(
        bars,
        tr_ctx={"phase_a_range": {"status": "forming", "sc_bar_idx": sc_idx, "sc_low": 82.0}},
    )
    assert pinned is not None
    assert pinned["sc_bar_idx"] == sc_idx
    assert pinned["search_mode"] == "pinned"


def test_w_diff2_cold_start_excludes_fail_bar_and_earlier_sc() -> None:
    """W-DIFF-2 / M-R3 / S-A5：fail_bar 后冷启动不得钉 fail 棒或更早 SC 为健康锚。"""
    total = 60
    old_sc = 25
    bars = _with_sc_at(total, old_sc, ar=True)
    # 无破位时冷启动本可认该 SC；ctx 带 fail_bar 后必须排除
    bare = _find_sc_anchor(bars, include_failed=False)
    assert bare is not None
    assert bare["sc_bar_idx"] == old_sc

    fail_bar = old_sc + 2
    cold = _find_sc_anchor(
        bars,
        tr_ctx={
            "phase_a_range": {
                "status": "failed",
                "fail_bar_idx": fail_bar,
                "sc_bar_idx": old_sc,
                "sc_low": 82.0,
            }
        },
        include_failed=False,
    )
    assert cold is None or cold["sc_bar_idx"] > fail_bar

    # include_failed=True 不套排除，仍可找到旧 SC（汇报失败锚）
    kept = _find_sc_anchor(
        bars,
        tr_ctx={"phase_a_range": {"status": "failed", "fail_bar_idx": fail_bar}},
        include_failed=True,
    )
    assert kept is not None
    assert kept["sc_bar_idx"] == old_sc

    # 破位序列经 wyckoff_analysis：不得健康 forming/established
    broken = _breakdown_then_fake_st_bars()
    result = wyckoff_analysis(broken, use_persisted_phase=False)
    assert result["phase_a_status"] == "failed"
    assert result["tr_maturity"] == "L0"
    assert result["box_display_mode"] == "none"
    fbi = result["phase_a_range"].get("fail_bar_idx")
    assert fbi is not None
    # 再冷启动：ctx 带 fail_bar → 不得把 fail 及更早钉成健康锚
    replay = _find_sc_anchor(
        broken,
        tr_ctx={"phase_a_range": dict(result["phase_a_range"])},
        include_failed=False,
    )
    if replay is not None:
        assert replay["sc_bar_idx"] > int(fbi)
        assert not replay.get("phase_a_failed")
    full = wyckoff_analysis(
        broken,
        use_persisted_phase=False,
        phase_a_range={
            "status": "failed",
            "fail_bar_idx": fbi,
            "sc_bar_idx": result["phase_a_range"]["sc_bar_idx"],
            "sc_low": result["phase_a_range"]["sc_low"],
        },
    )
    assert full["phase_a_status"] in {"failed", "none"} or (
        full["phase_a_range"].get("sc_bar_idx") is not None
        and int(full["phase_a_range"]["sc_bar_idx"]) > int(fbi)
    )
    if full["phase_a_status"] in {"forming", "established"}:
        assert int(full["phase_a_range"]["sc_bar_idx"]) > int(fbi)
