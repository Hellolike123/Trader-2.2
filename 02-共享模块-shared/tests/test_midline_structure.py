"""中线周线引擎 midline_structure 单测（M1/M2，规格 §9）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.midline_structure import (  # noqa: E402
    MIN_WEEKLY,
    SWING_N_LIFE,
    SWING_N_PULLBACK,
    SWING_N_TARGET,
    build_midline_levels,
    find_swing_levels,
)


def _bar(i: int, close: float, high: float | None = None, low: float | None = None) -> dict:
    c = close
    h = high if high is not None else c * 1.02
    lo = low if low is not None else c * 0.98
    return {
        "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
        "open": c,
        "high": h,
        "low": lo,
        "close": c,
        "volume": 1000 + i,
    }


def _weekly_bars_n(n: int, base: float = 50.0) -> list[dict]:
    """固定 fixture：温和上升后小幅回调，便于摆动可复现。"""
    out = []
    p = base
    for i in range(n):
        # 每 7 根一个局部低，每 5 根一个局部高
        if i % 7 == 3:
            c = p * 0.96
        elif i % 5 == 0:
            c = p * 1.03
        else:
            c = p * (1.005 if i % 2 == 0 else 0.998)
        out.append(_bar(i, c, high=max(p, c) * 1.01, low=min(p, c) * 0.99))
        p = c
    return out


# 固定笔段 fixture（timeframe=weekly）
_CHAN_WEEKLY_FULL = {
    "chanlun": {
        "timeframe": "weekly",
        "strokes": [
            {"direction": "up", "start_price": 40.0, "end_price": 55.0},
            {"direction": "down", "start_price": 55.0, "end_price": 48.0},
            {"direction": "up", "start_price": 48.0, "end_price": 62.0},
            {"direction": "down", "start_price": 62.0, "end_price": 52.5},
        ],
        "segments": [
            {"direction": "up", "high": 55.0, "low": 40.0, "start_price": 40.0, "end_price": 55.0},
            {"direction": "down", "high": 55.0, "low": 48.0, "start_price": 55.0, "end_price": 48.0},
            {"direction": "up", "high": 62.0, "low": 48.0, "start_price": 48.0, "end_price": 62.0},
        ],
        "zones": [
            {"valid": True, "zh_top": 54.0, "zh_bottom": 49.5, "zh_center": 51.75},
            {"valid": False, "zh_top": 60.0, "zh_bottom": 58.0, "zh_center": 59.0},
            {"valid": True, "zh_top": 58.0, "zh_bottom": 51.0, "zh_center": 54.5},
        ],
    }
}


class TestConstants:
    def test_frozen_constants(self):
        assert MIN_WEEKLY == 26
        assert SWING_N_LIFE == 20
        assert SWING_N_PULLBACK == 12
        assert SWING_N_TARGET == 40


class TestFindSwingLevels:
    def test_weekly_bars_fixed_fixture(self):
        bars = _weekly_bars_n(40, base=50.0)
        sw = find_swing_levels(bars)
        assert sw["life_support"] is not None and sw["life_support"] > 0
        assert sw["resist"] is not None and sw["resist"] > 0
        assert sw["target_resist"] is not None
        # 支撑应低于压力
        assert sw["life_support"] <= sw["resist"] + 1e-6

    def test_empty_bars(self):
        sw = find_swing_levels([])
        assert sw["life_support"] is None


class TestBuildMidlineLevels:
    def test_life_priority_up_seg_low(self):
        bars = _weekly_bars_n(40)
        r = build_midline_levels(
            current=58.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
        )
        # 最近 up seg low = 48.0
        assert r["life_line"] == pytest.approx(48.0)
        assert r["components"]["life_line"] == "seg_low"
        assert r["engine"] == "weekly_v1"
        assert r["source"] == "weekly_structure"
        assert r["quality"] == "full"
        assert "daily_key_levels_proxy" not in r["notes"]

    def test_life_priority_down_stroke_when_no_up_seg(self):
        bars = _weekly_bars_n(40)
        chan = {
            "timeframe": "weekly",
            "strokes": [
                {"direction": "up", "end_price": 60.0},
                {"direction": "down", "end_price": 47.2},
            ],
            "segments": [
                {"direction": "down", "high": 60.0, "low": 47.0},
            ],
            "zones": [],
        }
        r = build_midline_levels(current=50.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["life_line"] == pytest.approx(47.2)
        assert r["components"]["life_line"] == "last_down_stroke_end"

    def test_life_zone_zh_bottom_not_center(self):
        bars = _weekly_bars_n(40)
        chan = {
            "timeframe": "weekly",
            "strokes": [],
            "segments": [],
            "zones": [
                {"valid": True, "zh_bottom": 44.44, "zh_top": 50.0, "zh_center": 47.22},
            ],
            # 诱饵：若误用 center 会拿到 47.22
            "last_valid_zone_first_price": 47.22,
            "last_valid_zone_last_price": 47.22,
        }
        r = build_midline_levels(current=50.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["life_line"] == pytest.approx(44.44)
        assert r["components"]["life_line"] == "zone_zh_bottom"

    def test_non_weekly_timeframe_swing_only(self):
        bars = _weekly_bars_n(40)
        chan = {
            "chanlun": {
                "timeframe": "daily_fallback",
                "strokes": [
                    {"direction": "up", "end_price": 99.0},
                    {"direction": "down", "end_price": 11.0},
                ],
                "segments": [
                    {"direction": "up", "high": 99.0, "low": 11.0},
                ],
                "zones": [{"valid": True, "zh_bottom": 11.0, "zh_top": 20.0}],
            }
        }
        r = build_midline_levels(current=50.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["source"] == "weekly_swing_only"
        assert r["quality"] == "partial"
        # 不得使用 daily_fallback 笔段价 11.0 作 life
        assert r["life_line"] != pytest.approx(11.0)
        assert r["components"]["life_line"] == "weekly_swing_n20"

    def test_no_strokes_segments_swing_only(self):
        bars = _weekly_bars_n(40)
        chan = {"timeframe": "weekly", "strokes": [], "segments": [], "zones": []}
        r = build_midline_levels(current=50.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["source"] == "weekly_swing_only"
        assert r["quality"] == "partial"

    def test_swing_fallback_label_honest(self):
        # P0：单调上升无任何 2-touch 摆动 → 退化为区间最低/最高，
        # 标签须诚实标注 weekly_min_fallback / weekly_max_fallback，不得冒充周线摆动
        bars = []
        p = 50.0
        for i in range(40):
            p = p * 1.01
            bars.append(_bar(i, p, high=p * 1.01, low=p * 0.99))
        chan = {"timeframe": "weekly", "strokes": [], "segments": [], "zones": []}
        r = build_midline_levels(current=80.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["components"]["life_line"] == "weekly_min_fallback"
        assert r["components"]["pullback_low"] == "weekly_min_fallback"
        assert r["components"]["resist"] == "weekly_max_fallback"
        assert r["components"]["target"] == "weekly_max_fallback"

    def test_insufficient_too_short(self):
        bars = _weekly_bars_n(10)
        r = build_midline_levels(
            current=50.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
        )
        assert r["quality"] == "insufficient"
        assert r["life_line"] is None
        assert "weekly_too_short" in r["notes"]

    def test_weekly_missing(self):
        r = build_midline_levels(current=50.0, weekly_bars=[], chanlun_midline=_CHAN_WEEKLY_FULL)
        assert r["quality"] == "insufficient"
        assert "weekly_missing" in r["notes"]
        assert r["life_line"] is None

    def test_pullback_clamped_to_life(self):
        bars = _weekly_bars_n(40)
        # down stroke end 远低于 life(seg low=48)
        chan = {
            "timeframe": "weekly",
            "strokes": [
                {"direction": "up", "end_price": 62.0},
                {"direction": "down", "end_price": 40.0},  # 低于 life
            ],
            "segments": [
                {"direction": "up", "high": 62.0, "low": 48.0},
            ],
            "zones": [],
        }
        r = build_midline_levels(current=55.0, weekly_bars=bars, chanlun_midline=chan)
        assert r["life_line"] == pytest.approx(48.0)
        assert r["pullback_low"] == pytest.approx(48.0)  # 强制夹 life
        assert r["pullback_high"] >= r["pullback_low"]

    def test_resist_target_no_fib_from_structure(self):
        bars = _weekly_bars_n(40)
        r = build_midline_levels(
            current=58.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
        )
        # 最近 up stroke end = 62.0
        assert r["resist"] == pytest.approx(62.0)
        assert r["components"]["resist"] == "last_up_stroke_end"
        # 最近 up seg high = 62.0 → 合并
        assert r["target"] == pytest.approx(62.0)
        assert r["components"]["target"] == "seg_high"
        assert r["merge_resist_target"] is True
        assert "压力/目标" in r["line_resist"]

    def test_already_below_life(self):
        bars = _weekly_bars_n(40)
        r = build_midline_levels(
            current=40.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
        )
        assert "already_below_life" in r["notes"]

    def test_ignore_daily_key_levels_by_default(self):
        """E9：默认传入日线 key_levels 必须被忽略。"""
        bars = _weekly_bars_n(40)
        r = build_midline_levels(
            current=58.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
            key_levels={
                "mid_support": 1.11,
                "short_support": 2.22,
                "mid_resist": 3.33,
                "long_resist": 4.44,
            },
            stop=1.0,
            stop_losses={"stage_based": {"price": 0.5}},
        )
        assert r["life_line"] == pytest.approx(48.0)
        assert r["life_line"] != pytest.approx(1.11)
        assert "daily_key_levels_proxy" not in r["notes"]
        assert r["source"] == "weekly_structure"

    def test_display_lines_format(self):
        bars = _weekly_bars_n(40)
        r = build_midline_levels(
            current=58.0,
            weekly_bars=bars,
            chanlun_midline=_CHAN_WEEKLY_FULL,
        )
        assert "破则中线转弱" in r["line_life"]
        assert "到了才谈低吸" in r["line_pullback"]
        assert "🌟" not in r["line_life"]
