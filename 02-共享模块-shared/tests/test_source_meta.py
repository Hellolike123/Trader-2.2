"""D5 / #4 数据源溯源 _meta 单测（零网络，合同锁定）。"""
from __future__ import annotations

from types import SimpleNamespace

from trader_shared.light_data import _mark_cached, build_source_meta


def _bar(src="tencent-http", vol="lot", cached=False):
    b = {"date": "2026-08-07", "close": 10.0, "data_source": src, "vol_unit": vol}
    if cached:
        b["cached"] = True
    return b


def _fake_provider(backend="mootdx"):
    return SimpleNamespace(_backend=backend)


def _fake_snapshot(daily=None, b5m=None, wk=None):
    return SimpleNamespace(daily_bars=daily, bars_5m=b5m, weekly_bars=wk)


def test_mark_cached_stamps_first_bar_and_returns_new_list():
    src = [{"date": "2026-08-07", "close": 1.0}]
    out = _mark_cached(src)
    assert out is not src  # 返回新列表，不污染入参
    assert out[0].get("cached") is True
    assert "cached" not in src[0]  # 原对象未被改


def test_mark_cached_passthrough_on_empty_or_none():
    assert _mark_cached([]) == []
    assert _mark_cached(None) is None


def test_build_source_meta_reads_real_data_source_and_vol_unit():
    snap = _fake_snapshot(
        daily=[_bar("mootdx", "lot")],
        b5m=[_bar("sina", "lot")],
        wk=[_bar("tencent-qfq-week", "lot")],
    )
    meta = build_source_meta(snap, _fake_provider("mootdx"))
    assert meta["daily_source"] == "mootdx"
    assert meta["5m_source"] == "sina"
    assert meta["weekly_source"] == "tencent-qfq-week"
    assert meta["vol_unit"] == "lot"
    assert meta["provider_backend"] == "mootdx"
    assert meta["daily_cached"] is False  # 网络路径不带 cached


def test_build_source_meta_detects_daily_cache_hit():
    snap = _fake_snapshot(daily=[_bar("tencent-http", "lot", cached=True)])
    meta = build_source_meta(snap, _fake_provider("mootdx"))
    assert meta["daily_cached"] is True
    assert meta["daily_source"] == "tencent-http"


def test_build_source_meta_empty_bars_all_none():
    snap = _fake_snapshot(daily=[], b5m=[], wk=[])
    meta = build_source_meta(snap, _fake_provider("tencent"))
    assert meta["daily_source"] is None
    assert meta["5m_source"] is None
    assert meta["weekly_source"] is None
    assert meta["vol_unit"] is None
    assert meta["daily_cached"] is False
    assert meta["provider_backend"] == "tencent"
    assert "fetched_at" in meta
