"""Wyckoff core facade: public API + re-export of split submodules."""
from __future__ import annotations

import json
import os
from typing import Any

from trader_shared.light_data import to_float

# ── Wyckoff 常量（唯一来源：trader_shared.config） ----
from trader_shared.config import (
    WYCKOFF_MIN_BARS,
    WYCKOFF_BC_VOL_RATIO_THRESHOLD,
    WYCKOFF_BC_CHANGE_THRESHOLD,
    WYCKOFF_BC_UPPER_SHADOW_RATIO,
    WYCKOFF_BC_MIN_POS_PCT,
    WYCKOFF_SOW_SUPPORT_LOOKBACK,
    WYCKOFF_SOW_VOL_RATIO_THRESHOLD,
    WYCKOFF_SOW_CONSECUTIVE_DAYS,
    WYCKOFF_SPRING_SUPPORT_LOOKBACK,
    WYCKOFF_SPRING_RECLAIM_RATIO,
    WYCKOFF_SPRING_ATR_MULTIPLE,
    WYCKOFF_SPRING_BULLISH_VOL_RATIO,
    WYCKOFF_SPRING_LOW_VOL_RATIO,
    WYCKOFF_UTAD_BREAKOUT_RATIO,
    WYCKOFF_UTAD_RECLAIM_RATIO,
    WYCKOFF_UT_VOL_RATIO,
    WYCKOFF_DIVERGENCE_BARS,
    WYCKOFF_DIVERGENCE_RATIO,
    WYCKOFF_PHASE_LOOKBACK,
    WYCKOFF_VSA_AVG_SPREAD_PERIOD,
    WYCKOFF_SCORE_SPRING,
    WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS,
    WYCKOFF_SCORE_BULLISH_DIV,
    WYCKOFF_SCORE_UT,
    WYCKOFF_SCORE_BEARISH_DIV,
    WYCKOFF_SCORE_BC,
    WYCKOFF_SCORE_SOW,
    WYCKOFF_SCORE_MAX_ABS,
    WYCKOFF_SCORE_AR,
    WYCKOFF_SCORE_SOS,
    WYCKOFF_SCORE_ST,
    WYCKOFF_SCORE_LPS,
    WYCKOFF_SCORE_LPSY,
    WYCKOFF_SCORE_COMPRESSION,
    WYCKOFF_SCORE_TREND_PB,
    WYCKOFF_COMPRESSION_LOOKBACK,
    WYCKOFF_COMPRESSION_ATR_QUANTILE,
    WYCKOFF_COMPRESSION_VOL_RATIO,
    WYCKOFF_COMPRESSION_VOL_REF_WINDOW,
    WYCKOFF_TREND_PB_LOOKBACK,
    WYCKOFF_TREND_PB_MIN_PULLBACK,
    WYCKOFF_TREND_PB_MAX_PULLBACK,
    WYCKOFF_TREND_PB_VOL_SHRINK,
    WYCKOFF_TREND_PB_MA_WINDOW,
)


# ── 共享工具：Spring 刺穿深度 / BC 高位过滤 ─────────────────────────


from .wyckoff_phase import (
    _PHASE_ORDER,
    _WYCKOFF_PHASE_FILE,
    _detect_phase,
    _load_phase_state,
    _phase_key,
    _save_phase_state,
    _scan_for_signal,
    _transition_phase
)

from .wyckoff_events import (
    _board_vol_scale,
    _compute_dynamic_support,
    _detect_ar,
    _detect_buying_climax,
    _detect_compression,
    _detect_effort_vs_result,
    _detect_lps,
    _detect_lpsy,
    _detect_selling_climax,
    _detect_sign_of_weakness,
    _detect_sos,
    _detect_spring,
    _detect_st,
    _detect_trend_pullback,
    _detect_upthrust,
    _detect_volume_divergence,
    _is_bc_high_position,
    _is_frozen_board,
    _is_trading_range,
    _price_pos_pct,
    _spring_breach_level
)

def wyckoff_analysis(bars: list[dict], symbol: str = "", timeframe: str = "daily", use_persisted_phase: bool = True) -> dict:
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "spring_signal": False, "spring_reason": "数据不足", "spring_price": None,
            "upthrust_signal": False, "upthrust_reason": "数据不足", "upthrust_price": None,
            "bc_signal": False, "bc_reason": "数据不足", "bc_price": None,
            "sc_signal": False, "sc_reason": "数据不足", "sc_price": None,
            "sow_signal": False, "sow_reason": "数据不足", "sow_price": None,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            # 新增信号
            "ar_signal": False, "ar_reason": "数据不足", "ar_price": None,
            "sos_signal": False, "sos_reason": "数据不足", "sos_price": None,
            "st_signal": False, "st_reason": "数据不足", "st_price": None,
            "lps_signal": False, "lps_reason": "数据不足", "lps_price": None,
            "lpsy_signal": False, "lpsy_reason": "数据不足", "lpsy_price": None,
            "wyckoff_summary": "K线数据不足，无法进行威科夫分析",
        }

    # P2-2: 动态支撑位计算（多源集成）— 仅用于 Spring 检测
    _weekly_scale = 0.2 if timeframe == "weekly" else 1.0
    _phase_lb = max(10, int(WYCKOFF_PHASE_LOOKBACK * _weekly_scale))
    _support_lb = max(3, int(10 * _weekly_scale))
    dynamic_support = _compute_dynamic_support(bars, lookback=_support_lb)

    spring = _detect_spring(bars, _support=dynamic_support, symbol=symbol)
    upthrust = _detect_upthrust(bars)
    bc = _detect_buying_climax(bars)
    sc = _detect_selling_climax(bars)
    sow = _detect_sign_of_weakness(bars)  # SOW 使用自己的支撑位计算（处理 consecutive 逻辑）
    bearish_div, bullish_div = _detect_volume_divergence(bars)
    ar = _detect_ar(bars)
    sos = _detect_sos(bars)
    st = _detect_st(bars)
    lps = _detect_lps(bars)
    lpsy = _detect_lpsy(bars)
    # P2/P3: 新增信号
    compression = _detect_compression(bars)
    trend_pullback = _detect_trend_pullback(bars)

    # P1-1: 阶段状态机 — 基于信号序列推断积累/派发阶段
    signals_dict = {
        "spring_signal": spring["spring_signal"],
        "upthrust_signal": upthrust["upthrust_signal"],
        "bc_signal": bc["bc_signal"],
        "sc_signal": sc["sc_signal"],
        "sow_signal": sow["sow_signal"],
        "ar_signal": ar["ar_signal"],
        "sos_signal": sos["sos_signal"],
        "st_signal": st["st_signal"],
        "lps_signal": lps["lps_signal"],
        "lpsy_signal": lpsy["lpsy_signal"],
        "compression_signal": compression["compression_signal"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
    }
    phase = _detect_phase(bars, signals_dict, _phase_lookback=_phase_lb)

    # B: 跨日持久化状态机 — 加载旧状态、过渡、存储
    # use_persisted_phase=False 时（如中线威科夫）跳过持久化，直接返回本次
    # K 线的即时推断，避免「只进不退」状态机掩盖当前周期的真实阶段。
    if use_persisted_phase:
        old_state = _load_phase_state(symbol, timeframe)
        new_phase_state = _transition_phase(
            old_state,
            phase["phase"],
            phase["phase_label"],
            phase.get("phase_confidence_delta", 0.0),
        )
        _save_phase_state(symbol, timeframe, new_phase_state)
        # 用过渡后状态覆盖瞬时推断（phase 只进不退）
        phase = new_phase_state

    # P3-1: VSA 量价幅度分析
    vsa = _detect_effort_vs_result(bars)

    parts = []
    if spring["spring_signal"]:
        parts.append(f"弹簧信号: {spring['spring_reason']}")
    if upthrust["upthrust_signal"]:
        parts.append(f"上冲回落信号: {upthrust['upthrust_reason']}")
    if bc["bc_signal"]:
        parts.append(f"购买高潮: {bc['bc_reason']}")
    if sc["sc_signal"]:
        parts.append(f"卖力高潮: {sc['sc_reason']}")
    if sow["sow_signal"]:
        parts.append(f"弱势信号: {sow['sow_reason']}")
    if ar["ar_signal"]:
        parts.append(f"自动反弹: {ar['ar_reason']}")
    if sos["sos_signal"]:
        parts.append(f"强势信号: {sos['sos_reason']}")
    if st["st_signal"]:
        parts.append(f"二次测试: {st['st_reason']}")
    if lps["lps_signal"]:
        parts.append(f"最后支撑: {lps['lps_reason']}")
    if lpsy["lpsy_signal"]:
        parts.append(f"最后供应点: {lpsy['lpsy_reason']}")
    if bearish_div and bullish_div:
        parts.append("量价信号冲突，无法确定方向")
    elif bearish_div:
        parts.append("看空量价背离")
    elif bullish_div:
        parts.append("看多量价背离")
    if vsa["effort_no_result"]:
        parts.append("高量窄幅（努力无结果）")
    if vsa["no_supply"]:
        parts.append("低量窄幅（供应耗尽）")
    if compression["compression_signal"]:
        parts.append(f"压缩蓄势: {compression['compression_reason']}")
    if trend_pullback["trend_pullback_signal"]:
        parts.append(f"趋势回踩: {trend_pullback['trend_pullback_reason']}")
    if not parts:
        parts.append("无明显威科夫信号")

    return {
        "spring_signal": spring["spring_signal"],
        "spring_reason": spring["spring_reason"],
        "spring_price": round(spring["spring_price"], 2) if spring["spring_signal"] else None,
        "upthrust_signal": upthrust["upthrust_signal"],
        "upthrust_reason": upthrust["upthrust_reason"],
        "upthrust_price": round(upthrust["upthrust_price"], 2) if upthrust["upthrust_signal"] else None,
        "bc_signal": bc["bc_signal"],
        "bc_reason": bc["bc_reason"],
        "bc_price": round(bc["bc_price"], 2) if bc["bc_signal"] else None,
        "sow_signal": sow["sow_signal"],
        "sow_reason": sow["sow_reason"],
        "sow_price": round(sow["sow_price"], 2) if sow["sow_signal"] else None,
        "sc_signal": sc["sc_signal"],
        "sc_reason": sc["sc_reason"],
        "sc_price": round(sc["sc_price"], 2) if sc["sc_signal"] else None,
        "bearish_volume_divergence": bearish_div,
        "bullish_volume_divergence": bullish_div,
        # 新增信号
        "ar_signal": ar["ar_signal"],
        "ar_reason": ar["ar_reason"],
        "ar_price": round(ar["ar_price"], 2) if ar["ar_signal"] else None,
        "sos_signal": sos["sos_signal"],
        "sos_reason": sos["sos_reason"],
        "sos_price": round(sos["sos_price"], 2) if sos["sos_signal"] else None,
        "st_signal": st["st_signal"],
        "st_reason": st["st_reason"],
        "st_price": round(st["st_price"], 2) if st["st_signal"] else None,
        "lps_signal": lps["lps_signal"],
        "lps_reason": lps["lps_reason"],
        "lps_price": round(lps["lps_price"], 2) if lps["lps_signal"] else None,
        "lpsy_signal": lpsy["lpsy_signal"],
        "lpsy_reason": lpsy["lpsy_reason"],
        "lpsy_price": round(lpsy["lpsy_price"], 2) if lpsy["lpsy_signal"] else None,
        # P0-1: 弹簧量能分级
        "spring_vol_class": spring.get("spring_vol_class", "normal") if spring["spring_signal"] else None,
        # P1-1: 阶段状态机
        "phase": phase["phase"],
        "phase_label": phase["phase_label"],
        "phase_confidence_delta": phase.get("phase_confidence_delta", 0.0),
        # P3-1: VSA 量价幅度分析
        "effort_no_result": vsa["effort_no_result"],
        "no_supply": vsa["no_supply"],
        # P2/P3: 新增信号
        "compression_signal": compression["compression_signal"],
        "compression_reason": compression["compression_reason"],
        "compression_price": compression["compression_price"],
        "trend_pullback_signal": trend_pullback["trend_pullback_signal"],
        "trend_pullback_reason": trend_pullback["trend_pullback_reason"],
        "trend_pullback_price": trend_pullback["trend_pullback_price"],
        "wyckoff_summary": "；".join(parts),
    }

def wyckoff_strategy(current: float, bars: list[dict], change_pct: Any = None, quote: dict | None = None, symbol: str = "") -> dict:
    """日线威科夫（供 fusion / 短线侧兼容）。"""
    result = wyckoff_analysis(bars, symbol=symbol)
    if isinstance(result, dict):
        result = {**result, "timeframe": "daily"}
    return {"wyckoff": result}

def wyckoff_strategy_midline(
    current: float,
    weekly_bars: list[dict] | None = None,
    daily_bars: list[dict] | None = None,  # 保留兼容签名；中线威科夫周线独占，不再用于回退兜底
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str = "",
) -> dict:
    """中线威科夫独立判断：仅周K（周线不足则不参与中线定论，不回退日线）。

    与日线 fusion 路径分离：报告「威科夫：…」定性用本结果。
    """
    weekly_bars = weekly_bars or []
    # 中线威科夫周线独占：周线不足直接返回 insufficient，不参与 🧭 中线定论，
    # 不再回退日线（避免日线噪音稀释中线战略依据，违反 output-template.md:94）。
    if len(weekly_bars) < WYCKOFF_MIN_BARS:
        return {
            "wyckoff": {
                "timeframe": "insufficient",
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "wyckoff_summary": "周线数据不足，中线威科夫不参与定论",
            }
        }
    result = wyckoff_analysis(weekly_bars, symbol=symbol, timeframe="weekly", use_persisted_phase=False)
    if isinstance(result, dict):
        result = {**result, "timeframe": "weekly"}
    return {"wyckoff": result}

def calculate_wyckoff_score(bars: list[dict], symbol: str = "", analysis: dict | None = None) -> dict:
    """基于 Wyckoff 信号规则的独立打分函数。

    先调用 wyckoff_analysis() 获取 5 路信号，按权重累加 raw_score，
    再线性映射到 0-100 分数（50 为中性）。

    Args:
        bars: 日线 K 线数据列表，最少 WYCKOFF_MIN_BARS 根。
        analysis: 可选，已计算的 wyckoff_analysis 结果，避免重复调用。

    Returns:
        {
            "score": int,          # 0-100 分数
            "raw": int,            # 加权累加原始分（范围约 -80 ~ +80）
            "signals": list[str],  # 参与打分的信号明细
            "summary": str,        # 一句话总结
        }
    """
    if len(bars) < WYCKOFF_MIN_BARS:
        return {
            "score": 50,
            "raw": 0,
            "signals": [],
            "summary": "K线数据不足，无法打分",
        }

    # 打分应为纯函数：analysis 缺失时重算，但不触发 phase 持久化写盘
    analysis = analysis if analysis is not None else wyckoff_analysis(
        bars, symbol=symbol, use_persisted_phase=False
    )

    raw = 0
    signals: list[str] = []

    spring = analysis.get("spring_signal")
    bullish_div = analysis.get("bullish_volume_divergence")
    bearish_div = analysis.get("bearish_volume_divergence")
    upthrust = analysis.get("upthrust_signal")
    bc = analysis.get("bc_signal")
    sow = analysis.get("sow_signal")
    spring_vol_class = analysis.get("spring_vol_class")

    # 1. Spring — 最强看多信号；高量弹簧减半（可能是真破位，非供应耗尽）
    if spring:
        spring_pts = WYCKOFF_SCORE_SPRING
        if spring_vol_class == "high_vol_warning":
            spring_pts = spring_pts // 2  # 高量 Spring 分数减半
            signals.append(f"Spring(高量降权) +{spring_pts}")
        else:
            signals.append(f"Spring +{spring_pts}")
        raw += spring_pts

    # 2. Spring + 看多背离额外加分；高量 Spring 同步降权（与主分一致）
    if spring and bullish_div:
        bonus = WYCKOFF_SCORE_SPRING_BULLISH_DIV_BONUS
        if spring_vol_class == "high_vol_warning":
            bonus = bonus // 2  # 高量时背离加成减半（0 当 1 时 floor 为 0）
            if bonus > 0:
                signals.append(f"Spring×看多背离(高量降权) +{bonus}")
            else:
                signals.append("Spring×看多背离(高量降权) +0")
        else:
            signals.append(f"Spring×看多背离 +{bonus}")
        raw += bonus

    # 3. 独立看多背离
    if bullish_div and not spring:
        raw += WYCKOFF_SCORE_BULLISH_DIV
        signals.append(f"看多背离 +{WYCKOFF_SCORE_BULLISH_DIV}")

    # 4. Upthrust — 假突破派发
    if upthrust:
        raw += WYCKOFF_SCORE_UT
        signals.append(f"Upthrust {WYCKOFF_SCORE_UT}")

    # 5. 看空背离
    if bearish_div and not bullish_div:
        raw += WYCKOFF_SCORE_BEARISH_DIV
        signals.append(f"看空背离 {WYCKOFF_SCORE_BEARISH_DIV}")

    # 6. Buying Climax — 天量滞涨
    if bc:
        raw += WYCKOFF_SCORE_BC
        signals.append(f"购买高潮 {WYCKOFF_SCORE_BC}")

    # 7. Sign of Weakness — 放量跌破
    if sow:
        raw += WYCKOFF_SCORE_SOW
        signals.append(f"弱势信号 {WYCKOFF_SCORE_SOW}")

    # ── 新增经典信号 ──

    # 8. AR (Automatic Rally) — BC 后自动反弹
    if analysis.get("ar_signal"):
        raw += WYCKOFF_SCORE_AR
        signals.append(f"AR 反弹 +{WYCKOFF_SCORE_AR}")

    # 9. SOS (Sign of Strength) — 强势突破
    if analysis.get("sos_signal"):
        raw += WYCKOFF_SCORE_SOS
        signals.append(f"SOS +{WYCKOFF_SCORE_SOS}")

    # 10. ST (Secondary Test) — 二次测试支撑
    if analysis.get("st_signal"):
        raw += WYCKOFF_SCORE_ST
        signals.append(f"ST +{WYCKOFF_SCORE_ST}")

    # 11. LPS (Last Point of Support) — 最后支撑点
    if analysis.get("lps_signal"):
        raw += WYCKOFF_SCORE_LPS
        signals.append(f"LPS +{WYCKOFF_SCORE_LPS}")

    # 12. P2: Compression — 压缩蓄势
    if analysis.get("compression_signal"):
        raw += WYCKOFF_SCORE_COMPRESSION
        signals.append(f"压缩蓄势 +{WYCKOFF_SCORE_COMPRESSION}")

    # 13. P3: Trend Pullback — 趋势回踩
    if analysis.get("trend_pullback_signal"):
        raw += WYCKOFF_SCORE_TREND_PB
        signals.append(f"趋势回踩 +{WYCKOFF_SCORE_TREND_PB}")

    # 14. SC (Selling Climax) — 卖力高潮，看多
    if analysis.get("sc_signal"):
        raw += WYCKOFF_SCORE_AR  # SC 的看多强度与 AR 同级（+10）
        signals.append(f"SC +{WYCKOFF_SCORE_AR}")

    # 15. LPSY (Last Point of Supply) — 最后供应点，看空
    if analysis.get("lpsy_signal"):
        raw += WYCKOFF_SCORE_LPSY  # LPSY 负向等同 LPS 正向强度
        signals.append(f"LPSY {WYCKOFF_SCORE_LPSY}")

    # ── P3-1: VSA 量价幅度修正 ──
    effort_no_result = analysis.get("effort_no_result", False)
    no_supply = analysis.get("no_supply", False)

    # Spring + 低量窄幅（供应耗尽）→ 额外加分
    if spring and no_supply:
        raw += 5
        signals.append("Spring×供应耗尽 +5")

    # UT + 高量窄幅（努力无结果）→ 额外扣分（派发确认）
    if upthrust and effort_no_result:
        raw -= 5
        signals.append("UT×努力无结果 -5")

    # SOS + 高量窄幅 → SOS 不可靠，取消加分
    if analysis.get("sos_signal") and effort_no_result:
        raw -= WYCKOFF_SCORE_SOS
        signals.append(f"SOS×努力无结果 撤销 +{WYCKOFF_SCORE_SOS}")

    # VSA 单独修正：低量窄幅（供应耗尽）独立看多
    if no_supply and not spring and not analysis.get("sos_signal"):
        raw += 5
        signals.append("供应耗尽 +5")
    # VSA 单独修正：高量窄幅（努力无结果）独立看空
    if effort_no_result and not upthrust and not analysis.get("sos_signal"):
        raw -= 5
        signals.append("努力无结果 -5")

    # ── 阶段置信度修正：phase_confidence_delta * 20 取整后微调 raw ──
    phase_delta = analysis.get("phase_confidence_delta") or 0.0
    try:
        phase_adj = int(round(float(phase_delta) * 20))
    except (TypeError, ValueError):
        phase_adj = 0
    if phase_adj:
        raw += phase_adj
        signals.append(f"阶段修正 {phase_adj:+d}")

    # 线性映射: raw ∈ [-MAX_ABS, +MAX_ABS] → score ∈ [0, 100]
    score = max(0, min(100, 50 + raw * 50 // WYCKOFF_SCORE_MAX_ABS))

    if score >= 70:
        summary = f"威科夫看多（{score}/100）"
    elif score >= 60:
        summary = f"威科夫偏多（{score}/100）"
    elif score <= 30:
        summary = f"威科夫看空（{score}/100）"
    elif score <= 40:
        summary = f"威科夫偏空（{score}/100）"
    else:
        summary = f"威科夫中性（{score}/100）"

    return {
        "score": score,
        "raw": raw,
        "signals": signals,
        "summary": summary,
    }

def format_wyckoff_oneline(
    wyckoff: dict[str, Any] | None = None,
    *,
    direction: int | None = None,
    show_phase: bool = False,
) -> str:
    """报告用威科夫一行人话（结论 + 白话，不拆第二行）。

    优先级与 fusion 主信号大致对齐：
      Spring > SOS > UT > BC > SOW > LPSY > SC > AR > ST > LPS > Compression > TrendPullback > 背离 > 无信号
    LPSY（最后供应点）在 SOW 之前：派发 D 阶段信号比 C 阶段更接近 breakdown。
    SC（卖力高潮）在 AR 之前：SC 是积累启动的原发事件，AR 是 SC 后的跟随反弹。

    Args:
        wyckoff: 威科夫分析结果 dict
        direction: 外部覆盖方向
        show_phase: 是否在输出中显示 phase_label

    Returns:
        如「威科夫：低位假跌破后收回，偏多（更像洗盘，缩量较可信）」
        如 show_phase=True：「积累期 C（测试：Spring）· 低位假跌破后收回，偏多」
    """
    wyk = wyckoff if isinstance(wyckoff, dict) else {}
    # 兼容 strategy 包装
    if "wyckoff" in wyk and isinstance(wyk.get("wyckoff"), dict):
        wyk = wyk["wyckoff"]

    def _dir_label(d: int) -> str:
        if d > 0:
            return "偏多"
        if d < 0:
            return "偏空"
        return "中性"

    # 按 fusion 优先级选主信号
    if wyk.get("spring_signal"):
        vol = wyk.get("spring_vol_class") or "normal"
        if vol == "high_vol_warning":
            main = "低位跌破后收回"
            note = "放量跌破，也可能是真破位，信号偏弱"
            d = 1
        elif vol == "low_vol_confirm":
            main = "低位假跌破后收回"
            note = "更像洗盘，缩量较可信"
            d = 1
        else:
            main = "低位假跌破后收回"
            note = "更像洗盘吸筹"
            d = 1
    elif wyk.get("sos_signal"):
        main, note, d = "连续放量上攻", "多头发力，趋势转强迹象", 1
    elif wyk.get("upthrust_signal"):
        main, note, d = "冲高回落假突破", "上方试盘失败，结构偏顶", -1
    elif wyk.get("bc_signal"):
        main, note, d = "高位放量滞涨", "购买高潮迹象，注意见好就收", -1
    elif wyk.get("sow_signal"):
        main, note, d = "放量跌破支撑", "弱势确认，防守优先", -1
    elif wyk.get("ar_signal"):
        main, note, d = "高潮后快速反弹", "仅反弹，还不能当反转", 1
    elif wyk.get("sc_signal"):
        main, note, d = "天量宽幅下跌", "卖力高潮，抛压宣泄后可能止跌", 1
    elif wyk.get("st_signal"):
        main, note, d = "回踩支撑站住", "二次确认支撑有效", 1
    elif wyk.get("lps_signal"):
        main, note, d = "突破后缩量回踩", "回踩不破，仍偏强", 1
    elif wyk.get("lpsy_signal"):
        main, note, d = "反弹受阻缩量", "最后供应点，警惕破位下行", -1
    # P2/P3: 新增信号（优先级在 LPS 之后、divergence 之前）
    elif wyk.get("compression_signal"):
        main, note, d = "压缩蓄势", "振幅收窄+量能枯竭，突破在即", 1
    elif wyk.get("trend_pullback_signal"):
        main, note, d = "趋势回踩", "回踩不破均线，趋势延续", 1
    elif wyk.get("bullish_volume_divergence") and not wyk.get("bearish_volume_divergence"):
        main, note, d = "下跌缩量", "抛压减轻，有止跌迹象", 1
    elif wyk.get("bearish_volume_divergence") and not wyk.get("bullish_volume_divergence"):
        main, note, d = "上涨缩量", "上攻乏力，慎追高", -1
    else:
        # 已跑完引擎但未触发 Spring/SOS/UT 等事件 → 不是「数据不全」
        # 有 timeframe / summary 视为已计算；完全空 dict 才偏数据不足
        has_run = bool(
            wyk.get("timeframe")
            or wyk.get("wyckoff_summary")
            or any(
                k.endswith("_signal") or k.endswith("_reason")
                for k in wyk.keys()
            )
        )
        if has_run:
            _phase = wyk.get("phase_label") or ""
            _tf2 = "（日线）" if wyk.get("timeframe") == "daily_fallback" else ""
            if show_phase and _phase and "无明确阶段" not in _phase:
                return f"威科夫：{_phase} · 暂无事件 · 中性{_tf2}"
            return f"威科夫：暂无事件 · 中性{_tf2}"
        return "威科夫：数据不足 · 中性"

    # 外部 fusion direction 可覆盖展示方向（保持与融合层一致）
    if direction is not None:
        d = int(direction)
    # phase 前缀（如 show_phase=True 且 phase 非 none）
    phase_prefix = ""
    if show_phase:
        _phase = wyk.get("phase_label") or ""
        if _phase and "无明确阶段" not in _phase:
            phase_prefix = f"{_phase} · "
    # 回退标注：周线不足时用日线分析，诚实提示
    _tf_suffix = ""
    if wyk.get("timeframe") == "daily_fallback":
        _tf_suffix = "（日线）"
    # 句式：威科夫：{判断} · {偏多|偏空|中性}（说明）{回退标注}
    return f"威科夫：{phase_prefix}{main} · {_dir_label(d)}（{note}）{_tf_suffix}"
