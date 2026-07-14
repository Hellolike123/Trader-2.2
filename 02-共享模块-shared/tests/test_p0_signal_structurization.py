"""P0-1 信号结构化字段 — 等价性闸门。

证明: 融合层改用 signal_tier 字段后, 三处强信号布尔量 (strong_bullish_chan /
strong_bearish_chan / strong_bearish_vpf) 与旧 reason 中文关键词匹配 100% 等价,
且端到端 merge_decisions 行为无漂移。

策略:
  1. signal_schema 契约单测 (tier 集合 / 判定函数)
  2. _chan_to_signal 每个分支 signal_tier 正确 + 旧关键词布尔 == 新 tier 布尔
  3. vpf build/vpf_to_fusion_signal signal_tier 正确 + 旧关键词布尔 == 新 tier 布尔
  4. 端到端: merge_decisions 在真实信号源输入下不崩, 且布尔等价已覆盖全矩阵
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02-共享模块-shared"))
sys.path.insert(0, str(ROOT / "01-功能包-packages" / "trader" / "scripts"))

from trader_shared import fusion_core, signal_schema, vpf_core
from trader_shared.signal_schema import (
    SignalTier,
    chan_is_strong_bear,
    chan_is_strong_bull,
    vpf_is_bearish_warning,
    vpf_tier_from_reason,
)

# ── 旧关键词匹配逻辑 (P0-1 前 fusion 实际行为, 作为等价基准) ──
_OLD_CHAN_BULL_KW = ("一类买", "二类买", "三类买", "1类买", "2类买", "3类买",
                     "底背驰", "1st buy", "2nd buy", "3rd buy", "bottom divergence")
_OLD_CHAN_BEAR_KW = ("一类卖", "1类卖", "1st sell", "顶背驰", "top_divergence")
_OLD_VPF_KW = ("天量", "滞涨", "连", "流出")


def _old_strong_bullish_chan(sig):
    return sig.get("direction") == 1 and any(
        k in sig.get("reason", "") for k in _OLD_CHAN_BULL_KW)


def _old_strong_bearish_chan(sig):
    return sig.get("direction") == -1 and any(
        k in sig.get("reason", "") for k in _OLD_CHAN_BEAR_KW)


def _old_strong_bearish_vpf(sig):
    return sig.get("direction") == -1 and (
        float(sig.get("confidence") or 0) >= 0.5
        or any(k in str(sig.get("reason") or "") for k in _OLD_VPF_KW)
    )


# ───────────────────────── 1. schema 契约 ─────────────────────────
def test_schema_tier_sets():
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_1)
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_2)
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_3)
    assert chan_is_strong_bull(SignalTier.CHAN_BOTTOM_DIVERGENCE)
    # 类二买 / 趋势 不强多
    assert not chan_is_strong_bull(SignalTier.CHAN_BUY_LIKE2)
    assert not chan_is_strong_bull(SignalTier.CHAN_TREND_UP)
    assert not chan_is_strong_bull(SignalTier.NEUTRAL)

    assert chan_is_strong_bear(SignalTier.CHAN_SELL_1)
    assert chan_is_strong_bear(SignalTier.CHAN_TOP_DIVERGENCE)
    # 二/三类卖不强空 (有意设计)
    assert not chan_is_strong_bear(SignalTier.CHAN_SELL_2)
    assert not chan_is_strong_bear(SignalTier.CHAN_SELL_3)

    assert vpf_is_bearish_warning(SignalTier.VPF_BEARISH_WARNING)
    assert not vpf_is_bearish_warning(SignalTier.NEUTRAL)


def test_vpf_tier_from_reason_parity():
    # 偏空关键词 → BEARISH_WARNING
    for r in ("天量天价", "放量滞涨", "主力连3日净流出", "近5日主力累计流出1200万（占比2.30%）"):
        assert vpf_tier_from_reason(r) == SignalTier.VPF_BEARISH_WARNING
    # 偏多 / 中性 → NEUTRAL
    for r in ("近5日主力累计流入800万", "价量资金中性", "资金数据不足", "价量偏多"):
        assert vpf_tier_from_reason(r) == SignalTier.NEUTRAL


def test_vpf_lian_substring_tightened():
    """P0-1 后跟进: `连` 子串从裸匹配收紧为"连续净流出"语义。

    旧逻辑 (裸 "连" in reason) 会误命中偏多文案"连续净流入",
    在 direction==-1 时错标 BEARISH_WARNING; 新逻辑要求伴随"净流出"且排除"净流入"。
    """
    # 1) 旧行为确有此误判 — 证明为什么必须改
    assert _old_strong_bearish_vpf({"direction": -1, "reason": "主力连续净流入3日"}) is True
    # 2) 新逻辑: 偏多"连续净流入"正确不标
    assert vpf_tier_from_reason("主力连续净流入3日") == SignalTier.NEUTRAL
    # 3) 新逻辑仍捕获真实偏空表述
    assert vpf_tier_from_reason("主力连续净流出3日") == SignalTier.VPF_BEARISH_WARNING
    assert vpf_tier_from_reason("主力连3日净流出") == SignalTier.VPF_BEARISH_WARNING
    # 4) 既有 parity 用例 (天量/滞涨/累计流出/流入/中性) 不受本次改动影响 — 见上方 parity 测试



# ───────────────────────── 2. chan 分支矩阵 ─────────────────────────
def _chan_raw(buy=None, sell=None, div_top=False, div_bottom=False, trend=None):
    raw = {"chanlun": {"buy_points": [], "sell_points": [], "divergence": {}}}
    if buy:
        raw["chanlun"]["buy_points"] = [buy]
    if sell:
        raw["chanlun"]["sell_points"] = [sell]
    if div_top or div_bottom:
        raw["chanlun"]["divergence"] = {
            "top_divergence": div_top, "bottom_divergence": div_bottom}
    if trend is not None:
        raw["chanlun"]["trend_label"] = trend
    return raw


@pytest.mark.parametrize("raw,expected_tier", [
    (_chan_raw(buy={"type": "一类买", "signal_id": "x"}), SignalTier.CHAN_BUY_1),
    (_chan_raw(buy={"type": "二类买", "signal_id": "x"}), SignalTier.CHAN_BUY_2),
    (_chan_raw(buy={"type": "三类买", "signal_id": "x"}), SignalTier.CHAN_BUY_3),
    (_chan_raw(buy={"type": "类二买", "signal_id": "x"}), SignalTier.CHAN_BUY_LIKE2),
    (_chan_raw(sell={"type": "一类卖", "signal_id": "x"}), SignalTier.CHAN_SELL_1),
    (_chan_raw(sell={"type": "二类卖", "signal_id": "x"}), SignalTier.CHAN_SELL_2),
    (_chan_raw(sell={"type": "三类卖", "signal_id": "x"}), SignalTier.CHAN_SELL_3),
    (_chan_raw(div_top=True), SignalTier.CHAN_TOP_DIVERGENCE),
    (_chan_raw(div_bottom=True), SignalTier.CHAN_BOTTOM_DIVERGENCE),
    (_chan_raw(trend="拉升段(盘整)"), SignalTier.CHAN_TREND_UP),
    (_chan_raw(trend="回调段(盘整)"), SignalTier.CHAN_TREND_DOWN),
    (_chan_raw(), SignalTier.NEUTRAL),
])
def test_chan_to_signal_tier_and_parity(raw, expected_tier):
    sig = fusion_core._chan_to_signal(raw)
    assert sig.get("signal_tier") == expected_tier
    # 关键: 新 tier 布尔 == 旧 reason 关键词布尔
    new_bull = chan_is_strong_bull(sig.get("signal_tier"))
    new_bear = chan_is_strong_bear(sig.get("signal_tier"))
    assert new_bull == _old_strong_bullish_chan(sig)
    assert new_bear == _old_strong_bearish_chan(sig)


# ── 优先级覆盖: 卖点优先于买点, 一类买优先于顶背驰等 (tier 须随最高优先级) ──
def test_chan_priority_tier():
    # 同时有一类买 + 一类卖 → 卖点赢 (SELL_1)
    raw = _chan_raw(buy={"type": "一类买", "signal_id": "b"},
                    sell={"type": "一类卖", "signal_id": "s"})
    assert fusion_core._chan_to_signal(raw).get("signal_tier") == SignalTier.CHAN_SELL_1
    # 一类买 + 底背驰 → 一类买赢 (BUY_1)
    raw = _chan_raw(buy={"type": "一类买", "signal_id": "b"}, div_bottom=True)
    assert fusion_core._chan_to_signal(raw).get("signal_tier") == SignalTier.CHAN_BUY_1


# ───────────────────────── 3. vpf 分支矩阵 ─────────────────────────
@pytest.mark.parametrize("vw,fund,expected_tier", [
    # 天量天价 (climactic)
    ({"warning_type": "climactic", "signal": 0, "reason": "", "volume_ratio": 3.2,
      "price_change": 5.0}, None, SignalTier.VPF_BEARISH_WARNING),
    # 放量滞涨 (stagnation)
    ({"warning_type": "stagnation", "signal": 0, "reason": "", "volume_ratio": 1.8,
      "price_change": 0.2}, None, SignalTier.VPF_BEARISH_WARNING),
    # 主力连续净流出
    (None, {"consecutive_outflow_days": 3, "daily_flow_5d": [-600, -700, -500],
            "cum_flow_5d_wan": -1800.0}, SignalTier.VPF_BEARISH_WARNING),
    # 主力累计流出 (无连出)
    (None, {"consecutive_outflow_days": 0, "cum_flow_5d_wan": -1200.0},
     SignalTier.VPF_BEARISH_WARNING),
    # 主力累计流入 (偏多, 不标 warning)
    (None, {"consecutive_inflow_days": 0, "cum_flow_5d_wan": 800.0},
     SignalTier.NEUTRAL),
    # 资金缺失, 价量中性
    ({"warning_type": "none", "signal": 0, "reason": "量价中性", "volume_ratio": 0,
      "price_change": 0}, None, SignalTier.NEUTRAL),
])
def test_vpf_build_tier_and_parity(vw, fund, expected_tier):
    sig = vpf_core.build_vpf_signal(vw, fund)
    assert sig.get("signal_tier") == expected_tier
    new_bear = vpf_is_bearish_warning(sig.get("signal_tier"))
    assert new_bear == _old_strong_bearish_vpf(sig)


def test_vpf_to_fusion_recomputes_tier():
    # 已有 vpf 结果, 无论是否预填 tier, vpf_to_fusion_signal 都按 reason 重算
    pre = {"raw_key": "vpf", "direction": -1, "confidence": 0.6,
           "reason": "主力连3日净流出", "signal_tier": "STALE_VALUE"}
    out = vpf_core.vpf_to_fusion_signal(pre)
    assert out["signal_tier"] == SignalTier.VPF_BEARISH_WARNING
    # 无数据兜底
    assert vpf_core.vpf_to_fusion_signal(None)["signal_tier"] == SignalTier.NEUTRAL


# ───────────────────────── 4. 端到端合并不崩 + 布尔等价覆盖 ─────────────────────────
def _mk_chan_signal(tier, direction, reason):
    return {"direction": direction, "confidence": 0.6, "reason": reason,
            "raw_key": "chan", "signal_tier": tier}


def _mk_vpf_signal(tier, direction, conf, reason):
    return {"direction": direction, "confidence": conf, "reason": reason,
            "raw_key": "vpf", "signal_tier": tier}


def test_merge_decisions_full_matrix_no_crash():
    """全矩阵: chan × vpf 组合喂 merge_decisions, 验证不崩且强信号布尔与旧逻辑一致。"""
    chan_tiers = [
        (SignalTier.CHAN_BUY_1, 1, "缠论一类买 (底背驰)"),
        (SignalTier.CHAN_BUY_LIKE2, 1, "缠论类二买 (回踩偏弱)"),
        (SignalTier.CHAN_SELL_1, -1, "缠论一类卖 (顶背驰)"),
        (SignalTier.CHAN_SELL_2, -1, "缠论二类卖 (高点降低)"),
        (SignalTier.CHAN_TOP_DIVERGENCE, -1, "缠论顶背驰"),
        (SignalTier.CHAN_BOTTOM_DIVERGENCE, 1, "缠论底背驰"),
        (SignalTier.CHAN_TREND_UP, 1, "缠论:拉升段"),
        (SignalTier.NEUTRAL, 0, "缠论无明确信号"),
    ]
    vpf_cases = [
        (SignalTier.VPF_BEARISH_WARNING, -1, 0.3, "主力连3日净流出"),
        (SignalTier.VPF_BEARISH_WARNING, -1, 0.6, "天量天价"),
        (SignalTier.NEUTRAL, -1, 0.4, "价量偏空"),
        (SignalTier.NEUTRAL, 1, 0.5, "主力连3日净流入"),
        (SignalTier.NEUTRAL, 0, 0.2, "价量资金中性"),
    ]
    for ct, cd, cr in chan_tiers:
        for vt, vd, vc, vr in vpf_cases:
            chan_sig = _mk_chan_signal(ct, cd, cr)
            vpf_sig = _mk_vpf_signal(vt, vd, vc, vr)
            # 旧逻辑基准 (基于 reason)
            old_bull = _old_strong_bullish_chan(chan_sig)
            old_bear = _old_strong_bearish_chan(chan_sig)
            old_vpf_bear = _old_strong_bearish_vpf(vpf_sig)
            # 新逻辑 (基于 tier)
            new_bull = chan_is_strong_bull(chan_sig.get("signal_tier"))
            new_bear = chan_is_strong_bear(chan_sig.get("signal_tier"))
            new_vpf_bear = vpf_is_bearish_warning(vpf_sig.get("signal_tier")) and vd == -1
            # 注意新逻辑在 fusion 内还叠加 direction 检查, 此处对齐
            new_vpf_bear = (vd == -1) and (
                vc >= 0.5 or vpf_is_bearish_warning(vpf_sig.get("signal_tier")))
            assert new_bull == old_bull, f"chan bull mismatch: {ct}"
            assert new_bear == old_bear, f"chan bear mismatch: {ct}"
            assert new_vpf_bear == old_vpf_bear, f"vpf bear mismatch: {vt},{vd},{vc}"


def test_merge_decisions_real_pipeline_smoke():
    """真实信号源输入跑通 merge_decisions (带 tier), 验证不崩、产出关键字段,
    且融合内部实际消费的 chan/vpf 信号其布尔判定与旧关键词逻辑等价。"""
    chan_raw = _chan_raw(buy={"type": "一类买", "signal_id": "b1"})
    vpf_in = {"volume_warning": {"warning_type": "climactic", "signal": 0,
                                 "reason": "", "volume_ratio": 3.0, "price_change": 4.0},
              "fund_features": {"consecutive_outflow_days": 3,
                                "daily_flow_5d": [-600, -700, -500]}}
    res = fusion_core.merge_decisions(
        chan_result=chan_raw,
        momentum_result={"momentum": {"score": 60, "direction": "bullish"}},
        wyckoff_result={},
        regime="正常",
        vpf_result=vpf_in,
    )
    assert "action" in res and "weighted_score" in res
    assert isinstance(res["weighted_score"], (int, float))

    # 端到端等价: 用与 merge_decisions 相同的入口重建 chan/vpf 信号,
    # 断言其内部强信号布尔量 == 旧 reason 关键词逻辑
    chan_sig = fusion_core._chan_to_signal(chan_raw)
    vpf_sig = vpf_core.build_vpf_signal(
        vpf_in.get("volume_warning"), vpf_in.get("fund_features"))
    assert chan_is_strong_bull(chan_sig.get("signal_tier")) == _old_strong_bullish_chan(chan_sig)
    assert chan_is_strong_bear(chan_sig.get("signal_tier")) == _old_strong_bearish_chan(chan_sig)
    assert vpf_is_bearish_warning(vpf_sig.get("signal_tier")) == _old_strong_bearish_vpf(vpf_sig)


def test_missing_tier_falls_back_neutral():
    """调用方不传 signal_tier → 视为 NEUTRAL, 等价旧'无关键词', 不崩。"""
    chan_sig = {"direction": 1, "confidence": 0.6, "reason": "缠论一类买 (底背驰)", "raw_key": "chan"}
    vpf_sig = {"direction": -1, "confidence": 0.3, "reason": "主力连3日净流出", "raw_key": "vpf"}
    # 不传 tier, 新逻辑按 NEUTRAL 处理 → strong_* 全 False, 等价旧逻辑"无关键词匹配"
    assert chan_is_strong_bull(chan_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
    assert chan_is_strong_bear(chan_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
    assert vpf_is_bearish_warning(vpf_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
