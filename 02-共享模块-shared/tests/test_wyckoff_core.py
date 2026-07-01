from __future__ import annotations

import sys

for mod in ("trader_shared.wyckoff_core", "light_data"):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.wyckoff_core import wyckoff_analysis, calculate_wyckoff_score


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
        bars.append(_make_bar(90, 113, 100, 107))
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
    def test_sow_detected_single_day(self):
        # 最近 14 天的 low 分别为 95
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        # 当天跌破 95，收在 94（确切跌破），成交量 101（量比 1.01 >= WYCKOFF_SOW_VOL_RATIO_THRESHOLD=1.0）
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 101})
        result = wyckoff_analysis(bars)
        assert result["sow_signal"] is True
        assert result["sow_price"] == 95.0

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
        assert result["score"] >= 60  # raw=25, score=50+25*50//80=65
        assert result["raw"] == 25    # 仅 Spring, 无其他信号
        assert any("Spring" in s for s in result["signals"])
        assert len([s for s in result["signals"] if "弱势" in s]) == 0
        assert "偏多" in result["summary"]  # score=65 → 偏多区间

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
        # 第 26 根: UT 触发 bar, volume=100 (避免 SOS 因 _make_bar 默认 volume=1000 而触发)
        bars.append({"open": 100, "high": 107, "low": 100, "close": 104, "volume": 100})
        # high=107 > 105.525 且 close=104 < 104.475 → 触发 Upthrust
        # baseline (bars[-11:-1]) 均量=100, current vol=100, SOS 不触发 (100 < 100*1.2)
        result = calculate_wyckoff_score(bars)
        assert result["raw"] == -20, f"Expected -20, got {result['raw']}: {result['signals']}"
        assert result["score"] == 39  # 50 + (-20)*50//95 = 50 - 11 = 39 (Python floor div)
        assert any("Upthrust" in s for s in result["signals"])
        assert "偏空" in result["summary"]

    def test_bearish_div_only(self):
        """仅看空背离 → 轻微看空"""
        bars = self._make_bars([
            {"open": 11, "high": 13, "low": 11, "close": 12, "volume": 500},
            {"open": 11, "high": 12, "low": 10, "close": 11, "volume": 600},
            {"open": 11, "high": 13, "low": 11, "close": 13, "volume": 550},
            {"open": 12, "high": 13, "low": 12, "close": 12, "volume": 500},
            {"open": 12, "high": 14, "low": 12, "close": 13, "volume": 200},  # 价格创新高+量能萎缩
        ])
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
        """弱势信号 → 扣分"""
        bars = [_make_bar(100, 105, 95, 100, 100) for _ in range(14)]
        bars.append({"open": 98, "high": 99, "low": 93, "close": 94, "volume": 101})
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
    """LPS (Last Point of Support) 最后支撑点 检测测试"""

    def test_lps_detected(self):
        """SOS 前缩量回调，低点不破前高 → LPS 触发

        修复后检测窗口 (25+ 根):
          bars[-5:]      = SOS (5 全阳, 放量)
          bars[-15:-5]   = 回调窗口 (5-10 根, 价格下行, 缩量)
          bars[-20:-15]  = pre_low 窗口 (5 根, 低点最低处)
          bars[:-20]     = base (至少 5 根)

        结构: 15 base + 5 pre_low + 5 pullback + 5 SOS = 30
        """
        # 15 根 base: low_min=96, vol=500
        bars = [
            {"open": 100, "high": 103, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 99, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 98, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 97, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 96, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 97, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 96, "close": 100, "volume": 500},
        ]
        # pre_low 5 根 (索引 15-19): 价格抬升, low=101~104
        bars.extend([
            {"open": 103, "high": 105, "low": 104, "close": 104, "volume": 500},
            {"open": 104, "high": 105, "low": 103, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 102, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 101, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 102, "close": 103, "volume": 500},
        ])
        # pullback 5 根 (索引 20-24): 价格下行, low > 94.04, 缩量 < 350
        bars.extend([
            {"open": 103, "high": 104, "low": 103, "close": 104, "volume": 400},
            {"open": 104, "high": 104, "low": 103, "close": 103.5, "volume": 350},
            {"open": 103.5, "high": 104, "low": 102, "close": 102, "volume": 300},
            {"open": 102, "high": 102, "low": 102, "close": 102, "volume": 280},
            {"open": 102, "high": 102, "low": 101.5, "close": 101.5, "volume": 250},
        ])
        # SOS 5 根 (索引 25-29): 全阳线, vol=1000, 涨幅 > 2%
        bars.extend([
            {"open": 101.5, "high": 103, "low": 101.5, "close": 102.5, "volume": 1000},
            {"open": 102.5, "high": 103.5, "low": 102.5, "close": 103.5, "volume": 1000},
            {"open": 103.5, "high": 104.5, "low": 103.5, "close": 104.5, "volume": 1000},
            {"open": 104.5, "high": 105.5, "low": 104.5, "close": 105.5, "volume": 1000},
            {"open": 105.5, "high": 106.5, "low": 105.5, "close": 106.5, "volume": 1000},
        ])
        # 总计 30 根
        # baseline = bars[-15:-5] = bars[15:25] (pre_low + pullback)
        #   = 5*500 + 400+350+300+280+250 = 3580 / 10 = 358
        # SOS avg_vol = 1000 > 358*1.2=429.6 ✓
        # SOS gain = (106.5-101.5)/101.5 = 4.93% > 2% ✓
        # pre_low = min(low of bars[10:15]) = min(96, 96, 98, 97, 96) = 96
        # LPS threshold = 96*0.99 = 94.04
        # pullback low = min(103, 103, 102, 102, 101.5) = 101.5 > 94.04 ✓
        # pullback vol end = 250 < 358*0.7=250.6 ✓
        # pullback price: 104→101.5, 101.5 <= 104*1.01=105.04 ✓
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is True, f"LPS not detected: {result.get('lps_reason')}"
        assert result["lps_price"] is not None


    def test_lps_not_detected_no_sos(self):
        """无 SOS 结构 → LPS 不触发"""
        bars = [_make_bar(100, 105, 95, 102, 500) for _ in range(25)]
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False

    def test_lps_not_detected_breaks_low(self):
        """回调跌破 SOS 前低 → LPS 不触发"""
        # 前 13 根: low_min=96
        bars = [
            {"open": 100, "high": 103, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 99, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 98, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 97, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 96, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
        ]
        # SOS 5 连阳
        bars.extend([
            {"open": 102, "high": 104, "low": 102, "close": 103, "volume": 600},
            {"open": 103, "high": 104, "low": 103, "close": 104, "volume": 600},
            {"open": 104, "high": 105, "low": 104, "close": 104, "volume": 600},
            {"open": 104, "high": 106, "low": 104, "close": 105, "volume": 600},
            {"open": 105, "high": 107, "low": 105, "close": 106, "volume": 600},
        ])
        # 回调跌破前低 (96*0.99=95.04): low=94 < 95.04
        bars.extend([
            {"open": 106, "high": 106, "low": 104, "close": 104, "volume": 450},
            {"open": 104, "high": 105, "low": 103, "close": 103, "volume": 400},
            {"open": 103, "high": 104, "low": 94, "close": 102, "volume": 320},  # low=94 < 95.04
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 300},
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 290},
        ])
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False

    def test_lps_not_detected_high_volume(self):
        """回调末期量能不萎缩 → LPS 不触发"""
        bars = [
            {"open": 100, "high": 103, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 99, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 98, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 97, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
            {"open": 102, "high": 104, "low": 97, "close": 103, "volume": 500},
            {"open": 103, "high": 105, "low": 96, "close": 100, "volume": 500},
            {"open": 100, "high": 103, "low": 96, "close": 101, "volume": 500},
            {"open": 101, "high": 104, "low": 98, "close": 102, "volume": 500},
        ]
        bars.extend([
            {"open": 102, "high": 104, "low": 102, "close": 103, "volume": 600},
            {"open": 103, "high": 104, "low": 103, "close": 104, "volume": 600},
            {"open": 104, "high": 105, "low": 104, "close": 104, "volume": 600},
            {"open": 104, "high": 106, "low": 104, "close": 105, "volume": 600},
            {"open": 105, "high": 107, "low": 105, "close": 106, "volume": 600},
        ])
        # 回调末期量=400 >= 500*0.7=350 → 不满足缩量
        bars.extend([
            {"open": 106, "high": 106, "low": 104, "close": 104, "volume": 450},
            {"open": 104, "high": 105, "low": 103, "close": 103, "volume": 400},
            {"open": 103, "high": 104, "low": 97, "close": 102, "volume": 400},
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 300},
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 290},
        ])
        result = wyckoff_analysis(bars)
        assert result["lps_signal"] is False


class TestWyckoffScoreWithClassicSignals:
    """calculate_wyckoff_score 消费新增经典信号的测试"""

    def test_ar_boosts_score(self):
        """AR 信号 → 分数提升 +10"""
        # BC 检测: vol_ratio=190/10=19, 涨幅0.5%<1%, 上影线=4/6=0.67>0.02 → BC ✓
        # 额外 bars volume=100 避免 BC 误触发
        bars = [_make_bar(100, 105, 95, 102, 10) for _ in range(16)]
        bars.append({"open": 101, "high": 105, "low": 99, "close": 100.5, "volume": 190})  # BC
        bars.extend([_make_bar(103, 105, 102, 104, 100) for _ in range(3)])
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


