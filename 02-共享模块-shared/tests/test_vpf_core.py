"""价量资金专家 (VPF) 单元测试。"""

from __future__ import annotations

from trader_shared.vpf_core import build_vpf_signal


class TestBuildVpfSignal:
    def test_fund_outflow_priority(self):
        ff = {
            "consecutive_outflow_days": 3,
            "consecutive_inflow_days": 0,
            "daily_flow_5d": [-600, -600, -600],
            "cum_flow_5d_wan": -1800,
            "flow_price_relation": "价跌资出",
        }
        sig = build_vpf_signal({"warning_type": "none", "signal": 0}, ff)
        assert sig["direction"] == -1
        assert sig["raw_key"] == "vpf"
        assert sig["fund_quality"] == "full"

    def test_missing_fund_uses_volume_only(self):
        vw = {
            "warning_type": "stagnation",
            "signal": -1,
            "confidence": 0.5,
            "reason": "放量滞涨（量比1.8，近3日+0.5%）",
            "volume_ratio": 1.8,
            "price_change": 0.5,
            "vol_label": "放量",
        }
        sig = build_vpf_signal(vw, {})
        assert sig["direction"] == -1
        assert sig["fund_quality"] == "missing"
        assert "资金未取到" in sig["reason"]
        assert "量比" in sig["reason"] or "放量" in sig["reason"]
        assert sig["confidence"] < 0.5  # 打折

    def test_flat_volume_snapshot_always_has_reason(self):
        vw = {
            "warning_type": "none",
            "signal": 0,
            "confidence": 0.2,
            "volume_ratio": 0.9,
            "price_change": -3.5,
            "vol_label": "平量",
            "reason": "平量（量比0.9，近3日-3.5%）",
        }
        sig = build_vpf_signal(vw, {})
        assert sig["direction"] == 0
        assert "0.9" in sig["reason"] or "平量" in sig["reason"]

    def test_fund_in_and_volume_ok_bullish(self):
        ff = {
            "consecutive_inflow_days": 3,
            "consecutive_outflow_days": 0,
            "daily_flow_5d": [200, 200, 200],
            "cum_flow_5d_wan": 600,
            "flow_price_relation": "价涨资入",
        }
        sig = build_vpf_signal({"warning_type": "none", "signal": 0, "reason": "量价关系正常"}, ff)
        assert sig["direction"] == 1
        assert sig["fund_quality"] == "full"

    def test_conflict_fund_in_volume_bear(self):
        """资金强信号优先：连入 conf>=0.55 时听资金，价量分歧写入 reason，不归零。"""
        ff = {
            "consecutive_inflow_days": 2,
            "consecutive_outflow_days": 0,
            "daily_flow_5d": [100, 100],
            "cum_flow_5d_wan": 200,
            "flow_price_relation": "价跌资入",
        }
        vw = {"warning_type": "climactic", "signal": -1, "confidence": 0.7, "reason": "天量天价"}
        sig = build_vpf_signal(vw, ff)
        assert sig["direction"] == 1  # 资金强信号优先，不因价量偏空归零
        assert sig["fund_direction"] == 1
        assert sig["vp_direction"] == -1
        assert sig["fund_quality"] == "full"
        assert ("连2日净进" in str(sig.get("reason") or "") or "主力连2日净流入" in str(sig.get("reason") or ""))
        assert "天量天价" in str(sig.get("reason") or "") or "价量" in str(sig.get("reason") or "")
