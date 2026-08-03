"""缠论语义正确性测试（P0/P2/P3 修复回归闸门）。

针对历史“胡算”与边界根因：
1. build_strokes 必须取【第一个】距离合格的反向分型成笔，而非延伸到最极端。
2. detect_divergence 的 fallback 峰谷扫描必须只扫【近期】窗口，
   不能把几年前的旧背离当现状污染买卖点信号。
3. P2：首笔从数据起点起算、左端无支点，属悬空不可信笔，须裁掉从完整支点起读。
4. P3：背驰须锚定【最后中枢】而非固定窗口，只比较多级中枢之后的趋势 legs。
"""
from trader_shared.chan_geometry import (
    build_strokes,
    build_segments,
    find_fractions,
    handle_inclusion,
    _calc_macd,
    _drop_leading_dangling_strokes,
    _last_pivot_anchor_bar,
)
from trader_shared.chan_structure import detect_divergence
from trader_shared.chan_core import chanlun_analysis, ChanlunEngine
from trader_shared.testing.mock_seam import apply_seam, gen_bars


def test_stroke_takes_first_qualifying_not_most_extreme():
    """初选：第一个合格反向成笔；若后续更高顶成为下一笔起点，§2.1a 衔接延伸上一笔。

    序列：底@0 → 顶@5(高12) → 顶@8(高15) → 底@20。
    从底@0 初选终点是顶@5；形成向下笔前起点抬到顶@8 时，衔接把上一笔 end 延到 15，
    保证价格连续（不再保留 12→15 断层）。
    """
    fractions = [
        {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
        {"type": "top", "index": 5, "high": 12.0, "low": 11.5, "close": 11.8},  # 初选合格反向
        {"type": "top", "index": 8, "high": 15.0, "low": 14.5, "close": 14.8},  # 下一笔起点抬高
        {"type": "bottom", "index": 20, "low": 8.0, "high": 8.5, "close": 8.2},
    ]
    result = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(result) == 2, f"应成 2 笔，实际 {len(result)}"
    assert result[0]["end_type"] == "top"
    assert result[0]["end_price"] == 15.0
    assert result[1]["start_price"] == 15.0
    assert result[1]["end_price"] == 8.0
    assert abs(float(result[0]["end_price"]) - float(result[1]["start_price"])) < 1e-9


def test_stroke_single_qualifying_top_keeps_first_end():
    """仅一个合格反向顶、无后续分型：终点就是该顶（初选规则）。"""
    fractions = [
        {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
        {"type": "top", "index": 5, "high": 12.0, "low": 11.5, "close": 11.8},
    ]
    result = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(result) == 1
    assert result[0]["end_price"] == 12.0
    assert result[0]["end_index"] == 5


def _make_bars(n, old_div_at=None, recent_div_at=None):
    """构造 bars：high/low/macd_histogram 齐全。

    old_div_at / recent_div_at: 在该索引附近放置一个“顶背离”形态
    （两个相邻峰：后峰价更高、MACD 更低）。其余区间单调上升无局部峰，
    确保 fallback 只在指定位置检测到峰。
    """
    bars = []
    for i in range(n):
        h = 30.0 + i * 0.01  # 单调上升，无局部峰
        l = h - 1.0
        bars.append({"index": i, "high": h, "low": l, "macd_histogram": 1.0})

    def plant(idx):
        # 在 idx 附近造两个峰：idx 和 idx+5，后者价更高、macd 更低
        for j in (idx, idx + 5):
            bars[j]["high"] = 50.0 + j
        bars[idx]["macd_histogram"] = 5.0
        bars[idx + 5]["macd_histogram"] = 2.0  # 后峰价更高、macd 更低 → 顶背离

    if old_div_at is not None:
        plant(old_div_at)
    if recent_div_at is not None:
        plant(recent_div_at)
    return bars


def test_divergence_fallback_ignores_old_history():
    """旧背离位于数据头部（超出近期窗口）时，fallback 必须忽略它。"""
    n = 250
    # 旧顶背离放在 idx=4（远早于 window=120 的扫描起点 130）
    bars = _make_bars(n, old_div_at=4)
    res = detect_divergence(bars, strokes=None)  # 无笔 → 走 fallback
    assert res["top_divergence"] is False, (
        "fallback 扫了全图历史，把头部旧背离当现状（错误）"
    )
    assert res["bottom_divergence"] is False


def test_divergence_fallback_detects_recent():
    """近期窗口内的背离仍应被检测到（证明限制窗口不是一刀切 False）。"""
    n = 250
    # 近期顶背离放在 idx=200（在 window=120 的扫描起点 130 之内）
    bars = _make_bars(n, recent_div_at=200)
    res = detect_divergence(bars, strokes=None)
    assert res["top_divergence"] is True, (
        "近期窗口内的背离未被检测到（限制过严）"
    )


# ───────────────────────── P2：前导悬空笔 ─────────────────────────


def test_drop_leading_dangling_strokes_removes_first():
    """首笔（数据起点、无左支点）必须被裁掉，从完整支点起读。"""
    s0 = {"start_index": 0, "end_index": 5, "direction": "up"}
    s1 = {"start_index": 6, "end_index": 12, "direction": "down"}
    s2 = {"start_index": 13, "end_index": 20, "direction": "up"}
    strokes = [s0, s1, s2]
    out = _drop_leading_dangling_strokes(strokes)
    assert out == [s1, s2], "应裁掉首笔 s0"
    # 笔数 < 2 时不裁
    assert _drop_leading_dangling_strokes([s0]) == [s0]
    assert _drop_leading_dangling_strokes([]) == []


def _zigzag_bars():
    """确定性锯齿序列（清晰多段 swing），确保能识别出多条笔。"""
    closes = [10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10, 9,
              10, 11, 12, 13, 14, 15, 16, 15, 14, 13, 12, 11, 10, 9]
    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "date": f"2024-01-{i + 1:02d}", "open": float(c), "high": float(c) + 0.5,
            "low": float(c) - 0.5, "close": float(c), "volume": 100.0,
        })
    return bars


def test_chanlun_compute_drops_leading_stroke(monkeypatch):
    """_chanlun_compute 输出的 strokes 应比「裸 build_strokes」少首笔（悬空笔）。"""
    apply_seam(monkeypatch)
    bars = _zigzag_bars()
    cleaned = _calc_macd(handle_inclusion(bars))
    raw = build_strokes(find_fractions(cleaned), min_bars_per_stroke=5, bars=cleaned)
    assert len(raw) >= 2, "锯齿序列应识别出多条笔，测试前提失效"
    res = chanlun_analysis(bars, current=bars[-1]["close"])
    trimmed = res["strokes"]
    # 首笔（数据起点、无左支点）被裁掉，从完整支点起读
    assert len(trimmed) == len(raw) - 1, (
        f"应裁掉左端悬空首笔：裸 {len(raw)} 笔 → 去悬空后 {len(trimmed)} 笔"
    )
    # engine 与批量路径须一致（共享内核）
    eng = ChanlunEngine(bars).get_analysis(current=bars[-1]["close"])
    assert len(eng["strokes"]) == len(trimmed), "引擎与批量 strokes 长度须一致"
    assert eng["strokes"] == trimmed, "引擎与批量 strokes 内容须一致"


# ───────────────────────── P3：锚定最后中枢 ─────────────────────────


def test_last_pivot_anchor_bar_maps_segment_index_to_bar():
    """最后中枢的成员元素若是线段（笔索引），须经 strokes 映射到 bar 索引。"""
    strokes = [
        {"start_index": 0, "end_index": 9},
        {"start_index": 10, "end_index": 19},
        {"start_index": 20, "end_index": 29},
        {"start_index": 30, "end_index": 39},
    ]
    # 最后中枢由两个线段构成（start/end 为笔索引）
    seg_a = {"start_index": 0, "end_index": 1}
    seg_b = {"start_index": 1, "end_index": 3}
    raw_zone = {"zh_top": 15.0, "zh_bottom": 12.0, "valid": True, "strokes": [seg_a, seg_b]}
    merged = [{"zh_top": 15.0, "zh_bottom": 12.0, "valid": True, "members": [raw_zone]}]
    anchor = _last_pivot_anchor_bar([seg_a, seg_b], strokes, merged)
    # 末成员 seg_b.end_index=3（笔索引）→ strokes[3].end_index = 39
    assert anchor == 39, f"应映射到 bar 39，实际 {anchor}"


def test_divergence_anchor_excludes_pre_anchor_history():
    """P3：锚定最后中枢后，中枢之前的背离必须被排除（fallback 窗口从 anchor 起算）。"""
    n = 250
    # 顶背离放在 idx=150（中枢锚点在 200 之后 → 应被排除）
    bars = _make_bars(n, recent_div_at=150)
    res_no_anchor = detect_divergence(bars, strokes=None, anchor_bar=None)
    res_anchored = detect_divergence(bars, strokes=None, anchor_bar=200)
    assert res_no_anchor["top_divergence"] is True, "未锚定时 150 在窗口内，应检出"
    assert res_anchored["top_divergence"] is False, "锚定后 150 在窗口外，必须排除旧背离"
