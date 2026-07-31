# -*- coding: utf-8 -*-
"""Classic fusion mappers（已 deprecated，仅 compare / 单测 / cards 兼容）。

生产三席语义以 analysis/fusion_card_signals.py 为准。
"""
from __future__ import annotations

from typing import Any

from trader_shared.safe_cast import safe_float  # noqa: F401 — kept for future mapper use
from trader_shared.signal_schema import SignalTier

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


def _chan_to_signal(chan_result: dict) -> dict:
    """将 chanlun_strategy() 的原始输出映射为统一信号。

    Deprecated for production：席位语义以 ``fusion_card_signals.chan_card_to_fusion_signal`` 为准。
    本函数仅供 ``compare`` 对账与旧测试。

    优先级: 卖点(按类型) > 一类买 > 顶背驰 > 类二买 > 二/三类买 > 底背驰 > trend_label
    （粘滞二/三类买不得压过顶背驰）

    缠论输出结构 (chanlun_strategy → run_all → levels["chanlun"]):
        {"chanlun": {"buy_points": [...], "sell_points": [...], "divergence": {...}, "trend_label": "..."}}
    也兼容扁平分析 dict。
    """
    try:
        from trader_shared.chan_core import unwrap_chan
        chan = unwrap_chan(chan_result) if isinstance(chan_result, dict) else {}
    except ImportError:  # pragma: no cover
        chan = chan_result.get("chanlun", {}) if isinstance(chan_result, dict) else {}
    if not isinstance(chan, dict):
        chan = {}

    buy_points = chan.get("buy_points", []) if isinstance(chan.get("buy_points"), list) else []
    sell_points = chan.get("sell_points", []) if isinstance(chan.get("sell_points"), list) else []
    divergence = chan.get("divergence", {}) if isinstance(chan.get("divergence"), dict) else {}
    trend_label = chan.get("trend_label", "数据不足")

    _SELL_RANK = {"一类卖": 0, "类二卖": 1, "类一卖": 2, "二类卖": 3, "三类卖": 4}
    _BUY_RANK = {"一类买": 0, "类二买": 1, "类一买": 2, "二类买": 3, "三类买": 4}
    _CHAN_CONF = {3: 0.8, 2: 0.55, 1: 0.35}

    def _best_point(points: list, rank_map: dict) -> dict | None:
        best = None
        best_r = 999
        for p in points:
            if not isinstance(p, dict):
                continue
            r = rank_map.get(p.get("type"), 999)
            if r < best_r:
                best, best_r = p, r
        return best

    def _point_conf(p: dict, default: float) -> float:
        try:
            c = int(p.get("confidence") or 0)
        except (TypeError, ValueError):
            c = 0
        base = _CHAN_CONF.get(c, default)
        # 区间套：小级别明确未确认时降权（报告已标 30m✗，fusion 不得仍满置信）
        if p.get("nesting_confirmed") is False:
            base *= 0.55
        elif p.get("lower_confirmed") is False:
            base *= 0.65
        return round(min(0.95, max(0.15, base)), 4)

    def _div_nesting_scale() -> float:
        """底/顶背驰的区间套确认：divergence 上的 *_lower_confirmed 字段。"""
        if divergence.get("bottom_divergence_lower_confirmed") is False:
            return 0.65
        if divergence.get("top_divergence_lower_confirmed") is False:
            return 0.65
        return 1.0

    # 1) 卖点：按类型真优先级（不依赖 list 顺序）
    best_sell = _best_point(sell_points, _SELL_RANK)
    if best_sell is not None:
        sp_type = best_sell.get("type", "")
        conf = _point_conf(best_sell, 0.5 if sp_type != "一类卖" else 0.8)
        reasons = {
            "一类卖": "缠论一类卖 (顶背驰)",
            "类一卖": "缠论类一卖 (柱弱确认·非面积背驰)",
            "类二卖": "缠论类二卖 (反抽偏弱)",
            "二类卖": "缠论二类卖 (高点降低)",
            "三类卖": "缠论三类卖 (跌破中枢)",
        }
        types = {
            "一类卖": "chan_sell_1",
            "类一卖": "chan_sell_soft1",
            "类二卖": "chan_sell_like2",
            "二类卖": "chan_sell_2",
            "三类卖": "chan_sell_3",
        }
        tiers = {
            "一类卖": SignalTier.CHAN_SELL_1,
            "类一卖": SignalTier.CHAN_SELL_SOFT1,
            "类二卖": SignalTier.CHAN_SELL_LIKE2,
            "二类卖": SignalTier.CHAN_SELL_2,
            "三类卖": SignalTier.CHAN_SELL_3,
        }
        if sp_type in reasons:
            if sp_type in ("类一卖", "类二卖"):
                conf = _point_conf(best_sell, 0.35)
            return {
                "direction": -1,
                "confidence": conf,
                "reason": reasons[sp_type],
                "raw_key": "chan",
                "signal_id": best_sell.get("signal_id"),
                "signal_type": types[sp_type],
                "signal_tier": tiers[sp_type],
            }

    best_buy = _best_point(buy_points, _BUY_RANK)

    # 2) 一类买优先于顶背驰
    if best_buy is not None and best_buy.get("type") == "一类买":
        return {
            "direction": 1,
            "confidence": _point_conf(best_buy, 0.8),
            "reason": "缠论一类买 (底背驰)",
            "raw_key": "chan",
            "signal_id": best_buy.get("signal_id"),
            "signal_type": "chan_buy_1",
            "signal_tier": SignalTier.CHAN_BUY_1,
        }

    # 3) 顶背驰优先于粘滞二/三类买
    if divergence.get("top_divergence"):
        return {"direction": -1, "confidence": round(0.5 * _div_nesting_scale(), 4),
                "reason": "缠论顶背驰", "raw_key": "chan",
                "signal_tier": SignalTier.CHAN_TOP_DIVERGENCE}

    # 3.4) 类一买：柱序列弱确认，不强多
    if best_buy is not None and best_buy.get("type") == "类一买":
        return {
            "direction": 1,
            "confidence": _point_conf(best_buy, 0.35),
            "reason": "缠论类一买 (柱弱确认·非面积背驰)",
            "raw_key": "chan",
            "signal_id": best_buy.get("signal_id"),
            "signal_type": "chan_buy_soft1",
            "signal_tier": SignalTier.CHAN_BUY_SOFT1,
        }

    # 3.5) 类二买：介于一类买与二类买之间的弱化信号
    if best_buy is not None and best_buy.get("type") == "类二买":
        return {
            "direction": 1,
            "confidence": _point_conf(best_buy, 0.35),
            "reason": "缠论类二买 (回踩偏弱)",
            "raw_key": "chan",
            "signal_id": best_buy.get("signal_id"),
            "signal_type": "chan_buy_like2",
            "signal_tier": SignalTier.CHAN_BUY_LIKE2,
        }

    # 4) 二/三类买
    if best_buy is not None and best_buy.get("type") in ("二类买", "三类买"):
        bp_type = best_buy.get("type")
        return {
            "direction": 1,
            "confidence": _point_conf(best_buy, 0.4),
            "reason": "缠论二类买 (低点抬高)" if bp_type == "二类买" else "缠论三类买 (突破中枢)",
            "raw_key": "chan",
            "signal_id": best_buy.get("signal_id"),
            "signal_type": "chan_buy_2" if bp_type == "二类买" else "chan_buy_3",
            "signal_tier": SignalTier.CHAN_BUY_2 if bp_type == "二类买" else SignalTier.CHAN_BUY_3,
        }

    # 5) 底背驰
    if divergence.get("bottom_divergence"):
        return {"direction": 1, "confidence": round(0.5 * _div_nesting_scale(), 4),
                "reason": "缠论底背驰", "raw_key": "chan",
                "signal_tier": SignalTier.CHAN_BOTTOM_DIVERGENCE}

    # 6) 趋势
    structure_type = chan.get("structure_type", "")
    _st_suffix = f"({structure_type})" if structure_type else ""
    if isinstance(trend_label, str):
        if "拉升段" in trend_label:
            return {"direction": 1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}{_st_suffix}", "raw_key": "chan",
                    "signal_tier": SignalTier.CHAN_TREND_UP}
        if "回调段" in trend_label:
            return {"direction": -1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}{_st_suffix}", "raw_key": "chan",
                    "signal_tier": SignalTier.CHAN_TREND_DOWN}

    return {"direction": 0, "confidence": 0.3,
            "reason": "缠论无明确信号", "raw_key": "chan",
            "signal_tier": SignalTier.NEUTRAL}


def _momentum_to_signal(momentum_result: dict) -> dict:
    """compare / 旧测试兼容：委托 cards 侧 ``momentum_raw_to_fusion_signal``。"""
    from trader_shared.analysis.fusion_card_signals import momentum_raw_to_fusion_signal

    out = momentum_raw_to_fusion_signal(momentum_result if isinstance(momentum_result, dict) else {})
    # classic 调用方不要求 from_card 标记
    out = dict(out)
    out.pop("from_card", None)
    return out



def _wyckoff_to_signal(wyckoff_result: dict) -> dict:
    """将 wyckoff_analysis() 的原始输出映射为统一信号。

    ⚠️ 兼容/测试用：**短线 fusion 已不调用本函数**（第三席为 VPF，
    ``merge_decisions`` 不再对 wyckoff 加权）。保留供单测与历史脚本。
    生产消费面：中线 ``format_wyckoff_oneline`` + ``calculate_wyckoff_score``（池/复盘）。

    威科夫输出结构 (wyckoff_strategy → {"wyckoff": {...}}):
        {"wyckoff": {"spring_signal": True, "bullish_volume_divergence": False, ...}}

    信号优先级（强→弱）：
      Spring + bullish_div (0.75) > Spring (0.7) > SOS (0.7) >
      Upthrust (0.6) > BC (0.55) > SOW (0.5) >
      AR (0.6) > ST (0.5) > LPS (0.5) >
      背离 (0.5) > 无信号 (0.2)

    说明：BC/SOW 排在 AR 之前，使「BC-15+AR+10」净偏空与打分方向一致。
    ar / sos / st / lps / bc / sow 消费原始 *_reason 字符串。
    孤立/过早信号（spring_premature / upthrust_premature）降置信或跳过抬分语义。
    """
    wyk = wyckoff_result.get("wyckoff", {}) if isinstance(wyckoff_result, dict) else {}
    if not isinstance(wyk, dict):
        wyk = {}

    spring = wyk.get("spring_signal") and not wyk.get("spring_premature")
    bullish_div = wyk.get("bullish_volume_divergence")
    bearish_div = wyk.get("bearish_volume_divergence")
    upthrust = wyk.get("upthrust_signal") and not wyk.get("upthrust_premature")

    # 经典 + 看空信号
    ar = wyk.get("ar_signal")
    sos = wyk.get("sos_signal")
    st = wyk.get("st_signal")
    lps = wyk.get("lps_signal")
    bc = wyk.get("bc_signal")
    sow = wyk.get("sow_signal")

    # 从原始结果取 reason 字符串，保持可追溯
    def _reason(base_key: str, fallback: str) -> str:
        r = wyk.get(f"{base_key}_reason", "")
        if not r:
            return fallback
        return r

    # ── Spring 系列 (最强做多信号) ──
    if spring:
        # 高量弹簧可能是真破位：confidence 从 0.7 降到约 0.45
        high_vol_spring = wyk.get("spring_vol_class") == "high_vol_warning"
        if high_vol_spring:
            confidence = 0.5 if bullish_div else 0.45
        else:
            confidence = 0.75 if bullish_div else 0.7
        return {
            "direction": 1,
            "confidence": confidence,
            "reason": f"威科夫弹簧 ({_reason('spring', '支撑测试有效')})",
            "raw_key": "wyckoff",
        }

    # ── SOS: Sign of Strength (强势确认) ──
    if sos:
        return {
            "direction": 1,
            "confidence": 0.7,
            "reason": f"威科夫 {(_reason('sos', '强势突破'))}",
            "raw_key": "wyckoff",
        }

    # ── Upthrust: 上冲回落 (看空) ──
    if upthrust:
        return {
            "direction": -1,
            "confidence": 0.6,
            "reason": f"威科夫 {_reason('upthrust', '上冲回落')}",
            "raw_key": "wyckoff",
        }

    # ── BC: Buying Climax 购买高潮 (看空，P1 接入 fusion) ──
    if bc:
        return {
            "direction": -1,
            "confidence": 0.55,
            "reason": f"威科夫 {_reason('bc', '购买高潮')}",
            "raw_key": "wyckoff",
        }

    # ── SOW: Sign of Weakness 弱势 (看空) ──
    if sow:
        return {
            "direction": -1,
            "confidence": 0.5,
            "reason": f"威科夫 {_reason('sow', '弱势信号')}",
            "raw_key": "wyckoff",
        }

    # ── AR: Automatic Rally (SC 后自动反弹；⑥B 不再绑 BC) ──
    if ar:
        return {
            "direction": 1,
            "confidence": 0.6,
            "reason": f"威科夫 {_reason('ar', 'SC后自动反弹')}",
            "raw_key": "wyckoff",
        }

    # ── ST: Secondary Test (Spring 后二次测试) ──
    if st:
        return {
            "direction": 1,
            "confidence": 0.5,
            "reason": f"威科夫 {_reason('st', '二次测试确认')}",
            "raw_key": "wyckoff",
        }

    # ── LPS: Last Point of Support (最后支撑点) ──
    if lps:
        return {
            "direction": 1,
            "confidence": 0.5,
            "reason": f"威科夫 {_reason('lps', '最后支撑确认')}",
            "raw_key": "wyckoff",
        }

    # ── 背离 (同时出现以看涨为准) ──
    if bullish_div and not bearish_div:
        return {
            "direction": 1, "confidence": 0.5,
            "reason": "威科夫看多量价背离", "raw_key": "wyckoff"}
    if bearish_div and not bullish_div:
        return {
            "direction": -1, "confidence": 0.5,
            "reason": "威科夫看空量价背离", "raw_key": "wyckoff"}

    return {"direction": 0, "confidence": 0.2,
            "reason": "威科夫无明确信号", "raw_key": "wyckoff"}

