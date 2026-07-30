"""板块数据模块 — 基于 Tushare 的概念/行业板块查询与缓存。

提供：
- 概念板块列表/成分股
- 同花顺概念/行业指数及日线
- 申万行业分类
- 个股行业 + 板块涨跌幅快照（报告用，按自然日缓存）

缓存约定：
- 列表类：TTL 24h / 12h（变化慢）
- 个股板块涨跌、ths 日线最新：fetch_date=今天则复用，换日回源
"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
import trader_shared.cache_utils as _cu
from trader_shared.tushare_client import get_client

_logger = get_logger(__name__)

# 缓存 TTL（板块列表变化慢）
_CACHE_TTL_SECTOR_LIST = 24 * 3600
_CACHE_TTL_SECTOR_DETAIL = 12 * 3600
_CACHE_TTL_DAY = 3 * 86400  # 文件年龄兜底；真正看 fetch_date

_SECTOR_KEYWORDS = {
    "家用电器": ["白色家电", "黑色家电", "小家电", "家电零部件"],
    "电子": ["电子零部件", "电子化学品"],
    "计算机": ["软件开发", "计算机设备"],
    "医药": ["化学制药", "中药", "生物制品"],
    "银行": ["国有大行", "股份制银行", "城商行"],
    "食品饮料": ["白酒", "乳品", "调味品"],
}

# 进程内：个股板块快照 code -> (fetch_date, payload)
_stock_sector_mem: dict[str, tuple[str, dict[str, Any]]] = {}


def _unwrap_list(cached) -> list[dict[str, Any]] | None:
    """get_cached 返回 CacheResult；兼容旧调用误用。"""
    if cached is None:
        return None
    data = cached.data if hasattr(cached, "data") else cached
    if isinstance(data, list):
        return data
    return None


def get_concept_list() -> list[dict[str, Any]]:
    """获取概念板块列表。带缓存（24h）。"""
    cached = _cu.get_cached("sector_concept_list", "__global__", ttl=_CACHE_TTL_SECTOR_LIST)
    rows = _unwrap_list(cached)
    if rows is not None and cached is not None and not getattr(cached, "stale", False):
        return rows
    client = get_client()
    data = client.query_concept() or []
    if data:
        _cu.set_cached("sector_concept_list", "__global__", data)
    return data


def get_concept_detail(concept_id: str) -> list[dict[str, Any]]:
    """获取概念板块成分股。带缓存（12h）。"""
    cached = _cu.get_cached("sector_concept_detail", concept_id, ttl=_CACHE_TTL_SECTOR_DETAIL)
    rows = _unwrap_list(cached)
    if rows is not None and cached is not None and not getattr(cached, "stale", False):
        return rows
    client = get_client()
    data = client.query_concept_detail(concept_id) or []
    if data:
        _cu.set_cached("sector_concept_detail", concept_id, data)
    return data


def get_ths_index(index_type: str = "N") -> list[dict[str, Any]]:
    """获取同花顺概念/行业指数列表。type: 'N'=概念, 'I'=行业。带缓存（24h）。"""
    cache_key = f"ths_index_{index_type}"
    cached = _cu.get_cached("sector_ths_index", cache_key, ttl=_CACHE_TTL_SECTOR_LIST)
    rows = _unwrap_list(cached)
    if rows is not None and cached is not None and not getattr(cached, "stale", False):
        return rows
    client = get_client()
    data = client.query_ths_index(index_type) or []
    if data:
        _cu.set_cached("sector_ths_index", cache_key, data)
    return data


def get_ths_daily(
    ts_code: str, start_date: str = "", end_date: str = ""
) -> list[dict[str, Any]]:
    """获取同花顺板块指数日线。

    无起止日期时按自然日缓存（报告只读最新一根涨跌）；带日期范围则直连不缓存。
    返回时间正序，[-1]=最新（Tushare ths_daily 常倒序）。
    """
    def _sort_asc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows or [],
            key=lambda r: str(r.get("trade_date") or r.get("date") or ""),
        )

    if start_date or end_date:
        client = get_client()
        return _sort_asc(client.query_ths_daily(ts_code, start_date, end_date) or [])

    today = _cu.cache_calendar_date()
    key = str(ts_code).replace(".", "_")
    cached = _cu.get_cached("sector_ths_daily", key, ttl=_CACHE_TTL_DAY)
    if cached is not None and _cu.is_fetch_date_today(cached.data, today):
        rows = cached.data.get("rows") if isinstance(cached.data, dict) else None
        if isinstance(rows, list):
            return _sort_asc(list(rows))

    client = get_client()
    data = _sort_asc(client.query_ths_daily(ts_code, start_date="", end_date="") or [])
    if data:
        try:
            _cu.set_cached(
                "sector_ths_daily",
                key,
                {"fetch_date": today, "rows": data},
            )
        except OSError as exc:
            _logger.debug("ths_daily cache write failed: %s", exc)
    return data


def get_ths_member(ts_code: str) -> list[dict[str, Any]]:
    """获取同花顺板块成分股。带缓存（12h）。"""
    cached = _cu.get_cached("sector_ths_member", ts_code, ttl=_CACHE_TTL_SECTOR_DETAIL)
    rows = _unwrap_list(cached)
    if rows is not None and cached is not None and not getattr(cached, "stale", False):
        return rows
    client = get_client()
    data = client.query_ths_member(ts_code) or []
    if data:
        _cu.set_cached("sector_ths_member", ts_code, data)
    return data


def get_index_classify(src: str = "SW") -> list[dict[str, Any]]:
    """获取行业分类。带缓存（24h）。"""
    cache_key = f"index_classify_{src}"
    cached = _cu.get_cached("sector_index_classify", cache_key, ttl=_CACHE_TTL_SECTOR_LIST)
    rows = _unwrap_list(cached)
    if rows is not None and cached is not None and not getattr(cached, "stale", False):
        return rows
    client = get_client()
    data = client.query_index_classify(src) or []
    if data:
        _cu.set_cached("sector_index_classify", cache_key, data)
    return data


def _match_ths_industry(
    industry: str, ths_indices: list[dict[str, Any]]
) -> dict[str, Any] | None:
    matched = None
    for keyword in _SECTOR_KEYWORDS.get(industry, []):
        for idx in ths_indices:
            if str(idx.get("name", "")) == keyword:
                return idx
    for idx in ths_indices:
        idx_name = str(idx.get("name", ""))
        if industry == idx_name or industry in idx_name:
            return idx
    for idx in ths_indices:
        idx_name = str(idx.get("name", ""))
        if "家电" in idx_name and "家电" in industry:
            return idx
    return matched


def get_stock_sector_snapshot(ts_code: str) -> dict[str, Any] | None:
    """个股行业 + 匹配板块 + 板块当日涨跌。无缓存，打网。"""
    client = get_client()
    if not client.available:
        return None

    stock_info = client.query(
        "stock_basic", ts_code=ts_code, fields="ts_code,name,industry"
    )
    if not stock_info:
        return None
    industry = stock_info[0].get("industry", "")
    if not industry:
        return None

    ths_indices = get_ths_index("I")  # 列表级缓存
    matched = _match_ths_industry(str(industry), ths_indices or [])
    if not matched:
        return {"industry": industry, "status": "未匹配板块"}

    sector_code = matched.get("ts_code", "")
    sector_name = matched.get("name", "")
    sector_daily = get_ths_daily(str(sector_code))  # 日频缓存
    if not sector_daily:
        return {
            "industry": industry,
            "sector_name": sector_name,
            "sector_code": sector_code,
            "status": "无日线",
        }

    latest = sector_daily[-1]
    sector_chg_pct = float(latest.get("pct_change", 0) or 0)
    return {
        "industry": industry,
        "sector_name": sector_name,
        "sector_code": sector_code,
        "sector_change_pct": sector_chg_pct,
        "status": "正常",
    }


def get_stock_sector_snapshot_cached(ts_code: str) -> dict[str, Any] | None:
    """报告用板块快照：当天第一次打网，同日复用，换日回源。"""
    code = str(ts_code or "").strip()
    if not code:
        return None

    today = _cu.cache_calendar_date()
    mem = _stock_sector_mem.get(code)
    if mem is not None and mem[0] == today:
        return dict(mem[1])

    file_key = code.replace(".", "_")
    cached = _cu.get_cached("sector_stock_snap", file_key, ttl=_CACHE_TTL_DAY)
    if cached is not None and _cu.is_fetch_date_today(cached.data, today):
        snap = cached.data.get("snapshot") if isinstance(cached.data, dict) else None
        if isinstance(snap, dict):
            _stock_sector_mem[code] = (today, snap)
            return dict(snap)

    try:
        snap = get_stock_sector_snapshot(code)
    except Exception as exc:
        _logger.debug("sector snapshot failed for %s: %s", code, exc)
        if cached is not None and isinstance(cached.data, dict):
            old = cached.data.get("snapshot")
            if isinstance(old, dict):
                return dict(old)
        return None

    if snap is not None:
        payload = {"fetch_date": today, "snapshot": snap}
        try:
            _cu.set_cached("sector_stock_snap", file_key, payload)
        except OSError as exc:
            _logger.debug("sector snap cache write failed: %s", exc)
        _stock_sector_mem[code] = (today, snap)
    return dict(snap) if isinstance(snap, dict) else snap


def clear_sector_mem_cache() -> None:
    """测试用。"""
    _stock_sector_mem.clear()
