# -*- coding: utf-8 -*-
"""Fusion 仅仪表 + 单一 execution_caps 出口（架构 #4/#5）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_extreme_weighted_score_does_not_change_major_stage():
    """fusion weighted_score 不得微调 major_stage。"""
    from trader_shared.stage_detect import _detect_major_stage

    ma = {"ma5": 10.0, "ma10": 9.8, "ma20": 9.5, "ma30": 9.2}
    bars = [
        {"close": 9.0 + i * 0.05, "high": 9.1 + i * 0.05, "low": 8.9 + i * 0.05, "volume": 1000}
        for i in range(30)
    ]
    mf = {"stage": "accumulation", "confidence": 70, "reason": "吸筹"}

    base, *_ = _detect_major_stage(
        10.5, ma, bars, fusion_hint=None, main_force_result=mf
    )
    bull, *_ = _detect_major_stage(
        10.5,
        ma,
        bars,
        fusion_hint={"weighted_score": 0.99, "confidence": 0.95, "action": "增持"},
        main_force_result=mf,
    )
    bear, *_ = _detect_major_stage(
        10.5,
        ma,
        bars,
        fusion_hint={"weighted_score": -0.99, "confidence": 0.95, "action": "空仓/止损"},
        main_force_result=mf,
    )
    assert base == bull == bear


def test_chip_stage_no_fusion_confidence_mutate_from_score():
    """chip_stage 不得因 weighted_score<0 改写 fusion.confidence。"""
    src = Path(ROOT / "trader_shared/report_pipeline/chip_stage.py").read_text(encoding="utf-8")
    assert "weighted_score" not in src or "report_fusion[\"confidence\"]" not in src
    assert "confidence" not in src or "_boost" not in src
    # 明确：旧 mutate 块已删除
    assert 'report_fusion["confidence"]' not in src
    assert "_boost" not in src


def test_no_mid_bullish_downgrade_in_attach_short_midline():
    """纪律只收紧：不得再有 mid_bullish_downgrade 改写 action。"""
    src = Path(
        ROOT / "trader_shared/report_pipeline/attach_short_midline.py"
    ).read_text(encoding="utf-8")
    assert "mid_bullish_downgrade" not in src
    assert "减1/3 (中线偏多)" not in src


def test_attach_short_midline_no_fusion_action_force_no_chase():
    """key_prices chase 不得再读 fusion.action。"""
    src = Path(
        ROOT / "trader_shared/report_pipeline/attach_short_midline.py"
    ).read_text(encoding="utf-8")
    # 场景闸仍可存在；fusion.action 分支已删
    assert 'report_fusion or {}).get("action"' not in src
    assert '_fa = str((report_fusion' not in src


def test_holding_hint_no_fusion_action_fallback():
    """holding_hint 只听纪律，不回退 fusion.action。"""
    sm = Path(
        ROOT / "trader_shared/report_pipeline/attach_short_midline.py"
    ).read_text(encoding="utf-8")
    sp = Path(
        ROOT / "trader_shared/report_pipeline/attach_stage_pack.py"
    ).read_text(encoding="utf-8")
    assert 'fusion") or {}).get("action")' not in sm
    assert "(report.get(\"fusion\") or {}).get(\"action\")" not in sm
    assert "fusion_action_str" not in sp
    assert "disc_action_str or fusion_action_str" not in sp
    assert 'report_fusion or {}).get("action"' not in sp
    # stage_pack 不消费 fusion（merge 在其后）
    assert "report_fusion" not in sp


def test_structure_stage_omits_fusion_hint_and_result():
    """structure_stage 调用点不传 fusion action/score 进阶段/结构。"""
    src = Path(
        ROOT / "trader_shared/report_pipeline/structure_stage.py"
    ).read_text(encoding="utf-8")
    assert "fusion_hint=None" in src
    assert "fusion_result=None" in src
    assert "report_fusion" not in src
    assert '"weighted_score": report_fusion.get("weighted_score"' not in src


def test_builder_pre_cards_early_merge_after_stage_pack():
    """A1：pre_cards 早；merge 在 stage_pack 后、short_midline 前；不做 A2。"""
    src = Path(ROOT / "trader_shared/report_builder.py").read_text(encoding="utf-8")
    # 只看 build_report 函数体（避开顶部 import）
    body = src.split("def build_report", 1)[1]
    assert "run_pre_cards_stage(" in body
    assert "run_fusion_merge_stage(" in body
    i_pre = body.index("run_pre_cards_stage(")
    i_struct = body.index("run_structure_stage(")
    i_pack = body.index("attach_stage_position_pack(")
    i_merge = body.index("run_fusion_merge_stage(")
    i_sm = body.index("attach_short_midline_and_decision(")
    assert i_pre < i_struct < i_pack < i_merge < i_sm


def test_fusion_merge_stage_tags_instrument():
    """merge 出口带 product_role=instrument。"""
    from trader_shared.report_pipeline.fusion_stage import run_fusion_merge_stage

    fusion = run_fusion_merge_stage(
        chan_result={},
        momentum_result={},
        wyck_result={},
        bars=[],
        env={"level": "正常", "hmm_regime_en": "range"},
        quote={"current_change_pct": 0},
        current=10.0,
        main_force_env="unknown",
        fetcher=None,
        data_status="full",
        fund_flow_features=None,
        snapshot=type("S", (), {})(),
        volume_warning=None,
        analysis_cards={},
    )
    assert isinstance(fusion, dict)
    assert fusion.get("product_role") == "instrument"
    assert "fusion_verbatim" in fusion
    # R4/A4：仪表文案，禁止 🎯 action 指令主行；仍保留字段
    verbatim = str(fusion.get("fusion_verbatim") or "")
    assert verbatim
    assert "🎯" not in verbatim
    assert "仅参考" in verbatim


def test_assemble_stage_omits_fusion_hint():
    src = Path(
        ROOT / "trader_shared/report_pipeline/assemble_stage.py"
    ).read_text(encoding="utf-8")
    assert "fusion_hint=None" in src


def test_dv_deny_caps_via_apply_execution_caps_only():
    from trader_shared.decision_view import apply_decision_view, apply_execution_caps

    r = {
        "discipline": {
            "allow_new_entry": True,
            "suggested_pct_cap": 25,
            "position_cap_pct": 25,
            "suggested_pct_cap_mid": 20,
            "suggested_pct_cap_short": 15,
            "entry_checklist": {
                "all_green": True,
                "missing_labels": [],
                "entry_line": "新开：可试探（清单全绿）",
            },
            "entry_line": "新开：可试探（清单全绿）",
        },
        "resonance": {"grade": "empty", "scene": "pullback_probe", "conflict": False},
        "strategy_match": {
            "schema_version": "strategy_match_v1",
            "gates": {"entry": {"primary": None, "mode": "off", "executable": False}},
        },
        "suggested_pct": 25,
        "position_info": {"suggested_pct": 25},
        "has_position": False,
        "conclusion": {"execution": "回踩轻仓试探", "reason": "测"},
    }
    apply_decision_view(r, tighten_discipline=True)
    assert r["decision_view"]["allow_new_recommend"] is False
    # 尚未 caps
    assert r["discipline"]["suggested_pct_cap"] == 25
    apply_execution_caps(r)
    assert r["suggested_pct"] == 0
    assert r["position_info"]["suggested_pct"] == 0
    assert r["discipline"]["suggested_pct_cap"] == 0
    assert r["discipline"]["position_cap_pct"] == 0
    assert r["discipline"]["suggested_pct_cap_mid"] == 0
    assert r["discipline"]["suggested_pct_cap_short"] == 0


def test_attach_decision_stack_calls_execution_caps_on_fail_closed(monkeypatch):
    from trader_shared.report_pipeline.attach_decision_stack import (
        attach_analysis_decision_stack,
    )

    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "suggested_pct": 18,
        "position_info": {"suggested_pct": 18},
        "discipline": {
            "allow_new_entry": False,
            "suggested_pct_cap": 18,
            "position_cap_pct": 18,
            "action": "观望",
        },
        "analysis_cards": {},
        "has_position": False,
    }

    def _boom(*_a, **_k):
        raise RuntimeError("match boom")

    import trader_shared.strategy_match as sm

    monkeypatch.setattr(sm, "match_strategies", _boom)
    out = attach_analysis_decision_stack(report)
    assert out["decision_view"]["allow_new_recommend"] is False
    assert out["suggested_pct"] == 0
    assert out["discipline"]["suggested_pct_cap"] == 0


def test_attach_short_midline_has_no_suggested_pct_surgery_block():
    """attach 内不再有 allow_new_entry→suggested_pct 手术（交给 caps）。"""
    src = Path(
        ROOT / "trader_shared/report_pipeline/attach_short_midline.py"
    ).read_text(encoding="utf-8")
    assert "0%（纪律不新开）" not in src
    assert "0%（纪律禁止加仓；持仓按减仓/观察）" not in src
    assert "纪律 cap 收紧" not in src


def test_attach_short_midline_outer_fail_zeros_caps_via_execution_caps(monkeypatch):
    """短中线外层失败：fail-closed DV + apply_execution_caps 清零 stage_pack 残留。"""
    from trader_shared.report_pipeline.attach_short_midline import (
        attach_short_midline_and_decision,
    )
    from trader_shared.report_pipeline.stage_context import StageContext

    report = {
        "suggested_pct": 22,
        "position_info": {"suggested_pct": 22},
        "has_position": False,
        "discipline": {
            "allow_new_entry": True,
            "suggested_pct_cap": 22,
            "position_cap_pct": 22,
        },
    }

    def _boom_key_prices(**_k):
        raise RuntimeError("key_prices boom")

    import trader_shared.key_prices as kp

    monkeypatch.setattr(kp, "build_key_prices", _boom_key_prices)
    ctx = StageContext(
        current=10.0,
        scene="回踩",
        report_fusion={"weighted_score": 0.3, "action": "半仓试"},
        stage_result={"major_stage": "蓄势", "momentum": "中性"},
        weekly_bars=[],
        suggested=22,
        theory_status="",
        market_env_data={},
        has_position=False,
        data_status="full",
        chip_resistance_lower=None,
        chip_resistance_upper=None,
        stage="蓄势",
        short_term_momentum="蓄势",
    )
    out = attach_short_midline_and_decision(report, ctx)
    assert out["decision_view"]["allow_new_recommend"] is False
    assert out["suggested_pct"] == 0
    assert out["position_info"]["suggested_pct"] == 0
    assert out["discipline"]["suggested_pct_cap"] == 0
