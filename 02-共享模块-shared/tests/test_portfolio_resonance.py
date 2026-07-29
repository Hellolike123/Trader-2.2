"""仓位轮动吃共振档（无网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trader_shared.portfolio_core as pc  # noqa: E402
from trader_shared.portfolio_core import enrich_portfolio_resonance, sort_candidates  # noqa: E402


def test_enrich_demotes_conflict_and_cuts_weight(monkeypatch):
    monkeypatch.setattr(
        pc,
        "_pool_resonance_index",
        lambda: {
            "冲突票": {"resonance_grade": "conflict", "resonance_summary": "共振：冲突"},
        },
    )
    items = enrich_portfolio_resonance(
        [
            {
                "ok": True,
                "name": "冲突票",
                "symbol": "688001.SH",
                "status": "低吸观察",
                "score": 80,
            }
        ]
    )
    assert items[0]["status"] == "防守观察"
    assert items[0]["resonance_weight"] == 0.5
    assert items[0]["resonance_grade"] == "conflict"


def test_enrich_aligned_boost(monkeypatch):
    monkeypatch.setattr(
        pc,
        "_pool_resonance_index",
        lambda: {"齐票": {"resonance_grade": "aligned", "resonance_summary": "共振：齐"}},
    )
    items = enrich_portfolio_resonance(
        [{"ok": True, "name": "齐票", "status": "等转强", "score": 50}]
    )
    assert items[0]["resonance_weight"] == 1.15
    assert items[0]["status"] == "等转强"


def test_sort_prefers_aligned_same_status():
    items = [
        {
            "ok": True,
            "name": "冲突",
            "status": "防守观察",
            "score": 90,
            "resonance_grade": "conflict",
        },
        {
            "ok": True,
            "name": "齐",
            "status": "防守观察",
            "score": 60,
            "resonance_grade": "aligned",
        },
    ]
    ordered = sort_candidates(items)
    assert ordered[0]["name"] == "齐"
