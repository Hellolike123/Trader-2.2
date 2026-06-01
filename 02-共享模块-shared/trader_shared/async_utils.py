"""Async utilities for concurrent data fetching.

Provides async versions of data fetching functions using aiohttp.
Sync wrappers are provided for backward compatibility.

Usage:
    # Async (for concurrent multi-stock fetching)
    import asyncio
    from trader_shared.async_utils import fetch_all_quotes_async
    results = asyncio.run(fetch_all_quotes_async(["688248", "601600"]))

    # Sync wrapper (backward compatible)
    from trader_shared.async_utils import fetch_quote_sync
    quote = fetch_quote_sync("688248")
"""
from __future__ import annotations

import asyncio
import json
import re
import ssl
from typing import Any

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

# ── aiohttp availability check (lazy) ──
_AIOHTTP_AVAILABLE: bool | None = None


def _check_aiohttp() -> bool:
    global _AIOHTTP_AVAILABLE
    if _AIOHTTP_AVAILABLE is not None:
        return _AIOHTTP_AVAILABLE
    try:
        import aiohttp  # noqa: F401
        _AIOHTTP_AVAILABLE = True
    except ImportError:
        _AIOHTTP_AVAILABLE = False
    return _AIOHTTP_AVAILABLE


# ── Constants (mirror light_data.py) ──
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


def _to_float(value: Any) -> float | None:
    """Safe float conversion (mirrors light_data.to_float)."""
    import math
    if value in (None, "", "-", "--", "null", "None"):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _resolve_qq_symbol(code: str) -> str:
    """Convert stock code to Tencent qq_symbol format (e.g. 'sh688248')."""
    code = code.strip().upper()
    if "." in code:
        parts = code.split(".", 1)
        num, market = parts[0], parts[1].lower()
    elif code.startswith(("SH", "SZ", "BJ")):
        market, num = code[:2].lower(), code[2:]
    else:
        num = code
        market = "sh" if num.startswith(("6", "688", "689")) else "sz"
    return f"{market}{num}"


async def fetch_quote_async(
    session: "aiohttp.ClientSession",
    code: str,
) -> dict[str, Any]:
    """Fetch real-time quote from Tencent API asynchronously.

    Args:
        session: aiohttp client session
        code: Stock code (e.g. "688248" or "688248.SH")

    Returns:
        Quote dict with current_price, pre_close, etc.
    """
    qq = _resolve_qq_symbol(code)
    url = TENCENT_QUOTE_URL + qq
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            text = await resp.text(encoding="gbk", errors="ignore")
            match = re.search(r'="([^"]*)"', text)
            if not match or len(match.group(1).split("~")) < 35:
                return {"error": "incomplete_data", "code": code}
            fields = match.group(1).split("~")
            return {
                "name": fields[1] or code,
                "symbol": f"{code}",
                "current_price": _to_float(fields[3]),
                "pre_close": _to_float(fields[4]),
                "open": _to_float(fields[5]),
                "high": _to_float(fields[33]) if len(fields) > 33 else None,
                "low": _to_float(fields[34]) if len(fields) > 34 else None,
                "volume": _to_float(fields[36]) if len(fields) > 36 else None,
                "amount": _to_float(fields[37]) if len(fields) > 37 else None,
                "turnover_rate": _to_float(fields[38]) if len(fields) > 38 else None,
                "current_change_pct": _to_float(fields[32]) if len(fields) > 32 else None,
                "data_source": "tencent-async",
            }
    except Exception as exc:
        _logger.debug("Async quote fetch failed for %s: %s", code, exc)
        return {"error": str(exc), "code": code}


async def fetch_qfq_daily_async(
    session: "aiohttp.ClientSession",
    code: str,
    days: int = 300,
) -> list[dict[str, Any]]:
    """Fetch forward-adjusted daily K-line bars asynchronously.

    Args:
        session: aiohttp client session
        code: Stock code
        days: Number of days of history

    Returns:
        List of bar dicts
    """
    qq = _resolve_qq_symbol(code)
    raw_params = f"_var=kline_dayhfq&param={qq},day,,,{max(days, 20)},qfq"
    url = f"{TENCENT_FQKLINE_URL}?{raw_params}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text(encoding="utf-8", errors="ignore")
            # Extract JSON from JSONP
            raw = text.strip()
            if "=" in raw:
                raw = raw.split("=", 1)[1].strip()
            payload = json.loads(raw.rstrip(";"))
            sec_data = (payload.get("data") or {}).get(qq) or {}
            rows = sec_data.get("qfqday") or sec_data.get("day") or []
            bars: list[dict[str, Any]] = []
            for row in rows:
                if isinstance(row, list) and len(row) >= 6:
                    bars.append({
                        "date": row[0],
                        "open": _to_float(row[1]),
                        "close": _to_float(row[2]),
                        "high": _to_float(row[3]),
                        "low": _to_float(row[4]),
                        "volume": _to_float(row[5]),
                        "data_source": "tencent-async",
                    })
            return bars
    except Exception as exc:
        _logger.debug("Async daily bars fetch failed for %s: %s", code, exc)
        return []


async def fetch_all_quotes_async(codes: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch quotes for multiple stocks concurrently.

    Args:
        codes: List of stock codes

    Returns:
        Dict mapping code → quote dict
    """
    if not _check_aiohttp():
        _logger.warning("aiohttp not installed, falling back to sync")
        return _fetch_all_quotes_sync_fallback(codes)

    import aiohttp
    ssl_ctx = ssl._create_unverified_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {code: fetch_quote_async(session, code) for code in codes}
        results: dict[str, dict[str, Any]] = {}
        for code, task in tasks.items():
            results[code] = await task
        return results


async def fetch_all_daily_async(codes: list[str], days: int = 300) -> dict[str, list[dict[str, Any]]]:
    """Fetch daily bars for multiple stocks concurrently.

    Args:
        codes: List of stock codes
        days: Number of days of history

    Returns:
        Dict mapping code → list of bar dicts
    """
    if not _check_aiohttp():
        _logger.warning("aiohttp not installed, falling back to sync")
        return _fetch_all_daily_sync_fallback(codes, days)

    import aiohttp
    ssl_ctx = ssl._create_unverified_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {code: fetch_qfq_daily_async(session, code, days) for code in codes}
        results: dict[str, list[dict[str, Any]]] = {}
        for code, task in tasks.items():
            results[code] = await task
        return results


# ── Sync wrappers (backward compatibility) ──

def fetch_quote_sync(code: str) -> dict[str, Any]:
    """Sync wrapper for fetch_quote_async."""
    if not _check_aiohttp():
        return _fetch_quote_sync_fallback(code)
    return asyncio.run(fetch_quote_async(None, code))  # type: ignore[arg-type]


def fetch_qfq_daily_sync(code: str, days: int = 300) -> list[dict[str, Any]]:
    """Sync wrapper for fetch_qfq_daily_async."""
    if not _check_aiohttp():
        return _fetch_daily_sync_fallback(code, days)
    return asyncio.run(fetch_qfq_daily_async(None, code, days))  # type: ignore[arg-type]


# ── Sync fallbacks (when aiohttp not installed) ──

def _fetch_quote_sync_fallback(code: str) -> dict[str, Any]:
    """Sync fallback using urllib."""
    from trader_shared.light_data import HttpClient, resolve_security, fetch_quote
    http = HttpClient()
    sec = resolve_security(code)
    return fetch_quote(sec, http)


def _fetch_daily_sync_fallback(code: str, days: int) -> list[dict[str, Any]]:
    """Sync fallback using urllib."""
    from trader_shared.light_data import HttpClient, resolve_security, fetch_qfq_daily
    http = HttpClient()
    sec = resolve_security(code)
    return fetch_qfq_daily(sec, http, days=days)


def _fetch_all_quotes_sync_fallback(codes: list[str]) -> dict[str, dict[str, Any]]:
    """Sync fallback for batch quote fetching."""
    from concurrent.futures import ThreadPoolExecutor
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_fetch_quote_sync_fallback, code): code for code in codes}
        for future in futures:
            code = futures[future]
            try:
                results[code] = future.result()
            except Exception as exc:
                results[code] = {"error": str(exc), "code": code}
    return results


def _fetch_all_daily_sync_fallback(codes: list[str], days: int) -> dict[str, list[dict[str, Any]]]:
    """Sync fallback for batch daily bars fetching."""
    from concurrent.futures import ThreadPoolExecutor
    results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_fetch_daily_sync_fallback, code, days): code for code in codes}
        for future in futures:
            code = futures[future]
            try:
                results[code] = future.result()
            except Exception as exc:
                _logger.debug("Sync daily fetch failed for %s: %s", code, exc)
                results[code] = []
    return results
