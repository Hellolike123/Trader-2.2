"""日频缓存：当天复用、换日回源。"""
from __future__ import annotations

import trader_shared.cache_utils as cu
import trader_shared.chip_data as chip


def test_get_day_scoped_bars_same_day(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-17")
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=1.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    def _fetch():
        calls["n"] += 1
        return [{"date": "2026-07-16", "close": 10.0}] * 30

    a = cu.get_day_scoped_bars("daily", "000988", _fetch, min_rows=20)
    b = cu.get_day_scoped_bars("daily", "000988", _fetch, min_rows=20)
    assert len(a) == 30 and len(b) == 30
    assert calls["n"] == 1


def test_is_fetch_date_today():
    assert cu.is_fetch_date_today({"fetch_date": "2026-07-17"}, "2026-07-17")
    assert not cu.is_fetch_date_today({"fetch_date": "2026-07-16"}, "2026-07-17")
    assert not cu.is_fetch_date_today({}, "2026-07-17")
    assert not cu.is_fetch_date_today([1, 2], "2026-07-17")


def test_unwrap_bars_payload():
    rows = [{"close": 1.0}]
    assert cu.unwrap_bars_payload({"fetch_date": "2026-07-17", "rows": rows}) == rows
    assert cu.unwrap_bars_payload(rows) == rows
    assert cu.unwrap_bars_payload({"fetch_date": "2026-07-17"}) is None
    assert cu.unwrap_bars_payload(None) is None


def test_get_day_scoped_bars_fetch_fail_rejects_cross_day(monkeypatch):
    """拉源失败时不得用跨日 {fetch_date, rows} 冒充可用。"""
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-18")
    old = {"fetch_date": "2026-07-17", "rows": [{"close": 1.0}] * 30}

    def _get(key, target, ttl=None):
        return cu.CacheResult(data=old, stale=False, age_seconds=1.0, source="file")

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", lambda *a, **k: None)

    def _boom():
        raise RuntimeError("net down")

    out = cu.get_day_scoped_bars("daily", "000988", _boom, min_rows=20)
    assert out == []


def test_get_day_scoped_bars_unwraps_same_day_payload(monkeypatch):
    """同日 ``{fetch_date, rows}`` 解包为 list，不回源。"""
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-17")
    payload = {"fetch_date": "2026-07-17", "rows": [{"close": 2.0}] * 30}
    calls = {"n": 0}

    def _get(key, target, ttl=None):
        return cu.CacheResult(data=payload, stale=False, age_seconds=1.0, source="file")

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", lambda *a, **k: None)

    def _boom():
        calls["n"] += 1
        raise RuntimeError("net down")

    out = cu.get_day_scoped_bars("daily", "000988", _boom, min_rows=20)
    assert len(out) == 30
    assert calls["n"] == 0


def test_cyq_same_day_hits_cache(monkeypatch):
    chip.clear_cyq_mem_cache()
    calls = {"n": 0}
    rows = [{"trade_date": "20260716", "winner_rate": 12.3}]

    def _fake_net(ts_code, start_date="", end_date=""):
        calls["n"] += 1
        return list(rows)

    monkeypatch.setattr(chip, "get_cyq_perf", _fake_net)
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-17")
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=1.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    r1 = chip.get_cyq_perf_cached("000988.SZ")
    r2 = chip.get_cyq_perf_cached("000988.SZ")
    assert r1 == rows
    assert r2 == rows
    assert calls["n"] == 1, "同日第二次不得再打网"


def test_cyq_next_day_refetches(monkeypatch):
    chip.clear_cyq_mem_cache()
    calls = {"n": 0}
    day = {"v": "2026-07-16"}

    def _fake_net(ts_code, start_date="", end_date=""):
        calls["n"] += 1
        return [{"trade_date": day["v"].replace("-", ""), "winner_rate": calls["n"]}]

    monkeypatch.setattr(chip, "get_cyq_perf", _fake_net)
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: day["v"])
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=1.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    r1 = chip.get_cyq_perf_cached("000988.SZ")
    assert r1[0]["winner_rate"] == 1
    day["v"] = "2026-07-17"  # 换日
    chip.clear_cyq_mem_cache()  # 模拟新进程只剩文件；文件仍带旧 fetch_date
    r2 = chip.get_cyq_perf_cached("000988.SZ")
    assert calls["n"] == 2, "换日必须回源"
    assert r2[0]["winner_rate"] == 2


def test_fund_flow_same_day_hits(monkeypatch):
    calls = {"n": 0}
    today = "2026-07-17"
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: today)
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=10.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    import trader_shared.fund_flow_data as ff

    def _fetch(symbol):
        calls["n"] += 1
        return [{"date": today, "main_net": -1}]

    monkeypatch.setattr(ff, "fetch_fund_flow", _fetch)
    monkeypatch.setattr(ff, "calc_fund_flow_features", lambda flows: {"ok": True})

    a = cu.fetch_fund_flow_cached("000988")
    b = cu.fetch_fund_flow_cached("000988")
    assert a.get("fetch_date") == today
    assert b.get("features") == {"ok": True}
    assert calls["n"] == 1


def test_sector_snapshot_same_day(monkeypatch):
    import trader_shared.sector_data as sd

    sd.clear_sector_mem_cache()
    calls = {"n": 0}
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: "2026-07-17")
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=1.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    def _raw(ts_code):
        calls["n"] += 1
        return {"industry": "专用机械", "status": "正常", "sector_change_pct": 1.2}

    monkeypatch.setattr(sd, "get_stock_sector_snapshot", _raw)
    a = sd.get_stock_sector_snapshot_cached("000988.SZ")
    b = sd.get_stock_sector_snapshot_cached("000988.SZ")
    assert a["status"] == "正常"
    assert b["sector_change_pct"] == 1.2
    assert calls["n"] == 1


def test_market_env_same_day_skips_network(monkeypatch):
    """文件已有今日 fetch_date 时 assess 不再 _fetch_index_data。"""
    import trader_shared.market_env as me

    me._assess_cache = None
    me._assess_cache_time = 0
    today = "2026-07-17"
    payload = {
        "level": "偏弱",
        "change_pct": -1.0,
        "fetch_date": today,
        "bars": [{"date": today, "close": 5000, "volume": 1}],
        "note": "cached",
    }
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: today)
    monkeypatch.setattr(
        cu,
        "get_cached",
        lambda key, target, ttl=None: cu.CacheResult(
            data=payload, stale=False, age_seconds=10.0, source="file"
        ),
    )
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError("should not fetch index")

    monkeypatch.setattr(me, "_fetch_index_data", _boom)
    env = me.assess()
    assert env["level"] == "偏弱"
    assert called["n"] == 0
    me._assess_cache = None


def test_daily_bars_cache_target_buckets():
    assert cu.daily_bars_cache_target("688248", provider="tencent", adjust="qfq") == (
        "tencent/qfq/688248"
    )
    assert cu.daily_bars_cache_target("000001", provider="tushare", adjust="none") == (
        "tushare/none/000001"
    )
    # 路径分隔符不得穿透缓存目录
    assert "/" not in cu._safe_cache_seg("a/b")
    assert cu.daily_bars_cache_target("a/b", provider="x\\y", adjust="qfq") == (
        "x_y/qfq/a_b"
    )


def test_fund_flow_cross_day_refetch(monkeypatch):
    calls = {"n": 0}
    day = {"v": "2026-07-16"}
    monkeypatch.setattr(cu, "cache_calendar_date", lambda: day["v"])
    store: dict = {}

    def _get(key, target, ttl=None):
        data = store.get((key, target))
        if data is None:
            return None
        return cu.CacheResult(data=data, stale=False, age_seconds=10.0, source="file")

    def _set(key, target, data):
        store[(key, target)] = data

    monkeypatch.setattr(cu, "get_cached", _get)
    monkeypatch.setattr(cu, "set_cached", _set)

    import trader_shared.fund_flow_data as ff

    def _fetch(symbol):
        calls["n"] += 1
        return [{"date": day["v"], "main_net": calls["n"]}]

    monkeypatch.setattr(ff, "fetch_fund_flow", _fetch)
    monkeypatch.setattr(ff, "calc_fund_flow_features", lambda flows: {"n": calls["n"]})

    cu.fetch_fund_flow_cached("000988")
    day["v"] = "2026-07-17"
    cu.fetch_fund_flow_cached("000988")
    assert calls["n"] == 2
