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
            "signals": {k: v["direction"] for k, v in result["signals_detail"].items()},
        }
        print(f"FUSION: {json.dumps(log_data, ensure_ascii=False)}")
    except (json.JSONDecodeError, TypeError):
        # JSON 序列化失败不影响决策
        pass


def _chan_to_signal(chan_result: dict) -> dict:
    """将 chanlun_strategy() 的原始输出映射为统一信号。

    优先级: buy_points > divergence > trend_label

    缠论输出结构 (chanlun_strategy → run_all → levels["chanlun"]):
        {"chanlun": {"buy_points": [...], "divergence": {...}, "trend_label": "..."}}
    """
    chan = chan_result.get("chanlun", {}) if isinstance(chan_result, dict) else {}
    if not isinstance(chan, dict):
        chan = {}

    buy_points = chan.get("buy_points", [])
    divergence = chan.get("divergence", {})
    trend_label = chan.get("trend_label", "数据不足")

    # 优先级1: buy_points (一类买 > 二类买 > 三类买)
    if isinstance(buy_points, list):
        for bp in buy_points:
            if not isinstance(bp, dict):
                continue
            bp_type = bp.get("type", "")
            if bp_type == "一类买":
                return {"direction": 1, "confidence": 0.8,
                        "reason": "缠论一类买 (底背驰)", "raw_key": "chan"}
            if bp_type == "二类买":
                return {"direction": 1, "confidence": 0.6,
                        "reason": "缠论二类买 (低点抬高)", "raw_key": "chan"}
            if bp_type == "三类买":
                return {"direction": 1, "confidence": 0.4,
                        "reason": "缠论三类买 (突破中枢)", "raw_key": "chan"}

    # 优先级2: 背驰
    if isinstance(divergence, dict):
        if divergence.get("bottom_divergence"):
            return {"direction": 1, "confidence": 0.5,
                    "reason": "缠论底背驰", "raw_key": "chan"}
        if divergence.get("top_divergence"):
            return {"direction": -1, "confidence": 0.5,
                    "reason": "缠论顶背驰", "raw_key": "chan"}

    # 优先级3: 趋势
    if isinstance(trend_label, str):
        if "拉升段" in trend_label:
            return {"direction": 1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}", "raw_key": "chan"}
        if "回调段" in trend_label:
            return {"direction": -1, "confidence": 0.4,
                    "reason": f"缠论:{trend_label}", "raw_key": "chan"}

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
    }


def _score_to_confidence(score: float) -> float:
    """从 0-100 分数映射到 0-1 置信度。

    U 型函数: 两端信号强 → 置信度高, 中间灰区 → 置信度低
    - <= 25/>= 75: 极端信号, 置信度 0.8
    - <= 35/  >= 65: 强信号, 0.6
    - <= 40/ >= 60: 中等信号, 0.5
    - 41-59: 灰区, 0.2-0.5 (50 最低)
    """
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 0.2

    if score >= 75:
        return 0.8
    if score >= 65:
        return 0.6
    if score >= 60:
        return 0.5

    if score <= 25:
        return 0.8
    if score <= 35:
        return 0.6
    if score <= 40:
        return 0.5

    # 41-59 灰区: V 形, 50 最低 (0.2), 向 40/60 两侧上升 (0.5)
    if score < 50:
        ratio = (50 - score) / 10
        return 0.2 + ratio * 0.3
    else:
        ratio = (score - 50) / 9
        return 0.2 + ratio * 0.3


def _wyckoff_to_signal(wyckoff_result: dict) -> dict:
    """将 wyckoff_analysis() 的原始输出映射为统一信号。

    威科夫输出结构 (wyckoff_strategy → run_all → levels["wyckoff"]):
        {"wyckoff": {"spring_signal": True, "bullish_volume_divergence": False, ...}}

    Spring 信号最强 (0.7)，背离次之 (0.5)，上冲回落看空 (0.6)。
    Spring + bullish_div 同时存在时叠加 (取较高者, 不重复加)。
    """
    wyk = wyckoff_result.get("wyckoff", {}) if isinstance(wyckoff_result, dict) else {}
    if not isinstance(wyk, dict):
        wyk = {}

    spring = wyk.get("spring_signal")
    bullish_div = wyk.get("bullish_volume_divergence")
    bearish_div = wyk.get("bearish_volume_divergence")
    upthrust = wyk.get("upthrust_signal")
    spring_reason = wyk.get("spring_reason", "")

    # Spring 信号最强 (0.7) + 如果同时有 bullish_div，微调为 0.75
    if spring:
        confidence = 0.7
        if bullish_div:
            confidence = 0.75
        return {
            "direction": 1,
            "confidence": confidence,
            "reason": f"威科夫弹簧 ({spring_reason})",
            "raw_key": "wyckoff",
        }

    # 看涨 vs 看空背离 (同时出现以看涨为准, 威科夫偏多信号权重更高)
    if bullish_div and not bearish_div:
        return {"direction": 1, "confidence": 0.5,
                "reason": "威科夫看多量价背离", "raw_key": "wyckoff"}
    if bearish_div and not bullish_div:
        return {"direction": -1, "confidence": 0.5,
                "reason": "威科夫看空量价背离", "raw_key": "wyckoff"}

    # 上冲回落 (看空)
    if upthrust:
        return {"direction": -1, "confidence": 0.6,
                "reason": "威科夫上冲回落", "raw_key": "wyckoff"}

    return {"direction": 0, "confidence": 0.2,
            "reason": "威科夫无明确信号", "raw_key": "wyckoff"}


def merge_decisions(
    chan_result: dict,
    momentum_result: dict,
    wyckoff_result: dict,
    regime: str = "正常",
) -> dict:
    """决策融合层核心函数。

    Args:
        chan_result:     chanlun_strategy() 的返回值 (levels["chanlun"])
        momentum_result: momentum_strategy() 的返回值 (levels["momentum"])
        wyckoff_result:  wyckoff_strategy() 的返回值 (levels["wyckoff"])
        regime:          market_env assess() 返回的 level 字段
                         ("正常" | "偏弱" | "很差" | "未知")

    Returns:
        {
            "action": str,
            "confidence": float,
            "weighted_score": float,
            "regime": str,
            "disagreement": float,
            "signals_detail": {...},
            "weights_used": {...},
        }
    """
    from fusion_regime import get_regime_weights, score_to_action, compute_confidence

    # 1. 信号标准化 (只读, 不修改输入)
    try:
        chan_signal = _chan_to_signal(chan_result)
    except Exception:
        print(f"FUSION-WARN: chanlun signal normalization failed", file=sys.stderr)
        chan_signal = {"direction": 0, "confidence": 0.0,
                       "reason": "缠论标准化异常", "raw_key": "chan"}

    try:
        momentum_signal = _momentum_to_signal(momentum_result)
    except Exception:
        print(f"FUSION-WARN: momentum signal normalization failed", file=sys.stderr)
        momentum_signal = {"direction": 0, "confidence": 0.0,
                           "reason": "动量标准化异常", "raw_key": "momentum"}

    try:
        wyckoff_signal = _wyckoff_to_signal(wyckoff_result)
    except Exception:
        print(f"FUSION-WARN: wyckoff signal normalization failed", file=sys.stderr)
        wyckoff_signal = {"direction": 0, "confidence": 0.0,
                          "reason": "威科夫标准化异常", "raw_key": "wyckoff"}

    # 2. 获取 Regime 权重
    weights = get_regime_weights(regime)

    # 3. 加权计算
    weighted_score = (
        chan_signal["direction"] * chan_signal["confidence"] * weights["chan"] +
        momentum_signal["direction"] * momentum_signal["confidence"] * weights["momentum"] +
        wyckoff_signal["direction"] * wyckoff_signal["confidence"] * weights["wyckoff"]
    )

    # 4. 分歧检测 (0=全一致, 2=完全相反)
    directions = [chan_signal["direction"],
                  momentum_signal["direction"],
                  wyckoff_signal["direction"]]
    disagreement = max(directions) - min(directions)

    # 5. 决策映射
    action = score_to_action(weighted_score, disagreement, regime)

    # 6. 综合置信度
    confidence = compute_confidence(weighted_score, disagreement, weights)

    result = {
        "action": action,
        "confidence": round(confidence, 3),
        "weighted_score": round(weighted_score, 3),
        "regime": regime,
        "disagreement": round(disagreement, 3),
        "signals_detail": {
            "chan": chan_signal,
            "momentum": momentum_signal,
            "wyckoff": wyckoff_signal,
        },
        "weights_used": weights,
    }

    # 7. 日志 + 安全模式
    _log_fusion(result)
    if FUSION_LOG_ONLY:
        result["action"] = "日志模式 (FUSION_LOG_ONLY=true)，决策由现有系统输出"

    return result
