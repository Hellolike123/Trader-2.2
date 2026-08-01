# -*- coding: utf-8 -*-
"""阶段字段命名纪律（architecture #2 / BUSINESS §2.0）。

三套真相，禁止混用：

- ``midline_stage`` / ``conclusion.stage_line``
  周线威科夫短词 → 面板「阶段：」（吸筹/主升/派发/无阶段…）
- ``major_stage``
  日线四阶段 → 门控 / 选股池软信号（蓄势/主升/派发/衰退…）
- ``short_term_momentum``
  EXPMA 短期动能 → 走强/修复/震荡/转弱

``report["stage"]`` 是 ``short_term_momentum`` 的兼容别名（池/旧读方）；
**不是** ``major_stage``，也不是轻量 ``determine_stage`` 位置分类。
面板「阶段：」**禁止**指向 ``major_stage``。
"""
from __future__ import annotations

from typing import Any

# 日线四阶段词表（major_stage）
MAJOR_STAGE_VOCAB = frozenset({
    "蓄势", "蓄势偏强", "蓄势偏弱", "主升", "派发", "衰退",
})

# 短期动能词表（short_term_momentum / report["stage"] 别名）
SHORT_MOMENTUM_VOCAB = frozenset({"走强", "修复", "震荡", "转弱"})

# 中线面板阶段不足标记（不得靠 major_stage 软绿）
MIDLINE_STAGE_INSUFFICIENT = frozenset({"无阶段", ""})


def alias_report_stage(short_term_momentum: str | None) -> str:
    """``report["stage"]`` ← ``short_term_momentum``（缺省震荡）。"""
    s = str(short_term_momentum or "").strip()
    return s if s else "震荡"


def major_stage_from_report(r: dict[str, Any] | None) -> str:
    """只读 ``major_stage``；禁止把 走强/修复 等动能词映射成主升/蓄势。"""
    if not isinstance(r, dict):
        return ""
    major = str(r.get("major_stage") or "").strip()
    if major:
        return major
    # 遗留：仅当 stage 已是日线四阶段词时接受；绝不做 走强→主升
    legacy = str(r.get("stage") or "").strip()
    if legacy in MAJOR_STAGE_VOCAB:
        return legacy
    if legacy.startswith(("蓄势", "主升", "派发", "衰退")):
        return legacy
    return ""
