"""S-2 观察档快照合同 — 法源 docs/plans/chanlun-s2-s3-followup-handoff.md §1。

锁定：类一/类二永不进入正式六灯；正式类型不被标观察。
夹具 type 集合对齐 2026-08-04 离线五票 smoke（§10）。
"""
from __future__ import annotations

from trader_shared.chanlun_render import (
    _collect_points,
    _display_point_type,
    render_chanlun_card,
)
from trader_shared.chanlun_run import build_chanlun_view


def _view(buy=None, sell=None, directions=None) -> dict:
    strokes = []
    for i, d in enumerate(directions or ["up", "down", "up"]):
        strokes.append(
            {
                "direction": d,
                "start_index": i * 5,
                "end_index": i * 5 + 4,
                "start_price": 10.0 + i,
                "end_price": 11.0 + i,
            }
        )
    result = {
        "chanlun": {
            "timeframe": "daily",
            "structure_type": "盘整",
            "trend_label": "回调段",
            "strokes": strokes,
            "zones": [{"zh_top": 12.0, "zh_bottom": 10.0, "valid": True}],
            "segments": [{"direction": "up"}],
            "buy_points": list(buy or []),
            "sell_points": list(sell or []),
            "zones_count": 1,
            "pivot_count": 1,
        }
    }
    return build_chanlun_view(result, current=11.5)


def test_s2_t1_observe_types_never_in_formal_keys():
    """S2-T1：类一/类二只进 observe。"""
    view = _view(
        buy=[{"type": "类一买", "price": 95.27}, {"type": "类二买", "price": 90.0}],
        sell=[{"type": "类一卖", "price": 1416.88}, {"type": "类二卖", "price": 45.14}],
    )
    formal, observe = _collect_points(view)
    assert formal == {}
    labels = [lab for lab, _ in observe]
    assert "类一买（观察）" in labels
    assert "类二买（观察）" in labels
    assert "类一卖（观察）" in labels
    assert "类二卖（观察）" in labels
    for key in formal:
        assert not str(key).startswith(("类一", "类二"))


def test_s2_t3_smoke_type_snapshot_mix_with_formal():
    """S2-T3：§10 出现过的观察档与正式灯可共存且不串档。"""
    view = _view(
        buy=[{"type": "三类买", "price": 30.0}, {"type": "类一买", "price": 95.27}],
        sell=[{"type": "类一卖", "price": 1416.88}, {"type": "类二卖", "price": 45.14}],
    )
    formal, observe = _collect_points(view)
    assert "三类买" in formal
    assert formal["三类买"]
    assert "类一买" not in formal
    assert "类一卖" not in formal
    assert "类二卖" not in formal
    obs_join = " ".join(lab for lab, _ in observe)
    assert "类一买（观察）" in obs_join
    assert "类一卖（观察）" in obs_join
    assert "类二卖（观察）" in obs_join
    assert "1416.88" in " ".join(p for _, p in observe) or any(
        p.startswith("1416") for _, p in observe
    )


def test_s2_t2_formal_not_marked_observe_via_display():
    """S2-T2：正式类型 display 不加（观察）。"""
    for t in ("一类买", "二类买", "三类买", "一类卖", "二类卖", "三类卖"):
        assert "观察" not in _display_point_type(t)
    for t in ("类一买", "类二卖"):
        assert _display_point_type(t).endswith("（观察）")


def test_s2_card_text_observe_suffix_and_no_fake_formal_lamp():
    """面板：观察带后缀；正式六灯行不把类一写成一类。"""
    view = _view(
        buy=[{"type": "类一买", "price": 29.98}],
        sell=[{"type": "类二卖", "price": 34.10}],
    )
    plan = {
        "name": "测",
        "code": "000000",
        "current": 31.0,
        "short_view": view,
        "midline_view": _view(directions=["down", "up", "down"]),
        "chanlun": {
            "timeframe": "daily",
            "strokes": view.get("recent_stroke_directions") and [],
            "buy_points": view["buy_points"],
            "sell_points": view["sell_points"],
            "structure_type": "盘整",
            "trend_label": "回调段",
        },
    }
    # slim may need richer plan; card path is enough for point lines
    from trader_shared.chanlun_render import render_chanlun_card

    # build_chanlun_view already stripped; card expects plan with views or legacy
    text = render_chanlun_card(
        {
            "name": "测",
            "code": "000000",
            "view": view,
            "short_view": view,
            "midline_view": view,
        }
    )
    assert "类一买（观察）" in text or "（观察）" in text
    # must not promote
    assert "● 一类买" not in text.replace("类一买", "")
