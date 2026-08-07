"""防回归：Bug R 修复后不得把高低点同步抬高/降低的震荡市乱切段。

对照 formulas.md §3.1：向上段特征序列（向下笔）须最后三根形成双侧底分型才终结；
仅高低点同步抬高时形不成底分型，1 段 up 是正确输出。
"""
from trader_shared.chan_geometry import build_segments


def _stroke(start_price, end_price, start_index, direction):
    return {
        "start_type": "bottom" if direction == "up" else "top",
        "end_type": "top" if direction == "up" else "bottom",
        "start_index": start_index,
        "end_index": start_index + 5,
        "start_price": start_price,
        "end_price": end_price,
        "direction": direction,
        "power_price": abs(end_price - start_price),
        "length": 5,
    }


def test_nine_strokes_rising_ladder_stays_one_up_segment():
    """9 笔 up-down 交替，向下笔高低点同步抬高 → 形不成底分型 → 1 段 up。"""
    prices = [
        (10.0, 12.0, "up"),
        (12.0, 11.0, "down"),
        (11.0, 13.0, "up"),
        (13.0, 11.5, "down"),
        (11.5, 13.5, "up"),
        (13.5, 12.0, "down"),
        (12.0, 14.0, "up"),
        (14.0, 12.5, "down"),
        (12.5, 14.5, "up"),
    ]
    strokes = [_stroke(s, e, i * 5, d) for i, (s, e, d) in enumerate(prices)]
    segs = build_segments(strokes, min_strokes=3)

    assert len(segs) == 1
    assert segs[0]["direction"] == "up"
    assert segs[0]["strokes_count"] == 9
