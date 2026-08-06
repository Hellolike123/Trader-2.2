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


def test_bias_are_and_trend_rally_bear():
    assert to_wyckoff_state_view({"are_signal": True, "phase": "none"})["bias"] == "bear"
    assert to_wyckoff_state_view({"trend_rally_signal": True, "phase": "none"})["bias"] == "bear"


def test_bias_ar_and_trend_pullback_bull():
    assert to_wyckoff_state_view({"ar_signal": True, "phase": "none"})["bias"] == "bull"
    assert to_wyckoff_state_view({"trend_pullback_signal": True, "phase": "none"})["bias"] == "bull"


def test_phase_prefix_bias_accumulation_b():
    """生产 phase 为 accumulation_a/b/...，阶段兜底 bias 须命中。"""
    v = to_wyckoff_state_view(
        {
            "phase": "accumulation_b",
            "phase_label": "积累B",
            "spring_signal": False,
            "sos_signal": False,
        }
    )
    assert v["bias"] == "bull"


def test_phase_prefix_bias_distribution_c():
    v = to_wyckoff_state_view(
        {
            "phase": "distribution_c",
            "phase_label": "派发C",
            "utad_signal": False,
            "sow_signal": False,
            "lpsy_signal": False,
            "bc_signal": False,
            "upthrust_signal": False,
        }
    )
    assert v["bias"] == "bear"


def test_weak_spring_neutral_bias():
    v = to_wyckoff_state_view(
        {
            "spring_signal": True,
            "spring_strength": "weak",
            "spring_vol_class": "low_vol_confirm",
            "spring_premature": False,
            "phase": "none",
        }
    )
    assert v["bias"] == "neutral"


def test_forming_summary_mentions_unpinned_range():
    v = to_wyckoff_state_view(
        {
            "sc_signal": True,
            "sc_reason": "卖力高潮",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_a_status": "forming",
            "timeframe": "weekly",
        }
    )
    assert v["phase_a_status"] == "forming"
    assert "箱体未成形" in v["summary_oneline"]


def test_gate_reason_forming_phase_a_in_summary():
    v = to_wyckoff_state_view(
        {
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_a_status": "forming",
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "forming_phase_a",
            "sc_signal": True,
        }
    )
    assert "箱体未成形" in v["summary_oneline"]
    assert "不抬升" in v["summary_oneline"] or "箱体未成形" in v["summary_oneline"]


def test_secondary_test_sc_in_active_events():
    v = to_wyckoff_state_view(
        {
            "secondary_test_sc_signal": True,
            "secondary_test_sc_reason": "SC 区二次测试",
            "st_sc_low": 81.8,
            "phase": "accumulation_a",
            "phase_a_status": "established",
        }
    )
    assert "secondary_test_sc" in v["active_events"]
    assert v["event_detail"]["secondary_test_sc"]["price"] == 81.8


def test_format_daily_phase_no_tr_isomorphic():
    from trader_shared.wyckoff_view import format_daily_phase_display

    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "none",
            "phase_a_status": "none",
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "no_tr",
        }
    )
    assert line.startswith("威科夫：")
    assert "日线阶段：" not in line
    assert "无清晰区间" in line
    assert "暂定不出" in line
    assert "对照" in line


def test_format_daily_phase_forming():
    from trader_shared.wyckoff_view import format_daily_phase_display

    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_a_status": "forming",
            "phase_tr_gated": False,
        }
    )
    assert line.startswith("威科夫：")
    assert "箱体未成形" in line
    assert "上沿未出" in line
    assert "对照" in line


def test_format_daily_phase_established():
    from trader_shared.wyckoff_view import format_daily_phase_display

    # SC+AR 无 ST → 雏形（禁止成熟「箱体 lo-hi」）
    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（停止：SC+AR）",
            "phase_a_status": "established",
            "sc_low": 10.0,
            "ar_high": 12.0,
            "tr_lower": 10.0,
            "tr_upper": 12.0,
            "secondary_test_sc_signal": False,
            "tr_maturity": "L1",
            "box_display_mode": "proto",
        }
    )
    assert line.startswith("威科夫：")
    assert "雏形 10.00-12.00（待 ST）" in line
    assert "箱体 10.00-12.00" not in line
    assert "对照" in line

    # 真 ST → 可写箱体
    line_box = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_b",
            "phase_label": "积累期 B",
            "phase_a_status": "established",
            "sc_low": 10.0,
            "ar_high": 12.0,
            "secondary_test_sc_signal": True,
            "tr_maturity": "L2",
            "box_display_mode": "box",
        }
    )
    assert "箱体 10.00-12.00" in line_box


def test_format_daily_phase_forming_shows_lower():
    from trader_shared.wyckoff_view import format_daily_phase_display

    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_a_status": "forming",
            "sc_low": 38.14,
            "tr_maturity": "L1",
            "box_display_mode": "proto",
        }
    )
    assert "雏形" in line
    assert "下沿 38.14（上沿未出）" in line
    assert "箱体 38" not in line


def test_format_daily_phase_established_invalid_bounds_no_pinned_fallback():
    """lo>=hi 时不写「箱体已钉」假已钉。"""
    from trader_shared.wyckoff_view import format_daily_phase_display

    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（停止：SC+AR）",
            "phase_a_status": "established",
            "sc_low": 12.0,
            "ar_high": 10.0,
        }
    )
    assert "箱体已钉" not in line
    assert "箱体 12" not in line
    assert "对照" in line


def test_format_daily_phase_legacy_unpinned_label():
    """旧 phase_label「区间未钉」映射为雏形人话（禁用成熟箱体词）。"""
    from trader_shared.wyckoff_view import format_daily_phase_display

    line = format_daily_phase_display(
        {
            "timeframe": "daily",
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，区间未钉）",
            "phase_a_status": "forming",
            "sc_low": 21.5,
            "tr_maturity": "L1",
            "box_display_mode": "proto",
        }
    )
    assert "雏形" in line
    assert "下沿 21.50（上沿未出）" in line
    assert "区间未钉" not in line
    assert "箱体 21" not in line


def test_confidence_rs_merged_delta_strong_gt_neutral_gt_weak():
    """R11：合并 RS 后的 phase_confidence_delta → View confidence 排序 strong>neutral>weak。"""
    base = {
        "timeframe": "weekly",
        "phase": "accumulation_b",
        "phase_label": "积累B",
        "spring_premature": False,
        "upthrust_premature": False,
        "phase_tr_gated": False,
        "tr_quality": 0.5,
    }
    strong = to_wyckoff_state_view({**base, "phase_confidence_delta": 0.08})
    neutral = to_wyckoff_state_view({**base, "phase_confidence_delta": 0.0})
    weak = to_wyckoff_state_view({**base, "phase_confidence_delta": -0.08})
    assert strong["confidence"] > neutral["confidence"] > weak["confidence"]


def test_r_f4_phase_a_failed_gate_note_uses_shixiao():
    """R-F4：view 直接进面板的 phase_a_failed 映射写「失效」不写「失败」。"""
    v = to_wyckoff_state_view(
        {
            "phase": "none",
            "phase_label": "无明确阶段",
            "phase_a_status": "failed",
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "phase_a_failed",
            "sc_signal": True,
            "timeframe": "daily",
        }
    )
    line = v["summary_oneline"]
    assert "Phase A 失效" in line
    assert "阶段不参与定论" in line
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in line


def test_p_l1_failed_phase_label_sanitized_on_view():
    """P-L1/P-L4/M-L1：failed fixture 的 view.phase_label 无「Phase A 失败」禁词。"""
    v = to_wyckoff_state_view(
        {
            "phase": "none",
            "phase_label": "无明确阶段（Phase A 失败，破位未收回）",
            "phase_a_status": "failed",
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "phase_a_failed",
            "sc_signal": True,
            "timeframe": "daily",
        }
    )
    label = v["phase_label"]
    assert label == "无明确阶段（Phase A 失效，破位未收回）"
    assert "Phase A 失效" in label
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in label
    # 引擎若给无空格「Phase A失败」亦须收口
    v2 = to_wyckoff_state_view(
        {
            "phase_label": "Phase A失败",
            "phase_a_status": "failed",
            "timeframe": "daily",
        }
    )
    assert "Phase A失败" not in v2["phase_label"]
    assert "Phase A 失败" not in v2["phase_label"]
    assert "Phase A失效" in v2["phase_label"] or "Phase A 失效" in v2["phase_label"]
