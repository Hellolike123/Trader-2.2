"""M8：chip / wyckoff_phase / position_add 锁内 RMW。"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from trader_shared.json_atomic import load_json_dict, locked_rmw_json


def _worker(path: str, key: str, val: str) -> None:
    def _mutate(data: dict) -> dict:
        data[key] = val
        return data

    locked_rmw_json(Path(path), _mutate)


def test_concurrent_locked_rmw_keeps_both_keys(tmp_path: Path):
    store = tmp_path / "store.json"
    p1 = mp.Process(target=_worker, args=(str(store), "a", "1"))
    p2 = mp.Process(target=_worker, args=(str(store), "b", "2"))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    assert p1.exitcode == 0 and p2.exitcode == 0
    data = load_json_dict(store)
    assert data.get("a") == "1"
    assert data.get("b") == "2"


def test_wyckoff_phase_atomic_save(tmp_path: Path, monkeypatch):
    store = tmp_path / "wyckoff_phase.json"
    monkeypatch.setattr(
        "trader_shared.wyckoff_phase._WYCKOFF_PHASE_FILE",
        str(store),
    )
    from trader_shared.wyckoff_phase import _save_phase_state, _load_phase_state

    _save_phase_state("688248", "weekly", {"phase": "accumulation_b"})
    _save_phase_state("000001", "daily", {"phase": "markup"})
    assert store.exists()
    raw = store.read_text(encoding="utf-8")
    assert raw.strip().endswith("}")  # 非截断
    assert _load_phase_state("688248", "weekly")["phase"] == "accumulation_b"
    assert _load_phase_state("000001", "daily")["phase"] == "markup"


def test_position_add_cross_process(tmp_path: Path, monkeypatch):
    store = tmp_path / "last_add_dates.json"
    monkeypatch.setenv("TRADER_LAST_ADD_PATH", str(store))

    def _rec(sym: str, day: str) -> None:
        from trader_shared.position_add_store import record_last_add
        record_last_add(sym, day)

    p1 = mp.Process(target=_rec, args=("688248.SH", "2026-07-28"))
    p2 = mp.Process(target=_rec, args=("000001.SZ", "2026-07-29"))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    assert p1.exitcode == 0 and p2.exitcode == 0
    from trader_shared.position_add_store import get_last_add_date
    assert get_last_add_date("688248.SH") == "2026-07-28"
    assert get_last_add_date("000001.SZ") == "2026-07-29"
