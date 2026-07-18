"""Arch C：fusion 从 analysis_cards 取三席。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.fusion_card_signals import (  # noqa: E402
    chan_card_to_fusion_signal,
    fusion_signals_from_cards,
    momentum_card_to_fusion_signal,
    vpf_card_to_fusion_signal,
)
from trader_shared.fusion_core import merge_decisions  # noqa: E402


def test_chan_card_buy1_signal():
    sig = chan_card_to_fusion_signal({
        "type_short": "一买",
        "type_raw": "一类买",
        "direction": 1,
        "summary_line": "一买 · 底背驰 · 看涨",
        "same_level": True,
        "raw_available": True,
    })
    assert sig["direction"] == 1
    assert sig["confidence"] >= 0.7
    assert sig.get("from_card") is True
    assert "chan_buy_1" in str(sig.get("signal_tier") or "")


def test_fusion_signals_from_cards_bundle():
    cards = {
        "chan": {"type_short": "一买", "direction": 1, "raw_available": True, "summary_line": "一买"},
        "momentum": {"direction": 0, "confidence": 0.2, "reason": "中性", "raw_available": True},
        "vpf": {"direction": -1, "confidence": 0.4, "reason": "流出", "raw_available": True, "fund_quality": "full"},
    }
    bundle = fusion_signals_from_cards(cards)
    assert bundle is not None
    assert bundle["chan"]["direction"] == 1
    assert bundle["vpf"]["direction"] == -1


def test_merge_decisions_cards_path(monkeypatch):
    monkeypatch.setenv("FUSION_FROM_CARDS", "cards")
    cards = {
        "chan": {
            "type_short": "一买",
            "type_raw": "一类买",
            "direction": 1,
            "summary_line": "一买",
            "raw_available": True,
            "same_level": True,
        },
        "momentum": {"direction": 1, "confidence": 0.5, "reason": "动量偏多", "raw_available": True},
        "vpf": {
            "direction": 1,
            "confidence": 0.3,
            "reason": "中性偏多",
            "raw_available": True,
            "fund_quality": "missing",
        },
    }
    # classic 输入故意给空结构，cards 路径应仍能产出
    out = merge_decisions(
        chan_result={"chanlun": {"buy_points": [], "sell_points": [], "divergence": {}, "trend_label": ""}},
        momentum_result={"momentum": {"score": 50, "direction": "neutral"}},
        regime="正常",
        analysis_cards=cards,
        fusion_from_cards="cards",
    )
    assert out.get("fusion_input_path") == "cards"
    assert out["signals_detail"]["chan"].get("from_card") is True
    assert out["signals_detail"]["chan"]["direction"] == 1


def test_merge_decisions_classic_path(monkeypatch):
    monkeypatch.setenv("FUSION_FROM_CARDS", "classic")
    out = merge_decisions(
        chan_result={
            "chanlun": {
                "buy_points": [{"type": "一类买", "price": 10, "confidence": 3}],
                "sell_points": [],
                "divergence": {"bottom_divergence": True},
                "trend_label": "上涨",
            }
        },
        momentum_result={"momentum": {"score": 60, "direction": "bullish"}},
        regime="正常",
        analysis_cards={
            "chan": {"type_short": "一卖", "direction": -1, "raw_available": True},  # 若误用卡会看空
        },
        fusion_from_cards="classic",
    )
    assert out.get("fusion_input_path") == "classic"
    # classic 应看多（一类买），不应被错误卡带偏
    assert out["signals_detail"]["chan"]["direction"] == 1
    assert out["signals_detail"]["chan"].get("from_card") is not True


def test_merge_compare_attaches_fusion_compare(monkeypatch):
    monkeypatch.setenv("FUSION_FROM_CARDS", "compare")
    cards = {
        "chan": {"type_short": "一买", "direction": 1, "raw_available": True, "summary_line": "一买", "type_raw": "一类买"},
        "momentum": {"direction": 0, "confidence": 0.2, "reason": "中性", "raw_available": True},
        "vpf": {"direction": 0, "confidence": 0.2, "reason": "中性", "raw_available": True},
    }
    out = merge_decisions(
        chan_result={"chanlun": {"buy_points": [], "sell_points": [], "divergence": {}, "trend_label": "盘整"}},
        momentum_result={"momentum": {"score": 50, "direction": "neutral"}},
        regime="正常",
        analysis_cards=cards,
        fusion_from_cards="compare",
    )
    assert out.get("fusion_input_path") == "cards"
    assert "fusion_compare" in out
    assert "classic" in out["fusion_compare"]
    assert "cards" in out["fusion_compare"]
