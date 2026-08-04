"""W-01：阶段机滑窗须透传 timeframe，周线不得默默用日线参数。
B 收尾：AR 子窗锚统一（wyckoff-epic-vol-phase-verif-handoff §1 方向 B，TP-1/TP-2）。
"""
from __future__ import annotations

from trader_shared.wyckoff_events import _detect_ar, _find_sc_anchor
from trader_shared.wyckoff_phase import _detect_phase, _scan_for_signal


def test_w01_scan_for_signal_passes_timeframe_to_detector():
    seen: dict = {}

    def _fake_detector(bars, tr_ctx=None, *, timeframe="daily", is_index=False):
        seen["timeframe"] = timeframe
        seen["is_index"] = is_index
        seen["tr_ctx"] = tr_ctx
        return {"sc_signal": False}

    bars = [{"close": 10.0 + i * 0.01} for i in range(40)]
    tr = {"in_tr": True}
    _scan_for_signal(
        bars,
        _fake_detector,
        window=15,
        step=5,
        max_lookback_bars=30,
        tr_ctx=tr,
        timeframe="weekly",
        is_index=False,
    )
    assert seen["timeframe"] == "weekly"
    assert seen["is_index"] is False
    assert seen["tr_ctx"] is tr


def test_w01_scan_for_signal_falls_back_when_detector_ignores_timeframe():
    """无 timeframe 形参的检测器仍可被滑窗调用。"""
    calls = {"n": 0}

    def _legacy(bars, tr_ctx=None):
        calls["n"] += 1
        return {"bc_signal": False}

    bars = [{"close": 10.0} for _ in range(20)]
    assert _scan_for_signal(bars, _legacy, window=10, step=5, timeframe="weekly") is False
    assert calls["n"] >= 1


# ── B 收尾：AR 子窗锚统一（wyckoff-epic-vol-phase-verif-handoff §1 方向 B）────────────
# 撕裂：P-M4 剥离 sc_anchor 后，子窗内 _detect_ar 对**子窗**冷启动重算 SC 锚，
# 与主流程 AR 灯（完整序列统一锚）索引口径可能不同 → AR 被绑到历史 SC 上。
# 统一：主流程锚存在时 AR 只认「统一 SC」之后的反弹（remap 进 wide_bars 单次评估）。


def _bar(o, h, l, c, v, idx):
    return {
        "date": f"2026-{(idx // 28) + 1:02d}-{(idx % 28) + 1:02d}",
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def _ar_tearing_bars() -> list[dict]:
    """90 根：横盘基线 + 历史 SC1(idx65)+AR1(idx66) + 统一 SC2(idx80) 后无反弹。

    SC1/SC2 均满足 _find_sc_anchor 条件（低位天量严格阴线，未破位）。
    """
    bars = []
    for i in range(55):
        bars.append(_bar(79.5, 81.0, 79.0, 80.0, 1000, i))
    while len(bars) < 65:
        bars.append(_bar(79.5, 81.0, 79.0, 80.0, 1000, len(bars)))
    bars.append(_bar(76.0, 76.5, 74.0, 74.5, 6000, 65))   # SC1（历史）
    bars.append(_bar(74.5, 79.0, 74.0, 78.5, 800, 66))    # AR1（SC1 后反弹）
    for i in range(67, 80):
        bars.append(_bar(79.5, 81.0, 79.0, 80.0, 1000, i))
    bars.append(_bar(77.0, 77.5, 76.5, 76.8, 7000, 80))   # SC2（统一锚）
    for i, c in enumerate([77.2, 77.4, 77.6, 77.5, 77.3, 77.1, 77.2, 77.0, 77.1]):
        bars.append(_bar(77.0, 77.8, 76.8, c, 900, 81 + i))  # SC2 后无 2% 反弹
    return bars


def _phase_signals(last_close: float) -> dict:
    keys = [
        "spring_signal", "upthrust_signal", "bc_signal", "sc_signal", "sow_signal",
        "ar_signal", "are_signal", "sos_signal", "st_signal", "spring_test_signal",
        "secondary_test_sc_signal", "lps_signal", "lpsy_signal", "compression_signal",
        "trend_pullback_signal", "trend_rally_signal", "bu_signal", "utad_signal",
        "ps_signal", "psy_signal",
    ]
    s = {k: False for k in keys}
    s["last_close"] = last_close
    s["tr_upper"] = 81.0
    return s


class TestArUnifiedAnchorB:
    """B-M3：统一锚路径 AR 只认统一 SC；无锚路径保持原滑窗重算（P-M3 兼容）。"""

    def test_b1_unified_anchor_ignores_historical_sc(self):
        """统一 SC2 存在但 SC2 后无 AR → ar_found 不得被历史 SC1+AR1 抬升。

        子窗重算（旧路径）确实能检出 SC1+AR1（证明撕裂存在）；统一后 label 只报
        「卖力高潮：SC」，不再虚构「停止：SC+AR」。
        """
        bars = _ar_tearing_bars()
        anchor = _find_sc_anchor(bars, tr_ctx=None, include_failed=False)
        assert anchor is not None and anchor["sc_bar_idx"] == 80  # 统一 SC=SC2
        tr_ctx = {
            "tr_quality": 0.8, "phase_a_status": "established", "in_tr": True,
            "tr_lower": 76.0, "sc_anchor": anchor,
        }
        # 撕裂存在性：旧路径（子窗重算）能检出 SC1+AR1
        sub_ctx = {k: v for k, v in tr_ctx.items() if k != "sc_anchor"}
        assert _scan_for_signal(
            bars[-60:], _detect_ar, window=18, step=5, max_lookback_bars=30,
            tr_ctx=sub_ctx, timeframe="daily",
        ) is True

        result = _detect_phase(
            bars, _phase_signals(bars[-1]["close"]), tr_ctx=tr_ctx, timeframe="daily"
        )
        assert result["phase"] == "accumulation_a"
        assert "SC+AR" not in result["phase_label"]  # 不再绑历史 SC1 的 AR

    def test_b2_unified_anchor_finds_ar_after_unified_sc(self):
        """统一 SC2 后确有反弹 → ar_found=True，label 报「停止：SC+AR」。"""
        bars = _ar_tearing_bars()
        # SC2(idx80) 后 idx81 放一根合格 AR（> SC2 close 76.8×1.02）
        bars[81] = _bar(76.9, 79.5, 76.8, 79.0, 700, 81)
        anchor = _find_sc_anchor(bars, tr_ctx=None, include_failed=False)
        assert anchor is not None and anchor["sc_bar_idx"] == 80
        tr_ctx = {
            "tr_quality": 0.8, "phase_a_status": "established", "in_tr": True,
            "tr_lower": 76.0, "sc_anchor": anchor,
        }
        result = _detect_phase(
            bars, _phase_signals(bars[-1]["close"]), tr_ctx=tr_ctx, timeframe="daily"
        )
        assert result["phase"] == "accumulation_a"
        assert "SC+AR" in result["phase_label"]

    def test_b3_unified_anchor_out_of_lookback_degrades_to_signals(self):
        """统一锚早于 lookback（remap 出界）→ ar_found 退化为 signals 判定。"""
        bars = _ar_tearing_bars()
        anchor = _find_sc_anchor(bars, tr_ctx=None, include_failed=False)
        # 伪造锚到 idx10（远早于默认 lookback=60）→ remap 出界
        anchor = {**anchor, "sc_bar_idx": 10}
        tr_ctx = {
            "tr_quality": 0.8, "phase_a_status": "established", "in_tr": True,
            "tr_lower": 76.0, "sc_anchor": anchor,
        }
        result = _detect_phase(
            bars, _phase_signals(bars[-1]["close"]), tr_ctx=tr_ctx, timeframe="daily"
        )
        assert "SC+AR" not in result["phase_label"]  # 历史 SC1+AR1 不再被认可

    def test_b4_no_anchor_keeps_legacy_scan(self):
        """无 sc_anchor（孤立调用，P-M3 兼容）→ 原滑窗重算仍可检出历史 SC1+AR1。"""
        bars = _ar_tearing_bars()
        tr_ctx = {
            "tr_quality": 0.8, "phase_a_status": "established", "in_tr": True,
            "tr_lower": 76.0,  # 无 sc_anchor
        }
        result = _detect_phase(
            bars, _phase_signals(bars[-1]["close"]), tr_ctx=tr_ctx, timeframe="daily"
        )
        assert result["phase"] == "accumulation_a"
        assert "SC+AR" in result["phase_label"]  # 历史定位语义保留（向后兼容）
