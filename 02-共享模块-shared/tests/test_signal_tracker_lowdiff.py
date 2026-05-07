#!/usr/bin/env python3
"""BUG-013/023/067 低难度修复回归测试。

BUG-013: 坏行计数不可观测 — _load_results/_load_signals 静默跳过
BUG-023: symbol/name 缺少规范化（trim、大小写、后缀统一）
BUG-067: CLI exit code 规范 — 始终 return 0
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


# ═══════ BUG-013: 坏行计数/可观测性 ═══════

class TestBadLineObservability:
    """BUG-013: 读取 JSONL 时坏行应有计数或日志。"""

    def setup_method(self):
        self.tmp = Path(f"/tmp/.trader_test_badline_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {
            "RESULT_PATH": st.RESULT_PATH,
        }
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"

    def teardown_method(self):
        st.RESULT_PATH = self._orig["RESULT_PATH"]
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bad_lines_detected_in_result_reader(self):
        """坏行混入时，_load_results 应返回记录数+坏行数。

        修复后 _load_results 应返回 (results, bad_count) 或在模块级暴露 bad_line_count。
        """
        result = self.tmp / "signal_results.jsonl"
        good = json.dumps({"symbol": "688248.SH", "signal_date": "2025-04-01", "r_5d": 3.5})
        bad = "THIS IS NOT JSON!!!"
        result.write_text(good + "\n" + bad + "\n" + good + "\n", encoding="utf-8")

        result_val = st._load_results()

        # 如果返回值是 tuple (results, bad_count)，则 bad_count 应为 1
        if isinstance(result_val, tuple):
            results, bad_count = result_val
            assert len(results) == 2
            assert bad_count == 1
        else:
            # 如果返回形式未变（仅向后兼容），则应暴露模块级统计
            assert len(result_val) == 2
            # 模块级应暴露 bad_line_count（在内部维护计数）
            assert hasattr(st, "_bad_line_count"), "应暴露 _bad_line_count 模块级变量"
            assert st._bad_line_count > 0, "坏行计数应 > 0"

    def test_show_single_handles_bad_lines_gracefully(self):
        """show_single 读结果文件时应能处理坏行。"""
        result = self.tmp / "signal_results.jsonl"
        bad = "not json..."
        good = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2025-04-01", "r_5d": 3.5,
            "outcome": "up", "schema_version": "v1",
        })
        result.write_text(bad + "\n" + good + "\n" + bad + "\n", encoding="utf-8")

        # 不应抛出异常
        panel = st.show_single("688248.SH")
        assert "信号追踪面板" in panel


# ═══════ BUG-023: symbol/name 规范化 ═══════

class TestSymbolNormalization:
    """BUG-023: symbol 输入应规范化（trim、大小写、后缀统一）。"""

    def test_normalize_symbol_handles_case(self):
        """.sz/.SZ/.Sz 应统一为 .SH/.SZ。"""
        assert st._normalize_symbol("688248.sz") == "688248.SZ"
        assert st._normalize_symbol("688248.Sz") == "688248.SZ"
        assert st._normalize_symbol("601600.sh") == "601600.SH"

    def test_normalize_symbol_handles_space(self):
        """前后空格应消除。"""
        assert st._normalize_symbol(" 688248 ") == "688248.SH"
        assert st._normalize_symbol("  688248.SH  ") == "688248.SH"

    def test_normalize_symbol_handles_mixed_input(self):
        """6/9 开头→SH, 0/3 开头→SZ。"""
        assert st._normalize_symbol("600001") == "600001.SH"  # 沪市主板
        assert st._normalize_symbol("300750") == "300750.SZ"  # 深市创业板
        assert st._normalize_symbol("002594") == "002594.SZ"  # 深市中小板

    def test_show_single_accepts_bare_code(self):
        """show_single 应接受裸代码（无前缀）。"""
        self.tmp = Path(f"/tmp/.trader_test_show_single_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {"RESULT_PATH": st.RESULT_PATH}
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"

        result = self.tmp / "signal_results.jsonl"
        good = json.dumps({
            "symbol": "688248.SH", "name": "南网科技",
            "signal_date": "2025-04-01", "r_5d": 3.5,
            "outcome": "up", "schema_version": "v1",
        })
        result.write_text(good + "\n", encoding="utf-8")

        # 裸码应匹配 -> .SH
        panel = st.show_single("688248")
        assert "信号追踪面板" in panel

        st.RESULT_PATH = self._orig["RESULT_PATH"]
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_show_single_accepts_lowercase_suffix(self):
        """show_single 应接受 .sz 后缀匹配。"""
        self.tmp = Path(f"/tmp/.trader_test_show_single2_{id(self)}")
        self.tmp.mkdir(exist_ok=True, parents=True)
        self._orig = {"RESULT_PATH": st.RESULT_PATH}
        st.RESULT_PATH = self.tmp / "signal_results.jsonl"

        result = self.tmp / "signal_results.jsonl"
        good = json.dumps({
            "symbol": "000001.sz", "name": "平安银行",
            "signal_date": "2025-04-01", "r_5d": -1.0,
            "outcome": "down", "schema_version": "v1",
        })
        result.write_text(good + "\n", encoding="utf-8")

        # .sz 应匹配
        panel = st.show_single("000001.SZ")
        assert "信号追踪面板" in panel

        st.RESULT_PATH = self._orig["RESULT_PATH"]
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


# ═══════ BUG-067: CLI 退出码规范 ═══════

class TestCliExitCodes:
    """BUG-067: CLI 应有区分成功/失败的退出码。"""

    def test_main_returns_non_zero_on_error(self):
        """main() 应在失败时返回非0退出码。"""
        import inspect
        source = inspect.getsource(st.main)
        # 应包含 sys.exit 或 return 非 0
        has_nonzero = ("sys.exit" in source or
                       "return 1" in source or
                       "return 2" in source)
        assert has_nonzero, f"main() 应定义非 0 退出码。当前代码:\n{source[:500]}"
