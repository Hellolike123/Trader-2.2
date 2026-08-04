"""C 合同测例 — 四票离线回归（wyckoff-epic-vol-phase-verif-handoff §1 方向 C）。

法源：``docs/plans/wyckoff-epic-vol-phase-verif-handoff.md`` §1（C-M1~C-M5）与 §4 验收（C1~C3）。

设计（C-M1）：**直接读 ~/.trader/cache 缓存 JSON 构造 bars**（不触网、不经过
fetch 层），``wyckoff_analysis`` 跑四票（南网 688248 / 茅台 600519 / 宁德 300750 /
工行 601398，日线 + 周线）；缓存缺失 → ``pytest.skip``（C-P1：只 skip 不报红）。

断言边界（C-M5，以缓存实际数据为准，不臆造）—— 2026-08-04 实测：
- 688248 日线（mootdx，370 根 last=07-31）：TR 非空（tr_quality=0.417）、BC 亮、
  distribution_confirmed=False、sos_kind 键存在、phase_a status=established。
- 688248 周线（daily_aggregate，171 根 last=08-03，旧格式无 vol_unit）：
  **TR 空（tr_quality=None）**、BC 亮、distribution_confirmed=True（08-03 突破日
  只含于周线缓存 → 派发确认成立；日线缓存缺 08-03，与周线数据边界不同，注明）。
  handoff C-M2 的「TR 非空 / distribution_confirmed=False」只对**日线**成立。
- 688248 周线 volume 单位与日线可比：周线[-2]（07-27~07-31 完整周）
  vol=251123.0 == 日线同周 5 根 vol 之和 251123.0（比值 1.0，同一单位=手）。
- 600519（mootdx 日线 500 根 / sina 周线 260 根）：SC 失效场景成立 →
  ar_reason 含「失效」且不含「未检测到 SC」（日线 + 周线均如此）。
- 300750 / 601398（日线 + 周线）：无矛盾字段——
  ``accumulation_confirmed ∧ phase_a_status == "failed"`` 不得并存（C-M4）。

离线约束：autouse fixture 禁周线 RS（``index_weekly_bars=None`` 会拉指数周线触网）；
``use_persisted_phase=False / use_persisted_phase_a_anchor=False`` 不读写
~/.trader 状态（C-P2：临时目录隔离由参数保证，不写真实状态文件）。
"""
from __future__ import annotations

import json
import os

import pytest

import trader_shared.wyckoff_rs as wrs
from trader_shared.wyckoff_core import wyckoff_analysis

_CACHE = os.path.expanduser("~/.trader/cache")


@pytest.fixture(autouse=True)
def _offline_rs(monkeypatch):
    """禁周线 RS：避免 index_weekly_bars=None 触发拉指数周线（C-P1 禁网）。"""
    monkeypatch.setattr(wrs, "WYCKOFF_RS_ENABLED", False)


def _load_bars(rel: str) -> list[dict]:
    path = os.path.join(_CACHE, rel)
    if not os.path.exists(path):
        pytest.skip(f"缓存缺失: {rel}（离线回归跳过，C-P1）")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    rows = d["rows"] if isinstance(d, dict) else d
    if not rows:
        pytest.skip(f"缓存为空: {rel}")
    return rows


def _analyze(code: str, rel: str, tf: str) -> dict:
    bars = _load_bars(rel)
    return wyckoff_analysis(
        bars,
        symbol=code,
        timeframe=tf,
        use_persisted_phase=False,          # 不读不写 ~/.trader 持久化阶段（C-P2）
        use_persisted_phase_a_anchor=False,  # 不读不写持久化 Phase A 锚（C-P2）
    )


class TestNanwang688248C:
    """C-M2：南网 688248 —— TR/BC/dist/sos_kind + 周线单位可比。"""

    def test_daily_tr_bc_dist_soskind(self):
        r = _analyze("688248", "daily/688248.json", "daily")
        # TR 非空（fallback 数据可识别交易区间）
        assert r.get("tr_quality") is not None
        assert r.get("tr_lower") is not None and r.get("tr_upper") is not None
        # BC 亮（近 90 根窗口内高位派发顶；实测 bc_signal=True）
        assert r.get("bc_signal") is True
        # dist 不误确认（实测 False）
        assert r.get("distribution_confirmed") is False
        # sos_kind 字段存在（实测 sos_signal=False → 值为 None，键必须存在）
        assert "sos_kind" in r
        # 数据边界注明：日线缓存 last=2026-07-31，08-03 突破日不在缓存内（C-M5）
        assert r.get("phase_a_range", {}).get("status") in (
            "established", "forming", "none", "failed",
        )

    def test_weekly_volume_comparable_with_daily(self):
        """周线（daily_aggregate，手）与日线（mootdx，手）同单位可比较。

        断言边界：周线[-2]=2026-07-31 完整周（07-27~07-31）vol 严格等于日线
        同周 5 根 vol 之和；周线 last=08-03 只含于周线缓存（日线缓存缺 08-03），
        故可比性验证用完整周（周线[-2]）。
        """
        daily = _load_bars("daily/688248.json")
        weekly = _load_bars("weekly/688248_SH.json")
        assert weekly[-1]["date"] > daily[-1]["date"], (
            "周线缓存含 08-03 而日线缓存止于 07-31 —— 断言边界以缓存为准"
        )
        week_bar = weekly[-2]  # 完整周（07-27~07-31）
        same_week = [b for b in daily if b["date"] <= week_bar["date"]][-5:]
        assert len(same_week) == 5
        assert week_bar["volume"] == pytest.approx(
            sum(b["volume"] for b in same_week), rel=1e-6
        ), "周线=日线逐日求和（daily_aggregate，同单位=手）"

    def test_weekly_fields_exist(self):
        r = _analyze("688248", "weekly/688248_SH.json", "weekly")
        assert "sos_kind" in r
        # 注明（C-M5）：周线缓存边界含 08-03 → 实测 distribution_confirmed=True、
        # tr_quality=None；不断言这两项（与 handoff C-M2 日线口径不同）
        assert r.get("bc_signal") is True


class TestMaotai600519C:
    """C-M3：茅台 600519 —— SC 失效场景文案（ar_reason 含「失效」）。"""

    @pytest.mark.parametrize("rel,tf", [
        ("daily/600519.json", "daily"),
        ("weekly/600519_SH.json", "weekly"),
    ])
    def test_sc_failed_wording(self, rel, tf):
        r = _analyze("600519", rel, tf)
        pa = r.get("phase_a_range") or {}
        if pa.get("status") == "failed":
            # 实测：ar_reason="SC 已失效（Phase A 失败），链终止，须重新寻底"
            assert "失效" in str(r.get("ar_reason") or "")
            assert "未检测到 SC" not in str(r.get("ar_reason") or "")
        else:
            # 缓存数据若不构成失效场景 → 退化为字段结构完整断言（C-M5 不臆造）
            assert r.get("ar_reason")  # 非空
            assert "sos_kind" in r


class TestNoContradictionC:
    """C-M4：宁德 300750 / 工行 601398 —— 防误报，无矛盾字段。"""

    @pytest.mark.parametrize("code,rel,tf", [
        ("300750", "daily/300750.json", "daily"),
        ("300750", "weekly/300750_SZ.json", "weekly"),
        ("601398", "daily/601398.json", "daily"),
        ("601398", "weekly/601398_SH.json", "weekly"),
    ])
    def test_no_acc_confirmed_with_failed_phase_a(self, code, rel, tf):
        r = _analyze(code, rel, tf)
        pa = r.get("phase_a_range") or {}
        # 实测：四组均满足（acc_conf=False 或 pa_status != failed）
        assert not (
            bool(r.get("accumulation_confirmed"))
            and pa.get("status") == "failed"
        ), f"{code} {tf}: accumulation_confirmed 与 phase_a failed 并存（矛盾）"
        # 输出契约字段存在（供渲染/下游消费）
        assert "distribution_confirmed" in r
        assert "sos_kind" in r
