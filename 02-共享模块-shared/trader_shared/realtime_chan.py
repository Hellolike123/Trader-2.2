"""T0 盘中实时缠论增量引擎。

两个入口：
- ``get_realtime_chan``  — 日线级（opt-in，默认关，需 T0_REALTIME_CHAN=1）。
- ``get_realtime_chan_5m`` — 5 分钟级（T0 主路径，始终可用）。

设计要点：
- 复用 ``ChanlunEngine``（``update_bar`` append/replace + ``get_analysis``），
  不重实现任何缠论算法。
- 5m 路径：直接用 ``kline_5m`` bars 喂入引擎，每根 bar 有独立时间戳，
  盘中价格变动即时反映到笔/段/买卖点。
- 日线路径（遗留）：基于 ``daily_bars`` + ``quote`` 合成当日 forming bar。
- 优先 ``ChanlunEngine.load`` 预热状态（``cache warm`` 预建），失败则静默回退
  到从 bars 批量 build。
- 返回 ``{result, signature}``；``signature`` 为可跨 tick 比对的指纹，
  供 monitor 检测「日内新成笔 / 新买卖点」。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from trader_shared.light_data import to_float
from trader_shared.config import CHANLUN_STATE_DIR
from trader_shared.chan_core import ChanlunEngine


def _today_cn_str() -> str:
    try:
        from trader_shared.cn_time import today_cn
        return today_cn().isoformat()
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _load_or_build(symbol: str, daily: list[dict], state_dir: str = CHANLUN_STATE_DIR) -> ChanlunEngine:
    """优先 load 预热状态，失败（无预热/反序列化异常）则静默回退到批量 build。

    state 文件名按 Part B 约定为 ``{code}.json``（6 位代码）。T0 的 ``symbol`` 可能带
    交易所后缀（如 ``688248.SH``）或纯 6 位，故尝试多组候选文件名，最大化命中预热缓存。
    """
    candidates: list[str] = [str(symbol), str(symbol).replace(".", "")]
    m = re.search(r"\d{6}", str(symbol))
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        if not cand:
            continue
        path = f"{state_dir}/{cand}.json"
        if os.path.exists(path):
            try:
                return ChanlunEngine.load(path)
            except Exception:
                break  # 文件存在但损坏 → 回退批量 build
    eng = ChanlunEngine()
    for b in daily:
        eng.update_bar(b)
    return eng


def _chan_signature(result: dict | None) -> tuple:
    """从分析结果提取可跨 tick 比对的指纹。

    包含：structure_type + trend_label + 末笔 (direction, end_price) + 排序后的
    buy/sell_points type 列表。价格按 2 位四舍五入以容忍盘中 tick 抖动。
    """
    if not isinstance(result, dict):
        return ("empty",)
    strokes = result.get("strokes") or []
    last = strokes[-1] if strokes else {}
    end_price = to_float(last.get("end_price"))
    end_price = round(end_price, 2) if end_price is not None else None
    buy_types = tuple(sorted(bp.get("type") for bp in (result.get("buy_points") or [])))
    sell_types = tuple(sorted(sp.get("type") for sp in (result.get("sell_points") or [])))
    return (
        result.get("structure_type"),
        result.get("trend_label"),
        last.get("direction"),
        end_price,
        buy_types,
        sell_types,
    )


def get_realtime_chan(
    symbol: str,
    plan: dict,
    state_dir: str = CHANLUN_STATE_DIR,
) -> dict:
    """基于 build_plan 结果做实时缠论增量更新，返回 ``{result, signature}``。

    Args:
        symbol: 标的键（用于 load 预热状态文件）。
        plan: ``build_plan(target)`` 返回 dict，需含 ``current_price`` / ``quote``，
            以及日线 ``daily_bars``（位于 ``plan["data"]["daily_bars"]``，兼容顶层
            ``plan["daily_bars"]`` 兜底；``quote`` 兼容 ``plan["data"]["quote"]`` 与
            ``plan["quote"]``）。
        state_dir: 预热状态目录。

    Returns:
        {"result": <chanlun_analysis dict>, "signature": <tuple 指纹>}
    """
    # 日线：build_plan 把日线放进 plan["data"]["daily_bars"]，同时兼容顶层键兜底
    daily = (plan.get("data") or {}).get("daily_bars") or plan.get("daily_bars") or []
    current = to_float(plan.get("current_price") or 0)
    if not current and daily:
        current = to_float((daily[-1] or {}).get("close")) or 0.0

    # quote OHLC：兼容 plan["data"]["quote"] 与 plan["quote"] 两种布局
    quote = (plan.get("data") or {}).get("quote") or plan.get("quote") or {}
    last = daily[-1] if daily else {}
    today_bar = {
        "open": to_float(quote.get("open") if quote.get("open") is not None else last.get("open")),
        "high": to_float(quote.get("high") if quote.get("high") is not None else last.get("high")),
        "low": to_float(quote.get("low") if quote.get("low") is not None else last.get("low")),
        "close": current,
        "volume": to_float(quote.get("volume")) or 0,
        "date": _today_cn_str(),
    }

    eng = _load_or_build(symbol, daily, state_dir)
    eng.update_bar(today_bar)  # 同 date → replace 语义
    result = eng.get_analysis(current, symbol=symbol)
    signature = _chan_signature(result)
    return {"result": result, "signature": signature}


def _normalize_5m_bars(bars: list[dict]) -> list[dict]:
    """将 5m bars 的 ``date`` 归一化为带时分秒的唯一时间戳。

    上游 ``light_data`` 把分钟 K 的 ``date`` 截断成日（如 "2026-07-16"），
    完整时间戳放在 ``time`` 字段。ChanlunEngine 以 ``bar['date']`` 作唯一身份，
    同日所有 5m 棒 date 相同会导致后一根覆盖前一根，引擎塌缩成 1 根。
    """
    norm: list[dict] = []
    for b in bars:
        if not isinstance(b, dict):
            continue
        nb = dict(b)
        full_ts = nb.get("time") or nb.get("datetime") or nb.get("day") or ""
        if full_ts and (":" in str(full_ts) or " " in str(full_ts)):
            nb["date"] = str(full_ts)
        elif not nb.get("date"):
            nb["date"] = str(full_ts) if full_ts else ""
        norm.append(nb)
    return norm


def get_realtime_chan_5m(
    symbol: str,
    kline_5m: list[dict],
    current_price: float = 0.0,
    state_dir: str = CHANLUN_STATE_DIR,
) -> dict:
    """5 分钟级实时缠论增量更新，T0 主路径。

    直接用 5m bars 喂入 ChanlunEngine，不依赖日线。
    bars 不足 ``CHANLUN_MIN_BARS`` 根时返回空结果（不报错）。

    Args:
        symbol: 标的键（用于 load 预热状态文件）。
        kline_5m: 5 分钟 K 线列表（需含 OHLCV + 时间字段）。
        current_price: 当前价（用于 get_analysis）。
        state_dir: 预热状态目录。

    Returns:
        {"result": <chanlun_analysis dict>, "signature": <tuple 指纹>}
    """
    if not kline_5m or len(kline_5m) < 20:
        return {"result": None, "signature": ("insufficient_data",)}

    bars = _normalize_5m_bars(kline_5m)

    # 5m 预热状态文件名加后缀，避免与日线状态冲突
    candidates: list[str] = [str(symbol), str(symbol).replace(".", "")]
    m = re.search(r"\d{6}", str(symbol))
    if m:
        candidates.append(m.group(0))

    eng: ChanlunEngine | None = None
    for cand in candidates:
        if not cand:
            continue
        path = f"{state_dir}/{cand}_5m.json"
        if os.path.exists(path):
            try:
                eng = ChanlunEngine.load(path)
                break
            except Exception:
                break

    if eng is None:
        eng = ChanlunEngine()
        for b in bars:
            eng.update_bar(b)

    result = eng.get_analysis(current_price, symbol=symbol)
    signature = _chan_signature(result)
    return {"result": result, "signature": signature}
