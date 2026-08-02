"""C-02：Tushare 周线缓存键须带市场，避免同码 SH/SZ 互毒。"""
from __future__ import annotations

from unittest.mock import MagicMock

import trader_shared.cache_utils as cu
import trader_shared.data_provider as dp


def test_c02_tushare_weekly_cache_key_includes_market(monkeypatch):
    seen: dict = {}

    def _scoped(key, target, fetch_fn, min_rows=1):
        seen["key"] = key
        seen["target"] = target
        return [
            {
                "date": f"2026-0{i}-01",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1,
            }
            for i in range(1, 6)
        ]

    monkeypatch.setattr(cu, "get_day_scoped_bars", _scoped)
    monkeypatch.setattr(
        "trader_shared.indicator_math.weekly_bars_look_like_weekly",
        lambda bars: True,
    )

    provider = dp.TushareProvider.__new__(dp.TushareProvider)
    provider._client = MagicMock()
    provider._fallback = MagicMock()

    sh = dp.Security(code="000852", market="SH", name="中证1000")
    bars = provider.fetch_weekly(sh, datalen=8)
    assert bars
    assert seen["key"] == cu.CACHE_WEEKLY
    assert seen["target"] == "000852_SH"

    sz = dp.Security(code="000852", market="SZ", name="石化机械")
    provider.fetch_weekly(sz, datalen=8)
    assert seen["target"] == "000852_SZ"
    assert seen["target"] != "000852"
