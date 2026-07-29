# -*- coding: utf-8 -*-
"""买点盖生命周期挂接。"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.report_pipeline._common import MarkFn, _noop_mark

_logger = get_logger(__name__)

def apply_buy_point_lifecycle(
    report: dict[str, Any],
    *,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """买点盖生命周期（L1 判定 + L2 持久化）：写字段；失败则只收紧 discipline 新开。

    与 build_report 原逻辑一致；失败不抛。
    """
    _mark = mark or _noop_mark
    if not isinstance(report, dict):
        return report
    try:
        from trader_shared.buy_point_lifecycle import build_buy_point_lifecycle_for_report
        from trader_shared.chan_discipline import format_entry_line_c1

        _life = build_buy_point_lifecycle_for_report(report, persist=True)
        report["buy_point_lifecycle"] = _life
        if _life.get("status") == "failed":
            _disc = report.get("discipline") if isinstance(report.get("discipline"), dict) else {}
            _disc["allow_new_entry"] = False
            _cl = (
                _disc.get("entry_checklist")
                if isinstance(_disc.get("entry_checklist"), dict)
                else {}
            )
            _cl = dict(_cl)
            _cl["all_green"] = False
            _flags = _cl.get("flags") if isinstance(_cl.get("flags"), dict) else {}
            _flags = dict(_flags)
            _flags["short_trigger"] = False
            _cl["flags"] = _flags
            _items = _cl.get("items") if isinstance(_cl.get("items"), dict) else {}
            _items = dict(_items)
            _items["short_trigger"] = False
            _cl["items"] = _items
            _miss = list(_cl.get("missing_labels") or [])
            if "买点已失效" not in _miss:
                _miss.append("买点已失效")
            _cl["missing_labels"] = _miss
            _cl["entry_line"] = format_entry_line_c1(all_green=False, missing=_miss)
            _disc["entry_checklist"] = _cl
            _disc["entry_line"] = _cl["entry_line"]
            report["discipline"] = _disc
        _mark("buy_point_lifecycle")
    except Exception as _life_exc:
        _logger.debug("buy_point_lifecycle skip: %s", _life_exc)
        report.setdefault("buy_point_lifecycle", {"status": "none", "display_line": ""})
    return report

