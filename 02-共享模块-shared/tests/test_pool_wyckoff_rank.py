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
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→ST→LPS，还差SOS"
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
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→ST→LPS→SOS"
    assert "事件" not in format_wyckoff_chain_plain(item)


def test_format_short_chain():
    item = {"wyckoff": {"sc_signal": True, "ar_signal": True}}
    assert format_wyckoff_chain_plain(item) == "威：SC→AR，还差ST"


def test_format_empty():
    assert format_wyckoff_chain_plain({"wyckoff": {}}) == "威：吸筹链未成型"


def test_bc_cooldown_plain():
    item = {"wyckoff": {"bc_signal": True, "sc_signal": False}}
    assert format_wyckoff_chain_plain(item) == "威：BC后观望"
    assert wyckoff_chain_rank(item) == 0


def test_bc_with_sc_ar_uses_chain_not_bc_watch():
    item = {"wyckoff": {"bc_signal": True, "sc_signal": True, "ar_signal": True}}
    assert format_wyckoff_chain_plain(item) == "威：SC→AR，还差ST"
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
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→ST→LPS，还差SOS"
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
    assert format_wyckoff_chain_plain(item) == "威：SC→AR→ST，还差LPS"


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
    assert record["wyckoff_chain_plain"] == "威：SC→AR→ST→LPS→SOS"
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


def test_sort_within_ready_prefers_longer_chain():
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
    }
    short = {
        **base,
        "name": "链短",
        "wyckoff": {"sc_signal": True, "ar_signal": True},
        "wyckoff_chain_rank": None,
    }
    long = {
        **base,
        "name": "链长",
        "total_score": 60,  # 分更低仍应因链更长排前
        "wyckoff": {
            "sc_signal": True,
            "ar_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sos_signal": True,
        },
        "wyckoff_chain_rank": None,
    }
    ordered = sort_items_unified([short, long])
    assert ordered[0]["name"] == "链长"
