"""C-D4d：密分型下笔链不得饿死（南网/华工周线实锤回归）。

根因：build_strokes 在「近距反向 skip」后碰到同向分型直接 break，
连续密顶底会让整链停在旧向上笔上，面板假看涨。
"""
from __future__ import annotations

from trader_shared.chan_geometry import build_strokes, build_zones


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
    # 下一笔从更高顶起扫时衔接延伸：上一向上笔终点跟到 25
    assert strokes[0]["end_price"] == 25.0
    # 向下笔须从更高顶 25 落到底 12
    down = [s for s in strokes if s["direction"] == "down"]
    assert down, "密分型后必须形成向下笔"
    assert down[-1]["start_price"] == 25.0
    assert down[-1]["end_price"] == 12.0
    assert strokes[-1]["direction"] == "down"
    assert abs(float(strokes[0]["end_price"]) - float(down[-1]["start_price"])) < 1e-9


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
    """初选终点仍是第一个合格反向；下一笔起点抬高顶时衔接延伸上一笔（不断裂）。"""
    fractions = [
        _f("bottom", 0, high=10.5, low=10.0),
        _f("top", 5, high=12.0, low=11.5),
        _f("top", 8, high=15.0, low=14.5),
        _f("bottom", 20, high=8.5, low=8.0),
    ]
    result = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(result) == 2
    # 第二笔从更高顶起扫时，衔接把上一向上笔终点延到 15（价格连续）
    assert result[0]["end_price"] == 15.0
    assert result[1]["start_price"] == 15.0
    assert result[1]["end_price"] == 8.0


def test_bridge_lower_bottom_before_next_up_no_gap():
    """南网日线形：下笔后近顶不够距 → 更深底 → 合格顶；须先延下笔再向上，禁止 start≪prev_end。

    中间顶 62 < 笔起点 70，不破坏下跌极值，允许衔接延伸。
    """
    fractions = [
        _f("bottom", 0, high=51, low=50),
        _f("top", 10, high=70, low=68),       # up
        _f("bottom", 16, high=60, low=57),      # down 至 57
        _f("top", 17, high=62, low=58),         # 近顶，距1，不成笔（未破起点）
        _f("bottom", 23, high=41, low=37),      # 更深底
        _f("top", 29, high=45, low=41),         # 合格反向 → up 37→45
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(strokes) >= 3
    down = [s for s in strokes if s["direction"] == "down"]
    assert down, "须有向下笔"
    assert down[-1]["end_price"] == 37.0
    assert down[-1]["end_index"] == 23
    last_up = [s for s in strokes if s["direction"] == "up"][-1]
    assert last_up["start_price"] == 37.0
    assert last_up["end_price"] == 45.0
    # 价格衔接：无 57→37 断层
    assert abs(float(down[-1]["end_price"]) - float(last_up["start_price"])) < 1e-9


def test_extend_blocked_by_higher_mid_top():
    """华工形：短距更高顶破下笔起点 → §2.1c 先成短上笔，再下到深底；无吞、无断层。"""
    fractions = [
        _f("bottom", 0, high=51, low=50),
        _f("top", 10, high=180, low=170),        # up → 180
        _f("bottom", 16, high=165, low=160),       # 首个合格下笔终点 160
        _f("top", 18, high=188, low=175),          # 更高顶（距不足但破极值）
        _f("bottom", 24, high=100, low=90),         # 更深底
        _f("top", 30, high=110, low=100),
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    downs = [s for s in strokes if s["direction"] == "down"]
    assert downs, "须有向下笔"
    # 不得出现一笔从 180 直落到 90（跨过 188）
    assert not any(
        abs(float(s["start_price"]) - 180) < 1e-6 and abs(float(s["end_price"]) - 90) < 1e-6
        for s in downs
    )
    # 第一向下笔应停在首个合格底附近
    first_down = downs[0]
    assert float(first_down["start_price"]) == 180.0
    assert float(first_down["end_price"]) == 160.0
    # §2.1c：短上笔 160→188，再下 188→90，价格连续
    assert any(
        s["direction"] == "up"
        and abs(float(s["start_price"]) - 160) < 1e-6
        and abs(float(s["end_price"]) - 188) < 1e-6
        for s in strokes
    )
    assert any(
        s["direction"] == "down"
        and abs(float(s["start_price"]) - 188) < 1e-6
        and abs(float(s["end_price"]) - 90) < 1e-6
        for s in strokes
    )
    for a, b in zip(strokes, strokes[1:]):
        assert abs(float(a["end_price"]) - float(b["start_price"])) < 1e-9


def test_short_down_breaks_prior_up_extreme():
    """对称：上笔后短距更低底破起点 → 破例成短下笔，无 90→120 断层。"""
    fractions = [
        _f("top", 0, high=100, low=99),
        _f("bottom", 10, high=80, low=70),
        _f("top", 16, high=90, low=85),
        _f("bottom", 18, high=60, low=55),  # 破上笔起点 70
        _f("top", 24, high=120, low=110),
        _f("bottom", 30, high=100, low=95),
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    assert any(
        s["direction"] == "down"
        and abs(float(s["start_price"]) - 90) < 1e-6
        and abs(float(s["end_price"]) - 55) < 1e-6
        for s in strokes
    )
    for a, b in zip(strokes, strokes[1:]):
        assert abs(float(a["end_price"]) - float(b["start_price"])) < 1e-9


def test_zhonghang_gap_after_deeper_bottom_then_break_top():
    """中航光电日线形：下笔后近顶未破 → 更深底 → 短距更高顶破起点。

    旧 §2.1c 要求 start 锚在上一笔终点，起点推到更深底后漏掉 42.99 短上笔，
    留下 down 40.74 → up 38.62 断层。
    """
    fractions = [
        _f("bottom", 206, high=38.0, low=37.5),
        _f("top", 212, high=42.64, low=41.0),
        _f("bottom", 216, high=41.48, low=40.74),   # down 终点
        _f("top", 218, high=42.22, low=41.41),      # 近顶未破 42.64
        _f("bottom", 220, high=42.0, low=40.57),     # 更深底（start 被推离 216）
        _f("top", 221, high=42.99, low=41.63),      # 破极值短顶
        _f("bottom", 229, high=39.03, low=38.62),
        _f("top", 235, high=41.91, low=40.0),
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    for a, b in zip(strokes, strokes[1:]):
        assert abs(float(a["end_price"]) - float(b["start_price"])) < 1e-9, (
            f"断层 {a['end_price']}→{b['start_price']} strokes={strokes}"
        )
    # 更深底衔接后短上笔到 42.99，再下到 38.62（连续，不再 40.74 跳空起笔）
    assert any(
        s["direction"] == "up"
        and abs(float(s["start_price"]) - 40.57) < 1e-6
        and abs(float(s["end_price"]) - 42.99) < 1e-6
        for s in strokes
    ), strokes
    downs = [s for s in strokes if s["direction"] == "down"]
    assert any(abs(float(s["end_price"]) - 40.57) < 1e-6 for s in downs)


def test_extreme_breaking_short_stroke_feeds_pivot():
    """§2.1c + §4：破极值短笔须作为普通笔参与中枢，不得因 length<5 被丢弃。"""
    fractions = [
        _f("top", 0, high=20.0, low=19.0),
        _f("bottom", 10, high=11.0, low=10.0),     # down 20→10
        _f("top", 12, high=16.0, low=15.0),        # 近顶（距 2，未破 20）
        _f("bottom", 13, high=9.5, low=9.0),        # 更深底（start 推进）
        _f("top", 14, high=21.0, low=20.0),         # 更高顶破下笔起点 20 → 短上破例
        _f("bottom", 20, high=12.0, low=11.0),
    ]
    strokes = build_strokes(fractions, min_bars_per_stroke=5)
    short_up = [
        s for s in strokes
        if s["direction"] == "up" and int(s["length"]) < 4
    ]
    assert short_up, f"应有破极值短上笔，实际 strokes={strokes}"
    zones = build_zones(strokes, merge=False)
    assert zones, f"短笔参与后须能形成中枢，实际 strokes={strokes}"
    assert zones[0]["valid"] is True
    assert zones[0]["zh_top"] > zones[0]["zh_bottom"]
