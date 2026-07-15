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


def _compute_level_verdicts(inner_buy_points, lower_bars, tf, price_tol, min_lower_bars, symbol):
    """对单个小级别跑 chanlun，返回 (verdicts, bottom_div_confirmed)。

    verdicts: 与 inner_buy_points 对齐的 list[(confirmed: bool, type: str)]。
    等价性闸门：lower_bars 缺失 / 过短 / 计算异常时返回 (None, False) → 调用方跳过该级别。
    """
    if not lower_bars or len(lower_bars) < min_lower_bars:
        return None, False
    try:
        lower_res = chanlun_analysis(
            lower_bars,
            current=lower_bars[-1]["close"],
            symbol=symbol,
            timeframe=tf,
        )
    except Exception:
        return None, False

    lower_inner = _resolve_inner(lower_res)
    if lower_inner is None:
        return None, False

    lower_bps = lower_inner.get("buy_points", []) or []
    lower_div = lower_inner.get("divergence", {}) or {}
    lower_bottom_div = bool(lower_div.get("bottom_divergence"))

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

    verdicts = []
    for bp in inner_buy_points:
        if not isinstance(bp, dict):
            verdicts.append((False, ""))
            continue
        ok, ctype = _match(bp.get("price"))
        verdicts.append((ok, ctype or ""))
    return verdicts, lower_bottom_div


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
    if inner is None:
        return daily_result
    bps = inner.get("buy_points", []) or []
    verdicts, bottom_div_c = _compute_level_verdicts(
        bps, lower_bars, lower_timeframe, price_tol, min_lower_bars, symbol)
    if verdicts is None:
        return daily_result

    confirmed_count = 0
    for bp, (ok, ctype) in zip(bps, verdicts):
        if not isinstance(bp, dict):
            continue
        bp["lower_confirmed"] = ok
        bp["lower_confirm_type"] = ctype
        if ok:
            confirmed_count += 1

    # 底背驰确认：小级别同价位区间也出现底背驰即确认
    div = inner.get("divergence")
    if isinstance(div, dict) and div.get("bottom_divergence"):
        div["bottom_divergence_lower_confirmed"] = bottom_div_c

    daily_result["nesting_confirmation"] = {
        "lower_timeframe": lower_timeframe,
        "confirmed_count": confirmed_count,
        "total_buy_points": len(bps),
        "bottom_divergence_confirmed": bottom_div_c,
    }
    return daily_result


def confirm_nested_chain(
    daily_result: dict,
    lower_series: list[tuple[str, list[dict]]],
    price_tol: float = 0.03,
    min_lower_bars: int = 60,
    symbol: str | None = None,
) -> dict:
    """多级别区间套：日线买卖点经 30m → 5m → 1m 逐级确认（粗→细），用于 T0 精确定位。

    lower_series: 有序的 (timeframe, bars) 列表，从粗到细，例如
                  [("30m", bars30), ("5m", bars5), ("1m", bars1)]。
    只有 lower_series[0] 为 30m 时，顶层 lower_confirmed 退化为与单级别一致（兼容旧渲染）。

    标注增强（每个日线 buy_point）：
      - lower_confirmed / lower_confirm_type   : 取自"首个可用级别"（默认 30m，兼容 report_core 旧渲染）
      - nesting_chain                          : 各级别 [{timeframe, confirmed, type}] 列表
      - nesting_confirmed                      : 所有可用级别均确认（T0 高置信入场）
    顶层 nesting_confirmation 增加 levels / chain 汇总。

    等价性闸门：若无任何级别取到数据，原样返回（零副作用）。
    """
    inner = _resolve_inner(daily_result)
    if inner is None or not lower_series:
        return daily_result
    bps = inner.get("buy_points", []) or []

    chain: list[dict] = []                          # 各级别汇总（含 skipped）
    per_bp_levels: list[list] = [[] for _ in bps]   # 每个买点在各级别的 (tf, ok, ctype)
    bottom_div_per_level: list[bool] = []
    has_any_data = False

    for tf, bars in lower_series:
        verdicts, bottom_div_c = _compute_level_verdicts(
            bps, bars, tf, price_tol, min_lower_bars, symbol)
        if verdicts is None:
            chain.append({"timeframe": tf, "status": "skipped", "reason": "no_data_or_error"})
            continue
        has_any_data = True
        chain.append({
            "timeframe": tf,
            "status": "done",
            "bottom_divergence_confirmed": bottom_div_c,
        })
        bottom_div_per_level.append(bottom_div_c)
        for i, (ok, ctype) in enumerate(verdicts):
            per_bp_levels[i].append((tf, ok, ctype))

    if not has_any_data:
        return daily_result

    confirmed_count = 0
    for i, bp in enumerate(bps):
        if not isinstance(bp, dict):
            continue
        levels = per_bp_levels[i]
        if not levels:
            continue
        first_tf, first_ok, first_ct = levels[0]
        bp["lower_confirmed"] = first_ok
        bp["lower_confirm_type"] = first_ct
        bp["nesting_chain"] = [
            {"timeframe": t, "confirmed": c, "type": ct} for (t, c, ct) in levels
        ]
        bp["nesting_confirmed"] = all(c for (_, c, _) in levels)
        if bp["nesting_confirmed"]:
            confirmed_count += 1

    div = inner.get("divergence")
    _all_div = all(bottom_div_per_level) if bottom_div_per_level else False
    if isinstance(div, dict) and div.get("bottom_divergence"):
        div["bottom_divergence_lower_confirmed"] = _all_div

    daily_result["nesting_confirmation"] = {
        "lower_timeframe": lower_series[0][0],
        "levels": [c.get("timeframe") for c in chain],
        "chain": chain,
        "confirmed_count": confirmed_count,
        "total_buy_points": len(bps),
        "bottom_divergence_confirmed": _all_div,
    }
    return daily_result
