"""缠论 Skill 合同测试（C-D4a–c / C-D5 / C-B* slim）。"""
from __future__ import annotations

import pytest

from trader_shared.chanlun_render import render_chanlun_card, render_chanlun_slim
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
    short = text.split("⚡ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert up_view["stroke_count"] == 3
    assert up_view["current_stroke_direction"] == "up"
    assert "笔：3" in short
    assert "当前笔：向上笔" in short
    assert "近笔：↑↓↑" in short


def test_cd4b_last_down_matches_card(down_view):
    text = render_chanlun_card(_plan(down_view))
    short = text.split("⚡ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert down_view["stroke_count"] == 3
    assert down_view["current_stroke_direction"] == "down"
    assert "笔：3" in short
    assert "当前笔：向下笔" in short
    assert "近笔：↓↑↓" in short


def test_cd4c_recent_sequence_is_engine_order():
    view = build_chanlun_view(_engine_result(["down", "up", "down", "up", "down", "up"]))
    assert view["stroke_count"] == 6
    assert view["recent_stroke_directions"] == ["up", "down", "up", "down", "up"]
    text = render_chanlun_card(_plan(view))
    assert "笔：6" in text
    assert "当前笔：向上笔" in text
    assert "近笔：↑↓↑↓↑" in text


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
    assert "买点：未形成" in no_point_text
    assert "一类买" not in no_point_text

    with_point = _engine_result(["up", "down", "up"])
    with_point["chanlun"]["buy_points"] = [{"type": "一类买", "price": 10.25}]
    point_text = render_chanlun_card(_plan(build_chanlun_view(with_point)))
    assert "买点：一类买 10.25" in point_text
    assert "（观察）" not in point_text.split("买点：", 1)[1].split("\n", 1)[0]


def test_ot5_observe_tier_like_points_marked():
    """O-T5 / M-O1：类一/类二可见面须标（观察）。"""
    like2 = _engine_result(["up", "down", "up"])
    like2["chanlun"]["buy_points"] = [{"type": "类二买", "price": 346.16}]
    like2["chanlun"]["sell_points"] = [{"type": "类一卖", "price": 350.0}]
    text = render_chanlun_card(_plan(build_chanlun_view(like2)))
    assert "买点：类二买（观察） 346.16" in text
    assert "卖点：类一卖（观察） 350.00" in text
    for forbidden in ("宜买", "可执行", "可低吸", "该买了", "接近一买"):
        assert forbidden not in text

    soft1 = _engine_result(["up", "down", "up"])
    soft1["chanlun"]["buy_points"] = [
        {"type": "类一买", "price": 10.5},
        {"type": "类二买", "price": 11.0},
    ]
    multi = render_chanlun_card(_plan(build_chanlun_view(soft1)))
    assert "类一买（观察） 10.50" in multi
    assert "类二买（观察） 11.00" in multi


def test_ot5_formal_points_not_marked_observe():
    """O-T5 / M-O2：正式一类/二类/三类不得误标（观察）。"""
    formal = _engine_result(["up", "down", "up"])
    formal["chanlun"]["buy_points"] = [
        {"type": "一类买", "price": 10.25},
        {"type": "二类买", "price": 10.50},
        {"type": "三类买", "price": 10.75},
    ]
    formal["chanlun"]["sell_points"] = [
        {"type": "一类卖", "price": 12.0},
        {"type": "二类卖", "price": 12.5},
        {"type": "三类卖", "price": 13.0},
    ]
    text = render_chanlun_card(_plan(build_chanlun_view(formal)))
    buy_line = next(line for line in text.splitlines() if "买点：" in line)
    sell_line = next(line for line in text.splitlines() if "卖点：" in line)
    assert "（观察）" not in buy_line
    assert "（观察）" not in sell_line
    assert "一类买 10.25" in buy_line
    assert "二类买 10.50" in buy_line
    assert "三类买 10.75" in buy_line


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


def test_cd5_stdout_default_is_slim_b(monkeypatch, capsys, up_view):
    """C-B1 / C-B5：默认 B·中剪；微信红线。"""
    from trader_shared import chanlun_run

    monkeypatch.setattr(chanlun_run, "build_chanlun_plan", lambda target: _plan(up_view))
    monkeypatch.setattr(
        chanlun_run,
        "attach_change_and_persist_snapshot",
        lambda plan: {**plan, "change_line": "首次记录，暂无对比"},
    )
    assert chanlun_run.main(["--target", "测试股"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("测试股（600000）｜现价 12.34")
    assert "🧭 周线 · 结构副读" in output
    assert "⚡ 日线 · 本波" in output
    assert "🔮 推演" in output
    assert "#" not in output
    assert "**" not in output
    assert "|" not in output
    for forbidden in ("宜买", "可执行", "可低吸", "该买了", "三重共振买", "接近一买"):
        assert forbidden not in output


def test_cb6_brief_still_old_card(monkeypatch, capsys, up_view):
    """C-B6：--brief 仍出旧薄卡。"""
    from trader_shared import chanlun_run

    monkeypatch.setattr(chanlun_run, "build_chanlun_plan", lambda target: _plan(up_view))
    assert chanlun_run.main(["--target", "测试股", "--brief"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("缠论 — 测试股（600000）｜短中线结构卡")
    assert "📊 现况" in output


def test_cb1_slim_six_lamps_vertical(up_view):
    """C-B1：六灯竖排。"""
    text = render_chanlun_slim(_plan(up_view))
    daily = text.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    for lamp in ("一类买", "二类买", "三类买", "一类卖", "二类卖", "三类卖"):
        assert f"○ {lamp}" in daily or f"● {lamp}" in daily
    # 一行一灯：正式六灯各占一行
    lamp_lines = [ln for ln in daily.splitlines() if ln.strip().startswith(("●", "○"))]
    assert len(lamp_lines) >= 6


def test_cb2_no_points_all_empty_circles(up_view):
    """C-B2：无买卖点 → 六灯全 ○；无手补。"""
    text = render_chanlun_slim(_plan(up_view))
    daily = text.split("⚡ 日线 · 本波", 1)[1]
    for lamp in ("一类买", "二类买", "三类买", "一类卖", "二类卖", "三类卖"):
        assert f"○ {lamp}" in daily
    assert "● 一类买" not in daily
    assert "接近一买" not in text


def test_cb3_observe_like_appended_not_in_formal_slot():
    """C-B3：类二买仅观察追加；正式二类买仍 ○。"""
    like2 = _engine_result(["up", "down", "up"])
    like2["chanlun"]["buy_points"] = [{"type": "类二买", "price": 346.16}]
    text = render_chanlun_slim(_plan(build_chanlun_view(like2)))
    daily = text.split("⚡ 日线 · 本波", 1)[1]
    assert "○ 二类买" in daily
    assert "● 类二买（观察） 346.16" in daily


def test_cb4_midline_fallback_tagged(up_view):
    """C-B4：daily_fallback → 周线句含（日线）。"""
    fallback = build_chanlun_view(
        _engine_result(["up", "down", "up"], timeframe="daily_fallback")
    )
    text = render_chanlun_slim(_plan(up_view, fallback))
    weekly = text.split("🧭 周线 · 结构副读", 1)[1].split("⚡ 日线", 1)[0]
    assert "（日线）" in weekly


def test_slim_formal_buy_lights_and_pool(up_view):
    with_point = _engine_result(["up", "down", "up"])
    with_point["chanlun"]["buy_points"] = [{"type": "二类买", "price": 10.50}]
    plan = _plan(build_chanlun_view(with_point))
    text = render_chanlun_slim(plan)
    assert "● 二类买 10.50" in text
    assert "入池：建议入池" in text
    assert "可盯" in text.splitlines()[1]


def test_cd4e_tip_leave_demotes_stale_up_stroke():
    """C-D4e：现价大幅低于末向上笔终点 → 不得再喊向上笔/拉升段。"""
    stale = _engine_result(["up", "down", "up"])
    stale["chanlun"]["strokes"][-1]["end_price"] = 187.0
    stale["chanlun"]["trend_label"] = "拉升段"
    view = build_chanlun_view(stale, current=95.0)
    assert view["current_stroke_direction"] == "up"  # 引擎原始末笔仍可核
    assert view["tip_leave"] == "up_left"
    text = render_chanlun_card(_plan(view))
    short = text.split("⚡ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert "高点已离开·向下未成笔" in short
    assert "当前笔：向上笔" not in short
    assert "走势：拉升段" not in short


def test_wechat_layout_has_section_breaks_and_buy_first():
    """微信排版：分节空行 + 买卖点在结构之前。"""
    text = render_chanlun_card(
        _plan(build_chanlun_view(_engine_result(["up", "down", "up"])))
    )
    assert "\n\n📊 现况\n" in text
    assert "\n\n⚡ 短线（日）\n" in text
    short = text.split("⚡ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert short.index("买点：") < short.index("结构：")
    assert short.index("卖点：") < short.index("结构：")
    assert "|" not in text


def test_g_k3_zones_count_raw_and_pivot_count_merged():
    """G-K3 / C-DIFF-5 / M-G3：zones_count=raw、pivot_count=merged；面板可区分。"""
    engine = _engine_result(["up", "down", "up", "down", "up"])
    engine["chanlun"]["zones"] = [{"valid": True}, {"valid": True}]
    engine["chanlun"]["zones_count"] = 5  # raw 滑动窗
    engine["chanlun"]["pivot_count"] = 2  # 合并后中枢
    view = build_chanlun_view(engine)
    assert view["zones_count"] == 5
    assert view["pivot_count"] == 2
    assert view["zones_count"] != view["pivot_count"]

    text = render_chanlun_card(_plan(view))
    short = text.split("⚡ 短线（日）", 1)[1].split("⏱ 中线副读", 1)[0]
    assert "中枢：2｜窗5｜段：1" in short
    # 旧单口径「中枢：5｜段」不得冒充
    assert "中枢：5｜段" not in short
