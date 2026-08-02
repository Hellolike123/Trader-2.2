"""data_access.py — 数据层简化接口

提供面向上层脚本的极简 API，屏蔽底层 provider/Security 细节：

    from trader_shared.data_access import get_daily, get_5m, get_weekly, get_quote, get_quotes

上层只需传股票代码字符串，无需关心 Security 对象、provider 切换、
缓存策略等内部细节。内部使用全局 provider（get_provider()）。

与 data_provider.py 的关系：
- data_provider.py 是核心实现层（含 UnifiedProvider / TushareProvider）
- data_access.py 是薄包装层（只做参数转换 + 错误兜底）
- 现有调用 provider.fetch_qfq_daily(sec, ...) 无需改动，可渐进替换
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from trader_shared._logging import get_logger
from trader_shared.data_provider import get_provider

_logger = get_logger(__name__)

# 批量行情并行上限（handoff：4～8）
_QUOTE_MAX_WORKERS = 6


def _provider_and_sec(target: str):
    """解析 target → (provider, Security)，内部复用。"""
    p = get_provider()
    sec = p.resolve_security(target)
    return p, sec


# ── 日线 ──────────────────────────────────────────────────────────────────────

def get_daily(target: str, days: int = 300) -> list[dict[str, Any]]:
    """获取前复权日 K 线（默认 300 天）。

    等价于原 provider.fetch_qfq_daily(sec, days=days)，但入参只需股票代码/名称。

    Args:
        target: 股票代码（"688248"）或中文名（"南网科技"）
        days: 请求天数，默认 300（覆盖 MA250）

    Returns:
        标准化日 K 线列表；失败时返回空列表（已记录日志）。
    """
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_qfq_daily(sec, days=days) or []
    except Exception as e:
        _logger.warning("get_daily(%s) failed: %s", target, e)
        return []


# ── 分钟线 ─────────────────────────────────────────────────────────────────────

def get_5m(target: str, datalen: int = 60) -> list[dict[str, Any]]:
    """获取 5 分钟 K 线（当日）。

    Args:
        target: 股票代码或名称
        datalen: 请求根数，默认 60（约覆盖一个完整交易日）

    Returns:
        5 分钟 K 线列表；失败时返回空列表。
    """
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_5m(sec, datalen=datalen) or []
    except Exception as e:
        _logger.warning("get_5m(%s) failed: %s", target, e)
        return []


def get_15m(target: str, datalen: int = 60) -> list[dict[str, Any]]:
    """获取 15 分钟 K 线。"""
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_15m(sec, datalen=datalen) or []
    except Exception as e:
        _logger.warning("get_15m(%s) failed: %s", target, e)
        return []


def get_30m(target: str, datalen: int = 60) -> list[dict[str, Any]]:
    """获取 30 分钟 K 线。"""
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_30m(sec, datalen=datalen) or []
    except Exception as e:
        _logger.warning("get_30m(%s) failed: %s", target, e)
        return []


# ── 周线 / 月线 ────────────────────────────────────────────────────────────────

def get_weekly(target: str, datalen: int = 80) -> list[dict[str, Any]]:
    """获取周 K 线（默认 80 根 ≈ 近 1.5 年）。

    用于中线分析（中枢、笔段、mid_key_prices 等）。
    """
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_weekly(sec, datalen=datalen) or []
    except Exception as e:
        _logger.warning("get_weekly(%s) failed: %s", target, e)
        return []


def get_monthly(target: str, datalen: int = 60) -> list[dict[str, Any]]:
    """获取月 K 线（默认 60 根 ≈ 5 年）。"""
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_monthly(sec, datalen=datalen) or []
    except Exception as e:
        _logger.warning("get_monthly(%s) failed: %s", target, e)
        return []


# ── 实时行情 ───────────────────────────────────────────────────────────────────

def get_quote(target: str) -> dict[str, Any]:
    """获取实时快照（现价、涨幅、量比等）。

    Returns:
        行情字典；失败时返回空字典。
    """
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_quote(sec) or {}
    except Exception as e:
        _logger.warning("get_quote(%s) failed: %s", target, e)
        return {}


def get_quotes(
    targets: Iterable[str],
    *,
    max_workers: int = _QUOTE_MAX_WORKERS,
) -> dict[str, dict[str, Any]]:
    """批量获取实时快照（经 get_provider / get_quote）。

    有界 ThreadPoolExecutor 并行；单票失败写入空 dict，不影响其余。

    Args:
        targets: 股票代码或名称可迭代
        max_workers: 并行上限，默认 6（夹在 4～8）

    Returns:
        ``{target: quote_dict}``；失败票对应 ``{}``。
    """
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in targets:
        t = str(raw or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    if not uniq:
        return {}

    workers = max(1, min(int(max_workers or _QUOTE_MAX_WORKERS), 8, len(uniq)))
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(get_quote, t): t for t in uniq}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                results[t] = fut.result() or {}
            except Exception as e:
                _logger.warning("get_quotes(%s) failed: %s", t, e)
                results[t] = {}
    return results


# ── Tick 数据 ──────────────────────────────────────────────────────────────────

def get_ticks(target: str, count: int = 500) -> list[dict[str, Any]]:
    """获取逐笔成交（用于 T0 大单监控）。"""
    try:
        p, sec = _provider_and_sec(target)
        return p.fetch_ticks(sec, count=count) or []
    except Exception as e:
        _logger.warning("get_ticks(%s) failed: %s", target, e)
        return []


# ── 全量快照（重量级） ────────────────────────────────────────────────────────

def get_snapshot(
    target: str,
    days: int = 365,
    include_5m: bool = True,
    include_weekly: bool = True,
    include_monthly: bool = True,
    include_ticks: bool = True,
):
    """获取 MarketSnapshot（行情 + 日线 + 可选分钟线/周线/月线/tick）。

    等价于原 provider.load_market_snapshot(...)，适合需要全量数据的分析场景。

    Returns:
        MarketSnapshot 对象；失败时返回 None（已记录日志）。
    """
    try:
        p, _ = _provider_and_sec(target)
        return p.load_market_snapshot(
            target,
            days=days,
            include_5m=include_5m,
            include_weekly=include_weekly,
            include_monthly=include_monthly,
            include_ticks=include_ticks,
        )
    except Exception as e:
        _logger.warning("get_snapshot(%s) failed: %s", target, e)
        return None
