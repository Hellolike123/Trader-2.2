# -*- coding: utf-8 -*-
"""Fusion 置信度映射（中性模块）。

从 classic_mappers 软抽，供 cards / classic re-export 共用。
禁止 analysis 经此再依赖 fusion_classic_mappers。
"""
from __future__ import annotations

_confidence_cache: dict[str, float] | None = None


def _load_confidence_params() -> dict[str, float]:
    """加载置信度映射参数。优先从 calibrated_params.json 读取，fallback 到 config 默认值。带模块级缓存。"""
    global _confidence_cache
    if _confidence_cache is not None:
        return _confidence_cache

    from trader_shared.config import CONFIDENCE_MAPPING_DEFAULTS
    # NOTE: calibration capability (self_calibration) is not implemented yet;
    # we always fall back to the config defaults below.
    _confidence_cache = dict(CONFIDENCE_MAPPING_DEFAULTS)
    return _confidence_cache


def _score_to_confidence(score: float) -> float:
    """从 0-100 分数映射到 0-1 置信度。

    U 型函数: 两端信号强 → 置信度高, 中间灰区 → 置信度低
    阈值从 calibrated_params.json 读取（可校准），fallback 到 config 默认值。
    """
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 0.2

    p = _load_confidence_params()
    ce, cs, cm, cf = p["conf_extreme"], p["conf_strong"], p["conf_medium"], p["conf_floor"]
    he, hs = p["high_extreme"], p["high_strong"]
    le, ls = p["low_extreme"], p["low_strong"]

    if score >= he:
        return ce
    if score >= hs:
        return cs
    if score >= (hs - 5):  # 60 附近
        return cm

    if score <= le:
        return ce
    if score <= ls:
        return cs
    if score <= (ls + 5):  # 40 附近
        return cm

    # 灰区: V 形, 50 最低 (cf), 向两侧上升 (cm)
    mid = 50
    half_width = (hs - 5) - mid  # 通常是 9
    if half_width <= 0:
        half_width = 9
    if score < mid:
        ratio = (mid - score) / half_width
    else:
        ratio = (score - mid) / half_width
    return cf + ratio * (cm - cf)
