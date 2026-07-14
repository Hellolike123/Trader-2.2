"""缠论语义正确性测试（P0 修复回归闸门）。

针对两处历史“胡算”根因：
1. build_strokes 必须取【第一个】距离合格的反向分型成笔，而非延伸到最极端。
2. detect_divergence 的 fallback 峰谷扫描必须只扫【近期】窗口，
   不能把几年前的旧背离当现状污染买卖点信号。
"""
from trader_shared.chan_geometry import build_strokes
from trader_shared.chan_structure import detect_divergence


def test_stroke_takes_first_qualifying_not_most_extreme():
    """笔终点应是第一个距离合格的反向分型，不是最极端的那个。

    序列：底@0 → 顶@5(高12) → 顶@8(高15) → 底@20。
    缠论：从底@0 出发，第一个合格反向分型是顶@5（高12）即止笔；
    若错误地延伸到最极端，会取到顶@8（高15），吞掉独立笔。
    """
    fractions = [
        {"type": "bottom", "index": 0, "low": 10.0, "high": 10.5, "close": 10.2},
        {"type": "top", "index": 5, "high": 12.0, "low": 11.5, "close": 11.8},  # 第一个合格反向
        {"type": "top", "index": 8, "high": 15.0, "low": 14.5, "close": 14.8},  # 更极端但更靠后
        {"type": "bottom", "index": 20, "low": 8.0, "high": 8.5, "close": 8.2},
    ]
    result = build_strokes(fractions, min_bars_per_stroke=5)
    assert len(result) == 2, f"应成 2 笔，实际 {len(result)}"
    # 第一笔终点必须是第一个合格反向分型（高12），而非最极端（高15）
    assert result[0]["end_price"] == 12.0, (
        f"笔终点取了最极端端点（错误），应为第一个合格反向分型 12.0，"
        f"实际 {result[0]['end_price']}"
    )
    assert result[0]["end_type"] == "top"
    # 第二笔：顶@8 → 底@20
    assert result[1]["start_price"] == 15.0
    assert result[1]["end_price"] == 8.0


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
