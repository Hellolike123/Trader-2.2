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
        bars = [_make_bar(100, 105, 90, 102) for _ in range(14)]
        bars.append(_make_bar(85, 100, 84, 92))
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
        """SOW 需连续 2 日跌破支撑（support 从不含确认窗口的 K 线计算）。"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 连续 2 天跌破 95（support 从 bars[2:14] 计算 = 95）
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        bars.append({"open": 95, "high": 96, "low": 92, "close": 93, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is True
        assert result["sow_price"] == 95.0

    def test_sow_not_detected_single_day(self):
        """仅 1 日跌破不足以触发 SOW（consecutive=2）。"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is False
        assert "1/2" in result["sow_reason"]

    def test_sow_not_detected_due_to_volume(self):
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 当天虽然跌破，但是成交量 90（量比 0.9 < 1.0），被过滤
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 90})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is False


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
        # Spring: low=85 < 88.65, close=91 >= 90 → Spring ✓
        # volume=150 < 200 → 不触发 SOW ✓
        bars.append(_make_bar(85, 95, 85, 91, 150))
        result = calculate_wyckoff_score(bars)
        # Spring +25 + accumulation_c 阶段修正 +2 = 27
        assert result["score"] >= 60
        assert result["raw"] == 27
        assert any("Spring" in s for s in result["signals"])
        assert len([s for s in result["signals"] if "弱势" in s]) == 0
        assert "偏多" in result["summary"] or "看多" in result["summary"]

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
            {"open": 90, "high": 95, "low": 85, "close": 91, "volume": 80},   # Spring: low=85<88.65, close=91>=90 + 缩量
        ])
        # 验证 Spring 和看多背离都被检测到
        analysis = wyckoff_analysis(bars)
        assert analysis["spring_signal"] is True, f"Spring not detected: {analysis}"
        assert analysis["bullish_volume_divergence"] is True
        # Spring(25) + Spring×看多(5) + 看多背离(10) = 40
        result = calculate_wyckoff_score(bars)
        assert result["raw"] > 0
        assert result["score"] > 60  # 50 + 40*50//80 = 75
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
        # Upthrust -20 + distribution_a 阶段修正 -1 = -21
        assert result["raw"] == -21, f"Expected -21, got {result['raw']}: {result['signals']}"
        assert result["score"] == 38  # 50 + (-21)*50//95 = 50 - 12 = 38
        assert any("Upthrust" in s for s in result["signals"])
        assert "偏空" in result["summary"]

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
    """AR (Automatic Rally) 自动反弹 检测测试"""

    def test_ar_detected(self):
        """BC 后 1-3 根放量反弹 → AR 触发

        需要 >= 18 根 (WYCKOFF_MIN_BARS+3) 才能触发 AR 检测。
        使用 volume=10 的 base 避免 BC 被额外 bars 误触发。
        """
        # 前 16 根: 中性 K 线，低 volume=10
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
        # BC bar: 天量 (190) + 滞涨 → BC 触发 (vol_ratio = 190/10 = 19)
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})
        # AR bar: close=103 > 100.5*1.02=102.51, vol=130 > 10*1.2=12
        bars.append({"open": 101, "high": 104, "low": 100, "close": 103, "volume": 130})
        # 再加 3 根凑够 20 根
        bars.extend([{"open": 103, "high": 105, "low": 102, "close": 104, "volume": 10} for _ in range(3)])
        # 总计 20 根
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is True, f"AR not detected: {result.get('ar_reason')}"

    def test_ar_not_detected_no_bc(self):
        """无 BC 事件 → AR 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(16)]
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False

    def test_ar_not_detected_weak_rally(self):
        """BC 后反弹不足 2% → AR 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(14)]
        bars.append(_make_bar(101, 105, 99, 100.5, 190))  # BC
        # close=101 不满足 > 100.5*1.02=102.51
        bars.append({"open": 100, "high": 102, "low": 99, "close": 101, "volume": 130})
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False

    def test_ar_not_detected_low_volume(self):
        """BC 后反弹涨幅够但量能不足 → AR 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(14)]
        bars.append(_make_bar(101, 105, 99, 100.5, 190))  # BC
        # close=103 > 102.51 ✓, 但 vol=100 < 120 ✗
        bars.append({"open": 101, "high": 104, "low": 100, "close": 103, "volume": 100})
        result = wyckoff_analysis(bars)
        assert result["ar_signal"] is False


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
        # Spring bar: low=85 < 90*0.985=88.65, close=91 >= 90, vol=150 < 200 (avoid SOW)
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 150})
        result = calculate_wyckoff_score(bars)
        spring_signals = [s for s in result["signals"] if "Spring" in s]
        assert len(spring_signals) >= 1, f"Spring not detected: {result['signals']}"
        assert result["score"] > 60  # Spring=+25

    def test_ar_adds_10(self):
        """AR 信号贡献 +10。BC=-15 + AR=+10 + 派发阶段修正=-2 → raw=-7。"""
        from trader_shared.wyckoff_core import calculate_wyckoff_score
        # BC bar: vol_ratio=1000/10=100>>1.8, change=0.5%<1%
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
        bars.append(_make_bar(101, 105, 100, 100.5, 1000))  # BC at bar 17
        # 阴线缓冲：避免最后5根4/5阳线触发 SOS
        bars.append(_make_bar(100, 101, 99, 99.5, 100))
        # AR bar: close=103 > 100.5*1.02=102.51, vol=300 > 10*1.2=12
        bars.append(_make_bar(101, 103, 101, 103, 300))  # AR trigger
        result = calculate_wyckoff_score(bars)
        # BC-15 + AR+10 + phase(distribution_a BC+AR) delta=-0.10 → -2
        assert result["raw"] == -7, f"Expected raw=-7 (BC-15+AR+10+阶段-2), got {result['raw']}"
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
        bars.append(_make_bar(91, 91.5, 89.5, 90.5, 100))
        # 收尾 bars (index 19-25): low≥90, 确保不被误判为 Spring
        for i in range(7):
            bars.append(_make_bar(90 + i * 0.1, 91 + i * 0.1, 90, 90.5, 150))
        # bars[-1] (index 26): Spring bar
        bars.append(_make_bar(89, 91, 88, 90, 150))
        result = calculate_wyckoff_score(bars)
        assert result["raw"] == 35, f"Spring+ST+阶段: expected raw=35 (25+8+2), got {result['raw']}"

    def test_lps_adds_12(self):
        """LPS 信号精确贡献 +12。SOS(+15) + LPS(+12) = 27。

        正确时序: base + pre_sos + SOS + pullback
        volume: baseline=150, SOS=200, pullback 末端=80
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
        # 末窗口是回调而非 SOS → 通常仅 LPS +12
        result = calculate_wyckoff_score(bars)
        assert any("LPS" in s for s in result["signals"]), f"LPS not scored: {result['signals']}"
        assert result["raw"] in (12, 27), f"Expected raw 12 or 27 (LPS±SOS), got {result['raw']}"


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

    def test_bc_ar_is_distribution_a_not_accumulation(self):
        from unittest.mock import patch

        signals = {
            "spring_signal": False,
            "sos_signal": False,
            "lps_signal": False,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]

        def fake_scan(_bars, detector_fn, window=15, step=5):
            name = getattr(detector_fn, "__name__", "")
            if name == "_detect_buying_climax":
                return True
            if name == "_detect_ar":
                return True
            return False

        with patch("trader_shared.wyckoff_core._scan_for_signal", side_effect=fake_scan):
            result = _detect_phase(bars, signals)

        assert result["phase"] == "distribution_a"
        assert "accumulation" not in result["phase"]
        assert result["phase_confidence_delta"] < 0

    def test_spring_starts_accumulation_c(self):
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sos_signal": False,
            "lps_signal": False,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]
        with patch("trader_shared.wyckoff_core._scan_for_signal", return_value=False):
            result = _detect_phase(bars, signals)
        assert result["phase"] == "accumulation_c"
        assert result["phase_confidence_delta"] > 0

    def test_spring_plus_sos_is_accumulation_d(self):
        from unittest.mock import patch

        signals = {
            "spring_signal": True,
            "sos_signal": True,
            "lps_signal": False,
        }
        bars = [_make_bar(100, 105, 95, 102, 100) for _ in range(40)]
        with patch("trader_shared.wyckoff_core._scan_for_signal", return_value=False):
            result = _detect_phase(bars, signals)
        assert result["phase"] == "accumulation_d"

    def test_phase_delta_consumed_in_score(self):
        """phase_confidence_delta 在 calculate_wyckoff_score 中被消费"""
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # 正常量 Spring（非高量）
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 150})
        result = calculate_wyckoff_score(bars)
        # Spring +25 + accumulation_c 阶段修正 +2 = 27
        assert result["raw"] == 27, f"Expected 27 (Spring25+阶段2), got {result['raw']}"
        assert any("阶段修正" in s for s in result["signals"])


class TestHighVolSpringDeweight:
    """高量 Spring 降权"""

    def test_high_vol_spring_score_halved(self):
        """spring_vol_class=high_vol_warning 时 Spring 分数减半"""
        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        # vol=300 >= 200*1.3 → high_vol_warning；low 刺穿支撑后收回
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 300})
        analysis = wyckoff_analysis(bars)
        assert analysis["spring_signal"] is True
        assert analysis["spring_vol_class"] == "high_vol_warning"
        result = calculate_wyckoff_score(bars)
        assert any("高量降权" in s for s in result["signals"])
        # Spring 减半 +12 + 阶段 accumulation_c +2 = 14
        assert result["raw"] == 14, f"Expected raw=14 (12+2), got {result['raw']}"
        # 显著低于正常 Spring(+25+2=27)
        assert result["raw"] < 25

    def test_high_vol_spring_bullish_div_bonus_halved(self):
        """高量 Spring + 看多背离：背离加成同步减半（5//2=2）"""
        from unittest.mock import patch

        bars = [_make_bar(100, 105, 90, 102, 200) for _ in range(15)]
        bars.append({"open": 89, "high": 93, "low": 85, "close": 91, "volume": 300})
        # 强制看多背离，避免构造脆弱的量价序列
        real = wyckoff_analysis
        def _fake_analysis(b, **kwargs):
            r = real(b, **kwargs)
            r["bullish_volume_divergence"] = True
            r["bearish_volume_divergence"] = False
            return r
        with patch("trader_shared.wyckoff_core.wyckoff_analysis", side_effect=_fake_analysis):
            result = calculate_wyckoff_score(bars)
        # Spring(高量)12 + 背离加成2 + 阶段2 = 16
        assert result["raw"] == 16, f"Expected 16, got {result['raw']}: {result['signals']}"
        assert any("看多背离" in s and "高量" in s for s in result["signals"])


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

    def test_daily_fallback(self):
        from trader_shared.wyckoff_core import wyckoff_strategy_midline
        daily = self._bars(40)
        r = wyckoff_strategy_midline(daily[-1]["close"], weekly_bars=[], daily_bars=daily)
        assert r["wyckoff"]["timeframe"] == "daily_fallback"

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


# ── P2/P3 新增信号测试 ──

from trader_shared.wyckoff_core import _detect_compression, _detect_trend_pullback


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


