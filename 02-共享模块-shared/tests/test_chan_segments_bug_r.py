"""Bug R（第二类线段破坏）回归测试。

对照 formulas.md §3.6：
- 向上段：特征序列（向下笔）low 跌破段起点 low → 段破坏
- 向下段：特征序列（向上笔）high 突破段起点 high → 段破坏
- 护栏：段内笔数 >= min_strokes 且剩余笔数 >= min_strokes

历史 bug：实现写成「整根脱离」（char_h < seg_pivot_low / char_l > seg_pivot_high），
导致只有价格完全回到起点另一侧才切，Bug R 分支近乎死代码。
"""
from trader_shared.chan_geometry import build_segments


def _stroke(start_price, end_price, start_index, direction):
    return {
        "start_type": "bottom" if direction == "up" else "top",
        "end_type": "top" if direction == "up" else "bottom",
        "start_index": start_index,
        "end_index": start_index + 3,
        "start_price": start_price,
        "end_price": end_price,
        "direction": direction,
        "power_price": abs(end_price - start_price),
        "length": 3,
    }


def test_up_segment_breaks_when_down_stroke_low_pierces_start():
    """向上段：向下笔 low 跌破段起点 low（10.0），且破坏后剩 >=3 笔 → 切段。

    第 3 笔创新高 18 确保首段方向明确判 up；第 6 笔跌到 9.5 跌破起点 10。
    """
    prices = [
        (10.0, 17.0, "up"),
        (17.0, 15.0, "down"),
        (15.0, 18.0, "up"),
        (18.0, 14.0, "down"),
        (14.0, 15.0, "up"),
        (15.0, 9.5, "down"),
        (9.5, 10.5, "up"),
        (10.5, 8.5, "down"),
        (8.5, 9.0, "up"),
    ]
    strokes = [_stroke(s, e, i * 3, d) for i, (s, e, d) in enumerate(prices)]
    segs = build_segments(strokes, min_strokes=3)

    assert len(segs) >= 2
    assert segs[0]["direction"] == "up"
    assert segs[1]["direction"] == "down"


def test_down_segment_breaks_when_up_stroke_high_pierces_start():
    """向下段对称：向上笔 high 突破段起点 high → 切段。"""
    prices = [
        (20.0, 13.0, "down"),
        (13.0, 15.0, "up"),
        (15.0, 12.0, "down"),
        (12.0, 18.0, "up"),
        (18.0, 17.0, "down"),
        (17.0, 20.5, "up"),
        (20.5, 19.0, "down"),
        (19.0, 22.0, "up"),
        (22.0, 21.0, "down"),
    ]
    strokes = [_stroke(s, e, i * 3, d) for i, (s, e, d) in enumerate(prices)]
    segs = build_segments(strokes, min_strokes=3)

    assert len(segs) >= 2
    assert segs[0]["direction"] == "down"
    assert segs[1]["direction"] == "up"


def test_unilateral_up_does_not_break():
    """真单边上涨：回落笔 low 始终高于起点 low，不切段。"""
    prices = [
        (10.0, 12.0, "up"),
        (12.0, 11.5, "down"),
        (11.5, 13.0, "up"),
        (13.0, 12.5, "down"),
        (12.5, 14.0, "up"),
        (14.0, 13.5, "down"),
    ]
    strokes = [_stroke(s, e, i * 3, d) for i, (s, e, d) in enumerate(prices)]
    segs = build_segments(strokes, min_strokes=3)

    assert len(segs) == 1
    assert segs[0]["direction"] == "up"


def test_three_strokes_not_cut_by_guardrail():
    """3 笔：护栏 seg_len >= min_strokes 后剩余笔不足 3，不切。"""
    prices = [
        (10.0, 12.0, "up"),
        (12.0, 9.5, "down"),
        (9.5, 10.0, "up"),
    ]
    strokes = [_stroke(s, e, i * 3, d) for i, (s, e, d) in enumerate(prices)]
    segs = build_segments(strokes, min_strokes=3)

    assert len(segs) == 1
