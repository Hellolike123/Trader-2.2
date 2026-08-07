"""中枢合并回归测试（formulas.md §4.2）。

合并取**交集**（zh_top=min, zh_bottom=max）：
- 窄震荡不得被并集撑成巨中枢（Bug S 回归）
- 链式交集若塌缩到 top <= bottom，停止合并另起，不出现非法中枢
- 纯 gap 不合并
"""
from trader_shared.chan_geometry import build_zones, _merge_zones


def test_narrow_oscillation_merge_keeps_narrow_pivot():
    """5 笔 ~0.5 元窄震荡：交集合并后宽度 ~0.3 元，不得被并集撑到 >1 元。"""
    items = [
        {"start_price": 10.0, "end_price": 10.6, "direction": "up",
         "start_index": 0, "end_index": 5},
        {"start_price": 10.6, "end_price": 10.1, "direction": "down",
         "start_index": 5, "end_index": 10},
        {"start_price": 10.1, "end_price": 10.55, "direction": "up",
         "start_index": 10, "end_index": 15},
        {"start_price": 10.55, "end_price": 10.2, "direction": "down",
         "start_index": 15, "end_index": 20},
        {"start_price": 10.2, "end_price": 10.5, "direction": "up",
         "start_index": 20, "end_index": 25},
    ]
    merged = build_zones(items, merge=True)
    assert len(merged) == 1
    z = merged[0]
    width = z["zh_top"] - z["zh_bottom"]
    assert z["zh_top"] > z["zh_bottom"]
    assert width <= 0.5, f"narrow pivot blown up to {width}"


def test_gap_zones_not_merged():
    """不重叠（gap）中枢不得合并。"""
    raw_zones = [
        {"zh_top": 12.0, "zh_bottom": 10.0, "zh_center": 11.0, "valid": True},
        {"zh_top": 14.0, "zh_bottom": 12.05, "zh_center": 13.025, "valid": True},
    ]
    merged = _merge_zones(raw_zones, gap_pct=0.015)
    assert len(merged) == 2
    for z in merged:
        assert z["zh_top"] > z["zh_bottom"]


def test_chain_collapse_stops_merge_not_invalid():
    """链式交集若塌缩到 top <= bottom（无公共重叠），另起中枢，不出非法中枢。"""
    raw_zones = [
        {"zh_top": 10.0, "zh_bottom": 8.0, "zh_center": 9.0, "valid": True,
         "strokes": [{"start_index": 0, "end_index": 2}]},
        {"zh_top": 9.0, "zh_bottom": 7.0, "zh_center": 8.0, "valid": True,
         "strokes": [{"start_index": 1, "end_index": 3}]},
        {"zh_top": 7.5, "zh_bottom": 6.0, "zh_center": 6.75, "valid": True,
         "strokes": [{"start_index": 2, "end_index": 4}]},
    ]
    merged = _merge_zones(raw_zones, gap_pct=0.015)
    for z in merged:
        assert z["zh_top"] > z["zh_bottom"]
