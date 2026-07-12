"""板块数据模块 — 基于 Tushare 的概念/行业板块查询与缓存。

提供：
- 概念板块列表/成分股
- 同花顺概念/行业指数及日线
- 申万行业分类
- 带文件缓存（板块列表变化慢，TTL 24h）

使用方式：
    from trader_shared.sector_data import get_concept_list, get_ths_daily
    concepts = get_concept_list()
    bars = get_ths_daily("885947.TI", start_date="20260101")
"""
from __future__ import annotations

import os
from typing import Any

from trader_shared.tushare_client import get_client
from trader_shared.cache_utils import get_cached, set_cached

# 缓存 TTL（板块列表变化慢，24h）
_CACHE_TTL_SECTOR_LIST = 24 * 3600
_CACHE_TTL_SECTOR_DETAIL = 12 * 3600


def get_concept_list() -> list[dict[str, Any]]:
    """获取概念板块列表。带缓存（24h）。"""
    cached = get_cached("sector_concept_list", "__global__", ttl=_CACHE_TTL_SECTOR_LIST)
    if cached is not None:
        return cached
    client = get_client()
    data = client.query_concept()
    if data:
        set_cached("sector_concept_list", "__global__", data)
    return data


def get_concept_detail(concept_id: str) -> list[dict[str, Any]]:
    """获取概念板块成分股。带缓存（12h）。"""
    cached = get_cached("sector_concept_detail", concept_id, ttl=_CACHE_TTL_SECTOR_DETAIL)
    if cached is not None:
        return cached
    client = get_client()
    data = client.query_concept_detail(concept_id)
    if data:
        set_cached("sector_concept_detail", concept_id, data)
    return data


def get_ths_index(index_type: str = "N") -> list[dict[str, Any]]:
    """获取同花顺概念/行业指数列表。type: 'N'=概念, 'I'=行业。带缓存（24h）。"""
    cache_key = f"ths_index_{index_type}"
    cached = get_cached("sector_ths_index", cache_key, ttl=_CACHE_TTL_SECTOR_LIST)
    if cached is not None:
        return cached
    client = get_client()
    data = client.query_ths_index(index_type)
    if data:
        set_cached("sector_ths_index", cache_key, data)
    return data


def get_ths_daily(
    ts_code: str, start_date: str = "", end_date: str = ""
) -> list[dict[str, Any]]:
    """获取同花顺板块指数日线。不缓存（行情数据变化快）。"""
    client = get_client()
    return client.query_ths_daily(ts_code, start_date, end_date)


def get_ths_member(ts_code: str) -> list[dict[str, Any]]:
    """获取同花顺板块成分股。带缓存（12h）。"""
    cached = get_cached("sector_ths_member", ts_code, ttl=_CACHE_TTL_SECTOR_DETAIL)
    if cached is not None:
        return cached
    client = get_client()
    data = client.query_ths_member(ts_code)
    if data:
        set_cached("sector_ths_member", ts_code, data)
    return data


def get_index_classify(src: str = "SW") -> list[dict[str, Any]]:
    """获取行业分类。带缓存（24h）。"""
    cache_key = f"index_classify_{src}"
    cached = get_cached("sector_index_classify", cache_key, ttl=_CACHE_TTL_SECTOR_LIST)
    if cached is not None:
        return cached
    client = get_client()
    data = client.query_index_classify(src)
    if data:
        set_cached("sector_index_classify", cache_key, data)
    return data
