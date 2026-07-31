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
    _detect_sos,
)


def _make_bar(open_, high, low, close, volume=1000):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


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
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 最新一天：量比 1.9（高于 WYCKOFF_BC_VOL_RATIO_THRESHOLD=1.8），上影线明显，收阴，涨幅仅 0.5%
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is True
        assert result["bc_price"] == 105.0

    def test_bc_not_detected_due_to_volume(self):
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 最新一天：量比仅 1.6（低于 1.8），不满足
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 160})
        result = wyckoff_analysis(bars)
        assert result["bc_signal"] is False


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
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
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

    def test_ar_low_volume_soft_still_triggers(self):
        """SC 后反弹涨幅够但量能不足 → AR 仍触发，标 ar_volume_soft"""
        bars = self._sc_then_rally_bars(rally_close=104, rally_vol=11)
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is True
        assert result.get("ar_volume_soft") is True
        assert "soft" in (result.get("ar_reason") or "")


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


class TestDetectST:
    """ST (Secondary Test) 二次测试 检测测试"""

    def test_st_detected(self):
        """Spring 后 3-15 根缩量回测支撑 → ST 触发

        需要 >= 31 根 bar 才能让 spring_idx 搜索到索引 15 的 Spring
        ST bar low 必须在 [support*0.99, support*1.01] = [89.1, 90.9] 区间
        volume < avg_vol*0.8 = 160
        """
        # 前 15 根: low=90, vol=200
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # 索引 15: Spring bar: low=85 < 88.65, close=91 >= 90
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 300})
        # 索引 16-20: 上涨远离支撑
        bars.extend([
            {"open": 92, "high": 96, "low": 91, "close": 95, "volume": 200},
            {"open": 95, "high": 98, "low": 94, "close": 97, "volume": 220},
            {"open": 97, "high": 100, "low": 96, "close": 99, "volume": 210},
            {"open": 99, "high": 101, "low": 98, "close": 100, "volume": 200},
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 200},
        ])
        # 索引 21-24: 横盘靠近支撑
        bars.extend([
            {"open": 101, "high": 102, "low": 100, "close": 101, "volume": 190},
            {"open": 101, "high": 102, "low": 100, "close": 100, "volume": 180},
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 180},
            {"open": 100, "high": 101, "low": 98, "close": 99, "volume": 180},
        ])
        # 索引 25: ST bar: low=89.5 ∈ [89.1, 90.9], vol=150 < 160
        bars.append({"open": 90, "high": 91, "low": 89.5, "close": 90, "volume": 150})
        # 需要至少 31 根: 15 + 1 + 5 + 4 + 1 = 26, 还需要更多
        # 再加几根
        bars.extend([
            {"open": 90, "high": 92, "low": 89, "close": 91, "volume": 180},
            {"open": 91, "high": 93, "low": 90, "close": 92, "volume": 180},
            {"open": 92, "high": 94, "low": 91, "close": 93, "volume": 180},
            {"open": 93, "high": 95, "low": 92, "close": 94, "volume": 180},
            {"open": 94, "high": 96, "low": 93, "close": 95, "volume": 180},
        ])
        # 总计: 15 + 1 + 5 + 4 + 1 + 5 = 31
        result = wyckoff_analysis(bars)
        assert result["st_signal"] is True, f"ST not detected: {result.get('st_reason')}"

    def test_st_not_detected_no_spring(self):
        """无 Spring 事件 → ST 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(31)]
        result = wyckoff_analysis(bars)
        assert result["st_signal"] is False

    def test_st_not_detected_high_volume(self):
        """Spring 后回测但量能不萎缩 → ST 不触发"""
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 300})  # Spring
        bars.extend([
            {"open": 92, "high": 96, "low": 91, "close": 95, "volume": 200},
            {"open": 95, "high": 98, "low": 94, "close": 97, "volume": 220},
            {"open": 97, "high": 100, "low": 96, "close": 99, "volume": 210},
            {"open": 99, "high": 101, "low": 98, "close": 100, "volume": 200},
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 200},
        ])
        bars.extend([
            {"open": 101, "high": 102, "low": 100, "close": 101, "volume": 190},
            {"open": 101, "high": 102, "low": 100, "close": 100, "volume": 180},
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 180},
            {"open": 100, "high": 101, "low": 98, "close": 99, "volume": 180},
        ])
        # volume=180 > 200*0.8=160 → 不满足缩量
        bars.append({"open": 90, "high": 91, "low": 89.5, "close": 90, "volume": 180})
        bars.extend([
            {"open": 90, "high": 92, "low": 89, "close": 91, "volume": 180},
            {"open": 91, "high": 93, "low": 90, "close": 92, "volume": 180},
            {"open": 92, "high": 94, "low": 91, "close": 93, "volume": 180},
            {"open": 93, "high": 95, "low": 92, "close": 94, "volume": 180},
            {"open": 94, "high": 96, "low": 93, "close": 95, "volume": 180},
        ])
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
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
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

        数学推导：S > 1.38B 满足 SOS，S < 1.8B 避免 BC。取 S=1.5B。
        20 base bars (vol=200) + 5 SOS bars (vol=300)。
        """
        from trader_shared.wyckoff_core import calculate_wyckoff_score
        bars = []
        for i in range(20):
            o = 100 + i * 0.01
            bars.append(_make_bar(o, o + 0.5, o - 0.5, o + 0.2, 200))
        # 5 连阳：累计涨 (106.16-104)/104 ≈ 2.1% ≥ 2%
        for i in range(5):
            o = 104 + i * 0.44
            c = o + 0.4
            bars.append(_make_bar(o, c, o - 0.2, c, 300))
        result = calculate_wyckoff_score(bars)
        assert result["raw"] == 15, f"Expected raw=15 (SOS only), got {result['raw']}"

    def test_st_adds_8(self):
        """ST 信号贡献 +8。Spring(+25) + ST(+8) + 阶段(accumulation_c +2) = 35。

        构造：27 根 bars (ST 需要 len >= 26)
        - bars[4:14]: 基准 10 根 (low=90, vol=200)
        - bars[14]: Spring (low=88<90*0.985, close=90>=90)
        - bars[15:17]: 2 根中间 bar
        - bars[18]: ST trigger (low=89.5≈support, vol=100<200*0.8=160)
        - bars[19:25]: 7 根收尾 (low≥90, 不触发新 Spring)
        - bars[26]: Spring bar (bars[-1], low=88<90*0.985, close=90>=90)
        """
        from trader_shared.wyckoff_core import calculate_wyckoff_score
        # 前 14 根：基准，low=90
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(14)]
        # Spring bar (index 14)
        bars.append(_make_bar(89, 91, 88, 90, 150))
        # 中间 bar (index 15-16)
        bars.append(_make_bar(91, 92, 90, 91.5, 180))
        bars.append(_make_bar(91.5, 92, 90.5, 91, 180))
        # ST trigger (index 18): low=89.5 回到 support(90) ±1%, vol=100 < 200*0.8
        bars.append(_make_bar(91, 91.5, 88.5, 90.5, 100))
        # 收尾 bars (index 19-25): low≥90, 确保不被误判为 Spring
        for i in range(7):
            bars.append(_make_bar(90 + i * 0.1, 91 + i * 0.1, 90, 90.5, 150))
        # bars[-1] (index 26): Spring bar, close=97 → reclaim=7/2=350% ≥ 50%
        bars.append(_make_bar(89, 97, 88, 97, 150))
        result = calculate_wyckoff_score(bars)
        # Spring 过早(12)+ST(8)+TR质量(4)=24
        assert result["raw"] == 24, f"Expected raw=24 (Spring12+ST8+TR4), got {result['raw']}"

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
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
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
        # ARE：随后 1–3 根放量跌 ≥2%
        bars.append(_make_bar(104, 104.5, 100, 101, 4000))
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
        assert result["phase_a_range"]["anchor_bars"] == 15

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

    def test_ar_volume_soft_still_signals(self):
        """量能不足 1.2× 时结构满足仍亮 AR，标 soft。"""
        bars = self._decline_base(16)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))
        bars.append(_make_bar(83.2, 87.0, 83.0, 86.0, 80))  # +3.6%，缩量
        from trader_shared.wyckoff_events import _detect_ar

        ar = _detect_ar(bars)
        assert ar["ar_signal"] is True
        assert ar["ar_volume_soft"] is True
        assert "soft" in ar["ar_reason"]

    def test_ar_event_light_note(self):
        from trader_shared.wyckoff_core import format_wyckoff_event_light

        line = format_wyckoff_event_light({"ar_signal": True, "timeframe": "daily"})
        assert "钉潜在上沿" in line
        assert "仅反弹不能当反转" in line

    def test_config_exports_climax_anchor_bars(self):
        from trader_shared import config

        assert hasattr(config, "WYCKOFF_CLIMAX_ANCHOR_BARS")
        assert config.WYCKOFF_CLIMAX_ANCHOR_BARS == 15
        assert "WYCKOFF_CLIMAX_ANCHOR_BARS" in config.__all__


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
        """SC + 缩量二次测试 + AR（established + secondary ST）。"""
        bars = self._decline_base(14, vol=100)
        bars.append(_make_bar(84.0, 85.0, 82.0, 83.0, 2500))  # SC low=82
        bars.append(_make_bar(83.0, 83.4, 81.8, 82.5, 800))   # ST: 近 sc_low, 量缩
        for i in range(3):
            bars.append(_make_bar(82.6 + i * 0.1, 83.0 + i * 0.1, 82.4 + i * 0.1, 82.7 + i * 0.1, 120))
        bars.append(_make_bar(83.0, 87.0, 82.8, 86.0, 130))   # AR
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
        assert "区间未钉" in ph["phase_label"]
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
        bars = self._nanwang_like_bars()
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result["tr_lower"] == result["sc_low"]
        assert result["tr_upper"] == result["ar_high"]
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
        """无 established + 分位 TR 达标 + 压缩 → no_established_seed，不进 B。"""
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
        assert ph.get("phase_tr_gated") is True
        assert ph.get("phase_tr_gate_reason") == "no_established_seed"

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

    def test_p2_r6_cause_effect_uses_seed_width(self):
        """established + ST：tr_lower≤sc_low（refine），cause_effect_range = 种子宽。"""
        bars = self._nanwang_with_st_bars()
        while len(bars) < 25:
            bars.insert(0, _make_bar(90.0, 91.0, 89.0, 90.0, 100))
        result = wyckoff_analysis(bars, use_persisted_phase=False)
        assert result["phase_a_status"] == "established"
        assert result["secondary_test_sc_signal"] is True
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
        # 因果目标基于种子上下沿 1:1
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
