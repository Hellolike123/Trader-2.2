"""t0_candidate_core fusion override 阈值：严格 >（对齐 decision_core）。

法源：docs/plans/arch-residual-cleanup-handoff.md R2/A2；
docs/audit/p0-batch-1-report.md — 「超过阈值」= 严格 >。
"""
from __future__ import annotations

import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "trader_shared"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_t0_source_uses_strict_gt_not_gte():
    """源码锁：fallback 路径须 fc > threshold，禁止 >=。"""
    src = (PKG / "t0_candidate_core.py").read_text(encoding="utf-8")
    assert "fc > FUSION_CONFIDENCE_THRESHOLD" in src
    assert "fc >= FUSION_CONFIDENCE_THRESHOLD" not in src


def test_t0_fallback_no_override_when_fc_equals_threshold(monkeypatch):
    """A2 无网边界：override 开且 fc == threshold → 不覆盖（走 t0 fallback）。"""
    import trader_shared.config as _cfg
    import trader_shared.t0_candidate_core as t0

    monkeypatch.setattr(t0, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)
    th = float(t0.FUSION_CONFIDENCE_THRESHOLD)

    real_import = builtins.__import__

    def _block_decision_core(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "trader_shared.decision_core" or (
            name == "trader_shared" and fromlist and "decision_core" in fromlist
        ):
            raise ImportError("forced offline for t0 fallback")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_decision_core)

    # 中间价位无 override → 防守观察；若误用 >= 会 remap「减仓」→ 冲高减仓
    status = t0.status_for(
        current=10.3,
        support=10.0,
        low_zone_upper=10.1,
        confirm=10.5,
        hard_stop=9.5,
        position_ratio=0.0,
        change_pct=0.0,
        fusion_result={"action": "减仓", "confidence": th},
    )
    assert status == "防守观察"


def test_t0_fallback_overrides_when_fc_above_threshold(monkeypatch):
    """对照：override 开且 fc > threshold → fallback 可 remap。"""
    import trader_shared.config as _cfg
    import trader_shared.t0_candidate_core as t0

    monkeypatch.setattr(t0, "FUSION_OVERRIDE_ENABLED", True)
    monkeypatch.setattr(_cfg, "FUSION_OVERRIDE_ENABLED", True)
    th = float(t0.FUSION_CONFIDENCE_THRESHOLD)

    real_import = builtins.__import__

    def _block_decision_core(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "trader_shared.decision_core" or (
            name == "trader_shared" and fromlist and "decision_core" in fromlist
        ):
            raise ImportError("forced offline for t0 fallback")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_decision_core)

    status = t0.status_for(
        current=10.3,
        support=10.0,
        low_zone_upper=10.1,
        confirm=10.5,
        hard_stop=9.5,
        position_ratio=0.0,
        change_pct=0.0,
        fusion_result={"action": "减仓", "confidence": th + 0.01},
    )
    assert status == "冲高减仓"
