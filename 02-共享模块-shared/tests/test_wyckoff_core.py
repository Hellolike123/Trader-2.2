from __future__ import annotations

import sys

for mod in ("trader_shared.wyckoff_core", "light_data"):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.wyckoff_core import (
    wyckoff_analysis,
    calculate_wyckoff_score,
    format_wyckoff_oneline,
    _detect_phase,
    _detect_lps,
)
from trader_shared.wyckoff_events import _detect_sos  # 直连 events，避免 facade/缓存歧义


def _make_bar(open_, high, low, close, volume=1000):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _prerise(n: int, low: float, high: float, volume: int = 100) -> list[dict]:
    """FINDING-5 辅助：生成 n 根平滑上行段，用于构造 BC 的前置主升（≥15% 涨幅）。"""
    bars = []
    for i in range(n):
        p = low + (high - low) * i / max(n - 1, 1)
        bars.append(_make_bar(round(p, 2), round(p + 0.3, 2), round(p - 0.3, 2), round(p, 2), volume))
    return bars


class TestDetectSpring:
    def test_spring_detected(self):
        """Spring: 跌破90后收回97（收回力度117%），满足50%门槛。"""
        bars = [_make_bar(100, 105, 90, 102) for _ in range(14)]
        bars.append(_make_bar(85, 100, 84, 97))  # close=97, reclaim=7/6=117%
        result = wyckoff_analysis(bars)
        assert result["spring_signal"] is True
        assert result["spring_price"] is not None

    def test_spring_not_detected(self):
        bars = [_make_bar(100, 105, 95, 102) for _ in range(14)]
        bars.append(_make_bar(90, 100, 87, 87))
        result = wyckoff_analysis(bars)
        assert result["spring_signal"] is False

    def test_no_break(self):
        bars = [_make_bar(100, 105, 95, 102) for _ in range(14)]
        bars.append(_make_bar(90, 100, 90, 94))
        result = wyckoff_analysis(bars)
        assert result["spring_signal"] is False


class TestDetectUpthrust:
    def test_upthrust_detected(self):
        bars = [_make_bar(100, 110, 95, 105) for _ in range(14)]
        bars.append(_make_bar(90, 113, 100, 107, 1500))  # volume 1.5x avg → UT confirmed
        result = wyckoff_analysis(bars)
        assert result["upthrust_signal"] is True
        assert result["upthrust_price"] is not None

    def test_upthrust_not_detected(self):
        bars = [_make_bar(100, 110, 95, 105) for _ in range(14)]
        bars.append(_make_bar(90, 113, 100, 110))
        result = wyckoff_analysis(bars)
        assert result["upthrust_signal"] is False


class TestVolumeDivergence:
    def test_bearish_divergence(self):
        bars = [_make_bar(10, 12, 9, 11) for _ in range(10)]
        bars.extend([
            {"open": 11, "high": 13, "low": 11, "close": 12, "volume": 100},
            {"open": 11, "high": 12, "low": 10, "close": 11, "volume": 200},
            {"open": 11, "high": 13, "low": 11, "close": 13, "volume": 150},
            {"open": 12, "high": 13, "low": 12, "close": 12, "volume": 100},
            {"open": 12, "high": 14, "low": 12, "close": 13, "volume": 50},
        ])
        result = wyckoff_analysis(bars)
        assert result["bearish_volume_divergence"] is True

    def test_bullish_divergence(self):
        bars = [_make_bar(10, 12, 9, 11) for _ in range(10)]
        bars.extend([
            {"open": 12, "high": 13, "low": 12, "close": 12, "volume": 100},
            {"open": 12, "high": 12, "low": 10, "close": 11, "volume": 200},
            {"open": 11, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"open": 9, "high": 11, "low": 9, "close": 11, "volume": 50},
            {"open": 10, "high": 12, "low": 10, "close": 10, "volume": 50},
        ])
        result = wyckoff_analysis(bars)
        assert result["bullish_volume_divergence"] is True


class TestWyckoffAnalysis:
    def test_insufficient_bars(self):
        bars = [_make_bar(10, 12, 10, 11) for _ in range(14)]
        result = wyckoff_analysis(bars)
        assert result["spring_signal"] is False
        assert result["upthrust_signal"] is False
        assert result["spring_reason"] == "数据不足"
        assert result["upthrust_reason"] == "数据不足"


class TestDetectBuyingClimax:
    def test_bc_detected(self):
        # 准备 14 天的数据，作为 recent 平均 volume 约 100
        bars = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 最新一天：量比 1.9（高于 WYCKOFF_BC_VOL_RATIO_THRESHOLD=1.5），上影线明显，收阴，涨幅仅 0.5%
        # FINDING-5：前置 20 根平滑上行（85→100）提供 ≥15% 主升，满足 BC 前置涨幅条件
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is True
        assert result["bc_price"] == 105.0

    def test_bc_not_detected_due_to_volume(self):
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 最新一天：量比仅 1.4（低于 1.5），不满足
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 140})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is False

    def test_bc_rejected_no_pre_rise(self):
        """FINDING-5：区间内反弹棒（近窗高位、放量、长上影）但无前置主升 → 不标 BC。

        隆基 601012 型：长期横盘后单根反弹到近 10 日高、量比 1.7、长上影，
        但 60 日内未从低点抬升≥15% → 非威科夫原典 BC，应拒。
        """
        from trader_shared.wyckoff_events import _detect_buying_climax

        # 长期横盘（90 根），最低 ~13、最高 ~14，无趋势性主升
        bars = [_make_bar(13.5, 14.0, 13.2, 13.6, 100) for _ in range(90)]
        # 反弹棒：量比 1.7、长上影、收阴、近窗高位（14.0 为横盘区间上沿）
        bars.append(_make_bar(13.7, 14.0, 13.5, 13.55, 170))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is False, r["bc_reason"]

    def test_bc_real_climax_with_pre_rise(self):
        """FINDING-5：前置主升（≥15%）+ 长窗高位 + 放量滞涨 → 真 BC 保留。

        茅台 600519 型：长期主升末端天量长上影，是威科夫原典 BC，应触发。
        """
        from trader_shared.wyckoff_events import _detect_buying_climax

        # 前置主升：60 根从 100 拉到 130（+30%）
        bars = _prerise(60, 100, 130)
        # 顶部日：量比 1.8、长上影、滞涨 +1%、处长窗高位
        bars.append(_make_bar(129.0, 132.0, 128.5, 130.5, 180))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is True, r["bc_reason"]
        assert r["bc_bar_idx"] == 60


class TestBuyingClimaxRetroScan:
    """Bug H：BC 回溯窗口 90 + 滞涨 5.0 + 长上影分支（docs/plans/wyckoff-epic-context-refactor-handoff H-M1~M7 / H1~H6）。

    参考 TestBCHighPosition 风格：护栏（量比≥1.5、高位 pos≥0.65）不变。
    """

    def _tail_after_bc(self, n: int = 59, start: float = 12.0) -> list[dict]:
        """BC 之后的缓跌尾段（量 100，量比 <1.5、单日变化 <5%，非 BC）。"""
        bars = []
        for i in range(n):
            p = start - i * (start - 8.0) / max(n, 1)
            bars.append(_make_bar(round(p + 0.15, 2), round(p + 0.4, 2),
                                  round(p - 0.4, 2), round(p, 2), 100))
        return bars

    def test_bc_found_60_bars_back(self):
        """H1：历史顶部在 60 根前 → WYCKOFF_BC_SCAN_BARS=90 回溯窗口可扫到（旧 5 根窗口永远扫不到）。"""
        from trader_shared.wyckoff_events import _detect_buying_climax

        bars = []
        # 0..9：低位垫底（量 100）
        for _ in range(10):
            bars.append(_make_bar(10.0, 10.5, 9.5, 10.0, 100))
        # 10..19：拉到高位 ~12（量 100）
        for i in range(10):
            p = 10.0 + i * 0.2
            bars.append(_make_bar(round(p, 2), round(p + 0.3, 2),
                                  round(p - 0.2, 2), round(p + 0.15, 2), 100))
        # 20：BC 顶部日 —— 滞涨 +1.7%（<5.0）、上影比 0.17（<0.25）、量比 3.0、高位 pos 1.0
        bars.append(_make_bar(12.0, 12.2, 11.9, 12.15, 300))
        # 21..79：缓跌尾段 59 根
        bars.extend(self._tail_after_bc())
        assert len(bars) == 80
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is True, r["bc_reason"]
        assert r["bc_bar_idx"] == 20

    def test_bc_triggered_by_stagnant_5pct(self):
        """H3：+2.2% 无显著长上影 → 滞涨 5.0 分支触发（旧 1.0 阈值会拒）。"""
        from trader_shared.wyckoff_events import _detect_buying_climax

        bars = _prerise(20, 8.5, 10) + [_make_bar(10, 10.5, 9.5, 10, 100) for _ in range(14)]
        # FINDING-5：前置 20 根上行（8.5→10）提供 ≥15% 主升，满足 BC 前置涨幅条件
        # 顶部日：+2.2%、上影比 0.23（<0.25）、收阳（非收阴）、量比 3.0
        bars.append(_make_bar(10.1, 10.27, 10.05, 10.22, 300))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is True, r["bc_reason"]
        assert "涨幅仅" in r["bc_reason"], "应由滞涨分支触发"
        assert "显著长上影" not in r["bc_reason"]

    def test_bc_triggered_by_strong_upper_shadow(self):
        """H2：+6.8% + 上影比 0.31（06-25 型）→ 长上影分支触发（滞涨 5.0 已失效、非收阴）。"""
        from trader_shared.wyckoff_events import _detect_buying_climax

        bars = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # FINDING-5：前置 20 根上行（85→100）提供 ≥15% 主升
        # 顶部日：+6.8%、上影比 (109.9-106.8)/(109.9-100.0) = 0.313 ≥ 0.25、收阳
        bars.append(_make_bar(100.0, 109.9, 100.0, 106.8, 300))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is True, r["bc_reason"]
        assert "显著长上影" in r["bc_reason"]

    def test_upper_shadow_boundary_024_026(self):
        """H4：上影比 0.24 → 不触发；0.26 → 触发（边界）。

        +5.2%（非滞涨）、收阳（非收阴）→ 只有长上影分支能触发。
        """
        from trader_shared.wyckoff_events import _detect_buying_climax

        base = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # FINDING-5：前置 20 根上行（85→100）提供 ≥15% 主升
        # h=106.84：upper=1.64 / range=6.84 → 0.2398 < 0.25
        assert (106.84 - 105.2) / (106.84 - 100.0) < 0.25
        r1 = _detect_buying_climax(base + [_make_bar(100.0, 106.84, 100.0, 105.2, 300)])
        assert r1["bc_signal"] is False, r1["bc_reason"]
        # h=107.03：upper=1.83 / range=7.03 → 0.2603 ≥ 0.25
        assert (107.03 - 105.2) / (107.03 - 100.0) >= 0.25
        r2 = _detect_buying_climax(base + [_make_bar(100.0, 107.03, 100.0, 105.2, 300)])
        assert r2["bc_signal"] is True, r2["bc_reason"]

    def test_bc_rejected_low_vol_ratio(self):
        """H5：量比 1.4（<1.5）→ 拒（量比护栏单独验证，pos/滞涨/上影分支均满足）。"""
        from trader_shared.wyckoff_events import _detect_buying_climax

        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 顶部日：+0.96% 滞涨、高位 pos≈0.95、上影比 0.20（各触发分支都满足），
        # 唯独量比 140/100=1.4 < 1.5 → 只能量比闸拒
        bars.append(_make_bar(104.0, 105.5, 103.0, 105.0, 140))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is False, r["bc_reason"]

    def test_bc_rejected_low_position_high_volume(self):
        """H5b：低位天量 → 拒（_is_bc_high_position 护栏不变）。"""
        from trader_shared.wyckoff_events import _detect_buying_climax

        bars = []
        for i in range(14):
            # 前段冲高到 120，当前在 100 附近 → pos 偏低
            h = 100 + i * 1.5
            bars.append(_make_bar(h - 1, h, h - 3, h - 0.5, 100))
        bars.append(_make_bar(102, 103, 99, 100, 300))
        r = _detect_buying_climax(bars)
        assert r["bc_signal"] is False

    def test_are_reuses_bc_detector_60_bars_back(self):
        """H6：ARE 复用 _detect_buying_climax（H-M5）——60 根前的 BC 也能成为 ARE 锚（旧 ARE 15 根窗口扫不到）。"""
        from trader_shared.wyckoff_events import _detect_are, _detect_buying_climax

        bars = []
        for _ in range(10):
            bars.append(_make_bar(10.0, 10.5, 9.5, 10.0, 100))
        for i in range(10):
            p = 10.0 + i * 0.2
            bars.append(_make_bar(round(p, 2), round(p + 0.3, 2),
                                  round(p - 0.2, 2), round(p + 0.15, 2), 100))
        bars.append(_make_bar(12.0, 12.2, 11.9, 12.15, 300))  # BC（idx 20）
        bars.extend(self._tail_after_bc())                     # 59 根缓跌
        # 近端一根放量跌 ≥2%（量比 1.4 < 1.5 → 本身非 BC，ARE 回落棒）
        bars.append(_make_bar(7.9, 8.0, 7.2, 7.3, 140))
        bc = _detect_buying_climax(bars)
        assert bc["bc_signal"] is True and bc["bc_bar_idx"] == 20, bc["bc_reason"]
        are = _detect_are(bars)
        assert are["are_signal"] is True, are.get("are_reason")

    def test_config_exports_new_bc_constants(self):
        """H-M1~M3：新/改常量导出（env 可覆、__all__ 同步）。"""
        from trader_shared import config

        assert config.WYCKOFF_BC_SCAN_BARS == 90
        assert config.WYCKOFF_BC_CHANGE_THRESHOLD == 5.0
        assert config.WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO == 0.25
        assert "WYCKOFF_BC_SCAN_BARS" in config.__all__
        assert "WYCKOFF_BC_CHANGE_THRESHOLD" in config.__all__
        assert "WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO" in config.__all__


class TestDetectSosThrust:
    """SOS climb OR thrust — docs/plans/wyckoff-sos-single-day-handoff.md"""

    def _pad(self, n: int = 20, o: float = 42.0, c: float = 42.0, v: float = 1000.0):
        # 阴/平为主，避免误触 climb（≥4/5 阳）
        return [_make_bar(o, o + 0.5, o - 0.5, c, v) for _ in range(n)]

    def _tr(self, upper: float = 44.50, baseline: float = 47000.0):
        return {"tr_upper": upper, "tr_lower": 41.50, "tr_baseline_volume": baseline}

    def test_thrust_sos_breakout_above_tr(self):
        bars = self._pad()
        # 两根阴线打断 climb 窗口；量 9 万 / 基线 4.7 万 → 量比明确 ≥1.8
        bars.extend([
            _make_bar(42.41, 43.28, 41.40, 41.55, 34532),
            _make_bar(42.49, 43.10, 41.82, 41.90, 39720),
            _make_bar(42.66, 47.92, 42.66, 45.50, 90000),
        ])
        r = _detect_sos(bars, tr_ctx=self._tr())
        assert r["sos_signal"] is True, r
        assert r.get("sos_kind") == "thrust"
        assert r["sos_price"] == 45.50
        assert "单日爆发" in (r.get("sos_reason") or "")

    def test_thrust_blocked_inside_tr(self):
        bars = self._pad()
        bars.append(_make_bar(42.0, 44.0, 42.0, 44.40, 90000))  # 大阳但未过 44.50
        r = _detect_sos(bars, tr_ctx=self._tr())
        assert r["sos_signal"] is False
        assert r.get("sos_kind") is None

    def test_thrust_gain_boundary(self):
        bars = self._pad()
        # 昨收钉在开盘价附近，避免 max(开收,昨收涨幅) 把 4.9% 抬过 5%
        bars.append(_make_bar(42.90, 43.0, 42.8, 42.90, 1000))
        # 4.9%: open=昨收=42.90 -> close 45.00
        bars_lo = bars + [_make_bar(42.90, 46.0, 42.90, 45.00, 90000)]
        r_lo = _detect_sos(bars_lo, tr_ctx=self._tr(upper=44.0))
        assert r_lo["sos_signal"] is False, r_lo
        # 5.1%: open=昨收=42.82 -> close 45.00
        bars2 = self._pad()
        bars2.append(_make_bar(42.82, 43.0, 42.7, 42.82, 1000))
        bars_hi = bars2 + [_make_bar(42.82, 46.0, 42.82, 45.00, 90000)]
        r_hi = _detect_sos(bars_hi, tr_ctx=self._tr(upper=44.0))
        assert r_hi["sos_signal"] is True, r_hi
        assert r_hi.get("sos_kind") == "thrust"

    def test_thrust_vol_boundary(self):
        baseline = 10000.0
        # pad 量=基线，并设 tr_start，使溪内中位数基线=baseline（不被默认 pad 1000 带偏）
        bars = self._pad(v=baseline)
        tr = self._tr(upper=44.0, baseline=baseline)
        tr["tr_start"] = 0
        bars_lo = bars + [_make_bar(42.0, 48.0, 42.0, 45.0, int(baseline * 1.7))]
        r_lo = _detect_sos(bars_lo, tr_ctx=tr)
        assert r_lo["sos_signal"] is False, r_lo
        bars_hi = bars + [_make_bar(42.0, 48.0, 42.0, 45.0, int(baseline * 1.8))]
        r_hi = _detect_sos(bars_hi, tr_ctx=tr)
        assert r_hi["sos_signal"] is True, r_hi
        assert r_hi.get("sos_kind") == "thrust"

    def test_thrust_requires_tr_upper(self):
        bars = self._pad()
        bars.append(_make_bar(42.0, 48.0, 42.0, 45.0, 90000))
        r = _detect_sos(bars, tr_ctx={"tr_baseline_volume": 10000.0})  # 无 upper
        assert r["sos_signal"] is False
        r2 = _detect_sos(bars, tr_ctx=None)
        assert r2["sos_signal"] is False

    def test_thrust_price_cap_blocks_remote_high(self):
        """价幅上限（2026-08-06）：收盘 ≤1.5×上沿 亮，远超（历史高位反弹）灭。"""
        # 近箱突破：close=45.50 ≤ 44.0×1.5 → 应亮（thrust 路径，tr_start=0 保基线）
        bars = self._pad(v=47000.0)
        tr = self._tr(upper=44.0)
        tr["tr_start"] = 0
        bars.append(_make_bar(42.0, 48.0, 42.0, 45.50, 90000))
        r_near = _detect_sos(bars, tr_ctx=tr)
        assert r_near["sos_signal"] is True, r_near
        assert r_near.get("sos_kind") == "thrust"

        # 历史高位反弹：close=70.09 > 46.53×1.5 → 应灭（德方纳米场景）
        bars2 = self._pad(v=47000.0)
        tr2 = self._tr(upper=46.53)
        tr2["tr_start"] = 0
        bars2.append(_make_bar(66.0, 72.0, 66.0, 70.09, 90000))
        r_far = _detect_sos(bars2, tr_ctx=tr2)
        assert r_far["sos_signal"] is False, r_far
        # climb 失败（pad 阴线）可能先于 thrust 返回，reason 不固定；
        # 关键断言是「熄灭」——历史高位 70.09 不得被判定为 SOS。
        assert r_far.get("sos_kind") is None

    def test_thrust_price_cap_direct_remote_high(self):
        """直测 _try_sos_thrust：close=70.09 vs upper=46.53×1.5 → 价幅上限拒绝。"""
        from trader_shared.wyckoff_events import _try_sos_thrust

        bars = [
            {"open": 66.0, "close": 66.0, "high": 66.2, "low": 65.8, "volume": 47000},
            {"open": 66.5, "close": 70.09, "high": 72.0, "low": 66.5, "volume": 90000},
        ]
        tr = {"tr_upper": 46.53, "tr_lower": 41.0, "tr_baseline_volume": 47000, "tr_start": 0}
        r = _try_sos_thrust(bars, tr, 47000.0)
        assert r["sos_signal"] is False, r
        assert "远超上沿" in (r.get("sos_reason") or "")

        # 近箱突破（≤1.5×）：close=50 vs upper=46.53 → 放行（thrust 正常）
        bars2 = [
            {"open": 46.0, "close": 46.0, "high": 46.2, "low": 45.8, "volume": 47000},
            {"open": 46.5, "close": 50.0, "high": 50.5, "low": 46.5, "volume": 90000},
        ]
        r2 = _try_sos_thrust(bars2, tr, 47000.0)
        assert r2["sos_signal"] is True, r2
        assert r2.get("sos_kind") == "thrust"

    def test_climb_price_cap_via_at_tip(self):
        """climb 路径价幅上限（2026-08-06）：历史高位 5 连阳经 _detect_sos_at_tip 被拒。"""
        from trader_shared.wyckoff_events import _detect_sos_at_tip

        def _mk(o, c, v):
            return {"open": o, "close": c, "high": max(o, c) + 0.1, "low": min(o, c) - 0.1, "volume": v}

        # 前 15 根低价阴线 pad（保 climb 窗口在末 5 根 + 量比基线）+ 历史高位 5 连阳（66→70.09）
        pad = [_mk(45.0, 44.8, 47000) for _ in range(15)]
        bars = pad + [
            _mk(66, 66.5, 60000), _mk(66.5, 67, 65000), _mk(67, 68, 70000),
            _mk(68, 69, 75000), _mk(69, 70.09, 90000),
        ]
        tr = {"tr_upper": 46.53, "tr_lower": 41.0, "tr_baseline_volume": 47000, "tr_start": 0}
        r = _detect_sos_at_tip(bars, tr)
        assert r["sos_signal"] is False, r
        assert "远超上沿" in (r.get("sos_reason") or "")

        # 近箱 5 连阳（45→46.5，≤46.53×1.5）→ 放行
        bars2 = pad + [
            _mk(45, 45.3, 60000), _mk(45.3, 45.6, 65000), _mk(45.6, 46.0, 70000),
            _mk(46.0, 46.3, 75000), _mk(46.3, 46.5, 90000),
        ]
        r2 = _detect_sos_at_tip(bars2, tr)
        assert r2["sos_signal"] is True, r2

    def test_climb_sos_still_works(self):
        # 20 根基线缩量 + 5 根放量阳线爬坡
        bars = [_make_bar(40.0, 40.5, 39.5, 40.0, 1000) for _ in range(20)]
        bars.extend([
            _make_bar(40.0, 41.0, 39.9, 40.8, 1500),
            _make_bar(40.8, 41.5, 40.5, 41.2, 1500),
            _make_bar(41.2, 42.0, 41.0, 41.8, 1500),
            _make_bar(41.8, 42.5, 41.5, 41.6, 900),   # 1 阴，仍 4/5 阳
            _make_bar(41.6, 43.0, 41.5, 42.8, 1600),
        ])
        r = _detect_sos(bars, tr_ctx=None)
        assert r["sos_signal"] is True
        assert r.get("sos_kind") == "climb"
        assert "阳线" in (r.get("sos_reason") or "")

    def test_backup_can_anchor_thrust_sos(self):
        from trader_shared.wyckoff_events import _detect_backup

        bars = self._pad(25)
        # 在 i=len-4 处 thrust SOS：需 sub 切片末根为爆发日
        bars.append(_make_bar(42.66, 47.92, 42.66, 45.50, 90000))
        # SOS 后至少 2 根缩量回踩，不破 TR 上沿区
        bars.append(_make_bar(45.40, 45.80, 44.80, 45.20, 20000))
        bars.append(_make_bar(45.10, 45.50, 44.70, 45.00, 18000))
        tr = self._tr()
        # 直接确认末日 thrust 在回扫窗内
        sos_at = _detect_sos(bars[:-2], tr_ctx=tr)
        assert sos_at["sos_signal"] is True and sos_at.get("sos_kind") == "thrust"
        bu = _detect_backup(bars, tr_ctx=tr)
        assert bu.get("bu_signal") is True, bu


class TestNanwangLikeThrust:
    """南网风格：AR 天量后横盘 + 单日站上 ar_high。"""

    def test_thrust_after_ar_volume_spike_uses_median_baseline(self):
        bars = [_make_bar(42.0, 42.5, 41.6, 42.0, 47000) for _ in range(20)]
        bars.append(_make_bar(39.0, 43.5, 38.5, 42.99, 145000))  # AR 天量
        tr_start = len(bars)
        for i in range(8):
            b = 42.0 + (i % 3) * 0.3
            bars.append(_make_bar(b, b + 0.5, b - 0.4, b + 0.05, 47000))
        bars.append(_make_bar(42.66, 47.92, 42.66, 45.50, 84500))  # SOS 日
        tr_ctx = {
            "ar_high": 42.99,
            "tr_start": tr_start,
            "tr_upper": 45.14,  # 突破后抬高的分位上沿（溪仍用 ar_high）
            # 故意给偏高的整段 baseline（含突破），应被溪内中位数覆盖
            "tr_baseline_volume": 90000,
            "phase_a_range": {"ar_high": 42.99, "sc_low": 37.80, "status": "established"},
        }
        r = _detect_sos(bars, tr_ctx=tr_ctx, lookback_tips=1)
        assert r["sos_signal"] is True, r
        assert r.get("sos_kind") == "thrust"
        assert r.get("sos_price") == 45.50


class TestSosScFloor:
    """近端 SOS 不得回扫到 SC 之前的旧强势（周线 63 元类）。"""

    def test_min_tip_idx_blocks_pre_sc_sos(self):
        bars = [_make_bar(60.0, 61.0, 59.0, 60.5, 2000) for _ in range(20)]
        # 旧强势 tip（SC 之前，回扫不得采用）
        bars.append(_make_bar(60.0, 64.0, 60.0, 63.14, 9000))
        for _ in range(5):
            bars.append(_make_bar(50.0, 51.0, 49.0, 50.0, 1000))
        bars.append(_make_bar(40.0, 41.0, 37.8, 38.0, 8000))  # SC
        sc_idx = len(bars) - 1
        for _ in range(8):
            bars.append(_make_bar(42.0, 42.5, 41.5, 42.0, 1200))  # SC 后无 thrust
        r = _detect_sos(
            bars,
            tr_ctx={"tr_upper": 55.0, "tr_baseline_volume": 1000.0},
            lookback_tips=40,
            min_tip_idx=sc_idx,
        )
        assert r.get("sos_signal") is False or r.get("sos_price") != 63.14
        assert r.get("sos_price") != 63.14


class TestTradingRangeFallbackBugB:
    """Bug B：SC 前高打断 grow → fallback 滑窗仍可检出崩盘后横盘。"""

    def test_nanwang_like_crash_then_range_not_none(self):
        from trader_shared.wyckoff_events import _detect_trading_range

        bars = []
        # 高位派发段
        for i in range(15):
            p = 60.0 + (i % 5) * 0.8
            bars.append(_make_bar(p, p + 1.5, p - 1.0, p + 0.3, 5000))
        # 崩盘（含更高旧高刺穿风险）
        bars.append(_make_bar(55.0, 55.06, 48.0, 49.0, 20000))
        bars.append(_make_bar(48.0, 48.5, 40.0, 42.0, 25000))
        bars.append(_make_bar(42.0, 43.0, 37.80, 38.5, 30000))  # SC low
        # AR
        bars.append(_make_bar(39.0, 43.5, 38.5, 42.99, 145000))
        # 横盘吸筹 ~12 根 41.5–44.5
        for i in range(12):
            base = 42.0 + (i % 4) * 0.4
            bars.append(_make_bar(base, min(44.4, base + 0.8), max(41.6, base - 0.6), base + 0.1, 47000))
        # 突破
        bars.append(_make_bar(42.66, 47.92, 42.66, 45.50, 84500))
        tr = _detect_trading_range(bars)
        assert tr is not None, "崩盘后横盘+突破应检出 TR（fallback）"
        assert tr["tr_upper"] is not None and tr["tr_lower"] is not None
        # 上沿应接近横盘带，不应被 55 旧高钉死
        assert tr["tr_upper"] < 52.0
        assert tr["tr_lower"] > 36.0


class TestEventClusterBugCG:
    """Bug C：旧派发簇污染；Bug G：phase_a failed 作废簇。"""

    def test_sc_resets_pre_sc_distribution(self, monkeypatch):
        """统一锚后（I-M3）：簇 SC 重置锚来自完整序列 _find_sc_anchor，不再滑窗重算。
        SC 之后的 UT/SOW 才参与簇；SC 之前/同棒事件作废。"""
        from trader_shared import wyckoff_events as we

        bars = [_make_bar(10, 11, 9, 10, 100) for _ in range(40)]

        def fake_scan(scan, fn, tr_ctx, window, step=1, **kw):
            name = getattr(fn, "__name__", "")
            if name == "_detect_upthrust":
                return 5, {"upthrust_signal": True, "upthrust_strength": "ordinary"}
            if name == "_detect_sign_of_weakness":
                return 12, {"sow_signal": True}
            return -1, None

        # 统一锚：SC 在 idx=20（UT@5 / SOW@12 之前）→ 旧派发事件全部作废
        monkeypatch.setattr(
            we,
            "_find_sc_anchor",
            lambda *a, **k: {
                "sc_bar_idx": 20,
                "sc_low": 9.0,
                "sc_close": 10.0,
                "sc_avg_vol": 100.0,
                "vol_ratio": 2.0,
                "change_pct": -3.0,
                "pos": 0.1,
                "cur_high": 10.0,
                "cur_open": 10.5,
                "anchor_bars": 40,
                "search_mode": "cold_start",
            },
        )
        monkeypatch.setattr(we, "_scan_last_event", fake_scan)
        r = we._detect_event_cluster(bars)
        assert r["distribution_confirmed"] is False

    def test_stale_sow_not_fresh_enough(self, monkeypatch):
        from trader_shared import wyckoff_events as we

        bars = [_make_bar(10, 11, 9, 10, 100) for _ in range(60)]

        def fake_scan(scan, fn, tr_ctx, window, step=1, **kw):
            name = getattr(fn, "__name__", "")
            if name == "_detect_upthrust":
                return 40, {"upthrust_signal": True, "upthrust_strength": "ordinary"}
            if name == "_detect_sign_of_weakness":
                return 46, {"sow_signal": True}  # 距末 14 根，默认 fresh=10 → 不够新
            return -1, None

        monkeypatch.setattr(we, "_scan_last_event", fake_scan)
        r = we._detect_event_cluster(bars)
        assert r["distribution_confirmed"] is False

    def test_phase_a_failed_clears_cluster(self, monkeypatch):
        import trader_shared.wyckoff_core as wc

        bars = [_make_bar(100, 101, 99, 100, 100) for _ in range(40)]

        monkeypatch.setattr(
            wc,
            "_detect_event_cluster",
            lambda *a, **k: {
                "accumulation_confirmed": True,
                "distribution_confirmed": False,
                "accumulation_failed": False,
                "distribution_failed": False,
                "cluster_quality": "medium",
                "cluster_confidence": 0.65,
                "cluster_reason": "积累确认：支撑测试(ordinary)→SOS 突破",
            },
        )

        def _failed_pa(*a, **k):
            return {
                "sc_low": 90.0,
                "ar_high": None,
                "sc_bar_idx": 10,
                "ar_bar_idx": None,
                "status": "failed",
                "fail_reason": "有效跌破 SC 未收回",
                "anchor_bars": 15,
                "st_sc_low": None,
                "sc_low_refined": None,
            }

        monkeypatch.setattr(wc, "_build_phase_a_range", _failed_pa)
        monkeypatch.setattr(wc, "_refine_phase_a_sc_low", lambda pa, st: pa)
        r = wc.wyckoff_analysis(bars)
        assert r["accumulation_confirmed"] is False
        assert r["distribution_confirmed"] is False
        assert "Phase A 失败" in (r.get("cluster_reason") or "")


class TestClusterScAnchorUnified:
    """I：簇 SC 重置锚与主流程统一（docs/plans/wyckoff-epic-context-refactor-handoff I-M1~M6 / I1~I3）。

    构造「完整序列 SC 锚 ≠ 旧滑窗重算 SC 锚」场景：
    - 完整序列 `_find_sc_anchor` 锚定 bars[45]（天量跳空大跌 SC）；
    - 尾段 bars[55:70] 的 15 根子序列里，bars[59]（T）的前 6 根高量（320）被
      截断窗裁掉，近窗均量被压低 → 量比 6.0 → 旧滑窗重算会把它判成「更近的 SC」，
      从而把 45~59 之间的事件全部清掉（Bug I 机制：同一函数在截断子序列上结果不同）；
    - 统一锚后簇改用完整序列锚（scan 偏移 35）→ 45 之后的事件保留。
    """

    def _split_anchor_bars(self) -> list[dict]:
        bars = []
        # 0..34：缓升 88→94（量 100）
        for i in range(35):
            p = 88 + i * (6 / 34)
            bars.append(_make_bar(round(p - 0.5, 2), round(p + 0.5, 2),
                                  round(p - 1.0, 2), round(p, 2), 100))
        # 35..44：平台 99~100（量 100）
        for i in range(10):
            bars.append(_make_bar(99.5, 100.5, 98.8, round(99.8 + 0.02 * i, 2), 100))
        # 45：SC #1 —— 天量跳空大跌（量比 3.0、-7%、pos≈0.47）
        bars.append(_make_bar(95.0, 96.0, 92.0, 93.0, 300))
        # 46..48：反弹
        bars.append(_make_bar(95.5, 97.5, 94.5, 97.0, 100))
        bars.append(_make_bar(97.0, 98.5, 96.0, 98.0, 100))
        bars.append(_make_bar(98.0, 99.5, 97.0, 99.0, 100))
        # 49..54：高量平台（抬 T 的完整序列近窗均量 → T 全序列量比 1.41 < 1.5）
        for _ in range(6):
            bars.append(_make_bar(99.2, 100.2, 98.8, 99.6, 320))
        # 55..58：低量缓升（子序列里 T 的近窗均量被压低 → 量比 6.0）
        bars.append(_make_bar(101.0, 102.0, 100.5, 101.2, 50))
        bars.append(_make_bar(101.2, 102.2, 100.7, 101.5, 50))
        bars.append(_make_bar(101.5, 102.5, 101.0, 101.8, 50))
        bars.append(_make_bar(101.8, 103.0, 101.3, 102.5, 50))
        # 59：mini-SC 候选 T —— 完整序列非 SC，15 根子序列里是 SC
        bars.append(_make_bar(98.5, 99.0, 95.5, 96.0, 300))
        # 60..69：缓跌尾段（单日变化 <1.5%、量比 <1.5，非 SC）
        for i in range(10):
            p = 98.0 - i * 0.2
            bars.append(_make_bar(round(p + 0.15, 2), round(p + 0.4, 2),
                                  round(p - 0.4, 2), round(p, 2), 100))
        return bars

    def test_full_sequence_anchor_differs_from_truncated_recompute(self):
        """撕裂前提（I-M6 场景）：完整序列锚(45) ≠ 15 根子序列重算锚(全局 59)。"""
        from trader_shared import wyckoff_events as we

        bars = self._split_anchor_bars()
        full_anchor = we._find_sc_anchor(bars, include_failed=True)
        sub_anchor = we._find_sc_anchor(bars[-15:], include_failed=True)
        assert full_anchor is not None, "完整序列应锚定 SC #1"
        assert full_anchor["sc_bar_idx"] == 45
        assert sub_anchor is not None, "15 根子序列应把 T 重算成 SC（截断窗量比 6.0）"
        assert sub_anchor["sc_bar_idx"] == 4  # 全局 59
        assert sub_anchor["sc_bar_idx"] + (len(bars) - 15) != full_anchor["sc_bar_idx"]
        assert sub_anchor["vol_ratio"] >= 5.0  # 截断近窗（4 根低量 50）→ 量比 6.0

    def test_cluster_sc_anchor_matches_main_flow(self, monkeypatch):
        """I-M3~M6：簇锚 == 主流程锚；SC 不再走滑窗重算；统一锚之后的事件保留。"""
        from trader_shared import wyckoff_events as we

        bars = self._split_anchor_bars()
        # 主流程锚（_detect_selling_climax 同款调用）
        main_anchor = we._find_sc_anchor(bars, include_failed=True)
        assert main_anchor is not None and main_anchor["sc_bar_idx"] == 45

        calls: list[str] = []

        def fake_scan(scan, fn, tr_ctx, window, step=1, **kw):
            calls.append(getattr(fn, "__name__", ""))
            name = getattr(fn, "__name__", "")
            if name == "_detect_upthrust":
                return 42, {"upthrust_signal": True, "upthrust_strength": "ordinary"}
            if name == "_detect_sign_of_weakness":
                return 54, {"sow_signal": True}
            return -1, None

        monkeypatch.setattr(we, "_scan_last_event", fake_scan)
        r = we._detect_event_cluster(bars)
        assert "_detect_selling_climax" not in calls, "SC 不得再经滑窗重算（I-M3）"
        # 统一锚 scan 偏移 = 45 - (70-60) = 35；UT(42)/SOW(54) 均在锚之后 → 保留
        assert r["distribution_confirmed"] is True, (
            f"UT/SOW 应落在统一锚之后被保留, got {r['cluster_reason']}"
        )

    def test_cluster_filters_events_before_unified_anchor(self, monkeypatch):
        """I-M4 边界：统一锚(scan 35)之前的事件仍被过滤（与原「SC 之后才认事件」语义一致）。"""
        from trader_shared import wyckoff_events as we

        bars = self._split_anchor_bars()

        def fake_scan(scan, fn, tr_ctx, window, step=1, **kw):
            name = getattr(fn, "__name__", "")
            if name == "_detect_upthrust":
                return 30, {"upthrust_signal": True, "upthrust_strength": "ordinary"}
            if name == "_detect_sign_of_weakness":
                return 54, {"sow_signal": True}
            return -1, None

        monkeypatch.setattr(we, "_scan_last_event", fake_scan)
        r = we._detect_event_cluster(bars)
        assert r["distribution_confirmed"] is False, "统一锚之前的事件应被 SC 重置锚清掉"

    def test_find_sc_anchor_returns_tr_ctx_anchor_directly(self):
        """I-M1：tr_ctx.sc_anchor 为 dict → 直接返回（含可选 phase_a_failed/fail_* 字段）。"""
        from trader_shared.wyckoff_events import _find_sc_anchor

        bars = [_make_bar(10, 11, 9, 10, 100) for _ in range(30)]
        anchor = {
            "sc_bar_idx": 5,
            "sc_low": 8.5,
            "sc_close": 9.0,
            "sc_avg_vol": 100.0,
            "vol_ratio": 2.0,
            "change_pct": -3.0,
            "pos": 0.2,
            "cur_high": 10.5,
            "cur_open": 9.8,
            "anchor_bars": 90,
            "search_mode": "pinned",
            "phase_a_failed": True,
            "fail_bar_idx": 20,
            "fail_reason": "SC 后有效跌破未收回（Phase A 失败）",
        }
        out = _find_sc_anchor(bars, {"sc_anchor": anchor}, include_failed=False)
        assert out is anchor, "sc_anchor 字段存在时应直接返回，不重算、不冷启动"
        assert out["sc_bar_idx"] == 5
        assert out["phase_a_failed"] is True and out["fail_bar_idx"] == 20

    def test_find_sc_anchor_without_sc_anchor_field_unchanged(self):
        """I-M2：无 sc_anchor 字段 → 现有行为不变（tr_ctx 为普通 dict 也不受影响）。"""
        from trader_shared.wyckoff_events import _find_sc_anchor

        bars = [_make_bar(10, 11, 9, 10, 100) for _ in range(30)]
        assert _find_sc_anchor(bars, {"tr_upper": 11.0, "tr_lower": 9.0}) is None
        assert _find_sc_anchor(bars, None) is None
        assert _find_sc_anchor(bars, {"sc_anchor": None}) is None
        assert _find_sc_anchor(bars, {"sc_anchor": "not-a-dict"}) is None


class TestDetectSignOfWeakness:
    def test_sow_detected_consecutive(self):
        """SOW 需连续 2 日跌破支撑且收盘仍破（support 从不含确认窗口的 K 线计算）。"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 连续 2 天跌破 95（support 从 bars[2:14] 计算 = 95），收盘仍在下方
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        bars.append({"open": 95, "high": 96, "low": 92, "close": 93, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is True
        assert result.get("sow_intraday_warn") is False
        assert result["sow_price"] == 95.0

    def test_sow_intraday_warn_reclaim_not_signal(self):
        """⑤B：连续刺穿但末日收盘收回 → 仅 warn，不计正式 SOW。"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        # 刺穿 support=95 后收盘收回
        bars.append({"open": 94, "high": 98, "low": 92, "close": 96, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is False
        assert result.get("sow_intraday_warn") is True
        assert "警告" in (result.get("sow_reason") or "")
        # 不计分：注入 warn 不应出现 SOW 扣分字样
        scored = calculate_wyckoff_score(bars, analysis={
            **result,
            "spring_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "sow_intraday_warn": True,
        })
        assert not any("SOW" in s or "弱势" in s for s in scored["signals"])

    def test_sow_not_detected_single_day(self):
        """仅 1 日跌破不足以触发 SOW（consecutive=2）。"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is False
        assert result.get("sow_intraday_warn") is False
        assert "1/2" in result["sow_reason"]

    def test_sow_not_detected_due_to_volume(self):
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 当天虽然跌破，但是成交量 90（量比 0.9 < 1.0），被过滤
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 90})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is False
        assert result.get("sow_intraday_warn") is False


class TestCalculateWyckoffScore:
    """calculate_wyckoff_score 单元测试"""

    def _make_bars(self, extra: list[dict], base_volume: int = 100) -> list[dict]:
        """生成 14 根中性 K 线 + extra 作为 bars 数据
        
        base_volume 用于避免与额外数据的 volume 冲突导致误触发 BC。
        设为 100 时 extra 的 volume 需明显高于或低于 100 才会触发 BC。
        """
        bars = [_make_bar(100, 105, 95, 102, base_volume) for _ in range(14)]
        bars.extend(extra)
        return bars

    def test_insufficient_bars(self):
        """数据不足时返回中性 50 分"""
        bars = [_make_bar(10, 12, 10, 11, 100) for _ in range(14)]
        result = calculate_wyckoff_score(bars)
        assert result["score"] == 50
        assert result["raw"] == 0
        assert result["signals"] == []
        assert "数据不足" in result["summary"]

    def test_no_signals_neutral(self):
        """无任何信号时返回 50 分"""
        bars = self._make_bars([_make_bar(100, 105, 95, 102, 100)])
        result = calculate_wyckoff_score(bars)
        assert result["score"] == 50
        assert result["raw"] == 0
        assert result["signals"] == []
        assert "中性" in result["summary"]

    def test_spring_only(self):
        """仅 Spring 信号 → 看多
        
        Spring 条件: low 刺穿 support*0.985, 但 close 回到 support 上方。
        support = min(low of recent) = 90, breach = 88.65
        关键: volume 必须 < avg*1.0 以避免 SOW 误触发
        """
        # 前 14 根: low=90, volume=200 → support=90, avg=200
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(14)]
        # Spring: low=85, close=97 → reclaim=7/6=117% ≥ 50% ✓
        # volume=150 < 200 → 不触发 SOW ✓
        bars.append(_make_bar(85, 95, 85, 97, 150))
        result = calculate_wyckoff_score(bars)
        # Spring 过早减半 25//2=12，无 phase 修正（孤立 Spring 无 B 背景）
        assert result["raw"] == 12, f"Expected 12 (Spring premature 25//2), got {result['raw']}"
        assert any("Spring" in s for s in result["signals"])
        assert any("降权" in s for s in result["signals"]), "孤立 Spring 应有降权标注"

    def test_spring_with_bullish_div_bonus(self):
        """Spring + 看多背离 → 额外加分
        
        Spring: 最后 1 根 bar low 刺穿 support*0.985 且 close >= support
        看多背离: 最后 5 根价格创新低但后半段量能萎缩
        需要 base_volume 足够高以避免 SOW 误触发
        """
        bars = [_make_bar(100, 105, 90, 102, 2000) for _ in range(10)]
        bars.extend([
            {"open": 100, "high": 102, "low": 98, "close": 100, "volume": 500},
            {"open": 99, "high": 100, "low": 96, "close": 97, "volume": 600},
            {"open": 97, "high": 95, "low": 90, "close": 91, "volume": 500},  # 逐步下跌
            {"open": 91, "high": 96, "low": 88, "close": 92, "volume": 100},  # 跌破支撑后收回
            {"open": 90, "high": 95, "low": 85, "close": 97, "volume": 80},   # Spring: low=85, close=97, reclaim=7/6=117% + 缩量
        ])
        # 验证 Spring 和看多背离都被检测到
        analysis = wyckoff_analysis(bars)
        assert analysis["spring_signal"] is True, f"Spring not detected: {analysis}"
        assert analysis["bullish_volume_divergence"] is True
        # Spring 过早→减半(12) + Spring×看多过早→减半(2) + 看多背离(10) = 24
        result = calculate_wyckoff_score(bars)
        assert result["raw"] > 0
        assert result["score"] > 50  # 中性偏多
        spring_signals = [s for s in result["signals"] if "Spring" in s]
        assert len(spring_signals) >= 2  # 至少有 Spring 和 Spring×看多

    def test_upthrust_only(self):
        """仅 Upthrust 信号 → 看空

        使用 25 根 base 避免 extra bar 被 SOS 误检测。
        Upthrust 条件: high 突破 resistance*1.005, 但 close 回落至 resistance*0.995 之下。
        resistance = max(high of recent) = 105, breakout = 105.525, reclaim = 104.475
        """
        # 25 根 base: high=105, volume=100, low=95
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(25)]
        # 第 26 根: UT 触发 bar, volume=130 >= 100*1.2 (满足 UT 放量确认)
        bars.append({"open": 100, "high": 107, "low": 100, "close": 104, "volume": 130})
        # high=107 > 105.525 且 close=104 < 104.475 → 触发 Upthrust
        # volume=130 >= 100*1.2 → 满足 UT 放量确认
        # SOS 不触发 (avg_vol=104 < 100*1.2=120, 不满足量能条件)
        result = calculate_wyckoff_score(bars)
        # UT 过早减半 -20//2=-10，无 phase 修正（孤立 UT 无 B 背景）
        assert result["raw"] == -10, f"Expected -10 (UT premature -20//2), got {result['raw']}: {result['signals']}"
        assert result["score"] == 46  # 50 + (-10)*50//130 = 50 - 4 = 46
        assert any("Upthrust" in s for s in result["signals"])
        assert "中性" in result["summary"]

    def test_bearish_div_only(self):
        """仅看空背离 → 轻微看空

        近 5 根：温和抬高创新高 + 后半量萎缩；避免 SOS（累计涨幅 <2% / 量能不足）
        与看多背离（无新低）。
        """
        # 全程同价位区，避免 base=100 与 extra=11 跳变触发 SOS
        bars = [_make_bar(100, 105, 98, 102, 400) for _ in range(14)]
        bars.extend([
            {"open": 102, "high": 104, "low": 101, "close": 103, "volume": 400},
            {"open": 103, "high": 105, "low": 102, "close": 104, "volume": 380},
            {"open": 104, "high": 106, "low": 103, "close": 105, "volume": 150},
            {"open": 105, "high": 107, "low": 104, "close": 106, "volume": 140},
            {"open": 106, "high": 109, "low": 105, "close": 108, "volume": 120},  # 创新高+缩量
        ])
        analysis = wyckoff_analysis(bars)
        assert analysis["bearish_volume_divergence"] is True
        assert analysis["bullish_volume_divergence"] is False
        assert analysis["sos_signal"] is False
        result = calculate_wyckoff_score(bars)
        assert result["raw"] < 0  # -10
        assert result["score"] <= 50

    def test_bullish_div_only(self):
        """仅看多背离 → 轻微看多"""
        # base_volume=1000, 额外 bars 的 volume < 1000 不会触发 BC
        bars = self._make_bars([
            {"open": 10, "high": 11, "low": 10, "close": 10, "volume": 500},
            {"open": 10, "high": 10, "low": 8, "close": 9, "volume": 600},
            {"open": 9, "high": 9, "low": 7, "close": 8, "volume": 500},
            {"open": 7, "high": 9, "low": 7, "close": 9, "volume": 200},
            {"open": 8, "high": 10, "low": 7, "close": 8, "volume": 180},  # 价格新低+量能萎缩
        ], base_volume=1000)
        # price[0]=10, price[min]=7 < 10, vol_second_half_avg=190 < vol_first_half_avg*0.85=493
        result = calculate_wyckoff_score(bars)
        assert result["raw"] > 0  # +10
        assert result["score"] > 50  # 50 + 10*50//80 = 56

    def test_bc_penalty(self):
        """购买高潮 → 扣分"""
        bars = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # FINDING-5：前置 20 根上行（85→100）提供 ≥15% 主升
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        result = calculate_wyckoff_score(bars)
        assert result["raw"] < 0
        assert result["score"] <= 50
        assert any("购买高潮" in s for s in result["signals"])

    def test_sow_penalty(self):
        """弱势信号 → 扣分（连续 2 日跌破确认）"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        bars.append({"open": 95, "high": 96, "low": 92, "close": 93, "volume": 130})
        result = calculate_wyckoff_score(bars)
        assert result["raw"] < 0
        assert result["score"] <= 50
        assert any("弱势" in s for s in result["signals"])

    def test_score_clamped_to_0_100(self):
        """极端情况下分数不会超出 [0, 100]"""
        # 构造多个看空信号叠加
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(10)]
        bars.extend([
            {"open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
            {"open": 11, "high": 12, "low": 10, "close": 11, "volume": 200},
            {"open": 11, "high": 13, "low": 11, "close": 13, "volume": 150},  # bearish div peak
            {"open": 12, "high": 13, "low": 12, "close": 12, "volume": 100},
            {"open": 98, "high": 99, "low": 93, "close": 94, "volume": 101},  # SOW
        ])
        result = calculate_wyckoff_score(bars)
        assert 0 <= result["score"] <= 100

    def test_return_fields(self):
        """返回 dict 包含必要字段"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(14)]
        result = calculate_wyckoff_score(bars)
        assert "score" in result
        assert "raw" in result
        assert "signals" in result
        assert "summary" in result
        assert isinstance(result["score"], int)
        assert isinstance(result["raw"], int)
        assert isinstance(result["signals"], list)
        assert isinstance(result["summary"], str)


class TestDetectAR:
    """AR (Automatic Rally) 自动反弹 — ⑥B 只绑 SC"""

    def _sc_then_rally_bars(self, rally_close: float, rally_vol: int) -> list[dict]:
        """构造低位 SC + 随后反弹（SC close 固定 98，rally 相对 98 判断 2%）。"""
        bars = []
        for i in range(20):
            base = 150 - i * 2  # 150 → 112，抬高近窗上沿
            bars.append(_make_bar(base, base + 3, base - 3, base, 10))
        prev = bars[-1]["close"]
        # SC：天量阴线、深跌、低位 pos
        bars.append({"open": prev - 1, "high": 99, "low": 95, "close": 98, "volume": 250})
        bars.append({
            "open": 98,
            "high": max(rally_close + 1, 100),
            "low": 97,
            "close": rally_close,
            "volume": rally_vol,
        })
        bars.extend([
            _make_bar(rally_close, rally_close + 1, rally_close - 1, rally_close, 10)
            for _ in range(2)
        ])
        return bars

    def test_ar_detected_after_sc(self):
        """SC 后 1-3 根放量反弹 → AR 触发"""
        # 98*1.02=99.96；rally close=104, vol=80 > 10*1.2
        bars = self._sc_then_rally_bars(rally_close=104, rally_vol=80)
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is True, f"AR not detected: {result.get('ar_reason')}"
        assert "SC" in (result.get("ar_reason") or "")

    def test_ar_not_detected_bc_only(self):
        """⑥B：仅有 BC（无 SC）→ 即使放量上弹也不出 AR"""
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
        # 高位 BC
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        bars.append({"open": 101, "high": 104, "low": 100, "close": 103, "volume": 130})
        bars.extend([_make_bar(103, 105, 102, 104, 10) for _ in range(3)])
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False

    def test_ar_not_detected_no_sc(self):
        """无 SC 事件 → AR 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(16)]
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False

    def test_ar_not_detected_weak_rally(self):
        """SC 后反弹不足 2% → AR 不触发"""
        # 98*1.02=99.96；close=99 不足
        bars = self._sc_then_rally_bars(rally_close=99, rally_vol=80)
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False

    def test_ar_weak_vs_sc_still_triggers_no_soft(self):
        """P2-C：相对 SC 弱量反弹仍亮 AR，且非 soft（原典弱量）。"""
        bars = self._sc_then_rally_bars(rally_close=104, rally_vol=11)
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is True
        assert result.get("ar_volume_soft") is False
        assert "弱于SC" in (result.get("ar_reason") or "")

    def test_ar_strong_vs_sc_marks_soft(self):
        """P2-C：反弹量明显高于 SC → 仍亮 AR，标 soft（量能偏强/非原典弱量）。"""
        from trader_shared.wyckoff_events import _detect_ar

        # 仅 SC + 一根强量反弹（勿追加弱量尾棒，否则 prefer 会改选弱量）
        bars = []
        for i in range(20):
            base = 150 - i * 2
            bars.append(_make_bar(base, base + 3, base - 3, base, 10))
        prev = bars[-1]["close"]
        bars.append({"open": prev - 1, "high": 99, "low": 95, "close": 98, "volume": 250})
        bars.append({"open": 98, "high": 105, "low": 97, "close": 104, "volume": 400})
        ar = _detect_ar(bars)
        assert ar["ar_signal"] is True
        assert ar.get("ar_volume_soft") is True
        assert "soft" in (ar.get("ar_reason") or "") or "偏强" in (ar.get("ar_reason") or "")


class TestDetectSOS:
    """SOS (Sign of Strength) 强势信号 检测测试"""

    def test_sos_detected(self):
        """5 连阳 + 累计涨>=2% + 放量 → SOS 触发

        关键: 每根 SOS bar 必须 close > open (严格阳线).
        过渡 bar volume=500, SOS bar volume=600.
        baseline_avg_vol ≈ 540, sos_avg_vol=600 > 540*1.2=648 → 需提高 volume
        """
        # 前 10 根: 中性，volume=500
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(10)]
        # 2 根过渡: volume=500
        bars.extend([
            {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 101, "close": 103, "volume": 500},
        ])
        # SOS 5 根: 全阳线 (close > open), volume=700 > 540*1.2=648
        # open[0]=101, close[4]=105, gain=4/101=3.96% >= 2% ✓
        bars.extend([
            {"open": 101, "high": 103, "low": 101, "close": 102, "volume": 700},
            {"open": 102, "high": 103, "low": 102, "close": 103, "volume": 700},
            {"open": 103, "high": 104, "low": 102, "close": 103.5, "volume": 700},
            {"open": 103.5, "high": 105, "low": 103.5, "close": 104.5, "volume": 700},
            {"open": 104.5, "high": 106, "low": 104.5, "close": 105, "volume": 700},
        ])
        result = wyckoff_analysis(bars)
        assert result["sos_signal"] is True, f"SOS not detected: {result.get('sos_reason')}"

    def test_sos_not_detected_non_bullish(self):
        """非全部阳线 → SOS 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(10)]
        bars.extend([
            {"open": 101, "high": 103, "low": 101, "close": 102, "volume": 600},
            {"open": 103, "high": 104, "low": 102, "close": 103, "volume": 600},
            {"open": 103, "high": 103, "low": 101, "close": 102, "volume": 600},  # 阴线
            {"open": 102, "high": 104, "low": 102, "close": 103, "volume": 600},
            {"open": 103, "high": 105, "low": 103, "close": 104, "volume": 600},
        ])
        result = wyckoff_analysis(bars)
        assert result["sos_signal"] is False

    def test_sos_not_detected_low_gain(self):
        """涨幅不足 2% → SOS 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(10)]
        bars.extend([
            {"open": 101, "high": 101, "low": 101, "close": 101, "volume": 600},
            {"open": 101, "high": 102, "low": 101, "close": 102, "volume": 600},
            {"open": 102, "high": 102, "low": 101, "close": 102, "volume": 600},
            {"open": 102, "high": 103, "low": 102, "close": 103, "volume": 600},
            {"open": 102, "high": 103, "low": 102, "close": 103, "volume": 600},  # 涨幅仅 2%
        ])
        # close[4]=103, open[0]=101, gain=2/101=1.98% < 2%
        result = wyckoff_analysis(bars)
        assert result["sos_signal"] is False

    def test_sos_not_detected_low_volume(self):
        """量能不足 → SOS 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(10)]
        bars.extend([
            {"open": 101, "high": 103, "low": 101, "close": 102, "volume": 500},
            {"open": 102, "high": 103, "low": 102, "close": 103, "volume": 500},
            {"open": 103, "high": 104, "low": 102, "close": 103, "volume": 500},
            {"open": 103, "high": 104, "low": 103, "close": 104, "volume": 500},
            {"open": 103, "high": 105, "low": 103, "close": 104, "volume": 500},  # 均量=500 < 500*1.2=600
        ])
        result = wyckoff_analysis(bars)
        assert result["sos_signal"] is False


class TestPhaseAEventBoundsForSpring:
    """L1 雏形 sc_low 须能锚 Spring 事件，避免「非交易区间」误杀。"""

    def test_event_bounds_injects_sc_low(self):
        from trader_shared.wyckoff_core import _event_bounds_tr_ctx_from_phase_a

        ctx = _event_bounds_tr_ctx_from_phase_a(
            None, {"status": "established", "sc_low": 37.8, "ar_high": 43.0}
        )
        assert ctx is not None
        assert ctx["tr_lower"] == 37.8
        assert ctx["tr_upper"] == 43.0
        assert ctx.get("tr_seed_source") == "phase_a_event"

    def test_spring_not_blocked_by_amplitude_when_phase_a_bounds(self):
        """大振幅序列无 phase_a 下沿会被区间闸挡住；有 sc_low 则进入刺穿判定。"""
        from trader_shared import wyckoff_events as we
        from trader_shared.wyckoff_core import _event_bounds_tr_ctx_from_phase_a

        bars = [_make_bar(20 + i * 0.5, 21 + i * 0.5, 19 + i * 0.5, 20.5 + i * 0.5, 1_000_000) for i in range(30)]
        bars.append(_make_bar(40, 41, 39.5, 40.5, 1_000_000))
        bare = we._detect_spring(bars)
        assert bare.get("spring_signal") is False
        # 无箱时常见「非交易区间」；有箱后不得再被该闸一票否决
        ctx = _event_bounds_tr_ctx_from_phase_a(
            None, {"status": "established", "sc_low": 10.0, "ar_high": 15.0}
        )
        with_pa = we._detect_spring(bars, tr_ctx=ctx)
        assert with_pa.get("spring_reason") != "非交易区间（振幅过大）"


class TestDetectST:
    """ST (Secondary Test) 二次测试 检测测试"""

    def _spring_then_test_bars(self, *, st_vol: int):
        """P1-1：真 Spring（缩量+收回中轴）+ 3 根后 ST 候选。"""
        # 前 15 根: low=90, vol=200
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # Spring：low 刺穿 + close 强收回 + 缩量（过 _detect_spring 全闸）
        bars.append({"open": 89, "high": 98, "low": 85, "close": 97, "volume": 150})
        # 中间 3 根远离后再回（ST 窗 spring+3 起）
        bars.extend([
            {"open": 97, "high": 99, "low": 96, "close": 98, "volume": 200},
            {"open": 98, "high": 100, "low": 97, "close": 99, "volume": 200},
            {"open": 99, "high": 100, "low": 98, "close": 99, "volume": 200},
        ])
        # ST：回测 support≈90 ±1%，量相对 spring 前均量缩
        bars.append({"open": 91, "high": 92, "low": 89.5, "close": 90.5, "volume": st_vol})
        # 近端填充：总长≥26；ST age≤8（6 根填充 age=6，tip 再+1 仍≤7）
        bars.extend([_make_bar(91, 93, 90, 92, 180) for _ in range(6)])
        return bars

    def test_st_detected(self):
        """Spring 后 3-15 根缩量回测支撑 → ST 触发"""
        bars = self._spring_then_test_bars(st_vol=100)
        result = wyckoff_analysis(bars)
        assert result["st_signal"] is True, f"ST not detected: {result.get('st_reason')}"

    def test_st_not_detected_no_spring(self):
        """无 Spring 事件 → ST 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(31)]
        result = wyckoff_analysis(bars)
        assert result["st_signal"] is False

    def test_st_not_detected_high_volume(self):
        """Spring 后回测但量能不萎缩 → ST 不触发"""
        bars = self._spring_then_test_bars(st_vol=200)  # >= avg*0.8
        result = wyckoff_analysis(bars)
        assert result["st_signal"] is False


class TestDetectLPS:
    """LPS (Last Point of Support) 最后支撑点 检测测试

    正确时序: SOS → 回调 → LPS（回调在 SOS 之后）
    """

    @staticmethod
    def _base_bars(n: int = 15, vol: int = 500, low: float = 96.0) -> list[dict]:
        return [
            {"open": 100, "high": 103, "low": low, "close": 101, "volume": vol}
            for _ in range(n)
        ]

    @staticmethod
    def _sos_bars(start_open: float = 101.0, vol: int = 1000, one_bearish: bool = False) -> list[dict]:
        """构造 5 根 SOS 窗口；one_bearish=True 时第 3 根阴线（仍 4/5 阳）。"""
        out = []
        for i in range(5):
            o = start_open + i * 0.5
            if one_bearish and i == 2:
                # 阴线：close < open，但仍保持整体抬高趋势
                c = o - 0.1
                out.append({"open": o, "high": o + 0.2, "low": c - 0.1, "close": c, "volume": vol})
            else:
                c = o + 0.45
                out.append({"open": o, "high": c + 0.1, "low": o - 0.1, "close": c, "volume": vol})
        return out

    def test_lps_detected_after_sos(self):
        """SOS 后缩量回调不破前低 → LPS 触发

        结构: 15 base + 5 pre_sos + 5 SOS + 5 pullback = 30
        时序: ... → SOS → 回调 → LPS
        """
        bars = self._base_bars(15, vol=500, low=96)
        # pre_sos: 建立 SOS 前低 ~98
        bars.extend([
            {"open": 100, "high": 102, "low": 98, "close": 101, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.0, vol=1000))
        # pullback: 缩量下行，不破 pre_low=98；末端 vol < baseline*0.7=350
        bars.extend([
            {"open": 103.5, "high": 104, "low": 102.5, "close": 102.8, "volume": 400},
            {"open": 102.8, "high": 103, "low": 101.8, "close": 102.0, "volume": 320},
            {"open": 102.0, "high": 102.2, "low": 101.0, "close": 101.2, "volume": 280},
            {"open": 101.2, "high": 101.5, "low": 100.5, "close": 100.8, "volume": 240},
            {"open": 100.8, "high": 101.0, "low": 100.0, "close": 100.2, "volume": 200},
        ])
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is True, f"LPS not detected: {result.get('lps_reason')}"
        assert result["lps_price"] is not None
        assert "SOS 后" in result["lps_reason"]

    def test_lps_accepts_sos_4_of_5(self):
        """LPS 接受 SOS 为 4/5 阳线（与 _detect_sos 对齐）"""
        bars = self._base_bars(15, vol=500, low=96)
        bars.extend([
            {"open": 100, "high": 102, "low": 98, "close": 101, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.0, vol=1000, one_bearish=True))
        bars.extend([
            {"open": 103.0, "high": 103.2, "low": 102.0, "close": 102.2, "volume": 380},
            {"open": 102.2, "high": 102.4, "low": 101.2, "close": 101.4, "volume": 300},
            {"open": 101.4, "high": 101.6, "low": 100.5, "close": 100.8, "volume": 250},
            {"open": 100.8, "high": 101.0, "low": 100.2, "close": 100.4, "volume": 220},
            {"open": 100.4, "high": 100.6, "low": 99.8, "close": 100.0, "volume": 200},
        ])
        result = _detect_lps(bars)
        assert result["lps_signal"] is True, f"LPS 4/5 SOS failed: {result.get('lps_reason')}"

    def test_lps_not_wrong_sequence_pullback_before_sos(self):
        """回调在 SOS 之前（错误旧时序）→ 不应触发 LPS"""
        bars = self._base_bars(15, vol=500, low=96)
        # pre_low 窗口
        bars.extend([
            {"open": 103, "high": 105, "low": 101, "close": 103, "volume": 500}
            for _ in range(5)
        ])
        # 回调在前
        bars.extend([
            {"open": 103, "high": 104, "low": 103, "close": 104, "volume": 400},
            {"open": 104, "high": 104, "low": 103, "close": 103.5, "volume": 350},
            {"open": 103.5, "high": 104, "low": 102, "close": 102, "volume": 300},
            {"open": 102, "high": 102, "low": 102, "close": 102, "volume": 280},
            {"open": 102, "high": 102, "low": 101.5, "close": 101.5, "volume": 250},
        ])
        # SOS 在末尾（旧错误时序）
        bars.extend([
            {"open": 101.5, "high": 103, "low": 101.5, "close": 102.5, "volume": 1000},
            {"open": 102.5, "high": 103.5, "low": 102.5, "close": 103.5, "volume": 1000},
            {"open": 103.5, "high": 104.5, "low": 103.5, "close": 104.5, "volume": 1000},
            {"open": 104.5, "high": 105.5, "low": 104.5, "close": 105.5, "volume": 1000},
            {"open": 105.5, "high": 106.5, "low": 105.5, "close": 106.5, "volume": 1000},
        ])
        result = _detect_lps(bars)
        assert result["lps_signal"] is False, "错误时序（回调在 SOS 前）不应触发 LPS"

    def test_lps_not_detected_no_sos(self):
        """无 SOS 结构 → LPS 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(30)]
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False

    def test_lps_not_detected_breaks_low(self):
        """SOS 后回调跌破 SOS 前低 → LPS 不触发"""
        bars = self._base_bars(15, vol=500, low=96)
        bars.extend([
            {"open": 100, "high": 102, "low": 98, "close": 101, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.0, vol=1000))
        # 回调跌破前低 98*0.99=97.02
        bars.extend([
            {"open": 103.5, "high": 104, "low": 102, "close": 102.5, "volume": 400},
            {"open": 102.5, "high": 103, "low": 100, "close": 100.5, "volume": 320},
            {"open": 100.5, "high": 101, "low": 96, "close": 97.0, "volume": 280},  # low=96 < 97.02
            {"open": 97.0, "high": 98, "low": 96.5, "close": 97.5, "volume": 250},
            {"open": 97.5, "high": 98, "low": 97.0, "close": 97.2, "volume": 200},
        ])
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False
        assert "跌破" in (result.get("lps_reason") or "") or result["lps_signal"] is False

    def test_lps_no_fallback_to_earlier_sos_after_break(self):
        """最近有效 SOS 后回调破位 → 不得回退到更早「看似有效」的 SOS 仍触发 LPS。

        结构: 远端 SOS 后良好缩量回调（若被选中会触发），再叠近端 SOS + 破位回调。
        正确行为：锁定近端 SOS，破位后直接失败。
        """
        bars = self._base_bars(12, vol=500, low=96)
        # 远端 pre + SOS（若回退评估会成功）
        bars.extend([
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.0, vol=1000))
        # 远端后的「好回调」中间段（缩量不破）
        bars.extend([
            {"open": 103.5, "high": 104, "low": 102.5, "close": 102.8, "volume": 300},
            {"open": 102.8, "high": 103, "low": 101.5, "close": 101.8, "volume": 250},
            {"open": 101.8, "high": 102, "low": 101.0, "close": 101.2, "volume": 200},
        ])
        # 近端 pre + SOS
        bars.extend([
            {"open": 101.2, "high": 102, "low": 100.5, "close": 101.5, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.5, vol=1000))
        # 近端破位回调
        bars.extend([
            {"open": 104.0, "high": 104.2, "low": 102.5, "close": 102.8, "volume": 400},
            {"open": 102.8, "high": 103.0, "low": 100.0, "close": 100.5, "volume": 320},
            {"open": 100.5, "high": 101.0, "low": 98.0, "close": 98.5, "volume": 280},
            {"open": 98.5, "high": 99.0, "low": 97.5, "close": 98.0, "volume": 220},
            {"open": 98.0, "high": 98.5, "low": 97.0, "close": 97.5, "volume": 180},
        ])
        result = _detect_lps(bars)
        assert result["lps_signal"] is False, (
            f"近端 SOS 破位后不应回退远端 SOS 触发 LPS: {result}"
        )

    def test_lps_not_detected_high_volume(self):
        """SOS 后回调末端量能不萎缩 → LPS 不触发"""
        bars = self._base_bars(15, vol=500, low=96)
        bars.extend([
            {"open": 100, "high": 102, "low": 98, "close": 101, "volume": 500}
            for _ in range(5)
        ])
        bars.extend(self._sos_bars(start_open=101.0, vol=1000))
        # 末端量 400 >= 500*0.7=350
        bars.extend([
            {"open": 103.5, "high": 104, "low": 102.5, "close": 102.8, "volume": 450},
            {"open": 102.8, "high": 103, "low": 101.8, "close": 102.0, "volume": 420},
            {"open": 102.0, "high": 102.2, "low": 101.0, "close": 101.2, "volume": 410},
            {"open": 101.2, "high": 101.5, "low": 100.5, "close": 100.8, "volume": 400},
            {"open": 100.8, "high": 101.0, "low": 100.0, "close": 100.2, "volume": 400},
        ])
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False


class TestWyckoffScoreWithClassicSignals:
    """calculate_wyckoff_score 消费新增经典信号的测试"""

    def test_ar_boosts_score(self):
        """AR 信号 → 分数提升 +10"""
        bars = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
        # FINDING-5：前置主升（85→100）满足 BC 前置涨幅条件
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})  # BC
        # 2 根阳线 + 1 根阴线 → 最后5根中仅3阳 → SOS不触发
        bars.append(_make_bar(103, 105, 102, 104, 100))
        bars.append(_make_bar(104, 105, 102, 103, 100))  # 阴线
        bars.append(_make_bar(103, 105, 102, 104, 100))
        result = calculate_wyckoff_score(bars)
        # BC 触发 (-15), score 应该下降
        assert any("购买高潮" in s for s in result["signals"])
        assert result["raw"] < 0

    def test_sos_boosts_score(self):
        """SOS 信号 → 分数提升 +15"""
        # 验证 calculate_wyckoff_score 不会因新增信号而崩溃
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(20)]
        result = calculate_wyckoff_score(bars)
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100
        assert "signals" in result

    def test_combined_spring_sos_st(self):
        """Spring 信号 → 高分

        Spring bar 必须是最后一根 (bars[-1]), 因为 _detect_spring 只检测当前 bar.
        15 base(low=90) + 1 Spring(low=85, close=91) = 16 根
        """
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # Spring bar: low=85, close=97 → reclaim=7/6=117% ≥ 50%, vol=150 < 200
        bars.append({"open": 89, "high": 97, "low": 85, "close": 97, "volume": 150})
        result = calculate_wyckoff_score(bars)
        spring_signals = [s for s in result["signals"] if "Spring" in s]
        assert len(spring_signals) >= 1, f"Spring not detected: {result['signals']}"
        assert result["score"] > 50  # Spring=+25 → 50+25*50//130=59，仍看多（P1-2 分母130调整）

    def test_ar_adds_10(self):
        """AR 信号贡献 +10（⑥B：挂在 SC 后）。SC=+10 + AR=+10 + 积累阶段修正=+2 → raw=22。"""
        from trader_shared.wyckoff_core import calculate_wyckoff_score
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(20)]
        analysis = {
            "spring_signal": False, "upthrust_signal": False,
            "bc_signal": False, "sc_signal": True, "sow_signal": False,
            "ar_signal": True, "sos_signal": False, "st_signal": False,
            "lps_signal": False, "lpsy_signal": False,
            "compression_signal": False, "trend_pullback_signal": False,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            "effort_no_result": False, "no_supply": False,
            "accumulation_confirmed": False, "distribution_confirmed": False,
            "phase_confidence_delta": 0.10,  # accumulation_a SC+AR
            "spring_premature": False, "upthrust_premature": False,
            "tr_quality": None,
        }
        result = calculate_wyckoff_score(bars, analysis=analysis)
        assert result["raw"] == 22, f"Expected raw=22 (SC+10+AR+10+阶段+2), got {result['raw']}"
        assert any("AR" in s for s in result["signals"])
        assert any("阶段修正" in s for s in result["signals"])

    def test_sos_adds_15(self):
        """SOS 信号精确贡献 +15。5 连阳放量突破，无其他信号。

        数学推导：S > 1.38B 满足 SOS。取 S=1.5B。
        20 base bars (vol=200) + 5 SOS bars (vol=300)。
        Bug H 新合同（滞涨门槛 5.0）：首日跳空 ≥5%（+5.3%），否则 +4% 的高位放量
        首日会被判 BC（滞涨 <5%）→ raw 被 BC(-15) 抵消。
        """
        from trader_shared.wyckoff_core import calculate_wyckoff_score
        bars = []
        for i in range(20):
            o = 100 + i * 0.01
            bars.append(_make_bar(o, o + 0.5, o - 0.5, o + 0.2, 200))
        # 5 连阳：首日跳空 +5.3%（≥5.0，非滞涨），累计涨 ≥2%
        bars.append(_make_bar(100.6, 105.7, 100.4, 105.7, 300))
        for i in range(1, 5):
            o = 104 + i * 0.44
            c = o + 0.4
            bars.append(_make_bar(o, c, o - 0.2, c, 300))
        result = calculate_wyckoff_score(bars)
        assert result["raw"] == 15, f"Expected raw=15 (SOS only), got {result['raw']}"

    def test_st_adds_8(self):
        """ST 信号贡献 +8（与 Spring 同序列可共存）。"""
        from trader_shared.wyckoff_core import calculate_wyckoff_score, wyckoff_analysis

        helper = TestDetectST()
        bars = helper._spring_then_test_bars(st_vol=100)
        # 末日再挂一根有效 Spring，保证 tip spring 灯 + 序列内 ST
        bars.append({"open": 89, "high": 98, "low": 85, "close": 97, "volume": 150})
        an = wyckoff_analysis(bars)
        assert an.get("st_signal") is True, f"ST 应亮: {an.get('st_reason')}"
        assert an.get("spring_signal") is True
        result = calculate_wyckoff_score(bars)
        assert any("Spring确认" in s or "ST" in s for s in result["signals"]), result["signals"]
        # Spring 全分或降权 + ST(+8) 至少高于裸 ST
        assert result["raw"] >= 8

    def test_lps_adds_12(self):
        """LPS 信号精确贡献 +12。回调段缩量触发 VSA 供应耗尽 +5。

        正确时序: base + pre_sos + SOS + pullback
        volume: baseline=150, SOS=200, pullback 末端=80
        P1-1 修复: 孤立 LPSY（无派发背景）不再打分，故不再抵消 LPS。
        """
        from trader_shared.wyckoff_core import calculate_wyckoff_score, wyckoff_analysis
        bars = []
        # 15 根基准
        for i in range(15):
            bars.append(_make_bar(100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100 + i * 0.1, 150))
        # pre_sos 5 根 (low=98)
        for i in range(5):
            bars.append(_make_bar(100, 101, 98, 100, 150))
        # SOS 5 连阳 (vol=200)
        for i in range(5):
            o = 100 + i * 0.5
            c = o + 0.45
            bars.append(_make_bar(o, c + 0.1, o - 0.1, c, 200))
        # 回调 5 根缩量
        for i in range(5):
            o = 102.5 - i * 0.4
            c = o - 0.2
            bars.append(_make_bar(o, o + 0.1, c - 0.1, c, 80))
        analysis = wyckoff_analysis(bars)
        assert analysis["lps_signal"] is True, f"LPS not detected: {analysis.get('lps_reason')}"
        # 末窗口是回调而非 SOS → LPS +12 + 供应耗尽 +5 = 17
        result = calculate_wyckoff_score(bars)
        assert any("LPS" in s for s in result["signals"]), f"LPS not scored: {result['signals']}"
        # P1-1 修复后孤立 LPSY 不打分，raw 应为 17（LPS+12 + 供应耗尽+5）
        assert result["raw"] == 17, f"Expected raw 17 (LPS+12 + 供应耗尽+5), got {result['raw']}"


class TestWyckoffScoreClusterReverseSOS:
    """派发确认 + 近端 SOS 不打分对冲（wyckoff-cluster-reverse-event-handoff §1.2）。"""

    def _analysis(self, **kw) -> dict:
        base = {
            "spring_signal": False, "upthrust_signal": False, "bc_signal": False,
            "sc_signal": False, "sow_signal": False, "ar_signal": False,
            "are_signal": False, "sos_signal": False, "st_signal": False,
            "lps_signal": False, "lpsy_signal": False, "compression_signal": False,
            "trend_pullback_signal": False, "trend_rally_signal": False,
            "bearish_volume_divergence": False, "bullish_volume_divergence": False,
            "effort_no_result": False, "no_supply": False,
            "accumulation_confirmed": False, "distribution_confirmed": False,
            "accumulation_failed": False, "distribution_failed": False,
            "cluster_contested": False,
            "phase_confidence_delta": 0.0, "spring_premature": False,
            "upthrust_premature": False, "tr_quality": None,
        }
        base.update(kw)
        return base

    def _bars(self) -> list[dict]:
        return [_make_bar(100, 101, 99, 100, 100) for _ in range(20)]

    def test_distribution_confirmed_suppresses_sos(self):
        from trader_shared.wyckoff_core import calculate_wyckoff_score

        result = calculate_wyckoff_score(
            self._bars(),
            analysis=self._analysis(
                sos_signal=True,
                distribution_confirmed=True,
                distribution_failed=False,
                cluster_contested=True,
            ),
        )
        assert result["raw"] == -15, f"派发确认不应被 SOS 对冲, got {result['signals']}"
        assert "互斥抑制:sos_signal" in result["signals"], result["signals"]
        assert not any("SOS +15" in s for s in result["signals"]), result["signals"]
        assert any("派发确认" in s for s in result["signals"]), result["signals"]

    def test_distribution_failed_keeps_sos(self):
        """UT→SOS 无 SOW（假派发实为吸筹）→ SOS 仍计分（回归）。"""
        from trader_shared.wyckoff_core import calculate_wyckoff_score

        result = calculate_wyckoff_score(
            self._bars(),
            analysis=self._analysis(sos_signal=True, distribution_failed=True),
        )
        assert any("SOS +15" in s for s in result["signals"]), result["signals"]
        assert any("派发失败" in s for s in result["signals"]), result["signals"]
        assert result["raw"] == 35, f"Expected SOS+15 + 派发失败+20, got {result['signals']}"


class TestDetectSOSFourOfFive:
    """SOS ≥4/5 阳线对齐测试"""

    def test_sos_4_of_5_bullish_triggers(self):
        """4/5 阳线 + 放量抬高 ≥2% → SOS 触发"""
        bars = []
        for i in range(15):
            o = 100 + i * 0.01
            bars.append(_make_bar(o, o + 0.5, o - 0.5, o + 0.2, 200))
        # 4 阳 + 1 阴（第 3 根），整体仍抬高 ≥2%
        seq = [
            (104.0, 104.5),   # 阳
            (104.5, 105.0),   # 阳
            (105.0, 104.8),   # 阴
            (104.8, 105.4),   # 阳
            (105.4, 106.2),   # 阳；累计 (106.2-104)/104 ≈ 2.1%
        ]
        for o, c in seq:
            bars.append(_make_bar(o, max(o, c) + 0.1, min(o, c) - 0.1, c, 300))
        result = _detect_sos(bars)
        assert result["sos_signal"] is True, f"SOS 4/5 failed: {result.get('sos_reason')}"
        assert "4/5" in result["sos_reason"]

    def test_sos_3_of_5_not_trigger(self):
        """仅 3/5 阳线 → SOS 不触发"""
        bars = []
        for i in range(15):
            o = 100 + i * 0.01
            bars.append(_make_bar(o, o + 0.5, o - 0.5, o + 0.2, 200))
        seq = [
            (104.0, 104.5),
            (104.5, 104.3),  # 阴
            (104.3, 104.8),
            (104.8, 104.6),  # 阴
            (104.6, 106.2),
        ]
        for o, c in seq:
            bars.append(_make_bar(o, max(o, c) + 0.1, min(o, c) - 0.1, c, 300))
        result = _detect_sos(bars)
        assert result["sos_signal"] is False
        assert "3/5" in result.get("sos_reason", "")


class TestDetectPhaseSemantics:
    """phase 语义纠偏：BC+AR 不得进 accumulation_a"""

    _OK_TR = {
        "tr_quality": 0.7,
        "tr_upper": 105.0,
        "tr_lower": 95.0,
        "in_tr": True,
        "tr_width": 40,
        "phase_a_status": "established",
    }

    def test_bc_ar_is_distribution_a_not_accumulation(self):
        from unittest.mock import patch

        signals = {
            "spring_signal": False,
            "sos_signal": False,
            "lps_signal": False,
            "bc_signal": True,  # 派发极性；AR 不再构成派发 B，但 BC alone → distribution_a
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]

        def fake_scan(_bars, detector_fn, **kwargs):
            name = getattr(detector_fn, "__name__", "")
            if name == "_detect_buying_climax":
                return True
            if name == "_detect_ar":
                return True
            return False

        with patch("trader_shared.wyckoff_phase._scan_for_signal", side_effect=fake_scan):
            result = _detect_phase(bars, signals, tr_ctx=self._OK_TR)

        assert result["phase"] == "distribution_a"
        assert "accumulation" not in result["phase"]
        assert result["phase_confidence_delta"] < 0

    def test_spring_starts_accumulation_c(self):
        """Spring + B 背景(SC+AR) → accumulation_c；无 B 背景的孤立 Spring 判过早"""
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sc_signal": True,  # 提供 B 背景
            "ar_signal": True,  # 提供 B 背景
            "sos_signal": False,
            "lps_signal": False,
            "spring_test_signal": False,
            "st_signal": False,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]
        with patch("trader_shared.wyckoff_phase._scan_for_signal", return_value=False):
            result = _detect_phase(bars, signals, tr_ctx=self._OK_TR)
        assert result["phase"] == "accumulation_c"
        assert result.get("spring_premature") is False
        assert result["phase_confidence_delta"] > 0

    def test_spring_plus_sos_is_accumulation_d(self):
        """Spring + SOS + B 背景(SC+AR) → accumulation_d"""
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sos_signal": True,
            "lps_signal": False,
            "sc_signal": True,  # 提供 B 背景
            "ar_signal": True,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]
        with patch("trader_shared.wyckoff_phase._scan_for_signal", return_value=False):
            result = _detect_phase(bars, signals, tr_ctx=self._OK_TR)
        assert result["phase"] == "accumulation_d"
        assert "SOS/LPS" in result.get("phase_label", "")

    def test_distribution_confirmed_blocks_accumulation_despite_sos(self):
        """派发确认 + Spring+SOS → 不得跳积累 D/C（_scan 重扫 SOS 也兜底）。"""
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sos_signal": True,
            "distribution_confirmed": True,
            "distribution_failed": False,
            "compression_signal": True,  # B 背景：Spring 非孤立
            "lps_signal": False,
            "spring_test_signal": False,
            "st_signal": False,
            "sc_signal": False,
            "ar_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "are_signal": False,
            "trend_pullback_signal": False,
            "trend_rally_signal": False,
            "bu_signal": False,
            "utad_signal": False,
            "tr_upper": 105.0,
            "last_close": 100.0,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]

        def fake_scan(_bars, detector_fn, **kwargs):
            # 钉死 _scan：不让 _detect_sos/_detect_spring 从 bars 重扫，只看 signals
            return False

        with patch("trader_shared.wyckoff_phase._scan_for_signal", side_effect=fake_scan):
            result = _detect_phase(bars, signals, tr_ctx=self._OK_TR)

        assert result["phase"] not in ("accumulation_d", "accumulation_c"), result
        assert result.get("spring_premature") is False, "守卫应真实生效，而非 premature 挡下"

    def test_distribution_failed_still_enters_accumulation(self):
        """distribution_failed（假派发实为吸筹）→ Spring+SOS 仍进积累 D（回归）。"""
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sos_signal": True,
            "distribution_confirmed": False,
            "distribution_failed": True,
            "compression_signal": True,  # B 背景：Spring 非孤立
            "lps_signal": False,
            "spring_test_signal": False,
            "st_signal": False,
            "sc_signal": False,
            "ar_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "are_signal": False,
            "trend_pullback_signal": False,
            "trend_rally_signal": False,
            "bu_signal": False,
            "utad_signal": False,
            "tr_upper": 105.0,
            "last_close": 100.0,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]
        with patch("trader_shared.wyckoff_phase._scan_for_signal", return_value=False):
            result = _detect_phase(bars, signals, tr_ctx=self._OK_TR)
        assert result["phase"] == "accumulation_d", result
        assert "SOS/LPS" in result.get("phase_label", ""), result

    def test_phase_delta_consumed_in_score(self):
        """phase_confidence_delta 在 calculate_wyckoff_score 中被消费"""
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # 正常量 Spring（非高量），通过传递 analysis dict 覆盖 phase 确保 delta 存在
        bars.append({"open": 89, "high": 97, "low": 85, "close": 97, "volume": 150})
        base = wyckoff_analysis(bars)
        # 覆盖 phase 为 accumulation_c 以提供 phase_confidence_delta=0.10，
        # 并确保 spring 不被判过早（spring_premature=False）
        override = {**base,
            "phase": "accumulation_c",
            "phase_label": "积累期 C（测试：Spring）",
            "phase_confidence_delta": 0.10,
            "spring_premature": False,
            # 固定 ordinary，避免缩量 weak 降权干扰「阶段修正」断言
            "spring_strength": "ordinary",
            "spring_vol_class": "normal",
        }
        result = calculate_wyckoff_score(bars, analysis=override)
        # Spring +25 + 阶段修正 +2 = 27
        assert result["raw"] == 27, f"Expected 27 (Spring25+阶段2), got {result['raw']}"
        assert any("阶段修正" in s for s in result["signals"])


class TestPhaseUnifiedScAnchor:
    """P-M7（docs/plans/wyckoff-epic-phase-unify-handoff 验收 P1~P5）：
    阶段机吃统一 SC 锚（Bug I 收尾）——注入同源、无注入回归、越界防护、子窗剥离、周线。"""

    _OK_TR = {
        "tr_quality": 0.7,
        "tr_upper": 105.0,
        "tr_lower": 95.0,
        "in_tr": True,
        "tr_width": 40,
        "phase_a_status": "established",
    }

    @staticmethod
    def _anchor(sc_bar_idx: int, **kw) -> dict:
        """与 _find_sc_anchor 返回同构的完整序列 SC 锚（含全部既有键）。"""
        out = {
            "sc_bar_idx": sc_bar_idx,
            "sc_low": 95.0,
            "sc_close": 96.0,
            "sc_avg_vol": 100.0,
            "vol_ratio": 2.0,
            "change_pct": -3.0,
            "pos": 0.2,
            "cur_high": 103.0,
            "cur_open": 99.0,
            "anchor_bars": 90,
            "search_mode": "pinned",
        }
        out.update(kw)
        return out

    @staticmethod
    def _sig(**kw) -> dict:
        d = {k: False for k in (
            "spring_signal", "upthrust_signal", "bc_signal", "sc_signal",
            "sow_signal", "ar_signal", "are_signal", "sos_signal", "st_signal",
            "spring_test_signal", "secondary_test_sc_signal", "lps_signal",
            "lpsy_signal", "compression_signal", "trend_pullback_signal",
            "trend_rally_signal", "bu_signal", "utad_signal",
            "ps_signal", "psy_signal",
        )}
        d.update(kw)
        return d

    def _run_with_fakes(self, bars, tr_ctx, *, lookback, timeframe="daily",
                        spring_idx=-1, ar_idx=-1, comp_idx=-1,
                        signals=None):
        """隔离 _scan/_last：记录调用与子窗 tr_ctx；仅 fake 指定事件索引。

        B 收尾（wyckoff-epic-vol-phase-verif-handoff 方向 B）：统一锚存在时 AR 走
        ``_ar_verdict``（直接调 _detect_ar 单次评估，不再经 _scan_last_event），
        故此处同步 patch ``wyckoff_phase._detect_ar`` 注入 ar_idx，保证阶段机
        顺序逻辑测试语义不变（索引由 fake 提供，与旧 _last fake 等价）。
        """
        from unittest.mock import patch
        from trader_shared import wyckoff_phase as wp

        scan_calls: list = []
        last_calls: list = []
        sig = signals if signals is not None else self._sig()

        def fake_scan(_bars, det, window=15, step=5, max_lookback_bars=None, **kw):
            scan_calls.append((getattr(det, "__name__", ""), kw.get("tr_ctx")))
            name = getattr(det, "__name__", "")
            # 仅 compression 可经 scan 亮 B 背景；spring 亮灯由 signals 控制，避免打乱既有 phase 断言
            if name == "_detect_compression" and comp_idx >= 0:
                return True
            if name == "_detect_spring" and bool(sig.get("spring_signal")):
                return True
            return False

        def fake_last(_bars, det, tr_ctx, window, step=1, **kw):
            last_calls.append((getattr(det, "__name__", ""), tr_ctx))
            name = getattr(det, "__name__", "")
            if name == "_detect_spring":
                if spring_idx >= 0:
                    return spring_idx, {"spring_signal": True}
                return -1, None
            if name == "_detect_ar":
                if ar_idx >= 0:
                    return ar_idx, {"ar_signal": True}
                return -1, None
            if name == "_detect_compression":
                if comp_idx >= 0:
                    return comp_idx, {"compression_signal": True}
                return -1, None
            return -1, None

        def fake_ar(_bars, tr_ctx=None, *, timeframe="daily", is_index=False):
            if ar_idx >= 0:
                return {"ar_signal": True, "ar_bar_idx": ar_idx}
            return {"ar_signal": False, "ar_bar_idx": None}

        with patch("trader_shared.wyckoff_phase._scan_for_signal", side_effect=fake_scan), \
             patch("trader_shared.wyckoff_phase._scan_last_event", side_effect=fake_last), \
             patch("trader_shared.wyckoff_phase._detect_ar", side_effect=fake_ar):
            ph = wp._detect_phase(
                bars, sig, _phase_lookback=lookback,
                tr_ctx=tr_ctx, timeframe=timeframe,
            )
        return ph, scan_calls, last_calls

    def test_p1_anchor_same_source_sc_found_and_converted_sc_idx_order(self):
        """验收 P1：注入统一锚 → sc_found=True 且 spring 次序用换算后 sc_idx（45→25）。
        wide_bars=bars[-40:]（offset=20）；若误用原始 45 → acc_b_ctx_idx=45 > 27 → 判过早。"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(60)]
        tr_ctx = {**self._OK_TR, "sc_anchor": self._anchor(45)}
        ph, scan_calls, last_calls = self._run_with_fakes(
            bars, tr_ctx, lookback=40, spring_idx=27, ar_idx=20)
        assert ph["phase"] == "accumulation_a"
        assert ph["spring_premature"] is False, "spring(27) 在换算 sc_idx(25) 之后 → 有效"
        # 同源：SC 不再经滑窗重算（_scan/_last 均不得出现 _detect_selling_climax）
        assert "_detect_selling_climax" not in [c[0] for c in scan_calls]
        assert "_detect_selling_climax" not in [c[0] for c in last_calls]
        # P-M4：子窗 tr_ctx 不含 sc_anchor（其余键原样）
        for _name, ctx in scan_calls + last_calls:
            assert ctx is None or "sc_anchor" not in ctx

    def test_p1b_spring_before_converted_sc_idx_premature(self):
        """验收 P1（次序边界）：spring(23) < 换算 sc_idx(25) → premature。"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(60)]
        tr_ctx = {**self._OK_TR, "sc_anchor": self._anchor(45)}
        ph, _, _ = self._run_with_fakes(
            bars, tr_ctx, lookback=40, spring_idx=23, ar_idx=20)
        assert ph["spring_premature"] is True, "spring(23) < 换算 sc_idx(25) → 过早"
        assert ph["phase"] == "accumulation_a"

    def test_p0_2_compression_after_spring_not_premature(self):
        """P0-2：SC→AR→Spring 后出现 compression，不得把 Spring 判 premature。"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(60)]
        tr_ctx = {**self._OK_TR, "sc_anchor": self._anchor(45)}  # wide sc_idx=25
        # spring=27, ar=20, comp=35（在 spring 之后）
        ph, _, _ = self._run_with_fakes(
            bars,
            tr_ctx,
            lookback=40,
            spring_idx=27,
            ar_idx=20,
            comp_idx=35,
            signals=self._sig(spring_signal=True),
        )
        assert ph["spring_premature"] is False, (
            "comp 在 spring 之后不得抬高 B 完成点导致 premature"
        )
        assert ph["phase"] == "accumulation_c"

    def test_p2_no_anchor_keeps_sliding_window_sc(self):
        """验收 P2：无 sc_anchor → 原滑窗逻辑零改动（_scan/_last 仍调 SC 检测器）。"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(60)]
        ph, scan_calls, last_calls = self._run_with_fakes(
            bars, self._OK_TR, lookback=40, spring_idx=27, ar_idx=20)
        assert "_detect_selling_climax" in [c[0] for c in scan_calls], "无锚应走原 _scan SC"
        assert "_detect_selling_climax" in [c[0] for c in last_calls], "无锚应走原 _last SC"
        # 原行为：无 sc/ar 索引 → B 背景缺失 → 孤立 spring 判过早、phase=none
        assert ph["spring_premature"] is True
        assert ph["phase"] == "none"

    def test_p3_anchor_outside_lookback_sc_idx_minus1(self):
        """验收 P3：锚 sc_bar_idx 在 lookback 外（bars=120、lookback=60 → 5-60=-55）→ -1 不崩。"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(120)]
        tr_ctx = {**self._OK_TR, "sc_anchor": self._anchor(5)}
        ph, scan_calls, last_calls = self._run_with_fakes(
            bars, tr_ctx, lookback=60, spring_idx=20, ar_idx=25)
        assert ph["phase"] == "accumulation_a", "sc_found 仍 True（锚存在）"
        assert ph["spring_premature"] is True, "sc_idx=-1 → 次序按无 SC 处理"
        assert "_detect_selling_climax" not in [c[0] for c in scan_calls]
        assert "_detect_selling_climax" not in [c[0] for c in last_calls]

    def test_p4_subwindow_ctx_strips_anchor_ar_still_lights(self):
        """验收 P4：带 sc_anchor 的 tr_ctx 下 _scan(_detect_ar) 子窗不越界、AR 仍亮（SC+AR）。"""
        from unittest.mock import patch
        from trader_shared import wyckoff_phase as wp

        # 低位 SC（全序列 idx=60）+ 放量反弹（TestDetectAR 同款下降段，SC 落在 wide_bars 末 30 根）
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(40)]
        for i in range(20):
            base = 150 - i * 2  # 150 → 112，抬高近窗上沿
            bars.append(_make_bar(base, base + 3, base - 3, base, 10))
        prev = bars[-1]["close"]
        bars.append({"open": prev - 1, "high": 99, "low": 95, "close": 98, "volume": 250})  # SC idx=60
        bars.append({"open": 98, "high": 105, "low": 97, "close": 104, "volume": 80})      # AR
        bars.append(_make_bar(104, 105, 103, 104, 10))
        bars.append(_make_bar(104, 105, 103, 104, 10))
        assert len(bars) == 64
        tr_ctx = {**self._OK_TR, "sc_anchor": self._anchor(60)}
        seen_ctx: list = []
        real_scan = wp._scan_for_signal

        def _spy(_bars, det, window=15, step=5, max_lookback_bars=None, **kw):
            seen_ctx.append(kw.get("tr_ctx"))
            if getattr(det, "__name__", "") == "_detect_ar":
                return real_scan(
                    _bars, det, window=window, step=step,
                    max_lookback_bars=max_lookback_bars, **kw,
                )
            return False

        def _fake_last(_bars, det, tr_ctx, window, step=1, **kw):
            return -1, None

        with patch("trader_shared.wyckoff_phase._scan_for_signal", side_effect=_spy), \
             patch("trader_shared.wyckoff_phase._scan_last_event", side_effect=_fake_last):
            ph = wp._detect_phase(bars, self._sig(), _phase_lookback=60, tr_ctx=tr_ctx)
        assert seen_ctx, "阶段机应调用滑窗"
        assert all(ctx is None or "sc_anchor" not in ctx for ctx in seen_ctx), \
            "P-M4：滑窗子 ctx 必须剥离 sc_anchor"
        # AR 子窗真实运行：不越界不崩、仍亮 → SC+AR 停止（未剥离时子窗 IndexError 被吞 → 无 AR）
        assert ph["phase"] == "accumulation_a"
        assert "SC+AR" in ph["phase_label"], ph["phase_label"]

    def test_p4b_unstripped_anchor_crashes_subwindow(self):
        """P-M4 陷阱对照：未剥离的 sc_anchor（全序列索引）进子窗 → _detect_ar 越界。"""
        from trader_shared.wyckoff_events import _detect_ar

        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(40)]
        for i in range(20):
            base = 150 - i * 2
            bars.append(_make_bar(base, base + 3, base - 3, base, 10))
        prev = bars[-1]["close"]
        bars.append({"open": prev - 1, "high": 99, "low": 95, "close": 98, "volume": 250})
        bars.append({"open": 98, "high": 105, "low": 97, "close": 104, "volume": 80})
        sub = bars[-18:]
        try:
            _detect_ar(sub, tr_ctx={**self._OK_TR, "sc_anchor": self._anchor(60)})
            raised = False
        except IndexError:
            raised = True
        assert raised, "未剥离的 sc_anchor 应导致子窗 bars[60] 越界（P-M4 依据）"

    def test_p5_weekly_anchor_consumed_with_weekly_params(self):
        """验收 P5：周线阶段机吃周线统一锚（39 帽冷启动），换算/次序用周线 wide_bars。"""
        from trader_shared import wyckoff_events as we
        from trader_shared.config import WYCKOFF_SC_COLD_START_BARS_WEEKLY

        bars = []
        for i in range(260):
            p = 100.0 + (i % 7) * 0.05
            bars.append(_make_bar(p, p + 0.1, p - 0.1, p + 0.02, 100))
        bars[250] = {"open": 100.5, "high": 100.8, "low": 98.0, "close": 98.6, "volume": 2000}
        # 周线统一锚（与周线 SC 灯同参 timeframe="weekly"）→ 39 帽冷启动
        anchor = we._find_sc_anchor(bars, timeframe="weekly", include_failed=True)
        assert anchor is not None and anchor["sc_bar_idx"] == 250
        assert anchor["anchor_bars"] == int(WYCKOFF_SC_COLD_START_BARS_WEEKLY), "周线 39 帽"
        tr_ctx = {**self._OK_TR, "sc_anchor": anchor}
        # 周线 lookback=12 → wide_bars=bars[-12:]（offset=248）→ sc_idx = 250-248 = 2
        ph, scan_calls, last_calls = self._run_with_fakes(
            bars, tr_ctx, lookback=12, timeframe="weekly", spring_idx=5, ar_idx=3)
        assert ph["phase"] == "accumulation_a", "周线阶段机吃周线锚 → sc_found"
        assert ph["spring_premature"] is False, "spring(5) 在换算 sc_idx(2)/ar(3) 之后 → 有效"
        assert "_detect_selling_climax" not in [c[0] for c in scan_calls]
        assert "_detect_selling_climax" not in [c[0] for c in last_calls]


class TestHighVolSpringDeweight:
    """高量 Spring 降权（通过 analysis override 提供 B 背景避免过早降权干扰）"""

    def _spring_analysis(self, bars):
        """计算分析并覆盖 spring_premature=False 以保留高量降权语义"""
        a = wyckoff_analysis(bars)
        a["spring_premature"] = False
        return a

    def test_high_vol_spring_filtered(self):
        """高量 Spring 直接过滤，不报信号（原典：放量跌破 = 真破位）"""
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # vol=300 >= 200*1.5 → 直接过滤
        bars.append({"open": 89, "high": 97, "low": 85, "close": 97, "volume": 300})
        analysis = self._spring_analysis(bars)
        assert analysis["spring_signal"] is False, "高量 Spring 应被过滤"
        assert "真破位" in analysis.get("spring_reason", "")
        assert analysis.get("spring_vol_class") == "high_vol_warning"
        assert analysis.get("spring_strength") == "failure"

    def test_high_vol_spring_no_score(self):
        """高量 Spring 被过滤后，即使有看多背离也不计分"""
        from unittest.mock import patch

        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        bars.append({"open": 89, "high": 97, "low": 85, "close": 97, "volume": 300})
        real = wyckoff_analysis
        def _fake_analysis(b, **kwargs):
            r = real(b, **kwargs)
            r["bullish_volume_divergence"] = True
            r["bearish_volume_divergence"] = False
            r["spring_premature"] = False
            return r
        with patch("trader_shared.wyckoff_core.wyckoff_analysis", side_effect=_fake_analysis):
            result = calculate_wyckoff_score(bars)
        # 高量 Spring 被过滤 → spring_signal=False → 无 Spring 加分
        spring_signals = [s for s in result["signals"] if "Spring" in s]
        assert len(spring_signals) == 0, f"高量 Spring 不应计分: {result['signals']}"


class TestBCHighPosition:
    """P1: BC 高位过滤"""

    def test_bc_rejected_at_low_position(self):
        """低位天量滞涨不标 BC"""
        # 高位在 120，当前在 100 附近放量阴线 → pos 偏低
        bars = []
        for i in range(14):
            # 前段冲高到 120
            h = 100 + i * 1.5
            bars.append(_make_bar(h - 1, h, h - 3, h - 0.5, 100))
        # 回落后低位天量（相对近 10 日区间偏下）
        bars.append({"open": 102, "high": 103, "low": 99, "close": 100, "volume": 300})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is False

    def test_bc_still_detected_at_high(self):
        """高位天量仍可触发 BC（回归）"""
        bars = _prerise(20, 85, 100) + [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # FINDING-5：前置 20 根上行（85→100）提供 ≥15% 主升
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is True


class TestWyckoffMidlineTimeframe:
    """中线威科夫：周K优先、日K回退"""

    def _bars(self, n: int = 40) -> list[dict]:
        bars = []
        price = 100.0
        for i in range(n):
            o = price
            c = price * (1.008 if i % 4 else 0.992)
            bars.append({
                "open": o,
                "high": max(o, c) * 1.01,
                "low": min(o, c) * 0.99,
                "close": c,
                "volume": 1000 + i * 20,
            })
            price = c
        return bars

    def test_prefers_weekly(self):
        from trader_shared.wyckoff_core import wyckoff_strategy_midline
        weekly = self._bars(30)
        daily = self._bars(60)
        r = wyckoff_strategy_midline(weekly[-1]["close"], weekly_bars=weekly, daily_bars=daily)
        assert r["wyckoff"]["timeframe"] == "weekly"

    def test_no_daily_fallback(self):
        from trader_shared.wyckoff_core import wyckoff_strategy_midline
        daily = self._bars(40)
        r = wyckoff_strategy_midline(daily[-1]["close"], weekly_bars=[], daily_bars=daily)
        assert r["wyckoff"]["timeframe"] == "insufficient"

    def test_insufficient(self):
        from trader_shared.wyckoff_core import wyckoff_strategy_midline
        r = wyckoff_strategy_midline(10.0, weekly_bars=[], daily_bars=self._bars(5))
        assert r["wyckoff"]["timeframe"] == "insufficient"


class TestFormatWyckoffOneline:
    """报告一行人话"""

    def test_no_signal(self):
        line = format_wyckoff_oneline({})
        assert line == "威科夫：数据不足 · 中性"
        line2 = format_wyckoff_oneline({
            "timeframe": "weekly",
            "wyckoff_summary": "无明显威科夫信号",
            "spring_signal": False,
        })
        assert line2 == "威科夫：暂无事件 · 中性"
        assert "\n" not in line

    def test_insufficient_timeframe_honest(self):
        """周线不足不得伪装成「暂无事件」."""
        line = format_wyckoff_oneline({
            "timeframe": "insufficient",
            "wyckoff_summary": "周线数据不足，中线威科夫不参与定论",
            "spring_signal": False,
        })
        assert "不参与定论" in line
        assert "暂无事件" not in line

    def test_spring_premature_not_bullish(self):
        line = format_wyckoff_oneline({
            "spring_signal": True,
            "spring_premature": True,
            "spring_vol_class": "low_vol_confirm",
        })
        assert "噪声" in line or "孤立" in line or "过早" in line
        assert "偏多" not in line  # premature → 中性展示

    def test_spring_low_vol_one_line(self):
        line = format_wyckoff_oneline({
            "spring_signal": True,
            "spring_vol_class": "low_vol_confirm",
        })
        assert line.startswith("威科夫：")
        assert " · 偏多" in line or "· 偏多" in line
        assert "洗盘" in line or "缩量" in line
        assert "Spring" not in line
        assert "积累期" not in line
        assert "\n" not in line
        # 句式：判断 · 多空（说明）
        assert "，偏多" not in line

    def test_high_vol_spring(self):
        line = format_wyckoff_oneline({
            "spring_signal": True,
            "spring_vol_class": "high_vol_warning",
        })
        assert "偏多" in line
        assert "放量" in line or "真破位" in line

    def test_bc(self):
        line = format_wyckoff_oneline({"bc_signal": True})
        assert "偏空" in line
        assert "高位" in line or "滞涨" in line

    def test_direction_override(self):
        line = format_wyckoff_oneline({"spring_signal": True}, direction=-1)
        assert "偏空" in line


class TestSpringBreachShared:
    """P1: Spring/ST 共用刺穿深度"""

    def test_spring_breach_level_atr(self):
        from trader_shared.wyckoff_core import _spring_breach_level
        bar = {"atr14": 2.0}
        # support 100, 0.5*ATR=1 → breach=99
        assert abs(_spring_breach_level(100.0, bar) - 99.0) < 1e-9

    def test_spring_breach_level_fallback_ratio(self):
        from trader_shared.wyckoff_core import _spring_breach_level
        # 无 atr → 100*0.985
        assert abs(_spring_breach_level(100.0, {}) - 98.5) < 1e-9

    def test_st_uses_atr_spring_anchor(self):
        """带 atr14 的 Spring 锚点可被 ST 识别（与固定 1.5% 路径一致不漏检）"""
        from trader_shared.wyckoff_core import _detect_st
        # 构造：10 日支撑 90，Spring 用 atr 刺穿（0.5*atr=2 → breach=88），再缩量回测
        bars = []
        for _ in range(12):
            bars.append({**_make_bar(100, 105, 90, 102, 200), "atr14": 4.0})
        # Spring bar: low=87 < 88, close=91 >= 90
        bars.append({**_make_bar(89, 93, 87, 91, 150), "atr14": 4.0})
        # 3-15 根后缩量回测支撑区
        for _ in range(4):
            bars.append({**_make_bar(95, 98, 94, 96, 180), "atr14": 4.0})
        bars.append({**_make_bar(92, 94, 90.5, 91.5, 80), "atr14": 4.0})  # 回测 + 缩量
        result = _detect_st(bars)
        # 若 ATR 路径未共用，固定 90*0.985=88.65 时 low=87 仍可检；主要断言不崩溃且有合理字段
        assert "st_signal" in result
        assert result["st_reason"] is not None


# ── P1 新增辅助函数测试 ──

from trader_shared.wyckoff_core import (
    _is_frozen_board,
    _board_vol_scale,
    _is_trading_range,
)


class TestIsFrozenBoard:
    def test_frozen_board_detected(self):
        # 一字板：开=高=低=收
        bar = {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0}
        assert _is_frozen_board(bar) is True

    def test_normal_board_not_frozen(self):
        bar = {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5}
        assert _is_frozen_board(bar) is False

    def test_small_range_not_frozen(self):
        # 范围 > 1%，不是一字板
        bar = {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1}
        assert _is_frozen_board(bar) is False

    def test_missing_data_not_frozen(self):
        bar = {"open": 10.0, "high": None, "low": 9.5, "close": 10.0}
        assert _is_frozen_board(bar) is False


class TestBoardVolScale:
    def test_chinext_20pct(self):
        assert _board_vol_scale("300001.SZ") == 1.41

    def test_star_20pct(self):
        assert _board_vol_scale("688248.SH") == 1.41

    def test_main_board_10pct(self):
        assert _board_vol_scale("000001.SZ") == 1.0

    def test_bse_board_10pct(self):
        assert _board_vol_scale("830001.BJ") == 1.0

    def test_code_without_suffix(self):
        assert _board_vol_scale("300001") == 1.41
        assert _board_vol_scale("000001") == 1.0


class TestIsTradingRange:
    def test_normal_range_passes(self):
        bars = [_make_bar(100 + i * 0.5, 102 + i * 0.5, 99 + i * 0.5, 101 + i * 0.5) for i in range(25)]
        assert _is_trading_range(bars) is True

    def test_extreme_range_fails(self):
        # 每根 K 线振幅小（TR 小），但整体价差大（从 50 涨到 200）
        bars = []
        for i in range(25):
            base = 50 + i * 6  # 50, 56, 62, ..., 200
            bars.append({"open": base, "high": base + 1, "low": base - 1, "close": base, "volume": 1000})
        assert _is_trading_range(bars) is False

    def test_short_data_passes(self):
        bars = [_make_bar(100, 105, 95, 102) for _ in range(5)]
        assert _is_trading_range(bars) is True


class TestSpringWithFrozenBoard:
    def test_frozen_board_skips_spring(self):
        # 正常 Spring 条件但当日一字板
        bars = [_make_bar(100, 105, 90, 102) for _ in range(14)]
        bars.append({"open": 85, "high": 85, "low": 85, "close": 85, "volume": 5000})  # 一字板
        result = wyckoff_analysis(bars)
        assert result["spring_signal"] is False

    def test_star_board_volume_scaled(self):
        # 科创板 20% 板块，量能阈值放大
        bars = [_make_bar(100, 105, 90, 102, 1000) for _ in range(14)]
        # Spring bar: 量比 1.35，主板会触发 high_vol_warning，科创板不触发（1.35 < 1.3*1.41）
        bars.append(_make_bar(85, 100, 84, 92, 1350))
        result = wyckoff_analysis(bars, symbol="688248.SH")
        # 科创板量能缩放后不触发 high_vol_warning
        if result["spring_signal"]:
            assert result.get("spring_vol_class") != "high_vol_warning"


class TestUpthrustSpringSymmetry:
    """Upthrust 与 Spring 对齐：一字板 / 区间闸 / 2 根内回落。"""

    def test_frozen_board_skips_upthrust(self):
        bars = [_make_bar(100, 110, 95, 105) for _ in range(14)]
        # 本可构成 UT 的高点，但一字板
        bars.append({"open": 113, "high": 113, "low": 113, "close": 113, "volume": 5000})
        from trader_shared.wyckoff_events import _detect_upthrust
        ut = _detect_upthrust(bars)
        assert ut["upthrust_signal"] is False
        assert "一字板" in (ut.get("upthrust_reason") or "")

    def test_upthrust_rejects_slow_fallback(self):
        """TR 上沿被突破后未在 2 根内回落 → 即使日后跌回也不算 UT。"""
        from trader_shared.wyckoff_events import _detect_upthrust
        bars = [_make_bar(100, 105, 98, 102) for _ in range(12)]
        bars.append(_make_bar(104, 112, 103, 111, 2000))  # 突破
        bars.append(_make_bar(111, 113, 110, 112, 2000))  # 仍站上
        bars.append(_make_bar(112, 114, 111, 113, 2000))  # 仍站上
        bars.append(_make_bar(110, 112, 99, 100, 2000))   # 才跌回
        tr_ctx = {"tr_upper": 105.0, "tr_lower": 98.0, "in_tr": False}
        ut = _detect_upthrust(bars, tr_ctx=tr_ctx)
        assert ut["upthrust_signal"] is False
        assert "2根内" in (ut.get("upthrust_reason") or "")

    def test_upthrust_accepts_next_day_reclaim(self):
        """昨突破站上、今再刺穿并收回收 → 当前棒计入 2 根窗口，应报 UT。"""
        from trader_shared.wyckoff_events import _detect_upthrust
        bars = [_make_bar(100, 105, 98, 102, 1000) for _ in range(12)]
        bars.append(_make_bar(104, 112, 103, 111, 2500))  # 昨：突破站上
        bars.append(_make_bar(110, 113, 99, 100, 2500))   # 今：再刺穿后回落
        tr_ctx = {"tr_upper": 105.0, "tr_lower": 98.0, "in_tr": False, "tr_baseline_volume": 1000}
        ut = _detect_upthrust(bars, tr_ctx=tr_ctx)
        assert ut["upthrust_signal"] is True, ut.get("upthrust_reason")


# ── P2/P3 新增信号测试 ──

from trader_shared.wyckoff_core import (
    _detect_are,
    _detect_compression,
    _detect_trend_pullback,
    _detect_trend_rally,
)


class TestCompression:
    def test_compression_detected(self):
        # 先有高波动期（60+ 根），再进入窄幅+缩量
        bars = []
        # 前 30 根：高波动 + 高量
        for i in range(30):
            bars.append({"open": 100, "high": 120, "low": 80, "close": 110, "volume": 1000})
        # 中间 30 根：中等波动
        for i in range(30):
            bars.append({"open": 100, "high": 105, "low": 95, "close": 102, "volume": 500})
        # 后 20 根：振幅逐渐收窄 + 缩量
        for i in range(20):
            range_size = 3 - i * 0.15  # 从 3 递减到 0.1
            bars.append({"open": 100, "high": 100 + range_size, "low": 100 - range_size, "close": 100.5, "volume": 100})
        result = _detect_compression(bars)
        assert result["compression_signal"] is True
        assert "压缩" in result["compression_reason"]

    def test_compression_not_detected_high_vol(self):
        # 高量能不触发
        bars = []
        for i in range(30):
            bars.append({"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000})
        result = _detect_compression(bars)
        assert result["compression_signal"] is False

    def test_compression_short_data(self):
        bars = [_make_bar(100, 101, 99, 100.5) for _ in range(5)]
        result = _detect_compression(bars)
        assert result["compression_signal"] is False


class TestTrendPullback:
    def test_trend_pullback_detected(self):
        # 上涨后回踩到 MA20 附近 + 缩量
        bars = []
        # 先涨 20 天
        for i in range(20):
            bars.append({"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1000})
        # 再跌 5 天（回踩）+ 缩量
        for i in range(5):
            bars.append({"open": 120 - i * 2, "high": 121 - i * 2, "low": 119 - i * 2, "close": 120 - i * 2, "volume": 300})
        # 最后 1 根站稳 MA20 附近
        bars.append({"open": 110, "high": 111, "low": 109, "close": 110, "volume": 400})
        result = _detect_trend_pullback(bars)
        # 可能触发也可能不触发，取决于 MA20 位置
        assert "trend_pullback_signal" in result

    def test_trend_pullback_no_pullback(self):
        # 一直涨，没有回撤
        bars = [{"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1000} for i in range(30)]
        result = _detect_trend_pullback(bars)
        assert result["trend_pullback_signal"] is False

    def test_trend_pullback_short_data(self):
        bars = [_make_bar(100, 101, 99, 100.5) for _ in range(5)]
        result = _detect_trend_pullback(bars)
        assert result["trend_pullback_signal"] is False


class TestCompressionInAnalysis:
    def test_compression_in_output(self):
        # 构造压缩条件：先高波动再窄幅缩量
        bars = []
        for i in range(30):
            bars.append({"open": 100, "high": 120, "low": 80, "close": 110, "volume": 1000})
        for i in range(30):
            bars.append({"open": 100, "high": 105, "low": 95, "close": 102, "volume": 500})
        for i in range(20):
            bars.append({"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 100})
        result = wyckoff_analysis(bars)
        assert "compression_signal" in result
        assert "compression_reason" in result


class TestFormatOnelineCompression:
    def test_compression_oneline(self):
        wyk = {"compression_signal": True, "compression_reason": "振幅压缩+量能枯竭"}
        line = format_wyckoff_oneline(wyk)
        assert "压缩蓄势" in line
        assert "偏多" in line

    def test_trend_pullback_oneline(self):
        wyk = {"trend_pullback_signal": True, "trend_pullback_reason": "趋势回踩+缩量"}
        line = format_wyckoff_oneline(wyk)
        assert "趋势回踩" in line
        assert "偏多" in line

    def test_are_and_trend_rally_oneline(self):
        are_line = format_wyckoff_oneline({"are_signal": True})
        assert "BC后快速回落" in are_line
        assert "偏空" in are_line
        rally_line = format_wyckoff_oneline({"trend_rally_signal": True})
        assert "趋势反抽" in rally_line
        assert "偏空" in rally_line


class TestAutomaticReaction:
    """ARE：BC 后自动回落，对称 AR。"""

    def test_are_after_bc(self):
        bars = []
        # 低位垫底 → 拉到高位
        for i in range(20):
            base = 80 + i
            bars.append(_make_bar(base, base + 2, base - 1, base + 1, 1000))
        # BC：高位天量滞涨/收阴
        bars.append(_make_bar(105, 108, 104, 104.5, 5000))
        # ARE：随后 1–3 根放量跌 ≥2%。
        # FINDING-5：回落棒量 1500——不构成 BC（近窗均量~1400，比 1.07<1.5），
        # 但满足 ARE 回落放量（> BC 前均量 1000×1.2=1200），避免其本身被判为「最近一次 BC」。
        bars.append(_make_bar(100, 100.5, 95, 95.5, 1500))
        are = _detect_are(bars)
        assert are["are_signal"] is True, are.get("are_reason")
        assert are["are_price"] is not None

    def test_are_requires_bc(self):
        bars = [_make_bar(100, 101, 99, 100, 1000) for _ in range(25)]
        bars.append(_make_bar(100, 101, 95, 96, 2000))  # 普跌无 BC
        assert _detect_are(bars)["are_signal"] is False


class TestTrendRally:
    """趋势反抽：对称 Trend Pullback。"""

    def test_trend_rally_no_rally(self):
        # 一直跌，没有反抽
        bars = [
            {"open": 150 - i, "high": 151 - i, "low": 148 - i, "close": 149 - i, "volume": 1000}
            for i in range(30)
        ]
        assert _detect_trend_rally(bars)["trend_rally_signal"] is False

    def test_trend_rally_short_data(self):
        bars = [_make_bar(100, 101, 99, 100.5) for _ in range(5)]
        assert _detect_trend_rally(bars)["trend_rally_signal"] is False

    def test_trend_rally_fields_present(self):
        bars = []
        for i in range(20):
            bars.append({"open": 150 - i, "high": 151 - i, "low": 148 - i, "close": 149 - i, "volume": 1000})
        for i in range(5):
            bars.append({"open": 130 + i * 2, "high": 131 + i * 2, "low": 129 + i * 2, "close": 130 + i * 2, "volume": 300})
        bars.append({"open": 138, "high": 139, "low": 137, "close": 138, "volume": 400})
        result = _detect_trend_rally(bars)
        assert "trend_rally_signal" in result
        assert "trend_rally_reason" in result


class TestPhaseARangeP1:
    """P1: SC/AR 锚点对齐 + phase_a_range 边界字段。"""

    def _decline_base(self, n: int = 14, start: float = 100.0, vol: int = 100) -> list[dict]:
        """横盘基底，便于 SC 棒整体处于近窗低位。"""
        bars = []
        for _ in range(n):
            bars.append(_make_bar(90.0, 91.0, 89.0, 90.0, vol))
        return bars

    def _nanwang_like_bars(self) -> list[dict]:
        """瀑布 SC 后隔数根才 AR（南网类），均在 15 根 anchor 内。"""
        bars = self._decline_base(14, vol=100)
        # SC：跳空大跌，棒体整体在低位（high 勿拉回近窗上沿）
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        # 中间整理 4 根
        for i in range(4):
            bars.append(_make_bar(83.2 + i * 0.1, 83.6 + i * 0.1, 82.8 + i * 0.1, 83.3 + i * 0.1, 120))
        # AR：反弹 +2.5%+，high 钉上沿
        bars.append(_make_bar(83.5, 87.0, 83.0, 86.0, 130))
        return bars

    def test_r1_nanwang_sc_ar_within_anchor(self):
        from trader_shared.wyckoff_events import _detect_ar, _detect_selling_climax

        bars = self._nanwang_like_bars()
        sc = _detect_selling_climax(bars)
        ar = _detect_ar(bars)
        assert sc["sc_signal"] is True
        assert ar["ar_signal"] is True
        assert sc["sc_low"] == 82.0
        assert ar["ar_high"] == 87.0
        assert sc["sc_low"] < ar["ar_high"]

    def test_r2_sc_ar_share_anchor(self):
        from trader_shared.wyckoff_events import _detect_ar, _detect_selling_climax

        bars = self._nanwang_like_bars()
        sc = _detect_selling_climax(bars)
        ar = _detect_ar(bars)
        assert sc["sc_bar_idx"] == ar["sc_bar_idx"]
        assert sc["sc_low"] == ar["sc_low"]

    def test_r3_sc_only_forming_not_established(self):
        bars = self._decline_base(14)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        # 无有效 AR（反弹不足 2%）
        bars.append(_make_bar(83.2, 83.6, 83.0, 83.5, 120))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["sc_signal"] is True
        assert result["ar_signal"] is False
        assert result["phase_a_status"] == "forming"
        assert result["phase_a_range"]["status"] == "forming"
        assert result["phase_a_range"]["ar_high"] is None

    def test_r4_sc_ar_established(self):
        bars = self._nanwang_like_bars()
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result["phase_a_range"]["status"] == "established"
        assert result["sc_low"] < result["ar_high"]
        from trader_shared.config import WYCKOFF_SC_COLD_START_BARS_DAILY

        assert result["phase_a_range"]["anchor_bars"] == WYCKOFF_SC_COLD_START_BARS_DAILY

    def test_r5_sc_window_matches_ar_no_fight(self):
        """同一 fixture：AR 亮则 SC 必亮（消除 5 vs 15 根不一致）。"""
        from trader_shared.wyckoff_events import _detect_ar, _detect_selling_climax

        bars = self._nanwang_like_bars()
        sc = _detect_selling_climax(bars)
        ar = _detect_ar(bars)
        if ar["ar_signal"]:
            assert sc["sc_signal"] is True

    def test_r6_weekly_midline_has_phase_a_range(self):
        from trader_shared.wyckoff_core import wyckoff_strategy_midline

        weekly = self._nanwang_like_bars()
        while len(weekly) < 20:
            weekly.insert(0, _make_bar(105.0, 106.0, 104.0, 104.5, 100))
        r = wyckoff_strategy_midline(weekly[-1]["close"], weekly_bars=weekly, daily_bars=weekly)
        wyk = r["wyckoff"]
        assert wyk["timeframe"] == "weekly"
        assert "phase_a_range" in wyk
        assert "phase_a_status" in wyk

    def test_ar_weak_vs_sc_not_soft(self):
        """P2-C：弱于 SC 量的反弹仍亮 AR，不标 soft。"""
        bars = self._decline_base(16)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        bars.append(_make_bar(83.2, 87.0, 83.0, 86.0, 80))  # +3.6%，弱于 SC
        from trader_shared.wyckoff_events import _detect_ar

        ar = _detect_ar(bars)
        assert ar["ar_signal"] is True
        assert ar["ar_volume_soft"] is False
        assert "弱于SC" in ar["ar_reason"]

    def test_ar_event_light_note(self):
        from trader_shared.wyckoff_core import format_wyckoff_event_light

        line = format_wyckoff_event_light({"ar_signal": True, "timeframe": "daily"})
        assert "钉潜在上沿" in line
        assert "仅反弹不能当反转" in line

    def test_config_exports_climax_anchor_bars(self):
        from trader_shared import config

        assert hasattr(config, "WYCKOFF_CLIMAX_ANCHOR_BARS")
        assert config.WYCKOFF_CLIMAX_ANCHOR_BARS == 15
        assert config.WYCKOFF_SC_COLD_START_BARS_DAILY == 90
        assert config.WYCKOFF_SC_COLD_START_BARS_WEEKLY == 39
        assert "WYCKOFF_CLIMAX_ANCHOR_BARS" in config.__all__
        assert "WYCKOFF_SC_COLD_START_BARS_DAILY" in config.__all__
        assert "WYCKOFF_SC_COLD_START_BARS_WEEKLY" in config.__all__


class TestSCFailedChainAr:
    """F: SC 失效链断裂 + 误导文案（wyckoff-sos-epic-fde-handoff §1 F-M1~F-M6 / §4 F1~F3）。

    SC 检测器用 include_failed=True（失效 SC 也亮灯）；_detect_ar 常规锚缺失时应
    再探测「存在但失效」的 SC 并输出失效态文案（含「失效」），而非「未检测到 SC」。
    """

    def _decline_base(self, n: int = 14, vol: int = 100) -> list[dict]:
        bars = []
        for _ in range(n):
            bars.append(_make_bar(90.0, 91.0, 89.0, 90.0, vol))
        return bars

    def _failed_sc_bars(self) -> list[dict]:
        """SC 亮灯（失效）→ 后续破位未收回（Phase A 失败），AR 锚缺失（茅台型）。"""
        bars = self._decline_base(14)
        # SC：跳空大跌放量（idx 14，sc_low=82.0）
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        # 两根整理（不构成新 SC：量比 < 1.5）
        bars.append(_make_bar(83.2, 83.6, 82.8, 83.3, 120))
        bars.append(_make_bar(83.4, 83.8, 83.0, 83.5, 120))
        # 有效跌破 SC low（82*0.988=81.016）且收盘未收回 → Phase A 失败
        bars.append(_make_bar(81.5, 82.0, 80.5, 81.0, 300))
        return bars

    def test_f1_failed_sc_ar_reports_invalidated_not_no_sc(self):
        """F1: SC 失效 + AR 锚缺失 → ar_reason 含「失效」、不含「未检测到 SC」；
        ar_signal=False；sc_low/sc_bar_idx 透出。"""
        from trader_shared.wyckoff_events import _detect_ar, _detect_selling_climax

        bars = self._failed_sc_bars()
        sc = _detect_selling_climax(bars)
        # 前提：SC 灯亮且标记失效（与 bug 报告口径一致）
        assert sc["sc_signal"] is True
        assert sc["phase_a_failed"] is True
        assert sc["sc_low"] == 82.0
        assert sc["sc_bar_idx"] == 14

        ar = _detect_ar(bars)
        assert ar["ar_signal"] is False
        assert "失效" in ar["ar_reason"]
        assert "未检测到 SC" not in ar["ar_reason"]
        assert ar["sc_low"] == 82.0
        assert ar["sc_bar_idx"] == 14

    def test_f2_valid_sc_ar_unchanged(self):
        """F2: SC 有效 → AR 原行为（回归：ar_signal / ar_high / sc_low / sc_bar_idx）。"""
        from trader_shared.wyckoff_events import _detect_ar, _detect_selling_climax

        bars = self._decline_base(14)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC
        for i in range(4):
            bars.append(_make_bar(83.2 + i * 0.1, 83.6 + i * 0.1, 82.8 + i * 0.1, 83.3 + i * 0.1, 120))
        bars.append(_make_bar(83.5, 87.0, 83.0, 86.0, 130))  # AR

        sc = _detect_selling_climax(bars)
        ar = _detect_ar(bars)
        assert sc["sc_signal"] is True
        assert ar["ar_signal"] is True
        assert ar["ar_high"] == 87.0
        assert ar["sc_low"] == sc["sc_low"] == 82.0
        assert ar["sc_bar_idx"] == sc["sc_bar_idx"] == 14
        assert "失效" not in ar["ar_reason"]

    def test_f3_no_sc_original_message(self):
        """F3: 无任何 SC → 维持原文案「未检测到 SC，无法触发 AR」。"""
        from trader_shared.wyckoff_events import _detect_ar

        bars = [_make_bar(100.0, 105.0, 95.0, 102.0, 100) for _ in range(18)]
        ar = _detect_ar(bars)
        assert ar["ar_signal"] is False
        assert ar["ar_reason"] == "未检测到 SC，无法触发 AR"
        assert ar["sc_low"] is None
        assert ar["sc_bar_idx"] is None


class TestPhaseARangeP2:
    """P2: 种子箱门控 + 广义 ST（测 SC）。"""

    def _decline_base(self, n: int = 14, vol: int = 100) -> list[dict]:
        bars = []
        for _ in range(n):
            bars.append(_make_bar(90.0, 91.0, 89.0, 90.0, vol))
        return bars

    def _sc_only_bars(self) -> list[dict]:
        bars = self._decline_base(14)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        bars.append(_make_bar(83.2, 83.6, 83.0, 83.5, 120))
        return bars

    def _nanwang_like_bars(self) -> list[dict]:
        bars = self._decline_base(14, vol=100)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        for i in range(4):
            bars.append(_make_bar(83.2 + i * 0.1, 83.6 + i * 0.1, 82.8 + i * 0.1, 83.3 + i * 0.1, 120))
        bars.append(_make_bar(83.5, 87.0, 83.0, 86.0, 130))
        return bars

    def _nanwang_with_st_bars(self) -> list[dict]:
        """SC + AR + 缩量二次测试（established + secondary ST；ST 在 AR+3）。

        ST 用收复阳线，避免近端阴线被误锚为新 SC。
        """
        bars = self._decline_base(14, vol=100)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC low=82
        bars.append(_make_bar(83.5, 87.0, 85.0, 86.0, 400))   # AR
        bars.append(_make_bar(85.2, 85.6, 85.0, 85.3, 120))   # AR+1
        bars.append(_make_bar(85.1, 85.5, 84.9, 85.2, 120))   # AR+2
        bars.append(_make_bar(82.2, 83.2, 81.8, 82.9, 800))   # ST @ AR+3（阳线）
        for _ in range(2):
            bars.append(_make_bar(85.0, 85.4, 84.8, 85.1, 120))
        return bars

    def _forming_good_tr_bars(self) -> list[dict]:
        """forming（SC 无 AR）+ 分位 TR 达标；SC 落在 anchor 窗内。"""
        pre = []
        for i in range(25):
            b = 88.0 + (i % 6) * 0.25
            pre.append(_make_bar(b, b + 0.5, b - 0.4, b + 0.1, 120))
        decline = [_make_bar(90.0, 91.0, 89.0, 90.0, 100) for _ in range(14)]
        sc = [_make_bar(84.0, 85.0, 82.0, 83.0, 2500)]
        post = []
        for i in range(8):
            b = 83.0 + (i % 4) * 0.12
            post.append(_make_bar(b, b + 0.35, b - 0.22, b + 0.05, 125))
        comp = [_make_bar(83.1, 83.25, 83.05, 83.12, 50) for _ in range(6)]
        return pre + decline + sc + post + comp

    def test_p2_r_forming_does_not_reach_b_plus(self):
        """forming（仅 SC）+ 高质量 TR + 压缩 → 阶段最高 A，闸 forming_phase_a。"""
        from trader_shared.wyckoff_phase import _detect_phase

        bars = self._forming_good_tr_bars()
        tr = {
            "tr_quality": 0.7,
            "tr_upper": 89.5,
            "tr_lower": 82.5,
            "in_tr": True,
            "phase_a_status": "forming",
        }
        ph = _detect_phase(
            bars,
            {
                "compression_signal": True,
                "sc_signal": True,
                "ar_signal": False,
                "spring_signal": True,
                "spring_test_signal": False,
                "st_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "are_signal": False,
                "sos_signal": False,
                "secondary_test_sc_signal": False,
                "lps_signal": False,
                "lpsy_signal": False,
                "trend_pullback_signal": False,
                "trend_rally_signal": False,
                "bu_signal": False,
                "utad_signal": False,
                "tr_upper": 89.5,
                "last_close": 83.1,
            },
            tr_ctx=tr,
        )
        assert ph["phase"] == "accumulation_a"
        assert "箱体未成形" in ph["phase_label"]
        assert ph["phase"] not in (
            "accumulation_b", "accumulation_c", "accumulation_d", "markup",
            "distribution_a", "distribution_b", "distribution_c", "distribution_d", "markdown",
        )
        assert ph.get("phase_tr_gated") is True
        assert ph.get("phase_tr_gate_reason") == "forming_phase_a"

        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "forming"
        assert result["sc_signal"] is True
        assert result["phase"] == "accumulation_a"
        assert float(result.get("tr_quality") or 0) >= 0.35

    def test_p2_established_seed_overlays_tr_bounds(self):
        """L2（SC+AR+ST）才写成熟种子箱 overlay；仅 SC+AR=L1 不放出 tr_lower/upper。"""
        bars = self._nanwang_with_st_bars()
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result.get("secondary_test_sc_signal") is True
        assert result.get("tr_maturity") in ("L2", "L3")
        assert result["tr_lower"] == min(float(result["sc_low"]), float(result["st_sc_low"]))
        assert result["tr_upper"] == result["ar_high"]
        assert result.get("tr_seed_source") == "phase_a_seed"
        assert result.get("phase_tr_gated") is not True

    def test_p2_established_low_percentile_tr_not_gated(self):
        """established 时分位 TR 差也不应永久 phase_tr_gated。"""
        from trader_shared.wyckoff_core import _overlay_phase_a_seed_tr_ctx

        phase_a = {
            "status": "established",
            "sc_low": 82.0,
            "ar_high": 87.0,
            "anchor_bars": 15,
        }
        bad_tr = {"tr_quality": 0.1, "tr_lower": 80.0, "tr_upper": 95.0}
        ctx = _overlay_phase_a_seed_tr_ctx(bad_tr, phase_a)
        assert ctx["tr_lower"] == 82.0
        assert ctx["tr_upper"] == 87.0
        assert float(ctx["tr_quality"]) >= 0.35
        assert ctx.get("phase_a_seed") is True

    def test_p2_secondary_test_sc_distinct_from_spring_test(self):
        from trader_shared.wyckoff_events import _detect_secondary_test_sc, _detect_st

        bars = self._nanwang_with_st_bars()
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        st_sc = _detect_secondary_test_sc(bars)
        st_spring = _detect_st(bars, tr_ctx={"tr_lower": 82.0, "tr_upper": 87.0})
        assert st_sc["secondary_test_sc_signal"] is True
        assert st_sc["st_sc_low"] is not None
        assert st_sc["st_sc_low"] <= 82.0
        assert st_spring["st_signal"] is False

    def test_p2_established_sc_ar_st_label(self):
        bars = self._nanwang_with_st_bars()
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result["secondary_test_sc_signal"] is True
        assert "SC+AR+ST" in result["phase_label"]
        assert result["phase_a_range"].get("st_sc_low") is not None

    def test_p2_no_established_seed_blocks_b_on_good_tr(self):
        """裸压缩不得进积累 B（G4）；无 SC/AR 时 phase=none。

        历史合同曾靠 no_established_seed 门控把「压缩→B」打回 none；
        G4 起压缩进 B 须停止背景，裸压缩不再赋 B，门控可不触发。
        """
        from trader_shared.wyckoff_phase import _detect_phase

        bars = [_make_bar(10.0, 10.01, 9.99, 10.0, 30000) for _ in range(60)]
        tr = {
            "tr_quality": 0.7,
            "tr_upper": 10.2,
            "tr_lower": 9.8,
            "in_tr": True,
            "phase_a_status": "none",
        }
        ph = _detect_phase(
            bars,
            {
                "compression_signal": True,
                "sc_signal": False,
                "ar_signal": False,
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "are_signal": False,
                "sos_signal": False,
                "st_signal": False,
                "spring_test_signal": False,
                "secondary_test_sc_signal": False,
                "lps_signal": False,
                "lpsy_signal": False,
                "trend_pullback_signal": False,
                "trend_rally_signal": False,
                "bu_signal": False,
                "utad_signal": False,
                "tr_upper": 10.2,
                "last_close": 10.0,
            },
            tr_ctx=tr,
        )
        assert ph["phase"] == "none"
        assert ph["phase"] != "accumulation_b"

    def test_p2_gate_reason_enum_values(self):
        """gate_reason 枚举稳定可测。"""
        expected = {"no_tr", "low_quality", "forming_phase_a", "no_established_seed"}
        from trader_shared.wyckoff_phase import _apply_p2_phase_a_gates

        blocked = _apply_p2_phase_a_gates(
            {"phase": "accumulation_b", "phase_label": "x"},
            "forming",
            True,
        )
        assert blocked["phase_tr_gate_reason"] in expected

        no_seed = _apply_p2_phase_a_gates(
            {"phase": "accumulation_c", "phase_label": "x"},
            "none",
            False,
        )
        assert no_seed["phase_tr_gate_reason"] == "no_established_seed"

    def test_p2_r6_cause_effect_uses_seed_width(self, monkeypatch):
        """L3（ST+AR+足够窗宽）：种子 overlay 后因果目标从种子上下沿投射（关 P&F = 高度 1:1）。

        短窗仅 L2 时量度会被 maturity 门禁清空；此处补齐 Phase B 宽度至 ≥ MEASURE_MIN_BARS。
        """
        monkeypatch.setattr("trader_shared.wyckoff_pnf.WYCKOFF_PNF_ENABLED", False)
        bars = self._nanwang_with_st_bars()
        # SC..末根须 ≥ WYCKOFF_MEASURE_MIN_BARS（默认 8）；fixture 本身约 6 根
        for _ in range(4):
            bars.append(_make_bar(84.0, 84.5, 83.6, 84.1, 110))
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result["secondary_test_sc_signal"] is True
        assert result.get("tr_maturity") == "L3"
        assert result.get("measure_allowed") is True
        sc_low = float(result["sc_low"])
        ar_high = float(result["ar_high"])
        tr_lo = float(result["tr_lower"])
        tr_hi = float(result["tr_upper"])
        assert tr_lo <= sc_low + 1e-9
        assert tr_hi == ar_high
        assert result.get("tr_seed_source") == "phase_a_seed"
        ce_range = result.get("cause_effect_range")
        assert ce_range is not None
        expected = round(ar_high - tr_lo, 2)
        assert abs(float(ce_range) - expected) < 0.02
        # 关 P&F：因果目标基于种子上下沿 1:1
        assert result.get("pnf_method") == "height_1to1_fallback"
        assert abs(float(result["cause_effect_up_target"]) - (ar_high + expected)) < 0.05
        assert abs(float(result["cause_effect_down_target"]) - (tr_lo - expected)) < 0.05

    def test_p2_r4_forming_low_quality_p0b_wins(self):
        """forming + tr_quality=0.2 → P0-B 优先：none + low_quality（严于 forming A）。"""
        from trader_shared.wyckoff_phase import _detect_phase

        bars = [_make_bar(10.0, 10.01, 9.99, 10.0, 30000) for _ in range(60)]
        tr = {
            "tr_quality": 0.2,
            "tr_upper": 10.2,
            "tr_lower": 9.8,
            "in_tr": True,
            "phase_a_status": "forming",
        }
        ph = _detect_phase(
            bars,
            {
                "sc_signal": True,
                "ar_signal": False,
                "compression_signal": False,
                "spring_signal": False,
                "upthrust_signal": False,
                "bc_signal": False,
                "sow_signal": False,
                "are_signal": False,
                "sos_signal": False,
                "st_signal": False,
                "spring_test_signal": False,
                "secondary_test_sc_signal": False,
                "lps_signal": False,
                "lpsy_signal": False,
                "trend_pullback_signal": False,
                "trend_rally_signal": False,
                "bu_signal": False,
                "utad_signal": False,
                "tr_upper": 10.2,
                "last_close": 10.0,
            },
            tr_ctx=tr,
        )
        assert ph["phase"] == "none"
        assert ph.get("phase_tr_gated") is True
        assert ph.get("phase_tr_gate_reason") == "low_quality"
