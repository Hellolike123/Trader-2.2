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


# Tushare stock_basic.industry → 同花顺行业指数候选名（有真实日线才可做强弱）
_INDUSTRY_THS_ALIASES: dict[str, tuple[str, ...]] = {
    "化工原料": ("化学原料", "商品化工(A股)", "化学制品(A股)", "电池化学品"),
    "化学原料": ("化学原料", "商品化工(A股)"),
    "电气设备": ("电气设备", "电源设备", "电池"),
    "元器件": ("电子元件", "电子", "半导体"),
    "半导体": ("半导体", "半导体产品与设备Ⅱ(A股)"),
    "汽车配件": ("汽车零部件", "汽车与汽车零部件(A股)"),
    "建筑工程": ("建筑与工程", "建筑装饰"),
    "软件服务": ("软件开发", "软件与服务(A股)"),
}

# 交易主题概念 → 优先对照的 THS 指数名（只映射到有指数的尺子，概念本身不算假指数）
_CONCEPT_TO_THS_INDEX: dict[str, tuple[str, ...]] = {
    "磷酸铁锂": ("电池化学品", "锂电池", "电池"),
    "锂电池": ("锂电池", "电池"),
    "锂电正极": ("电池化学品", "锂电池", "电池"),
    "锂电负极": ("电池化学品", "锂电池", "电池"),
    "锂电池概念": ("锂电池", "电池"),
    "宁德时代概念": ("锂电池", "电池"),
    "储能": ("电池", "锂电池"),
    "光伏": ("光伏概念", "电源设备"),
    "新能源汽车": ("新能源汽车", "电池"),
    "芯片": ("半导体", "集成电路"),
    "人工智能": ("人工智能", "软件开发"),
    "消费电子": ("消费电子", "元器件"),
}

# 同花顺行业指数里，适合做「主交易板块」的优先名（有日线）
_PREFERRED_THS_TRADE_INDEX = (
    "电池",
    "锂电池",
    "电池化学品",
    "光伏概念",
    "新能源汽车",
    "半导体",
    "软件开发",
    "化学原料",
    "商品化工(A股)",
    "化学制品(A股)",
)


def _index_by_names(
    ths_indices: list[dict[str, Any]], names: tuple[str, ...] | list[str]
) -> dict[str, Any] | None:
    by_name = {str(x.get("name") or "").strip(): x for x in ths_indices if isinstance(x, dict)}
    for n in names:
        hit = by_name.get(str(n).strip())
        if hit:
            return hit
    # 宽松：全等失败后再 contains（短名优先已在 names 顺序里）
    for n in names:
        nn = str(n).strip()
        if not nn:
            continue
        for name, idx in by_name.items():
            if nn == name or nn in name or name in nn:
                return idx
    return None


def _match_ths_industry(
    industry: str, ths_indices: list[dict[str, Any]]
) -> dict[str, Any] | None:
    ind = str(industry or "").strip()
    if not ind:
        return None
    # 1) 显式别名
    aliased = _INDUSTRY_THS_ALIASES.get(ind)
    if aliased:
        hit = _index_by_names(ths_indices, aliased)
        if hit:
            return hit
    # 2) 关键词表
    for keyword in _SECTOR_KEYWORDS.get(ind, []):
        hit = _index_by_names(ths_indices, (keyword,))
        if hit:
            return hit
    # 3) 原名全等/包含
    hit = _index_by_names(ths_indices, (ind,))
    if hit:
        return hit
    # 4) 家电特判
    for idx in ths_indices:
        idx_name = str(idx.get("name", ""))
        if "家电" in idx_name and "家电" in ind:
            return idx
    return None


def _concept_names_for_stock(ts_code: str) -> list[str]:
    """个股概念标签（身份，不做假指数比较）。"""
    client = get_client()
    if not client.available:
        return []
    rows = client.query("concept_detail", ts_code=ts_code) or []
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        n = str(row.get("concept_name") or row.get("name") or "").strip()
        if not n or n in seen:
            continue
        seen.add(n)
        names.append(n)
    return names


def _match_ths_from_concepts(
    concept_names: list[str], ths_indices: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """概念只作映射线索 → 有真实日线的 THS 指数；返回 (index, via_concept)."""
    for cn in concept_names:
        cands = _CONCEPT_TO_THS_INDEX.get(cn)
        if not cands:
            # 概念名若本身就是优先交易指数名
            if cn in _PREFERRED_THS_TRADE_INDEX:
                cands = (cn,)
            else:
                continue
        hit = _index_by_names(ths_indices, cands)
        if hit:
            return hit, cn
    return None, ""


def _pack_sector_snap(
    *,
    industry: str,
    matched: dict[str, Any],
    concepts: list[str],
    match_via: str,
) -> dict[str, Any]:
    sector_code = str(matched.get("ts_code") or "")
    sector_name = str(matched.get("name") or "")
    primary_concept = concepts[0] if concepts else ""
    base = {
        "industry": industry,
        "sector_name": sector_name,
        "sector_code": sector_code,
        "concepts": concepts[:6],
        "primary_concept": primary_concept,
        "match_via": match_via,
    }
    if not sector_code:
        return {**base, "status": "未匹配板块"}
    sector_daily = get_ths_daily(sector_code)
    if not sector_daily:
        return {**base, "status": "无日线"}
    latest = sector_daily[-1]
    try:
        sector_chg_pct = float(latest.get("pct_change", 0) or 0)
    except (TypeError, ValueError):
        sector_chg_pct = 0.0
    return {
        **base,
        "sector_change_pct": sector_chg_pct,
        "status": "正常",
    }


def get_stock_sector_snapshot(ts_code: str) -> dict[str, Any] | None:
    """个股：概念标签 + 唯一主板块指数（有日线才可强弱）。

    规则：
    - 概念 = 身份标签（可多选），**不做假指数比较**
    - 比较尺子 = 同花顺板块/行业指数（必须有日线）唯一一条
    - 映射优先：概念→交易指数；其次 stock_basic.industry→指数（含别名）
    """
    client = get_client()
    if not client.available:
        return None

    code = str(ts_code or "").strip()
    if not code:
        return None

    stock_info = client.query(
        "stock_basic", ts_code=code, fields="ts_code,name,industry"
    )
    if not stock_info:
        return None
    industry = str(stock_info[0].get("industry") or "").strip()

    concepts = _concept_names_for_stock(code)
    ths_indices = get_ths_index("I") or []

    matched = None
    match_via = ""
    # 1) 概念映射到真实指数（德方：磷酸铁锂→电池化学品/锂电池）
    matched, via_c = _match_ths_from_concepts(concepts, ths_indices)
    if matched is not None:
        match_via = f"concept:{via_c}"
    # 2) 基础行业（别名表）
    if matched is None and industry:
        matched = _match_ths_industry(industry, ths_indices)
        if matched is not None:
            match_via = f"industry:{industry}"

    if matched is None:
        return {
            "industry": industry,
            "status": "未匹配板块",
            "concepts": concepts[:6],
            "primary_concept": concepts[0] if concepts else "",
            "match_via": "",
        }

    return _pack_sector_snap(
        industry=industry,
        matched=matched,
        concepts=concepts,
        match_via=match_via,
    )


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
    cached = _cu.get_cached("sector_stock_snap_v2", file_key, ttl=_CACHE_TTL_DAY)
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
            _cu.set_cached("sector_stock_snap_v2", file_key, payload)
        except OSError as exc:
            _logger.debug("sector snap cache write failed: %s", exc)
        _stock_sector_mem[code] = (today, snap)
    return dict(snap) if isinstance(snap, dict) else snap


def clear_sector_mem_cache() -> None:
    """测试用。"""
    _stock_sector_mem.clear()
