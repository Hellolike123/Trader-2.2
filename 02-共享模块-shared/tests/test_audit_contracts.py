"""交叉审计不变量：把「换 Agent 才能发现」的问题固化成门禁检查。

覆盖（report-wyckoff-state-fixes-handoff + chanlun 审计收口）：
1. 读写契约：渲染层读的 ts_code/code/symbol 必须有写入方或兜底
2. 死代码：_mid_resist 等已删变量不得复活
3. 脆弱转换：渲染层不得直接 int(dict.get(...)) 无兜底
4. Wyckoff 状态机盘点：_PHASE_ORDER 齐全、产出 phase 全部入表、全配对迁移不变量
5. 缠论结构不变量：structure_type 枚举受控、末两中枢语义、线段护栏、方向单源、formulas 章节存在
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.wyckoff_phase import _PHASE_ORDER, _transition_phase  # noqa: E402


def _read(rel: str) -> str:
    return (_SHARED / rel).read_text(encoding="utf-8")


# ── 1. 读写契约 ───────────────────────────────────────────────────────────
def test_report_writes_ts_code_and_code():
    src = _read("trader_shared/report_pipeline/assemble_stage.py")
    assert '"ts_code": sec.ts_code' in src
    assert '"code": getattr(sec, "code", None)' in src


def test_report_reads_have_symbol_fallback():
    src = _read("trader_shared/report_renderer/short_midline.py")
    assert src.count('or r.get("symbol") or ""') >= 3


# ── 2. 死代码 ─────────────────────────────────────────────────────────────
def test_no_mid_resist_dead_code():
    for p in (_SHARED / "trader_shared").rglob("*.py"):
        if "_mid_resist" in p.read_text(encoding="utf-8"):
            raise AssertionError(f"_mid_resist 复活: {p}")


# ── 3. 脆弱转换 ───────────────────────────────────────────────────────────
def test_chan_dir2_uses_safe_int():
    src = _read("trader_shared/report_renderer/short_midline.py")
    assert "_chan_dir2 = _safe_int(" in src
    assert "def _safe_int" in src


def test_no_unsafe_int_on_dict_get_in_renderer():
    src = _read("trader_shared/report_renderer/short_midline.py")
    bad = re.findall(r"\bint\(\s*[^)]*\.get\(", src)
    assert not bad, f"渲染层存在无兜底 int(dict.get(...)): {bad}"


# ── 4. Wyckoff 状态机盘点 ─────────────────────────────────────────────────
def test_phase_order_contains_distribution_b_and_monotonic_depths():
    order = _PHASE_ORDER
    assert order["distribution_b"] == -2
    neg = [order[k] for k in ("markdown", "distribution_d", "distribution_c", "distribution_b", "distribution_a")]
    assert neg == sorted(neg)
    assert abs(order["distribution_a"]) < abs(order["distribution_b"]) < abs(order["distribution_c"])


def test_all_produced_phase_literals_in_order_map():
    src = _read("trader_shared/wyckoff_phase.py")
    produced = set(re.findall(r'"phase":\s*"([^"]+)"', src))
    assert produced <= set(_PHASE_ORDER), produced - set(_PHASE_ORDER)


def test_transition_phase_all_pairs_invariants():
    phases = list(_PHASE_ORDER)

    def old(p: str) -> dict:
        return {
            "phase": p,
            "phase_label": p,
            "phase_confidence_delta": 0.0,
            "first_seen": p,
        }

    for a in phases:
        for b in phases:
            out = _transition_phase(old(a), b, b, 0.0)
            oa, ob = _PHASE_ORDER[a], _PHASE_ORDER[b]
            if b == "none":
                assert out["phase"] == a, (a, b, out)
            elif a == "none":
                assert out["phase"] == b, (a, b, out)
            elif oa * ob > 0:
                expect = b if abs(ob) > abs(oa) else a
                assert out["phase"] == expect, (a, b, out)
            else:
                assert out["phase"] == b, (a, b, out)


def test_transition_phase_has_direct_tests():
    assert (_SHARED / "tests" / "test_wyckoff_phase_transition.py").exists()


# ── 5. 缠论结构不变量 ─────────────────────────────────────────────────────
def test_structure_type_literals_allowed():
    src = _read("trader_shared/chan_structure.py")
    allowed = {"无结构", "单边上涨", "单边下跌", "盘整", "上涨趋势", "下跌趋势"}
    produced = set(re.findall(r'_ok\("([^"]+)"\)', src))
    assert produced <= allowed, produced - allowed


def test_classify_uses_last_two_zones():
    src = _read("trader_shared/chan_structure.py")
    assert "valid_zones[-2], valid_zones[-1]" in src


def test_segment_tail_guard_present_both_directions():
    src = _read("trader_shared/chan_geometry.py")
    assert src.count("(len(strokes) - i) >= min_strokes") >= 2


def test_chan_direction_single_source():
    src = _read("trader_shared/chan_core.py")
    assert "_prim = resolve_chanlun_primary" in src


def test_formulas_documented_sections_present():
    src = _read("trader_shared/formulas.md")
    for marker in ("§3.7", "§9.4", "§11A"):
        assert marker in src, f"formulas.md 缺 {marker}"
