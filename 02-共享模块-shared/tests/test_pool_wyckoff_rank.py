"""威科夫吸筹链文案与同道排序（无网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "01-功能包-packages"
    / "trader"
    / "scripts"
)
for p in (str(ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pool_cmds.scoring import sort_items_unified  # noqa: E402
from pool_cmds.wyckoff_rank import (  # noqa: E402
    extract_accum_events,
    format_wyckoff_chain_plain,
    wyckoff_chain_rank,
)


def test_format_chain_with_gap():
    item = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": False,
        }
    }
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→Spring确认→LPS，还差SOS"
    assert extract_accum_events(item) == ["SC", "AR", "ST", "LPS"]


def test_format_chain_complete():
    item = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": True,
        }
    }
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→Spring确认→LPS→SOS"
    assert "事件" not in format_wyckoff_chain_plain(item)


def test_format_short_chain():
    item = {"wyckoff": {"sc_signal": True, "ar_signal": True}}
    assert format_wyckoff_chain_plain(item) == "威：SC→AR，还差Spring确认"


def test_format_empty():
    assert format_wyckoff_chain_plain({"wyckoff": {}}) == "威：吸筹链未成型"


def test_c_f1_failed_phase_a_sc_has_no_gap_copy():
    """C-F1：phase_a_status=failed 时保留 SC，禁止「还差」。"""
    item = {"wyckoff": {"sc_signal": True}, "phase_a_status": "failed"}
    out = format_wyckoff_chain_plain(item)
    assert out == "威：SC（Phase A 已失效）"
    assert "还差" not in out


def test_c_f2_failed_phase_a_keeps_lit_chain_from_nested_range():
    """C-F2：nested phase_a_range.status=failed 时展示已亮链，不追加下一灯。

    W-02：广义 ST（secondary_test_sc）不进链 ST 槽，故链上只有 SC→AR。
    """
    item = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "secondary_test_sc_signal": True,
            "phase_a_range": {"status": "failed"},
        }
    }
    out = format_wyckoff_chain_plain(item)
    assert out == "威：SC→AR（Phase A 已失效）"
    assert "还差" not in out
    assert "Spring确认" not in out


def test_w02_secondary_test_sc_does_not_light_chain_st_as_spring_confirm():
    """W-02 / phase-a §4.4.2：测 SC 不得点亮链 ST；Spring 确认才点亮。"""
    only_st_sc = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": False,
            "spring_test_signal": False,
            "secondary_test_sc_signal": True,
        }
    }
    assert extract_accum_events(only_st_sc) == ["SC", "AR"]
    # 已亮链不含 Spring确认；「还差Spring确认」是缺口提示，允许
    out = format_wyckoff_chain_plain(only_st_sc)
    assert out.startswith("威：SC→AR")
    assert "SC→AR→Spring确认" not in out

    spring_confirm = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "spring_test_signal": True,
        }
    }
    assert extract_accum_events(spring_confirm) == ["SC", "AR", "ST"]
    assert format_wyckoff_chain_plain(spring_confirm) == "威：SC→AR→Spring确认，还差LPS"


def test_c_f3_failed_phase_a_without_accum_events_is_invalid_structure():
    """C-F3：failed 但无吸筹链亮灯时，不写健康未成型/还差。"""
    out = format_wyckoff_chain_plain({"phase_a_range": {"status": "failed"}})
    assert out == "威：结构已失效"
    assert "还差" not in out
    assert "吸筹链未成型" not in out


def test_w01_failed_phase_a_chain_rank_is_zero():
    """W-01：failed 长链不得按亮灯数排前；rank 须归零。"""
    failed_long = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "phase_a_status": "failed",
        }
    }
    healthy_short = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
        }
    }
    assert "已失效" in format_wyckoff_chain_plain(failed_long)
    assert wyckoff_chain_rank(failed_long) == 0
    assert wyckoff_chain_rank(healthy_short) == 2
    assert wyckoff_chain_rank(failed_long) < wyckoff_chain_rank(healthy_short)


def test_failed_phase_a_keeps_list_input_legacy_behavior():
    """列表输入只有 events，无 failed 信息时保持旧行为。"""
    assert format_wyckoff_chain_plain(["SC"]) == "威：SC，还差AR"


def test_bc_cooldown_plain():
    item = {"wyckoff": {"bc_signal": True, "sc_signal": False}}
    assert format_wyckoff_chain_plain(item) == "威：BC后观望"
    assert wyckoff_chain_rank(item) == 0


def test_bc_with_sc_ar_uses_chain_not_bc_watch():
    item = {"wyckoff": {"bc_signal": True, "sc_signal": True, "ar_signal": True}}
    assert format_wyckoff_chain_plain(item) == "威：SC→AR，还差Spring确认"
    assert wyckoff_chain_rank(item) == 2


def test_stale_cache_ignored_when_signals_update():
    """旧 plain/rank 缓存不得盖住新信号。"""
    item = {
        "wyckoff_chain_plain": "威：吸筹链未成型",
        "wyckoff_chain_rank": 0,
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": False,
        },
    }
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→Spring确认→LPS，还差SOS"
    assert wyckoff_chain_rank(item) == 4


def test_nested_emptyish_wyckoff_merges_flats():
    """legacy nested dict 不挡扁平旗。"""
    item = {
        "wyckoff": {"phase_label": "蓄势", "accumulation": True},
        "wyckoff_sc_signal": True,
        "wyckoff_ar_signal": True,
        "wyckoff_st_signal": True,
    }
    assert extract_accum_events(item) == ["SC", "AR", "ST"]
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→Spring确认，还差LPS"


def test_attach_report_overrides_stale_record_cache():
    from pool_cmds.wyckoff_rank import attach_wyckoff_chain_fields

    record = {
        "wyckoff_chain_plain": "威：吸筹链未成型",
        "wyckoff_chain_rank": 0,
        "wyckoff_chain": [],
    }
    report = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": True,
        }
    }
    attach_wyckoff_chain_fields(record, report)
    assert record["wyckoff_chain_plain"] == "威：SC→AR→Spring确认→LPS→SOS"
    assert record["wyckoff_chain_rank"] == 5


def test_rank_caps_without_st():
    no_st = {"wyckoff": {"sc_signal": True, "ar_signal": True, "lps_signal": True}}
    with_st = {
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
        }
    }
    assert wyckoff_chain_rank(no_st) <= 2
    assert wyckoff_chain_rank(with_st) == 4
    assert wyckoff_chain_rank(with_st) > wyckoff_chain_rank(no_st)


def _ready_base(**extra):
    base = {
        "lane": "ready",
        "lane_zh": "可盯",
        "status": "执行",
        "resonance_grade": "aligned",
        "total_score": 70,
        "major_stage": "蓄势",
        "current": 10.0,
        "trigger": 10.1,
        "confirm": 10.1,
        "defense": 9.0,
        "risk_reward": 1.8,
        "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
        "buy_point_status": "active",
        "decision_view": {
            "discipline_allow": True,
            "strategy_entry_lit": True,
            "allow_new_recommend": True,
        },
        "chan_buy_point_types": ["一买"],
        "rs_label": "neutral",
    }
    base.update(extra)
    return base


def test_sort_within_ready_prefers_longer_chain():
    short = _ready_base(
        name="链短",
        wyckoff={"sc_signal": True, "ar_signal": True},
        wyckoff_chain_rank=None,
    )
    long = _ready_base(
        name="链长",
        total_score=60,  # 分更低仍应因链更长排前
        wyckoff={
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": True,
        },
        wyckoff_chain_rank=None,
    )
    ordered = sort_items_unified([short, long])
    assert ordered[0]["name"] == "链长"


def test_sort_same_chain_prefers_strong_rs_over_neutral():
    """同道同链：强 RS 排前于中性（弱 RS 会降道，另测）。"""
    chain = {
        "sc_signal": True,
        "ar_signal": True,
        "st_signal": True,
        "lps_signal": True,
        "sos_signal": True,
    }
    neutral = _ready_base(
        name="中性RS",
        total_score=80,
        wyckoff={**chain, "rs_label": "neutral"},
        rs_label="neutral",
    )
    strong = _ready_base(
        name="强RS",
        total_score=50,
        wyckoff={**chain, "rs_label": "strong", "rs_note": "强于科创"},
        rs_label="strong",
        rs_note="强于科创",
    )
    ordered = sort_items_unified([neutral, strong])
    assert ordered[0]["name"] == "强RS"


def test_attach_copies_weekly_rs_fields():
    from pool_cmds.wyckoff_rank import attach_wyckoff_chain_fields, format_rs_plain, wyckoff_rs_rank

    record: dict = {}
    report = {
        "wyckoff": {
            "timeframe": "weekly",
            "sc_signal": True,
            "ar_signal": True,
            "rs_label": "strong",
            "rs_score": 0.75,
            "rs_note": "强于科创",
            "rs_index": "000688.SH",
            "rs_index_label": "科创",
            "rs_gate": "",
        }
    }
    attach_wyckoff_chain_fields(record, report)
    assert record["rs_label"] == "strong"
    assert record["rs_score"] == 0.75
    assert record["wyckoff_rs_rank"] == 3
    assert format_rs_plain(record) == "强于科创"
    assert wyckoff_rs_rank({"rs_label": "weak"}) == 0
    assert format_rs_plain({"rs_label": "weak", "rs_note": "弱于上证"}) == "弱于上证 · 慎跟"


def test_weak_rs_downgrades_ready_to_wait():
    from pool_cmds.classify import classify_lane

    report = {
        "current": 10.0,
        "trigger": 10.1,
        "confirm": 10.1,
        "support": 9.8,
        "defense": 9.0,
        "major_stage": "蓄势",
        "resonance_grade": "aligned",
        "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
        "decision_view": {
            "allow_new_recommend": True,
            "discipline_allow": True,
            "strategy_entry_lit": True,
        },
        "chan_buy_point_types": ["一买"],
        "rs_label": "weak",
        "rs_note": "弱于创业板",
        "wyckoff": {"rs_label": "weak", "timeframe": "weekly"},
    }
    out = classify_lane(report)
    assert out["lane"] == "wait"
    assert "慎跟" in out["lane_reason"]
