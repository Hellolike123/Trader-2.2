# -*- coding: utf-8 -*-
"""报告与 levels 自洽修正。"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.report_pipeline._common import MarkFn, _noop_mark

_logger = get_logger(__name__)

def sync_report_with_data(report: dict, levels: dict) -> dict:
    """脚本自洽校验：修正数据与文字标签的矛盾（自 report_builder 迁出）。"""
    from trader_shared.light_data import to_float
    """脚本自洽校验：修正数据与文字标签的矛盾"""
    current  = float(report.get("current") or 0)
    support  = float(report.get("support") or 0)
    resistance = float(report.get("resistance") or 0)
    confirm  = float(report.get("confirm") or 0)
    stop     = float(report.get("stop") or 0)
    take     = float(report.get("take") or 0)
    scene    = str(report.get("scene") or "")
    state_label  = str(report.get("state_label") or "")
    ma5  = to_float(levels.get("ma_values", {}).get("ma5"))
    ma10 = to_float(levels.get("ma_values", {}).get("ma10"))
    # MA 趋势与文字标签
    if ma5 is not None and ma10 is not None and current > 0:
        if ma5 > ma10 and "空头" in state_label:
            report["state_label"] = state_label.replace("空头", "多头")
        elif ma5 < ma10 and "多头" in state_label:
            report["state_label"] = state_label.replace("多头", "空头")
    # support > resistance → 筹码与 ATR 模块打架
    if support > 0 and resistance > 0 and support >= resistance:
        report["resistance"] = round(support * 1.03, 2)
        report["support"] = round(resistance * 0.97, 2)
        support = float(report["support"])
        resistance = float(report["resistance"])
    # stop 须在支撑下方；改 hard stop 后同步 effective_stop（勿留下旧 trailing 口径）
    if stop > 0 and support > 0 and stop >= support:
        report["stop"] = round(support * 0.97, 2)
        stop = float(report["stop"])
    try:
        from trader_shared.structure_core import effective_stop_price

        _eff = effective_stop_price(report.get("stop"), report.get("trailing_stop"))
        if _eff is not None:
            report["effective_stop"] = _eff
    except Exception:
        pass
    # take < confirm（止盈永远高于确认位）
    if take > 0 and confirm > 0 and take <= confirm:
        _zw = float(levels.get("zone_width_pct", 0.02) or 0.02)
        report["take"] = round(confirm * (1 + _zw), 2)
    # 场景与数值的逻辑一致性
    if scene in ("突破确认", "突破观察") and round(current, 2) < round(confirm, 2):
        report["scene"]        = "观望"
        report["state_label"]  = "未确认"
    elif scene in ("低吸观察", "防守观察") and current < support and support > 0:
        report["scene"]        = "破位下行"
        report["state_label"]  = "破位下行"
    elif scene == "冲高减仓" and current < support and support > 0:
        report["scene"]        = "低吸观察"
        report["state_label"]  = "低吸观察"
    elif scene == "突破观察" and current >= confirm and confirm > 0:
        report["scene"]        = "突破确认"
        report["state_label"]  = "趋势走强"
    elif scene in ("空间不足",) and current < support and support > 0:
        report["scene"]        = "修复观察"
        report["state_label"]  = "修复观察"
    return report

