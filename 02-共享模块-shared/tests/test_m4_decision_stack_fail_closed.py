"""M4：decision_stack 失败必须 fail-closed decision_view；persist 不冒充新开。"""
from __future__ import annotations

from trader_shared.report_pipeline.attach_decision_stack import attach_analysis_decision_stack
from trader_shared.signal_core import decision_persist_fields


def test_match_strategies_failure_writes_fail_closed_dv(monkeypatch):
    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "analysis_cards": {},
    }

    def _boom(*_a, **_k):
        raise RuntimeError("match boom")

    import trader_shared.strategy_match as sm
    monkeypatch.setattr(sm, "match_strategies", _boom)

    out = attach_analysis_decision_stack(report)
    dv = out.get("decision_view")
    assert isinstance(dv, dict)
    assert dv.get("allow_new_recommend") is False


def test_apply_decision_view_failure_fail_closed(monkeypatch):
    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "analysis_cards": {
            "chan": {"type_short": "二买", "direction": 1},
            "wyckoff_midline": {"timeframe": "weekly", "raw_available": True, "direction": 0},
            "chip": {"raw_available": True, "summary_line": "有峰"},
            "momentum": {"direction": 0, "confidence": 0.4},
        },
        "chip_peaks": [{"price": 9.5}],
        "key_prices": {"buy_zone_low": 9.5, "buy_zone_high": 10.2},
        "midline_stage": "吸筹",
    }

    def _boom(*_a, **_k):
        raise RuntimeError("dv boom")

    import trader_shared.decision_view as dv_mod
    monkeypatch.setattr(dv_mod, "apply_decision_view", _boom)

    out = attach_analysis_decision_stack(report)
    assert out["decision_view"]["allow_new_recommend"] is False


def test_persist_refuses_discipline_only_true():
    """无 DV 时不得用 discipline.allow_new_entry=True 写出允许新开。"""
    fields = decision_persist_fields(
        {"discipline": {"allow_new_entry": True}}
    )
    assert fields == {}
    assert fields.get("allow_new_recommend") is not True

    fields2 = decision_persist_fields(
        {
            "decision_view": {"allow_new_recommend": False},
            "discipline": {"allow_new_entry": True},
        }
    )
    assert fields2["allow_new_recommend"] is False


def test_outer_stack_failure_overwrites_stale_allow_true(monkeypatch):
    """M4：栈失败须强制覆盖陈旧 allow_new_recommend=True（禁 setdefault 泄漏）。"""
    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "decision_view": {
            "schema_version": "decision_view_v1",
            "allow_new_recommend": True,
            "summary_line": "陈旧放行",
        },
    }

    def _boom(*_a, **_k):
        raise RuntimeError("match boom")

    import trader_shared.strategy_match as sm
    monkeypatch.setattr(sm, "match_strategies", _boom)

    out = attach_analysis_decision_stack(report)
    assert out["decision_view"]["allow_new_recommend"] is False
    assert "不新开" in str(out["decision_view"].get("summary_line") or "")
