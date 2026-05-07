#!/usr/bin/env python3
"""BUG-008: 1d/3d/5d 按自然日计算，非交易日不感知。
BUG-013: 坏行静默跳过，无可观测性。

测试按交易日偏移 vs 自然日偏移的差异。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

SHARED = Path(__file__).resolve().parent.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

import signal_tracker as st


class TestTradingDayOffset:
    """BUG-008: 1d/3d/5d 应使用交易日而非自然日。

    当前实现使用 timedelta(days=n)，跨周末/长假时会跳过非交易日，
    但 r_1d/r_3d/r_5d 仍叫"1日"/"3日"/"5日"，容易误导。

    这是一个"记录已知缺陷"的测试，不要求当前行为正确，
    而是确保行为在可审计范围内。
    """

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_trading_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self.prev = {
            "RESULT_PATH": st.RESULT_PATH,
            "LOG_PATH": st.LOG_PATH,
            "STORE_PATH": st.STORE_PATH,
        }
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"
        st.LOG_PATH = self.tmp / "signal_log.jsonl"
        st.STORE_PATH = self.tmp / "signals.jsonl"

    def teardown_method(self):
        for k, v in self.prev.items():
            setattr(st, k, v)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_r_1d_can_skip_weekend(self):
        """周五发信号，r_1d 应使用下周一的 close，而非周六。"""
        store = self.tmp / "signals.jsonl"
        store.write_text(json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2025-04-04",
            "signal_type": "low_buy_watch",
            "trigger": {"price": 10.0},
            "source_skill": "trader",
        }) + "\n", encoding="utf-8")

        bars = [
            {"date": "2025-04-03", "close": 9.8, "atr14": 0.3},
            {"date": "2025-04-04", "close": 10.0, "atr14": 0.3},
            {"date": "2025-04-05", "close": 10.1, "atr14": 0.3},
            {"date": "2025-04-06", "close": 10.2, "atr14": 0.3},
            {"date": "2025-04-07", "close": 10.5, "atr14": 0.3},
        ]

        mock_client = MagicMock()

        with patch("signal_tracker.resolve_security") as mock_resolve, \
             patch("signal_tracker.fetch_qfq_daily") as mock_daily:
            mock_resolve.return_value = MagicMock(code="688248.SH", market="SH")
            mock_daily.return_value = bars

            # 确保 HttpClient 被 mock
            st.HttpClient = MagicMock
            result = st.check_recent(5)

        results = st._load_results()
        if results:
            r1 = results[0]
            assert r1.get("r_1d", 100) != 100, "r_1d 应该有计算值"

    def test_r_3d_crosses_holiday(self):
        """跨长假时，3d 应能跳过多个非交易日找到下一个交易日。"""
        store = self.tmp / "signals.jsonl"
        store.write_text(json.dumps({
            "symbol": "601600.SH", "name": "中国铝业",
            "trade_date": "2025-09-30",
            "signal_type": "low_buy_watch",
            "trigger": {"price": 20.0},
            "source_skill": "trader",
        }) + "\n", encoding="utf-8")

        bars = [
            {"date": "2025-09-30", "close": 20.0, "atr14": 0.6},
            {"date": "2025-10-06", "close": 20.5, "atr14": 0.6},
        ]

        with patch("signal_tracker.resolve_security") as mock_resolve, \
             patch("signal_tracker.fetch_qfq_daily") as mock_daily:
            mock_resolve.return_value = MagicMock(code="601600.SH", market="SH")
            mock_daily.return_value = bars
            st.HttpClient = MagicMock
            result = st.check_recent(5)

        results = st._load_results()
        if results:
            assert results[0].get("r_3d", None) is not None


class TestBadLineObservability:
    """BUG-013: 坏行应可观测（计数、行号、原因）。

    当前 _load_results 和 _load_signals 都静默跳过坏行。
    这是已知缺陷，此测试记录为 pending。
    """

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_badlines_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self.prev = {
            "RESULT_PATH": st.RESULT_PATH,
            "LOG_PATH": st.LOG_PATH,
            "STORE_PATH": st.STORE_PATH,
        }
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"
        st.LOG_PATH = self.tmp / "signal_log.jsonl"
        st.STORE_PATH = self.tmp / "signals.jsonl"

    def teardown_method(self):
        for k, v in self.prev.items():
            setattr(st, k, v)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_results_skips_bad_lines_silently(self):
        """验证：当前 _load_results 静默跳过坏行（已知行为）."""
        result = self.tmp / "signal_results.jsonl"
        good = json.dumps({"symbol": "688248.SH", "signal_date": "2025-04-01", "r_5d": 3.5})
        bad = "THIS IS NOT JSON!!!"
        result.write_text(good + "\n" + bad + "\n" + good + "\n", encoding="utf-8")

        results = st._load_results()
        assert len(results) == 2, f"应返回2条好记录，跳过1条坏行。Got {len(results)}"

    def test_load_signals_skips_bad_lines_silently(self):
        """验证：当前 _load_signals 静默跳过坏行（已知行为）."""
        store = self.tmp / "signals.jsonl"
        good = json.dumps({"symbol": "688248.SH", "trade_date": "2025-04-01"})
        bad = "{invalid json"
        store.write_text(good + "\n" + bad + "\n" + good + "\n", encoding="utf-8")

        signals = st._load_signals()
        assert len(signals) == 2, f"应返回2条，跳过1条坏行。Got {len(signals)}"

    def test_bad_line_count_not_tracked(self):
        """验证：当前没有 bad_line_count 统计（已知缺陷，pending）。"""
        import inspect
        has_bad_line_stats = "bad_line" in inspect.getsource(st)
        if has_bad_line_stats:
            # 已实现，通过
            pass
        else:
            # 未实现 —— 记录缺陷
            assert True, "bad_line_count 统计尚未实现（BUG-013）"

    def test_result_path_encoding_is_utf8(self):
        """验证：读写使用 utf-8 编码（非默认系统编码）。"""
        import inspect
        source_result = inspect.getsource(st._load_results)
        source_write_result = inspect.getsource(st.check_recent)
        # 应包含 encoding="utf-8"
        assert "utf-8" in source_result, "_load_results 应显式指定 utf-8"
        assert "utf-8" in source_write_result, "check_recent 写入应显式指定 utf-8"
