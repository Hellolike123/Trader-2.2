"""W-01：阶段机滑窗须透传 timeframe，周线不得默默用日线参数。"""
from __future__ import annotations

from trader_shared.wyckoff_phase import _scan_for_signal


def test_w01_scan_for_signal_passes_timeframe_to_detector():
    seen: dict = {}

    def _fake_detector(bars, tr_ctx=None, *, timeframe="daily", is_index=False):
        seen["timeframe"] = timeframe
        seen["is_index"] = is_index
        seen["tr_ctx"] = tr_ctx
        return {"sc_signal": False}

    bars = [{"close": 10.0 + i * 0.01} for i in range(40)]
    tr = {"in_tr": True}
    _scan_for_signal(
        bars,
        _fake_detector,
        window=15,
        step=5,
        max_lookback_bars=30,
        tr_ctx=tr,
        timeframe="weekly",
        is_index=False,
    )
    assert seen["timeframe"] == "weekly"
    assert seen["is_index"] is False
    assert seen["tr_ctx"] is tr


def test_w01_scan_for_signal_falls_back_when_detector_ignores_timeframe():
    """无 timeframe 形参的检测器仍可被滑窗调用。"""
    calls = {"n": 0}

    def _legacy(bars, tr_ctx=None):
        calls["n"] += 1
        return {"bc_signal": False}

    bars = [{"close": 10.0} for _ in range(20)]
    assert _scan_for_signal(bars, _legacy, window=10, step=5, timeframe="weekly") is False
    assert calls["n"] >= 1
