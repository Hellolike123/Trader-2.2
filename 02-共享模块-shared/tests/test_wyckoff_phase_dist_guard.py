"""FINDING-2 / FINDING-1 回归单测（wyckoff-chan-state-audit-handoff 建议改项）。

- FINDING-2：markup 分支必须受 `distribution_confirmed` 簇守卫，派发确认后的
  Spring+SOS 假突破不得抬成主升 Markup（与 accumulation_d 的 Spring 分支对称）。
- FINDING-1：markup 分支的 TR 上沿统一从 tr_ctx 读取（与 markdown 分支对称），
  不再依赖 signals.tr_upper。

验证策略：内部 bars 重算（_scan_for_signal / _scan_last_event / _detect_st）被
stub 为静默，信号完全由传入的 signals dict 驱动，确保测试只检验阶段机的分支逻辑。
Spring 需 Phase B 背景（此处用 compression_signal 提供）才非 premature。
"""

import pytest

import trader_shared.wyckoff_phase as wp


@pytest.fixture(autouse=True)
def _stub_scans(monkeypatch):
    # 所有滑窗扫描 / 末次事件扫描返回静默；Spring/Test 检测器返回无信号
    monkeypatch.setattr(wp, "_scan_for_signal", lambda *a, **k: False)
    monkeypatch.setattr(wp, "_scan_last_event", lambda *a, **k: (-1, None))
    monkeypatch.setattr(wp, "_detect_st", lambda *a, **k: {"st_signal": False})


def _flat(n: int = 20, close: float = 10.0) -> list[dict]:
    return [
        {
            "date": f"2024-01-{i:02d}",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000,
        }
        for i in range(1, n + 1)
    ]


def _established_tr_ctx(tr_upper: float = 11.0, tr_lower: float = 9.0) -> dict:
    return {
        "tr_quality": 0.9,
        "phase_a_status": "established",
        "tr_upper": tr_upper,
        "tr_lower": tr_lower,
    }


def _spring_sos_sig(**extra) -> dict:
    """非 premature 的 Spring+SOS 信号（用 compression_signal 提供 Phase B 背景）。"""
    base = {
        "spring_signal": True,
        "sos_signal": True,
        "compression_signal": True,
        "last_close": 12.0,
        "distribution_confirmed": False,
        "distribution_failed": False,
    }
    base.update(extra)
    return base


def test_distribution_cluster_guards_markup():
    """派发簇确认后，Spring+SOS+突破上沿不得判 Markup。"""
    bars = _flat(20, close=10.0)
    tr_ctx = _established_tr_ctx()

    # 分布=False：Spring+SOS+站上 TR 上沿 → 主升 Markup
    r_no = wp._detect_phase(bars, _spring_sos_sig(), tr_ctx=tr_ctx)
    assert r_no["phase"] == "markup", r_no

    # 分布=True：同样信号 → 不得 Markup（落 markdown/none，非主升）
    r_yes = wp._detect_phase(
        bars, _spring_sos_sig(distribution_confirmed=True), tr_ctx=tr_ctx
    )
    assert r_yes["phase"] != "markup", r_yes
    # 且不应被 Spring+SOS 抬成积累 D（同样受簇守卫约束）
    assert r_yes["phase"] != "accumulation_d", r_yes


def test_finding1_tr_upper_read_from_tr_ctx():
    """markup 的 TR 上沿只存在于 tr_ctx（signals 不提供），仍能正确判 Markup。"""
    bars = _flat(20, close=10.0)
    tr_ctx = _established_tr_ctx(tr_upper=11.0)
    # 故意不提供 signals.tr_upper，验证来源统一到 tr_ctx
    r = wp._detect_phase(bars, _spring_sos_sig(), tr_ctx=tr_ctx)
    assert r["phase"] == "markup", r
