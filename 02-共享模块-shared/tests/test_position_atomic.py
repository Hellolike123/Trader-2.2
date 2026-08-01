"""position.json 经 DataManager 原子 RMW 落盘。"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def test_save_position_atomic_roundtrip(tmp_path, monkeypatch):
    root = tmp_path / ".trader"
    root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_ROOT", str(root))

    # 引擎在 trader_shared；包入口为 identity shim
    from trader_shared import t0_account as acc
    import trader_shared.holdings as holdings_mod

    holdings_mod._migrated_once = False
    monkeypatch.setattr(acc, "POSITION_FILE", None)

    acc.save_position("688248", {"avg_cost": 50.0, "total_shares": 1000})
    pos = acc.load_position("688248")
    assert pos is not None
    assert pos["avg_cost"] == 50.0
    assert pos["total_shares"] == 1000

    # 文件可读且为合法 JSON
    raw = json.loads((root / "position.json").read_text(encoding="utf-8"))
    assert "688248" in raw["positions"]

    acc.save_position("000001", {"avg_cost": 10.0, "total_shares": 200})
    all_pos = acc.list_positions()
    assert set(all_pos) == {"688248", "000001"}

    # shim 身份替换：monkeypatch shared 对包入口生效
    pkg = Path(__file__).resolve().parents[2] / "01-功能包-packages" / "t0" / "scripts"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import t0_account as pkg_acc  # noqa: E402

    assert pkg_acc is acc or pkg_acc.__name__ in ("trader_shared.t0_account", "t0_account")
    assert hasattr(pkg_acc, "save_position")
