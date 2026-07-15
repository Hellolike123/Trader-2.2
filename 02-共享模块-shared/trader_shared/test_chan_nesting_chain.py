#!/usr/bin/env python3
"""多级别区间套（30m→5m→1m）纯函数测试：自包含、离线可跑（CI 门禁可用）。

不依赖 scripts/chan_csv 缓存：用 monkeypatch 控制 chanlun_analysis 的小级别返回值，
精确验证 confirm_nested_chain 的逐级 AND 聚合与等价性闸门。
"""
import copy

import pytest

from trader_shared.chan_nesting import confirm_nested_chain  # noqa: E402

# 构造一个"日线买点"结果（绕开真实 chanlun，直接造内层）
_DAILY = {"chanlun": {"buy_points": [{"price": 100.0, "type": "一类买"}],
                      "divergence": {"bottom_divergence": True}}}


def _tiny_bars():
    return [{"date": "20260101", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1}]


def _series(n):
    """n 根最小有效 bar，长度足以通过 min_lower_bars(60) 之外——这里仅占位，真正逻辑靠 monkeypatch。"""
    return [{"date": f"2026{i:02d}01", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1}
            for i in range(n)]


@pytest.fixture
def fake_chanlun(monkeypatch):
    """控制小级别 chanlun 返回值。

    通过 environ 风格的全局控制不优雅，改为：返回一个 callable，
    调用方在测试里再 setattr 覆盖。这里给出默认实现（无买点）。
    """
    def _default(bars, current=None, symbol=None, timeframe=None):
        return {"chanlun": {"buy_points": [], "divergence": {}}}
    monkeypatch.setattr("trader_shared.chan_nesting.chanlun_analysis", _default)
    return _default


def test_nested_chain_multi_level_and_logic(fake_chanlun, monkeypatch):
    """30m✓ + 5m✓ + 1m✗ → 各级标注正确，nesting_confirmed=False（AND 语义）。"""
    def _ctl(bars, current=None, symbol=None, timeframe=None):
        if timeframe in ("30m", "5m"):
            return {"chanlun": {"buy_points": [{"price": 100.5, "type": "一类买"}], "divergence": {}}}
        return {"chanlun": {"buy_points": [], "divergence": {}}}
    monkeypatch.setattr("trader_shared.chan_nesting.chanlun_analysis", _ctl)

    series = [("30m", _series(80)), ("5m", _series(80)), ("1m", _series(80))]
    out = confirm_nested_chain(copy.deepcopy(_DAILY), series, symbol="X")
    bp = out["chanlun"]["buy_points"][0]
    assert bp["nesting_chain"][0] == {"timeframe": "30m", "confirmed": True, "type": "一类买"}
    assert bp["nesting_chain"][1] == {"timeframe": "5m", "confirmed": True, "type": "一类买"}
    assert bp["nesting_chain"][2] == {"timeframe": "1m", "confirmed": False, "type": ""}
    assert bp["nesting_confirmed"] is False
    # 兼容旧渲染：lower_confirmed 取自首个可用级别 30m
    assert bp["lower_confirmed"] is True
    assert out["nesting_confirmation"]["levels"] == ["30m", "5m", "1m"]
    assert out["nesting_confirmation"]["confirmed_count"] == 0


def test_nested_chain_all_confirmed(fake_chanlun, monkeypatch):
    """30m✓ + 5m✓ + 1m✓ → nesting_confirmed=True（T0 高置信）。"""
    def _ctl(bars, current=None, symbol=None, timeframe=None):
        return {"chanlun": {"buy_points": [{"price": 99.9, "type": "一类买"}], "divergence": {}}}
    monkeypatch.setattr("trader_shared.chan_nesting.chanlun_analysis", _ctl)

    series = [("30m", _series(80)), ("5m", _series(80)), ("1m", _series(80))]
    out = confirm_nested_chain(copy.deepcopy(_DAILY), series, symbol="X")
    bp = out["chanlun"]["buy_points"][0]
    assert all(lv["confirmed"] for lv in bp["nesting_chain"])
    assert bp["nesting_confirmed"] is True
    assert out["nesting_confirmation"]["confirmed_count"] == 1


def test_nested_chain_empty_series_unchanged(fake_chanlun):
    """lower_series=[] → 原样返回，零副作用（等价性闸门）。"""
    daily = copy.deepcopy(_DAILY)
    out = confirm_nested_chain(daily, [])
    assert out is daily
    assert "nesting_confirmation" not in out
    assert "nesting_chain" not in out["chanlun"]["buy_points"][0]


def test_nested_chain_all_levels_skipped(fake_chanlun):
    """所有级别 bars 过短 → 全部 skipped，无 nesting_confirmation（等价性闸门）。"""
    out = confirm_nested_chain(copy.deepcopy(_DAILY), [("5m", _tiny_bars()), ("1m", _tiny_bars())])
    assert "nesting_confirmation" not in out
    assert out["chanlun"]["buy_points"][0].get("nesting_chain") is None


def test_nested_chain_single_30m_behaves_like_daily(fake_chanlun, monkeypatch):
    """仅 30m 一级时退化：与 confirm_daily_with_lower 行为一致（lower_confirmed 来自 30m）。"""
    def _ctl(bars, current=None, symbol=None, timeframe=None):
        return {"chanlun": {"buy_points": [{"price": 100.2, "type": "类二买"}], "divergence": {}}}
    monkeypatch.setattr("trader_shared.chan_nesting.chanlun_analysis", _ctl)

    out = confirm_nested_chain(copy.deepcopy(_DAILY), [("30m", _series(80))], symbol="X")
    bp = out["chanlun"]["buy_points"][0]
    assert bp["lower_confirmed"] is True
    assert bp["lower_confirm_type"] == "类二买"
    assert bp["nesting_chain"] == [{"timeframe": "30m", "confirmed": True, "type": "类二买"}]


def test_nested_chain_bottom_divergence_and_logic(fake_chanlun, monkeypatch):
    """底背驰需所有级别确认：30m✓ + 5m✗ → bottom_divergence_lower_confirmed=False。"""
    def _ctl(bars, current=None, symbol=None, timeframe=None):
        if timeframe == "30m":
            return {"chanlun": {"buy_points": [], "divergence": {"bottom_divergence": True}}}
        return {"chanlun": {"buy_points": [], "divergence": {}}}
    monkeypatch.setattr("trader_shared.chan_nesting.chanlun_analysis", _ctl)

    out = confirm_nested_chain(copy.deepcopy(_DAILY), [("30m", _series(80)), ("5m", _series(80))], symbol="X")
    div = out["chanlun"]["divergence"]
    assert div["bottom_divergence_lower_confirmed"] is False
    assert out["nesting_confirmation"]["bottom_divergence_confirmed"] is False
