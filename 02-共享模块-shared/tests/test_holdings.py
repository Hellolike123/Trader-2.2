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
    from trader_shared.holdings import get_holding
    import trader_shared.holdings as h

    h._migrated_once = False
    # No DataManager.ROOT_DIR monkeypatch: save must route via trader_paths(TRADER_ROOT)
    acc.save_position("688248.SH", {"avg_cost": 50.0, "total_shares": 1000, "name": "南网科技"})
    pos = acc.load_position("688248.SH")
    assert pos is not None
    assert pos["avg_cost"] == 50.0
    hit = get_holding("688248.SH")
    assert hit is not None
    assert hit["cost"] == 50.0
    assert hit["shares"] == 1000
    assert (trader_tmp / "position.json").exists()
    assert (trader_tmp / "holdings.json").exists()


def test_migrate_does_not_overwrite_existing_holdings(trader_tmp):
    from trader_shared.holdings import get_holding, migrate_legacy_into_holdings, upsert_holding
    from trader_shared.trader_paths import path
    import trader_shared.holdings as h

    upsert_holding("600519.SH", cost=1600.0, shares=100, name="茅台", source="manual")
    path("position").write_text(
        json.dumps(
            {
                "positions": {
                    "600519.SH": {"avg_cost": 999.0, "total_shares": 50, "name": "茅台"}
                }
            }
        ),
        encoding="utf-8",
    )
    h._migrated_once = False
    migrate_legacy_into_holdings()
    hit = get_holding("600519.SH")
    assert hit is not None
    assert hit["cost"] == 1600.0
    assert hit["shares"] == 100


def test_migrate_skips_portfolio_name_only_rows(trader_tmp):
    from trader_shared.holdings import list_holdings, migrate_legacy_into_holdings
    from trader_shared.trader_paths import path
    import trader_shared.holdings as h

    path("positions_portfolio").write_text(
        json.dumps(
            {
                "holdings": [
                    {"name": "南网科技", "shares": 2000, "cost": 35.99},
                    {
                        "name": "中国铝业",
                        "shares": 2000,
                        "cost": 11.5,
                        "symbol": "601600.SH",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    h._migrated_once = False
    migrate_legacy_into_holdings()
    by = list_holdings()
    assert "601600.SH" in by
    assert by["601600.SH"]["cost"] == 11.5
    # name-only must not invent a symbol key
    assert all("南网" not in k for k in by)
    assert not any(v.get("name") == "南网科技" for v in by.values())


def test_portfolio_load_keeps_name_only_when_ssot_present(trader_tmp, monkeypatch):
    """Regression: SSOT must not replace/wipe name-only positions.json rows."""
    import importlib
    import sys
    from trader_shared.holdings import upsert_holding
    from trader_shared.trader_paths import path

    pf = path("positions_portfolio")
    pf.write_text(
        json.dumps(
            {
                "holdings": [
                    {"name": "南网科技", "shares": 2000, "cost": 35.99},
                    {
                        "name": "浦发银行",
                        "shares": 100,
                        "cost": 10.0,
                        "symbol": "600000.SH",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    upsert_holding("688248.SH", cost=50.0, shares=1000, name="南网科技T0", source="t0")
    upsert_holding("600000.SH", cost=11.0, shares=200, name="浦发银行", source="t0")

    pkg = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "review"
        / "scripts"
    )
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    import final_portfolio as fp

    importlib.reload(fp)
    monkeypatch.setattr(fp, "POSITIONS_PATH", None)
    rows = fp.load_positions()
    names = [r.get("name") for r in rows]
    assert "南网科技" in names  # name-only preserved
    name_only = next(r for r in rows if r.get("name") == "南网科技")
    assert not (name_only.get("symbol") or name_only.get("code"))
    coded = next(r for r in rows if r.get("name") == "浦发银行")
    assert coded.get("cost") == 11.0  # SSOT overlay
    assert coded.get("shares") == 200
    # T0-only symbol appended (different name than name-only 南网科技)
    assert any(r.get("symbol") == "688248.SH" for r in rows)

    # record_buy must not wipe name-only from legacy file
    fp.record_buy("测试票", 100, 1.0, symbol="000001.SZ")
    raw = json.loads(pf.read_text(encoding="utf-8"))
    legacy_names = [r.get("name") for r in raw.get("holdings") or []]
    assert "南网科技" in legacy_names
