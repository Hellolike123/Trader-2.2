#!/usr/bin/env python3
"""Regression tests for BUG-094 (PF formula) / BUG-096 (signal_type unknown).

These tests verify the fix landed correctly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SHARED = Path(__file__).resolve().parent.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

import importlib
import signal_tracker as st
importlib.reload(st)


# ═══════ BUG-094: PF formula (标准 Profit Factor) ═══════

class TestProfitFactorFix:
    """BUG-094: PF = sum_profit/sum_loss，非平均比值。"""

    def test_pf_standard_formula_uses_total_ratio(self):
        """PF 应为总盈利/总亏损绝对值，不是平均盈利/平均亏损绝对值。

        构造场景：
        - 3 个涨: +10%, +20%, +30% → sum_profit = 60%
        - 2 个跌: -5%, -15% → sum_loss_abs = 20%
        - 正确 PF = 60/20 = 3.0
        - 旧公式 PF = avg(10,20,30)/avg(5,15) = 60/3/10/2 = 20/5 = 2.67 (低估)
        """
        results = [
            {"r_5d": 10, "outcome": "up", "signal_type": "track", "name": "股票A"},
            {"r_5d": 20, "outcome": "up", "signal_type": "track", "name": "股票A"},
            {"r_5d": 30, "outcome": "up", "signal_type": "track", "name": "股票A"},
            {"r_5d": -5, "outcome": "down", "signal_type": "track", "name": "股票A"},
            {"r_5d": -15, "outcome": "down", "signal_type": "track", "name": "股票A"},
        ]
        panel = st._make_panel(results, None)
        # PF = 60/20 = 3.00
        assert "盈亏比 3.00" in panel, f"PF 应为 3.00，实际面板：\n{panel}"

    def test_pf_zero_loss_returns_zero(self):
        """无亏损时 PF 应为 0（不是除以零异常或无穷）。"""
        results = [
            {"r_5d": 10, "outcome": "up", "name": "股票A"},
            {"r_5d": 20, "outcome": "up", "name": "股票A"},
        ]
        panel = st._make_panel(results, None)
        assert "盈亏比 0.00" in panel, f"无亏损时 PF 应为 0，实际面板：\n{panel}"


# ═══════ BUG-096: 空 signal_type → "unknown" ═══════

class TestSignalTypeUnknown:
    """BUG-096: 空 signal_type 分组显示为 'unknown'。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_unknown_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = st.RESULT_PATH
        st.RESULT_PATH = self.tmp / "results.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_signal_type_shows_unknown(self):
        """signal_type 为空字符串时，面板应分组显示为 'unknown'。"""
        rec1 = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2026-04-01", "signal_type": "",
            "r_5d": 3.0, "outcome": "up", "schema_version": 1,
        })
        rec2 = json.dumps({
            "symbol": "601600.SH", "name": "中国铝业",
            "signal_date": "2026-04-02", "signal_type": "",
            "r_5d": -2.0, "outcome": "down", "schema_version": 1,
        })
        st.RESULT_PATH.write_text(rec1 + "\n" + rec2 + "\n", encoding="utf-8")

        panel = st.show_all()
        assert "unknown" in panel.lower() or "unknown" in panel, \
            f"空 signal_type 应分组为 'unknown'，实际面板：\n{panel}"
        # 不应出现以空字符串为键的分组
        assert "'  : 2次" not in panel, "空类型不应以空字符串显示"


# ═══════ BUG-095: 单个样本不应被过滤 ═══════

class TestSingleSampleShown:
    """BUG-095: 个股明细不应跳过 total_s < 2 的记录。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_single_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = st.RESULT_PATH
        st.RESULT_PATH = self.tmp / "results.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_sample_shown_in_stock_detail(self):
        """单个样本的股票应出现在个股明细中，不应被跳过。"""
        rec = json.dumps({
            "symbol": "300750.SZ", "name": "宁德时代",
            "signal_date": "2026-04-01", "signal_type": "track",
            "r_5d": 5.0, "outcome": "up", "schema_version": 1,
        })
        st.RESULT_PATH.write_text(rec + "\n", encoding="utf-8")

        panel = st.show_all()
        assert "宁德时代" in panel, f"单样本股票应出现在面板中，实际：\n{panel}"
        assert "样本:1次" in panel, \
            f"应显示单个样本，实际面板：\n{panel}"


# ═══════ BUG-086: schema_version integer ═══════

class TestSchemaVersion:
    """BUG-086: schema_version 应为整数 1。"""

    def test_schema_version_is_integer(self):
        """新计算的结果应包含 schema_version=1（整数）。"""
        from unittest.mock import MagicMock

        sig = {
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2026-04-02", "signal_type": "track",
            "trigger": {"price": 10}, "source_skill": "trader",
        }

        mock_client = MagicMock()
        mock_bars = []
        import datetime as dt
        start = dt.date(2026, 3, 5)
        for i in range(40):
            d = (start + dt.timedelta(days=i)).strftime("%Y-%m-%d")
            close = 15 if d in ("2026-04-03", "2026-04-07") else 10
            mock_bars.append({"date": d, "close": close, "atr14": 0.5})

        with (
            patch.object(st, "HttpClient", return_value=mock_client),
            patch.object(st, "resolve_security", return_value=None),
            patch.object(st, "to_float", side_effect=lambda v: float(v) if v else 0.0),
            patch.object(st, "fetch_qfq_daily", return_value=mock_bars),
        ):
            result = st._compute_results_for_sig(sig)
            assert result is not None
            assert result.get("schema_version") == 1, \
                f"schema_version 应为整数 1，实际：{result.get('schema_version')}"
            assert isinstance(result.get("schema_version"), int), \
                f"schema_version 应为 int 类型，实际：{type(result.get('schema_version'))}"
