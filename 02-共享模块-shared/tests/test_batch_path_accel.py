# -*- coding: utf-8 -*-
"""批量路径加速回归测试（无网络）：refresh 死锁修复 + enrich 预热 + 腾讯 quote 硬超时。

覆盖 2026-08-06 三处性能/正确性改动，防止未来回归：
1. refresh 改用独立线程池（死锁修复：共享池嵌套导致全池卡死）
2. data_provider.prewarm_enrich（批量路径 enrich 预热，零语义改动）
3. light_data 腾讯 quote 硬超时（最坏 15.7s → 2.5s）
"""
from __future__ import annotations

import sys
import time
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


# ── 1. refresh 死锁回归 ─────────────────────────────────────────────────────


def _fake_pool() -> dict:
    return {
        "contract_version": 1,
        "updated_at": "2026-08-06",
        "items": [
            {"name": "票A", "target": "000001"},
            {"name": "票B", "target": "000002"},
            {"name": "票C", "target": "000003"},
        ],
    }


def test_refresh_uses_own_pool_not_shared(monkeypatch):
    """死锁修复回归：cmd_refresh 不得调用全局共享池（修复前共享池嵌套→死锁）。"""
    from pool_cmds import refresh as refresh_mod
    from pool_cmds.refresh import cmd_refresh

    monkeypatch.setattr(refresh_mod, "load_pool", lambda: _fake_pool())
    monkeypatch.setattr(refresh_mod, "active_items", lambda pool: pool["items"])
    monkeypatch.setattr(refresh_mod, "save_pool", lambda pool: None)
    monkeypatch.setattr(
        refresh_mod,
        "record_from_report",
        lambda key, report, offline=False: {
            "name": key,
            "target": key,
            "added_at": "2026-08-06",
            "major_stage": "蓄势",
            "status": "active",
        },
    )
    monkeypatch.setattr(
        refresh_mod,
        "safe_build_report",
        lambda target, offline=False: {"name": target, "target": target, "major_stage": "蓄势"},
    )
    # prewarm_enrich 在 refresh.py 内是函数内 import（调用时解析）→ 打源模块生效
    import trader_shared.data_provider as _dp

    monkeypatch.setattr(_dp, "prewarm_enrich", lambda keys: None)

    # 若 refresh 误用共享池 → 共享池被调用 → 这里抛异常让测试失败
    def _boom(*a, **k):
        raise AssertionError("refresh 不得使用全局共享池（死锁根因）")

    import trader_shared.cache_utils as _cu

    monkeypatch.setattr(_cu, "get_shared_build_pool", _boom)

    class _Args:
        target = None

    rc = cmd_refresh(_Args())
    assert rc == 0


def test_refresh_runs_in_parallel_not_serial(monkeypatch):
    """死锁修复回归：3 票各 0.2s → 独立池并行 ≈0.3s，串行会 ≈0.6s。"""
    from pool_cmds import refresh as refresh_mod
    from pool_cmds.refresh import cmd_refresh

    monkeypatch.setattr(refresh_mod, "load_pool", lambda: _fake_pool())
    monkeypatch.setattr(refresh_mod, "active_items", lambda pool: pool["items"])
    monkeypatch.setattr(refresh_mod, "save_pool", lambda pool: None)
    monkeypatch.setattr(
        refresh_mod,
        "record_from_report",
        lambda key, report, offline=False: {
            "name": key,
            "target": key,
            "added_at": "2026-08-06",
            "major_stage": "蓄势",
            "status": "active",
        },
    )
    import trader_shared.data_provider as _dp

    monkeypatch.setattr(_dp, "prewarm_enrich", lambda keys: None)

    def _slow(target, offline=False):
        time.sleep(0.2)
        return {"name": target, "target": target}

    monkeypatch.setattr(refresh_mod, "safe_build_report", _slow)

    class _Args:
        target = None

    t0 = time.time()
    rc = cmd_refresh(_Args())
    elapsed = time.time() - t0
    assert rc == 0
    # 串行 3×0.2=0.6s；并行 + 线程启动开销 < 0.55s 证明并行
    assert elapsed < 0.55, f"refresh 未并行（{elapsed:.2f}s），疑似串行/阻塞"


# ── 2. prewarm_enrich ───────────────────────────────────────────────────────


def test_prewarm_skipped_when_enrich_disabled(monkeypatch):
    """TRADER_SNAPSHOT_ENRICH=0 时 prewarm_enrich 不得抓取。"""
    from trader_shared import data_provider as _dp

    calls = []
    monkeypatch.setenv("TRADER_SNAPSHOT_ENRICH", "0")

    def _spy_enrich(snap):
        calls.append(snap)
        return snap

    monkeypatch.setattr(_dp, "_enrich_snapshot", _spy_enrich)
    _dp.prewarm_enrich(["000001", "000002"])
    assert calls == [], "ENRICH=0 时不应触发 enrich 抓取"


def test_prewarm_invalid_target_silent(monkeypatch):
    """无效 target 静默跳过，不抛错。"""
    from trader_shared import data_provider as _dp
    from trader_shared.light_data import resolve_security

    def _bad(target):
        raise ValueError(f"未知标的 {target}")

    monkeypatch.setattr(
        "trader_shared.light_data.resolve_security",
        _bad,
    )
    # 不抛即通过
    _dp.prewarm_enrich(["不存在的票ZZZ999"])


def test_prewarm_calls_enrich_for_each_target(monkeypatch):
    """正常路径：每 target 触发一次 _enrich_snapshot（写缓存）。"""
    from trader_shared import data_provider as _dp
    from trader_shared.market_types import Security

    seen = []

    def _mock_resolve(target):
        return Security(code=str(target), market="SZ", name=str(target))

    def _spy_enrich(snap):
        seen.append(snap.security.code)
        return snap

    monkeypatch.setattr(
        "trader_shared.light_data.resolve_security",
        _mock_resolve,
    )
    monkeypatch.setattr(_dp, "_enrich_snapshot", _spy_enrich)
    _dp.prewarm_enrich(["000001", "000001", "000002"])
    # 并行执行顺序不定 → 排序后计数比较
    assert sorted(seen) == ["000001", "000001", "000002"], f"应逐 target 触发，实际 {seen}"


# ── 3. 腾讯 quote 硬超时 ────────────────────────────────────────────────────


def test_tencent_hard_timeout_falls_back(monkeypatch):
    """腾讯腿挂 6s → 2.5s 硬超时切 mootdx，而非默认重试拖 15.7s。"""
    import trader_shared.light_data as _ld

    class _SlowHttp:
        def get_text(self, url, encoding="utf-8", max_retries=2):
            time.sleep(6)  # 远超硬超时 2.5s
            return "invalid"

    sec = _ld.resolve_security("000001")
    monkeypatch.setattr(_ld, "_tdx_first", lambda: False)  # 走腾讯优先分支
    monkeypatch.setattr(_ld, "_fetch_quote_tdx3", lambda sec: None)
    monkeypatch.setattr(
        _ld,
        "_fetch_quote_mootdx",
        lambda sec: {
            "name": sec.name,
            "symbol": sec.ts_code,
            "current_price": 10.5,
            "pre_close": 10.3,
            "open": 10.4,
            "high": 10.6,
            "low": 10.2,
            "volume": 1000,
            "current_change_pct": 1.94,
            "trade_date": "2026-08-06",
            "trade_time": "15:00",
            "data_source": "mootdx",
            "data_status": "full",
        },
    )

    t0 = time.time()
    q = _ld.fetch_quote(sec, _SlowHttp())
    elapsed = time.time() - t0
    assert q.get("data_source") == "mootdx", "腾讯失败应切 mootdx"
    # 硬超时 2.5s：elapsed 应在 ~2.5-3.5s（不是 6s+，也不是立即失败）
    assert elapsed < 4.0, f"硬超时未生效：{elapsed:.2f}s（预期 ≈2.5s）"
    assert elapsed >= 1.8, f"过早失败：{elapsed:.2f}s（应等硬超时边界）"
