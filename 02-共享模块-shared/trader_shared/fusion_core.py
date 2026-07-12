#!/usr/bin/env python3
"""决策融合层 — 信号标准化、加权汇总、冲突检测。

零修改现有代码。所有信号函数按统一接口运行，融合层消费其输出。

架构定位：
    现有 pipeline: 缠论/动量/威科夫 → status_for() → action_for()
    融合层在它们之上叠加:
                      ┌─────────────────────────────┐
    缠论结果 ────────┐                            │
    动量结果 ─────┐  │  merge_decisions()          │ → {action, confidence, signals_detail}
    威科夫结果 ─┘  │  │  + regime权重 + 冲突检测   │
                   │  └─────────────────────────────┘

设计文档: docs/designs/decision-fusion-layer.md

调用方式:
    from fusion_core import merge_decisions, log_only
    from trader_shared.scripts.market_env import get_env_for_skill

    env = get_env_for_skill("trader")
    result = merge_decisions(
        chan_result=chan_result,
        momentum_result=momentum_result,
        wyckoff_result=wyckoff_result,
        regime=env.get("level", "正常"),
    )
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from trader_shared.safe_cast import safe_float
from trader_shared._logging import get_logger
from trader_shared.interfaces import DataFetcher
from trader_shared.fetchers import get_fetcher

_logger = get_logger(__name__)

# ── [2.3] 贝叶斯融合（可选导入，无则降级） ───────────────────────────────────────────
try:
    from trader_shared.bayesian_fusion import is_enabled as _bayesian_enabled, bayesian_merge
    _BAYESIAN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BAYESIAN_AVAILABLE = False
    def _bayesian_enabled(): return False
    def bayesian_merge(chan, mom, wyk, regime_state="range"): return {}

# ── 安全模式: 环境变量控制 (FUSION_LOG_ONLY=true = 只日志, 不改决策行为)
# 默认关闭日志模式, 融合层正式生效。调试时可设置 FUSION_LOG_ONLY=true

FUSION_LOG_ONLY = os.environ.get("FUSION_LOG_ONLY", "false").lower() in ("true", "1", "yes")



def _log_fusion(result: dict) -> None:
    """打印 FUSION 日志，方便观察融合结果。
    
    只捕获 JSON 序列化错误，不吞逻辑错误。
    """
    try:
        log_data = {
            "action": result["action"],
            "weighted_score": result["weighted_score"],
            "disagreement": result["disagreement"],
            "regime": result["regime"],
            "main_force_env": result.get("main_force_env", "unknown"),
            "signals": {k: v["direction"] for k, v in result["signals_detail"].items()},
        }
        import sys
        print(f"FUSION: {json.dumps(log_data, ensure_ascii=False)}", file=sys.stderr)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        _logger.debug("Fusion log serialization failed: %s", exc)


def _chan_to_signal(chan_result: dict) -> dict:
    """将 chanlun_strategy() 的原始输出映射为统一信号。

    优先级: 卖点(按类型) > 一类买 > 顶背驰 > 二/三类买 > 底背驰 > trend_label
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

    _SELL_RANK = {"一类卖": 0, "二类卖": 1, "三类卖": 2}
    _BUY_RANK = {"一类买": 0, "二类买": 1, "三类买": 2}
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
        return _CHAN_CONF.get(c, default)

    # 1) 卖点：按类型真优先级（不依赖 list 顺序）
    best_sell = _best_point(sell_points, _SELL_RANK)
    if best_sell is not None:
        sp_type = best_sell.get("type", "")
        conf = _point_conf(best_sell, 0.5 if sp_type != "一类卖" else 0.8)
        reasons = {
            "一类卖": "缠论一类卖 (顶背驰)",
            "二类卖": "缠论二类卖 (高点降低)",
            "三类卖": "缠论三类卖 (跌破中枢)",
        }
        types = {"一类卖": "chan_sell_1", "二类卖": "chan_sell_2", "三类卖": "chan_sell_3"}
        if sp_type in reasons:
            return {
                "direction": -1,
                "confidence": conf,
                "reason": reasons[sp_type],
                "raw_key": "chan",
                "signal_id": best_sell.get("signal_id"),
                "signal_type": types[sp_type],
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
        }

    # 3) 顶背驰优先于粘滞二/三类买
    if divergence.get("top_divergence"):
        return {"direction": -1, "confidence": 0.5,
                "reason": "缠论顶背驰", "raw_key": "chan"}

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
        }

    # 5) 底背驰
    if divergence.get("bottom_divergence"):
        return {"direction": 1, "confidence": 0.5,
                "reason": "缠论底背驰", "raw_key": "chan"}

    # 6) 趋势
    structure_type = chan.get("structure_type", "")
    _st_suffix = f"({structure_type})" if structure_type else ""
    if isinstance(trend_label, str):
        if "拉升段" in trend_label:
            return {"direction": 1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}{_st_suffix}", "raw_key": "chan"}
        if "回调段" in trend_label:
            return {"direction": -1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}{_st_suffix}", "raw_key": "chan"}

    return {"direction": 0, "confidence": 0.3,
            "reason": "缠论无明确信号", "raw_key": "chan"}


def _momentum_to_signal(momentum_result: dict) -> dict:
    """将 assess_momentum() 的原始输出映射为统一信号。

    动量输出结构 (momentum_strategy → run_all → levels["momentum"]):
        {"momentum": {"score": 72, "direction": "bullish", "signals": [...]}}

    综合 direction (bullish/neutral/bearish) + score (0-100) → 统一信号。
    direction 决定方向，score 决定置信度幅度。
    """
    mom = momentum_result.get("momentum", {}) if isinstance(momentum_result, dict) else {}
    if not isinstance(mom, dict):
        mom = {}

    score = mom.get("score", 50)
    direction_str = mom.get("direction", "neutral")
    signals_list = mom.get("signals", [])

    # direction 字符串决定方向 (保持原始判断)
    dir_map = {"bullish": 1, "bearish": -1, "neutral": 0}
    direction = dir_map.get(direction_str, 0)

    # score 决定置信度
    confidence = _score_to_confidence(score)

    # direction 和 score 冲突时降低置信度
    # 如 direction="bullish" 但分数很低 → 有方向感但量化分数不支持 → 保守处理
    if direction != 0 and score <= 45:
        confidence = min(confidence, 0.4)

    reason = "、".join(signals_list[-2:]) if signals_list else "动量中性"
    return {
        "direction": direction,
        "confidence": confidence,
        "reason": reason,
        "raw_key": "momentum",
        "strength": mom.get("strength", ""),
    }


_confidence_cache: dict[str, float] | None = None


def _load_confidence_params() -> dict[str, float]:
    """加载置信度映射参数。优先从 calibrated_params.json 读取，fallback 到 config 默认值。带模块级缓存。"""
    global _confidence_cache
    if _confidence_cache is not None:
        return _confidence_cache

    from trader_shared.config import CONFIDENCE_MAPPING_DEFAULTS
    try:
        from trader_shared.self_calibration import load_calibrated_params
        cal = load_calibrated_params()
        if cal and "confidence_mapping" in cal:
            merged = dict(CONFIDENCE_MAPPING_DEFAULTS)
            merged.update(cal["confidence_mapping"])
            _confidence_cache = merged
            return merged
    except Exception:
        pass
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


def _wyckoff_to_signal(wyckoff_result: dict) -> dict:
    """将 wyckoff_analysis() 的原始输出映射为统一信号。

    威科夫输出结构 (wyckoff_strategy → run_all → levels["wyckoff"]):
        {"wyckoff": {"spring_signal": True, "bullish_volume_divergence": False, ...}}

    信号优先级（强→弱）：
      Spring + bullish_div (0.75) > Spring (0.7) > SOS (0.7) >
      Upthrust (0.6) > BC (0.55) > SOW (0.5) >
      AR (0.6) > ST (0.5) > LPS (0.5) >
      背离 (0.5) > 无信号 (0.2)

    说明：BC/SOW 排在 AR 之前，使「BC-15+AR+10」净偏空与 fusion 方向一致。
    ar / sos / st / lps / bc / sow 消费原始 *_reason 字符串。
    """
    wyk = wyckoff_result.get("wyckoff", {}) if isinstance(wyckoff_result, dict) else {}
    if not isinstance(wyk, dict):
        wyk = {}

    spring = wyk.get("spring_signal")
    bullish_div = wyk.get("bullish_volume_divergence")
    bearish_div = wyk.get("bearish_volume_divergence")
    upthrust = wyk.get("upthrust_signal")

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

    # ── AR: Automatic Rally (BC 后自动反弹) ──
    # 仅当 BC 未单独占主导时到达此处（BC 已在上方优先）
    if ar:
        return {
            "direction": 1,
            "confidence": 0.6,
            "reason": f"威科夫 {_reason('ar', '自动反弹')}",
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


def wyckoff_score_to_direction(score: int) -> dict:
    """将 WyckoffScore.score (0-100) 映射为统一信号。

    作为 _wyckoff_to_signal 的替代方案，直接从分数推导方向：
    - score >= 65: 看多, confidence = score/100
    - score <= 35: 看空, confidence = (100-score)/100
    - 35 < score < 65: 中性, confidence = 0.3

    自动受益：calculate_wyckoff_score() 新增 AR/SOS/ST/LPS 信号后，
    score 范围自动扩大，此函数无需改动即可反映新分数。
    当前 _wyckoff_to_signal 是主线，此函数保留为 score-based 备选。
    """
    if score >= 65:
        return {
            "direction": 1,
            "confidence": min(score / 100, 0.95),
            "reason": f"威科夫看多（{score}/100）",
            "raw_key": "wyckoff",
        }
    elif score <= 35:
        return {
            "direction": -1,
            "confidence": min((100 - score) / 100, 0.95),
            "reason": f"威科夫看空（{score}/100）",
            "raw_key": "wyckoff",
        }
    else:
        return {
            "direction": 0,
            "confidence": 0.3,
            "reason": f"威科夫中性（{score}/100）",
            "raw_key": "wyckoff",
        }


_MAIN_FORCE_WEIGHT_ADJUSTMENTS: dict[str, dict[str, float]] = {
    # 第三席为 vpf（价量资金）；旧 key wyckoff 不再使用
    "accumulation": {"chan": 0.0, "vpf": 0.10, "momentum": -0.10},
    "testing":      {"chan": 0.0, "vpf": 0.0,  "momentum": 0.0},
    "markup":       {"chan": -0.05, "vpf": 0.0,  "momentum": 0.10},
    "distribution": {"chan": -0.10, "vpf": 0.10, "momentum": -0.05},
    "markdown":     {"chan": -0.15, "vpf": -0.10, "momentum": -0.10},
    "unknown":      {"chan": 0.0, "vpf": 0.0, "momentum": 0.0},
}


def _apply_main_force_weights(weights: dict[str, float], main_force_env: str) -> dict[str, float]:
    """根据主力行为阶段修正三路信号权重，修正后归一化。"""
    adj = _MAIN_FORCE_WEIGHT_ADJUSTMENTS.get(main_force_env, {})
    if not adj:
        return weights
    adjusted = {}
    for k in weights:
        adjusted[k] = max(0.0, weights[k] + adj.get(k, 0.0))
    total = sum(adjusted.values())
    if total > 0:
        # 先归一化，然后将最后一个权重设为 1.0 - sum(其他权重) 确保精确和为1.0
        keys = list(adjusted.keys())
        for k in keys[:-1]:
            adjusted[k] = round(adjusted[k] / total, 4)
        adjusted[keys[-1]] = round(1.0 - sum(adjusted[k] for k in keys[:-1]), 4)
    return adjusted


def merge_decisions(
    chan_result: dict,
    momentum_result: dict,
    wyckoff_result: dict | None = None,
    regime: str = "正常",
    current_price: float = 0.0,
    bars: list = None,
    hmm_regime: str = "range",
    extend_fundamental: dict | None = None,
    extend_sentiment: dict | None = None,
    main_force_env: str | None = None,
    data_status: str = "full",
    fetcher: DataFetcher | None = None,  # DI: 可注入数据源
    volume_warning: dict | None = None,  # 量价背离警告 (可选)
    fund_flow_data: dict | None = None,  # P1-2: 资金流向特征 (可选)
    current_change_pct: float = 0.0,     # Phase 2: 个股今日涨跌幅（用于板块相对强弱）
    extend_sector: dict | None = None,   # Phase 2: 行业板块数据（A2）
    extend_concept: dict | None = None,  # Phase 2: 概念板块数据（B7）
    extend_northbound: dict | None = None,  # Phase 2: 北向资金（A8，预留接入）
    extend_margin: dict | None = None,      # Phase 2: 融资融券（预留接入）
    vpf_result: dict | None = None,         # 价量资金专家（优先）；缺省由 volume/fund 合成
) -> dict:
    """决策融合层核心函数。

    短线三席：缠论 + 动能 + 价量资金(vpf)。
    wyckoff_result 仅兼容旧调用签名，**不再参与短线加权**（威科夫留中线周线）。

    Args:
        chan_result:     chanlun_strategy() 的返回值 (levels["chanlun"])
        momentum_result: momentum_strategy() 的返回值 (levels["momentum"])
        wyckoff_result:  已弃用（短线不计分）；保留位置参数兼容旧测试/调用
        regime:          market_env assess() 返回的 level 字段
        volume_warning / fund_flow_data / vpf_result: 第三席 VPF 输入

    Returns:
        含 signals_detail.chan / momentum / vpf；weights_used 键为 chan/momentum/vpf
    """
    from trader_shared.fusion_regime import get_regime_weights, score_to_action, compute_confidence

    if fetcher is None:
        fetcher = get_fetcher()

    # 1. 信号标准化 (只读, 不修改输入)
    try:
        chan_signal = _chan_to_signal(chan_result)
    except (TypeError, KeyError) as exc:
        _logger.warning("Chanlun signal normalization failed: %s", exc)
        chan_signal = {"direction": 0, "confidence": 0.0,
                       "reason": "缠论标准化异常", "raw_key": "chan"}

    try:
        momentum_signal = _momentum_to_signal(momentum_result)
    except (TypeError, KeyError) as exc:
        _logger.warning("Momentum signal normalization failed: %s", exc)
        momentum_signal = {"direction": 0, "confidence": 0.0,
                           "reason": "动量标准化异常", "raw_key": "momentum"}

    # 第三席：价量资金（VPF）；不再用日线威科夫投票
    try:
        from trader_shared.vpf_core import build_vpf_signal, vpf_to_fusion_signal
        if isinstance(vpf_result, dict) and vpf_result.get("raw_key") == "vpf":
            vpf_signal = vpf_to_fusion_signal(vpf_result)
        else:
            # 计算近20日均成交额（万元），用于资金强度比归一化
            _avg_turnover_wan = None
            if bars and len(bars) >= 10:
                _amounts = []
                for _b in bars[-20:]:
                    _a = _b.get("amount") if isinstance(_b, dict) else getattr(_b, "amount", None)
                    if _a is not None:
                        try:
                            _amounts.append(float(str(_a).replace(",", "")))
                        except (TypeError, ValueError):
                            pass
                if _amounts:
                    _avg_turnover_wan = sum(_amounts) / len(_amounts) / 10000.0  # 元→万元

            vpf_signal = build_vpf_signal(
                volume_warning if isinstance(volume_warning, dict) else None,
                fund_flow_data if isinstance(fund_flow_data, dict) else None,
                bars=bars,
                avg_daily_turnover_wan=_avg_turnover_wan,
            )
    except Exception as exc:
        _logger.warning("VPF signal build failed: %s", exc)
        vpf_signal = {
            "direction": 0,
            "confidence": 0.2,
            "reason": "价量资金标准化异常",
            "raw_key": "vpf",
            "fund_quality": "missing",
        }

    # 2. 场景优先级过滤器 (Scenario Priority Filter)
    # 计算20日高低区间位置
    pos_pct = None
    if bars and len(bars) > 0 and current_price > 0:
        recent20 = bars[-20:]
        lows = []
        highs = []
        for b in recent20:
            if isinstance(b, dict):
                l_val = b.get("low")
                h_val = b.get("high")
            else:
                l_val = getattr(b, "low", None)
                h_val = getattr(b, "high", None)
            try:
                if l_val is not None:
                    lows.append(float(str(l_val).replace(",", "")))
                if h_val is not None:
                    highs.append(float(str(h_val).replace(",", "")))
            except (ValueError, TypeError):
                continue
        if lows and highs:
            min_l = min(lows)
            max_h = max(highs)
            if max_h > min_l:
                pos_pct = (current_price - min_l) / (max_h - min_l)

    chan_reason = chan_signal.get("reason", "")
    strong_bullish_chan = chan_signal.get("direction") == 1 and any(
        kw in chan_reason for kw in ("一类买", "二类买", "三类买", "1类买", "2类买", "3类买", "底背驰", "1st buy", "2nd buy", "3rd buy", "bottom divergence")
    )
    strong_bearish_chan = chan_signal.get("direction") == -1 and any(
        kw in chan_reason for kw in ("一类卖", "1类卖", "1st sell", "顶背驰", "top_divergence")
    )

    vpf_reason = str(vpf_signal.get("reason") or "")
    strong_bullish_vpf = vpf_signal.get("direction") == 1 and float(vpf_signal.get("confidence") or 0) >= 0.45
    strong_bearish_vpf = vpf_signal.get("direction") == -1 and (
        float(vpf_signal.get("confidence") or 0) >= 0.5
        or any(k in vpf_reason for k in ("天量", "滞涨", "连", "流出"))
    )

    mom_score = 50
    if isinstance(momentum_result, dict):
        # P2 Fix: momentum 键可能值为 None，直接 .get("score") 会抛 AttributeError
        mom = momentum_result.get("momentum") or {}
        mom_score = mom.get("score", 50) if isinstance(mom, dict) else 50

    # Fix 2: 有强多信号时的低位判断从 pos_pct <= 0.5 收紧到 <= 0.35
    # 50% 中轴并非低位，中轴附近的强多信号不应触发底部权重偏置
    # P2 Fix: bars < 20 时放宽阈值到 0.5，避免数据不足时误判
    _pct_threshold = 0.3 if (bars and len(bars) >= 20) else 0.5
    _pct_threshold_strong = 0.35 if (bars and len(bars) >= 20) else 0.5
    is_breakout_or_bottom = (pos_pct is not None and pos_pct <= _pct_threshold) or (
        (strong_bullish_chan or strong_bullish_vpf) and pos_pct is not None and pos_pct <= _pct_threshold_strong
    )

    # 真正的高位超买（价格在区间上沿 + 动量极强）：动量权重最高，
    # 因为高位要看动量是否衰竭来决定去留。
    is_genuine_climax = pos_pct is not None and pos_pct >= 0.7 and mom_score >= 80
    # 仅有强看空信号（顶背驰 / 价量资金偏空），未必处于高位：这是结构发出看空警告，
    # 应尊重结构信号而非给动量最高权重去否决它。
    is_bearish_structure_warning = (strong_bearish_chan or strong_bearish_vpf) and not is_genuine_climax

    if is_breakout_or_bottom:
        weights = {"chan": 0.44, "momentum": 0.20, "vpf": 0.36}
    elif is_genuine_climax:
        # 高位 + 强动量：动量权重最高（56%），高位看动量衰竭
        weights = {"chan": 0.20, "momentum": 0.56, "vpf": 0.24}
    elif is_bearish_structure_warning:
        # 结构/价量看空警告：尊重结构与 VPF，权重高于动量
        weights = {"chan": 0.44, "momentum": 0.20, "vpf": 0.36}
    else:
        regime_weights = get_regime_weights(regime)
        if regime == "很差":
            weights = regime_weights
        else:
            weights = regime_weights

    # 2.5 主力行为权重修正
    if main_force_env and main_force_env != "unknown":
        weights = _apply_main_force_weights(weights, main_force_env)

    # 3. 分歧检测与置信优先级冲突消解
    directions = [chan_signal["direction"],
                  momentum_signal["direction"],
                  vpf_signal["direction"]]
    disagreement = max(directions) - min(directions)
    disagreement_for_action = disagreement

    if disagreement > 1:
        if strong_bullish_chan or strong_bullish_vpf:
            if momentum_signal["direction"] == -1:
                # 衰减动量权重而非归零方向：confidence 是连续值可真正衰减，
                # direction 是离散值 (±1)，对它做 *0.3 会被 int() 抹成 0，
                # 导致冲突的动量信号彻底消失而非减弱。修正后保留方向、削弱权重。
                momentum_signal["confidence"] *= 0.3
            disagreement_for_action = 0
        elif strong_bearish_chan or strong_bearish_vpf:
            if momentum_signal["direction"] == 1:
                momentum_signal["confidence"] *= 0.3
            disagreement_for_action = 0

    # 4. 加权计算 (使用可能消解后的方向及权重)
    _w_vpf = weights.get("vpf", weights.get("wyckoff", 0.25))
    weighted_score = (
        chan_signal["direction"] * chan_signal["confidence"] * weights["chan"] +
        momentum_signal["direction"] * momentum_signal["confidence"] * weights["momentum"] +
        vpf_signal["direction"] * vpf_signal["confidence"] * _w_vpf
    )

    # 5. 决策映射
    # 先做数据断层降级，再映射 action（避免截断前的高分触发"半仓试"、
    # 但截断后 weighted_score=0.0，导致 action 与显示不一致）
    _action_score = weighted_score
    if data_status in ("partial", "degraded", "failed"):
        _action_score = min(weighted_score, 0.0)
    action = score_to_action(_action_score, disagreement_for_action, regime)

    # 5b. 高位修正：如果价格已在 20 日高位（pos_pct >= 0.8），
    # 且动作是"观望"类（隐含"等一下就有买点"），改为"高位观望"
    # 避免误导用户"回调就有机会"——实际可能再涨 50%
    if pos_pct is not None and pos_pct >= 0.8:
        # 包含所有"观望/等待"类 action（截断后可能产出"持股观望"）
        if action in {"等转强", "等转强观察", "回调观望", "观望 (信号冲突)", "持股观望", "观望"}:
            action = "高位观望"

    # 6. 综合置信度
    confidence = compute_confidence(weighted_score, disagreement_for_action, weights)

    # #7 修复：data_status=partial 时 weighted_score 也截断，避免
    # report 里 weighted_score 显示正数但 action 显示"持股观望"的矛盾。
    # 截断前的原始值保留为 raw_weighted_score，供调试用。
    _raw_weighted_score = weighted_score
    if data_status in ("partial", "degraded", "failed"):
        weighted_score = _action_score  # 已被截断到 min(weighted_score, 0.0)

    # ── [2.3新增] 贝叶斯概率决策融合 ──
    bayesian_used = False
    bayesian_info = {}
    if _BAYESIAN_AVAILABLE and _bayesian_enabled():
        try:
            bayesian_res = bayesian_merge(
                chan_signal=chan_signal,
                momentum_signal=momentum_signal,
                wyckoff_signal=vpf_signal,  # 第三席：VPF 复用 bayesian 槽位
                regime_state=hmm_regime
            )
            if bayesian_res and "action" in bayesian_res:
                action = bayesian_res["action"]
                confidence = bayesian_res["confidence"]
                weighted_score = bayesian_res["action_score"]
                bayesian_used = True
                bayesian_info = bayesian_res
        except Exception as exc:
            _logger.warning("Bayesian fusion failed, falling back: %s", exc)

    # ── [2.4新增] 量价背离警告 ──
    # 天量天价: 强烈看空信号，覆盖 action
    # 放量滞涨: 降低看多置信度
    if volume_warning and isinstance(volume_warning, dict):
        vw_type = volume_warning.get("warning_type", "none")
        vw_signal = volume_warning.get("signal", 0)
        vw_conf = volume_warning.get("confidence", 0.0)

        if vw_type == "climactic" and vw_signal == -1:
            # 天量天价: 强制改为卖出类 action
            positive_actions = {"半仓试 (多方主导)", "半仓试 (多方主导但有分歧)",
                                "增持", "等转强", "等转强观察", "回调观望",
                                "持股观望", "高位观望"}
            if action in positive_actions:
                action = "天量天价，减仓观望"
                confidence = min(confidence, 0.4)
        elif vw_type == "stagnation" and vw_signal == -1:
            # 放量滞涨: 降低看多置信度
            if weighted_score > 0:
                confidence *= (1 - vw_conf * 0.3)
                confidence = max(confidence, 0.2)

    # ── [P1-2] 大单连续流出一票否决 ──
    # 如果近 N 日主力连续净流出超阈值，强制覆盖 action 为减仓观望
    has_fund_flow_outflow_veto = False
    fund_flow_outflow_days = 0
    try:
        from trader_shared.config import (
            FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS,
            FUND_FLOW_OUTFLOW_VETO_WAN,
        )
        if fund_flow_data and isinstance(fund_flow_data, dict):
            consecutive_outflow = fund_flow_data.get("consecutive_outflow_days") or 0  # fix: None guard
            # 从近 N 日每日流向列表计算实际连续流出天数和均值
            daily_flow_5d = fund_flow_data.get("daily_flow_5d") or []  # fix: None guard
            cum_flow_5d = fund_flow_data.get("cum_flow_5d_wan") or 0  # fix: None guard
            if consecutive_outflow >= FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS:
                # 检查近 N 日每日流出是否均超阈值（防止单日巨额拉高均值）
                recent_n = daily_flow_5d[-FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS:] if daily_flow_5d else []
                # fix: require enough samples before applying all() veto
                if len(recent_n) >= FUND_FLOW_CONSECUTIVE_OUTFLOW_DAYS and all(
                    isinstance(v, (int, float)) and v < 0 and abs(v) > FUND_FLOW_OUTFLOW_VETO_WAN  # fix: contract ">" (strict)
                    for v in recent_n
                ):
                    has_fund_flow_outflow_veto = True
                    fund_flow_outflow_days = consecutive_outflow
    except ImportError:
        pass  # config 不可用时静默跳过
    except (TypeError, KeyError) as exc:
        _logger.debug("Fund flow outflow veto check failed: %s", exc)

    if has_fund_flow_outflow_veto:
        positive_actions = {"半仓试 (多方主导)", "半仓试 (多方主导但有分歧)",
                            "增持", "等转强", "等转强观察", "回调观望",
                            "持股观望", "高位观望"}
        if action in positive_actions:
            action = "资金流出，减仓观望"
            confidence = min(confidence, 0.35)

    # ── [2.3扩展] 股东户数筹码集中验证 ──
    try:
        sh_trend = (extend_fundamental or {}).get("shareholder", {})
        # Fix 6: 加 weighted_score > 0.2 门槛，避免弱信号时盲目给置信加成
        # 筹码集中可能是锁仓也可能是庄股，仅在多方信号有一定质量时才加持
        if sh_trend.get("status") == "筹码集中" and weighted_score > 0.2:
            confidence *= 1.15
            confidence = min(confidence, 1.0)
    except (TypeError, AttributeError) as exc:
        _logger.debug("Shareholder trend check failed: %s", exc)

    # ── [2.3扩展] 限售解禁一票否决风控 ──
    has_risk_unlock = False
    days_to_unlock = None
    unlock_ratio = None
    try:
        unlocks = (extend_sentiment or {}).get("unlocks", [])
        if unlocks:
            from datetime import datetime
            today_dt = datetime.now().date()
            for u in unlocks:
                u_date_str = u.get("date", "")
                try:
                    u_dt = datetime.strptime(u_date_str, "%Y-%m-%d").date()
                    days = (u_dt - today_dt).days
                    ratio = safe_float(u, "ratio")
                    if 0 <= days <= 15 and ratio >= 5.0:
                        has_risk_unlock = True
                        days_to_unlock = days
                        unlock_ratio = ratio
                        break
                except (ValueError, TypeError):
                    continue
    except (TypeError, AttributeError) as exc:
        _logger.debug("Unlock risk check failed: %s", exc)

    if has_risk_unlock:
        positive_actions = {"半仓试 (多方主导)", "半仓试 (多方主导但有分歧)", "增持", "等转强"}
        if action in positive_actions:
            action = "空仓 (限售解禁风险)"
            confidence = 0.3
            weighted_score = -0.5

    # ── [Phase 2] 板块相对强弱 / 概念热点 接入评分 ──
    # 仅在板块/概念数据 status == "正常" 时接入，缺失时退化为原行为。
    try:
        if extend_sector and isinstance(extend_sector, dict) and extend_sector.get("status") == "正常":
            sec_chg = safe_float(extend_sector, "sector_change_pct")
            # A3: 个股涨 + 板块跌 → 个股相对板块走强 → 置信度 +10%（封顶 1.0）
            if current_change_pct > 0 and sec_chg < 0:
                confidence *= 1.10
            # A4: 个股跌 + 板块涨 → 个股相对板块走弱 → 若加权分>0 则减分 -0.1
            elif current_change_pct < 0 and sec_chg > 0:
                if weighted_score > 0:
                    confidence = max(0.0, confidence - 0.1)
            # A5: 板块排名前 10% → 主线板块 → 置信度 +5%
            sec_rank = safe_float(extend_sector, "sector_rank")
            sec_total = safe_float(extend_sector, "sector_total")
            if sec_total > 0 and sec_rank > 0 and (sec_rank / sec_total) <= 0.1:
                confidence *= 1.05
            confidence = min(confidence, 1.0)
    except (TypeError, AttributeError, ValueError) as exc:
        _logger.debug("Sector relative strength check failed: %s", exc)

    try:
        if extend_concept and isinstance(extend_concept, dict) and extend_concept.get("status") == "正常":
            concept_list = extend_concept.get("concept_list") or []
            # B7: 个股命中概念（热点）板块 → 置信度 +5%
            if concept_list:
                confidence *= 1.05
                confidence = min(confidence, 1.0)
    except (TypeError, AttributeError) as exc:
        _logger.debug("Concept hotspot check failed: %s", exc)

    # ── [Phase 2] 融资融券 / 北向资金 接入微调置信度 ──
    try:
        # 1. 融资融券
        if extend_margin and isinstance(extend_margin, dict) and extend_margin.get("status") == "正常":
            _m_buy = safe_float(extend_margin, "margin_buy_wan")
            _m_sell = safe_float(extend_margin, "margin_sell_wan")
            _net_buy = _m_buy - _m_sell
            if weighted_score > 0.1:
                if _net_buy > 1000:
                    confidence *= 1.02
                elif _net_buy < -1000:
                    confidence *= 0.98
                    
        # 2. 北向资金
        if extend_northbound and isinstance(extend_northbound, dict) and extend_northbound.get("status") == "正常":
            _n_net = safe_float(extend_northbound, "north_net_flow_wan")
            _n_5d = safe_float(extend_northbound, "north_flow_5d_wan")
            if weighted_score > 0.1:
                if _n_net > 2000 or _n_5d > 10000:
                    confidence *= 1.05
                elif _n_net < 0 or _n_5d < 0:
                    confidence *= 0.95
                    
        # Keep confidence within [0.0, 1.0]
        confidence = max(0.0, min(confidence, 1.0))
    except (TypeError, AttributeError, ValueError) as exc:
        _logger.debug("Margin/Northbound confidence nudge failed: %s", exc)

    # 6.5 🛡️ 防幻觉拦截：数据断层降级
    # 只降置信度，不 truncation 分数本身（action 已在 493 行用 _action_score 处理过）
    if data_status in ("partial", "degraded", "failed"):
        confidence = min(confidence, 0.3)

    result = {
        "action": action,
        "confidence": round(confidence, 3),
        "weighted_score": round(weighted_score, 3),
        "raw_weighted_score": round(_raw_weighted_score, 3),  # #7: 截断前原始值，供调试
        "regime": regime,
        "hmm_regime": hmm_regime,
        "main_force_env": main_force_env or "unknown",
        "disagreement": round(disagreement, 3),
        "signals_detail": {
            "chan": chan_signal,
            "momentum": momentum_signal,
            "vpf": vpf_signal,
            # 兼容旧读方：短线威科夫已退出，占位中性
            "wyckoff": {
                "direction": 0,
                "confidence": 0.0,
                "reason": "短线已改价量资金，威科夫见中线",
                "raw_key": "wyckoff",
            },
        },
        "weights_used": weights,
    }
    if volume_warning:
        result["volume_warning"] = volume_warning
    if bayesian_used:
        result["bayesian_info"] = bayesian_info
    if has_risk_unlock:
        result["unlock_veto"] = True
        result["unlock_veto_msg"] = f"未来 {days_to_unlock} 天内有大额解禁风险 (比例 {unlock_ratio}%)"
    if has_fund_flow_outflow_veto:
        result["fund_flow_outflow_veto"] = True
        result["fund_flow_outflow_veto_msg"] = f"连续 {fund_flow_outflow_days} 日主力净流出超阈值"

    # 7. 日志 + 安全模式
    _log_fusion(result)
    if FUSION_LOG_ONLY:
        result["action"] = "日志模式 (FUSION_LOG_ONLY=true)，决策由现有 system 输出"

    return result


def merge_decisions_from_plugins(
    current: float,
    bars: list[dict[str, Any]],
    change_pct: float | None,
    quote: dict[str, Any],
    regime: str = "正常",
    hmm_regime: str = "range",
    main_force_env: str | None = None,
    extend_fundamental: dict | None = None,
    extend_sentiment: dict | None = None,
    data_status: str = "full",
    fetcher: DataFetcher | None = None,  # DI: 可注入数据源
    volume_warning: dict | None = None,  # 量价背离警告 (可选)
    fund_flow_data: dict | None = None,  # P1-2: 资金流向特征 (可选)
) -> dict:
    """Decision fusion using the plugin registry.

    Runs all registered plugins, then merges their results using the same
    logic as merge_decisions(). This is the plugin-based alternative to
    manually passing chan_result/momentum_result/wyckoff_result.

    Args:
        current: Current stock price
        bars: Daily K-line bars
        change_pct: Today's change percentage
        quote: Real-time quote dict
        regime: Market environment level
        hmm_regime: HMM regime state
        main_force_env: Main force behavior stage
        extend_fundamental: Extended fundamental data
        extend_sentiment: Extended sentiment data
        fund_flow_data: Fund flow features from calc_fund_flow_features()

    Returns:
        Same dict as merge_decisions()
    """
    from trader_shared.plugin_registry import get_registry

    registry = get_registry()
    plugin_results = registry.analyze_all(current, bars, change_pct, quote)

    # Map plugin results to the format expected by merge_decisions
    chan_result = plugin_results.get("chanlun", {})
    momentum_result = plugin_results.get("momentum", {})
    wyckoff_result = plugin_results.get("wyckoff", {})

    return merge_decisions(
        chan_result=chan_result,
        momentum_result=momentum_result,
        wyckoff_result=wyckoff_result,
        regime=regime,
        current_price=current,
        bars=bars,
        hmm_regime=hmm_regime,
        extend_fundamental=extend_fundamental,
        extend_sentiment=extend_sentiment,
        main_force_env=main_force_env,
        data_status=data_status,
        fetcher=fetcher,
        volume_warning=volume_warning,
        fund_flow_data=fund_flow_data,
    )
