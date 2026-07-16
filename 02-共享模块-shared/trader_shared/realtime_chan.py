"""T0 盘中实时缠论增量引擎（Phase 2 接入，opt-in 默认关）。

设计要点：
- 复用 Phase 1 的 ``ChanlunEngine``（``update_bar`` append/replace + ``get_analysis``），
  不重实现任何缠论算法。
- 基于 ``build_plan`` 的结果（``daily_bars`` + ``current_price`` + ``quote``）合成
  当日 forming bar，盘中价格变动即时反映到笔/段/买卖点。
- 优先 ``ChanlunEngine.load`` 预热状态（``cache warm`` 预建），失败（无预热/版本不符）
  则静默回退到从 ``daily`` 批量 build。
- ``get_realtime_chan`` 返回 ``{result, signature}``；``signature`` 为可跨 tick 比对
  的指纹，供 monitor 检测「日内新成笔 / 新买卖点」。

⚠️ 本模块所有对外调用方（monitor.run_once）必须用 ``T0_REALTIME_CHAN=1`` 环境变量
开关包裹，默认未设时绝不改变现有批量路径。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from trader_shared.light_data import to_float
from trader_shared.config import CHANLUN_STATE_DIR
from trader_shared.chan_core import ChanlunEngine


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
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    eng = _load_or_build(symbol, daily, state_dir)
    eng.update_bar(today_bar)  # 同 date → replace 语义
    result = eng.get_analysis(current, symbol=symbol)
    signature = _chan_signature(result)
    return {"result": result, "signature": signature}
