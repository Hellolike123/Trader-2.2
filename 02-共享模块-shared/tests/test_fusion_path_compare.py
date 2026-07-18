"""fusion classic vs cards 对账纯逻辑（无网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.fusion_path_compare import (  # noqa: E402
    diff_snapshots,
    format_text_report,
    snapshot_from_fusion,
    summarize_batch,
)


def test_snapshot_and_stable():
    fus = {
        "fusion_input_path": "classic",
        "weighted_score": 0.12,
        "confidence": 0.5,
        "disagreement": 0.1,
        "action": "持股观望",
        "signals_detail": {
            "chan": {"direction": 1, "confidence": 0.4, "reason": "一买"},
            "momentum": {"direction": 1, "confidence": 0.5, "reason": "偏多"},
            "vpf": {"direction": 0, "confidence": 0.2, "reason": "中性"},
        },
    }
    a = snapshot_from_fusion(fus)
    b = snapshot_from_fusion({**fus, "fusion_input_path": "cards"})
    d = diff_snapshots(a, b)
    assert d["level"] == "stable"
    assert d["flags"] == []


def test_mom_silenced_unstable():
    classic = snapshot_from_fusion({
        "weighted_score": 0.2,
        "action": "增持",
        "signals_detail": {
            "chan": {"direction": 0, "confidence": 0.3},
            "momentum": {"direction": 1, "confidence": 0.6},
            "vpf": {"direction": 0, "confidence": 0.2},
        },
    })
    cards = snapshot_from_fusion({
        "weighted_score": 0.02,
        "action": "持股观望",
        "signals_detail": {
            "chan": {"direction": 0, "confidence": 0.3},
            "momentum": {"direction": 0, "confidence": 0.0},
            "vpf": {"direction": 0, "confidence": 0.2},
        },
    })
    d = diff_snapshots(classic, cards)
    assert d["level"] == "unstable"
    assert any("mom_silenced" in f for f in d["flags"])


def test_summarize_recommend_cards_when_all_stable():
    rows = [{"level": "stable"} for _ in range(5)]
    sm = summarize_batch(rows)
    assert sm["recommend"] == "consider_cards_default"
    text = format_text_report(
        [{"target": "1", "name": "A", "level": "stable", "score_classic": 0.1,
          "score_cards": 0.1, "score_delta": 0.0, "action_classic": "x", "action_cards": "x",
          "flags": []}],
        sm,
    )
    assert "建议" in text
