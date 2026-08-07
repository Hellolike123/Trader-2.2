"""Wyckoff phase state machine + persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from trader_shared.light_data import to_float

# ── Wyckoff 常量（唯一来源：trader_shared.config） ----
from trader_shared.config import (
    WYCKOFF_MIN_BARS,
    WYCKOFF_CLIMAX_ANCHOR_BARS,
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
    WYCKOFF_PHASE_MIN_TR_QUALITY,
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
    _detect_are,
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
    _detect_trend_rally,
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

_P2_ACC_BLOCKED_WITHOUT_ESTABLISHED = frozenset({
    "accumulation_b",
    "accumulation_c",
    "accumulation_d",
    "markup",
})

_P2_FORMING_BLOCKED = _P2_ACC_BLOCKED_WITHOUT_ESTABLISHED | frozenset({
    "distribution_a",
    "distribution_b",
    "distribution_c",
    "distribution_d",
    "markdown",
})


def _tf_scan_params(
    timeframe: str,
    window: int,
    max_lookback_bars: int | None = None,
) -> tuple[int, int | None]:
    """阶段机滑窗尺寸：日线原值；周线半幅（``wyckoff-weekly-scan-windows-handoff`` §1.1）。

    周线叙事窗约 12 根；若仍用日线 window=15，``_scan_last_event`` 在 n<window 时系统性失效。
    半幅与 AR 周线缩放同族：``max(6, ceil(N/2))``。
    """
    if str(timeframe or "").lower() != "weekly":
        return int(window), max_lookback_bars
    w = max(6, (int(window) + 1) // 2)
    if max_lookback_bars is None:
        return w, None
    mlb = max(w, (int(max_lookback_bars) + 1) // 2)
    return w, mlb


def _apply_p2_phase_a_gates(
    result: dict[str, Any],
    phase_a_status: str,
    sc_found: bool,
) -> dict[str, Any]:
    """P2：无 established 种子箱时不得因分位 TR 抬升积累 B+；forming 仅允许 A（派发/markdown 亦闸）。"""
    out = dict(result)
    if "phase_tr_gated" not in out:
        out["phase_tr_gated"] = False
        out["phase_tr_gate_reason"] = ""

    if phase_a_status == "established":
        return out

    phase = out.get("phase", "none")
    blocked = (
        _P2_FORMING_BLOCKED
        if phase_a_status == "forming"
        else _P2_ACC_BLOCKED_WITHOUT_ESTABLISHED
    )
    if phase not in blocked:
        return out

    if phase_a_status == "forming" and sc_found:
        out.update({
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_confidence_delta": min(float(out.get("phase_confidence_delta") or 0.0), 0.05),
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "forming_phase_a",
        })
        return out

    out.update({
        "phase": "none",
        "phase_label": "无明确阶段（无 established 种子箱，阶段不参与定论）",
        "phase_confidence_delta": 0.0,
        "phase_tr_gated": True,
        "phase_tr_gate_reason": "no_established_seed",
    })
    return out

def _wyckoff_phase_path() -> Path:
    """``~/.trader/wyckoff_phase.json`` (via trader_paths).

    Tests may monkeypatch ``_WYCKOFF_PHASE_FILE`` to a custom path str/Path.
    """
    override = globals().get("_WYCKOFF_PHASE_FILE")
    if override:
        return Path(override)
    from trader_shared.trader_paths import path as trader_path
    return trader_path("wyckoff_phase")


# Backward-compat alias (None → use trader_paths); tests may monkeypatch.
_WYCKOFF_PHASE_FILE: str | Path | None = None

def _scan_for_signal(
    bars: list[dict],
    detector_fn: Any,
    window: int = 15,
    step: int = 5,
    max_lookback_bars: int | None = None,
    tr_ctx: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> bool:
    """在 bars 上滑动窗口运行检测器，找到任意窗口触发即返回 True。

    解决单次调用只能检测最近几根 K 线的问题——通过滑动窗口扫描历史。
    始终额外检查末尾窗口，避免 step>1 时漏掉最新信号。

    Args:
        max_lookback_bars: 限定只扫描最近 N 根 K 线（防历史幽灵信号），
                           如 30 表示只看 bars 的最后 30 根。
        timeframe / is_index: 透传给认周期的检测器（SC/AR 周线窗/阈值），
                              避免周线阶段机滑窗默默用日线参数（W-01）。
    """
    if max_lookback_bars is not None and len(bars) > max_lookback_bars:
        bars = bars[-max_lookback_bars:]
    n = len(bars)
    def _call_detector(sub: list[dict]) -> dict:
        """统一关键字传 tr_ctx + timeframe（与 _scan_last_event 一致）。

        Spring/SOW 第二位置参是 _support，位置传 tr_ctx 会错塞；
        无 timeframe/tr_ctx 形参时 TypeError → 逐级回退。
        """
        try:
            if tr_ctx is None:
                return detector_fn(sub, timeframe=timeframe, is_index=is_index)
            return detector_fn(
                sub, tr_ctx=tr_ctx, timeframe=timeframe, is_index=is_index
            )
        except TypeError:
            pass
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

def _detect_phase(
    bars: list[dict],
    signals: dict[str, Any],
    _phase_lookback: int | None = None,
    tr_ctx: dict | None = None,
    *,
    timeframe: str = "daily",
    is_index: bool = False,
) -> dict[str, Any]:
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
    # P-M2/P-M3：统一 SC 锚（wc 主流程经 phase_tr_ctx 注入，与 SC 灯同源）——
    # 有锚（dict）→ sc_found 恒 True、sc_idx 换算 wide_bars 偏移，不再滑窗重算 SC；
    # 无 sc_anchor 键 → 走原滑窗逻辑（向后兼容，孤立调用不受影响）。
    _unified_anchor = tr_ctx.get("sc_anchor") if isinstance(tr_ctx, dict) else None
    phase_a_status = (tr_ctx or {}).get("phase_a_status") or "none"

    if phase_a_status == "failed":
        return {
            "phase": "none",
            "phase_label": "无明确阶段（Phase A 失败，破位未收回）",
            "phase_confidence_delta": 0.0,
            "spring_premature": bool(signals.get("spring_signal")),
            "upthrust_premature": bool(signals.get("upthrust_signal")),
            "phase_tr_gated": True,
            "phase_tr_gate_reason": "phase_a_failed",
        }

    # P0-B + P2-A：低质量 / 无 TR → 事件可亮，阶段不抬升（forming 仍可到 A）
    tr_q = None
    if tr_ctx is not None and tr_ctx.get("tr_quality") is not None:
        try:
            tr_q = float(tr_ctx["tr_quality"])
        except (TypeError, ValueError):
            tr_q = None
    if tr_ctx is None or tr_q is None:
        gate_reason = "no_tr"
    elif tr_q < float(WYCKOFF_PHASE_MIN_TR_QUALITY):
        gate_reason = "low_quality"
    else:
        gate_reason = ""
    # P0-B 优先于 forming A（P2-R4：低质量 TR 时 forming 也不得抬到 accumulation_a）
    if gate_reason:
        label = (
            "无明确阶段（TR质量不足，阶段不参与定论）"
            if gate_reason == "low_quality"
            else "无明确阶段（无TR，阶段不参与定论）"
        )
        return {
            "phase": "none",
            "phase_label": label,
            "phase_confidence_delta": 0.0,
            "spring_premature": bool(signals.get("spring_signal")),
            "upthrust_premature": bool(signals.get("upthrust_signal")),
            "phase_tr_gated": True,
            "phase_tr_gate_reason": gate_reason,
        }

    # 当前 bar 信号优先（避免 scan step 漏检末尾），再滑动扫描历史窗口
    # 周线：window / max_lookback 半幅（S1；见 wyckoff-weekly-scan-windows-handoff）
    # P-M4：滑窗子窗口 ctx 剥掉 sc_anchor —— 锚是全序列索引，进子窗会让检测器
    # 短路返回后 bars[sc_bar_idx] 越界，异常被 _scan_for_signal 吞掉 → 静默无信号；
    # 阶段机门控（phase_a_status/tr_quality/tr_lower）继续读原 tr_ctx。
    _sub_ctx = (
        {k: v for k, v in tr_ctx.items() if k != "sc_anchor"}
        if isinstance(tr_ctx, dict)
        else None
    )
    _scan_kw = {"tr_ctx": _sub_ctx, "timeframe": timeframe, "is_index": is_index}

    def _scan(det, window: int, *, step: int = 5, max_lookback_bars: int | None = 30) -> bool:
        w, mlb = _tf_scan_params(timeframe, window, max_lookback_bars)
        return _scan_for_signal(
            wide_bars, det, window=w, step=step, max_lookback_bars=mlb, **_scan_kw
        )

    def _last(det, window: int) -> tuple[int, Any]:
        w, _ = _tf_scan_params(timeframe, window, None)
        return _scan_last_event(
            wide_bars, det, _sub_ctx, window=w, step=1, timeframe=timeframe, is_index=is_index
        )

    def _ar_verdict() -> tuple[bool | None, int | None]:
        """B 撕裂点收尾（AR 子窗锚统一，见 workflows/phase-scan-audit/ TP-1/TP-2）。

        统一锚存在（主流程注入）时：AR 只认「完整序列 SC 锚」之后的自动反弹——
        把统一锚 remap 进 wide_bars 局部索引后单次评估，不再对子窗重算 SC 锚。
        理由：P-M4 剥离 sc_anchor 后，子窗内 _detect_ar 会对**子窗**冷启动重算 SC，
        与主流程 AR 灯（完整序列锚）索引口径可能不同 → 同一批数据给出两个不同 SC，
        AR 信号被绑到与主流程 SC 不一致的历史 SC 上（历史定位语义撕裂）。
        SC 锚早于 lookback（remap 出界）→ 本窗无统一 AR，退化为 signals 判定。

        Returns:
            (found, idx) —— 统一锚路径：found=统一判定（已含 signals）、idx=wide_bars
            相对索引（无 AR 为 -1）；无锚（孤立调用，P-M3 兼容）：(None, None) →
            调用方回退原滑窗重算。
        """
        if _unified_anchor is None:
            return None, None
        offset = len(bars) - len(wide_bars)
        try:
            sc_full = int(_unified_anchor["sc_bar_idx"])
        except (TypeError, KeyError, ValueError):
            sc_full = -1
        local = sc_full - offset
        if not (0 <= local < len(wide_bars)):
            return bool(signals.get("ar_signal")), -1
        ar_ctx = {**_sub_ctx, "sc_anchor": {**_unified_anchor, "sc_bar_idx": local}}
        try:
            res = _detect_ar(wide_bars, tr_ctx=ar_ctx, timeframe=timeframe, is_index=is_index)
        except Exception:
            return bool(signals.get("ar_signal")), -1
        if res.get("ar_signal"):
            try:
                return True, int(res.get("ar_bar_idx") or -1)
            except (TypeError, ValueError):
                return True, -1
        return bool(signals.get("ar_signal")), -1

    bc_found = bool(signals.get("bc_signal")) or _scan(_detect_buying_climax, 15)
    ar_found, _ar_idx_unified = _ar_verdict()
    if _ar_idx_unified is None:
        # 无统一锚（孤立调用）：原滑窗重算（历史定位语义，P-M3 向后兼容）
        ar_found = bool(signals.get("ar_signal")) or _scan(
            _detect_ar, WYCKOFF_CLIMAX_ANCHOR_BARS + 3
        )
    are_found = bool(signals.get("are_signal")) or _scan(
        _detect_are, WYCKOFF_CLIMAX_ANCHOR_BARS + 3
    )
    ut_found = bool(signals.get("upthrust_signal")) or _scan(_detect_upthrust, 15)
    sow_found = bool(signals.get("sow_signal")) or _scan(_detect_sign_of_weakness, 16)
    # 新增：SC（卖力高潮）和 LPSY（最后供应点）扫描
    # P-M2：统一锚存在 → sc_found 恒 True（短路原 _scan SC 滑窗重算）；无锚 → 原逻辑（P-M3）
    if _unified_anchor is not None:
        sc_found = True
    else:
        sc_found = bool(signals.get("sc_signal")) or _scan(
            _detect_selling_climax, WYCKOFF_CLIMAX_ANCHOR_BARS
        )
    lpsy_found = bool(signals.get("lpsy_signal")) or _scan(_detect_lpsy, 15)

    def _finish(d: dict[str, Any]) -> dict[str, Any]:
        return _apply_p2_phase_a_gates(d, phase_a_status, sc_found)

    # 后期信号：当前 bar + 滑窗扫描（P1-3 修复：让经典积累链可被阶段机识别）
    spring = bool(signals.get("spring_signal")) or _scan(_detect_spring, 15)
    sos = bool(signals.get("sos_signal")) or _scan(_detect_sos, 15)
    lps = bool(signals.get("lps_signal")) or _scan(_detect_lps, 15)
    compression = bool(signals.get("compression_signal")) or _scan(_detect_compression, 20)
    trend_pullback = bool(signals.get("trend_pullback_signal")) or _scan(
        _detect_trend_pullback, 15
    )
    trend_rally = bool(signals.get("trend_rally_signal")) or _scan(_detect_trend_rally, 15)
    # Test of Spring（与 st_* 同源）
    spring_test = bool(
        signals.get("spring_test_signal") or signals.get("st_signal")
    ) or _scan(_detect_st, 20, max_lookback_bars=40)

    # ── 原典顺序校验：事件索引 — Spring/UT 必须在 Phase B 之后才有效 ────────
    # 计算各事件在 wide_bars 中的最后触发索引（若索引数组已排序则取最后出现位置）
    spring_idx, _ = _last(_detect_spring, 15)
    ut_idx, _ = _last(_detect_upthrust, 15)
    # P-M2：统一锚 → 全序列 sc_bar_idx 换算 wide_bars 偏移；换算结果不在
    # [0, len(wide_bars)) 内（持久化钉锚可能在 lookback 之外）→ -1（与原
    # 「滑窗未检出 SC」同义）；无锚 → 原 _last 滑窗（P-M3）
    if _unified_anchor is not None:
        try:
            sc_idx = int(_unified_anchor["sc_bar_idx"]) - (len(bars) - len(wide_bars))
        except (TypeError, KeyError, ValueError):
            sc_idx = -1  # 锚缺键/非法 → 与原「滑窗未检出 SC」同义（查 Agent SUGGESTED 1）
        if not (0 <= sc_idx < len(wide_bars)):
            sc_idx = -1
    else:
        sc_idx, _ = _last(_detect_selling_climax, WYCKOFF_CLIMAX_ANCHOR_BARS)
    bc_idx, _ = _last(_detect_buying_climax, WYCKOFF_CLIMAX_ANCHOR_BARS)
    if _ar_idx_unified is not None:
        ar_idx = _ar_idx_unified  # B 统一路径：wide_bars 相对索引，与 spring_idx 同空间
    else:
        ar_idx, _ = _last(_detect_ar, WYCKOFF_CLIMAX_ANCHOR_BARS + 3)
    are_idx, _ = _last(_detect_are, WYCKOFF_CLIMAX_ANCHOR_BARS + 3)
    comp_idx, _ = _last(_detect_compression, 20)

    # Phase B（建仓区）背景：
    #   积累：SC+AR（原典 Automatic Rally）或压缩蓄力
    #   派发：BC+ARE（Automatic Reaction）或 BC+(压缩/SOW) 或压缩蓄力
    # 判断来源：bar 索引（_scan_last_event）+ signals dict（信号覆盖）双源合并
    sc_ar_b_ctx = (sc_idx >= 0 and ar_idx >= 0) or \
                  (signals.get("sc_signal") and signals.get("ar_signal"))
    has_compression = comp_idx >= 0 or signals.get("compression_signal")
    bc_are_b_ctx = (bc_idx >= 0 and are_idx >= 0) or \
                   (signals.get("bc_signal") and signals.get("are_signal"))
    bc_dist_b_ctx = (
        bc_are_b_ctx
        or (bc_idx >= 0 and (comp_idx >= 0 or sow_found))
        or (
            signals.get("bc_signal")
            and (signals.get("compression_signal") or signals.get("sow_signal"))
        )
    )
    acc_b_ctx = sc_ar_b_ctx or has_compression           # 积累 B 背景
    dist_b_ctx = bc_dist_b_ctx or has_compression        # 派发 B 背景

    # Spring/UT 有效性（孤立性校验）— P0-2：
    #   B 背景只认「严格早于事件」完成的路径；事件之后的 compression 不得把真 Spring/UT 判 premature。
    #   spring_idx=-1 但信号来自 signals dict → 看 B 背景是否存在（兼容注入测）
    if spring_idx >= 0:
        prior_b: list[int] = []
        if (
            sc_idx >= 0
            and ar_idx >= 0
            and sc_idx < spring_idx
            and ar_idx < spring_idx
        ):
            prior_b.append(max(sc_idx, ar_idx))
        if comp_idx >= 0 and comp_idx < spring_idx:
            prior_b.append(comp_idx)
        if prior_b:
            spring_premature = False
        elif acc_b_ctx and sc_idx < 0 and ar_idx < 0 and comp_idx < 0:
            spring_premature = False  # 仅 signals 布尔、无扫描索引
        else:
            spring_premature = True
    elif spring:
        spring_premature = not acc_b_ctx
    else:
        spring_premature = False

    if ut_idx >= 0:
        prior_dist_b: list[int] = []
        if (
            bc_idx >= 0
            and are_idx >= 0
            and bc_idx < ut_idx
            and are_idx < ut_idx
        ):
            prior_dist_b.append(max(bc_idx, are_idx))
        # BC + (compression|SOW 索引侧) 在 UT 前；SOW 无稳定 idx 时靠 dist_b_ctx+bc
        if bc_idx >= 0 and bc_idx < ut_idx and (comp_idx >= 0 and comp_idx < ut_idx):
            prior_dist_b.append(max(bc_idx, comp_idx))
        if comp_idx >= 0 and comp_idx < ut_idx:
            prior_dist_b.append(comp_idx)
        if prior_dist_b:
            upthrust_premature = False
        elif dist_b_ctx and bc_idx < 0 and are_idx < 0 and comp_idx < 0:
            upthrust_premature = False
        elif (
            dist_b_ctx
            and bc_idx >= 0
            and bc_idx < ut_idx
            and sow_found
            and (are_idx < 0 or are_idx < ut_idx)
        ):
            # BC+SOW 派发 B（无 are/comp 索引）
            upthrust_premature = False
        else:
            upthrust_premature = True
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
            return _finish({
                "phase": "markup",
                "phase_label": "主升 Markup（离开积累区）",
                "phase_confidence_delta": 0.12,
                "spring_premature": False,
                "upthrust_premature": upthrust_premature,
            })
    # Markdown：派发确认后跌破 / UTAD+SOW
    if utad or (not upthrust_premature and ut_found and sow_found):
        tr_lower = (tr_ctx or {}).get("tr_lower") if tr_ctx else None
        if utad or (
            last_close is not None
            and tr_lower is not None
            and float(last_close) < float(tr_lower)
        ):
            return _finish({
                "phase": "markdown",
                "phase_label": "主跌 Markdown（离开派发区）",
                "phase_confidence_delta": -0.12,
                "spring_premature": spring_premature,
                "upthrust_premature": False if ut_found else upthrust_premature,
            })

    # ── 积累序列（原典：A停止→B建仓→C弹簧→D确认→E趋势） ──
    # Spring 必须先经 Phase B（有 SC+AR 停止行为或压缩蓄力）才有效
    # P0-A：Spring+Test 优先进 D；裸 Spring 只到 C；premature 不得被 test 洗白
    if not spring_premature and spring and spring_test:
        return _finish({
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+Test）",
            "phase_confidence_delta": 0.12,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
            "phase_tr_gated": False,
            "phase_tr_gate_reason": "",
        })
    if not spring_premature and spring and (sos or lps):
        return _finish({
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+SOS/LPS）",
            "phase_confidence_delta": 0.10,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
            "phase_tr_gated": False,
            "phase_tr_gate_reason": "",
        })
    if not spring_premature and spring and trend_pullback:
        return _finish({
            "phase": "accumulation_d",
            "phase_label": "积累期 D（确认：Spring+趋势回踩）",
            "phase_confidence_delta": 0.12,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
            "phase_tr_gated": False,
            "phase_tr_gate_reason": "",
        })
    if not spring_premature and spring:
        return _finish({
            "phase": "accumulation_c",
            "phase_label": "积累期 C（测试：Spring）",
            "phase_confidence_delta": 0.10,
            "spring_premature": False,
            "upthrust_premature": upthrust_premature,
            "phase_tr_gated": False,
            "phase_tr_gate_reason": "",
        })
    # P2: Compression = 积累期 B 末期（压缩蓄力）
    # 有派发极性时不得抢在 BC/ARE/SOW/UT 之前盖成积累 B（否则派发 A 永远到不了）
    _dist_polarity = bool(
        bc_found
        or are_found
        or sow_found
        or (ut_found and not upthrust_premature)
        or signals.get("distribution_confirmed")
    )
    if compression and not _dist_polarity:
        return _finish({
            "phase": "accumulation_b",
            "phase_label": "积累期 B（压缩蓄力）",
            "phase_confidence_delta": 0.08,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # 新增：SC（卖力高潮）→ 积累期 A，正式识别停止行为
    # （须在裸 TrendPullback 之前，避免 SC/AR 被回踩盖成 D）
    if sc_found and ar_found:
        _a_label = (
            "积累期 A（停止：SC+AR+ST）"
            if signals.get("secondary_test_sc_signal")
            else "积累期 A（停止：SC+AR）"
        )
        return _finish({
            "phase": "accumulation_a",
            "phase_label": _a_label,
            "phase_confidence_delta": 0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    if sc_found:
        return _finish({
            "phase": "accumulation_a",
            "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
            "phase_confidence_delta": 0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # AR 且无 BC/SC：可能是吸筹自动反弹
    if ar_found and not bc_found:
        return _finish({
            "phase": "accumulation_b",
            "phase_label": "积累期 B（辅助：AR无BC）",
            "phase_confidence_delta": 0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # P3: Trend Pullback = 积累期 D 趋势确认（停止行为之后）
    if trend_pullback:
        return _finish({
            "phase": "accumulation_d",
            "phase_label": "积累期 D（趋势回踩确认）",
            "phase_confidence_delta": 0.08,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })

    # ── 派发序列 ──
    # LPSY（最后供应点）→ 派发期 D；需要前置派发背景（BC/UT/SOW 至少一个）
    if lpsy_found and (bc_found or ut_found or sow_found):
        return _finish({
            "phase": "distribution_d",
            "phase_label": "派发期 D（最后供应点：LPSY）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # 无前置派发背景的孤立 LPSY → 可疑但不标派发 D
    if lpsy_found:
        return _finish({
            "phase": "none",
            "phase_label": "无明确阶段（孤立 LPSY，缺派发背景）",
            "phase_confidence_delta": 0.0,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # UT 必须先经 Phase B（BC+ARE/压缩/SOW 或压缩蓄力）才有效
    if not upthrust_premature and ut_found and sow_found:
        return _finish({
            "phase": "distribution_c",
            "phase_label": "派发期 C（确认：UT+SOW）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": False,
        })
    # 对称 Spring+TrendPullback：UT+TrendRally → 派发 D
    if not upthrust_premature and ut_found and trend_rally:
        return _finish({
            "phase": "distribution_d",
            "phase_label": "派发期 D（确认：UT+趋势反抽）",
            "phase_confidence_delta": -0.12,
            "spring_premature": spring_premature,
            "upthrust_premature": False,
        })
    # 派发 A：BC+ARE（对称 SC+AR），或 BC+压缩/SOW
    # （须在裸 TrendRally 之前，避免 BC/ARE 被反抽盖成 D）
    if bc_found and are_found:
        return _finish({
            "phase": "distribution_a",
            "phase_label": "派发期 A（停止：BC+ARE）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    if bc_found and (has_compression or sow_found):
        return _finish({
            "phase": "distribution_a",
            "phase_label": "派发期 A（停止：BC+蓄势/弱势）",
            "phase_confidence_delta": -0.10,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    if bc_found:
        return _finish({
            "phase": "distribution_a",
            "phase_label": "派发期 A（购买高潮：BC）",
            "phase_confidence_delta": -0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # ARE 且无 BC：可能是派发自动回落（弱背景）
    if are_found and not sc_found:
        return _finish({
            "phase": "distribution_b",
            "phase_label": "派发期 B（辅助：ARE无BC）",
            "phase_confidence_delta": -0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    # Trend Rally：跌势中反抽不过均线 → 派发 D（停止行为之后）
    if trend_rally:
        return _finish({
            "phase": "distribution_d",
            "phase_label": "派发期 D（趋势反抽确认）",
            "phase_confidence_delta": -0.08,
            "spring_premature": spring_premature,
            "upthrust_premature": upthrust_premature,
        })
    if not upthrust_premature and ut_found:
        # P1-3：裸 UT 对称裸 Spring → C 测试（非派发 A 停止）
        return _finish({
            "phase": "distribution_c",
            "phase_label": "派发期 C（测试：UT）",
            "phase_confidence_delta": -0.05,
            "spring_premature": spring_premature,
            "upthrust_premature": False,
        })

    # 孤立/过早 Spring 或 UT（无 Phase B 背景）、或完全无信号 → 无明确阶段
    # 但带 premature 标注，供 score 层降权使用
    reasons = []
    if spring_premature:
        reasons.append("Spring孤立/过早（缺Phase B背景）")
    if upthrust_premature:
        reasons.append("Upthrust孤立/过早（缺Phase B背景）")
    suffix = f"（{'；'.join(reasons)}）" if reasons else ""
    return _finish({
        "phase": "none",
        "phase_label": f"无明确阶段{suffix}",
        "phase_confidence_delta": 0.0,
        "spring_premature": spring_premature,
        "upthrust_premature": upthrust_premature,
    })

def _phase_key(symbol: str, timeframe: str) -> str:
    """持久化键：按 symbol + 周期维度隔离，避免日线与中线共用同一键互相污染。"""
    return f"{symbol}::{timeframe}"

def _load_phase_state(symbol: str, timeframe: str = "daily") -> dict[str, Any] | None:
    """从持久化文件加载该标的在指定周期的 phase 状态。"""
    if not symbol:
        return None
    try:
        from trader_shared.json_atomic import load_json_dict

        data = load_json_dict(_wyckoff_phase_path())
        rec = data.get(_phase_key(symbol, timeframe))
        return rec if isinstance(rec, dict) else None
    except (OSError, TypeError, ValueError):
        return None

def _save_phase_state(symbol: str, timeframe: str, phase_state: dict[str, Any]) -> None:
    """将 phase 状态持久化（锁内 RMW + tmp/fsync/replace）。"""
    if not symbol:
        return
    try:
        from trader_shared.json_atomic import locked_rmw_json

        key = _phase_key(symbol, timeframe)

        def _mutate(data: dict[str, Any]) -> dict[str, Any]:
            data[key] = phase_state
            return data

        locked_rmw_json(_wyckoff_phase_path(), _mutate)
    except OSError:
        pass

def _transition_phase(
    old_phase_state: dict[str, Any] | None,
    new_phase: str,
    new_phase_label: str,
    new_confidence_delta: float,
    *,
    force_apply_none: bool = False,
) -> dict[str, Any]:
    """状态机：phase 平滑过渡，允许反向翻转。

    规则：
      - 无旧状态 → 直接使用新 phase
      - 新 phase 为 "none" → 默认维持旧状态（平滑，不抖动）
      - force_apply_none=True（Phase A 破位失败等）→ 必须落下 none，禁止黏回健康叙事
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

    # 新 phase 无信号 → 默认保持旧状态；结构失败收口时强制落下 none（S-A5）
    if new_phase == "none":
        if force_apply_none:
            return {
                "phase": "none",
                "phase_label": new_phase_label,
                "phase_confidence_delta": new_confidence_delta,
                "first_seen": None,
            }
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
