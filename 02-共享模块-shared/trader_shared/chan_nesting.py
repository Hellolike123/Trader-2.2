#!/usr/bin/env python3
"""区间套确认：日线买卖点 / 底背驰经小级别(默认 30m)确认，过滤假信号。

设计原则（与项目最小侵入风格一致）：
- 纯函数，不碰网络。lower_bars 由调用方负责获取（生产环境走 DataProvider.fetch_kline）。
- 当 lower_bars 缺失 / 过短 / 计算异常时，原样返回 daily_result，零副作用（等价性闸门）。
- 只对日线 chanlun 结果做"标注增强"，不改任何价格 / 结构 / 评分。

用法（生产接入点见 report_builder.py）：
    from trader_shared.chan_nesting import confirm_daily_with_lower
    chan_result = confirm_daily_with_lower(chan_result, lower_bars_30m, lower_timeframe="30m")
"""
from __future__ import annotations

from typing import Any

from trader_shared.chan_core import chanlun_analysis


def _resolve_inner(daily_result: Any):
    """定位 chanlun 内层 dict。

    兼容两种形态：
      - {"chanlun": {buy_points, divergence, ...}}   （chanlun_analysis 透传形态）
      - {buy_points, divergence, ...}                （已剥层形态）
    返回内层 dict 或 None。
    """
    if not isinstance(daily_result, dict):
        return None
    if "chanlun" in daily_result and isinstance(daily_result["chanlun"], dict):
        inner = daily_result["chanlun"]
        # 防御：再剥一层（极端嵌套）
        if "chanlun" in inner and isinstance(inner["chanlun"], dict) and "buy_points" not in inner:
            return inner["chanlun"]
        return inner
    if "buy_points" in daily_result or "divergence" in daily_result:
        return daily_result
    return None


# 小级别买点类型（用于价位匹配确认）
_LOWER_BUY_TYPES = ("一类买", "二类买", "类二买")


def confirm_daily_with_lower(
    daily_result: dict,
    lower_bars: list[dict] | None = None,
    lower_timeframe: str = "30m",
    price_tol: float = 0.03,
    min_lower_bars: int = 60,
    symbol: str | None = None,
) -> dict:
    """用 lower_bars（小级别 K 线）确认日线买卖点 / 底背驰。

    标注增强：
      - 每个日线 buy_point 增加 lower_confirmed(bool) / lower_confirm_type(str)
      - divergence 增加 bottom_divergence_lower_confirmed(bool)
      - 顶层增加 nesting_confirmation 汇总

    返回原 daily_result（原地增强，无网络依赖）。
    """
    inner = _resolve_inner(daily_result)
    if inner is None or not lower_bars or len(lower_bars) < min_lower_bars:
        return daily_result

    try:
        lower_res = chanlun_analysis(
            lower_bars,
            current=lower_bars[-1]["close"],
            symbol=symbol,
            timeframe=lower_timeframe,
        )
    except Exception:
        return daily_result

    lower_inner = _resolve_inner(lower_res)
    if lower_inner is None:
        return daily_result

    lower_bps = lower_inner.get("buy_points", []) or []
    lower_div = lower_inner.get("divergence", {}) or {}
    lower_bottom_div = bool(lower_div.get("bottom_divergence"))

    # 小级别买点价位 / 类型
    lower_buy = [
        (bp.get("price"), bp.get("type"))
        for bp in lower_bps
        if bp.get("type") in _LOWER_BUY_TYPES
    ]

    def _match(price):
        """价位匹配：日线买点价附近是否有小级别同方向买点。"""
        if price is None:
            return False, None
        for lp, lt in lower_buy:
            if lp is not None and abs(lp - price) / price <= price_tol:
                return True, lt
        return False, None

    confirmed_count = 0
    for bp in inner.get("buy_points", []) or []:
        if not isinstance(bp, dict):
            continue
        ok, ctype = _match(bp.get("price"))
        bp["lower_confirmed"] = ok
        bp["lower_confirm_type"] = ctype or ""
        if ok:
            confirmed_count += 1

    # 底背驰确认：小级别同价位区间也出现底背驰即确认
    div = inner.get("divergence")
    if isinstance(div, dict) and div.get("bottom_divergence"):
        div["bottom_divergence_lower_confirmed"] = lower_bottom_div

    daily_result["nesting_confirmation"] = {
        "lower_timeframe": lower_timeframe,
        "confirmed_count": confirmed_count,
        "total_buy_points": len(inner.get("buy_points", []) or []),
        "bottom_divergence_confirmed": lower_bottom_div,
    }
    return daily_result
