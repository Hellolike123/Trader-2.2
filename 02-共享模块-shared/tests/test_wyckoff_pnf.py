"""威科夫 P&F：建图、水平计数、fallback、开关。"""
from __future__ import annotations

from trader_shared.wyckoff_events import _cause_effect_targets
from trader_shared.wyckoff_pnf import (
    METHOD_HEIGHT_1TO1,
    METHOD_HORIZONTAL,
    METHOD_VERTICAL,
    build_pnf_columns,
    columns_overlapping_tr,
    compute_cause_effect_targets,
    resolve_box_size,
)


def _bar(o: float, h: float, l: float, c: float, v: float = 1000.0) -> dict:
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _oscillating_tr_bars() -> list[dict]:
    """在约 10–20 区间内来回，box=1 / rev=3 时产生多列。"""
    bars: list[dict] = []
    # 初始
    bars.append(_bar(10, 10.5, 9.8, 10.2))
    # 拉升 → 开 X
    bars.append(_bar(10.2, 16.0, 10.0, 15.5))
    # 回落够 3 格 → O
    bars.append(_bar(15.5, 15.8, 9.0, 9.5))
    # 再上 → X
    bars.append(_bar(9.5, 17.0, 9.2, 16.5))
    # 再下 → O
    bars.append(_bar(16.5, 16.8, 8.5, 9.0))
    # 再上 → X
    bars.append(_bar(9.0, 18.0, 8.8, 17.5))
    # 再下 → O
    bars.append(_bar(17.5, 17.8, 9.5, 10.0))
    # 再上 → X
    bars.append(_bar(10.0, 16.0, 9.8, 15.5))
    return bars


def test_resolve_box_size_pct_and_floor():
    assert resolve_box_size(20.0, 10.0, box_pct=0.01, box_min=0.01) == 0.15
    assert resolve_box_size(20.0, 10.0, box_pct=0.0001, box_min=1.0) == 1.0


def test_build_pnf_columns_reversal():
    bars = _oscillating_tr_bars()
    cols = build_pnf_columns(bars, box_size=1.0, reversal=3)
    assert len(cols) >= 3
    dirs = [c["direction"] for c in cols]
    # 列方向必须交替
    for i in range(1, len(dirs)):
        assert dirs[i] != dirs[i - 1]
    assert cols[0]["direction"] in ("X", "O")
    assert all(c["box_count"] >= 1 for c in cols)


def test_horizontal_count_targets():
    bars = _oscillating_tr_bars()
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
        "tr_quality": 0.8,
    }
    ce = compute_cause_effect_targets(
        tr,
        bars,
        enabled=True,
        box_pct=0.0001,
        box_min=1.0,
        reversal=3,
        min_columns=3,
        vertical_enabled=True,
        include_reversal=False,
    )
    assert ce["pnf_method"] == METHOD_HORIZONTAL
    assert ce["pnf_box_size"] == 1.0
    assert ce["pnf_columns"] is not None and ce["pnf_columns"] >= 3
    effect = float(ce["cause_effect_range"])
    assert abs(effect - ce["pnf_columns"] * 1.0) < 1e-9
    assert ce["cause_effect_up_target"] == round(20.0 + effect, 2)
    assert ce["cause_effect_down_target"] == round(10.0 - effect, 2)
    assert "水平计数" in ce["cause_effect_note"]


def test_columns_overlapping_tr_filter():
    cols = [
        {"direction": "X", "top": 19, "bottom": 15, "box_count": 5},
        {"direction": "O", "top": 5, "bottom": 1, "box_count": 5},  # 完全在 TR 下
    ]
    ov = columns_overlapping_tr(cols, tr_upper=20.0, tr_lower=10.0, box_size=1.0)
    assert len(ov) == 1
    assert ov[0]["bottom"] == 15


def test_fallback_no_bars():
    ce = compute_cause_effect_targets(
        {"tr_upper": 20.0, "tr_lower": 10.0},
        None,
        enabled=True,
    )
    assert ce["pnf_method"] == METHOD_HEIGHT_1TO1
    assert ce["cause_effect_up_target"] == 30.0
    assert ce["cause_effect_down_target"] == 0.0
    assert ce["cause_effect_range"] == 10.0
    assert "缺 K 线" in ce["cause_effect_note"] or "1:1" in ce["cause_effect_note"]


def test_disabled_switch_forces_1to1():
    bars = _oscillating_tr_bars()
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
    }
    ce = compute_cause_effect_targets(
        tr,
        bars,
        enabled=False,
        box_pct=0.0001,
        box_min=1.0,
    )
    assert ce["pnf_method"] == METHOD_HEIGHT_1TO1
    assert ce["cause_effect_up_target"] == 30.0
    assert ce["cause_effect_down_target"] == 0.0
    assert "关闭" in ce["cause_effect_note"] or "P&F 已关闭" in ce["cause_effect_note"]


def test_vertical_fallback_when_few_columns():
    # 单边上行：通常只有 1 列 X，水平不足 → 垂直或 1:1
    bars = [_bar(10, 10.2, 9.9, 10.1)]
    for i in range(1, 12):
        px = 10 + i * 0.8
        bars.append(_bar(px - 0.3, px + 0.2, px - 0.5, px))
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
    }
    ce = compute_cause_effect_targets(
        tr,
        bars,
        enabled=True,
        box_pct=0.0001,
        box_min=1.0,
        reversal=3,
        min_columns=5,  # 抬高门槛逼垂直/1:1
        vertical_enabled=True,
        include_reversal=False,
    )
    assert ce["pnf_method"] in (METHOD_VERTICAL, METHOD_HEIGHT_1TO1)
    assert ce["cause_effect_up_target"] is not None
    assert "降级" in ce["cause_effect_note"] or "回退" in ce["cause_effect_note"] or "垂直" in ce["cause_effect_note"]


def test_low_quality_forces_1to1():
    bars = _oscillating_tr_bars()
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_quality": 0.1,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
    }
    ce = compute_cause_effect_targets(
        tr,
        bars,
        enabled=True,
        min_tr_quality=0.35,
        box_pct=0.0001,
        box_min=1.0,
    )
    assert ce["pnf_method"] == METHOD_HEIGHT_1TO1
    assert "质量" in ce["cause_effect_note"]


def test_no_tr_empty():
    ce = compute_cause_effect_targets(None, [])
    assert ce["cause_effect_up_target"] is None
    assert ce["pnf_method"] is None
    assert "无有效 TR" in ce["cause_effect_note"]


def test_events_delegate_no_bars_1to1():
    """兼容旧调用：无 bars → 1:1（数字与旧契约一致）。"""
    ce = _cause_effect_targets({"tr_upper": 20.0, "tr_lower": 10.0})
    assert ce["cause_effect_up_target"] == 30.0
    assert ce["cause_effect_down_target"] == 0.0
    assert ce["cause_effect_range"] == 10.0
    assert ce["pnf_method"] == METHOD_HEIGHT_1TO1


def test_include_reversal_multiplies_effect():
    bars = _oscillating_tr_bars()
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
    }
    base = dict(
        enabled=True,
        box_pct=0.0001,
        box_min=1.0,
        reversal=3,
        min_columns=3,
        vertical_enabled=False,
    )
    ce0 = compute_cause_effect_targets(tr, bars, include_reversal=False, **base)
    ce1 = compute_cause_effect_targets(tr, bars, include_reversal=True, **base)
    assert ce0["pnf_method"] == METHOD_HORIZONTAL
    assert ce1["pnf_method"] == METHOD_HORIZONTAL
    assert ce0["pnf_columns"] == ce1["pnf_columns"]
    assert abs(float(ce1["cause_effect_range"]) - float(ce0["cause_effect_range"]) * 3) < 1e-9


def test_min_columns_nonpositive_does_not_fake_zero_effect():
    """min_columns≤0 不得把 0 列当成水平成功（effect=0）。"""
    ce = compute_cause_effect_targets(
        {"tr_upper": 20.0, "tr_lower": 10.0},
        [_bar(15, 15.1, 14.9, 15.0)],  # 单根：通常建不出列
        enabled=True,
        box_pct=0.0001,
        box_min=1.0,
        min_columns=0,
        vertical_enabled=False,
    )
    assert ce["pnf_method"] == METHOD_HEIGHT_1TO1
    assert float(ce["cause_effect_range"]) == 10.0
    assert "回退" in ce["cause_effect_note"] or "失败" in ce["cause_effect_note"]


def test_vertical_uses_tallest_column():
    bars = [_bar(10, 10.2, 9.9, 10.1)]
    for i in range(1, 12):
        px = 10 + i * 0.8
        bars.append(_bar(px - 0.3, px + 0.2, px - 0.5, px))
    tr = {
        "tr_upper": 20.0,
        "tr_lower": 10.0,
        "tr_start": 0,
        "tr_end": len(bars) - 1,
    }
    ce = compute_cause_effect_targets(
        tr,
        bars,
        enabled=True,
        box_pct=0.0001,
        box_min=1.0,
        reversal=3,
        min_columns=5,
        vertical_enabled=True,
        include_reversal=False,
    )
    assert ce["pnf_method"] == METHOD_VERTICAL
    assert "垂直计数降级" in ce["cause_effect_note"]
    assert float(ce["cause_effect_range"]) >= 1.0
