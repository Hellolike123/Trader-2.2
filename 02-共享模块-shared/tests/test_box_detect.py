"""箱体检测独立模块单测（严格按 A股 箱体实务规则）。

锁定 detect_box 的：
  - 有效性校验（跨度/振幅/触及次数/平行/MA）
  - 状态机（inside / up_pending / up_confirmed / down_confirmed）
  - 假突破识别
  - 价格位置 / 止损位
  - 数据不足与无效大振幅的兜底
"""
from __future__ import annotations

import pytest

from trader_shared.box_detect import (
    BREAKOUT_VOL_RATIO,
    MIN_SPAN_DAYS,
    TOUCH_TOL_PCT,
    _cluster_rail,
    _rail_slope_pct,
    detect_box,
)


# ── 测试数据生成 ───────────────────────────────────────────────
def _box_bars(n_peaks: int, top: float = 100.0, bottom: float = 90.0,
              period: int = 8, vol: float = 1000.0) -> list[dict]:
    """生成在 (bottom, top) 间反复震荡的 OHLCV 序列。

    高序列在每周期 phase 0 处刺到 top（局部极大），
    低序列在每周期 phase half 处刺到 bottom（局部极小），
    间隔 period≥8 ≥ 2*min_gap+1，保证每个极值独立。
    """
    bars: list[dict] = []
    half = period // 2
    for p in range(n_peaks):
        # 最后一期只画到下沿(phase=half)，避免末根成为高序列的边界局部极大，
        # 否则会把 99.x 的伪影并入 100 的簇、拉低顶轨均值。
        last_phase = half if p == n_peaks - 1 else period - 1
        for i in range(last_phase + 1):
            hi_dist = min(i, period - i)
            high = top - 2.0 * (hi_dist / half)
            lo_dist = min(abs(i - half), period - abs(i - half))
            low = bottom + 2.0 * (lo_dist / half)
            close = (high + low) / 2.0
            bars.append({
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": vol,
            })
    return bars


def _append_close(bars: list[dict], close: float, vol: float,
                  high_pad: float = 0.5, low_pad: float = 0.5) -> None:
    """在序列末尾追加一根 bar（用于构造突破/破位）。"""
    bars.append({
        "high": round(close + high_pad, 2),
        "low": round(close - low_pad, 2),
        "close": round(close, 2),
        "volume": vol,
    })


# ── 1. 有效箱体（inside）─────────────────────────────────────
def test_valid_inside_box():
    bars = _box_bars(n_peaks=6)            # 48 根，跨度≥40
    r = detect_box(bars)
    assert r["found"] is True
    assert r["valid"] is True
    assert r["top"] == 100.0
    assert r["bottom"] == 90.0
    assert r["amplitude_pct"] == pytest.approx(11.11, abs=0.05)
    assert r["span_days"] >= MIN_SPAN_DAYS
    assert r["top_touches"] >= 3 and r["bottom_touches"] >= 3
    assert r["state"] == "inside"
    # 现价取末根 close（下沿附近 ≈94）→ 位置应在 35~65%
    assert 35 <= r["position_pct"] <= 65
    # 止损 = 下沿下方 1%
    assert r["stop_loss"] == pytest.approx(89.1, abs=0.01)
    assert r["false_breakout_risk"] is False


# ── 2. 向上突破确认 ─────────────────────────────────────────
def test_up_confirmed():
    bars = _box_bars(n_peaks=6)
    # 连续 2 日收盘站上 top_break=103，量比 ≥1.5x（ma20_vol≈1000）
    _append_close(bars, 104.0, vol=2000.0)
    _append_close(bars, 105.0, vol=2000.0)
    r = detect_box(bars)
    assert r["found"] is True
    assert r["state"] == "up_confirmed"
    assert r["breakout"]["direction"] == "up"
    assert r["breakout"]["confirm"] is True
    assert r["breakout"]["hold_days"] >= 2
    assert r["breakout"]["vol_ratio"] >= BREAKOUT_VOL_RATIO
    assert r["volume_context"] == "accumulate"


# ── 3. 向上突破待确认（量能不足）───────────────────────────
def test_up_pending_volume_gate():
    bars = _box_bars(n_peaks=6)
    # 连续 2 日站上沿，但量能仅持平（<1.5x）→ 待确认
    _append_close(bars, 104.0, vol=1000.0)
    _append_close(bars, 105.0, vol=1000.0)
    r = detect_box(bars)
    assert r["state"] == "up_pending"
    assert r["breakout"]["confirm"] is False
    assert r["breakout"]["vol_ratio"] < BREAKOUT_VOL_RATIO


# ── 4. 向下破位确认 ─────────────────────────────────────────
def test_down_confirmed():
    bars = _box_bars(n_peaks=6)
    # 连续 2 日收盘跌破 bot_break=87.3（缩量阴跌也算有效）
    _append_close(bars, 86.0, vol=900.0)
    _append_close(bars, 85.0, vol=900.0)
    r = detect_box(bars)
    assert r["found"] is True
    assert r["state"] == "down_confirmed"
    assert r["breakout"]["direction"] == "down"
    assert r["breakout"]["confirm"] is True


# ── 5. 假突破识别（刺穿回落 + 单日脉冲）────────────────────
def test_false_breakout():
    bars = _box_bars(n_peaks=6)
    # 末根 high 刺穿上沿(>100) 但收盘回落(≤100)，量能 ≥2x 脉冲
    bars.append({
        "high": 102.0,
        "low": 99.5,
        "close": 99.0,
        "volume": 2500.0,
    })
    r = detect_box(bars)
    assert r["state"] == "inside"          # 收盘未站上
    assert r["false_breakout_risk"] is True


# ── 6. 数据不足兜底 ─────────────────────────────────────────
def test_insufficient_data():
    bars = _box_bars(n_peaks=2)            # 仅 16 根 < 40
    r = detect_box(bars)
    assert r["found"] is False
    assert r["valid"] is False
    assert r["top"] is None
    assert r["bottom"] is None


# ── 7. 振幅过大 → 箱体无效 ─────────────────────────────────
def test_invalid_amplitude():
    # 上下沿差距过大（振幅 66% > 20%）→ found 但 valid=False
    bars = _box_bars(n_peaks=6, top=100.0, bottom=60.0)
    r = detect_box(bars)
    assert r["found"] is True
    assert r["valid"] is False
    assert r["amplitude_pct"] > 20.0
    assert "有效性未全部满足" in r["note"] or "仅供参考" in r["note"]


# ── 8. _cluster_rail 取触点最多的簇 ─────────────────────────
def test_cluster_rail_picks_max_count():
    # 6 个 100 附近 + 2 个 105 → 应选中 100 簇
    pts = [(i, 100.0) for i in range(0, 60, 10)]
    pts += [(100, 105.0), (110, 106.0)]
    mean, cnt, _ = _cluster_rail(pts, TOUCH_TOL_PCT)
    assert cnt == 6
    assert mean == pytest.approx(100.0, abs=0.01)


# ── 9. _rail_slope_pct 平行轨道斜率≈0 ──────────────────────
def test_rail_slope_flat():
    pts = [(i, 100.0) for i in range(0, 50, 10)]
    assert abs(_rail_slope_pct(pts)) < 1e-6
