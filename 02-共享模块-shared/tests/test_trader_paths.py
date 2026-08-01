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
    "signals",
    "chip_history",
    "calibrated_params",
    "trailing_stop_watermark",
    "buy_point_lifecycle",
    "last_add_dates",
    "wyckoff_phase",
    "position",
    "positions_portfolio",
    "account",
    "t0_ledger",
    "t0_state",
    "holdings",
}


def test_path_keys_cover_minimum():
    assert REQUIRED_KEYS.issubset(PATH_KEYS)


def test_keys_resolve_under_trader_root(tmp_path: Path, monkeypatch):
    root = tmp_path / "trader_home"
    monkeypatch.setenv("TRADER_ROOT", str(root))
    assert trader_root() == root
    assert path("root") == root
    assert path("pool") == root / "pool.json"
    assert path("holdings") == root / "holdings.json"
    assert path("position") == root / "position.json"
    assert path("positions_portfolio") == root / "positions.json"
    assert path("t0_ledger") == root / "t0_ledger.jsonl"
    assert path("t0_state") == root / "t0_state.json"
    assert path("buy_point_lifecycle") == root / "buy_point_lifecycle.json"
    assert path("trailing_stop_watermark") == root / "trailing_stop_watermark.json"


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
    from trader_shared.chip_migration_monitor import _chip_history_path
    from trader_shared.t0_account import _ledger_path, _position_path

    assert store_path() == root / "buy_point_lifecycle.json"
    assert _store_path() == root / "last_add_dates.json"
    assert _trailing_watermark_path() == root / "trailing_stop_watermark.json"
    assert _wyckoff_phase_path() == root / "wyckoff_phase.json"
    assert _chip_history_path() == root / "chip_history.json"
    assert _position_path() == root / "position.json"
    assert _ledger_path() == root / "t0_ledger.jsonl"


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
