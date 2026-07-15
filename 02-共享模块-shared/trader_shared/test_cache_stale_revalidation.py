"""回归测试：缓存 TTL 过期（stale）时，调用方必须回源而非把陈旧数据当真。

背景（2026-07-15）：
    get_cached 过期只标 stale=True 但仍返回旧数据，而所有调用点都直接
    ``return cached.data``，导致日K文件缓存（~/.trader/cache/daily/{code}.json）
    过期后仍被 fetch_qfq_daily 当作命中返回——报告日K曾因此停在 07-01（缺两周数据）。

修复：调用方必须检查 cached.stale，stale 时跳过缓存走回源。本测试锁定该行为。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

import pytest

import trader_shared.cache_utils as cu
import trader_shared.data_provider as dp
import trader_shared.light_data as ld
from trader_shared.cache_utils import CacheResult
from trader_shared.data_provider import Security, UnifiedProvider


def _stale_result(data):
    return CacheResult(data=data, stale=True, age_seconds=10**9, source="file")


class _FakeHttp:
    """返回纯 JSON（腾讯 qfqday），今日那根用动态日期。
    注意：extract_jsonp 对无 "=" 输入直接 json.loads，不要加 _var= 前缀。
    """

    def get_text(self, url: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return (
            '{"code":0,"msg":"","data":{"sh688248":{'
            f'"qfqday":[["{today}",10.0,11.0,12.0,9.0,1000]]'
            "}}}"
        )


class _FakeBreaker:
    """最小熔断对象：仅暴露 fetch_qfq_daily 实际调用的接口。"""

    is_open = False

    def record_success(self) -> None:
        pass

    def record_failure(self) -> None:
        pass


def test_get_cached_marks_expired_file_as_stale(tmp_path, monkeypatch):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir(parents=True)
    cache_file = daily_dir / "688248.json"
    cache_file.write_text(json.dumps([{"date": "2026-07-01", "close": 67.0}]))
    old = time.time() - 2 * 86400  # 2 天前
    os.utime(cache_file, (old, old))

    monkeypatch.setattr(cu, "CACHE_DIR", tmp_path)
    res = cu.get_cached("daily", "688248", ttl=86400)
    assert res is not None
    assert res.stale is True  # 底层必须把过期标成 stale
    assert res.data[0]["date"] == "2026-07-01"


def test_unified_provider_fetch_qfq_daily_skips_stale(monkeypatch):
    stale_bars = [{"date": "2026-07-01", "close": 67.0}]
    fresh_bars = [{"date": datetime.now().strftime("%Y-%m-%d"), "close": 48.05}]

    monkeypatch.setattr(cu, "get_cached", lambda key, target, ttl=None: _stale_result(stale_bars))
    monkeypatch.setattr(cu, "set_cached", lambda *a, **k: None)
    monkeypatch.setattr(ld, "fetch_qfq_daily", lambda sec, http, days=300: fresh_bars)

    provider = UnifiedProvider(backend="tencent")
    sec = Security(code="688248", market="sh", name="南网科技")
    result = provider.fetch_qfq_daily(sec, days=300)
    # 必须回源得到新鲜数据，而非把陈旧缓存当真返回
    assert result is fresh_bars


def test_light_data_fetch_qfq_daily_skips_stale(monkeypatch):
    stale_bars = [{"date": "2026-07-01", "close": 67.0}]
    today = datetime.now().strftime("%Y-%m-%d")
    monkeypatch.setattr(cu, "get_cached", lambda key, target, ttl=None: _stale_result(stale_bars))
    monkeypatch.setattr(cu, "set_cached_validated", lambda *a, **k: True)
    monkeypatch.setattr(ld, "_circuit_tencent_daily", _FakeBreaker())
    monkeypatch.setattr(ld, "get_from_cache", lambda key: None)
    monkeypatch.setattr(ld, "_rate_limit_delay", lambda: None)
    # 避免 do_fetch 失败后走真实网络回源
    monkeypatch.setattr(ld, "_fetch_daily_sina", lambda *a, **k: None)
    monkeypatch.setattr(ld, "_check_pytdx3", lambda: False)
    monkeypatch.setattr(ld, "_fetch_qfq_mootdx", lambda *a, **k: None)

    sec = ld.Security(code="688248", market="sh", name="南网科技")
    result = ld.fetch_qfq_daily(sec, _FakeHttp(), days=300)
    assert any(b["date"] == today for b in result), "回源应拿到含今日的新鲜日K"
    assert not any(b["date"] == "2026-07-01" for b in result), "陈旧缓存绝不能被当真返回"


def test_fetch_fund_flow_cached_skips_stale(monkeypatch):
    stale_ff = {"daily_flow": [{"date": "2026-07-01"}], "features": {}}
    monkeypatch.setattr(cu, "get_cached", lambda key, target, ttl=None: _stale_result(stale_ff))
    monkeypatch.setattr(cu, "set_cached", lambda *a, **k: None)

    ff_mod = pytest.importorskip("trader_shared.fund_flow_data")
    monkeypatch.setattr(ff_mod, "fetch_fund_flow", lambda symbol: [{"date": "fresh"}])
    monkeypatch.setattr(ff_mod, "calc_fund_flow_features", lambda flows: {"k": 1})

    result = cu.fetch_fund_flow_cached("688248")
    assert result != stale_ff
    assert result["daily_flow"] == [{"date": "fresh"}], "必须回源而非返回陈旧资金流"
