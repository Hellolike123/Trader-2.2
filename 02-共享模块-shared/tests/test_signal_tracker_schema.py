#!/usr/bin/env python3
"""BUG-014: 结果记录缺 schema_version 和兼容读取。

验收点：
- 新写记录带 schema_version
- 读旧记录（无版本）可兼容
- 混合新旧文件统计不报错
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

SHARED = Path(__file__).resolve().parent.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

import signal_tracker as st


class TestSchemaVersion:
    """BUG-014: schema_version 在结果记录中。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_schema_{id(self)}")
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

    def test_new_records_have_schema_version(self):
        """验证：_compute_results_for_sig 输出的记录包含 schema_version='v1'。"""
        from datetime import datetime as _dt, timedelta as _td
        sig = {
            "symbol": "688248.SH", "name": "南网科技",
            "trade_date": "2025-04-04",
            "signal_type": "low_buy_watch",
            "trigger": {"price": 10.0},
            "source_skill": "trader",
            "analysis_time": "2025-04-04T09:30:00",
        }

        bars = [
            {"date": "2025-04-03", "close": 9.8, "atr14": 0.3},
            {"date": "2025-04-04", "close": 10.0, "atr14": 0.3},
            {"date": "2025-04-05", "close": 10.1, "atr14": 0.3},
            {"date": "2025-04-06", "close": 10.2, "atr14": 0.3},
            {"date": "2025-04-07", "close": 10.5, "atr14": 0.3},
        ]

        with patch("signal_tracker.resolve_security") as mock_resolve, \
             patch.object(st, "HttpClient", MagicMock), \
             patch("signal_tracker.fetch_qfq_daily", return_value=bars), \
             patch.object(st, "to_float", return_value=0.3):
            mock_resolve.return_value = MagicMock(code="688248.SH", market="SH")
            result = st._compute_results_for_sig(sig)

        assert result is not None, f"Expected result record, got None"
        assert "schema_version" in result
        assert result["schema_version"] == 1


class TestSchemaVersionCompatibility:
    """验证：读取混合新旧格式文件时不报错。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_schema_compat_{id(self)}")
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

    def test_empty_string_schema_version_handled(self):
        """旧格式记录：没有 schema_version 字段，读取不应报错。"""
        result = self.tmp / "signal_results.jsonl"
        # 旧格式记录（无 schema_version）
        old_record = json.dumps({
            "symbol": "688248.SH",
            "signal_date": "2025-04-01",
            "r_5d": 3.5,
            "outcome": "up",
        })
        result.write_text(old_record + "\n", encoding="utf-8")

        # 不应抛出异常
        results = st._load_results()
        assert len(results) == 1
        assert results[0]["symbol"] == "688248.SH"

    def test_mixed_old_new_records(self):
        """混合新旧格式：应有记录无 schema_version 或有 schema_version='v1'。"""
        result = self.tmp / "signal_results.jsonl"
        old = json.dumps({
            "symbol": "688248.SH", "signal_date": "2025-04-01",
            "r_5d": 3.5, "outcome": "up",
        })
        new = json.dumps({
            "symbol": "601600.SH", "signal_date": "2025-04-02",
            "r_5d": -1.0, "outcome": "down",
            "schema_version": 1,
        })
        result.write_text(old + "\n" + new + "\n", encoding="utf-8")

        results = st._load_results()
        assert len(results) == 2

        # 验证新记录有 schema_version
        new_rec = [r for r in results if r["symbol"] == "601600.SH"]
        assert len(new_rec) == 1
        assert new_rec[0]["schema_version"] == 1

        # 验证旧记录仍可读取（无 schema_version 也不报错）
        old_rec = [r for r in results if r["symbol"] == "688248.SH"]
        assert len(old_rec) == 1

    def test_schema_version_field_value(self):
        """验证当前 schema_version 的值为 'v1'。"""
        import inspect
        source = inspect.getsource(st._compute_results_for_sig)
        assert '"schema_version": 1' in source or "'schema_version': 1" in source, \
            "_compute_results_for_sig 应写 schema_version=1"
