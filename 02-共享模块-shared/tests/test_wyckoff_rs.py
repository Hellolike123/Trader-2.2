"""Wyckoff 周线 RS 置信修正测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from trader_shared.market_env import resolve_board_index
from trader_shared.wyckoff_rs import (
    apply_rs_confidence_to_phase,
    compute_and_apply_weekly_rs,
    compute_wyckoff_rs,
)


def _weekly_closes(closes: list[float]) -> list[dict]:
    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "date": f"2024-{i + 1:02d}-01",
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": 1000,
        })
    return bars


class TestComputeWyckoffRs:
    def test_r1_stock_plus8_index_plus2_is_strong(self):
        """R1：6 周窗个股 +8%、科创50 +2% → strong；score=0.75；delta>0。"""
        # lookback=6 → 用 closes[0] 与 closes[6]；中间价任意
        stock = _weekly_closes([100.0, 101, 102, 103, 104, 105, 108.0])
        index = _weekly_closes([100.0, 100.5, 101, 101.5, 101.8, 101.9, 102.0])
        rs = compute_wyckoff_rs(
            stock, index, index_code="000688.SH", index_label="科创", lookback_weeks=6
        )
        assert rs["rs_index"] == "000688.SH"
        assert rs["rs_stock_return"] == pytest.approx(0.08, abs=1e-4)
        assert rs["rs_index_return"] == pytest.approx(0.02, abs=1e-4)
        assert rs["rs_relative_return"] == pytest.approx(0.06, abs=1e-4)
        assert rs["rs_score"] == pytest.approx(0.75, abs=1e-4)  # 0.06 / 0.08
        assert rs["rs_label"] == "strong"
        assert rs["rs_confidence_delta"] > 0
        assert "强于科创" in rs["rs_note"]

    def test_strong_rs(self):
        stock = _weekly_closes([100, 102, 104, 106, 108, 110, 115])
        index = _weekly_closes([100, 101, 102, 103, 104, 105, 106])
        rs = compute_wyckoff_rs(stock, index, index_code="399006.SZ", index_label="创业板")
        assert rs["rs_label"] == "strong"
        assert rs["rs_score"] > 0.25
        assert rs["rs_confidence_delta"] > 0
        assert "强于创业板" in rs["rs_note"]

    def test_weak_rs(self):
        stock = _weekly_closes([100, 99, 98, 97, 96, 95, 94])
        index = _weekly_closes([100, 101, 102, 103, 104, 105, 106])
        rs = compute_wyckoff_rs(stock, index, index_code="399001.SZ", index_label="深成")
        assert rs["rs_label"] == "weak"
        assert rs["rs_score"] < -0.25
        assert rs["rs_confidence_delta"] < 0
        assert "弱于深成" in rs["rs_note"]

    def test_missing_index_is_neutral(self):
        stock = _weekly_closes([100, 102, 104, 106, 108, 110, 112])
        rs = compute_wyckoff_rs(stock, [], index_code="000688.SH", index_label="科创")
        assert rs["rs_label"] == "neutral"
        assert rs["rs_score"] is None
        assert rs["rs_confidence_delta"] == 0.0
        assert rs["rs_gate"] == "missing"
        assert rs["rs_note"] == "数据不足"


class TestResolveBoardIndex:
    @pytest.mark.parametrize(
        "code,expected_code,expected_label",
        [
            ("688248", "000688.SH", "科创"),
            ("300750", "399006.SZ", "创业板"),
            ("600519", "000001.SH", "上证"),
            ("000001", "399001.SZ", "深成"),
            ("002594", "399001.SZ", "深成"),
        ],
    )
    def test_board_index_mapping(self, code, expected_code, expected_label):
        idx, label = resolve_board_index(code)
        assert idx == expected_code
        assert label == expected_label


class TestRsDoesNotLiftPhase:
    def test_strong_rs_keeps_phase_none(self):
        from trader_shared.wyckoff_core import wyckoff_analysis

        stock = _weekly_closes([100] * 8 + [110, 115, 120, 125, 130, 135, 140])
        index = _weekly_closes([100] * 8 + [100, 101, 102, 103, 104, 105, 106])

        with patch("trader_shared.wyckoff_core._detect_phase") as mock_phase:
            mock_phase.return_value = {
                "phase": "none",
                "phase_label": "无明确阶段",
                "phase_confidence_delta": 0.0,
                "spring_premature": False,
                "upthrust_premature": False,
                "phase_tr_gated": False,
            }
            result = wyckoff_analysis(
                stock,
                symbol="688248",
                timeframe="weekly",
                use_persisted_phase=False,
                index_weekly_bars=index,
            )

        assert result["phase"] == "none"
        assert result["rs_label"] == "strong"
        assert result["phase_confidence_delta"] > 0

    def test_strong_rs_keeps_gated_phase_none(self):
        from trader_shared.wyckoff_core import wyckoff_analysis

        stock = _weekly_closes([100] * 8 + [110, 115, 120, 125, 130, 135, 140])
        index = _weekly_closes([100] * 8 + [100, 101, 102, 103, 104, 105, 106])

        with patch("trader_shared.wyckoff_core._detect_phase") as mock_phase:
            mock_phase.return_value = {
                "phase": "none",
                "phase_label": "无明确阶段",
                "phase_confidence_delta": 0.0,
                "spring_premature": False,
                "upthrust_premature": False,
                "phase_tr_gated": True,
            }
            result = wyckoff_analysis(
                stock,
                symbol="688248",
                timeframe="weekly",
                use_persisted_phase=False,
                index_weekly_bars=index,
            )

        assert result["phase"] == "none"
        assert result["phase_tr_gated"] is True
        assert result["rs_label"] == "strong"
        assert result["phase_confidence_delta"] == 0.0


class TestRsConfidenceDirection:
    def test_apply_rs_increases_delta_when_strong(self):
        rs = {
            "rs_label": "strong",
            "rs_confidence_delta": 0.05,
        }
        phase = {"phase": "accumulation_c", "phase_label": "积累C", "phase_confidence_delta": 0.10}
        out = apply_rs_confidence_to_phase(phase, rs)
        assert out["phase"] == "accumulation_c"
        assert out["phase_confidence_delta"] > 0.10

    def test_apply_rs_decreases_delta_when_weak(self):
        rs = {
            "rs_label": "weak",
            "rs_confidence_delta": -0.05,
        }
        phase = {"phase": "accumulation_c", "phase_label": "积累C", "phase_confidence_delta": 0.10}
        out = apply_rs_confidence_to_phase(phase, rs)
        assert out["phase_confidence_delta"] < 0.10

    def test_weak_rs_spring_extra_penalty(self):
        rs = {
            "rs_label": "weak",
            "rs_confidence_delta": -0.05,
        }
        phase = {
            "phase": "none",
            "phase_label": "无",
            "phase_confidence_delta": 0.0,
            "spring_premature": True,
        }
        signals = {"spring_signal": True}
        out = apply_rs_confidence_to_phase(phase, rs, signals)
        assert out["phase_confidence_delta"] < -0.05


class TestWeeklyRsIntegration:
    def test_compute_and_apply_weekly_rs(self):
        stock = _weekly_closes([100] * 8 + [110, 115, 120, 125, 130, 135, 140])
        index = _weekly_closes([100] * 8 + [100, 101, 102, 103, 104, 105, 106])
        phase = {"phase": "accumulation_b", "phase_label": "积累B", "phase_confidence_delta": 0.08}
        signals = {"spring_signal": False}

        new_phase, rs = compute_and_apply_weekly_rs(
            stock, phase, signals, "688248", index_weekly_bars=index
        )
        assert rs["rs_index"] == "000688.SH"
        assert rs["rs_label"] == "strong"
        assert new_phase["phase"] == "accumulation_b"
        assert new_phase["phase_confidence_delta"] > phase["phase_confidence_delta"]

    def test_daily_analysis_skips_rs_fields_default(self):
        from trader_shared.wyckoff_core import wyckoff_analysis

        bars = _weekly_closes([100] * 20)
        result = wyckoff_analysis(bars, symbol="688248", timeframe="daily", use_persisted_phase=False)
        assert result.get("rs_label", "neutral") == "neutral"
        assert result.get("rs_confidence_delta", 0.0) == 0.0
        assert result.get("rs_gate") == "disabled"
        assert "日线" in (result.get("rs_note") or "")


class TestRsGatedAndPremature:
    def test_strong_rs_capped_when_spring_premature(self):
        rs = {"rs_label": "strong", "rs_confidence_delta": 0.06}
        phase = {
            "phase": "none",
            "phase_label": "无",
            "phase_confidence_delta": 0.0,
            "spring_premature": True,
        }
        out = apply_rs_confidence_to_phase(phase, rs, {"spring_signal": True})
        assert out["phase"] == "none"
        assert out["spring_premature"] is True
        assert out["phase_confidence_delta"] <= 0.02

    def test_strong_rs_no_boost_when_phase_tr_gated(self):
        rs = {"rs_label": "strong", "rs_confidence_delta": 0.06}
        phase = {
            "phase": "none",
            "phase_label": "无",
            "phase_confidence_delta": 0.0,
            "phase_tr_gated": True,
        }
        out = apply_rs_confidence_to_phase(phase, rs)
        assert out["phase"] == "none"
        assert out["phase_tr_gated"] is True
        assert out["phase_confidence_delta"] == 0.0


class TestRsEnabledSwitch:
    def test_disabled_returns_gate_disabled(self, monkeypatch):
        monkeypatch.setattr("trader_shared.wyckoff_rs.WYCKOFF_RS_ENABLED", False)
        stock = _weekly_closes([100] * 8 + [110, 115, 120, 125, 130, 135, 140])
        index = _weekly_closes([100] * 8 + [100, 101, 102, 103, 104, 105, 106])
        phase = {"phase": "none", "phase_label": "无", "phase_confidence_delta": 0.0}
        new_phase, rs = compute_and_apply_weekly_rs(
            stock, phase, {}, "688248", index_weekly_bars=index
        )
        assert rs["rs_gate"] == "disabled"
        assert new_phase["phase_confidence_delta"] == 0.0

    def test_disabled_in_wyckoff_analysis(self, monkeypatch):
        from trader_shared.wyckoff_core import wyckoff_analysis

        monkeypatch.setattr("trader_shared.wyckoff_rs.WYCKOFF_RS_ENABLED", False)
        stock = _weekly_closes([100] * 20)
        with patch("trader_shared.wyckoff_core._detect_phase") as mock_phase:
            mock_phase.return_value = {
                "phase": "accumulation_b",
                "phase_label": "积累B",
                "phase_confidence_delta": 0.08,
                "spring_premature": False,
                "upthrust_premature": False,
                "phase_tr_gated": False,
            }
            result = wyckoff_analysis(
                stock,
                symbol="688248",
                timeframe="weekly",
                use_persisted_phase=False,
            )
        assert result["rs_gate"] == "disabled"
        assert result["phase_confidence_delta"] == 0.08
