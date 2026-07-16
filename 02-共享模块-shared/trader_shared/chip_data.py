"""筹码分布数据模块 — 基于 Tushare 的 cyq_perf / cyq_chips。

提供：
- 筹码分布（成本分位数、获利比例、加权均价）
- 每日筹码（逐价位筹码分布）

替代自行推算的 chip_distribution.py，数据更准确（官方计算）。

缓存约定（与用户对齐）：
- 前一天 / 历史：可缓存
- 当天：第一次拉网，当天内再分析同一票直接读缓存
- 换日：重新拉网

使用方式：
    from trader_shared.chip_data import get_cyq_perf, get_cyq_perf_cached, get_cyq_chips
    perf = get_cyq_perf_cached("688248.SH")
"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.tushare_client import get_client

_logger = get_logger(__name__)

# 进程内同日复用（比文件更快；换日或进程重启后走文件/网络）
_cyq_mem: dict[str, tuple[str, list[dict[str, Any]]]] = {}


def get_cyq_perf(
    ts_code: str, start_date: str = "", end_date: str = ""
) -> list[dict[str, Any]]:
    """获取筹码分布（成本分位数、获利比例、加权均价）。无打网。

    返回字段：ts_code, trade_date, his_low, his_high, cost_5pct, cost_15pct,
    cost_50pct, cost_85pct, cost_95pct, weight_avg, winner_rate 等。
    """
    client = get_client()
    return client.query_cyq_perf(ts_code, start_date, end_date)


def get_cyq_perf_cached(
    ts_code: str,
    start_date: str = "",
    end_date: str = "",
) -> list[dict[str, Any]]:
    """筹码 cyq_perf：同日缓存，换日回源。

    缓存键为 ts_code（含 .SH/.SZ）。payload：
        {"fetch_date": "YYYY-MM-DD", "rows": [...]}

    mock_seam 仍 patch ``get_cyq_perf``；本函数经其回源，测试零改。
    """
    from trader_shared.cache_utils import (
        CACHE_CYQ,
        TTL_CYQ,
        cache_calendar_date,
        get_cached,
        is_fetch_date_today,
        set_cached,
    )

    code = str(ts_code or "").strip()
    if not code:
        return []

    today = cache_calendar_date()

    # 1) 内存
    mem = _cyq_mem.get(code)
    if mem is not None and mem[0] == today:
        return list(mem[1])

    # 2) 文件：fetch_date == 今天 → 直接用
    cached = get_cached(CACHE_CYQ, code.replace(".", "_"), ttl=TTL_CYQ)
    if cached is not None and is_fetch_date_today(cached.data, today):
        rows = cached.data.get("rows") if isinstance(cached.data, dict) else None
        if isinstance(rows, list):
            _cyq_mem[code] = (today, rows)
            return list(rows)

    # 3) 打网
    try:
        rows = get_cyq_perf(code, start_date=start_date, end_date=end_date) or []
    except Exception as exc:
        _logger.debug("get_cyq_perf network failed for %s: %s", code, exc)
        # 回源失败：退回文件里旧 rows（若有），避免整段筹码空
        if cached is not None and isinstance(cached.data, dict):
            old = cached.data.get("rows")
            if isinstance(old, list) and old:
                return list(old)
        return []

    if rows:
        payload = {"fetch_date": today, "rows": rows}
        try:
            set_cached(CACHE_CYQ, code.replace(".", "_"), payload)
        except OSError as exc:
            _logger.debug("cyq cache write failed for %s: %s", code, exc)
        _cyq_mem[code] = (today, rows)
    return list(rows)


def get_cyq_chips(ts_code: str, trade_date: str) -> list[dict[str, Any]]:
    """获取每日筹码分布（逐价位）。"""
    client = get_client()
    return client.query_cyq_chips(ts_code, trade_date)


def clear_cyq_mem_cache() -> None:
    """测试用：清空进程内 cyq 缓存。"""
    _cyq_mem.clear()
