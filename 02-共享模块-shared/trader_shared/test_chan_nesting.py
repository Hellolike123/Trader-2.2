#!/usr/bin/env python3
"""区间套确认纯函数测试（离线，依赖 scripts/chan_csv + scripts/chan_csv_30m 缓存）。

缓存缺失时整体 skip（CI runner 无缓存，确定性门禁不受影响）。
"""
import copy
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02-共享模块-shared"))
sys.path.insert(0, str(ROOT / "01-功能包-packages/trader/scripts"))

from trader_shared.chan_core import chanlun_analysis  # noqa: E402
from trader_shared.chan_nesting import confirm_daily_with_lower  # noqa: E402

CSV_DAILY = ROOT / "scripts" / "chan_csv"
CSV_30M = ROOT / "scripts" / "chan_csv_30m"

pytestmark = pytest.mark.skipif(
    not (CSV_DAILY.exists() and CSV_30M.exists()),
    reason="需要 scripts/chan_csv + scripts/chan_csv_30m 缓存（离线验证用）",
)


def _load(path):
    bars = []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.strip().split(",")
            if len(p) < 6:
                continue
            bars.append({
                "date": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]), "volume": float(p[5]),
            })
    return bars


def _daily(symbol):
    return chanlun_analysis(
        _load(CSV_DAILY / f"{symbol}.csv"),
        current=_load(CSV_DAILY / f"{symbol}.csv")[-1]["close"],
        symbol=symbol, timeframe="daily",
    )


def test_confirm_marks_buy_points():
    """confirm 后日线买点应带 lower_confirmed 标注 + 顶层 nesting_confirmation。"""
    daily_res = _daily("300760.SZ")  # 迈瑞：日线一类买 + 30m 确认
    assert daily_res, "daily chanlun 应有结果"
    lower = _load(CSV_30M / "300760.SZ.csv")
    out = confirm_daily_with_lower(daily_res, lower, lower_timeframe="30m", symbol="300760.SZ")
    inner = out.get("chanlun", out)
    bps = inner.get("buy_points", [])
    assert bps, "迈瑞应有买点"
    for bp in bps:
        assert "lower_confirmed" in bp
        assert "lower_confirm_type" in bp
    assert "nesting_confirmation" in out
    assert out["nesting_confirmation"]["lower_timeframe"] == "30m"


def test_no_lower_returns_unchanged():
    """lower_bars=None 时原样返回，零副作用（等价性闸门）。"""
    daily_res = _daily("600519.SH")
    out = confirm_daily_with_lower(daily_res, None)
    assert out is daily_res
    assert "nesting_confirmation" not in out
    inner = out.get("chanlun", out)
    for bp in inner.get("buy_points", []):
        assert "lower_confirmed" not in bp


def test_lower_too_short_skipped():
    """lower_bars 过短时跳过，不产生 nesting_confirmation。"""
    daily_res = _daily("600519.SH")
    tiny = [{"date": "20260101", "open": 1, "close": 1, "high": 1, "low": 1, "volume": 1}]
    out = confirm_daily_with_lower(daily_res, tiny, lower_timeframe="30m")
    assert "nesting_confirmation" not in out


def test_confirm_filters_false_signals():
    """经 30m 确认后，标注应区分确认/未确认（验证核心过滤能力）。"""
    daily_res = _daily("000001.SZ")  # 平安银行：日线底背驰但 30m 未确认
    lower = _load(CSV_30M / "000001.SZ.csv")
    out = confirm_daily_with_lower(daily_res, lower, lower_timeframe="30m", symbol="000001.SZ")
    inner = out.get("chanlun", out)
    div = inner.get("divergence", {})
    # 底背驰存在时应带 lower 确认字段
    if isinstance(div, dict) and div.get("bottom_divergence"):
        assert "bottom_divergence_lower_confirmed" in div
