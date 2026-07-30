"""买点盖生命周期 L1 + L2。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.buy_point_lifecycle import (  # noqa: E402
    build_buy_point_lifecycle_for_report,
    clear_failed_record,
    evaluate_buy_point_lifecycle,
    load_failed_record,
    mint_lifecycle_signal_id,
    reconcile_with_store,
    save_failed_record,
)


def test_close_below_lid_failed():
    out = evaluate_buy_point_lifecycle(
        current=9.5,
        last_close=9.5,
        lid_price=10.0,
        has_buy_signal=True,
        intraday=False,
    )
    assert out["status"] == "failed"
    assert "已失效" in out["display_line"]


def test_intraday_pierce_close_back_watching():
    out = evaluate_buy_point_lifecycle(
        current=9.8,
        last_close=10.2,
        lid_price=10.0,
        has_buy_signal=True,
        intraday=True,
    )
    assert out["status"] == "watching"


def test_active_above_lid():
    out = evaluate_buy_point_lifecycle(
        current=10.5,
        last_close=10.5,
        lid_price=10.0,
        has_buy_signal=True,
    )
    assert out["status"] == "active"
    assert "有效" in out["display_line"]


def test_report_builder_shape_failed():
    life = build_buy_point_lifecycle_for_report(
        {
            "current": 9.0,
            "support": 10.0,
            "chan_buy_point_types": ["一类买"],
            "daily_bars": [{"close": 9.0}],
            "key_prices": {"buy_zone_low": 10.0},
        },
        persist=False,
    )
    assert life["status"] == "failed"


def test_l2_persist_failed_and_block_old_signal_id(tmp_path: Path):
    store = tmp_path / "buy_point_lifecycle.json"
    symbol = "688248.SH"
    old_sid = "aaaaaaaaaaaaaaaa"

    save_failed_record(
        symbol,
        signal_id=old_sid,
        lid_price=10.0,
        failed_date="2026-07-28",
        path=store,
    )
    prev = load_failed_record(symbol, path=store)
    assert prev is not None
    assert prev["signal_id"] == old_sid

    # 同日或同旧 id 试图 active → 仍 failed，禁止接旧
    blocked = reconcile_with_store(
        {
            "status": "active",
            "lid_price": 10.0,
            "signal_id": None,
            "failed_date": None,
            "note": "买点有效",
            "display_line": "买点：有效（盖 10.00）",
        },
        symbol=symbol,
        trade_date="2026-07-28",
        candidate_signal_id=old_sid,
        persist=True,
        path=store,
    )
    assert blocked["status"] == "failed"
    assert blocked["signal_id"] == old_sid
    assert blocked.get("blocked_reuse") is True


def test_l03_next_day_stand_up_gets_new_signal_id(tmp_path: Path):
    """L-03：失败日后大阳站上 → 新 signal_id，非旧 id。"""
    store = tmp_path / "buy_point_lifecycle.json"
    symbol = "688248.SH"
    old_sid = "bbbbbbbbbbbbbbbb"
    save_failed_record(
        symbol,
        signal_id=old_sid,
        lid_price=10.0,
        failed_date="2026-07-28",
        path=store,
    )

    life = build_buy_point_lifecycle_for_report(
        {
            "symbol": symbol,
            "trade_date": "2026-07-29",
            "current": 11.0,
            "support": 10.0,
            "chan_buy_point_types": ["一类买"],
            "daily_bars": [{"date": "2026-07-29", "close": 11.0}],
            "key_prices": {"buy_zone_low": 10.0},
            "chanlun": {
                "buy_points": [
                    {"type": "一类买", "price": 10.5, "signal_id": "cccccccccccccccc"}
                ]
            },
        },
        persist=True,
        store=store,
    )
    assert life["status"] == "active"
    assert life["signal_id"] != old_sid
    assert life["signal_id"] == "cccccccccccccccc"
    assert load_failed_record(symbol, path=store) is None


def test_l03_mint_new_id_when_candidate_missing(tmp_path: Path):
    store = tmp_path / "buy_point_lifecycle.json"
    symbol = "000001.SZ"
    old_sid = mint_lifecycle_signal_id(symbol, "2026-07-28", 10.0)
    save_failed_record(
        symbol,
        signal_id=old_sid,
        lid_price=10.0,
        failed_date="2026-07-28",
        path=store,
    )
    life = build_buy_point_lifecycle_for_report(
        {
            "symbol": symbol,
            "trade_date": "2026-07-29",
            "current": 11.2,
            "support": 10.0,
            "chan_buy_point_types": ["二类买"],
            "daily_bars": [{"date": "2026-07-29", "close": 11.2}],
            "key_prices": {"buy_zone_low": 10.0},
        },
        persist=True,
        store=store,
    )
    assert life["status"] == "active"
    assert life["signal_id"]
    assert life["signal_id"] != old_sid
    assert load_failed_record(symbol, path=store) is None


def test_l2_failed_writes_store(tmp_path: Path):
    store = tmp_path / "buy_point_lifecycle.json"
    symbol = "600519.SH"
    life = build_buy_point_lifecycle_for_report(
        {
            "symbol": symbol,
            "trade_date": "2026-07-29",
            "current": 9.0,
            "support": 10.0,
            "chan_buy_point_types": ["一类买"],
            "daily_bars": [{"date": "2026-07-29", "close": 9.0}],
            "key_prices": {"buy_zone_low": 10.0},
        },
        persist=True,
        store=store,
    )
    assert life["status"] == "failed"
    assert life["signal_id"]
    assert life["failed_date"] == "2026-07-29"
    rec = load_failed_record(symbol, path=store)
    assert rec is not None
    assert rec["signal_id"] == life["signal_id"]
    clear_failed_record(symbol, path=store)
    assert load_failed_record(symbol, path=store) is None


def test_l04_failed_tightens_checklist_even_if_empty():
    """L-04：failed 时无清单也要写出 entry_line，且不允许新开。"""
    from trader_shared.report_pipeline.attach_buy_point import apply_buy_point_lifecycle

    report = {
        "current": 9.0,
        "support": 10.0,
        "chan_buy_point_types": ["一类买"],
        "daily_bars": [{"close": 9.0}],
        "key_prices": {"buy_zone_low": 10.0},
        "discipline": {
            "allow_new_entry": True,
            "entry_checklist": {
                "all_green": True,
                "flags": {
                    "mid_trend": True,
                    "pullback": True,
                    "short_trigger": True,
                    "fusion_conf": True,
                    "chip_fund": True,
                },
                "items": {},
                "missing_labels": [],
                "entry_line": "新开：可试探（清单全绿）",
            },
            "entry_line": "新开：可试探（清单全绿）",
        },
    }
    apply_buy_point_lifecycle(report)
    assert report["buy_point_lifecycle"]["status"] == "failed"
    disc = report["discipline"]
    assert disc["allow_new_entry"] is False
    cl = disc["entry_checklist"]
    assert cl["all_green"] is False
    assert cl["flags"]["short_trigger"] is False
    assert "买点已失效" in cl["missing_labels"]
    assert disc["entry_line"].startswith("新开：先别买") or disc["entry_line"].startswith("新开：否")


def test_life_line_not_preferred_over_buy_zone_low():
    """life_line 是中线结构支撑，不得当作 mid_pullback_low 抢先于 buy_zone_low。"""
    from trader_shared.buy_point_lifecycle import resolve_lid_price

    lid = resolve_lid_price(
        support=8.0,
        mid_pullback_low=None,  # pullback_low 缺失时不应塞 life_line
        buy_zone_low=9.80,
        explicit_lid=None,
    )
    assert lid == 9.8

    life = build_buy_point_lifecycle_for_report(
        {
            "current": 10.5,
            "support": 8.0,
            "chan_buy_point_types": ["一类买"],
            "daily_bars": [{"close": 10.5}],
            "key_prices": {"buy_zone_low": 9.80},
            "mid_key_prices": {"life_line": 8.50, "pullback_low": None},
        },
        persist=False,
    )
    assert life["lid_price"] == 9.8
    assert life["status"] == "active"
