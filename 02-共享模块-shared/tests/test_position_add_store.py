"""T+1 last_add_date 持久化。"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest


@pytest.fixture()
def add_store(tmp_path, monkeypatch):
    path = tmp_path / "last_add_dates.json"
    monkeypatch.setenv("TRADER_LAST_ADD_PATH", str(path))
    return path


def test_record_and_resolve_roundtrip(add_store):
    from trader_shared.position_add_store import get_last_add_date, record_last_add, resolve_last_add_date

    with patch("trader_shared.position_add_store._today_iso", return_value="2026-07-31"):
        td = record_last_add("688248.SH", name="南网科技")
    assert td == "2026-07-31"
    assert get_last_add_date("688248.SH") == "2026-07-31"
    assert get_last_add_date("688248") == "2026-07-31"
    assert get_last_add_date(None, name="南网科技") == "2026-07-31"
    assert resolve_last_add_date("688248.SH") == "2026-07-31"


def test_report_override_wins(add_store):
    from trader_shared.position_add_store import record_last_add, resolve_last_add_date

    record_last_add("000001.SZ", trade_date="2026-07-01")
    assert resolve_last_add_date(
        "000001.SZ",
        report={"last_add_date": "2026-07-30"},
    ) == "2026-07-30"


def test_maybe_record_only_on_pullback_add(add_store):
    from trader_shared.position_add_store import (
        get_last_add_date,
        maybe_record_from_report,
    )

    with patch("trader_shared.position_add_store._today_iso", return_value="2026-07-31"):
        maybe_record_from_report({
            "symbol": "600519.SH",
            "name": "贵州茅台",
            "position_state": {"state": "持仓观察"},
        })
        assert get_last_add_date("600519.SH") is None
        maybe_record_from_report({
            "symbol": "600519.SH",
            "name": "贵州茅台",
            "position_state": {"state": "回踩加仓"},
        })
        assert get_last_add_date("600519.SH") == "2026-07-31"


def test_t1_cooldown_reads_store(add_store):
    """evaluate_position_state 读到 store 中的今日加仓日 → T+1 冷却。"""
    from trader_shared.position_add_store import record_last_add
    from trader_shared.stage_positioning import evaluate_position_state

    record_last_add("000001.SZ", trade_date="2026-07-02")
    with patch("trader_shared.cn_time.today_cn", return_value=date(2026, 7, 2)):
        result = evaluate_position_state(
            current_price=10.0,
            support=10.0,
            resistance=12.0,
            stop_price=9.0,
            confirm_price=12.5,
            atr14=0.3,
            major_stage="蓄势",
            momentum="走强",
            has_position=True,
            entry_price=10.0,
            last_add_date="2026-07-02",
        )
    assert result["state"] == "持仓观察"
    assert "T+1" in result["transition_reason"]
