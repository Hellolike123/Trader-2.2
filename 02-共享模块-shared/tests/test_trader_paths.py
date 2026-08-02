"""trader_paths registry: TRADER_ROOT, env overrides, concurrent rmw smoke."""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from trader_shared.trader_paths import PATH_KEYS, load_json, path, rmw_json, trader_root


REQUIRED_KEYS = {
    "root",
    "pool",
    "pending",
    "last_plan",
    "pool_archive",
    "signals",
    "signal_results",
    "chip_history",
    "calibrated_params",
    "trailing_stop_watermark",
    "buy_point_lifecycle",
    "last_add_dates",
    "wyckoff_phase",
    "wyckoff_phase_a_anchor",
    "position",
    "positions_portfolio",
    "account",
    "t0_ledger",
    "t0_state",
    "holdings",
    "last_target",
}


def test_path_keys_cover_minimum():
    assert REQUIRED_KEYS.issubset(PATH_KEYS)


def test_keys_resolve_under_trader_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "trader_home"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    assert trader_root() == root
    assert path("root") == root
    assert path("pool") == root / "pool.json"
    assert path("pool_archive") == root / "pool_archive.json"
    assert path("holdings") == root / "holdings.json"
    assert path("position") == root / "position.json"
    assert path("positions_portfolio") == root / "positions.json"
    assert path("t0_ledger") == root / "t0_ledger.jsonl"
    assert path("t0_state") == root / "t0_state.json"
    assert path("buy_point_lifecycle") == root / "buy_point_lifecycle.json"
    assert path("trailing_stop_watermark") == root / "trailing_stop_watermark.json"
    assert path("last_target") == root / "last_target.txt"
    assert path("signals") == root / "signals.jsonl"
    assert path("signal_results") == root / "signal_results.jsonl"
    assert path("wyckoff_light_snapshot") == root / "wyckoff_light_snapshot.json"
    assert path("wyckoff_phase_a_anchor") == root / "wyckoff_phase_a_anchor.json"


def test_env_override_buy_point_lifecycle(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    custom = tmp_path / "custom_lifecycle.json"
    monkeypatch.setenv("TRADER_BUY_POINT_LIFECYCLE_PATH", str(custom))
    assert path("buy_point_lifecycle") == custom
    # other keys still under TRADER_ROOT
    assert path("pool") == root / "pool.json"


def test_env_override_last_add_and_t0_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path / "root"))
    last_add = tmp_path / "la.json"
    t0_state = tmp_path / "state.json"
    monkeypatch.setenv("TRADER_LAST_ADD_PATH", str(last_add))
    monkeypatch.setenv("T0_TRADER_STATE_PATH", str(t0_state))
    assert path("last_add_dates") == last_add
    assert path("t0_state") == t0_state


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        path("not_a_real_key")


def _rmw_worker(root: str, key: str, val: str) -> None:
    import os

    os.environ["TRADER_ROOT"] = root

    def _mutate(data: dict) -> dict:
        data[key] = val
        return data

    rmw_json("holdings", _mutate)


def test_rmw_via_path_helper_concurrent_safe(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    # seed empty
    assert load_json("holdings") == {}

    p1 = mp.Process(target=_rmw_worker, args=(str(root), "a", "1"))
    p2 = mp.Process(target=_rmw_worker, args=(str(root), "b", "2"))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    assert p1.exitcode == 0 and p2.exitcode == 0
    data = load_json("holdings")
    assert data.get("a") == "1"
    assert data.get("b") == "2"


def test_writers_route_through_registry(tmp_path: Path, monkeypatch):
    """Smoke: migrated modules resolve stores under TRADER_ROOT."""
    root = tmp_path / "root"
    monkeypatch.setenv("TRADER_ROOT", str(root))

    from trader_shared.buy_point_lifecycle import store_path
    from trader_shared.position_add_store import _store_path
    from trader_shared.structure_core import _trailing_watermark_path
    from trader_shared.wyckoff_phase import _wyckoff_phase_path
    from trader_shared.wyckoff_phase_a_store import _wyckoff_phase_a_anchor_path
    from trader_shared.chip_migration_monitor import _chip_history_path
    from trader_shared.t0_account import _ledger_path, _position_path

    assert store_path() == root / "buy_point_lifecycle.json"
    assert _store_path() == root / "last_add_dates.json"
    assert _trailing_watermark_path() == root / "trailing_stop_watermark.json"
    assert _wyckoff_phase_path() == root / "wyckoff_phase.json"
    assert _wyckoff_phase_a_anchor_path() == root / "wyckoff_phase_a_anchor.json"
    assert _chip_history_path() == root / "chip_history.json"
    assert _position_path() == root / "position.json"
    assert _ledger_path() == root / "t0_ledger.jsonl"


def test_signal_core_pool_count_uses_trader_root(tmp_path: Path, monkeypatch):
    """C leak lock: get_pool_count must honor TRADER_ROOT, not HOME/.trader."""
    import json

    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    (home / ".trader").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ROOT", str(root))
    monkeypatch.setenv("HOME", str(home))

    (root / "pool.json").write_text(
        json.dumps({"items": [{"name": "A", "status": "执行"}, {"name": "B", "status": "淘汰"}]}),
        encoding="utf-8",
    )
    (home / ".trader" / "pool.json").write_text(
        json.dumps({"items": [{"name": "X", "status": "执行"}]}),
        encoding="utf-8",
    )

    from trader_shared.signal_core import get_pool_count

    assert get_pool_count() == 1


def test_t0_save_uses_trader_root_without_datamanager_patch(tmp_path: Path, monkeypatch):
    """Step A: t0 position writer must not hardcode ~/.trader via DataManager."""
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("TRADER_ROOT", str(root))
    # Ensure HOME/.trader would be a different place if DataManager leaked
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    from trader_shared import t0_account as acc
    import trader_shared.holdings as h

    h._migrated_once = False
    monkeypatch.setattr(acc, "POSITION_FILE", None)
    acc.save_position("000001.SZ", {"avg_cost": 10.0, "total_shares": 100})
    assert (root / "position.json").exists()
    assert not (home / ".trader" / "position.json").exists()


def test_signal_store_default_uses_trader_root(tmp_path: Path, monkeypatch):
    """signal_store DEFAULT path must honor TRADER_ROOT via trader_paths."""
    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    (home / ".trader").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ROOT", str(root))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("TRADER_SIGNAL_STORE_PATH", raising=False)

    import trader_shared.signal_store as store_mod

    store_mod.DEFAULT_SIGNAL_STORE_PATH = None
    p = store_mod._get_default_store_path()
    assert p == root / "signals.jsonl"
    assert p != home / ".trader" / "signals.jsonl"


def test_signal_store_env_override(tmp_path: Path, monkeypatch):
    custom = tmp_path / "custom_signals.jsonl"
    monkeypatch.setenv("TRADER_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("TRADER_SIGNAL_STORE_PATH", str(custom))

    import trader_shared.signal_store as store_mod

    store_mod.DEFAULT_SIGNAL_STORE_PATH = None
    assert store_mod._get_default_store_path() == custom


def test_pool_readers_use_trader_root(tmp_path: Path, monkeypatch):
    """cache_utils / wyckoff_run / portfolio_core pool reads honor TRADER_ROOT."""
    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    (home / ".trader").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ROOT", str(root))
    monkeypatch.setenv("HOME", str(home))

    from trader_shared.wyckoff_run import _pool_path

    assert _pool_path() == root / "pool.json"

    import json

    (root / "pool.json").write_text(
        json.dumps({"items": [{"name": "测", "status": "执行"}]}),
        encoding="utf-8",
    )
    (home / ".trader" / "pool.json").write_text(
        json.dumps({"items": [{"name": "漏", "status": "执行"}]}),
        encoding="utf-8",
    )

    from trader_shared.portfolio_core import _pool_resonance_index

    idx = _pool_resonance_index()
    assert "测" in idx or any("测" in str(k) for k in idx)
    assert "漏" not in idx and not any("漏" in str(k) for k in idx)


def test_last_target_key_resolves(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    assert path("last_target") == root / "last_target.txt"


def test_signal_tracker_paths_use_trader_root(tmp_path: Path, monkeypatch):
    """STORE_PATH / RESULT_PATH resolve under TRADER_ROOT (not HOME/.trader)."""
    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    (home / ".trader").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ROOT", str(root))
    monkeypatch.setenv("HOME", str(home))

    import trader_shared.signal_tracker as st

    # Restore proxies if a prior test replaced them with concrete Paths
    st.STORE_PATH = st._TraderKeyedPath("signals")
    st.RESULT_PATH = st._TraderKeyedPath("signal_results")

    assert Path(st.STORE_PATH) == root / "signals.jsonl"
    assert Path(st.RESULT_PATH) == root / "signal_results.jsonl"


def test_review_render_signals_use_trader_root(tmp_path: Path, monkeypatch):
    """review_render win-rate reader checks TRADER_ROOT signals, not HOME/.trader."""
    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    (home / ".trader").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ROOT", str(root))
    monkeypatch.setenv("HOME", str(home))

    # Only HOME has the file → must treat as missing (TRADER_ROOT wins)
    (home / ".trader" / "signals.jsonl").write_text("{}\n", encoding="utf-8")

    from trader_shared import review_render as rr

    assert rr._load_historical_win_rate("000001") is None

    # Root file present → passes exists gate; provider boom → still None (offline)
    (root / "signals.jsonl").write_text("", encoding="utf-8")

    class _Boom:
        def resolve_security(self, *_a, **_k):
            raise RuntimeError("offline")

        def fetch_qfq_daily(self, *_a, **_k):
            raise RuntimeError("offline")

    import trader_shared.data_provider as dp

    monkeypatch.setattr(dp, "get_provider", lambda: _Boom())
    assert rr._load_historical_win_rate("000001") is None
    assert path("signals") == root / "signals.jsonl"


def test_final_portfolio_positions_use_trader_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    import importlib
    import sys

    pkg = Path(__file__).resolve().parents[2] / "01-功能包-packages/review/scripts"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import final_portfolio as fp

    importlib.reload(fp)
    fp.POSITIONS_PATH = None
    assert fp._positions_path() == root / "positions.json"
