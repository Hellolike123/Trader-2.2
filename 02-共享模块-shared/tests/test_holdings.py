"""holdings SSOT: resolve_cost, upsert roundtrip, M3 regression, watermark gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def trader_tmp(tmp_path, monkeypatch):
    root = tmp_path / "trader"
    root.mkdir()
    monkeypatch.setenv("TRADER_ROOT", str(root))
    import trader_shared.holdings as h

    h._migrated_once = False
    return root


def test_resolve_cost_explicit_wins(trader_tmp):
    from trader_shared.holdings import resolve_cost_price, upsert_holding

    upsert_holding("600519.SH", cost=1600.0, shares=100, name="贵州茅台")
    assert resolve_cost_price("600519.SH", explicit_cost=1700.0) == 1700.0


def test_resolve_cost_uses_holdings_when_explicit_zero(trader_tmp):
    from trader_shared.holdings import resolve_cost_price, upsert_holding

    upsert_holding("600519.SH", cost=1600.0, shares=100, name="贵州茅台")
    assert resolve_cost_price("600519.SH", explicit_cost=0.0) == 1600.0
    assert resolve_cost_price("600519", explicit_cost=0) == 1600.0


def test_resolve_cost_empty_is_zero(trader_tmp):
    from trader_shared.holdings import resolve_cost_price

    assert resolve_cost_price("000001.SZ", explicit_cost=0) == 0.0
    assert resolve_cost_price("", explicit_cost=0) == 0.0


def test_upsert_get_roundtrip(trader_tmp):
    from trader_shared.holdings import get_holding, list_holdings, upsert_holding
    from trader_shared.trader_paths import path

    rec = upsert_holding(
        "688248.SH", cost=42.5, shares=200, name="南网科技", source="manual"
    )
    assert rec["cost"] == 42.5
    assert get_holding("688248.SH")["shares"] == 200
    assert "688248.SH" in list_holdings()
    raw = json.loads(path("holdings").read_text(encoding="utf-8"))
    assert raw["schema"] == "holdings_v1"
    assert raw["by_symbol"]["688248.SH"]["name"] == "南网科技"


def test_track_signals_do_not_create_holdings(trader_tmp, monkeypatch):
    """M3 regression: signals track/low_buy must not populate holdings or cost."""
    from trader_shared.holdings import list_holdings, resolve_cost_price
    from trader_shared.signal_core import read_signals_for_report

    home = trader_tmp.parent / "home"
    trader = home / ".trader"
    trader.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    # Keep holdings under TRADER_ROOT (trader_tmp); signals under HOME/.trader for signal_core
    signals = trader / "signals.jsonl"
    rows = [
        {
            "symbol": "688248",
            "name": "南网科技",
            "signal_type": "track",
            "trigger": {"price": 42.5},
            "trade_date": "2026-07-28",
        },
        {
            "symbol": "688248",
            "name": "南网科技",
            "signal_type": "low_buy_triggered",
            "trigger": {"price": 41.0},
            "trade_date": "2026-07-29",
        },
    ]
    signals.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    bars = [{"date": f"2026-07-{d:02d}", "close": 40.0 + d} for d in range(20, 32)]
    cost, _wr = read_signals_for_report("688248", bars)
    assert cost == 0.0
    assert list_holdings() == {}
    assert resolve_cost_price("688248.SH", explicit_cost=0) == 0.0


def test_watermark_gate_uses_resolved_cost(trader_tmp, monkeypatch):
    """Unit-level: resolved cost>0 enables trail symbol; cost=0 does not."""
    from trader_shared.holdings import resolve_cost_price, upsert_holding

    upsert_holding("600000.SH", cost=11.5, shares=100)
    resolved = resolve_cost_price("600000.SH", explicit_cost=0.0)
    assert resolved > 0
    trail_sym = "600000.SH" if float(resolved or 0) > 0 else None
    assert trail_sym == "600000.SH"

    empty = resolve_cost_price("000001.SZ", explicit_cost=0.0)
    assert empty == 0.0
    assert ( "000001.SZ" if float(empty or 0) > 0 else None) is None

    # report_builder must call resolve_cost_price before watermark gate
    import trader_shared.report_builder as rb

    src = Path(rb.__file__).read_text(encoding="utf-8")
    assert "resolve_cost_price" in src
    assert "if float(cost_price or 0) > 0:" in src
    # M3: signal cost must not drive ratchet
    assert "or float(_signal_cost_price or 0) > 0" not in src


def test_migrate_legacy_position_json(trader_tmp, monkeypatch):
    from trader_shared.trader_paths import path
    import trader_shared.holdings as h

    pos = path("position")
    pos.write_text(
        json.dumps(
            {
                "positions": {
                    "600519.SH": {"avg_cost": 1500.0, "total_shares": 100, "name": "茅台"}
                }
            }
        ),
        encoding="utf-8",
    )
    h._migrated_once = False
    from trader_shared.holdings import get_holding, migrate_legacy_into_holdings

    migrate_legacy_into_holdings()
    hit = get_holding("600519.SH")
    assert hit is not None
    assert hit["cost"] == 1500.0
    assert hit["shares"] == 100


def test_t0_save_dual_writes_holdings(trader_tmp, monkeypatch):
    from trader_shared import t0_account as acc
    from trader_shared import data_manager as dm
    from trader_shared.holdings import get_holding
    import trader_shared.holdings as h

    h._migrated_once = False
    monkeypatch.setattr(acc, "POSITION_FILE", trader_tmp / "position.json")
    monkeypatch.setattr(dm.DataManager, "ROOT_DIR", trader_tmp)

    acc.save_position("688248.SH", {"avg_cost": 50.0, "total_shares": 1000, "name": "南网科技"})
    pos = acc.load_position("688248.SH")
    assert pos is not None
    assert pos["avg_cost"] == 50.0
    hit = get_holding("688248.SH")
    assert hit is not None
    assert hit["cost"] == 50.0
    assert hit["shares"] == 1000
