"""展示兜底：现价反向离开末笔终点时，禁止「拉升趋势中」假有。"""
from __future__ import annotations

from trader_shared.conclusion_block import _build_wave_label, _stroke_tip_left_against


def _chan(*, direction: str, end_price: float, trend: str = "拉升段", segs: int = 0) -> dict:
    strokes = [
        {"direction": "down", "end_price": end_price * 0.8, "start_price": end_price},
        {"direction": "up", "end_price": end_price * 0.9, "start_price": end_price * 0.8},
        {"direction": direction, "end_price": end_price, "start_price": end_price * 0.9},
    ]
    segments = (
        [{"direction": "up"}, {"direction": "down"}, {"direction": "up"}]
        if segs >= 2
        else ([{"direction": "up"}] if segs == 1 else [])
    )
    return {
        "strokes": strokes,
        "segments": segments,
        "trend_label": trend,
        "structure_type": "上涨趋势",
        "buy_points": [],
        "sell_points": [],
        "divergence": {},
        "merged_zones": [],
    }


def test_tip_left_detects_up_stroke_crash():
    strokes = [{"direction": "up", "end_price": 187.0}]
    assert _stroke_tip_left_against(strokes, 95.0) == "up_left"
    assert _stroke_tip_left_against(strokes, 180.0) == ""


def test_wave_label_demotes_rally_when_price_left_tip():
    chan = _chan(direction="up", end_price=187.0, trend="拉升段", segs=1)
    label = _build_wave_label(chan, current=95.0)
    assert "拉升趋势中" not in label
    assert "高点已离开" in label


def test_wave_label_keeps_rally_when_price_near_tip():
    chan = _chan(direction="up", end_price=100.0, trend="拉升段", segs=1)
    label = _build_wave_label(chan, current=98.0)
    assert "拉升趋势中" in label or "拉升" in label
    assert "高点已离开" not in label
