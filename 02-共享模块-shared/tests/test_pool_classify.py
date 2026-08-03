"""选股池策略分道 classify_lane（无网络）。"""
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

from pool_cmds.classify import (  # noqa: E402
    classify_lane,
    ensure_lane,
    lane_rank,
    _chan_signal,
    _wyckoff_veto,
)
from pool_cmds.scoring import sort_items_unified  # noqa: E402


def test_stale_lane():
    out = classify_lane(
        {
            "current": 12.0,
            "trigger": 10.0,
            "confirm": 10.0,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.5},
            "decision_view": {
                "allow_new_recommend": True,
                "discipline_allow": True,
                "strategy_entry_lit": True,
            },
        }
    )
    assert out["lane"] == "stale"
    assert out["lane_zh"] == "计划过时"


def test_stale_still_mentions_failed_bp():
    out = classify_lane(
        {
            "current": 12.0,
            "trigger": 10.0,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "failed", "lid_price": 10.2},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": False,
            },
        }
    )
    assert out["lane"] == "stale"
    assert "买点失效" in out["lane_reason"]


def test_decay_beats_stale():
    out = classify_lane(
        {
            "current": 12.0,
            "trigger": 10.0,
            "defense": 9.0,
            "major_stage": "衰退",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.5},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": True,
            },
        }
    )
    assert out["lane"] == "avoid"
    assert out["status"] == "淘汰"


def test_avoid_failed_buy_point():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "failed", "lid_price": 10.2},
            "decision_view": {
                "allow_new_recommend": False,
                "discipline_allow": True,
                "strategy_entry_lit": True,
            },
        }
    )
    assert out["lane"] == "avoid"
    assert "买点失效" in out["lane_reason"]
    assert out["buy_point_valid"] is False


def test_avoid_momentum_veto():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.1,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "momentum_veto",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": True,
                "allow_new_recommend": False,
            },
        }
    )
    assert out["lane"] == "avoid"


def test_wyckoff_missing_distrib_background_not_veto():
    assert (
        _wyckoff_veto(
            {
                "major_stage": "蓄势",
                "wyckoff": {"phase_label": "无明确阶段（孤立 LPSY，缺派发背景）"},
            }
        )
        is False
    )


def test_wyckoff_event_code_vetoes():
    assert _wyckoff_veto({"major_stage": "蓄势", "wyckoff": {"event_type": "utad"}}) is True


def test_wyckoff_live_signal_vetoes():
    assert _wyckoff_veto({"major_stage": "蓄势", "wyckoff": {"are_signal": True}}) is True
    assert _wyckoff_veto({"major_stage": "蓄势", "wyckoff": {"bc_signal": True}}) is True
    assert _wyckoff_veto(
        {"major_stage": "蓄势", "wyckoff": {"upthrust_signal": True, "upthrust_premature": False}}
    ) is True
    assert _wyckoff_veto(
        {"major_stage": "蓄势", "wyckoff": {"upthrust_signal": True, "upthrust_premature": True}}
    ) is False
    assert _wyckoff_veto(
        {"major_stage": "蓄势", "wyckoff": {"trend_rally_signal": True}}
    ) is True


def test_ready_with_chan_and_active_bp():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "support": 9.8,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "missing_structure",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
            "decision_view": {
                "allow_new_recommend": False,
                "discipline_allow": True,
                "strategy_entry_lit": True,
            },
            "chan_buy_point_types": ["一买"],
        }
    )
    assert out["lane"] == "ready"
    assert out["status"] == "执行"
    assert out["buy_point_valid"] is True


def test_bp_none_in_zone_is_wait_not_ready():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "support": 9.8,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "none"},
            "decision_view": {
                "allow_new_recommend": False,
                "discipline_allow": True,
                "strategy_entry_lit": False,
            },
            "chan_buy_point_types": [],
        }
    )
    assert out["lane"] == "wait"


def test_discipline_false_blocks_ready():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.1,
            "confirm": 10.1,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "aligned",
            "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
            "decision_view": {
                "allow_new_recommend": False,
                "discipline_allow": False,
                "strategy_entry_lit": True,
            },
            "chan_buy_point_types": ["一买"],
        }
    )
    assert out["lane"] != "ready"


def test_offline_placeholder_is_wait():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.35,
            "confirm": 10.35,
            "support": 9.75,
            "defense": 9.45,
            "major_stage": "蓄势",
            "data_freshness": "offline",
            "data_note": "实时数据失败，使用离线占位：boom",
            "buy_point_lifecycle": {"status": "none"},
            "decision_view": {
                "discipline_allow": True,
                "strategy_entry_lit": False,
                "allow_new_recommend": False,
            },
        }
    )
    assert out["lane"] == "wait"
    assert "离线" in out["lane_reason"]


def test_wait_when_no_chan():
    out = classify_lane(
        {
            "current": 10.0,
            "trigger": 10.4,
            "confirm": 10.4,
            "support": 10.35,
            "defense": 9.0,
            "major_stage": "蓄势",
            "resonance_grade": "empty",
            "buy_point_lifecycle": {"status": "none"},
            "decision_view": {
                "allow_new_recommend": False,
                "discipline_allow": True,
                "strategy_entry_lit": False,
            },
            "chan_buy_point_types": [],
        }
    )
    assert out["lane"] == "wait"


def test_chan_signal_formal_only_rejects_observe():
    """F4：类一/类二观察档不得算日缠真信号；正式一类买可。"""
    assert _chan_signal(
        {"chan_buy_point_types": ["类一买"]}, strategy_entry_lit=False
    ) is False
    assert _chan_signal(
        {"chan_buy_point_types": ["类二买"]}, strategy_entry_lit=False
    ) is False
    assert _chan_signal(
        {"chan_buy_point_types": ["一类买"]}, strategy_entry_lit=False
    ) is True
    assert _chan_signal(
        {"chan_buy_point_types": ["二类买"]}, strategy_entry_lit=False
    ) is True
    # 禁止子串：不得因「一买」命中「类一买」
    assert _chan_signal(
        {"chan_buy_point_types": ["类一买"]}, strategy_entry_lit=False
    ) is False
    assert _chan_signal(
        {"chan_buy_point_types": ["一买"]}, strategy_entry_lit=False
    ) is True


def test_ensure_lane_reclassifies_price_drift():
    """刷价后旧 lane=ready 必须重算为计划过时。"""
    item = {
        "name": "漂移",
        "lane": "ready",
        "lane_zh": "可盯",
        "status": "执行",
        "current": 12.0,
        "trigger": 10.0,
        "confirm": 10.0,
        "defense": 9.0,
        "major_stage": "蓄势",
        "resonance_grade": "aligned",
        "buy_point_lifecycle": {"status": "active", "lid_price": 9.5},
        "buy_point_status": "active",
        "decision_view": {
            "discipline_allow": True,
            "strategy_entry_lit": True,
            "allow_new_recommend": True,
        },
    }
    out = ensure_lane(item)
    assert out["lane"] == "stale"
    assert out["status"] == "观察"


def test_sort_ready_beats_high_score_wait():
    ready = {
        "name": "可盯低分",
        "resonance_grade": "aligned",
        "total_score": 60,
        "major_stage": "蓄势",
        "current": 10.0,
        "trigger": 10.1,
        "confirm": 10.1,
        "defense": 9.0,
        "risk_reward": 1.6,
        "buy_point_lifecycle": {"status": "active", "lid_price": 9.8},
        "decision_view": {
            "discipline_allow": True,
            "strategy_entry_lit": True,
            "allow_new_recommend": True,
        },
        "chan_buy_point_types": ["一买"],
    }
    wait = {
        "name": "等齐高分",
        "resonance_grade": "aligned",
        "total_score": 95,
        "major_stage": "主升",
        "current": 10.0,
        "trigger": 10.1,
        "confirm": 10.1,
        "defense": 9.0,
        "risk_reward": 2.5,
        "buy_point_lifecycle": {"status": "none"},
        "decision_view": {
            "discipline_allow": True,
            "strategy_entry_lit": False,
            "allow_new_recommend": False,
        },
        "chan_buy_point_types": [],
    }
    ordered = sort_items_unified([wait, ready])
    assert ordered[0]["name"] == "可盯低分"
    assert lane_rank("ready") > lane_rank("wait") > lane_rank("avoid")
