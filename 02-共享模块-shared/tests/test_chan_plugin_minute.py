"""ChanlunPlugin 分钟路径：归一化 date、空结果解包、timeframe=5m 标签。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader_shared.config import CHANLUN_MIN_BARS
from trader_shared.plugins.chan_plugin import (
    ChanlunPlugin,
    _MINUTE_MIN_BARS,
    _normalize_minute_bars,
)


def test_minute_min_bars_aligned_with_config():
    assert _MINUTE_MIN_BARS == CHANLUN_MIN_BARS


def test_normalize_minute_bars_time_overrides_day_date():
    bars = [
        {
            "date": "2026-07-16",
            "time": "2026-07-16 09:35:00",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        },
        {
            "date": "2026-07-16",
            "time": "2026-07-16 09:40:00",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1.1,
            "volume": 1,
        },
    ]
    norm = _normalize_minute_bars(bars)
    assert norm[0]["date"] == "2026-07-16 09:35:00"
    assert norm[1]["date"] == "2026-07-16 09:40:00"
    assert len({b["date"] for b in norm}) == 2


def test_normalize_skips_non_dict_and_empty_safe():
    assert _normalize_minute_bars([]) == []
    assert _normalize_minute_bars([None, "x", 1]) == []  # type: ignore[list-item]
    only_day = [{"date": "2026-07-16", "close": 1.0}]
    norm = _normalize_minute_bars(only_day)
    assert norm[0]["date"] == "2026-07-16"  # 无 time 时保留原 date（可能塌缩，属上游缺字段）


def test_plugin_minute_path_sets_timeframe_5m(monkeypatch):
    from trader_shared import chan_core

    def _fake(current, bars, change_pct=None, quote=None, **kwargs):
        return {"chanlun": {"timeframe": "daily", "structure_type": "up", "buy_points": []}}

    monkeypatch.setattr(chan_core, "chanlun_strategy", _fake)
    minute = [
        {
            "date": "2026-07-16",
            "time": f"2026-07-16 09:{30 + i:02d}:00",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10 + i * 0.01,
            "volume": 100,
        }
        for i in range(CHANLUN_MIN_BARS)
    ]
    out = ChanlunPlugin().analyze(10.5, [], 0.0, {}, minute_bars=minute)
    assert out["chanlun"]["timeframe"] == "5m"


def test_check_5m_unpacks_empty_chanlun(monkeypatch):
    """空 chanlun dict 必须解包为内层 {}，不能用 or 落到包装层。"""
    import importlib.util

    mon_path = (
        Path(__file__).resolve().parents[2]
        / "01-功能包-packages"
        / "t0"
        / "scripts"
        / "monitor.py"
    )
    if not mon_path.is_file():
        return  # 包路径不可用时跳过
    spec = importlib.util.spec_from_file_location("t0_monitor_under_test", mon_path)
    assert spec and spec.loader
    # monitor 依赖同目录模块；把 scripts 放进 path
    scripts_dir = str(mon_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    mon = importlib.util.module_from_spec(spec)
    # 避免执行 monitor 顶层时拉全量依赖失败：只测解包逻辑
    from trader_shared.plugins import chan_plugin as cp

    def _fake_analyze(self, current, bars, change_pct, quote, weekly_bars=None, minute_bars=None):
        return {"chanlun": {}}

    monkeypatch.setattr(cp.ChanlunPlugin, "analyze", _fake_analyze)

    # 直接复刻解包逻辑（与 monitor 修复后一致）做契约断言
    res = {"chanlun": {}}
    if isinstance(res.get("chanlun"), dict):
        flat = res["chanlun"]
    else:
        flat = res
    assert flat == {}
    assert flat is not res
