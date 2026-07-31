"""Wyckoff phase state machine + persistence."""
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
    WYCKOFF_PHASE_PREMATURE_SPRING_PENALTY,
    WYCKOFF_PHASE_PREMATURE_UT_PENALTY,
    WYCKOFF_SCORE_PREMATURE_HALF,
)


# ── 共享工具：Spring 刺穿深度 / BC 高位过滤 ─────────────────────────


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
    _spring_breach_level,
    _scan_last_event,
)

_PHASE_ORDER = {
    "markdown": -4,           # 主跌（派发完成后）
    "distribution_d": -3,
    "distribution_c": -2,
    "distribution_a": -1,
    "none": 0,
    "accumulation_a": 1,
    "accumulation_b": 2,
    "accumulation_c": 3,
    "accumulation_d": 4,
    "markup": 5,              # 主升（积累完成后）
}

_WYCKOFF_PHASE_FILE = os.path.expanduser("~/.trader/wyckoff_phase.json")

def _scan_for_signal(
    bars: list[dict],
    detector_fn: Any,
    window: int = 15,
    step: int = 5,
    max_lookback_bars: int | None = None,
    tr_ctx: dict | None = None,
) -> bool:
    """在 bars 上滑动窗口运行检测器，找到任意窗口触发即返回 True。

    解决单次调用只能检测最近几根 K 线的问题——通过滑动窗口扫描历史。
    始终额外检查末尾窗口，避免 step>1 时漏掉最新信号。

    Args:
        max_lookback_bars: 限定只扫描最近 N 根 K 线（防历史幽灵信号），
                           如 30 表示只看 bars 的最后 30 根。
    """
    if max_lookback_bars is not None and len(bars) > max_lookback_bars:
        bars = bars[-max_lookback_bars:]
    n = len(bars)
    def _call_detector(sub: list[dict]) -> dict:
        """统一关键字传 tr_ctx（与 _scan_last_event 一致）。

        Spring/SOW 第二位置参是 _support，位置传 tr_ctx 会错塞；
        compression 等无 tr_ctx 形参时 TypeError → 回退无参调用。
        """
        if tr_ctx is None:
            return detector_fn(sub)
        try:
            return detector_fn(sub, tr_ctx=tr_ctx)
        except TypeError:
            return detector_fn(sub)

    if n < window:
        # 数据不足整窗时，仍尝试整段 bars（兼容短序列末尾信号）
        try:
            result = _call_detector(bars)
            for key in result:
                if key.endswith("_signal") and result[key] is True:
                    return True
        except Exception:
            pass
        return False

    starts = list(range(0, n - window + 1, step))
    last_start = n - window
    if last_start not in starts:
        starts.append(last_start)

    for start in starts:
        sub = bars[start:start + window]
        try:
            result = _call_detector(sub)
            for key in result:
                if key.endswith("_signal") and result[key] is True:
                    return True
        except Exception:
            continue
    return False

def _detect_phase(bars: list[dict], signals: dict[str, Any], _phase_lookback: int | None = None, tr_ctx: dict | None = None) -> dict[str, Any]:
    """基于信号序列推断威科夫阶段（积累 Phase A-E / 派发 Phase A'-E'）。

    原典约束（五阶段机串联）：
      - Spring/Upthrust 必须出现在 Phase B（停止后建仓区）之后才有效（C 阶段）。
      - 孤立 Spring（早于 B、或完全无 B 背景）→ spring_premature=True，判噪声，不赋积累阶段。
      - 孤立 Upthrust（早于 B、或完全无 B 背景）→ upthrust_premature=True，判噪声，不赋派发阶段。

    Args:
        _phase_lookback: 覆盖 WYCKOFF_PHASE_LOOKBACK（用于周线缩比）

    Returns:
        {"phase": str, "phase_label": str, "phase_confidence_delta": float,
         "spring_premature": bool, "upthrust_premature": bool}
        phase_confidence_delta: 阶段上下文对当前信号置信度的修正
        spring_premature/upthrust_premature: Spring/UT 是否为孤立信号（无 Phase B 背景）
    """
    lookback = min(_phase_lookback if _phase_lookback is not None else WYCKOFF_PHASE_LOOKBACK, len(bars))
    wide_bars = bars[-lookback:]

    # 当前 bar 信号优先（避免 scan step 漏检末尾），再滑动扫描历史窗口
    bc_found = bool(signals.get("bc_signal")) or _scan_for_signal(
        wide_bars, _detect_buying_climax, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    ar_found = bool(signals.get("ar_signal")) or _scan_for_signal(
        wide_bars, _detect_ar, window=18, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    ut_found = bool(signals.get("upthrust_signal")) or _scan_for_signal(
        wide_bars, _detect_upthrust, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    sow_found = bool(signals.get("sow_signal")) or _scan_for_signal(
        wide_bars, _detect_sign_of_weakness, window=16, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    # 新增：SC（卖力高潮）和 LPSY（最后供应点）扫描
    sc_found = bool(signals.get("sc_signal")) or _scan_for_signal(
        wide_bars, _detect_selling_climax, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    lpsy_found = bool(signals.get("lpsy_signal")) or _scan_for_signal(
        wide_bars, _detect_lpsy, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )

    # 后期信号：当前 bar + 滑窗扫描（P1-3 修复：让经典积累链可被阶段机识别）
    spring = bool(signals.get("spring_signal")) or _scan_for_signal(
        wide_bars, _detect_spring, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    sos = bool(signals.get("sos_signal")) or _scan_for_signal(
        wide_bars, _detect_sos, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    lps = bool(signals.get("lps_signal")) or _scan_for_signal(
        wide_bars, _detect_lps, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    compression = bool(signals.get("compression_signal")) or _scan_for_signal(
        wide_bars, _detect_compression, window=20, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )
    trend_pullback = bool(signals.get("trend_pullback_signal")) or _scan_for_signal(
        wide_bars, _detect_trend_pullback, window=15, step=5, max_lookback_bars=30, tr_ctx=tr_ctx
    )

    # ── 原典顺序校验：事件索引 — Spring/UT 必须在 Phase B 之后才有效 ────────
    # 计算各事件在 wide_bars 中的最后触发索引（若索引数组已排序则取最后出现位置）
    spring_idx, _ = _scan_last_event(wide_bars, _detect_spring, tr_ctx, window=15, step=1)
    ut_idx, _ = _scan_last_event(wide_bars, _detect_upthrust, tr_ctx, window=15, step=1)
    sc_idx, _ = _scan_last_event(wide_bars, _detect_selling_climax, tr_ctx, window=15, step=1)
    bc_idx, _ = _scan_last_event(wide_bars, _detect_buying_climax, tr_ctx, window=15, step=1)
    ar_idx, _ = _scan_last_event(wide_bars, _detect_ar, tr_ctx, window=18, step=1)
    comp_idx, _ = _scan_last_event(wide_bars, _detect_compression, tr_ctx, window=20, step=1)

    # Phase B（建仓区）背景：
    #   积累：SC+AR（原典 Automatic Rally）或压缩蓄力
    #   派发（⑥B）：不再用 BC+AR（AR 已只绑 SC）；改靠 BC+(压缩/SOW) 或压缩蓄力
    # 判断来源：bar 索引（_scan_last_event）+ signals dict（信号覆盖）双源合并
    sc_ar_b_ctx = (sc_idx >= 0 and ar_idx >= 0) or \
                  (signals.get("sc_signal") and signals.get("ar_signal"))
    has_compression = comp_idx >= 0 or signals.get("compression_signal")
    bc_dist_b_ctx = (
        (bc_idx >= 0 and (comp_idx >= 0 or sow_found))
        or (
            signals.get("bc_signal")
            and (signals.get("compression_signal") or signals.get("sow_signal"))
        )
    )
    acc_b_ctx = sc_ar_b_ctx or has_compression           # 积累 B 背景
    dist_b_ctx = bc_dist_b_ctx or has_compression        # 派发 B 背景

    # Spring/UT 有效性（孤立性校验）：
    #   spring_idx>=0：有 bar 位置 → 在 B 背景之后才算有效
    #   spring_idx=-1 但信号来自 signals dict → 看 B 背景是否存在（保守判断）
    if spring_idx >= 0:
        acc_b_ctx_idx = max(sc_idx, ar_idx, comp_idx)
        spring_premature = not (acc_b_ctx and spring_idx > acc_b_ctx_idx)
    elif spring:
        spring_premature = not acc_b_ctx
    else:
        spring_premature = False

    if ut_idx >= 0:
        dist_b_ctx_idx = max(bc_idx, comp_idx)
        upthrust_premature = not (dist_b_ctx and ut_idx > dist_b_ctx_idx)
    elif ut_found:
        upthrust_premature = not dist_b_ctx
    else:
        upthrust_premature = False

    # ── Markup / Markdown（E 后主升/主跌标签）──
    last_close = signals.get("last_close")
    tr_upper = signals.get("tr_upper")
    bu = bool(signals.get("bu_signal"))
    utad = bool(signals.get("utad_signal"))
    # Markup：积累 D 确认后 + 站上 TR 上沿，或 BU（SOS 后备份买）
    if (not spring_premature and spring and (sos or lps)) or bu:
        if bu or (
            last_close is not None
            and tr_upper is not None
            and float(last_close) > float(tr_upper)
            and sos
        ):
            return {
                "phase": "markup",
                "phase_label": "主升 Markup（离开积累区）",
                "phase_confidence_delta": 0.12,
                "spring_premature": False,
                "upthrust_premature": upthrust_premature,
            }
    # Markdown：派发确认后跌破 / UTAD+SOW
    if utad or (not upthrust_premature and ut_found and sow_found):
        tr_lower = (tr_ctx or {}).get("tr_lower") if tr_ctx else None
        if utad or (
            last_close is not None
            and tr_lower is not None
            and float(last_close) < float(tr_lower)
        ):
            return {
                "phase": "markdown",
                "phase_label": "主跌 Markdown（离开派发区）",
                "phase_confidence_delta": -0.12,
                "spring_premature": spring_premature,
                "upthrust_premature": False if ut_found else upthrust_premature,
            }

    # ── 积累序列（原典：A停止→B建仓→C弹簧→D确认→E趋势） ──
    # Spring 必须先经 Phase B（有 SC+AR 停止行为或压缩蓄力）才有效
    if not spring_premature and spring and (sos or lps):
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+SOS/LPS）",
            "phase_confidence_delta": 0.10,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
        }
    if not spring_premature and spring and trend_pullback:
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+趋势回踩）",
            "phase_confidence_delta": 0.12,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
        }
    if not spring_premature and spring:
        return {
            "phase": "accumulation_c",
            "phase_label": "积累期 C（测试：Spring）",
            "phase_confidence_delta": 0.10,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
        }
    # P2: Compression = 积累期 B 末期（压缩蓄力）
    if compression:
        return {
            "phase": "accumulation_b",
            "phase_label": "积累期 B（压缩蓄力）",
            "phase_confidence_delta": 0.08,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    # P3: Trend Pullback = 积累期 D 趋势确认
    if trend_pullback:
        return {
            "phase": "accumulation_d",
            "phase_label": "积累期 D（趋势回踩确认）",
            "phase_confidence_delta": 0.08,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    # 新增：SC（卖力高潮）→ 积累期 A，正式识别停止行为
    if sc_found and ar_found:
        return {
            "phase": "accumulation_a",
            "phase_label": "积累期 A（停止：SC+AR）",
            "phase_confidence_delta": 0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    if sc_found:
        return {
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC）",
            "phase_confidence_delta": 0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    # AR 且无 BC/SC：可能是吸筹自动反弹
    if ar_found and not bc_found:
        return {
            "phase": "accumulation_b",
            "phase_label": "积累期 B（辅助：AR无BC）",
            "phase_confidence_delta": 0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }

    # ── 派发序列 ──
    # LPSY（最后供应点）→ 派发期 D；需要前置派发背景（BC/UT/SOW 至少一个）
    if lpsy_found and (bc_found or ut_found or sow_found):
        return {
            "phase": "distribution_d",
            "phase_label": "派发期 D（最后供应点：LPSY）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    # 无前置派发背景的孤立 LPSY → 可疑但不标派发 D
    if lpsy_found:
        return {
            "phase": "none",
            "phase_label": "无明确阶段（孤立 LPSY，缺派发背景）",
            "phase_confidence_delta": 0.0,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    # UT 必须先经 Phase B（BC+压缩/SOW 或压缩蓄力）才有效
    if not upthrust_premature and ut_found and sow_found:
        return {
            "phase": "distribution_c",
            "phase_label": "派发期 C（确认：UT+SOW）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": False,
        }
    # ⑥B：派发 A 加强靠 BC+压缩/SOW，不再用 BC+AR（AR 只服务积累）
    if bc_found and (has_compression or sow_found):
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（停止：BC+蓄势/弱势）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    if bc_found:
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（购买高潮：BC）",
            "phase_confidence_delta": -0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        }
    if not upthrust_premature and ut_found:
        return {
            "phase": "distribution_a",
            "phase_label": "派发期 A（上冲回落：UT）",
            "phase_confidence_delta": -0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": False,
        }

    # 孤立/过早 Spring 或 UT（无 Phase B 背景）、或完全无信号 → 无明确阶段
    # 但带 premature 标注，供 score 层降权使用
    reasons = []
    if spring_premature:
        reasons.append("Spring孤立/过早（缺Phase B背景）")
    if upthrust_premature:
        reasons.append("Upthrust孤立/过早（缺Phase B背景）")
    suffix = f"（{'；'.join(reasons)}）" if reasons else ""
    return {
        "phase": "none",
        "phase_label": f"无明确阶段{suffix}",
        "phase_confidence_delta": 0.0,
        "spring_premature": spring_premature,
        "upthrust_premature": upthrust_premature,
    }

def _phase_key(symbol: str, timeframe: str) -> str:
    """持久化键：按 symbol + 周期维度隔离，避免日线与中线共用同一键互相污染。"""
    return f"{symbol}::{timeframe}"

def _load_phase_state(symbol: str, timeframe: str = "daily") -> dict[str, Any] | None:
    """从持久化文件加载该标的在指定周期的 phase 状态。"""
    if not symbol:
        return None
    try:
        if os.path.exists(_WYCKOFF_PHASE_FILE):
            with open(_WYCKOFF_PHASE_FILE) as f:
                data = json.load(f)
            return data.get(_phase_key(symbol, timeframe))
    except (json.JSONDecodeError, OSError):
        pass
    return None

def _save_phase_state(symbol: str, timeframe: str, phase_state: dict[str, Any]) -> None:
    """将 phase 状态持久化到文件（按 symbol + 周期维度写）。"""
    if not symbol:
        return
    try:
        os.makedirs(os.path.dirname(_WYCKOFF_PHASE_FILE), exist_ok=True)
        data = {}
        if os.path.exists(_WYCKOFF_PHASE_FILE):
            try:
                with open(_WYCKOFF_PHASE_FILE) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {}
        data[_phase_key(symbol, timeframe)] = phase_state
        with open(_WYCKOFF_PHASE_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

def _transition_phase(
    old_phase_state: dict[str, Any] | None,
    new_phase: str,
    new_phase_label: str,
    new_confidence_delta: float,
) -> dict[str, Any]:
    """状态机：phase 平滑过渡，允许反向翻转。

    规则：
      - 无旧状态 → 直接使用新 phase
      - 新 phase 为 "none" → 维持旧状态（平滑，不抖动）
      - 同方向（同为积累或同为派发）→ 只升级不降级
      - 反方向（积累↔派发）→ 允许翻转（基于方向符号，不再限制白名单）
    """
    if old_phase_state is None:
        return {
            "phase": new_phase,
            "phase_label": new_phase_label,
            "phase_confidence_delta": new_confidence_delta,
            "first_seen": new_phase if new_phase != "none" else None,
        }

    old_phase = old_phase_state.get("phase", "none")
    old_order = _PHASE_ORDER.get(old_phase, 0)
    new_order = _PHASE_ORDER.get(new_phase, 0)
    first_seen = old_phase_state.get("first_seen")

    # 新 phase 无信号 → 保持旧状态
    if new_phase == "none":
        return {**old_phase_state, "phase_confidence_delta": 0.0}

    # 旧 phase 也是 "none" → 直接升级
    if old_phase == "none":
        return {
            "phase": new_phase,
            "phase_label": new_phase_label,
            "phase_confidence_delta": new_confidence_delta,
            "first_seen": new_phase,
        }

    # 同方向（同正或同负）：只升级不降级
    if (
        (old_order > 0 and new_order > 0)  # 积累
        or (old_order < 0 and new_order < 0)  # 派发
    ):
        if new_order <= old_order:
            # 信号弱于或持平当前 → 保持旧阶段，但更新 confidence
            return {**old_phase_state, "phase_confidence_delta": new_confidence_delta}
        # 升级
        return {
            "phase": new_phase,
            "phase_label": new_phase_label,
            "phase_confidence_delta": new_confidence_delta,
            "first_seen": first_seen or new_phase,
        }

    # 反方向：积累切派发或派发切积累 → 允许翻转（基于方向符号，不再限制白名单）
    # 修复「只进不退」：原 strong_flip 白名单排除 distribution_a/b、accumulation_b，
    # 导致清晰派发信号无法翻转积累阶段（报告 phase_label 黏住旧阶段）。
    if old_order * new_order < 0:
        return {
            "phase": new_phase,
            "phase_label": new_phase_label,
            "phase_confidence_delta": new_confidence_delta,
            "first_seen": new_phase,
        }

    # 反方向但符号判定异常 → 维持旧阶段
    return {**old_phase_state, "phase_confidence_delta": 0.0}
