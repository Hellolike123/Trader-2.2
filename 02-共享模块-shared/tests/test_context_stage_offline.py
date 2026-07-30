# -*- coding: utf-8 -*-
"""context_stage 离线缝：frozen snapshot 不得赋值。"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class _FrozenSnap:
    data_status: str = "full"
    quote: dict[str, Any] = field(default_factory=dict)
    daily_bars: list = field(default_factory=list)
    bars_5m: list = field(default_factory=list)
    weekly_bars: list = field(default_factory=list)
    monthly_bars: list = field(default_factory=list)
    missing_sources: list = field(default_factory=list)
    source_errors: dict = field(default_factory=dict)
    fetched_at: str = ""
    data_freshness: str = "live"


def test_context_stage_partial_without_mutating_frozen_snapshot(monkeypatch):
    import trader_shared.report_pipeline.context_stage as cs
    from trader_shared.report_pipeline.context_stage import run_analysis_context_stage

    bars = [
        {
            "date": f"2026-07-{i:02d}",
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0 + i * 0.01,
            "volume": 1000,
            "atr14": 0.3,
            "atr_ratio": 0.02,
            "adjust": "qfq",
            "data_source": "tencent",
        }
        for i in range(1, 25)
    ]
    quote: dict[str, Any] = {"name": "测试", "symbol": "sh600000"}  # 无 current_price
    snap = _FrozenSnap(data_status="full", quote=quote, daily_bars=bars)

    class _FakeFut:
        def __init__(self, val=None):
            self._val = val if val is not None else {}

        def result(self, timeout=None):
            return self._val

    class _FakePool:
        def submit(self, fn, *a, **k):
            return _FakeFut({})

    monkeypatch.setattr("trader_shared.cache_utils.get_shared_build_pool", lambda: _FakePool())
    monkeypatch.setattr(cs, "detect_risk_flags", lambda *a, **k: [])
    monkeypatch.setattr(cs, "build_live_bar_anchor", lambda *a, **k: (None, None))
    monkeypatch.setattr(
        "trader_shared.indicator_math.calc_supertrend",
        lambda *a, **k: {"direction": None},
    )
    monkeypatch.setattr("trader_shared.indicator_math.calc_vwap", lambda *a, **k: {})
    monkeypatch.setattr(
        "trader_shared.signal_core.read_signals_for_report",
        lambda *a, **k: (0.0, None),
    )
    monkeypatch.setattr(
        "trader_shared.get_env_for_skill",
        lambda *a, **k: {"level": "未知", "hmm_regime_en": "range"},
    )

    class _Reg:
        def analyze_all(self, *a, **k):
            return {"chanlun": {}, "momentum": {}, "wyckoff": {}}

    monkeypatch.setattr("trader_shared.plugin_registry.get_registry", lambda: _Reg())
    monkeypatch.setenv("TRADER_CHAN_NESTING", "0")

    out = run_analysis_context_stage(
        target="600000",
        snapshot=snap,
        bars=bars,
        quote=quote,
        sec=type("S", (), {"ts_code": "600000.SH", "name": "测试"})(),
        provider=object(),
        mark=None,
    )
    assert out["data_status"] == "partial"
    assert abs(out["current"] - float(bars[-1]["close"])) < 1e-9
    assert snap.data_status == "full"
