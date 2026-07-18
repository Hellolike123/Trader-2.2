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


def chan_card_to_fusion_signal(card: dict[str, Any] | None) -> dict[str, Any]:
    """缠论卡 → fusion 信号（近似 _chan_to_signal 的强度语义）。"""
    c = card if isinstance(card, dict) else {}
    d = _as_dir(c.get("direction"))
    t_short = str(c.get("type_short") or "")
    t_raw = str(c.get("type_raw") or "")
    blob = t_short + t_raw + str(c.get("summary_line") or "")

    conf = 0.35
    tier = SignalTier.NEUTRAL
    if "一买" in t_short or "一类买" in t_raw or "一类买" in blob:
        conf, tier = 0.8, SignalTier.CHAN_BUY_1
        d = 1
    elif "二买" in t_short or "二类买" in t_raw:
        conf, tier = 0.4, SignalTier.CHAN_BUY_2
        d = 1
    elif "三买" in t_short or "三类买" in t_raw:
        conf, tier = 0.4, SignalTier.CHAN_BUY_3
        d = 1
    elif "类二买" in t_short or "类二买" in t_raw:
        conf, tier = 0.35, SignalTier.CHAN_BUY_LIKE2
        d = 1
    elif "一卖" in t_short or "一类卖" in t_raw:
        conf, tier = 0.8, SignalTier.CHAN_SELL_1
        d = -1
    elif "二卖" in t_short or "二类卖" in t_raw:
        conf, tier = 0.5, SignalTier.CHAN_SELL_2
        d = -1
    elif "三卖" in t_short or "三类卖" in t_raw:
        conf, tier = 0.5, SignalTier.CHAN_SELL_3
        d = -1
    elif "底背驰" in blob:
        conf, tier = 0.5, SignalTier.CHAN_BOTTOM_DIVERGENCE
        d = 1
    elif "顶背驰" in blob:
        conf, tier = 0.5, SignalTier.CHAN_TOP_DIVERGENCE
        d = -1
    elif d != 0:
        conf = 0.35

    if c.get("same_level") is False:
        conf *= 0.65

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
        conf_f = float(conf) if conf is not None else 0.2
    except (TypeError, ValueError):
        conf_f = 0.2
    if not c.get("raw_available") and conf_f == 0:
        conf_f = 0.0
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
    try:
        conf_f = float(c.get("confidence") or 0.2)
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
    """返回 {chan, momentum, vpf} 三席；cards 无效则 None。"""
    if not isinstance(cards, dict) or not cards:
        return None
    chan_c = cards.get("chan") if isinstance(cards.get("chan"), dict) else {}
    mom_c = cards.get("momentum") if isinstance(cards.get("momentum"), dict) else {}
    vpf_c = cards.get("vpf") if isinstance(cards.get("vpf"), dict) else {}
    # 至少有一席 raw_available 或有方向信息
    if not any(
        (isinstance(x, dict) and (x.get("raw_available") or x.get("direction") is not None or x.get("summary_line")))
        for x in (chan_c, mom_c, vpf_c)
    ):
        return None
    return {
        "chan": chan_card_to_fusion_signal(chan_c),
        "momentum": momentum_card_to_fusion_signal(mom_c),
        "vpf": vpf_card_to_fusion_signal(vpf_c),
    }
