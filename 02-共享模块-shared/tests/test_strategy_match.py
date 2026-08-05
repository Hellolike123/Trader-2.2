"""P1 闸口契约 + P2 策略匹配 S-01～S-06。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.strategy_match import (  # noqa: E402
    GATES,
    build_match_context,
    format_gates_brief,
    load_strategy_packs,
    match_strategies,
    stop_buffer,
)


def test_g01_six_gates_present():
    r = match_strategies({"current": 10, "has_position": False, "allow_new_entry": False})
    assert r["schema_version"] == "strategy_match_v1"
    for g in GATES:
        assert g in r["gates"]


def test_context_includes_resonance_fields():
    """阶段 2：match context 暴露共振字段，供 YAML match。"""
    report = {
        "current": 10.0,
        "major_stage": "蓄势",
        "resonance": {
            "schema_version": "resonance_v1",
            "scene": "pullback_probe",
            "grade": "aligned",
            "conflict": False,
            "posts": {
                "background": {"ok": True, "note": "x"},
                "structure": {"ok": True, "note": "x"},
                "chip": {"ok": True, "note": "x"},
                "momentum": {"ok": True, "note": "x"},
            },
        },
        "analysis_cards": {"chan": {"type_short": "一买", "type_raw": "一类买"}},
    }
    ctx = build_match_context(report)
    assert ctx["resonance_grade"] == "aligned"
    assert ctx["resonance_aligned"] is True
    assert ctx["resonance_scene"] == "pullback_probe"
    assert ctx["resonance_post_structure"] is True
    assert ctx["resonance_conflict"] is False


def test_entry_pack_can_require_resonance_aligned():
    """策略包 match 可用 resonance_grade；未齐时不入选该包。"""
    pack = {
        "id": "entry.resonance_aligned_probe",
        "name": "共振齐试探",
        "gate": "entry",
        "priority": 99,
        "match": {
            "all": [
                {"field": "resonance_grade", "in": ["aligned"]},
                {"field": "chan_type_short", "in": ["一买"]},
            ]
        },
    }
    base = {
        "current": 15,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": True,
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "resonance": {
            "grade": "missing_structure",
            "scene": "pullback_probe",
            "conflict": False,
            "posts": {},
        },
    }
    r_miss = match_strategies(base, packs=[pack])
    assert r_miss["gates"]["entry"]["primary"] is None or (
        r_miss["gates"]["entry"]["primary"] or {}
    ).get("id") != "entry.resonance_aligned_probe"

    base["resonance"] = {
        "grade": "aligned",
        "scene": "pullback_probe",
        "conflict": False,
        "posts": {
            "background": {"ok": True},
            "structure": {"ok": True},
            "chip": {"ok": True},
            "momentum": {"ok": True},
        },
    }
    r_ok = match_strategies(base, packs=[pack])
    assert r_ok["gates"]["entry"]["primary"] is not None
    assert r_ok["gates"]["entry"]["primary"]["id"] == "entry.resonance_aligned_probe"


def test_g02_stop_policy_full_clear():
    r = match_strategies({"current": 10, "support": 9.5, "has_position": True, "cost": 10})
    assert r["gates"]["stop"]["stop_policy"] == "全清"
    assert r["gates"]["manage"]["stop_policy"] == "全清"


def test_s01_block_new_no_position_entry_not_active():
    """S-01: 不新开、无持仓 → entry 不得 active。"""
    r = match_strategies({
        "current": 20,
        "has_position": False,
        "allow_new_entry": False,
        "action_text": "不新开 · 观望",
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "checklist_all_green": False,
    })
    ent = r["gates"]["entry"]
    assert ent["mode"] in ("plan", "off")
    assert ent.get("executable") is not True
    assert ent["mode"] != "active"
    brief = format_gates_brief(r)
    assert "执行" not in brief.split("买：")[1].split("\n")[0] or "预案" in brief


def test_s02_sow_support_weak_veto_entry():
    """S-02: SOW + 下方难撑 → defense 否决 entry active。"""
    r = match_strategies({
        "current": 41.0,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": True,
        "wyckoff_event": "SOW",
        "chip_support_weak": True,
        "chip_trapped_tag": "多数套牢",
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
    })
    sel = r["gates"]["select"]
    assert sel["primary"] is not None
    assert "defense" in sel["primary"]["id"] or sel["veto_entry"] is True
    assert sel["veto_entry"] is True
    assert r["gates"]["entry"]["mode"] != "active"
    assert r["gates"]["entry"]["executable"] is not True


def test_s03_buy1_checklist_not_green_plan_only():
    """S-03: 一买 + 清单未全绿 → 不可可试探执行。"""
    r = match_strategies({
        "current": 15,
        "support": 14,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": False,
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "regime": "正常",
    })
    ent = r["gates"]["entry"]
    assert ent["primary"] is not None
    assert "buy1" in ent["primary"]["id"] or "一买" in (ent["primary"].get("name") or "")
    assert ent["mode"] == "plan"
    assert ent["executable"] is False


def test_l3_buy_point_failed_blocks_executable():
    """L3：lifecycle failed → entry 不得 executable，reason=买点已失效。"""
    r = match_strategies({
        "current": 15,
        "support": 14,
        "has_position": False,
        "allow_new_entry": True,  # 即使纪律未收紧，闸口仍拦
        "checklist_all_green": True,
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "regime": "正常",
        "buy_point_lifecycle": {
            "status": "failed",
            "lid_price": 14.0,
            "signal_id": "deadbeefdeadbeef",
            "failed_date": "2026-07-28",
            "display_line": "买点：已失效（破 14.00，须重走）",
        },
    })
    ent = r["gates"]["entry"]
    assert ent["mode"] == "plan"
    assert ent["executable"] is False
    assert ent.get("reason") == "买点已失效"
    assert ent.get("buy_point_status") == "failed"
    assert r["context"].get("buy_point_failed") is True
    brief = format_gates_brief(r)
    assert "买点已失效" in brief


def test_l3_watching_does_not_block_entry():
    """L3：watching（盘中破盖收盘收回）不关 entry executable。"""
    r = match_strategies({
        "current": 15,
        "support": 14,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": True,
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "regime": "正常",
        "buy_point_lifecycle": {
            "status": "watching",
            "lid_price": 14.0,
            "signal_id": "watchwatchwatch1",
            "display_line": "买点：观察中",
        },
    })
    ent = r["gates"]["entry"]
    assert ent["mode"] == "active"
    assert ent["executable"] is True
    assert ent.get("buy_point_status") == "watching"
    assert ent.get("reason") != "买点已失效"


def test_s04_position_floor_stop_full_clear():
    """S-04: 持仓 + floor → manage 止损价 + 全清。"""
    r = match_strategies({
        "current": 20.0,
        "support": 18.0,
        "stop": 17.5,
        "has_position": True,
        "cost": 19.0,
        "allow_new_entry": False,
    })
    man = r["gates"]["manage"]
    assert man["mode"] == "active"
    assert man["floor_price"] == 18.0
    assert man["stop_price"] is not None
    assert man["stop_price"] < 18.0
    assert man["stop_policy"] == "全清"
    assert r["gates"]["stop"]["stop_policy"] == "全清"
    assert r["gates"]["entry"]["mode"] == "off"


def test_s05_no_cost_not_s2():
    """S-05: 无 cost → 不得 S2。"""
    r = match_strategies({
        "current": 25.0,
        "support": 24.0,
        "has_position": True,
        "cost": None,
    })
    assert r["gates"]["manage"]["stage_id"] == "S1"
    # 有 cost 且浮盈足够才 S2
    r2 = match_strategies({
        "current": 25.0,
        "support": 20.0,
        "has_position": True,
        "cost": 20.0,  # +25%
    })
    assert r2["gates"]["manage"]["stage_id"] == "S2"


def test_s06_two_entry_only_one_primary():
    """S-06: 一买同时匹配 buy1/buy2 包 → 仅 1 primary（高 priority）。"""
    r = match_strategies({
        "current": 12,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": True,
        "chan_type_short": "一买",
        "chan_type_raw": "一类买",
        "regime": "正常",
    })
    ent = r["gates"]["entry"]
    assert ent["primary"] is not None
    assert ent["primary"]["id"] == "entry.chan_buy1_probe"
    cands = ent.get("candidates") or []
    assert all(c["id"] != ent["primary"]["id"] for c in cands)
    # 候选至多 1
    assert len(cands) <= 1


def test_load_packs_from_yaml():
    packs = load_strategy_packs()
    ids = {p["id"] for p in packs}
    assert "select.observe_G" in ids
    assert "manage.wyckoff_trail" in ids
    assert "stop.invalidate_full" in ids


def test_stop_buffer_tiers():
    assert stop_buffer(150) == 0.25
    assert stop_buffer(5) == 0.03
    assert stop_buffer(50) >= 0.05


def test_format_gates_brief_no_md():
    r = match_strategies({"current": 10, "has_position": False, "allow_new_entry": False})
    text = format_gates_brief(r)
    assert "📐" in text
    assert "#" not in text.split("\n")[0] or text.startswith("📐")
    assert "**" not in text
