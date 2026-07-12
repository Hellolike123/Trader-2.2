"""筹码分布数据模块 — 基于 Tushare 的 cyq_perf / cyq_chips。

提供：
- 筹码分布（成本分位数、获利比例、加权均价）
- 每日筹码（逐价位筹码分布）

替代自行推算的 chip_distribution.py，数据更准确（官方计算）。

使用方式：
    from trader_shared.chip_data import get_cyq_perf, get_cyq_chips
    perf = get_cyq_perf("688248.SH", start_date="20260701")
    chips = get_cyq_chips("688248.SH", trade_date="20260710")
"""
from __future__ import annotations

from typing import Any

from trader_shared.tushare_client import get_client


def get_cyq_perf(
    ts_code: str, start_date: str = "", end_date: str = ""
) -> list[dict[str, Any]]:
    """获取筹码分布（成本分位数、获利比例、加权均价）。

    返回字段：ts_code, trade_date, his_low, his_high, cost_5pct, cost_15pct,
    cost_50pct, cost_85pct, cost_95pct, weight_avg, winner_rate 等。
    """
    client = get_client()
    return client.query_cyq_perf(ts_code, start_date, end_date)


def get_cyq_chips(ts_code: str, trade_date: str) -> list[dict[str, Any]]:
    """获取每日筹码分布（逐价位）。"""
    client = get_client()
    return client.query_cyq_chips(ts_code, trade_date)
