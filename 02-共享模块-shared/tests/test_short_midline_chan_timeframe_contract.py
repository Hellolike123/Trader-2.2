"""契约测试：短线吃日线缠论，中线吃周线缠论。

锁死两条轨的周期路由，防止后续重构把两者混用：
- 短线（fusion / 短线专家）：ChanlunPlugin → chanlun_strategy(日线)，weekly 仅作 higher_trend 过滤
- 中线（🧭 / 周线关键价引擎）：chanlun_strategy_midline(周线)，周线不足才回退日线

不依赖网络与真实行情，全部走 monkeypatch。
"""

import sys
from pathlib import Path

# 让测试在 PYTHONPATH 未预设时也能 import trader_shared
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from trader_shared import chan_core
from trader_shared.plugins.chan_plugin import ChanlunPlugin
from trader_shared.plugin_registry import get_registry


# ── 测试夹具 ──────────────────────────────────────────────────────────────
def _make_bars(n: int, prefix: str, start: float = 10.0) -> list[dict]:
    """生成 n 根 K，date 用 prefix 区分日线/周线，保证内容可区分。"""
    bars = []
    for i in range(n):
        p = start + i * 0.1
        bars.append(
            {
                "date": f"{prefix}-{i:02d}",
                "open": round(p, 2),
                "high": round(p + 0.5, 2),
                "low": round(p - 0.5, 2),
                "close": round(p + 0.2, 2),
                "volume": 1000 + i,
            }
        )
    return bars


@pytest.fixture
def daily_bars():
    return _make_bars(30, "D")


@pytest.fixture
def weekly_bars():
    return _make_bars(40, "W")


@pytest.fixture
def quote():
    return {"symbol": "600000.SH", "trade_date": "2026-07-15", "current_price": 13.0}


# ── 测试 1：中线内部确实在周线上跑笔段（而非日线） ──────────────────────────
def test_midline_uses_weekly_bars(monkeypatch, daily_bars, weekly_bars):
    seen = {}

    def _fake_analysis(bars, *args, **kwargs):
        seen["bars"] = bars
        return {"structure_type": "up", "structure_confidence": "high",
                "trend_label": "上涨", "divergence": {}, "buy_points": [],
                "sell_points": []}

    monkeypatch.setattr(chan_core, "chanlun_analysis", _fake_analysis)

    out = chan_core.chanlun_strategy_midline(
        13.0, weekly_bars, daily_bars, quote={"trade_date": "2026-07-15"}
    )

    assert seen["bars"] is weekly_bars, "中线 chanlun_analysis 应吃到周线，而非日线"
    inner = out.get("chanlun", out)
    assert inner.get("timeframe") == "weekly", "周线充足时 timeframe 应为 weekly"


# ── 测试 2：中线周线不足时回退日线（回归保护） ─────────────────────────────
def test_midline_falls_back_to_daily_when_weekly_short(monkeypatch, daily_bars):
    short_weekly = _make_bars(5, "W")  # < CHANLUN_MIN_BARS(20)
    seen = {}

    def _fake_analysis(bars, *args, **kwargs):
        seen["bars"] = bars
        return {"structure_type": "", "structure_confidence": "low",
                "trend_label": "数据不足", "divergence": {}, "buy_points": [],
                "sell_points": []}

    monkeypatch.setattr(chan_core, "chanlun_analysis", _fake_analysis)

    out = chan_core.chanlun_strategy_midline(
        13.0, short_weekly, daily_bars, quote={"trade_date": "2026-07-15"}
    )

    assert seen["bars"] is daily_bars, "周线不足应回退到日线"
    inner = out.get("chanlun", out)
    assert inner.get("timeframe") == "daily_fallback", "回退时 timeframe 应为 daily_fallback"


# ── 测试 3：短线 ChanlunPlugin 路由到日线，weekly 仅作过滤 ──────────────────
def test_shortline_plugin_routes_to_daily(monkeypatch, daily_bars, weekly_bars, quote):
    calls = {}

    def _fake_strategy(current, bars, change_pct=None, quote=None,
                       symbol=None, analysis_date=None, weekly_bars=None):
        calls["args"] = (current, bars, change_pct, quote)
        calls["weekly"] = weekly_bars
        return {"chanlun": {"timeframe": "daily"}}

    monkeypatch.setattr(chan_core, "chanlun_strategy", _fake_strategy)

    ChanlunPlugin().analyze(13.0, daily_bars, 0.5, quote, weekly_bars=weekly_bars)

    assert calls["args"][1] is daily_bars, "短线 ChanlunPlugin 应把日线传给 chanlun_strategy"
    assert calls["weekly"] is weekly_bars, "weekly_bars 应作为 higher_trend 过滤透传，不是主序列"


# ── 测试 4：组合点 analyze_all 整体路由（最贴近生产的契约） ─────────────────
def test_analyze_all_routes_short_daily_mid_weekly(monkeypatch, daily_bars, weekly_bars, quote):
    short_calls, mid_calls = {}, {}

    def _fake_short(current, bars, change_pct=None, quote=None,
                    symbol=None, analysis_date=None, weekly_bars=None):
        short_calls["bars"] = bars
        short_calls["weekly"] = weekly_bars
        return {"chanlun": {"timeframe": "daily"}}

    def _fake_mid(current, weekly_bars=None, daily_bars=None, change_pct=None,
                  quote=None, symbol=None, analysis_date=None):
        mid_calls["weekly"] = weekly_bars
        mid_calls["daily"] = daily_bars
        return {"chanlun": {"timeframe": "weekly"}}

    # 缠论两条路由
    monkeypatch.setattr(chan_core, "chanlun_strategy", _fake_short)
    monkeypatch.setattr(chan_core, "chanlun_strategy_midline", _fake_mid)
    # 非缠论策略打桩，避免无关计算、保速度
    monkeypatch.setattr("trader_shared.wyckoff_core.wyckoff_strategy",
                        lambda *a, **k: {"direction": 0})
    monkeypatch.setattr("trader_shared.wyckoff_core.wyckoff_strategy_midline",
                        lambda *a, **k: {"direction": 0})

    registry = get_registry()
    registry.analyze_all(13.0, daily_bars, 0.5, quote,
                         weekly_bars=weekly_bars, midline=True)

    # 短线：chanlun_strategy 主序列 = 日线
    assert short_calls.get("bars") is daily_bars, "analyze_all 应把日线喂给短线缠论"
    assert short_calls.get("weekly") is weekly_bars, "短线 weekly 仅作过滤透传"
    # 中线：chanlun_strategy_midline 主序列 = 周线
    assert mid_calls.get("weekly") is weekly_bars, "analyze_all 应把周线喂给中线缠论"
    assert mid_calls.get("daily") is daily_bars, "中线日线应作为 fallback 透传"
