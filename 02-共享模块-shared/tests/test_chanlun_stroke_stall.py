"""C-D4d：密分型下笔链不得饿死（南网/华工周线实锤回归）。

根因：build_strokes 在「近距反向 skip」后碰到同向分型直接 break，
连续密顶底会让整链停在旧向上笔上，面板假看涨。
"""
from __future__ import annotations

from trader_shared.chan_geometry import build_strokes


def _f(typ: str, idx: int, *, high: float, low: float) -> dict:
    return {
        "type": typ,
        "index": idx,
        "high": high,
        "low": low,
        "close": (high + low) / 2,
    }


def test_stroke_stall_same_type_after_near_reverse_continues():
    """近底不够距 → 更高顶 → 够距底：必须成向下笔，不得停在旧顶。

    模拟南网周线：up 已在顶@10 成笔；其后底@12（距2）不够，顶@14 更高，
    底@20 够距 → 应有 down 笔。
    """
    fractions = [
        _f("bottom", 0, high=11, low=10),
        _f("top", 10, high=20, low=19),  # 第一笔 up 终点
        _f("bottom", 12, high=18, low=17),  # 距顶不够
        _f("top", 14, high=25, low=24),  # 同向更高顶（旧逻辑 break 饿死）
        _f("bottom", 20, high=16, low=12),  # 合格反向
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(strokes) >= 2, f"应至少 2 笔，实际 {strokes}"
    assert strokes[0]["direction"] == "up"
    assert strokes[0]["end_price"] == 20.0
    # 向下笔须从更高顶 25 落到底 12
    down = [s for s in strokes if s["direction"] == "down"]
    assert down, "密分型后必须形成向下笔"
    assert down[-1]["start_price"] == 25.0
    assert down[-1]["end_price"] == 12.0
    assert strokes[-1]["direction"] == "down"


def test_stroke_extends_when_no_reverse_but_same_extreme_advances():
    """序列末无合格反向、仅同向新高：延伸上一向上笔终点，避免僵尸旧顶。"""
    fractions = [
        _f("bottom", 0, high=11, low=10),
        _f("top", 5, high=20, low=19),
        _f("bottom", 7, high=18, low=17),  # 近距，不成笔
        _f("top", 9, high=28, low=27),  # 新高，无更远底
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(strokes) == 1
    assert strokes[0]["direction"] == "up"
    assert strokes[0]["end_price"] == 28.0
    assert strokes[0]["end_index"] == 9


def test_first_qualifying_end_not_most_extreme_still_holds():
    """回归 formulas §2.1：成笔终点仍是第一个合格反向，不吞后续更高顶。"""
    fractions = [
        _f("bottom", 0, high=10.5, low=10.0),
        _f("top", 5, high=12.0, low=11.5),
        _f("top", 8, high=15.0, low=14.5),
        _f("bottom", 20, high=8.5, low=8.0),
    ]
    result = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(result) == 2
    assert result[0]["end_price"] == 12.0
    assert result[1]["start_price"] == 15.0
    assert result[1]["end_price"] == 8.0
