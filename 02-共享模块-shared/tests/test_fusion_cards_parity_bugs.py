"""回归：Agent 裁定 I1–I10（动量卡契约 / 缠论卡 / strategy cost_price）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.analysis.cards import build_chan_card, build_momentum_card  # noqa: E402
from trader_shared.analysis.fusion_card_signals import (  # noqa: E402
    chan_card_to_fusion_signal,
    fusion_signals_from_cards,
    momentum_card_to_fusion_signal,
    vpf_card_to_fusion_signal,
)
from trader_shared.fusion_core import _fusion_input_mode, _momentum_to_signal, merge_decisions  # noqa: E402
from trader_shared.strategy_match import build_match_context, match_strategies  # noqa: E402


def test_i1_momentum_card_production_shape_bullish():
    """I1: 真实 assess_momentum 形态 direction 字符串 + score → 非零席。"""
    raw = {
        "momentum": {
            "score": 72,
            "direction": "bullish",
            "signals": ["MACD金叉", "RSI偏强"],
            "strength": "strong",
        }
    }
    card = build_momentum_card(raw)
    assert card["direction"] == 1
    assert card["confidence"] > 0.3
    assert card["raw_available"] is True
    classic = _momentum_to_signal(raw)
    assert card["direction"] == classic["direction"]
    assert abs(card["confidence"] - classic["confidence"]) < 0.05

    sig = momentum_card_to_fusion_signal(card)
    assert sig["direction"] == 1
    assert sig["confidence"] > 0.3


def test_i1_momentum_card_bearish_score():
    card = build_momentum_card(
        {"momentum": {"score": 28, "direction": "bearish", "signals": ["量能萎缩"]}}
    )
    assert card["direction"] == -1
    assert card["confidence"] > 0.3


def test_i1_merge_cards_path_uses_live_momentum_shape(monkeypatch):
    monkeypatch.setenv("FUSION_FROM_CARDS", "cards")
    mom_raw = {"momentum": {"score": 72, "direction": "bullish", "signals": ["偏强"]}}
    cards = {
        "chan": {
            "type_short": "暂无买卖点",
            "type_raw": "暂无买卖点",
            "direction": 0,
            "raw_available": True,
            "summary_line": "中性",
        },
        "momentum": build_momentum_card(mom_raw),
        "vpf": {
            "direction": 0,
            "confidence": 0.2,
            "reason": "中性",
            "raw_available": True,
        },
    }
    out = merge_decisions(
        chan_result={"chanlun": {"buy_points": [], "sell_points": [], "divergence": {}, "trend_label": ""}},
        momentum_result=mom_raw,
        regime="正常",
        analysis_cards=cards,
        fusion_from_cards="cards",
    )
    assert out.get("fusion_input_path") == "cards"
    mom_sig = out["signals_detail"]["momentum"]
    assert mom_sig["direction"] == 1
    assert mom_sig["confidence"] > 0.3


def test_default_fusion_mode_is_cards(monkeypatch):
    monkeypatch.delenv("FUSION_FROM_CARDS", raising=False)
    assert _fusion_input_mode() == "cards"


def test_fusion_mode_classic_explicit(monkeypatch):
    monkeypatch.setenv("FUSION_FROM_CARDS", "classic")
    assert _fusion_input_mode() == "classic"


def test_i4_like2_not_buy2():
    """I4: 类二买 不得 命中 二买 子串。"""
    sig = chan_card_to_fusion_signal({
        "type_short": "类二买",
        "type_raw": "类二买",
        "direction": 1,
        "raw_available": True,
        "summary_line": "类二买 · 回踩偏弱",
    })
    assert sig["direction"] == 1
    assert "like2" in str(sig.get("signal_tier") or "").lower() or "LIKE2" in str(sig.get("signal_tier") or "")
    assert sig["confidence"] <= 0.4


def test_i2_i3_nesting_and_point_conf_on_card():
    """I2/I3: 卡携带 nesting + point conf，fusion 降权。"""
    chan = {
        "chanlun": {
            "buy_points": [{
                "type": "一类买",
                "price": 10.0,
                "confidence": 3,
                "lower_confirmed": False,
                "nesting_confirmed": False,
            }],
            "sell_points": [],
            "divergence": {},
            "trend_label": "上涨",
        }
    }
    card = build_chan_card(chan)
    assert card.get("point_confidence") == 3
    assert card.get("nesting_confirmed") is False
    full = chan_card_to_fusion_signal({
        **card,
        "nesting_confirmed": True,  # 对照满置信
        "lower_confirmed": True,
        "point_confidence": 3,
    })
    demoted = chan_card_to_fusion_signal(card)
    assert demoted["confidence"] < full["confidence"]
    assert demoted["confidence"] <= 0.8 * 0.55 + 0.01


def test_i5_callback_trend_direction():
    """I5: 回调段 resolve → direction -1，卡→fusion 有空向。"""
    from trader_shared.chan_core import resolve_chanlun_primary

    info = resolve_chanlun_primary({
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "回调段",
            "structure_type": "盘整",
        }
    })
    assert info["direction"] == -1
    card = build_chan_card({
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "回调段",
            "structure_type": "盘整",
        }
    })
    assert card["direction"] == -1
    sig = chan_card_to_fusion_signal(card)
    assert sig["direction"] == -1
    assert sig["confidence"] >= 0.35


def test_i6_empty_cards_do_not_activate_path():
    """I6: 仅 direction:0 的空卡不得激活 cards 路径。"""
    empty = {
        "chan": {"direction": 0, "raw_available": False, "summary_line": ""},
        "momentum": {"direction": 0, "raw_available": False},
        "vpf": {"direction": 0, "raw_available": False},
    }
    assert fusion_signals_from_cards(empty) is None


def test_i8_vpf_true_zero_confidence():
    sig = vpf_card_to_fusion_signal({
        "direction": 0,
        "confidence": 0.0,
        "reason": "中性",
        "raw_available": True,
    })
    assert sig["confidence"] == 0.0


def test_i9_cost_price_enables_manage_stage():
    """I9: 实盘 cost_price 应驱动 S2。"""
    ctx = build_match_context({
        "current": 11.0,
        "has_position": True,
        "cost_price": 10.0,
        "stop": 9.5,
        "support": 9.8,
    })
    assert ctx["cost"] == 10.0
    r = match_strategies({
        "current": 11.0,
        "has_position": True,
        "cost_price": 10.0,
        "stop": 9.5,
        "support": 9.8,
    })
    # pnl +10% → S2
    assert r["gates"]["manage"]["stage_id"] == "S2"


def test_i10_strategy_stop_not_looser_than_structure():
    """I10: trail 不得低于结构 hard stop（多头更松）。"""
    r = match_strategies({
        "current": 20.0,
        "has_position": True,
        "cost": 19.0,
        "support": 18.0,  # floor；减 buffer 后可能 < structure stop
        "stop": 17.8,  # 结构 hard stop
    })
    sp = r["gates"]["manage"]["stop_price"]
    assert sp is not None
    assert float(sp) >= 17.8
