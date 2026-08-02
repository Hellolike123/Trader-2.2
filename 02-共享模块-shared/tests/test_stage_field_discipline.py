# -*- coding: utf-8 -*-
"""阶段字段纪律（architecture #2）：三套真相不混用。"""
from __future__ import annotations

from trader_shared.stage_fields import (
    MAJOR_STAGE_VOCAB,
    SHORT_MOMENTUM_VOCAB,
    alias_report_stage,
    major_stage_from_report,
)
from trader_shared.signal_core import _get_major_stage as signal_get_major
from trader_shared.report_presentation import _get_major_stage as present_get_major
from trader_shared.report_pipeline.assemble_stage import assemble_base_report
from trader_shared.report_pipeline.attach_stage_pack import attach_stage_position_pack
from trader_shared.report_pipeline.stage_context import StageContext
from trader_shared.resonance import build_resonance, _eval_background


def _minimal_assemble_ctx(**over) -> StageContext:
    """assemble StageContext 最小桩（只测 stage 字段写入）。"""
    class _Sec:
        name = "测"
        ts_code = "000001.SZ"

    class _Snap:
        data_status = "full"
        data_freshness = "live"
        missing_sources = []
        source_errors = {}
        fetched_at = ""
        extend_fundamental = None
        extend_sentiment = None
        extend_margin = None
        extend_northbound = None
        extend_concept = None

    stage_result = {
        "major_stage": "蓄势",
        "major_reason": "测",
        "momentum": "走强",
        "momentum_reason": "测",
        "action": "观望",
        "max_position_pct": 10,
        "stage_label": "蓄势期 + 走强",
        "confidence": 50,
        "protection_notes": [],
        "stop_losses": {},
    }
    levels = {
        "low_zone": "1-2",
        "low_zone_lower": 1.0,
        "low_zone_upper": 2.0,
        "ma_values": {},
        "trailing_stop": None,
        "effective_stop": 1.0,
        "fusion_override_used": False,
        "theory_fusion_conflict": False,
    }
    base = dict(
        intraday_as_of=None,
        quote={"name": "测", "symbol": "000001.SZ", "current_change_pct": 0},
        sec=_Sec(),
        analysis_time="",
        current=10.0,
        weekly_proxy_close=9.5,
        monthly_proxy_close=9.0,
        support=9.0,
        resistance=11.0,
        confirm=10.5,
        stop=8.5,
        take=11.0,
        stage="修复",  # determine_stage 词：assemble 必须忽略
        scene="等转强",
        levels=levels,
        replay="",
        volume_text="",
        upward_momentum="",
        low=9.0,
        high=11.0,
        snapshot=_Snap(),
        bars=[],
        risk_flags=[],
        atr14_val=0.5,
        atr_ratio_val=1.0,
        atr_level="中",
        atr_cap=10,
        st={},
        st_dir=None,
        vwap_res={},
        base_status="中性整理",
        theory_status="等转强",
        state_label="等转强",
        volume_note="",
        market_env_data={},
        position_cap=10,
        ma250=None,
        chip={},
        chip_peaks=[],
        chip_support=None,
        chip_resistance=None,
        chip_support_lower=0,
        chip_support_upper=0,
        chip_resistance_lower=0,
        chip_resistance_upper=0,
        report_fusion={},
        main_force_score_result={},
        big_order_result={},
        stage_result=stage_result,
        wyck_result={},
        wyck_mid_result=None,
        chan_result={},
        chan_mid_result=None,
        expma10_val=None,
        expma12_val=None,
        expma20_val=None,
        expma50_val=None,
        expma_trend=None,
        expma_status_result={},
        resonance_result={},
        sector_data=None,
    )
    base.update(over)
    return StageContext.from_mapping(base)


def test_alias_report_stage_equals_momentum():
    assert alias_report_stage("走强") == "走强"
    assert alias_report_stage("") == "震荡"


def test_assemble_stage_aliases_short_term_momentum_not_determine_stage():
    """report['stage'] == short_term_momentum；忽略传入的 determine_stage 词。"""
    report = assemble_base_report(_minimal_assemble_ctx(stage="修复"))
    assert report["short_term_momentum"] == "走强"
    assert report["stage"] == report["short_term_momentum"] == "走强"
    assert report["major_stage"] == "蓄势"
    # 面板阶段词与 major / determine_stage 词表不混
    assert report["stage"] in SHORT_MOMENTUM_VOCAB
    assert report["major_stage"] in MAJOR_STAGE_VOCAB
    assert report["stage"] != "修复"  # 未采用 determine_stage 入参


def test_panel_stage_line_not_major_or_determine_stage_words():
    """stage_line / midline_stage 应为周线威科夫短词，不等于 determine_stage 动能词表冒充 major。"""
    # 定论块：无阶段 ≠ 蓄势/走强
    from trader_shared.conclusion_block import synthesize_midline_verdict

    v = synthesize_midline_verdict(
        chanlun_midline={"chanlun": {"structure_type": "盘整", "structure_confidence": "low"}},
        wyckoff_midline={"phase": "none", "timeframe": "insufficient"},
        fallback_stage="走强",
    )
    assert v["stage"] == "无阶段"
    assert v["stage"] not in SHORT_MOMENTUM_VOCAB
    assert v["stage"] != "蓄势"


def test_get_major_stage_no_momentum_map():
    """走强不得映射成主升。"""
    r = {"stage": "走强", "short_term_momentum": "走强"}
    assert major_stage_from_report(r) == ""
    assert signal_get_major(r) == ""
    assert present_get_major(r) == ""

    r2 = {"major_stage": "蓄势", "stage": "走强"}
    assert signal_get_major(r2) == "蓄势"
    assert present_get_major(r2) == "蓄势"


def test_attach_stage_pack_fallback_not_fed_by_zouqiang():
    """缺 stage_result 时不得用 stage=走强 填 major_stage。"""
    report = {
        "symbol": "000001.SZ",
        "name": "测",
        "support": 9.0,
        "resistance": 11.0,
        "stop": 8.5,
        "confirm": 10.5,
        "scene": "等转强",
        "major_stage": "",  # 空 → 默认蓄势，而非走强
        "short_term_momentum": "走强",
    }
    ctx = StageContext(
        cost_price=0.0,
        current=10.0,
        market_env_data={},
        stage_result=None,  # 触发 fallback
        atr14_val=0.5,
        bars=[],
        wyck_result={},
        support=9.0,
        confirm=10.5,
        expma10_val=None,
        expma20_val=None,
        chip_migration=None,
        levels={"ma_values": {}, "atr_pct": 0.02},
        bars_date="",
        base_status="中性整理",
        theory_status="等转强",
        scene="等转强",
        signal_win_rate=None,
        stage="走强",
        short_term_momentum="走强",
    )
    out, _, _, _ = attach_stage_position_pack(report, ctx)
    # position_info / stage_stop 用的 major 不得是动能词
    assert out.get("position_info") is not None
    # fallback major 应为蓄势（默认），不是走强
    from trader_shared.stage_positioning import compute_position_with_env

    # 直接再验 fallback 构造：走强不能进 major
    bad = {"major_stage": "走强", "momentum": "走强"}
    assert bad["major_stage"] not in MAJOR_STAGE_VOCAB
    # attach 后 report 上若写了 major，不应是走强
    maj = str(out.get("major_stage") or "")
    assert maj != "走强"
    if maj:
        assert maj in MAJOR_STAGE_VOCAB or maj.startswith("蓄势")


def test_mistery_gate_refuses_momentum_as_major_stage():
    """走强不得经 mistery_gate 洗成主升。"""
    from trader_shared.mistery_gate import compute_mistery_gate, _normalize_stage

    assert _normalize_stage("走强") == ""
    assert _normalize_stage("修复") == ""
    assert _normalize_stage("蓄势偏强") == "蓄势"
    g = compute_mistery_gate({
        "major_stage": "走强",  # 误传动能词
        "short_term_momentum": "走强",
        "regime": "正常",
        "current": 10,
        "support": 9.5,
        "stop": 9.0,
        "confirm": 11,
        "risk": 0.5,
        "reward_near": 1.5,
    })
    # 缺 major → 降档；不得按「主升×走强」放行
    assert "缺字段降档" in " ".join(g.get("notes") or []) or g.get("position_cap_pct", 99) <= 10
    assert g.get("action") != "加仓"


def test_resonance_wujieduan_plus_major_xushi_not_aligned():
    """中线无阶段 + major 蓄势 → 背景不通过，不得 aligned。"""
    cards = {
        "wyckoff_midline": {
            "direction": 0,
            "bias": "neutral",
            "timeframe": "weekly",
            "summary_line": "周线无清晰阶段",
            "raw_available": True,
            "phase": "none",
        },
        "chan": {"direction": 0, "bias": "neutral", "summary_line": "中性"},
        "chip": {"direction": 0, "bias": "neutral", "summary_line": "中性"},
        "momentum": {"direction": 0, "bias": "neutral", "summary_line": "中性"},
    }
    report = {
        "major_stage": "蓄势",
        "midline_stage": "无阶段",
        "midline_bias": "neutral",
        "wyckoff_midline": {"phase": "none", "timeframe": "weekly"},
        "analysis_cards": cards,
        "theory_status": "等转强",
        "support": 10.0,
        "current": 10.5,
        "confirm": 11.0,
        "stop": 9.5,
    }
    bg = _eval_background(report, cards)
    assert bg["ok"] is False
    assert "无阶段" in bg["note"] or "不参与" in bg["note"]
    res = build_resonance(report)
    assert res["posts"]["background"]["ok"] is False
    assert res["grade"] != "aligned"


def test_g_k2_wyckoff_alias_equals_midline_no_daily_fallback():
    """G-K2 / W-DIFF-3 / M-G2：mid 不足时 report['wyckoff'] = insufficient 桩，≠ daily。"""
    daily = {
        "timeframe": "daily",
        "phase": "accumulation_b",
        "wyckoff_summary": "日线吸筹",
        "spring_signal": False,
        "upthrust_signal": False,
        "bc_signal": False,
        "sow_signal": False,
        "sos_signal": False,
    }
    report = assemble_base_report(
        _minimal_assemble_ctx(
            wyck_result={"wyckoff": daily},
            wyck_mid_result=None,
        )
    )
    assert report["wyckoff"] is report["wyckoff_midline"]
    assert report["wyckoff"]["timeframe"] == "insufficient"
    assert report["wyckoff"] is not report["wyckoff_daily"]
    assert report["wyckoff_daily"] is daily or report["wyckoff_daily"] == daily

    mid = {
        "timeframe": "weekly",
        "phase": "accumulation_c",
        "wyckoff_summary": "周线吸筹",
        "spring_signal": True,
        "upthrust_signal": False,
        "bc_signal": False,
        "sow_signal": False,
        "sos_signal": False,
    }
    report2 = assemble_base_report(
        _minimal_assemble_ctx(
            wyck_result={"wyckoff": daily},
            wyck_mid_result={"wyckoff": mid},
        )
    )
    assert report2["wyckoff"] is report2["wyckoff_midline"]
    assert report2["wyckoff"] is mid
    assert report2["wyckoff"] is not report2["wyckoff_daily"]
