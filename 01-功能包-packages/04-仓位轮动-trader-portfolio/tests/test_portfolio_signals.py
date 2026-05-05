#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACTS = ROOT.parents[1] / "02-共享模块-shared" / "03-输出校验-contracts"
CANDIDATE = ROOT.parents[1] / "02-共享模块-shared" / "02-候选逻辑-candidate"
MARKET = ROOT.parents[1] / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_SCRIPTS = ROOT.parents[1] / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
for _p in (SCRIPTS, CONTRACTS, CANDIDATE, MARKET, SHARED_SCRIPTS, SHARED_ROOT):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
for name in ("config", "light_data", "signal_store", "models", "pipeline", "signal_contract", "signal_tracker", "candidate_core", "candidate_model"):
    sys.modules.pop(name, None)

from portfolio_run import render_markdown


def _fake_item(symbol: str, name: str, status: str) -> dict:
    return {
        "ok": True,
        "symbol": symbol,
        "name": name,
        "status": status,
        "atr14": 1.5,
        "atr_ratio": 0.015,
        "livermore_tier": 3,
        "buy_low": 55.0,
        "buy_high": 56.5,
        "defense": 57.0,
        "stop": 54.0,
        "take": 58.0,
    }


def test_portfolio_markdown_includes_stocks():
    items = [
        _fake_item("688248.SH", "南网科技", "优先候选"),
        _fake_item("601600.SH", "中国铝业", "等转强"),
    ]
    result = render_markdown(items)
    assert "南网科技" in result
    assert "中国铝业" in result
    assert "轮动仓位" in result
    assert "止损" in result
    assert "关键价位" in result


def test_portfolio_markdown_includes_positions():
    items = [
        _fake_item("688248.SH", "南网科技", "低吸观察"),
        _fake_item("601600.SH", "中国铝业", "防守观察"),
    ]
    result = render_markdown(items)
    assert "主仓" in result
    assert "副仓" in result
    assert "现金" in result
    assert "加仓" in result or "建仓" in result


def test_portfolio_markdown_includes_conclusion():
    items = [
        _fake_item("688248.SH", "南网科技", "优先候选"),
        _fake_item("601600.SH", "中国铝业", "等转强"),
    ]
    result = render_markdown(items)
    assert "结论" in result or "当前仓位" in result
    assert "仓位" in result
