"""Arch C：从 analysis_cards 构造 fusion 三席标准化信号。

契约：docs/designs/analysis-strategy-boundaries.md §阶段 C
不重算缠/威/筹，只读卡字段 → {direction, confidence, reason, raw_key, signal_tier?}
"""
from __future__ import annotations

from typing import Any

from trader_shared.signal_schema import SignalTier


def _as_dir(x: Any) -> int:
    try:
        d = int(x)
    except (TypeError, ValueError):
        return 0
    if d > 0:
        return 1
    if d < 0:
        return -1
    return 0


def _clip_conf(c: float) -> float:
    return max(0.0, min(0.95, float(c)))


_CHAN_CONF = {3: 0.8, 2: 0.55, 1: 0.35}


def _apply_point_conf_scales(card: dict[str, Any], default_conf: float) -> float:
    """对齐 classic _point_conf：点置信阶梯 + 区间套降权。"""
    base = default_conf
    pc = card.get("point_confidence")
    if pc is not None:
        try:
            base = _CHAN_CONF.get(int(pc), default_conf)
        except (TypeError, ValueError):
            pass
    if card.get("nesting_confirmed") is False:
        base *= 0.55
    elif card.get("lower_confirmed") is False:
        base *= 0.65
    elif card.get("same_level") is False:
        # 兼容旧卡：仅当无 nesting 字段时降权
        base *= 0.65
    return base


def chan_card_to_fusion_signal(card: dict[str, Any] | None) -> dict[str, Any]:
    """缠论卡 → fusion 信号（近似 _chan_to_signal 的强度语义）。"""
    c = card if isinstance(card, dict) else {}
    d = _as_dir(c.get("direction"))
    t_short = str(c.get("type_short") or "").strip()
    t_raw = str(c.get("type_raw") or "").strip()
    blob = t_short + t_raw + str(c.get("summary_line") or "")
    note = str(c.get("note") or "")

    conf = 0.35
    tier = SignalTier.NEUTRAL
    # 精确/最长优先：类二买 必须在 二买 之前；优先 type_raw / type_short 全等
    if t_raw == "一类买" or t_short == "一买" or "一类买" in t_raw:
        conf, tier = 0.8, SignalTier.CHAN_BUY_1
        d = 1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "类二买" or t_short == "类二买":
        conf, tier = 0.35, SignalTier.CHAN_BUY_LIKE2
        d = 1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "二类买" or t_short == "二买":
        conf, tier = 0.4, SignalTier.CHAN_BUY_2
        d = 1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "三类买" or t_short == "三买":
        conf, tier = 0.4, SignalTier.CHAN_BUY_3
        d = 1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "一类卖" or t_short == "一卖":
        conf, tier = 0.8, SignalTier.CHAN_SELL_1
        d = -1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "二类卖" or t_short == "二卖":
        conf, tier = 0.5, SignalTier.CHAN_SELL_2
        d = -1
        conf = _apply_point_conf_scales(c, conf)
    elif t_raw == "三类卖" or t_short == "三卖":
        conf, tier = 0.5, SignalTier.CHAN_SELL_3
        d = -1
        conf = _apply_point_conf_scales(c, conf)
    elif "底背驰" in blob or t_short == "底背驰":
        conf, tier = 0.5, SignalTier.CHAN_BOTTOM_DIVERGENCE
        d = 1
        if c.get("lower_confirmed") is False:
            conf *= 0.65
    elif "顶背驰" in blob or t_short == "顶背驰":
        conf, tier = 0.5, SignalTier.CHAN_TOP_DIVERGENCE
        d = -1
        if c.get("lower_confirmed") is False:
            conf *= 0.65
    elif "拉升段" in note or "拉升段" in blob or (d > 0 and "拉升" in note):
        conf, tier = 0.4, SignalTier.CHAN_TREND_UP
        d = 1
    elif "回调段" in note or "回调段" in blob or (d < 0 and "回调" in note):
        conf, tier = 0.4, SignalTier.CHAN_TREND_DOWN
        d = -1
    elif d != 0:
        conf = 0.35

    reason = str(c.get("summary_line") or c.get("note") or t_raw or "缠论中性")
    return {
        "direction": d,
        "confidence": round(_clip_conf(conf), 4),
        "reason": reason if reason.startswith("缠") or "背驰" in reason or "买" in reason or "卖" in reason else f"缠论{reason}",
        "raw_key": "chan",
        "signal_tier": tier,
        "from_card": True,
    }


def momentum_card_to_fusion_signal(card: dict[str, Any] | None) -> dict[str, Any]:
    c = card if isinstance(card, dict) else {}
    d = _as_dir(c.get("direction"))
    conf = c.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0
    # 卡上无 conf 但有 score 时补算（与 classic 一致）
    if conf is None and c.get("score") is not None:
        from trader_shared.fusion_core import _score_to_confidence

        conf_f = _score_to_confidence(c.get("score"))
    reason = str(c.get("reason") or c.get("summary_line") or "动量中性")
    return {
        "direction": d,
        "confidence": round(_clip_conf(conf_f), 4),
        "reason": reason,
        "raw_key": "momentum",
        "strength": str(c.get("strength") or ""),
        "from_card": True,
    }


def vpf_card_to_fusion_signal(card: dict[str, Any] | None) -> dict[str, Any]:
    from trader_shared.vpf_core import vpf_to_fusion_signal
    from trader_shared.signal_schema import vpf_tier_from_reason

    c = card if isinstance(card, dict) else {}
    # 已是 fusion 形态
    if c.get("raw_key") == "vpf" and "direction" in c:
        out = vpf_to_fusion_signal(c)
        out["from_card"] = True
        return out
    reason = str(c.get("reason") or c.get("summary_line") or "价量资金中性")
    d = _as_dir(c.get("direction"))
    raw_conf = c.get("confidence")
    try:
        conf_f = float(raw_conf) if raw_conf is not None else 0.2
    except (TypeError, ValueError):
        conf_f = 0.2
    out = {
        "direction": d,
        "confidence": round(_clip_conf(conf_f), 4),
        "reason": reason,
        "raw_key": "vpf",
        "fund_quality": str(c.get("fund_quality") or ""),
        "vp_direction": _as_dir(c.get("vp_direction")),
        "fund_direction": _as_dir(c.get("fund_direction")),
        "warning_type": str(c.get("warning_type") or ""),
        "signal_tier": vpf_tier_from_reason(reason),
        "from_card": True,
    }
    return out


def fusion_signals_from_cards(cards: dict[str, Any] | None) -> dict[str, dict[str, Any]] | None:
    """返回 {chan, momentum, vpf} 三席；cards 无效则 None（回退 classic）。"""
    if not isinstance(cards, dict) or not cards:
        return None
    chan_c = cards.get("chan") if isinstance(cards.get("chan"), dict) else {}
    mom_c = cards.get("momentum") if isinstance(cards.get("momentum"), dict) else {}
    vpf_c = cards.get("vpf") if isinstance(cards.get("vpf"), dict) else {}
    # 必须至少一席 raw_available=True，避免空卡 direction:0 假激活
    if not any(isinstance(x, dict) and x.get("raw_available") for x in (chan_c, mom_c, vpf_c)):
        return None
    return {
        "chan": chan_card_to_fusion_signal(chan_c),
        "momentum": momentum_card_to_fusion_signal(mom_c),
        "vpf": vpf_card_to_fusion_signal(vpf_c),
    }
