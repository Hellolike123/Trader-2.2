"""P0 分析意见卡契约测试 A-01～A-06。

docs/designs/analysis-opinion-cards.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.analysis_cards import (  # noqa: E402
    assert_card_numeric_finite,
    build_chan_card,
    build_chip_card,
    build_momentum_card,
    build_vpf_card,
    build_wyckoff_card,
)


def test_a01_wyckoff_weekly_no_tr_honest_summary():
    """A-01: 周线已算但无 TR/无事件 → 人话含已算/定不出，非静默空。"""
    raw = {
        "timeframe": "weekly",
        "phase": "none",
        "phase_label": "无明确阶段",
        "wyckoff_summary": "无明显威科夫信号",
        "tr_quality": None,
        "tr_upper": None,
        "tr_lower": None,
        "spring_signal": False,
    }
    card = build_wyckoff_card(raw, role="midline")
    assert card["schema_version"] == "wyckoff_card_v1"
    assert card["status"] == "none"
    assert card["tr_ok"] is False
    line = card["summary_line"]
    assert "威科夫" in line
    assert any(k in line for k in ("已算", "定不出", "暂无", "不据此"))
    assert_card_numeric_finite(card)


def test_a02_wyckoff_spring_event_card():
    """A-02: Spring 事件卡非空，灯在 summary。"""
    raw = {
        "spring_signal": True,
        "spring_vol_class": "low_vol_confirm",
        "timeframe": "daily",
        "phase_label": "积累期 C（测试：Spring）",
    }
    card = build_wyckoff_card(raw, role="daily")
    assert card["status"] == "event"
    assert card["event_code"] == "Spring"
    assert "弹簧" in card["event_cn"] or card["event_cn"]
    assert "Spring" in card["summary_line"] or "弹簧" in card["summary_line"]
    assert card["direction"] in (-1, 0, 1)
    assert_card_numeric_finite(card)


def test_a03_chan_buy1_type_first():
    """A-03: 一类买 → type_short 一买，summary 类型优先。"""
    chan = {
        "chanlun": {
            "buy_points": [{"type": "一类买", "price": 10.0}],
            "sell_points": [],
            "divergence": {"bottom_divergence": True},
            "trend_label": "上涨",
        }
    }
    card = build_chan_card(chan, role="daily")
    assert card["schema_version"] == "chan_card_v1"
    assert card["type_short"] == "一买" or card["type_raw"] == "一类买"
    assert "一买" in card["summary_line"] or "一类买" in card["summary_line"]
    assert card["direction"] == 1
    assert_card_numeric_finite(card)


def test_a03b_chan_does_not_infer_from_fusion_reason():
    """C-D3c：引擎无点时禁止从 fusion.reason 手补一买。"""
    card = build_chan_card(
        {},
        fusion_chan={"reason": "缠论一类买 (底背驰)", "direction": 1},
    )
    assert card.get("status") != "point"
    assert card.get("type_short") not in ("一买", "一类买")
    assert "一买" not in str(card.get("summary_line") or "")
    assert "一类买" not in str(card.get("summary_line") or "")


def test_a04_chip_no_peaks_no_pct_empty():
    """A-04: 无峰无 pct → has_data False，summary 空。"""
    card = build_chip_card(40.0, [], None, None)
    assert card["schema_version"] == "chip_card_v1"
    assert card["has_data"] is False
    assert card["summary_line"] == ""
    assert_card_numeric_finite(card)


def test_a05_chip_price_below_all_peaks_scheme_c():
    """A-05: 跌穿成本区 → 支撑弱 · 阻力 · 套牢面大。"""
    card = build_chip_card(
        41.63,
        [
            {"price": 44.4, "share_of_total": 5},
            {"price": 50.4, "share_of_total": 15},
        ],
        {"has_history": True, "warning_level": "none", "migration_pct": 0},
        9.0,
    )
    assert card["has_data"] is True
    assert "支撑弱" in card["support_tag"] or "支撑弱" in card["summary_line"]
    assert card["resist_px"] == pytest.approx(44.4)
    assert "套牢面大" in card["trapped_tag"] or "套牢面大" in card["summary_line"]
    assert card["summary_line"].startswith("筹码：")
    assert " · " in card["summary_line"]
    assert_card_numeric_finite(card)


def test_a06_all_cards_numeric_finite():
    """A-06: 各卡数值有限。"""
    cards = [
        build_wyckoff_card({"sos_signal": True, "timeframe": "daily"}),
        build_chan_card({"chanlun": {"buy_points": [], "sell_points": [{"type": "一类卖"}], "divergence": {}, "trend_label": "下跌"}}),
        build_momentum_card({"direction": 1, "confidence": 0.5, "reason": "动量偏多"}),
        build_vpf_card({"direction": -1, "confidence": 0.4, "reason": "流出", "fund_direction": -1, "vp_direction": 0}),
        build_chip_card(10.0, [{"price": 9.0}, {"price": 11.0}], None, 50.0),
    ]
    for c in cards:
        assert_card_numeric_finite(c)
        assert "schema_version" in c
        assert "source" in c


def test_momentum_and_vpf_card_shape():
    m = build_momentum_card({"momentum": {"direction": 0, "confidence": 0.2, "reason": "中性", "strength": "neutral"}})
    assert m["direction"] == 0
    assert 0.0 <= m["confidence"] <= 1.0
    v = build_vpf_card({
        "direction": 1,
        "confidence": 0.55,
        "reason": "主力连2日",
        "fund_direction": 1,
        "vp_direction": -1,
        "warning_type": "climactic",
        "fund_quality": "full",
    })
    assert v["fund_direction"] == 1
    assert v["vp_direction"] == -1
    assert v["warning_type"] == "climactic"


def test_p_l_failed_phase_label_sanitized_on_card():
    """P-L1/P-L2/P-L4/M-L1：failed card 可见 phase_label/main 无「Phase A 失败」。"""
    raw = {
        "phase": "none",
        "phase_label": "无明确阶段（Phase A 失败，破位未收回）",
        "phase_a_status": "failed",
        "phase_tr_gated": True,
        "phase_tr_gate_reason": "phase_a_failed",
        "sc_signal": True,
        "sc_price": 10.0,
        "timeframe": "daily",
        "tr_maturity": "L0",
        "box_display_mode": "none",
        "measure_allowed": False,
    }
    card = build_wyckoff_card(raw, role="daily")
    label = card["phase_label"]
    assert label == "无明确阶段（Phase A 失效，破位未收回）"
    assert "Phase A 失效" in label
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in label
        assert bad not in str(card.get("main") or "")
        assert bad not in str(card.get("note") or "")
    assert "Phase A 失效" in str(card.get("main") or "")
    assert_card_numeric_finite(card)
