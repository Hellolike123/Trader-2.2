"""Stage detection engine."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import numpy as np
from trader_shared._logging import get_logger
from trader_shared.safe_cast import safe_float
from trader_shared.config import (
    ACCUMULATION_DAYS_LIMIT, MARKUP_DAYS_LIMIT,
    RALLY_REDUCE_FULL_SCORE, RALLY_REDUCE_MIN_SCORE,
    RALLY_REDUCE_POSITION_PCT, RALLY_REDUCE_LITE_POSITION_PCT,
    CORRELATION_THRESHOLD, CORRELATION_LOOKBACK_DAYS,
)

from .stage_state import (
    _STATE_FILE,
    _load_stage_state,
    _logger,
    _save_stage_state,
    calc_portfolio_correlation
)

from .stage_stops import (
    check_time_stop,
    compute_exit_plan,
    compute_stage_stop,
    compute_stop_losses,
    compute_stop_summary
)

_ADD_ACTIONS = frozenset({"增持", "半仓试 (多方主导)", "半仓试 (多方主导但有分歧)"})

_DECISION_MATRIX: dict[str, dict[str, tuple[str, int]]] = {
    "蓄势": {
        "走强": ("低吸试盘", 20),
        "修复": ("回调低吸", 15),
        "震荡": ("观望等待", 0),
        "转弱": ("观望等待", 0),
    },
    "蓄势偏强": {
        "走强": ("试探建仓", 30),
        "修复": ("回调低吸", 25),
        "震荡": ("小仓试探", 10),
        "转弱": ("观望等待", 0),
    },
    "蓄势偏弱": {
        "走强": ("观望等待", 0),
        "修复": ("观望等待", 0),
        "震荡": ("观望等待", 0),
        "转弱": ("观望等待", 0),
    },
    "主升": {
        "走强": ("顺势加仓", 60),
        "修复": ("回踩加仓", 40),
        "震荡": ("底仓持有", 20),
        "转弱": ("跌破防线减仓", 20),
    },
    "派发": {
        "走强": ("逢高减磅", 20),
        "修复": ("逢反弹减仓", 10),
        "震荡": ("逢反弹减仓", 10),
        "转弱": ("清仓逃命", 0),
    },
    "衰退": {
        "走强": ("空仓规避", 0),
        "修复": ("空仓规避", 0),
        "震荡": ("空仓规避", 0),
        "转弱": ("空仓规避", 0),
    },
}

_ENV_LIMITS: dict[str, dict[str, int]] = {
    #                单票上限  总仓位上限  新建仓
    "牛市": {"single": 40, "total": 80, "init": 10},
    "震荡市": {"single": 30, "total": 60, "init": 10},
    "熊市": {"single": 20, "total": 30, "init": 10},
}

_REDUCE_ACTIONS = frozenset({
    "减仓",
    "空仓/止损",
    "空仓 (大盘很差, 一票否决)",
    "天量天价，减仓观望",
    "资金流出，减仓观望",
    "空仓 (限售解禁风险)",
    "减1/3 (高位松动)",
})

def _bearish_alignment(bars: list[dict[str, Any]], current: float) -> bool:
    """空头排列：现价在所有均线下方且 MA5<MA10<MA20（确认下跌趋势）。

    P1b：用于收紧蓄势判定——空头排列下缩量下跌是衰退而非筑底，
    反弹上涨也不是蓄势偏强，禁止输出蓄势/蓄势偏强。
    """
    if len(bars) < 20 or current <= 0:
        return False
    closes = [float(b.get("close") or 0) for b in bars[-20:] if b.get("close")]
    if len(closes) < 20:
        return False
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes) / 20
    if ma5 <= 0 or ma10 <= 0 or ma20 <= 0:
        return False
    # 空头排列：短期均线在下方（MA5 < MA10 < MA20）且现价跌破所有均线
    return current < ma20 and ma5 < ma10 < ma20

def _assess_volume_price(
    bars: list[dict[str, Any]],
    wyckoff_result: dict[str, Any] | None = None,
) -> tuple[str, float, str]:
    """威科夫量价关系判定四阶段。

    优先使用 wyckoff_core 的真实信号（spring/upthrust/背离），
    无威科夫信号时 fallback 到量比+涨跌幅启发式判断。

    Returns:
        (stage, score, reason)
        score: 0-100，该维度对阶段判定的置信度
    """
    if not bars or len(bars) < 20:
        return "蓄势", 30, "数据不足，默认蓄势"

    # ── 威科夫信号优先判定 ──
    if wyckoff_result:
        # 兼容两种格式：嵌套（wyckoff_strategy 包装后 {"wyckoff": {...}}）
        # 和扁平（wyckoff_analysis 直接返回 {...}）
        if isinstance(wyckoff_result, dict) and "wyckoff" in wyckoff_result:
            wyk = wyckoff_result["wyckoff"]
        else:
            wyk = wyckoff_result if isinstance(wyckoff_result, dict) else {}
        if isinstance(wyk, dict):
            spring = wyk.get("spring_signal")
            upthrust = wyk.get("upthrust_signal")
            bullish_div = wyk.get("bullish_volume_divergence")
            bearish_div = wyk.get("bearish_volume_divergence")
            spring_reason = wyk.get("spring_reason", "")

            # Spring = 吸筹确认 → 蓄势偏强/主升前兆
            if spring:
                return "蓄势偏强", 75, f"威科夫弹簧确认（{spring_reason}），吸筹末期"

            # 上冲回落 = 派发信号
            if upthrust:
                return "派发", 70, "威科夫上冲回落，派发信号"

            # 看多量价背离 = 吸筹
            if bullish_div and not bearish_div:
                return "蓄势偏强", 60, "威科夫看多量价背离，吸筹中"

            # 看空量价背离 = 派发
            if bearish_div and not bullish_div:
                return "派发", 60, "威科夫看空量价背离，派发中"

    recent5 = bars[-5:]
    recent20 = bars[-20:]
    current_price = float(bars[-1].get("close") or 0)
    bearish_align = _bearish_alignment(bars, current_price)

    # 计算量能比率
    vol_5 = [float(b.get("volume") or 0) for b in recent5]
    vol_20 = [float(b.get("volume") or 0) for b in recent20]
    avg_vol_5 = sum(vol_5) / max(len(vol_5), 1)
    avg_vol_20 = sum(vol_20) / max(len(vol_20), 1)
    if avg_vol_20 <= 0:
        # 须返回 (str, float, str)；旧 (0.0,"","") 会污染 major_stage / 打崩 assess_stage
        return "蓄势", 30.0, "量能缺失，默认蓄势"
    vol_ratio = avg_vol_5 / avg_vol_20

    # P1 Fix: 计算 5 日涨幅时，剔除历史单日涨跌幅 > 7% 的跳空缺口日，
    # 避免单日缺口主导阶段判定（如涨停后横盘 4 天被误判为"主升"）
    # 注意：最后一天（今天）不排除，真突破不应被误杀
    close_5_start = float(recent5[0].get("close") or 0)
    close_5_end = float(recent5[-1].get("close") or 0)

    # 计算每日涨跌幅，找出跳空日（排除最后一天/今天）
    gap_indices: set[int] = set()
    for i, b in enumerate(recent5):
        if i == 0 or i == len(recent5) - 1:
            continue
        prev_c = float(recent5[i - 1].get("close") or 0)
        cur_c = float(b.get("close") or 0)
        if prev_c > 0 and abs(cur_c - prev_c) / prev_c > 0.07:
            gap_indices.add(i)

    if close_5_start > 0:
        if gap_indices:
            # P1 Fix: 剔除跳空日，基准价为第一个跳空日前一日的收盘价。
            # 原代码 base_idx 循环从 0 开始、index 0 永不为 gap，永远返回 0 —— 跳空检测完全旁路。
            base_idx = max(0, min(gap_indices) - 1)
            base_price = float(recent5[base_idx].get("close") or close_5_start)
            if base_price > 0:
                price_change_5 = (close_5_end - base_price) / base_price
            else:
                price_change_5 = 0.0
        else:
            price_change_5 = (close_5_end - close_5_start) / close_5_start
    else:
        price_change_5 = 0.0

    # 计算振幅
    highs = [float(b.get("high") or 0) for b in recent5]
    lows = [float(b.get("low") or 0) for b in recent5]
    if close_5_start > 0:
        amplitude = (max(highs) - min(lows)) / close_5_start
    else:
        amplitude = 0.0

    # 威科夫四阶段判定
    is_low_volume = vol_ratio < 0.8    # 缩量
    is_high_volume = vol_ratio > 1.2   # 放量
    is_rising = price_change_5 > 0.03  # 涨幅 > 3%
    is_falling = price_change_5 < -0.03  # 跌幅 > 3%
    is_flat = abs(price_change_5) < 0.01  # 振幅 < 1%
    is_strong_rising = price_change_5 > 0.08  # 涨幅 > 8%，强势突破

    if is_low_volume and is_flat and amplitude < 0.05:
        return "蓄势", 70, f"缩量横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_rising:
        return "主升", 80, f"放量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if is_strong_rising:
        if bearish_align:
            return "蓄势", 50, f"缩量强势上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
        return "蓄势偏强", 55, f"缩量强势上涨，量价不配合（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if is_high_volume and is_flat:
        return "派发", 65, f"放量不涨（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_falling:
        return "衰退", 75, f"放量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # 弱信号：缩量下跌（可能是衰退末期的缩量筑底）
    if is_low_volume and is_falling:
        # P1b：空头排列时缩量下跌是衰退而非筑底，禁止判蓄势
        if bearish_align:
            return "蓄势偏弱", 35, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）｜空头排列非筑底"
        return "蓄势", 50, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%），可能筑底"

    # 弱信号：放量但方向不明确（分涨跌处理）
    if is_high_volume:
        if price_change_5 > 0:
            if bearish_align:
                return "蓄势", 50, f"放量微涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
            return "蓄势偏强", 50, f"放量微涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        else:
            return "派发", 45, f"放量微跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # ── 正常量能区域分化（vol_ratio 0.8~1.2，覆盖约 65% 的交易日） ──
    if vol_ratio >= 0.8 and vol_ratio < 1.2:
        if price_change_5 > 0.03:
            if bearish_align:
                return "蓄势", 55, f"正常量能上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
            return "蓄势偏强", 65, f"正常量能上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 > 0.01:
            if bearish_align:
                return "蓄势", 50, f"温和上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
            return "蓄势偏强", 58, f"温和上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.03:
            if bearish_align:
                return "衰退", 55, f"正常量能下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）｜空头排列"
            return "蓄势偏弱", 55, f"正常量能下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.01:
            if bearish_align:
                return "衰退", 48, f"正常量能回调（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）｜空头排列"
            return "蓄势偏弱", 48, f"正常量能回调（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        # 正常量能 + 横盘 → 真正的蓄势
        return "蓄势", 40, f"正常量能横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # ── 缩量区域分化 ──
    if vol_ratio < 0.8:
        if price_change_5 > 0.01:
            if bearish_align:
                return "蓄势", 50, f"缩量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
            return "蓄势偏强", 58, f"缩量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.01:
            if bearish_align:
                return "衰退", 42, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）｜空头排列"
            return "蓄势偏弱", 42, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        # 缩量横盘已在上面处理（is_low_volume and is_flat），这里兜底
        return "蓄势", 40, f"缩量横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # ── 放量区域 ──
    # 已在上面处理（is_high_volume + rising/flat/falling）
    # 这里是放量但幅度不够大的兜底
    if price_change_5 > 0:
        if bearish_align:
            return "蓄势", 50, f"放量微涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）｜空头排列反弹非蓄势偏强"
        return "蓄势偏强", 50, f"放量微涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if price_change_5 < 0:
        if bearish_align:
            return "衰退", 48, f"放量微跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）｜空头排列"
        return "蓄势偏弱", 48, f"放量微跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # 默认
    return "蓄势", 40, f"量价无明确信号（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

def _detect_main_force_stage(main_force_result: dict | None) -> tuple[str | None, float, str]:
    """主力行为 → 大阶段映射。

    Args:
        main_force_result: detect_main_force_stage() 的返回值，含 stage/confidence/signals

    Returns:
        (stage, confidence, reason)
        stage=None 表示无数据，不参与融合
        confidence: 0-100
    """
    if not main_force_result or not isinstance(main_force_result, dict):
        return None, 0.0, ""

    mf_stage = main_force_result.get("stage", "unknown")
    mf_confidence = float(main_force_result.get("confidence") or 0)
    mf_signals = main_force_result.get("signals", [])

    if mf_stage == "unknown" or mf_confidence <= 0:
        return None, 0.0, ""

    signal_text = "；".join(mf_signals[-2:]) if mf_signals else ""

    mapping = {
        "accumulation": ("蓄势", 60),
        "testing": ("蓄势偏强", 55),
        "markup": ("主升", 70),
        "distribution": ("派发", 65),
        "markdown": ("衰退", 60),
    }

    result = mapping.get(mf_stage)
    if result is None:
        return None, 0.0, ""

    stage, base_conf = result
    # 置信度打折：main_force 的 confidence 是 0-1，一致性高时全额，低时打折
    conf_multiplier = min(mf_confidence, 1.0) if mf_confidence > 0 else 0.5
    confidence = min(100, int(base_conf * min(conf_multiplier, 1.0)))

    reason = f"主力{mf_stage}(置信度{mf_confidence:.2f})"
    if signal_text:
        reason += f" [{signal_text}]"

    return stage, confidence, reason

def _volume_price_confirm(
    mf_stage: str,
    bars: list[dict[str, Any]] | None,
    wyckoff_result: dict[str, Any] | None = None,
) -> tuple[str, float, str]:
    """量价确认主力信号的真假。

    不独立判阶段，只对主力信号做确认/降级/升级。

    Args:
        mf_stage: main_force 输出的阶段 (accumulation/testing/markup/distribution/markdown)
        bars: K线数据
        wyckoff_result: 威科夫分析结果

    Returns:
        (action, confidence, reason)
        action: "confirm" / "downgrade" / "upgrade"
        confidence: 0-1 确认置信度
    """
    if not bars or len(bars) < 5:
        return "confirm", 0.0, "数据不足，默认确认"

    recent5 = bars[-5:]

    # ── 量价计算 ──
    vol_5 = [float(b.get("volume") or 0) for b in recent5]
    vol_20_avg = 0.0
    if len(bars) >= 20:
        vol_20 = [float(b.get("volume") or 0) for b in bars[-20:]]
        vol_20_avg = sum(vol_20) / max(len(vol_20), 1)
    elif len(bars) >= 10:
        vol_10 = [float(b.get("volume") or 0) for b in bars[-10:]]
        vol_20_avg = sum(vol_10) / max(len(vol_10), 1)
    avg_vol_5 = sum(vol_5) / max(len(vol_5), 1)
    vol_ratio = avg_vol_5 / max(vol_20_avg, 1) if vol_20_avg > 0 else 1.0

    close_5_start = float(recent5[0].get("close") or 0)
    close_5_end = float(recent5[-1].get("close") or 0)
    price_change_5 = (close_5_end - close_5_start) / close_5_start if close_5_start > 0 else 0.0

    # ── 提取威科夫信号 ──
    spring = False
    upthrust = False
    if wyckoff_result:
        wyk = wyckoff_result.get("wyckoff", {}) if isinstance(wyckoff_result, dict) else {}
        if isinstance(wyk, dict):
            spring = wyk.get("spring_signal", False)
            upthrust = wyk.get("upthrust_signal", False)

    # ── 量价判断 ──
    rising = price_change_5 > 0.03
    falling = price_change_5 < -0.03
    flat = abs(price_change_5) < 0.01
    high_vol = vol_ratio > 1.2
    low_vol = vol_ratio < 0.8

    if mf_stage == "markup":
        # 拉升 → 需放量上涨确认
        if high_vol and rising:
            return "confirm", 0.30, f"放量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if falling:
            return "downgrade", 0.20, f"价跌，不配合拉升信号"
        if low_vol:
            return "downgrade", 0.20, f"缩量拉升，量价不配合（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "accumulation":
        # 吸筹 → 缩量筑底最佳
        if low_vol and flat:
            return "confirm", 0.30, f"缩量筑底（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if high_vol and falling:
            return "downgrade", 0.25, f"放量下跌，吸筹期走坏"
        if spring:
            return "upgrade", 0.25, "Wyckoff Spring确认吸筹"
        if falling:
            return "downgrade", 0.15, "价跌，可能吸筹失败"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "distribution":
        # 派发 → 放量滞涨或价跌
        if high_vol and (flat or falling):
            return "confirm", 0.30, f"放量滞涨/下跌（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if upthrust:
            return "confirm", 0.30, "Wyckoff Upthrust确认派发"
        if low_vol and rising:
            return "downgrade", 0.20, "缩量上涨，非典型派发"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "testing":
        # 试盘 → 价冲高+小幅回落是正常试盘
        return "confirm", 0.15, "试盘期量价中性"

    elif mf_stage == "markdown":
        # 砸盘 → 放量下跌确认
        if high_vol and falling:
            return "confirm", 0.30, f"放量下跌确认砸盘"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    return "confirm", 0.0, "未知主力阶段"

def _downgrade_stage(stage: str) -> str:
    """将阶段降一级。用于量价不配合主力信号时的保守处理。

    Note: "蓄势偏弱"下再无更低阶段可降，main_force "衰退"已是最差阶段。
    """
    mapping = {
        "主升": "蓄势偏强",
        "蓄势偏强": "蓄势",
        "蓄势": "蓄势偏弱",
        "派发": "蓄势偏弱",
    }
    return mapping.get(stage, stage)

def _upgrade_stage(stage: str) -> str:
    """将阶段升一级。用于 Wyckoff 等信号增强确认时。"""
    mapping = {
        "蓄势": "蓄势偏强",
        "蓄势偏强": "主升",
        "蓄势偏弱": "蓄势偏强",  # 蓄势偏弱跳一级到蓄势偏强
    }
    return mapping.get(stage, stage)

def _detect_major_stage(
    current: float,
    ma_values: dict[str, float | None],
    bars: list[dict[str, Any]] | None = None,
    fusion_hint: dict[str, Any] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    chan_result: dict[str, Any] | None = None,
    main_force_result: dict[str, Any] | None = None,
) -> tuple[str, float, str, str]:
    """主力行为三层架构判定大阶段。

    第一层：主力行为主判定（60%） — main_force 五阶段映射
    第二层：量价确认（30%） — 验证主力信号真伪
    第三层：结构兜底（10%） — 主力数据不可用时使用量价启发式

    All new params default None for backward compatibility.

    Args:
        current: 当前价格
        ma_values: 均线值字典（保留用于兜底兼容）
        bars: K线数据
        fusion_hint: 已废弃（兼容入参）；fusion 仅仪表，不得微调 major_stage
        wyckoff_result: 威科夫分析结果
        chan_result: 缠论分析结果（兜底保留，当前未使用）
        main_force_result: 主力行为分析结果

    Returns:
        (stage, confidence, reason, vp_stage)
    """
    # 始终计算量价评估供 vp_stage 兼容 + 兜底
    vp_stage, vp_score, vp_reason = _assess_volume_price(bars, wyckoff_result=wyckoff_result)

    # ── 第一步：主力行为主判定 ──
    mf_stage, mf_conf, mf_reason = _detect_main_force_stage(main_force_result)

    if mf_stage is not None:
        # ── 第二步：量价确认（用原始英文 stage 匹配）──
        raw_mf_stage = main_force_result.get("stage", "unknown") if isinstance(main_force_result, dict) else "unknown"
        confirm_action, confirm_conf, confirm_reason = _volume_price_confirm(
            raw_mf_stage, bars, wyckoff_result
        )

        if confirm_action == "confirm":
            final_stage = mf_stage
            confidence = min(100, int(mf_conf + 30 * confirm_conf))
            reason = f"主力:{mf_reason} | 量价确认:{confirm_reason}"
        elif confirm_action == "downgrade":
            final_stage = _downgrade_stage(mf_stage)
            confidence = int(mf_conf * 0.6)
            reason = f"主力:{mf_reason} | 量价不符，降级:{confirm_reason}"
        elif confirm_action == "upgrade":
            final_stage = _upgrade_stage(mf_stage)
            confidence = min(100, mf_conf + 15)
            reason = f"主力:{mf_reason} | Wyckoff增强:{confirm_reason}"
        else:
            final_stage = mf_stage
            confidence = mf_conf
            reason = mf_reason

        # fusion_hint 已废弃：fusion 仅仪表，不得用 weighted_score 微调 major_stage
        _ = fusion_hint
    else:
        # ── 第三步：结构兜底 — 量价启发式 ──
        final_stage = vp_stage
        confidence = vp_score
        reason = f"量价兜底:{vp_reason}"

    return final_stage, confidence, reason, vp_stage

def _detect_short_term_momentum(
    current: float,
    expma10: float | None,
    expma20: float | None,
    change_pct: float,
    position_ratio: float,
) -> tuple[str, str]:
    """判定短期动能：走强/修复/震荡/转弱"""
    if expma10 is None or expma20 is None:
        return "震荡", "EXPMA数据不足"

    dist_to_expma20 = (current - expma20) / max(expma20, 1)

    # 走强 (Strong)：现价站上 EXPMA(10) 且 EXPMA(10) > EXPMA(20)
    if current >= expma10 and expma10 > expma20:
        return "走强", "站上EXPMA(10)且多头排列"

    # 均线粘合优先判断为震荡（需在修复之前，避免粘合期误报修复）
    if abs(expma10 - expma20) / max(expma20, 1) < 0.01:
        return "震荡", "EXPMA均线粘合"

    # 修复 (Recovery)：现价在 EXPMA(10) 与 EXPMA(20) 之间
    if min(expma10, expma20) <= current < max(expma10, expma20):
        return "修复", "回踩生命线(EXPMA10/20之间)"

    if current < expma20:
        if change_pct < -2.0 or expma10 < expma20:
            return "转弱", "跌破EXPMA(20)且走势破位"
        if abs(dist_to_expma20) < 0.03:
            return "震荡", "跌破EXPMA(20)但距离不远"
        return "转弱", "跌破EXPMA(20)且偏离较大"

    return "震荡", "走势未匹配极强/极弱特征"

def _layer1_multi_day_confirm(
    raw_stage: str,
    state: dict[str, Any],
    trade_date: str = "",
    price_change_5: float = 0.0,
) -> tuple[str, bool]:
    """第一层：多日确认。默认连续 3 日信号一致才确认阶段转换。
    但当近5日涨幅>5%时，只需1天确认（避免强势突破被死板规则拖住）。

    Returns:
        (confirmed_stage, is_transition)
    """
    prev_stage = state.get("last_confirmed_stage", "蓄势")
    pending_stage = state.get("pending_stage", "")
    pending_count = state.get("pending_count", 0)
    pending_date = state.get("pending_date", "")

    # 强势突破时降低确认天数
    required_days = 1 if price_change_5 > 0.05 else 3

    if raw_stage == prev_stage:
        # 信号一致，重置 pending
        return prev_stage, False

    if not trade_date:
        # 降级模式：trade_date 为空时直接返回原始阶段，不触发转换
        state["pending_stage"] = ""
        state["pending_count"] = 0
        state["pending_date"] = ""
        return raw_stage, False

    if raw_stage == pending_stage:
        # 连续相同的非当前信号 — 按交易日计数
        if trade_date == pending_date:
            # 同一天：如果已满确认天数，直接确认；否则不递增
            if pending_count >= required_days:
                return raw_stage, True
            return prev_stage, False
        # 新交易日，递增
        pending_count += 1
        if pending_count >= required_days:
            # 确认转换
            return raw_stage, True
        # 还没到确认天数，保持当前阶段
        state["pending_count"] = pending_count
        state["pending_date"] = trade_date
        return prev_stage, False
    else:
        # 新的非当前信号，重新计数
        state["pending_stage"] = raw_stage
        state["pending_count"] = 1
        state["pending_date"] = trade_date
        return prev_stage, False

def _layer2_confidence_gate(
    stage: str,
    confidence: int,
    state: dict[str, Any],
    vp_stage: str = "",
) -> tuple[str, int]:
    """第二层：置信度评分。< 35% 保持上次阶段，但量价明确判主升/衰退时不拦截。

    Returns:
        (final_stage, final_confidence)
    """
    if confidence < 35:
        # 量价维度明确判主升或衰退时，信任量价信号（不被置信度门控拦截）
        if vp_stage in ("主升", "衰退"):
            return stage, max(confidence, 40)
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, confidence
    return stage, confidence

def _layer3_cross_validation(
    stage: str,
    chan_result: dict[str, Any] | None,
    momentum_result: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """第三层：缠论+动量交叉验证。冲突时降级。

    Returns:
        (final_stage, conflict_note)
    """
    if chan_result is None and momentum_result is None:
        return stage, None

    # 缠论冲突检查
    if chan_result and isinstance(chan_result, dict):
        chan = chan_result.get("chanlun", {})
        if isinstance(chan, dict):
            divergence = chan.get("divergence", {})
            if stage == "主升" and divergence.get("top_divergence"):
                return "派发", "缠论顶背离与主升冲突，降级为派发"
            if stage == "衰退" and divergence.get("bottom_divergence"):
                return "蓄势", "缠论底背离与衰退冲突，降级为蓄势"

    # 动量冲突检查
    if momentum_result and isinstance(momentum_result, dict):
        mom = momentum_result.get("momentum", {})
        if isinstance(mom, dict):
            direction = mom.get("direction", "neutral")
            if stage == "主升" and direction == "bearish":
                return "派发", "动量看空与主升冲突，降级为派发"
            if stage == "衰退" and direction == "bullish":
                return "蓄势", "动量看多与衰退冲突，降级为蓄势"

    return stage, None

def _layer4_stage_lock(
    stage: str,
    state: dict[str, Any],
    is_transition: bool,
) -> tuple[str, bool]:
    """第四层：阶段锁定期。转换后锁定 3 天（从 5 天降低，避免错过波段窗口）。

    Returns:
        (final_stage, is_locked)
    """
    lock_remaining = state.get("lock_remaining", 0)

    if is_transition:
        # 新转换，设置锁定期（从 5 天降低到 3 天）
        state["lock_remaining"] = 3
        return stage, True

    if lock_remaining > 0:
        # 锁定期内
        state["lock_remaining"] = lock_remaining - 1
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, True

    return stage, False

def compute_position_with_env(
    stage: str,
    momentum: str,
    market_env: str = "震荡市",
    pnl_pct: float = 0.0,
    total_position_pct: float = 0.0,
) -> dict[str, Any]:
    """根据阶段+大盘环境计算建议仓位。

    Returns:
        {
            "stage_position_pct": int,   # 阶段仓位
            "env_limit_pct": int,        # 大盘环境单票上限
            "total_limit_pct": int,      # 大盘环境总仓位上限
            "suggested_pct": int,        # 建议仓位（取较小值）
            "market_env": str,
            "hard_rule_blocked": bool,   # 硬规则阻止
            "hard_rule_reason": str,
        }
    """
    # 阶段仓位
    stage_pct = _DECISION_MATRIX.get(stage, {}).get(momentum, ("观察", 0))[1]

    # 大盘环境限制
    env = _ENV_LIMITS.get(market_env, _ENV_LIMITS["震荡市"])
    single_limit = env["single"]
    total_limit = env["total"]

    # 硬规则检查（收集所有触发的原因）
    hard_blocked = False
    hard_reasons: list[str] = []

    if pnl_pct < 0:
        hard_blocked = True
        hard_reasons.append("持仓亏损，禁止加仓")

    if stage == "衰退":
        hard_blocked = True
        hard_reasons.append("衰退期，禁止建仓")

    if total_position_pct >= total_limit:
        hard_blocked = True
        hard_reasons.append(f"总仓位 {total_position_pct}% 已达上限 {total_limit}%")

    # 合并原因为字符串
    hard_reason = "；".join(hard_reasons) if hard_reasons else ""

    # 建议仓位
    if hard_blocked:
        suggested = 0
    else:
        suggested = min(stage_pct, single_limit)

    return {
        "stage_position_pct": stage_pct,
        "env_limit_pct": single_limit,
        "total_limit_pct": total_limit,
        "suggested_pct": suggested,
        "market_env": market_env,
        "hard_rule_blocked": hard_blocked,
        "hard_rule_reason": hard_reason,
    }

def action_for_holding_state(
    fusion_action: str,
    has_position: bool,
) -> dict[str, str]:
    """根据持仓状态给 fusion action 加场景标签，消除与 suggested_pct 的互斥。

    当 fusion action 说「减仓」但 suggested_pct=0（未持仓）时，
    两个语义互斥：减仓的前提是你有仓位才能减。
    此函数通过 holding_hint 明确场景，让 AI 渲染时不再同框打架。

    Returns:
        {
            "action": str,        # 原始 action 保留
            "holding_hint": str,  # 场景化提示（显示给用户/AI）
        }
    """
    action = str(fusion_action).strip()

    if action in _REDUCE_ACTIONS:
        if has_position:
            return {"action": action, "holding_hint": "已有仓位者执行减仓/止损"}
        return {"action": action, "holding_hint": "未持仓者不参与，无仓可减"}

    if action in _ADD_ACTIONS:
        if has_position:
            return {"action": action, "holding_hint": "已有仓位者按 suggested_pct 加仓"}
        return {"action": action, "holding_hint": "未持仓者按 suggested_pct 建仓"}

    # 持股观望 / 等转强观察 / 观望(信号冲突) 等
    return {"action": action, "holding_hint": "观望等待，不操作"}

def assess_stage(
    current: float,
    ma_values: dict[str, float | None],
    change_pct: float,
    bars: list[dict[str, Any]] | None = None,
    position_ratio: float = 0.5,
    chan_result: dict[str, Any] | None = None,
    momentum_result: dict[str, Any] | None = None,
    support: float = 0.0,
    pnl_pct: float = 0.0,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
    fib_retrace: dict[str, Any] | None = None,
    symbol: str = "",
    trade_date: str = "",
    fusion_hint: dict[str, Any] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    main_force_result: dict[str, Any] | None = None,
    extend_sector: dict[str, Any] | None = None,  # Phase 2: 行业板块数据交叉验证 (A6)
    chip_support_lower: float = 0.0,
    chip_resistance_lower: float = 0.0,
    chip_resistance_upper: float = 0.0,
    major_stage_seed: tuple | None = None,
) -> dict[str, Any]:
    """四阶段定位主函数（主力行为驱动 + 量价确认 + 四层防护）

    Returns:
        {
            "major_stage": str,       # 日线四阶段：蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退
            "major_reason": str,
            "momentum": str,          # short_term_momentum：走强/修复/震荡/转弱（EXPMA）
            "momentum_reason": str,
            "action": str,            # 操作建议
            "max_position_pct": int,  # 最大仓位百分比
            "stage_label": str,       # "蓄势期 + 修复"
            "confidence": int,        # 阶段置信度 0-100
            "protection_notes": list, # 四层防护触发说明
            "stop_losses": dict,
        }

    命名纪律（非本函数产出）：面板「阶段：」= midline_stage（周线威科夫）；
    report["stage"] 别名 short_term_momentum=momentum；勿与 major_stage 混用。
    """
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")
    ma20 = ma_values.get("ma20")

    # 第一步：综合阶段判定（主力行为优先 + 量价确认 + 结构兜底）
    # build_report 可传入 structure_stage 已算好的 seed，避免同票双算
    if (
        isinstance(major_stage_seed, tuple)
        and len(major_stage_seed) >= 4
        and major_stage_seed[0]
    ):
        raw_stage = str(major_stage_seed[0])
        try:
            raw_confidence = float(major_stage_seed[1])
        except (TypeError, ValueError):
            raw_confidence = 50.0
        raw_reason = str(major_stage_seed[2] or "")
        vp_stage = str(major_stage_seed[3] or "")
    else:
        raw_stage, raw_confidence, raw_reason, vp_stage = _detect_major_stage(
            current, ma_values, bars, fusion_hint=fusion_hint, wyckoff_result=wyckoff_result,
            chan_result=chan_result, main_force_result=main_force_result,
        )

    # P1 Fix: 新股置信度打折 — 当数据不足 60 天时，置信度按比例折扣
    new_stock_warning = ""
    if bars and len(bars) < 60:
        discount = len(bars) / 60.0
        raw_confidence = int(raw_confidence * discount)
        new_stock_warning = f"新股数据不足（{len(bars)}天），置信度打折"

    # 防护说明列表需先于 A6 板块交叉验证块初始化（避免 UnboundLocalError）
    protection_notes: list[str] = []

    # ── [Phase 2 - A6] 板块数据交叉验证 ──
    # 个股强弱 与 板块强弱 共振/背离，用于升级确认或减分。
    # 仅在板块数据 status == "正常" 时接入，缺失时退化为原行为。
    if extend_sector and isinstance(extend_sector, dict) and extend_sector.get("status") == "正常":
        sec_chg = safe_float(extend_sector, "sector_change_pct")
        if change_pct > 0 and sec_chg > 0:
            # 个股走强 + 板块走强 → 共振 → 升级确认
            if raw_stage in ("蓄势偏弱", "蓄势", "蓄势偏强"):
                raw_stage = _upgrade_stage(raw_stage)
                raw_confidence = min(100, raw_confidence + 10)
                protection_notes.append(f"板块共振走强（{sec_chg:+.1f}%），阶段升级确认")
        elif change_pct < 0 and sec_chg > 0:
            # 个股走弱 + 板块走强 → 背离 → 减分存疑
            raw_confidence = max(0, raw_confidence - 10)
            protection_notes.append(f"个股走弱但板块走强（{sec_chg:+.1f}%），阶段判定存疑减分")

    # 加载阶段状态
    state = _load_stage_state(symbol=symbol)

    # P1 Fix: 新股数据不足警告
    if new_stock_warning:
        protection_notes.append(new_stock_warning)

    # Fix A4: 实际执行顺序：层2(置信度) → 层1(多日确认) → 层3(交叉验证) → 层4(锁定)
    # 逻辑合理：先过滤低置信信号，再做多日确认，注释编号之前写反了

    # 置信度门控（先于多日确认，过滤噪音信号）
    gated_stage, gated_confidence = _layer2_confidence_gate(raw_stage, raw_confidence, state, vp_stage=vp_stage)
    if gated_stage != raw_stage:
        protection_notes.append(f"置信度{raw_confidence}%<35%，保持{gated_stage}")

    # 多日确认（在置信度过滤之后，确认阶段转换真实性）
    # 计算5日涨幅，强势时降低确认天数
    _price_change_5 = 0.0
    if bars and len(bars) >= 5:
        try:
            _c5 = float(bars[-5].get("close") or 0)
            _cend = float(bars[-1].get("close") or 0)
            if _c5 > 0:
                _price_change_5 = (_cend - _c5) / _c5
        except (TypeError, ValueError):
            pass
    confirmed_stage, is_transition = _layer1_multi_day_confirm(
        gated_stage, state, trade_date=trade_date, price_change_5=_price_change_5
    )
    if confirmed_stage != gated_stage:
        _req = 1 if abs(_price_change_5) > 0.05 else 3
        protection_notes.append(f"多日确认中（{state.get('pending_count', 0)}/{_req}）")

    # 第三层：交叉验证
    validated_stage, conflict_note = _layer3_cross_validation(
        confirmed_stage, chan_result, momentum_result
    )
    if conflict_note:
        protection_notes.append(conflict_note)

    # 第四层：阶段锁定期
    final_stage, is_locked = _layer4_stage_lock(validated_stage, state, is_transition)
    if is_locked:
        protection_notes.append(f"阶段锁定3天")
        if final_stage != validated_stage:
            protection_notes.append(f"锁定期内保持{final_stage}")

    # 保存状态
    if is_transition:
        state["last_confirmed_stage"] = final_stage
        state["pending_stage"] = ""
        state["pending_count"] = 0
        state["pending_date"] = ""
    _save_stage_state(state, symbol=symbol)

    # 短期动能判定
    expma10 = ma_values.get("expma10")
    expma20 = ma_values.get("expma20")
    momentum, momentum_reason = _detect_short_term_momentum(
        current, expma10, expma20, change_pct, position_ratio
    )

    # 决策矩阵
    action, max_position = _DECISION_MATRIX.get(final_stage, {}).get(
        momentum, ("观察", 0)
    )

    # 黄金坑共振验证 (Golden Bid Resonance)
    if fib_retrace and "golden_bid" in fib_retrace and fib_retrace["golden_bid"] is not None:
        golden_bid = float(fib_retrace["golden_bid"])
        # Check if EXPMA(10) or EXPMA(20) is near golden_bid (e.g. within 1.5%)
        expma_vals = [v for v in (expma10, expma20) if v is not None]
        if expma_vals:
            for expma_val in expma_vals:
                if golden_bid > 0 and abs(expma_val - golden_bid) / golden_bid <= 0.015:
                    action = "🌟黄金共振加仓"
                    # 黄金共振：EXPMA支撑与Golden Bid重合，强力信号
                    # 拔高至 80% 作为最大建议仓位（实际仓位由 compute_position_with_env 根据大盘环境截断）
                    max_position = 80
                    protection_notes.append("触发黄金共振（EXPMA与Golden Bid重合）")
                    break

    stage_label = f"{final_stage}期 + {momentum}"

    # 硬规则同步: 亏损/衰退期 → action 强制改为"不碰"，position 归零
    if pnl_pct < 0 and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0
        stage_label = f"{final_stage}期 + {momentum}（亏损不加仓）"
    elif final_stage == "衰退" and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0

    # 三层止损体系
    stop_losses = compute_stop_losses(
        stage=final_stage,
        current=current,
        support=support,
        ma20=ma20,
        bars=bars,
        atr14=atr14,
        chip_migration=chip_migration,
        chip_support_lower=chip_support_lower,
    )

    return {
        "major_stage": final_stage,
        "major_reason": raw_reason,
        "momentum": momentum,
        "momentum_reason": momentum_reason,
        "action": action,
        "max_position_pct": max_position,
        "stage_label": stage_label,
        "confidence": gated_confidence,
        "protection_notes": protection_notes,
        "stop_losses": stop_losses,
    }
