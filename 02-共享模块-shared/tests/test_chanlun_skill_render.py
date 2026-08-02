"""缠论 Skill 合同测试（C-D4a–c / C-D5）。"""
from __future__ import annotations

import pytest

from trader_shared.chanlun_render import render_chanlun_card
from trader_shared.chanlun_run import build_chanlun_plan, build_chanlun_view
from trader_shared.market_types import MarketSnapshot, Security


def _engine_result(directions: list[str], *, timeframe: str = "daily") -> dict:
    strokes = [
        {
            "direction": direction,
            "start_price": 10.0 + index,
            "end_price": 11.0 + index,
        }
        for index, direction in enumerate(directions)
    ]
    return {
        "chanlun": {
            "timeframe": timeframe,
            "structure_type": "上涨趋势" if directions[-1:] == ["up"] else "下跌趋势",
            "trend_label": "拉升段" if directions[-1:] == ["up"] else "回调段",
            "strokes": strokes,
            "strokes_count": len(strokes),
            "segments": [{"direction": directions[-1]}] if directions else [],
            "zones": [{"valid": True}] if len(directions) >= 3 else [],
            "buy_points": [],
            "sell_points": [],
            # 即使汇总串有值，薄 view 也只能认上面的引擎数组。
            "buy_point_text": "无",
        }
    }


@pytest.fixture
def up_view() -> dict:
    return build_chanlun_view(_engine_result(["up", "down", "up"]))


@pytest.fixture
def down_view() -> dict:
    return build_chanlun_view(_engine_result(["down", "up", "down"]))


def _plan(short_view: dict, midline_view: dict | None = None) -> dict:
    return {
        "name": "测试股",
        "code": "600000",
        "price": 12.34,
        "data_ok": True,
        "data_bars_daily": 250,
        "data_bars_weekly": 80,
        "adjust_mode": "qfq",
        "data_note": "日周数据齐",
        "short_view": short_view,
        "midline_view": midline_view or build_chanlun_view(
            _engine_result(["down", "up", "down"], timeframe="weekly")
        ),
    }


def test_cd4a_last_up_matches_card(up_view):
    text = render_chanlun_card(_plan(up_view))
    short = text.split("⏱ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert up_view["stroke_count"] == 3
    assert up_view["current_stroke_direction"] == "up"
    assert "笔 3｜当前笔 向上笔｜近笔 ↑↓↑" in short


def test_cd4b_last_down_matches_card(down_view):
    text = render_chanlun_card(_plan(down_view))
    short = text.split("⏱ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert down_view["stroke_count"] == 3
    assert down_view["current_stroke_direction"] == "down"
    assert "笔 3｜当前笔 向下笔｜近笔 ↓↑↓" in short


def test_cd4c_recent_sequence_is_engine_order():
    view = build_chanlun_view(_engine_result(["down", "up", "down", "up", "down", "up"]))
    assert view["stroke_count"] == 6
    assert view["recent_stroke_directions"] == ["up", "down", "up", "down", "up"]
    text = render_chanlun_card(_plan(view))
    assert "笔 6｜当前笔 向上笔｜近笔 ↑↓↑↓↑" in text


def test_midline_daily_fallback_is_explicit(up_view):
    fallback = build_chanlun_view(
        _engine_result(["up", "down", "up"], timeframe="daily_fallback")
    )
    text = render_chanlun_card(_plan(up_view, fallback))
    assert "⏱ 中线副读（日线 fallback）" in text
    assert "中线阶段：" not in text


def test_buy_sell_points_only_come_from_engine_arrays(up_view):
    empty = _engine_result(["up", "down", "up"])
    empty["chanlun"]["buy_point_text"] = "一类买"
    no_point_text = render_chanlun_card(_plan(build_chanlun_view(empty)))
    assert "买点 未形成" in no_point_text
    assert "一类买" not in no_point_text

    with_point = _engine_result(["up", "down", "up"])
    with_point["chanlun"]["buy_points"] = [{"type": "一类买", "price": 10.25}]
    point_text = render_chanlun_card(_plan(build_chanlun_view(with_point)))
    assert "买点 一类买 10.25" in point_text


def test_build_plan_uses_shared_snapshot_and_both_engines(monkeypatch):
    from trader_shared import chan_core, light_data
    from trader_shared.config import LOOKBACK_DAYS

    daily = [
        {"date": f"2026-01-{index + 1:02d}", "close": 10 + index / 10, "adjust": "qfq"}
        for index in range(20)
    ]
    weekly = [
        {"date": f"2025-{index + 1:02d}-01", "close": 9 + index / 10, "adjust": "qfq"}
        for index in range(20)
    ]
    snapshot = MarketSnapshot(
        security=Security(code="600000", market="SH", name="测试股"),
        quote={"current_price": 12.34, "change_pct": 1.2, "trade_date": "2026-01-20"},
        daily_bars=daily,
        weekly_bars=weekly,
    )
    calls: dict[str, object] = {}

    def fake_load(target, **kwargs):
        calls["target"] = target
        calls["load_kwargs"] = kwargs
        return snapshot

    def fake_short(current, bars, **kwargs):
        calls["short_bars"] = bars
        calls["short_weekly"] = kwargs["weekly_bars"]
        return _engine_result(["up", "down", "up"])

    def fake_midline(current, **kwargs):
        calls["mid_daily"] = kwargs["daily_bars"]
        calls["mid_weekly"] = kwargs["weekly_bars"]
        return _engine_result(["down", "up", "down"], timeframe="weekly")

    monkeypatch.setattr(light_data, "load_market_snapshot", fake_load)
    monkeypatch.setattr(chan_core, "chanlun_strategy", fake_short)
    monkeypatch.setattr(chan_core, "chanlun_strategy_midline", fake_midline)

    plan = build_chanlun_plan("测试股")
    assert calls["target"] == "测试股"
    assert calls["load_kwargs"] == {
        "days": LOOKBACK_DAYS,
        "include_5m": False,
        "include_weekly": True,
        "include_monthly": False,
        "include_ticks": False,
    }
    assert calls["short_bars"] == daily
    assert calls["short_weekly"] == weekly
    assert calls["mid_daily"] == daily
    assert calls["mid_weekly"] == weekly
    assert plan["data_bars_daily"] == 20
    assert plan["data_bars_weekly"] == 20
    assert plan["adjust_mode"] == "qfq"


def test_cd5_stdout_is_wechat_safe(monkeypatch, capsys, up_view):
    from trader_shared import chanlun_run

    monkeypatch.setattr(chanlun_run, "build_chanlun_plan", lambda target: _plan(up_view))
    assert chanlun_run.main(["--target", "测试股"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("缠论 — 测试股（600000）｜短中线结构卡")
    assert "#" not in output
    assert "**" not in output
    assert "|" not in output
    for forbidden in ("宜买", "可执行", "可低吸", "该买了", "三重共振买"):
        assert forbidden not in output


def test_cd4e_tip_leave_demotes_stale_up_stroke():
    """C-D4e：现价大幅低于末向上笔终点 → 不得再喊向上笔/拉升段。"""
    stale = _engine_result(["up", "down", "up"])
    stale["chanlun"]["strokes"][-1]["end_price"] = 187.0
    stale["chanlun"]["trend_label"] = "拉升段"
    view = build_chanlun_view(stale, current=95.0)
    assert view["current_stroke_direction"] == "up"  # 引擎原始末笔仍可核
    assert view["tip_leave"] == "up_left"
    text = render_chanlun_card(_plan(view))
    short = text.split("⏱ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert "高点已离开·向下未成笔" in short
    assert "当前笔 向上笔" not in short
    assert "走势 拉升段" not in short
