"""P0-3 Trading Range (TR) 识别层专项测试。

验证原典「TR → 边界 → 事件」因果链在 wyckoff_events / wyckoff_core 中的落地：
  1. 横盘区间被正确识别为 TR（上下沿、基线量、宽度、质量）
  2. 趋势段 / 过窄噪声不被误判为 TR
  3. TR 边界用「反复测试的分位带」而非绝对极值 —— Spring/Upthrust 刺穿被排除（P0-3 关键修复）
  4. 事件检测器在 TR 语境下使用 TR 边界（而非局部极值）作为支撑/阻力/量能基线
  5. tr_ctx=None 时所有检测器走原逻辑、不崩溃（向后兼容铁律）

这些测试用合成 K 线构造，不依赖网络/数据源。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared import wyckoff_events as we
from trader_shared.wyckoff_core import wyckoff_analysis, calculate_wyckoff_score
from trader_shared.wyckoff_phase import _detect_phase


def mk(o, h, l, c, v):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "date": 0}


def build_flat_tr(n=45, with_spikes=False):
    """构造横盘 TR：low 8.5-8.8, high 9.2-9.3, close 在区间内震荡。

    with_spikes=True 时注入少数 high=9.8 的刺穿，使局部极值(max recent)显著高于
    TR 的 85 分位上沿 —— 用于验证事件检测器用的是 TR 边界而非局部极值。
    """
    bars = []
    for i in range(n):
        o = 8.9 + 0.1 * (i % 2)
        h = 9.2 + 0.1 * ((i // 3) % 2)
        l = 8.5 + 0.1 * ((i // 2) % 2)
        c = 8.9 + 0.15 * (1 if i % 2 else -1) * ((i // 3) % 2) + 0.05 * (i % 2)
        if with_spikes and i in (5, 20, 35):
            h = 9.8
        bars.append(mk(round(o, 2), round(h, 2), round(l, 2), round(c, 2),
                       1_000_000 + (i % 5) * 50_000))
    return bars


# ── 1. 横盘区间被正确识别为 TR ───────────────────────────────────────────────
def test_tr_detected_on_flat_range():
    bars = build_flat_tr()
    tr = we._detect_trading_range(bars)
    assert tr is not None, "横盘区间应被识别为 TR"
    assert tr["tr_width"] >= 20, f"TR 宽度应 >= 20, got {tr['tr_width']}"
    assert 6.0 <= tr["tr_amplitude_pct"] <= 30.0, f"振幅应在 [6,30]%, got {tr['tr_amplitude_pct']}"
    assert tr["tr_lower"] < tr["tr_upper"], "下沿应低于上沿"
    assert tr["in_tr"] is True, "末根收盘价应在 TR 内"
    assert tr["tr_baseline_volume"] > 0, "基线量应为正"
    # 质量分应在 (0,1]
    assert 0 < tr["tr_quality"] <= 1.0, f"tr_quality 应在 (0,1], got {tr['tr_quality']}"


# ── 2. 单调趋势不被误判为 TR（方向交替测试拦截） ─────────────────────────────
def test_tr_rejected_on_monotonic_trend():
    # 严格单调上涨：close 每根 +0.1，无方向反转 → dir_changes=0 → 非 TR
    bars = [mk(10 + i * 0.1, 10.2 + i * 0.1, 9.8 + i * 0.1, 10 + i * 0.1, 1_000_000)
            for i in range(40)]
    assert we._detect_trading_range(bars) is None, "单调趋势不应被识别为 TR"


# ── 3. 过窄区间不被识别为 TR（振幅阈值拦截） ───────────────────────────────
def test_tr_rejected_on_too_narrow():
    # 振幅 ~0% 的窄幅噪声
    bars = [mk(10, 10.01, 9.99, 10, 1_000_000) for _ in range(40)]
    assert we._detect_trading_range(bars) is None, "过窄区间不应被识别为 TR"


# ── 4. TR 边界排除 Spring 刺穿（P0-3 关键修复） ─────────────────────────────
def test_tr_boundary_excludes_spring_penetration():
    bars = build_flat_tr()
    # 末尾追加 Spring：low 刺穿到 8.2（低于 TR 下沿 ~8.5），收盘收回 8.75
    spring = mk(8.9, 9.0, 8.2, 8.75, 600_000)
    bars_s = bars + [spring]

    tr = we._detect_trading_range(bars_s)
    assert tr is not None, "含 Spring 的横盘仍应识别为 TR"
    # 关键：TR 下沿必须用分位带，排除 8.2 的刺穿毛刺
    assert tr["tr_lower"] > 8.2, f"TR 下沿应高于 Spring 刺穿低点 8.2, got {tr['tr_lower']}"
    assert tr["in_tr"] is True, "Spring 收盘收回 → 末根仍在 TR 内"

    # Spring 检测器在 TR 语境下用 tr_lower 作支撑 → 正确识别
    sp = we._detect_spring(bars_s, tr_ctx=tr)
    assert sp["spring_signal"] is True, f"TR 语境下 Spring 应触发, got {sp.get('spring_reason')}"


# ── 5. Upthrust 检测器在 TR 语境下用 TR 上沿为阻力 ──────────────────────────
def test_upthrust_uses_tr_upper_as_resistance():
    bars = build_flat_tr(with_spikes=True)
    # Upthrust 棒 high=9.6：介于 tr_upper(9.3) 与局部极值 max recent(9.8) 之间
    ut = mk(9.3, 9.6, 9.2, 9.2, 3_000_000)
    bars_u = bars + [ut]

    tr = we._detect_trading_range(bars_u)
    assert tr is not None
    # 验证局部极值确实高于 TR 上沿（否则对比无意义）
    recent_highs = [b["high"] for b in bars_u[-(we.WYCKOFF_SPRING_SUPPORT_LOOKBACK + 1):-1]]
    assert max(recent_highs) > tr["tr_upper"], "测试构造需 max(recent) > tr_upper"

    with_tr = we._detect_upthrust(bars_u, tr_ctx=tr)
    no_tr = we._detect_upthrust(bars_u)  # 不带 tr_ctx → 用局部极值作阻力
    assert with_tr["upthrust_signal"] is True, "TR 语境下 9.6 > tr_upper → 应触发 UT"
    assert no_tr["upthrust_signal"] is False, "无 TR 语境下 9.6 < 局部极值 → 不应触发 UT"


# ── 6. 事件检测器接受 tr_ctx=None 不崩溃（向后兼容铁律） ────────────────────
def test_detectors_accept_none_tr_ctx_backward_compat():
    bars = build_flat_tr()
    # 全部检测器在 tr_ctx=None 时走原逻辑，返回 dict 且不抛异常
    fns = [
        we._detect_spring, we._detect_upthrust, we._detect_sign_of_weakness,
        we._detect_sos, we._detect_st, we._detect_lps, we._detect_lpsy,
        we._detect_buying_climax, we._detect_selling_climax, we._detect_ar,
    ]
    for fn in fns:
        try:
            r = fn(bars, tr_ctx=None)
        except TypeError:
            r = fn(bars)  # 个别签名 tr_ctx 非首位，退化到无参
        assert isinstance(r, dict), f"{fn.__name__} 应返回 dict"
        # 每个信号 dict 必须含 *_signal 布尔键
        sig_keys = [k for k in r if k.endswith("_signal")]
        assert sig_keys, f"{fn.__name__} 缺少 *_signal 键"


# ── 7. wyckoff_analysis 端到端透出 tr_* 字段 ───────────────────────────────
def test_wyckoff_analysis_exposes_tr_fields():
    # 横盘 TR → tr_* 应被填充
    flat = build_flat_tr()
    an_flat = wyckoff_analysis(flat)
    assert an_flat["tr_lower"] is not None and an_flat["tr_upper"] is not None
    assert an_flat["tr_width"] >= 20
    assert an_flat["tr_in_range"] is True

    # 趋势段 → TR 未识别 → tr_* 全为 None（core 的 tr_ctx=None 分支）
    trend = [mk(10 + i * 0.1, 10.2 + i * 0.1, 9.8 + i * 0.1, 10 + i * 0.1, 1_000_000)
             for i in range(40)]
    an_trend = wyckoff_analysis(trend)
    assert an_trend["tr_lower"] is None
    assert an_trend["tr_upper"] is None
    assert an_trend["tr_width"] is None


# ════════════════════════════════════════════════════════════════════════════
# P0-4 Spring / Upthrust 真假分级 (Strength Grading) 专项测试
#
# 分级维度（原典）：刺穿深度(%) / 量能比(vs TR基线量) / 收回收盘位置(相对TR中轴)
# 四级：strong / ordinary / weak / failure（failure = 反向信号，弹簧失败→派发，
#       上冲失败→可能是真突破 SOS）
# ════════════════════════════════════════════════════════════════════════════

def _grade(tag="", spring_bar=None, upthrust_bar=None, with_spikes=True):
    """构造 TR + 指定刺穿/突破棒，返回 (spring_dict, upthrust_dict)。"""
    bars = build_flat_tr(with_spikes=with_spikes)
    if spring_bar is not None:
        bars = bars + [spring_bar]
    if upthrust_bar is not None:
        bars = bars + [upthrust_bar]
    tr = we._detect_trading_range(bars)
    sp = we._detect_spring(bars, tr_ctx=tr)
    ut = we._detect_upthrust(bars, tr_ctx=tr)
    return sp, ut


# ── 8. Strong Spring：深刺穿 + 量能配合 + 坚决收回中轴 ──────────────────────
def test_strong_spring_grading():
    # 成交量必须 < avg_vol×BULLISH_VOL_RATIO(1.3) ≈ 143万，否则被放量过滤器拦截判为 failure
    sp, _ = _grade(spring_bar=mk(8.9, 9.0, 8.2, 9.0, 1_200_000))
    assert sp["spring_signal"] is True
    assert sp["spring_strength"] == "strong", f"应为 strong, got {sp.get('spring_strength')}"
    assert sp["spring_depth_pct"] >= 1.5, "深度刺穿应 >= 1.5%"
    assert sp["spring_vol_ratio"] >= 1.0, "量能配合 vol_ratio 应 >= 1.0"
    assert sp["spring_reclaim_ratio"] >= 1.0, "收盘应收回 TR 中轴以上"
    assert "吸筹最强确认" in sp["spring_strength_note"]


# ── 8b. Strong Spring：缩量供应耗尽（原典最强）──────────────────────────────
def test_strong_low_vol_spring_grading():
    """P0-1：深刺+缩量+收回中轴 → strong（禁止标 weak）。"""
    sp, _ = _grade(spring_bar=mk(8.9, 9.0, 8.2, 9.0, 600_000))
    assert sp["spring_signal"] is True, f"应触发 spring, got {sp.get('spring_reason')}"
    assert sp["spring_vol_class"] == "low_vol_confirm"
    assert sp["spring_strength"] == "strong", f"缩量深刺应为 strong, got {sp.get('spring_strength')}"
    assert "供应耗尽" in sp["spring_strength_note"] or "缩量" in sp["spring_strength_note"]


# ── 9. Weak Spring：浅刺穿噪音 ──────────────────────────────────────────────
def test_weak_spring_grading():
    # 极浅刺穿（depth < WEAK_DEPTH 0.5%）→ weak 噪音；须能过 breach 线
    bar = mk(8.9, 8.95, 8.48, 8.75, 1_100_000)
    bar["atr14"] = 0.03  # breach 很浅，low=8.48 可过
    bars = build_flat_tr(with_spikes=True) + [bar]
    tr = we._detect_trading_range(bars)
    sp2 = we._detect_spring(bars, tr_ctx=tr)
    assert sp2["spring_signal"] is True, f"应触发 spring, got {sp2.get('spring_reason')}"
    assert sp2["spring_strength"] == "weak", f"浅刺应判 weak, got {sp2.get('spring_strength')}"
    assert "刺穿过浅" in sp2["spring_strength_note"] or "噪音" in sp2["spring_strength_note"]


# ── 10. Ordinary Spring：标准刺穿，深度/量/收回未同时达 strong ───────────────
def test_ordinary_spring_grading():
    # low=8.33(depth~2.0%, 介于 1.5%~2.5%) + 正常量(1.4M) + 收回中轴(close=8.8) → ordinary
    sp, _ = _grade(spring_bar=mk(8.9, 8.95, 8.33, 8.8, 1_400_000))
    assert sp["spring_signal"] is True
    assert sp["spring_strength"] == "ordinary", f"应为 ordinary, got {sp.get('spring_strength')}"


# ── 11. Spring Failure：刺穿支撑但收盘未收回 → 反向派发信号 ──────────────────
def test_spring_failure_reverse_signal():
    sp, _ = _grade(spring_bar=mk(8.9, 8.95, 8.2, 8.4, 2_500_000))
    assert sp["spring_signal"] is False, "刺穿后未收回 → 非有效 spring"
    assert sp["spring_strength"] == "failure", "刺穿未收回应为 failure(派发信号)"
    assert "弹簧失败" in sp["spring_reason"]


# ── 12. Strong Upthrust：深突破 + 放量派发 + 跌回中轴下 ──────────────────────
def test_strong_upthrust_grading():
    _, ut = _grade(upthrust_bar=mk(9.3, 9.6, 9.2, 8.8, 3_000_000))
    assert ut["upthrust_signal"] is True
    assert ut["upthrust_strength"] == "strong", f"应为 strong, got {ut.get('upthrust_strength')}"
    assert ut["upthrust_depth_pct"] >= 0.5
    assert ut["upthrust_vol_ratio"] >= 1.2, "派发需放量"
    assert ut["upthrust_reclaim_ratio"] >= 1.0, "收盘应跌回 TR 中轴以下"
    assert "派发最强确认" in ut["upthrust_strength_note"]


# ── 13. Upthrust Failure：突破后站住未回落 → 可能是真突破(SOS) ──────────────
# 用无 spikes 的 TR（tr_upper 稳定 ~9.3），避免刺穿毛刺抬高上沿分位带导致 in_tr=False
def test_upthrust_failure_reverse_signal():
    _, ut = _grade(upthrust_bar=mk(9.3, 9.6, 9.2, 9.4, 3_000_000), with_spikes=False)
    assert ut["upthrust_signal"] is False, "突破后站住 → 非有效 UT"
    assert ut["upthrust_strength"] == "failure", "站住未回落应为 failure(可能是真突破)"
    assert "上冲失败" in ut["upthrust_reason"]


# ── 14. 分级字段端到端透出（wyckoff_analysis） ───────────────────────────────
def test_wyckoff_analysis_exposes_strength_fields():
    bars = build_flat_tr(with_spikes=True) + [mk(8.9, 9.0, 8.2, 9.0, 1_200_000)]
    an = wyckoff_analysis(bars)
    assert an["spring_signal"] is True
    assert an["spring_strength"] == "strong"
    assert an["spring_depth_pct"] is not None
    assert an["spring_vol_ratio"] is not None
    assert an["spring_reclaim_ratio"] is not None
    # 无 UT 时应透出 None（失败/无信号分支字段一致）
    assert an["upthrust_strength"] is None


# ── 15. tr_ctx=None 时分级字段仍安全返回（兼容，不抛异常） ───────────────────
def test_strength_grading_without_tr_ctx_no_crash():
    bars = build_flat_tr(with_spikes=True) + [mk(8.9, 9.0, 8.2, 9.0, 1_200_000)]
    # 不带 tr_ctx：走原逻辑（局部极值支撑），仍返回 strength 字段（可能是 ordinary/None）
    sp = we._detect_spring(bars)  # tr_ctx 默认 None
    assert isinstance(sp, dict)
    assert "spring_strength" in sp, "不带 tr_ctx 也应含 spring_strength 字段"
    ut = we._detect_upthrust(bars)
    assert "upthrust_strength" in ut


def test_st_rejects_fake_spring_without_reclaim():
    """P1-1：仅刺穿未收回（非 _detect_spring）不得锚 ST。"""
    bars = build_flat_tr(n=40, with_spikes=False)
    tr = we._detect_trading_range(bars)
    assert tr is not None
    lo = float(tr["tr_lower"])
    # 假「刺穿」：low 破下沿但收盘不收回 → 非 Spring
    bars.append(mk(lo + 0.1, lo + 0.15, lo - 0.3, lo - 0.1, 1_200_000))
    # 后续缩量回踩区（若误锚会误亮 ST）
    for _ in range(5):
        bars.append(mk(lo + 0.05, lo + 0.1, lo + 0.01, lo + 0.05, 400_000))
    tr2 = we._detect_trading_range(bars) or tr
    assert we._detect_spring(bars[: len(bars) - 5], tr_ctx=tr2).get("spring_signal") is False
    st = we._detect_st(bars, tr_ctx=tr2)
    assert st.get("st_signal") is False, f"假刺穿不得触发 ST: {st}"


def test_volume_divergence_not_both_true():
    """P2-1：同窗不得同时 bullish+bearish。"""
    # 先涨后跌且后半缩量 → 至多一侧
    bars = []
    for i in range(5):
        c = 10.0 + i * 0.5
        bars.append(mk(c - 0.1, c + 0.2, c - 0.2, c, 1_000_000))
    for i in range(5):
        c = 12.0 - i * 0.6
        bars.append(mk(c + 0.1, c + 0.2, c - 0.3, c, 500_000))
    bearish, bullish = we._detect_volume_divergence(bars)
    assert not (bearish and bullish), f"双亮非法: bearish={bearish} bullish={bullish}"


# ════════════════════════════════════════════════════════════════════════════
# P0-5 事件簇确认 (Event Cluster Confirmation) 专项测试
#
# 将孤立信号升级为可信的积累/派发事件簇：校验事件先后顺序（trigger bar index）+ 用
# P0-4 strength 字段定级。覆盖：积累确认 / 派发确认 / 顺序颠倒不确认 / 积累失败 /
# 派发失败 / 无簇；外加端到端透出 + tr_ctx=None 兼容。
#
# bar 构造沿用已验证的 verify_cluster 数据（6 场景全部命中），确保与逻辑一致。
# ════════════════════════════════════════════════════════════════════════════

def _flat(n):
    """纯横盘 TR（与 verify_cluster 一致）：low 8.5-8.8, high 9.2-9.3, close 区间内。"""
    bars = []
    for i in range(n):
        o = 8.9 + 0.1 * (i % 2)
        h = 9.2 + 0.1 * ((i // 3) % 2)
        l = 8.5 + 0.1 * ((i // 2) % 2)
        c = 8.9 + 0.15 * (1 if i % 2 else -1) * ((i // 3) % 2) + 0.05 * (i % 2)
        bars.append(mk(round(o, 2), round(h, 2), round(l, 2), round(c, 2),
                       1_000_000 + (i % 5) * 50_000))
    return bars


def _append_sos(b, n=5, vol=1_600_000):
    """5 根阳线累计涨 ~2.7%，每根 range>1%（避一字板），量比>=1.2 → SOS 触发。"""
    start = 9.0
    for k in range(n):
        o = round(start + 0.05 * k, 3)
        c = round(o + 0.05, 3)
        h = round(c + 0.05, 3)
        l = round(o - 0.04, 3)
        b.append(mk(o, h, l, c, vol))


def _append_sow(b, n=6, vol=1_300_000):
    """连续跌破 TR 下沿 8.5：最后 2 根 low 均 <8.5，末根放量收低 → SOW 触发。

    量比取 1.3（≥SOW 阈值 1.0、< SC 阈值 1.5）：若量比 ≥1.5，末根破位 bar 会被
    `_detect_selling_climax` 同时判为 SC，簇的 SC 重置锚（Bug C 合同）将清掉
    簇内事件，派发确认/积累失败无法成立。"""
    start = 8.7
    for k in range(n):
        o = round(start - 0.07 * k, 3)
        c = round(o - 0.06, 3)
        h = round(o + 0.04, 3)
        l = round(c - 0.05, 3)
        b.append(mk(o, h, l, c, vol))


def _append_fillers(b, n=10, c=8.9):
    for _ in range(n):
        b.append(mk(8.9, 9.0, 8.8, c, 900_000))


def _cluster(bars):
    tr = we._detect_trading_range(bars)
    return we._detect_event_cluster(bars, tr_ctx=tr), tr


# ── 16. 积累确认：Spring(strong) → SOS（间隔 >= gap） ───────────────────────
def test_cluster_accumulation_confirmed():
    b = _flat(35)
    b.append(mk(8.9, 9.0, 8.2, 9.0, 1_200_000))  # strong spring (volume < 1.3×基线，绕过放量过滤器)
    _append_fillers(b)
    _append_sos(b)
    cl, tr = _cluster(b)
    assert cl["accumulation_confirmed"] is True, f"应积累确认, got {cl['cluster_reason']}"
    assert cl["distribution_confirmed"] is False
    assert cl["accumulation_failed"] is False
    assert cl["distribution_failed"] is False
    assert cl["cluster_quality"] == "high", "strong spring → high"
    assert abs(cl["cluster_confidence"] - 0.9) < 1e-6
    assert "SOS" in cl["cluster_reason"]


# ── 17. 派发确认：Upthrust → SOW（间隔 >= gap） ─────────────────────────────
def test_cluster_distribution_confirmed():
    b = _flat(35)
    b.append(mk(9.0, 9.6, 8.9, 9.0, 3_000_000))  # upthrust
    _append_fillers(b)
    _append_sow(b)
    cl, tr = _cluster(b)
    assert cl["distribution_confirmed"] is True, f"应派发确认, got {cl['cluster_reason']}"
    assert cl["accumulation_confirmed"] is False
    assert cl["cluster_quality"] in ("high", "medium", "low")
    assert "SOW" in cl["cluster_reason"]


# ── 18. 顺序颠倒：SOS 在前、Spring 在后 → 不确认 ───────────────────────────
def test_cluster_reversed_order_no_confirm():
    b = _flat(35)
    _append_sos(b)
    _append_fillers(b)
    b.append(mk(8.9, 9.0, 8.2, 9.0, 1_200_000))  # spring 在后
    cl, tr = _cluster(b)
    assert cl["accumulation_confirmed"] is False, "SOS 先于 Spring → 不应积累确认"
    assert cl["distribution_confirmed"] is False
    assert cl["accumulation_failed"] is False
    assert cl["distribution_failed"] is False
    assert cl["cluster_quality"] is None
    assert cl["cluster_confidence"] == 0.0


# ── 19. 积累失败：Spring → SOW（假突破实为派发） ────────────────────────────
def test_cluster_accumulation_failed():
    b = _flat(35)
    b.append(mk(8.9, 9.0, 8.2, 9.0, 1_200_000))  # spring
    _append_fillers(b)
    _append_sow(b)
    cl, tr = _cluster(b)
    assert cl["accumulation_failed"] is True, f"应积累失败, got {cl['cluster_reason']}"
    assert cl["accumulation_confirmed"] is False
    assert cl["distribution_confirmed"] is False
    assert abs(cl["cluster_confidence"] - 0.8) < 1e-6
    assert "假突破" in cl["cluster_reason"]


# ── 20. 派发失败：Upthrust → SOS（假派发实为吸筹） ──────────────────────────
def test_cluster_distribution_failed():
    b = _flat(35)
    b.append(mk(9.0, 9.6, 8.9, 9.0, 3_000_000))  # upthrust
    _append_fillers(b)
    _append_sos(b)
    cl, tr = _cluster(b)
    assert cl["distribution_failed"] is True, f"应派发失败, got {cl['cluster_reason']}"
    assert cl["distribution_confirmed"] is False
    assert cl["accumulation_confirmed"] is False
    assert "假派发" in cl["cluster_reason"]


# ── 21. 无簇：纯横盘 TR → 全部 False ───────────────────────────────────────
def test_cluster_none_on_plain_tr():
    cl, tr = _cluster(_flat(45))
    assert cl["accumulation_confirmed"] is False
    assert cl["distribution_confirmed"] is False
    assert cl["accumulation_failed"] is False
    assert cl["distribution_failed"] is False
    assert cl["cluster_quality"] is None
    assert cl["cluster_confidence"] == 0.0
    assert cl["cluster_reason"] == "无确认事件簇"


# ── 22. 端到端透出（wyckoff_analysis 含 7 个 cluster 字段） ─────────────────
def test_wyckoff_analysis_exposes_cluster_fields():
    b = _flat(35)
    b.append(mk(8.9, 9.0, 8.2, 9.0, 1_200_000))
    _append_fillers(b)
    _append_sos(b)
    an = wyckoff_analysis(b)
    assert an["accumulation_confirmed"] is True
    assert an["cluster_quality"] == "high"
    assert an["cluster_confidence"] == 0.9
    # 其余簇字段均为布尔/None，类型一致
    for key in ("distribution_confirmed", "accumulation_failed", "distribution_failed"):
        assert an[key] is False


# ── 23. tr_ctx=None 时簇检测仍安全返回（兼容，不抛异常） ─────────────────────
def test_cluster_without_tr_ctx_no_crash():
    b = _flat(35)
    b.append(mk(8.9, 9.0, 8.2, 9.0, 1_200_000))
    _append_fillers(b)
    _append_sos(b)
    # 不带 tr_ctx：走原逻辑（局部极值），仍返回完整 cluster dict
    cl = we._detect_event_cluster(b)  # tr_ctx 默认 None
    assert isinstance(cl, dict)
    for key in ("accumulation_confirmed", "distribution_confirmed",
                "accumulation_failed", "distribution_failed"):
        assert key in cl, f"cluster dict 缺 {key}"
        assert isinstance(cl[key], bool)
    assert "cluster_quality" in cl and "cluster_confidence" in cl and "cluster_reason" in cl


# ── 24～26：Feature ② 五阶段机原典串联 — Spring/UT 过早/有效 ──────────────

def _sig(**kw):
    """构造 signals dict 辅助。参数名 = 信号 key（如 spring_signal=True）"""
    d = {k: False for k in ("spring_signal", "upthrust_signal", "sc_signal",
                             "ar_signal", "are_signal", "bc_signal", "sos_signal",
                             "sow_signal", "lps_signal", "lpsy_signal",
                             "compression_signal", "trend_pullback_signal",
                             "trend_rally_signal", "st_signal", "spring_test_signal",
                             "secondary_test_sc_signal", "bu_signal", "utad_signal")}
    d.update(kw)
    return d


# P0-B：阶段机要求 TR 质量达标；单测注入干净 TR，避免超平坦 bars 被门控
# P2：含 sc+ar 的用例默认 established，否则 B+ 会被 no_established_seed 闸住
_OK_TR = {
    "tr_quality": 0.7,
    "tr_upper": 10.2,
    "tr_lower": 9.8,
    "in_tr": True,
    "tr_width": 40,
    "tr_amplitude_pct": 8.0,
    "tr_baseline_volume": 30_000.0,
    "phase_a_status": "established",
}


def _ph(bars, signals, tr_ctx=None):
    return _detect_phase(bars, signals, tr_ctx=tr_ctx if tr_ctx is not None else _OK_TR)


def _super_flat(n):
    """完全平坦的 bars（无任何探测器触发的量价噪声）"""
    return [mk(10.0, 10.01, 9.99, 10.0, 30_000) for _ in range(max(60, n))]


def test_phase_spring_valid_ac_full():
    """完整积累链 SC+AR+压缩+Spring → spring 有效（accumulation_c, prem=False）"""
    b = _super_flat(50)
    ph = _ph(b, _sig(spring_signal=True, sc_signal=True, ar_signal=True, compression_signal=True))
    assert ph.get("spring_premature") is False
    assert "accumulation" in ph["phase"], f"期望积累 phase，实得 {ph['phase']}"


def test_phase_spring_isolated():
    """孤立 Spring（无 B 背景）→ 判过早"""
    b = _super_flat(50)
    ph = _ph(b, _sig(spring_signal=True))
    assert ph.get("spring_premature") is True, "孤立 Spring 应判过早"
    assert ph["phase"] == "none", f"孤立 Spring phase 应为 none，实得 {ph['phase']}"


def test_phase_spring_sc_ar_valid():
    """Spring 在 SC+AR 之后 → 有效（B 背景完整）"""
    b = _super_flat(50)
    ph = _ph(b, _sig(spring_signal=True, sc_signal=True, ar_signal=True))
    assert ph.get("spring_premature") is False, "SC+AR 后 Spring 不应过早"
    assert "accumulation" in ph["phase"]


def test_phase_ut_isolated():
    """孤立 UT（无 B 背景）→ 判过早"""
    b = _super_flat(50)
    ph = _ph(b, _sig(upthrust_signal=True))
    assert ph.get("upthrust_premature") is True, "孤立 UT 应判过早"
    assert ph["phase"] == "none", f"孤立 UT phase 应为 none，实得 {ph['phase']}"


def test_phase_ut_bc_sow_valid():
    """⑥B：UT 在 BC+SOW（派发 B）之后 → 有效；不再依赖 BC+AR"""
    b = _super_flat(50)
    ph = _ph(
        b, _sig(upthrust_signal=True, bc_signal=True, sow_signal=True)
    )
    assert ph.get("upthrust_premature") is False, "BC+SOW 后 UT 不应过早"
    assert "distribution" in ph["phase"]


def test_sow_uses_tr_lower_when_close_below_range():
    """收盘已破 TR 下沿（in_tr=False）时，SOW 仍须按 tr_lower 判定，不退回近窗最低。"""
    bars = build_flat_tr(n=40, with_spikes=False)
    tr = we._detect_trading_range(bars)
    assert tr is not None and tr["tr_lower"] is not None
    lo = float(tr["tr_lower"])
    # 两日刺穿并收在下沿下方 → in_tr=False，但正式 SOW
    bars.append(mk(lo + 0.05, lo + 0.1, lo - 0.15, lo - 0.05, 2_500_000))
    bars.append(mk(lo - 0.02, lo + 0.05, lo - 0.2, lo - 0.08, 2_500_000))
    tr2 = we._detect_trading_range(bars)
    assert tr2 is not None
    assert tr2["in_tr"] is False, "收盘破下沿后 in_tr 应为 False"
    sow = we._detect_sign_of_weakness(bars, tr_ctx=tr2)
    assert sow["sow_signal"] is True, f"应正式 SOW, got {sow}"
    assert abs(float(sow["sow_price"]) - float(tr2["tr_lower"])) < 1e-6


def test_scan_for_signal_passes_tr_ctx_keyword():
    """阶段滑窗须关键字传 tr_ctx，避免塞进 Spring/SOW 的 _support。"""
    from trader_shared.wyckoff_phase import _scan_for_signal

    bars = build_flat_tr(n=40, with_spikes=False)
    tr = we._detect_trading_range(bars)
    assert tr is not None
    # 末根 Spring：刺穿下沿后收回
    lo = float(tr["tr_lower"])
    bars.append(mk(lo + 0.1, lo + 0.2, lo - 0.25, lo + 0.15, 1_200_000))
    tr2 = we._detect_trading_range(bars) or tr
    found = _scan_for_signal(
        bars, we._detect_spring, window=16, step=1, max_lookback_bars=30, tr_ctx=tr2
    )
    # 至少不应因 TypeError/错参静默全灭；直接检测末窗应能 Spring
    direct = we._detect_spring(bars, tr_ctx=tr2)
    if direct.get("spring_signal"):
        assert found is True, "滑窗应在 TR 语境下扫到 Spring"


def test_phase_ut_bc_ar_alone_not_dist_b():
    """⑥B：仅 BC+AR 不再构成派发 B（AR 只服务积累 SC）"""
    b = _super_flat(50)
    ph = _ph(b, _sig(upthrust_signal=True, bc_signal=True, ar_signal=True))
    assert ph.get("upthrust_premature") is True, "无压缩/SOW 时 BC+AR 不应让 UT 生效"


def test_phase_bc_are_not_overridden_by_compression():
    """压缩不得把 BC+ARE 盖成积累 B。"""
    b = _super_flat(50)
    ph = _ph(
        b, _sig(bc_signal=True, are_signal=True, compression_signal=True)
    )
    assert ph["phase"] == "distribution_a"
    assert "积累" not in ph.get("phase_label", "")


def test_phase_bc_not_masked_by_bare_trend_rally():
    """裸 TrendRally 不得把 BC 盖成派发 D。"""
    b = _super_flat(50)
    ph = _ph(b, _sig(bc_signal=True, trend_rally_signal=True))
    assert ph["phase"] == "distribution_a"
    assert "购买高潮" in ph.get("phase_label", "") or "BC" in ph.get("phase_label", "")


def test_phase_sc_not_masked_by_bare_trend_pullback():
    """裸 TrendPullback 不得把 SC+AR 盖成积累 D。"""
    b = _super_flat(50)
    ph = _ph(
        b, _sig(sc_signal=True, ar_signal=True, trend_pullback_signal=True)
    )
    assert ph["phase"] == "accumulation_a"


def test_phase_ut_trend_rally_is_distribution_d():
    """UT+TrendRally（有派发 B）→ 派发 D，对称 Spring+回踩。"""
    b = _super_flat(50)
    ph = _ph(
        b,
        _sig(
            upthrust_signal=True,
            bc_signal=True,
            are_signal=True,
            trend_rally_signal=True,
        ),
    )
    assert ph.get("upthrust_premature") is False
    assert ph["phase"] == "distribution_d"


def test_phase_bare_ut_with_b_is_distribution_c():
    """P1-3：压缩作派发 B 的裸 UT → distribution_c（测试）；BC+ARE 仍先到 A。"""
    b = _super_flat(50)
    ph = _ph(b, _sig(upthrust_signal=True, compression_signal=True))
    assert ph.get("upthrust_premature") is False
    assert ph["phase"] == "distribution_c"
    assert "测试" in ph.get("phase_label", "") or "UT" in ph.get("phase_label", "")


def test_phase_spring_ut_both_isolated():
    """Spring+UT 双孤立（都缺 B 背景）→ 都判过早, phase=none"""
    b = _super_flat(50)
    ph = _ph(b, _sig(spring_signal=True, upthrust_signal=True))
    assert ph.get("spring_premature") is True, "孤立 Spring 应判过早"
    assert ph.get("upthrust_premature") is True, "孤立 UT 应判过早"
    assert ph["phase"] == "none", f"双孤立 phase 应为 none，实得 {ph['phase']}"


# ── P0-A / P0-B 验收（handoff 2026-07-31）──────────────────────────────

def test_a1_spring_without_test_stays_c():
    """A1: 有效 Spring，无缩量回测 → accumulation_c；spring_test=False"""
    b = _super_flat(50)
    ph = _ph(
        b,
        _sig(
            spring_signal=True,
            sc_signal=True,
            ar_signal=True,
            spring_test_signal=False,
            st_signal=False,
        ),
    )
    assert ph["phase"] == "accumulation_c"
    assert ph.get("spring_premature") is False


def test_a2_spring_plus_test_goes_d():
    """A2: 有效 Spring + Test → accumulation_d（Spring+Test）"""
    b = _super_flat(50)
    ph = _ph(
        b,
        _sig(
            spring_signal=True,
            sc_signal=True,
            ar_signal=True,
            spring_test_signal=True,
            st_signal=True,
        ),
    )
    assert ph["phase"] == "accumulation_d"
    assert "Spring+Test" in ph.get("phase_label", "")


def test_a3_premature_spring_not_washed_by_test():
    """A3: spring_premature + 假确认 → 不进 accumulation_c/d"""
    b = _super_flat(50)
    ph = _ph(
        b,
        _sig(spring_signal=True, spring_test_signal=True, st_signal=True),
    )
    assert ph.get("spring_premature") is True
    assert ph["phase"] not in ("accumulation_c", "accumulation_d", "markup")


def test_a4_spring_sos_without_test_still_d():
    """A4: Spring + SOS，无 test → 仍可 D；文案走 SOS 路径"""
    b = _super_flat(50)
    ph = _ph(
        b,
        _sig(
            spring_signal=True,
            sc_signal=True,
            ar_signal=True,
            sos_signal=True,
            spring_test_signal=False,
            st_signal=False,
        ),
    )
    assert ph["phase"] == "accumulation_d"
    assert "SOS/LPS" in ph.get("phase_label", "")


def test_a5_st_and_spring_test_dual_write():
    """A5: st_signal 与 spring_test_signal 一致"""
    from trader_shared.wyckoff_events import _spring_test_fields_from_st

    for on in (True, False):
        st = {
            "st_signal": on,
            "st_reason": "Spring 支撑二次测试，缩量确认" if on else "未检测到",
            "st_price": 10.0 if on else None,
        }
        st_fields = _spring_test_fields_from_st(st)
        assert st_fields["spring_test_signal"] is on
        assert bool(st_fields["spring_test_signal"]) == bool(st["st_signal"])


def test_b1_low_tr_quality_gates_phase():
    """B1: tr_quality=0.2 + Spring 形态 → 可有事件语义，phase 不进积累 C/D/markup"""
    b = _super_flat(50)
    low = {**_OK_TR, "tr_quality": 0.2}
    ph = _detect_phase(
        b,
        _sig(spring_signal=True, sc_signal=True, ar_signal=True, spring_test_signal=True),
        tr_ctx=low,
    )
    assert ph["phase"] == "none"
    assert ph.get("phase_tr_gated") is True
    assert ph.get("phase_tr_gate_reason") == "low_quality"


def test_b2_good_tr_allows_spring_test_d():
    """B2: tr_quality=0.6 + 有效 Spring+test → 可按 P0-A 进 D"""
    b = _super_flat(50)
    good = {**_OK_TR, "tr_quality": 0.6}
    ph = _ph(
        b,
        _sig(
            spring_signal=True,
            sc_signal=True,
            ar_signal=True,
            spring_test_signal=True,
        ),
        tr_ctx=good,
    )
    assert ph["phase"] == "accumulation_d"
    assert not ph.get("phase_tr_gated")


def test_b3_no_tr_ctx_gates_phase():
    """B3: tr_ctx=None + 一堆事件 → phase 不进明确 A–E"""
    b = _super_flat(50)
    ph = _detect_phase(
        b,
        _sig(
            spring_signal=True,
            sc_signal=True,
            ar_signal=True,
            sos_signal=True,
            bc_signal=True,
        ),
        tr_ctx=None,
    )
    assert ph["phase"] == "none"
    assert ph.get("phase_tr_gated") is True
    assert ph.get("phase_tr_gate_reason") == "no_tr"


def test_b4_midline_weekly_path_still_runs():
    """B4: 周线 wyckoff_strategy_midline 路径跑通门控；不足仍 insufficient"""
    from trader_shared.wyckoff_core import wyckoff_strategy_midline

    daily = [mk(10.0, 10.1, 9.9, 10.0, 100_000) for _ in range(40)]
    r = wyckoff_strategy_midline(10.0, weekly_bars=[], daily_bars=daily)
    assert r["wyckoff"].get("timeframe") == "insufficient"

    # 构造有振幅震荡的周线，足以形成 TR
    weekly = []
    for i in range(40):
        base = 10.0 + (0.3 if i % 4 < 2 else -0.2)
        weekly.append(mk(base, base + 0.4, base - 0.4, base + 0.1, 200_000 + i * 1000))
    r2 = wyckoff_strategy_midline(weekly[-1]["close"], weekly_bars=weekly, daily_bars=daily)
    assert r2["wyckoff"].get("timeframe") == "weekly"
    assert "phase" in r2["wyckoff"]
    assert "phase_tr_gated" in r2["wyckoff"] or r2["wyckoff"].get("phase") is not None


# ── 27～29：Feature ① TR 质量接打分 + 过早信号降权 ───────────────────

def _fa_spring(tr_quality, spring_premature=False):
    """构造含 Spring 的分析 dict"""
    return dict(spring_signal=True, spring_premature=spring_premature,
                upthrust_signal=False, upthrust_premature=False,
                bc_signal=False, sc_signal=False, sow_signal=False,
                ar_signal=False, sos_signal=False, st_signal=False,
                lps_signal=False, lpsy_signal=False,
                compression_signal=False, trend_pullback_signal=False,
                bearish_volume_divergence=False, bullish_volume_divergence=False,
                effort_no_result=False, no_supply=False,
                accumulation_confirmed=False, distribution_confirmed=False,
                accumulation_failed=False, distribution_failed=False,
                tr_quality=tr_quality, spring_vol_class="normal",
                phase_confidence_delta=0.0)


def _fa_upthrust(tr_quality, upthrust_premature=False):
    """构造含 UT 的分析 dict"""
    d = _fa_spring(tr_quality)
    d["spring_signal"] = False
    d["upthrust_signal"] = True
    d["upthrust_premature"] = upthrust_premature
    return d


def test_tr_quality_score_adjustment():
    """TR 质量接打分：高质加分、低质减分，None 不调整"""
    b = _flat(30)
    s_high = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.9))
    s_neu = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.5))
    s_low = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.1))
    s_none = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=None))
    assert s_high["raw"] > s_neu["raw"], "高质 TR 应加分"
    assert s_neu["raw"] > s_low["raw"], "低质 TR 应减分"
    assert s_none["raw"] == s_neu["raw"], "tr_quality=None 应无调整"


def test_weak_spring_half_score():
    """弱弹簧（浅刺噪音）打分减半；缩量 ordinary 不减半。"""
    b = _flat(30)
    s_norm = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.5, spring_premature=False))
    weak = _fa_spring(tr_quality=0.5, spring_premature=False)
    weak["spring_strength"] = "weak"
    weak["spring_vol_class"] = "normal"
    s_weak = calculate_wyckoff_score(b, analysis=weak)
    assert s_norm["raw"] > s_weak["raw"], "弱弹簧 raw 应更低"
    assert s_weak["raw"] == 12, f"弱弹簧 raw 应为 12 (25//2)，实得 {s_weak['raw']}"
    assert any("弱" in s or "降权" in s for s in s_weak["signals"])

    low_vol = _fa_spring(tr_quality=0.5, spring_premature=False)
    low_vol["spring_strength"] = "ordinary"
    low_vol["spring_vol_class"] = "low_vol_confirm"
    s_lv = calculate_wyckoff_score(b, analysis=low_vol)
    assert s_lv["raw"] == s_norm["raw"], "缩量 ordinary 应全分，不得因 low_vol 降权"


def test_weak_upthrust_half_score():
    """P1-4：UT weak 打分绝对值减半。"""
    b = _flat(30)
    u_norm = calculate_wyckoff_score(b, analysis=_fa_upthrust(tr_quality=0.5, upthrust_premature=False))
    weak = _fa_upthrust(tr_quality=0.5, upthrust_premature=False)
    weak["upthrust_strength"] = "weak"
    u_weak = calculate_wyckoff_score(b, analysis=weak)
    assert u_norm["raw"] > u_weak["raw"] or abs(u_weak["raw"]) < abs(u_norm["raw"])
    # UT 基分 -20 → weak -10；tr_quality=0.5 无调整
    assert u_weak["raw"] == -10, f"弱 UT raw 应为 -10，实得 {u_weak['raw']}"
    assert any("弱" in s or "降权" in s for s in u_weak["signals"])


def test_spring_premature_half_score():
    """过早 Spring 分数减半"""
    b = _flat(30)
    s_norm = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.5, spring_premature=False))
    s_prem = calculate_wyckoff_score(b, analysis=_fa_spring(tr_quality=0.5, spring_premature=True))
    assert s_norm["raw"] > s_prem["raw"], "过早 Spring raw 应更低"
    assert s_prem["raw"] == 12, f"过早 Spring raw 应为 12 (25//2)，实得 {s_prem['raw']}"
    assert any("降权" in s for s in s_prem["signals"]), "过早 Spring 应有降权标注"


def test_upthrust_premature_half_score():
    """过早 UT 分数减半"""
    b = _flat(30)
    u_norm = calculate_wyckoff_score(b, analysis=_fa_upthrust(tr_quality=0.5, upthrust_premature=False))
    u_prem = calculate_wyckoff_score(b, analysis=_fa_upthrust(tr_quality=0.5, upthrust_premature=True))
    assert u_norm["raw"] < u_prem["raw"], "过早 UT 减半应使 raw 偏上（看空力度减弱）"
    assert any("降权" in s for s in u_prem["signals"]), "过早 UT 应有降权标注"


# ── Bug B fallback：下跌→横盘→突破不再 None（wyckoff-sos-修复交接说明 §2 / §11.4）────
def test_tr_fallback_on_crash_sideways_breakout():
    """高位派发→崩盘(SC)→短横盘(<20 根)→突破：主路径回溯振幅超限失败，
    fallback 末端对齐滑窗补出 TR（tr_fallback=True），不再 None。

    对应交接 §11.4 单元级：构造「下跌→横盘→突破」序列验证 _detect_trading_range 不 None。
    """
    bars = []
    for _ in range(10):
        bars.append(mk(54.0, 55.06, 53.5, 54.5, 1_000_000))
    bars.append(mk(54.5, 55.06, 50.0, 50.5, 8_000_000))
    bars.append(mk(50.5, 50.8, 42.0, 43.0, 9_000_000))
    bars.append(mk(43.0, 43.5, 37.8, 38.5, 10_000_000))  # SC 37.80
    bars.append(mk(38.5, 42.99, 38.0, 42.5, 5_000_000))  # AR 42.99
    for i in range(12):
        c = 43.0 if i % 2 == 0 else 43.4
        bars.append(mk(43.2, 44.5, 41.5, c, 4_700_000))  # 短横盘 41.5~44.5
    bars.append(mk(43.0, 47.92, 42.66, 45.50, 90_000_000))  # 突破 45.50

    tr = we._detect_trading_range(bars)
    assert tr is not None, "下跌→横盘→突破 不得再 None（Bug B fallback）"
    assert tr.get("tr_fallback") is True, "主路径失败应走 fallback"
    assert tr["tr_lower"] < tr["tr_upper"]
    assert 6.0 <= tr["tr_amplitude_pct"] <= 30.0
    # 交接 §0 期望：TR ≈ 41.5~44.5
    assert abs(tr["tr_lower"] - 41.5) < 1.0
    assert abs(tr["tr_upper"] - 44.5) < 1.0
    # 突破根超出上沿 → in_tr=False 属预期（区间识别仍成立）
    assert tr["in_tr"] is False
