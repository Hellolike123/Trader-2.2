# -*- coding: utf-8 -*-
"""风险旗 / 实时锚点 / fusion 仪表标签。"""
from __future__ import annotations

from typing import Any

from trader_shared.report_pipeline._common import MarkFn, _noop_mark  # noqa: F401

def detect_risk_flags(
    stock_name: str,
    quote: dict[str, Any] | None,
    bars: list | None,
) -> list[str]:
    """ST / 停牌 / 新股 风险旗（自 build_report 迁出，行为不变）。"""
    from trader_shared.light_data import to_float

    quote = quote if isinstance(quote, dict) else {}
    bars = bars or []
    risk_flags: list[str] = []
    name = str(stock_name or quote.get("name") or "")
    if "ST" in name or "*ST" in name:
        risk_flags.append("ST")
    cp = to_float(quote.get("current_price"))
    pc = to_float(quote.get("pre_close"))
    vol = to_float(quote.get("volume"))
    is_suspended = (
        cp is not None
        and pc is not None
        and vol is not None
        and cp > 0
        and abs(cp - pc) < 1e-6
        and vol < 1
    )
    if is_suspended:
        risk_flags.append("停牌")
    if len(bars) < 60:
        risk_flags.append("新股")
    return risk_flags


def build_live_bar_anchor(
    quote: dict[str, Any] | None,
    bars: list | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """盘中实时价锚点 live_bar（不并入 bars）与 intraday_as_of。"""
    quote = quote if isinstance(quote, dict) else {}
    bars = bars or []
    _today = str(quote.get("trade_date") or "")[:10]
    _last_date = (
        str(bars[-1].get("date") or bars[-1].get("trade_date") or "")[:10] if bars else ""
    )
    _cp = quote.get("current_price")
    live_bar = None
    if _today and _last_date != _today and _cp is not None and float(_cp) > 0:
        _cp_f = float(_cp)
        _pre = quote.get("pre_close")
        try:
            _prev_close = float(_pre) if _pre is not None and float(_pre) > 0 else None
        except (TypeError, ValueError):
            _prev_close = None
        if _prev_close is None:
            _chg = float(quote.get("current_change_pct") or 0)
            _prev_close = _cp_f / (1 + _chg / 100) if _chg != 0 else _cp_f
        def _qf(key: str, default: float) -> float:
            v = quote.get(key)
            try:
                f = float(v) if v is not None else default
                return f if f > 0 else default
            except (TypeError, ValueError):
                return default
        _open = _qf("open", _prev_close)
        _high = _qf("high", max(_cp_f, _open))
        _low = _qf("low", min(_cp_f, _open))
        # 保证 high/low 包住现价
        _high = max(_high, _cp_f, _open)
        _low = min(_low, _cp_f, _open)
        _prev_bar = bars[-1] if bars else {}
        _vol = quote.get("volume")
        try:
            _vol_f = float(_vol) if _vol is not None else 0.0
        except (TypeError, ValueError):
            _vol_f = 0.0
        live_bar = {
            "date": _today,
            "open": _open,
            "close": _cp_f,
            "high": _high,
            "low": _low,
            "volume": _vol_f,
            "data_source": "quote-today",
            "data_status": "partial",
            "atr14": _prev_bar.get("atr14", 0),
            "atr_ratio": _prev_bar.get("atr_ratio", 0),
            "atr7": _prev_bar.get("atr7", 0),
            "tr": _prev_bar.get("tr", 0),
            "is_synthetic": True,
        }
    intraday_as_of = _last_date if live_bar else None
    return live_bar, intraday_as_of


def tag_fusion_as_instrument(fusion: dict[str, Any] | None) -> dict[str, Any]:
    """标记 fusion 产品角色为仪表（不改分数/动作计算）。"""
    if not isinstance(fusion, dict):
        return {}
    fusion = dict(fusion)
    fusion["product_role"] = "instrument"
    fusion["product_role_note"] = "仅参考；出手以 decision_view（共振∧策略∧纪律）为准"
    return fusion


