"""中线关键价 mid_key_prices 单测（周线引擎 weekly_v1）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.mid_key_prices import build_mid_key_prices  # noqa: E402


def _bar(i: int, close: float) -> dict:
    return {
        "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
        "open": close,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": 1000 + i,
    }


def _weekly(n: int = 40, base: float = 50.0) -> list[dict]:
    out = []
    p = base
    for i in range(n):
        if i % 7 == 3:
            c = p * 0.96
        elif i % 5 == 0:
            c = p * 1.03
        else:
            c = p * (1.005 if i % 2 == 0 else 0.998)
        out.append(_bar(i, c))
        p = c
    return out


_CHAN = {
    "chanlun": {
        "timeframe": "weekly",
        "strokes": [
            {"direction": "up", "end_price": 55.0},
            {"direction": "down", "end_price": 48.0},
            {"direction": "up", "end_price": 62.0},
            {"direction": "down", "end_price": 52.5},
        ],
        "segments": [
            {"direction": "up", "high": 55.0, "low": 40.0},
            {"direction": "down", "high": 55.0, "low": 48.0},
            {"direction": "up", "high": 62.0, "low": 48.0},
        ],
        "zones": [
            {"valid": True, "zh_bottom": 51.0, "zh_top": 58.0, "zh_center": 54.5},
        ],
    }
}


class TestMidKeyPricesWeekly:
    def test_basic_structure_source(self):
        mk = build_mid_key_prices(
            current=58.7,
            weekly_bars=_weekly(40),
            chanlun_midline=_CHAN,
        )
        assert mk["engine"] == "weekly_v1"
        assert mk["source"] == "weekly_structure"
        assert mk["life_line"] == pytest.approx(51.0)
        assert mk["components"]["life_line"] == "zone_zh_bottom"
        assert "破则中线转弱" in mk["line_life"]
        assert "到了才谈低吸" in mk["line_pullback"]
        assert "daily_key_levels_proxy" not in mk["notes"]
        assert "source=weekly_structure" in mk["notes"]

    def test_default_ignores_daily_key_levels(self):
        mk = build_mid_key_prices(
            current=58.7,
            weekly_bars=_weekly(40),
            chanlun_midline=_CHAN,
            key_levels={
                "short_support": 54.15,
                "mid_support": 46.88,
                "mid_resist": 69.67,
                "long_resist": 75.0,
            },
            ma20=56.72,
            stop=55.51,
        )
        # 不得等于日线 mid_support
        assert mk["life_line"] != pytest.approx(46.88)
        assert mk["life_line"] == pytest.approx(51.0)
        assert "daily_key_levels_proxy" not in mk["notes"]

    def test_omit_life_when_insufficient(self):
        mk = build_mid_key_prices(current=10, weekly_bars=[], chanlun_midline={})
        assert mk["life_line"] is None
        assert mk["line_life"] == ""
        assert mk["quality"] == "insufficient"

    def test_merge_resist_target(self):
        mk = build_mid_key_prices(
            current=58.0,
            weekly_bars=_weekly(40),
            chanlun_midline=_CHAN,
        )
        # up stroke end == up seg high == 62
        assert mk["merge_resist_target"] is True
        assert "压力/目标" in mk["line_resist"]
        assert mk["line_target"] == ""

    def test_swing_only_when_no_chan(self):
        mk = build_mid_key_prices(
            current=55.0,
            weekly_bars=_weekly(40),
            chanlun_midline=None,
        )
        assert mk["source"] == "weekly_swing_only"
        assert mk["quality"] == "partial"
        assert mk["engine"] == "weekly_v1"
        assert mk["life_line"] is not None

    def test_degraded_daily_when_flag_and_no_weekly(self, monkeypatch):
        monkeypatch.setenv("MIDLINE_PRICE_DAILY_FALLBACK", "true")
        mk = build_mid_key_prices(
            current=58.7,
            weekly_bars=[],
            key_levels={
                "short_support": 54.15,
                "mid_support": 46.88,
                "mid_resist": 69.67,
                "long_resist": 75.0,
            },
            ma20=56.72,
            stop=55.51,
        )
        assert mk["life_line"] == pytest.approx(46.88)
        assert mk["source"] == "degraded_daily_key_levels"
        assert "degraded_daily_key_levels" in mk["notes"]
        assert "daily_key_levels_proxy" not in mk["notes"]

    def test_degraded_stage_stop_fallback(self, monkeypatch):
        monkeypatch.setenv("MIDLINE_PRICE_DAILY_FALLBACK", "true")
        mk = build_mid_key_prices(
            current=10,
            weekly_bars=_weekly(5),  # too short
            key_levels={"short_support": 9.0, "mid_support": 0, "mid_resist": 12, "long_resist": 13},
            stop_losses={"stage_based": {"price": 8.5}},
            stop=8.0,
        )
        assert mk["life_line"] == pytest.approx(8.5)
        assert "life=stage_based" in mk["notes"]
        assert mk["source"] == "degraded_daily_key_levels"

    def test_pullback_single_point_structure(self):
        chan = {
            "timeframe": "weekly",
            "strokes": [
                {"direction": "down", "end_price": 48.0},
                {"direction": "up", "end_price": 55.0},
            ],
            "segments": [
                {"direction": "up", "high": 55.0, "low": 48.0},
            ],
            "zones": [],
        }
        # 构造 closes 使 MA20 也贴近 48（用平稳 bars）
        bars = [_bar(i, 48.0) for i in range(40)]
        mk = build_mid_key_prices(current=50.0, weekly_bars=bars, chanlun_midline=chan)
        assert mk["pullback_low"] == pytest.approx(48.0)
        assert mk["pullback_high"] == pytest.approx(48.0)
        assert "回踩区 48.00" in mk["line_pullback"]
