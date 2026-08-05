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
    import trader_shared.cache_utils as _cu

    code = str(ts_code or "").strip()
    if not code:
        return []

    today = _cu.cache_calendar_date()

    # 1) 内存
    mem = _cyq_mem.get(code)
    if mem is not None and mem[0] == today:
        return list(mem[1])

    # 2) 文件：fetch_date == 今天 → 直接用
    cached = _cu.get_cached(_cu.CACHE_CYQ, code.replace(".", "_"), ttl=_cu.TTL_CYQ)
    if cached is not None and _cu.is_fetch_date_today(cached.data, today):
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
            _cu.set_cached(_cu.CACHE_CYQ, code.replace(".", "_"), payload)
        except OSError as exc:
            _logger.debug("cyq cache write failed for %s: %s", code, exc)
        _cyq_mem[code] = (today, rows)
    return list(rows)


def get_cyq_chips(ts_code: str, trade_date: str) -> list[dict[str, Any]]:
    """获取每日筹码分布（逐价位）。"""
    client = get_client()
    return client.query_cyq_chips(ts_code, trade_date)


_cyq_chips_mem: dict[str, tuple[str, list[dict[str, Any]]]] = {}


def get_cyq_chips_cached(ts_code: str, trade_date: str = "") -> list[dict[str, Any]]:
    """逐价位筹码：按 ts_code+trade_date 同日缓存。"""
    import trader_shared.cache_utils as _cu

    code = str(ts_code or "").strip()
    day = str(trade_date or "").strip()
    if not code:
        return []
    if not day:
        # 无日期时尝试用 cyq_perf 最新交易日
        perf = get_cyq_perf_cached(code)
        if perf:
            day = str(max(perf, key=lambda x: str(x.get("trade_date", ""))).get("trade_date") or "")
    if not day:
        return []
    key = f"{code}|{day}"
    today = _cu.cache_calendar_date()
    mem = _cyq_chips_mem.get(key)
    if mem is not None and mem[0] == today:
        return list(mem[1])
    cache_key = f"{code.replace('.', '_')}_{day}"
    cached = _cu.get_cached(getattr(_cu, "CACHE_CYQ_CHIPS", _cu.CACHE_CYQ), cache_key, ttl=getattr(_cu, "TTL_CYQ", 86400))
    if cached is not None and isinstance(cached.data, dict) and _cu.is_fetch_date_today(cached.data, today):
        rows = cached.data.get("rows")
        if isinstance(rows, list):
            _cyq_chips_mem[key] = (today, rows)
            return list(rows)
    try:
        rows = get_cyq_chips(code, day) or []
    except Exception as exc:
        _logger.debug("get_cyq_chips network failed for %s %s: %s", code, day, exc)
        if cached is not None and isinstance(cached.data, dict):
            old = cached.data.get("rows")
            if isinstance(old, list) and old:
                return list(old)
        return []
    if rows:
        payload = {"fetch_date": today, "rows": rows, "trade_date": day}
        try:
            _cu.set_cached(getattr(_cu, "CACHE_CYQ_CHIPS", _cu.CACHE_CYQ), cache_key, payload)
        except OSError as exc:
            _logger.debug("cyq_chips cache write failed for %s: %s", code, exc)
        _cyq_chips_mem[key] = (today, rows)
    return list(rows)


def cyq_chips_to_peaks(
    rows: list[dict[str, Any]] | None,
    *,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """把 cyq_chips 逐价位转成主峰候选。

    兼容字段：price/cost/pricecenter；percent/percent_chip/ratio；volume/vol。

    注意 percent 口径：
    - 专属网关常见：0.42 = 0.42%（各档之和≈100）
    - 少数源：0.0042 = 0.42%（各档之和≈1）
    不能把「已经是百分数且 <1.5 的小档」再 *100。
    """
    if not rows:
        return []

    parsed: list[tuple[float, float, float]] = []  # price, raw_share, vol
    for r in rows:
        if not isinstance(r, dict):
            continue
        px = r.get("price")
        if px is None:
            px = r.get("cost")
        if px is None:
            px = r.get("pricecenter")
        try:
            price = float(px or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        share = r.get("percent")
        if share is None:
            share = r.get("percent_chip")
        if share is None:
            share = r.get("ratio")
        try:
            share_raw = float(share or 0)
        except (TypeError, ValueError):
            share_raw = 0.0
        vol = r.get("volume")
        if vol is None:
            vol = r.get("vol")
        try:
            vol_f = float(vol or 0)
        except (TypeError, ValueError):
            vol_f = 0.0
        if share_raw <= 0 and vol_f <= 0:
            continue
        parsed.append((price, share_raw, vol_f))
    if not parsed:
        return []

    # 判定 share 是「百分数」还是「0~1 比例」
    shares = [s for _, s, _ in parsed if s > 0]
    scale = 1.0
    if shares:
        total = sum(shares)
        mx = max(shares)
        # 总和接近 1（或明显 < 5）且最大值很小 → 比例制，转百分
        if total <= 5.0 and mx <= 1.5:
            scale = 100.0

    scored: list[dict[str, Any]] = []
    for price, share_raw, vol_f in parsed:
        share_f = share_raw * scale if share_raw > 0 else 0.0
        score = share_f if share_f > 0 else vol_f
        if score <= 0:
            continue
        scored.append({
            "price": round(price, 2),
            "share_of_total": round(share_f, 2) if share_f > 0 else 0.0,
            "volume": vol_f,
            "_score": score,
        })
    if not scored:
        return []
    scored.sort(key=lambda x: -float(x.get("_score") or 0))
    out = []
    for item in scored[: max(1, int(top_n))]:
        item = dict(item)
        item.pop("_score", None)
        out.append(item)
    return out


def clear_cyq_mem_cache() -> None:
    """测试用：清空进程内 cyq / cyq_chips 缓存。"""
    _cyq_mem.clear()
    _cyq_chips_mem.clear()
    _cyq_chips_mem.clear()
