"""周线扫描窗缩放 S1 + S3（wyckoff-weekly-scan-windows-handoff）。"""
from __future__ import annotations

from trader_shared.config import WYCKOFF_ST_SC_MAX_BARS
from trader_shared.wyckoff_events import (
    _detect_secondary_test_sc,
    _scan_last_event,
    _st_sc_max_bars_for_tf,
)
from trader_shared.wyckoff_phase import _tf_scan_params


def _bar(o, h, l, c, v=1000):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_w_s1a_tf_scan_params_weekly_half():
    """W-S1a：周线 window/max_lookback 半幅。"""
    w, mlb = _tf_scan_params("weekly", 15, 30)
    assert w == 8  # ceil(15/2)
    assert mlb == 15  # ceil(30/2)
    w2, mlb2 = _tf_scan_params("daily", 15, 30)
    assert w2 == 15 and mlb2 == 30
    w3, mlb3 = _tf_scan_params("weekly", 20, 40)
    assert w3 == 10 and mlb3 == 20


def test_w_s1b_scan_last_event_short_series_fallback():
    """W-S1b：n < window 时不得恒 (-1, None)；整段试探可命中。"""

    def _always_signal(bars, tr_ctx=None, *, timeframe="daily", is_index=False):
        return {"spring_signal": True}

    bars = [_bar(10, 11, 9, 10) for _ in range(12)]
    idx, res = _scan_last_event(
        bars, _always_signal, None, window=15, step=1, timeframe="weekly"
    )
    assert idx == 11
    assert res is not None
    assert res.get("spring_signal") is True


def test_w_s1c_detect_phase_uses_scaled_window(monkeypatch):
    """W-S1c：周线 _detect_phase 滑窗调用经半幅缩放。"""
    from trader_shared import wyckoff_phase as wp

    seen_windows: list[int] = []
    real_scan = wp._scan_for_signal

    def _spy(bars, detector_fn, window=15, step=5, max_lookback_bars=None, **kw):
        seen_windows.append(int(window))
        return real_scan(
            bars,
            detector_fn,
            window=window,
            step=step,
            max_lookback_bars=max_lookback_bars,
            **kw,
        )

    monkeypatch.setattr(wp, "_scan_for_signal", _spy)
    # 过质量门：给够 TR + forming，使滑窗路径执行
    bars = [_bar(90, 91, 89, 90, 100) for _ in range(20)]
    signals = {
        "sc_signal": True,
        "ar_signal": True,
        "spring_signal": False,
        "sos_signal": False,
        "lps_signal": False,
        "bc_signal": False,
        "upthrust_signal": False,
        "sow_signal": False,
        "are_signal": False,
        "compression_signal": False,
        "trend_pullback_signal": False,
        "trend_rally_signal": False,
        "st_signal": False,
        "lpsy_signal": False,
    }
    tr_ctx = {
        "tr_quality": 0.8,
        "phase_a_status": "established",
        "in_tr": True,
    }
    wp._detect_phase(
        bars, signals, _phase_lookback=12, tr_ctx=tr_ctx, timeframe="weekly"
    )
    assert seen_windows, "expected phase machine to call _scan_for_signal"
    # 日线默认 15 → 周线 8；不得再出现未缩放的 15/16/20
    assert all(w <= 10 for w in seen_windows), seen_windows
    assert 8 in seen_windows or 9 in seen_windows or 10 in seen_windows


def test_w_s3_helper_weekly_half():
    assert _st_sc_max_bars_for_tf("daily") == int(WYCKOFF_ST_SC_MAX_BARS)
    assert _st_sc_max_bars_for_tf("weekly") == max(8, (int(WYCKOFF_ST_SC_MAX_BARS) + 1) // 2)
    assert _st_sc_max_bars_for_tf("weekly") == 11  # 22 → 11


def _sc_ar_st_at_offset(offset_from_st_start: int) -> list[dict]:
    """SC+AR 后，在 ST 窗起点起第 offset 根放合格 ST（0=AR+3）。"""
    bars = [_bar(90.0, 91.0, 89.0, 90.0, 100) for _ in range(14)]
    bars.append(_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
    bars.append(_bar(83.5, 87.0, 85.0, 86.0, 400))  # AR
    bars.append(_bar(85.2, 85.6, 85.0, 85.3, 120))  # AR+1
    bars.append(_bar(85.1, 85.5, 84.9, 85.2, 120))  # AR+2
    for _ in range(offset_from_st_start):
        bars.append(_bar(85.5, 86.0, 85.2, 85.7, 110))
    bars.append(_bar(82.2, 83.2, 81.8, 82.9, 800))  # ST
    for _ in range(2):
        bars.append(_bar(85.0, 85.4, 84.8, 85.2, 120))
    return bars


def test_w_s3a_late_st_rejected_on_weekly_accepted_on_daily():
    """W-S3a：ST 在窗起点+11（周线半幅外、日线窗内）→ 周否日可。"""
    bars = _sc_ar_st_at_offset(11)
    daily = _detect_secondary_test_sc(bars, timeframe="daily")
    weekly = _detect_secondary_test_sc(bars, timeframe="weekly")
    assert daily.get("secondary_test_sc_signal") is True
    assert weekly.get("secondary_test_sc_signal") is not True


def test_w_s3b_early_st_accepted_on_weekly():
    """W-S3b：ST 在半幅内（窗起点+5）→ 周线可认。"""
    bars = _sc_ar_st_at_offset(5)
    weekly = _detect_secondary_test_sc(bars, timeframe="weekly")
    assert weekly.get("secondary_test_sc_signal") is True
