"""signal_schema 与 VPF 契约测试（现行；不再依赖已退役 classic mapper）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02-共享模块-shared"))
sys.path.insert(0, str(ROOT / "01-功能包-packages" / "trader" / "scripts"))

from trader_shared import fusion_core, signal_schema, vpf_core  # noqa: E402
from trader_shared.signal_schema import (  # noqa: E402
    SignalTier,
    chan_is_strong_bear,
    chan_is_strong_bull,
    vpf_is_bearish_warning,
    vpf_tier_from_reason,
)

_OLD_VPF_KW = ("天量", "滞涨", "流出", "净出")


def _old_strong_bearish_vpf(sig):
    """VPF 旧关键词语义：与 vpf_is_bearish_warning 同向，不含裸「连」误伤净流入。"""
    if sig.get("direction") != -1:
        return False
    if float(sig.get("confidence") or 0) >= 0.5:
        return True
    reason = str(sig.get("reason") or "")
    if any(k in reason for k in _OLD_VPF_KW):
        if "流出" in reason and "净流入" in reason and "净流出" not in reason and "净出" not in reason:
            pass
        else:
            return True
    if "连" in reason and (("净流出" in reason) or ("净出" in reason)) and (
        "净流入" not in reason and "净进" not in reason
    ):
        return True
    return False


def test_schema_tier_sets():
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_1)
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_2)
    assert chan_is_strong_bull(SignalTier.CHAN_BUY_3)
    assert chan_is_strong_bull(SignalTier.CHAN_BOTTOM_DIVERGENCE)
    assert not chan_is_strong_bull(SignalTier.CHAN_BUY_LIKE2)
    assert not chan_is_strong_bull(SignalTier.CHAN_TREND_UP)
    assert not chan_is_strong_bull(SignalTier.NEUTRAL)

    assert chan_is_strong_bear(SignalTier.CHAN_SELL_1)
    assert chan_is_strong_bear(SignalTier.CHAN_TOP_DIVERGENCE)
    assert not chan_is_strong_bear(SignalTier.CHAN_SELL_2)
    assert not chan_is_strong_bear(SignalTier.CHAN_SELL_3)

    assert vpf_is_bearish_warning(SignalTier.VPF_BEARISH_WARNING)
    assert not vpf_is_bearish_warning(SignalTier.NEUTRAL)


def test_vpf_tier_from_reason_parity():
    for r in ("天量天价", "放量滞涨", "主力连3日净流出", "近5日主力累计流出1200万（占比2.30%）"):
        assert vpf_tier_from_reason(r) == SignalTier.VPF_BEARISH_WARNING
    for r in ("近5日主力累计流入800万", "价量资金中性", "资金数据不足", "价量偏多"):
        assert vpf_tier_from_reason(r) == SignalTier.NEUTRAL


def test_vpf_lian_substring_tightened():
    assert _old_strong_bearish_vpf({"direction": -1, "reason": "主力连续净流入3日"}) is False
    assert vpf_tier_from_reason("主力连续净流入3日") == SignalTier.NEUTRAL
    assert vpf_tier_from_reason("主力连续净流出3日") == SignalTier.VPF_BEARISH_WARNING
    assert vpf_tier_from_reason("主力连3日净流出") == SignalTier.VPF_BEARISH_WARNING


@pytest.mark.parametrize("vw,fund,expected_tier", [
    ({"warning_type": "climactic", "signal": 0, "reason": "", "volume_ratio": 3.2,
      "price_change": 5.0}, None, SignalTier.VPF_BEARISH_WARNING),
    ({"warning_type": "stagnation", "signal": 0, "reason": "", "volume_ratio": 1.8,
      "price_change": 0.2}, None, SignalTier.VPF_BEARISH_WARNING),
    (None, {"consecutive_outflow_days": 3, "daily_flow_5d": [-600, -700, -500],
            "cum_flow_5d_wan": -1800.0}, SignalTier.VPF_BEARISH_WARNING),
    (None, {"consecutive_outflow_days": 0, "cum_flow_5d_wan": -1200.0},
     SignalTier.VPF_BEARISH_WARNING),
    (None, {"consecutive_inflow_days": 0, "cum_flow_5d_wan": 800.0},
     SignalTier.NEUTRAL),
    ({"warning_type": "none", "signal": 0, "reason": "量价中性", "volume_ratio": 0,
      "price_change": 0}, None, SignalTier.NEUTRAL),
])
def test_vpf_build_tier_and_parity(vw, fund, expected_tier):
    sig = vpf_core.build_vpf_signal(vw, fund)
    assert sig.get("signal_tier") == expected_tier
    new_bear = vpf_is_bearish_warning(sig.get("signal_tier"))
    assert new_bear == _old_strong_bearish_vpf(sig)


def test_vpf_to_fusion_recomputes_tier():
    pre = {"raw_key": "vpf", "direction": -1, "confidence": 0.6,
           "reason": "主力连3日净流出", "signal_tier": "STALE_VALUE"}
    out = vpf_core.vpf_to_fusion_signal(pre)
    assert out["signal_tier"] == SignalTier.VPF_BEARISH_WARNING
    assert vpf_core.vpf_to_fusion_signal(None)["signal_tier"] == SignalTier.NEUTRAL


def test_merge_decisions_smoke():
    chan_raw = {"chanlun": {"buy_points": [{"type": "一类买", "signal_id": "b1"}],
                            "sell_points": [], "divergence": {}}}
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


def test_missing_tier_falls_back_neutral():
    chan_sig = {"direction": 1, "confidence": 0.6, "reason": "缠论一类买 (底背驰)", "raw_key": "chan"}
    vpf_sig = {"direction": -1, "confidence": 0.3, "reason": "主力连3日净流出", "raw_key": "vpf"}
    assert chan_is_strong_bull(chan_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
    assert chan_is_strong_bear(chan_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
    assert vpf_is_bearish_warning(vpf_sig.get("signal_tier", SignalTier.NEUTRAL)) is False
