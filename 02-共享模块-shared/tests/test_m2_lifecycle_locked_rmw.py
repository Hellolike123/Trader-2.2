"""M2：buy_point_lifecycle 锁内 RMW；并发写不同 symbol 均保留。"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from trader_shared.buy_point_lifecycle import (
    clear_failed_record,
    load_failed_record,
    save_failed_record,
    _load_store,
)


def _worker_save(store: str, symbol: str, sid: str) -> None:
    save_failed_record(
        symbol,
        signal_id=sid,
        lid_price=10.0,
        failed_date="2026-07-28",
        path=Path(store),
    )


def test_concurrent_save_different_symbols_both_kept(tmp_path: Path):
    store = tmp_path / "buy_point_lifecycle.json"
    p1 = mp.Process(target=_worker_save, args=(str(store), "688248.SH", "sid-aaa"))
    p2 = mp.Process(target=_worker_save, args=(str(store), "000001.SZ", "sid-bbb"))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    assert p1.exitcode == 0 and p2.exitcode == 0

    data = _load_store(store)
    assert "688248.SH" in data or any("688248" in k for k in data)
    assert "000001.SZ" in data or any("000001" in k for k in data)
    a = load_failed_record("688248.SH", path=store)
    b = load_failed_record("000001.SZ", path=store)
    assert a is not None and a["signal_id"] == "sid-aaa"
    assert b is not None and b["signal_id"] == "sid-bbb"


def test_env_path_respected(tmp_path: Path, monkeypatch):
    store = tmp_path / "custom_lifecycle.json"
    monkeypatch.setenv("TRADER_BUY_POINT_LIFECYCLE_PATH", str(store))
    from trader_shared import buy_point_lifecycle as bpl

    assert bpl.store_path() == store
    save_failed_record("600000.SH", signal_id="x", lid_price=1.0, failed_date="2026-07-28")
    assert store.exists()
    assert load_failed_record("600000.SH") is not None
    clear_failed_record("600000.SH")
    assert load_failed_record("600000.SH") is None
