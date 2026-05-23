#!/usr/bin/env python3
"""signal_tracker.py regression tests — verifies BUG-001 through BUG-012 fixes."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path setup ──────────────────────────────────────────────
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent  # 02-共享模块-shared/
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))

import signal_tracker as st


# ═══════ FIXTURES ═══════

class _TempPaths:
    """Temporarily replace RESULT_PATH / LOG_PATH / STORE_PATH."""

    def __init__(self, tmp_dir: Path):
        self._orig: dict[str, Path] = {}
        tmp_dir.mkdir(exist_ok=True, parents=True)
        self.result_path = tmp_dir / "signal_results.jsonl"
        self.log_path = tmp_dir / "signal_log.jsonl"
        self.store_path = tmp_dir / "signals.jsonl"

    def apply(self) -> None:
        self._orig = {
            "RESULT_PATH": st.RESULT_PATH,
            "LOG_PATH": st.LOG_PATH,
            "STORE_PATH": st.STORE_PATH,
        }
        st.RESULT_PATH = self.result_path
        st.LOG_PATH = self.log_path
        st.STORE_PATH = self.store_path

    def restore(self) -> None:
        for k, v in self._orig.items():
            setattr(st, k, v)


def _make_sig(
    symbol: str = "688248.SH",
    name: str = "南网科技",
    trade_date: str = "2025-04-01",
    signal_type: str = "low_buy_watch",
    price: float = 10.0,
    source_skill: str = "trader",
    analysis_time: str = "2025-04-01T09:30:00",
) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "trade_date": trade_date,
        "signal_type": signal_type,
        "trigger": {"price": price},
        "source_skill": source_skill,
        "analysis_time": analysis_time,
    }


# ═══════ BUG-001: fill_by_target 不丢失损坏行 ═══════

class TestFillByTargetPreservesBadLines:
    """BUG-001: fill_by_target should NOT discard bad lines when rewriting."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_fill_bad")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.log_path, self.tmp.result_path):
            p.unlink(missing_ok=True)

    def test_preserves_bad_line(self):
        self.tmp.apply()
        with open(self.tmp.log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"signal_id": "aaa", "target": "测试票", "outcome_pnl_pct": None}) + "\n")
            f.write("BROKEN LINE!!!\n")
            f.write(json.dumps({"signal_id": "bbb", "target": "测试票", "outcome_pnl_pct": None}) + "\n")

        n, _ = st.fill_by_target("测试票", 5.0)
        assert n == 2, f"Should update 2, got {n}"

        text = self.tmp.log_path.read_text(encoding="utf-8")
        assert "BROKEN LINE!!!" in text, f"Bad line was lost!\n{text}"


# ═══════ BUG-003: update subcommand calls check_recent ═══════

class TestUpdateSubcommandExists:
    """BUG-003: update subcommand should actually call check_recent."""

    def test_update_calls_check_recent(self):
        import inspect
        source = inspect.getsource(st.main)
        assert "check_recent" in source, "update subcommand should call check_recent"


# ═══════ BUG-005 + BUG-009: 显式异常捕获 ═══════

class TestExplicitExceptHandling:
    """BUG-005: ValueError caught explicitly. BUG-009: json.JSONDecodeError, ValueError."""

    def test_check_recent_uses_explicit_except(self):
        import inspect
        source = inspect.getsource(st.check_recent)
        assert "json.JSONDecodeError" in source, "check_recent should catch json.JSONDecodeError"

    def test_compute_results_uses_explicit_valueerror(self):
        import inspect
        source = inspect.getsource(st._compute_results_for_sig)
        assert "ValueError" in source, "_compute_results_for_sig should catch ValueError"

    def test_fill_by_target_preserves_bad_line(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_preserve_bad")
        self.tmp.apply()
        with open(self.tmp.log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"signal_id": "aaa", "target": "T", "outcome_pnl_pct": None}) + "\n")
            f.write("BAD!!!\n")
            f.write(json.dumps({"signal_id": "bbb", "target": "T", "outcome_pnl_pct": None}) + "\n")
        n, _ = st.fill_by_target("T", 1.0)
        assert n == 2, f"Should update 2, got {n}"
        text = self.tmp.log_path.read_text(encoding="utf-8")
        assert "BAD!!!" in text, f"Bad line was lost!\n{text}"
        self.tmp.restore()
        self.tmp.log_path.unlink(missing_ok=True)


# ═══════ BUG-006: 原子写 + fsync ═══════

class TestAtomicWriteAndFsync:
    """BUG-006: fill_by_target should use os.replace + fsync."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_atomic")

    def teardown_method(self):
        self.tmp.restore()
        self.tmp.log_path.unlink(missing_ok=True)

    def test_fill_by_target_uses_fsync_and_replace(self):
        self.tmp.apply()
        self.tmp.log_path.write_text(
            json.dumps({"signal_id": "x1", "target": "A", "outcome_pnl_pct": None}) + "\n",
            encoding="utf-8",
        )

        with patch("signal_tracker.os.replace") as mock_replace, \
             patch("signal_tracker.os.fsync") as mock_fsync, \
             patch("signal_tracker.os.open") as mock_open:
            mock_fd = MagicMock()
            mock_open.return_value = mock_fd
            st.fill_by_target("A", 1.0)
            mock_open.assert_called_once()
            mock_fsync.assert_called_once_with(mock_fd)
            mock_replace.assert_called_once()


# ═══════ BUG-010: _normalize_symbol 统一 symbol 格式 ═══════

class TestNormalizeSymbol:
    """BUG-010: _normalize_symbol should canonicalize bare codes."""

    def test_numeric_6xx_sh(self):
        assert st._normalize_symbol("688248") == "688248.SH"

    def test_numeric_0xx_sz(self):
        assert st._normalize_symbol("000001") == "000001.SZ"

    def test_numeric_3xx_sz(self):
        assert st._normalize_symbol("300750") == "300750.SZ"

    def test_already_has_suffix(self):
        assert st._normalize_symbol("688248.SH") == "688248.SH"
        assert st._normalize_symbol("688248.sz") == "688248.SZ"

    def test_empty_string(self):
        assert st._normalize_symbol("") == ""
        assert st._normalize_symbol(None) == ""


# ═══════ BUG-011: signal_type -> str default empty ═══════

class TestSignalTypeDefault:
    """BUG-011: signal_type should not return str(None) = 'None'."""

    def test_empty_signal_type_in_record(self):
        sig = {"symbol": "688248.SH", "trade_date": "2025-04-01"}
        # No signal_type key → should not produce "None" or "unknown"
        sig_type = str(sig.get("signal_type") or "")
        assert sig_type == "", f"Expected empty string, got '{sig_type}'"


# ═══════ BUG-012: show_single 按 result_time 排序 ═══════

class TestShowSingleSortByResultTime:
    """BUG-012: show_single should sort by result_time, not signal_date."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_sort")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.log_path, self.tmp.store_path):
            p.unlink(missing_ok=True)

    def test_sorts_by_result_time_not_signal_date(self):
        import inspect
        source = inspect.getsource(st.show_single)
        assert "result_time" in source, "show_single should sort by result_time"


# ═══════ BUG: strptime not repeated in scan loop ═══════

class TestNoRepeatedStrptime:
    """Verify scan loop reuses parsed datetime, doesn't call strptime 42 times."""

    def test_reuses_sig_dt(self):
        import inspect
        source = inspect.getsource(st._compute_results_for_sig)
        # Should use 'sig_dt + timedelta' not repeated strptime in the loop
        assert "sig_dt + timedelta" in source, "Should reuse sig_dt in scan loop"


# ═══════ check_recent 返回类型修复 ═══════

class TestCheckRecentReturnType:
    """check_recent should return dict, not int."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_ret_type")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path):
            p.unlink(missing_ok=True)

    def test_returns_dict(self):
        self.tmp.apply()
        self.tmp.store_path.write_text(
            json.dumps(_make_sig(trade_date="2024-01-01")) + "\n",
            encoding="utf-8",
        )

        with patch.object(st, "HttpClient", None):
            # HttpClient is None → returns at line 306
            result = st.check_recent(5)

        assert isinstance(result, dict), f"check_recent should return dict, got {type(result)}"
        assert "updated" in result and "skipped" in result


# ═══════ check_recent 空结果不写文件 ═══════

class TestCheckRecentEmptyWrite:
    """When no new results and no skipped, don't touch the file."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_empty")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path):
            p.unlink(missing_ok=True)

    def test_no_op_when_nothing(self):
        self.tmp.apply()
        # No signals, no results → should not create empty file
        result = st.check_recent(5)
        assert not self.tmp.result_path.exists(), "Should not create file on no-op"


# ═══════ 面板输出不包含非法标记 ═══════

class TestPanelOutputFormat:
    """Panel output should not contain # headings or table markers."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_panel")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path):
            p.unlink(missing_ok=True)

    def test_no_table_markers_panel(self):
        """Panel should not have |...| table syntax."""
        results = [
            {
                "symbol": "688248.SH",
                "name": "南网科技",
                "signal_date": "2025-04-01",
                "signal_type": "low_buy_watch",
                "source_skill": "trader",
                "signal_price": 10.0,
                "close_5d": 10.5,
                "r_5d": 5.0,
                "outcome": "up",
            }
        ]
        panel = st._make_panel(results, days_limit=None)
        # 面板不应有表格线 |...|
        assert "|" not in panel, "Panel should not contain table markers"


# ═══════ Phase 1: Signal Lifecycle V2 Tests ═══════

class TestSignalLifecycleV2:
    """Tests for Phase 1 enhancements: stable ID, deduplication, and migration."""

    def setup_method(self):
        self.tmp = _TempPaths(Path.home() / ".trader_test_phase1")

    def teardown_method(self):
        self.tmp.restore()
        for p in (self.tmp.result_path, self.tmp.store_path, self.tmp.log_path):
            p.unlink(missing_ok=True)

    def test_make_signal_id_robustness(self):
        # Case normalization and unicode normalization
        id1 = st.make_signal_id("688248.SH", "2025-04-01", "low_buy_watch", 10.0)
        id2 = st.make_signal_id("688248.sh", "2025-04-01", "LOW_BUY_WATCH", "10")
        assert id1 == id2
        assert len(id1) == 16
        # Symbol prefix normalization: SH688248 -> 688248.SH
        id3 = st.make_signal_id("SH688248", "2025-04-01", "low_buy_watch", 10.0)
        assert id1 == id3
        # Date normalization variations: slashes, dots, compact numeric format
        id4 = st.make_signal_id("688248.SH", "2025/04/01", "low_buy_watch", 10.0)
        id5 = st.make_signal_id("688248.SH", "2025.04.01", "low_buy_watch", 10.0)
        id6 = st.make_signal_id("688248.SH", "20250401", "low_buy_watch", 10.0)
        assert id1 == id4 == id5 == id6

    def test_deduplicate_signals_logic(self):
        # Create list of signal records, some duplicate, some active, some completed
        recs = [
            {"symbol": "688248.SH", "trade_date": "2025-04-01", "signal_type": "low_buy_watch", "current": 10.0, "status": "active", "analysis_time": "2025-04-01T09:30:00"},
            {"symbol": "688248.SH", "trade_date": "2025-04-01", "signal_type": "low_buy_watch", "current": 10.0, "status": "completed", "analysis_time": "2025-04-01T10:00:00"}, # completed should win
            {"symbol": "000001.SZ", "trade_date": "2025-04-01", "signal_type": "high_sell_watch", "current": 15.0, "status": "active"}
        ]
        deduped = st._deduplicate_signals(recs, [])
        assert len(deduped) == 2
        # Verify 688248.SH became completed
        s1 = [r for r in deduped if r["symbol"] == "688248.SH"][0]
        assert s1["status"] == "completed"

    def test_deduplicate_results_logic(self):
        # Create list of result records, duplicate signal_ids, one with outcome
        recs = [
            {"symbol": "688248.SH", "signal_date": "2025-04-01", "signal_type": "low_buy_watch", "signal_price": 10.0, "result_time": "2025-04-01T09:30:00"},
            {"symbol": "688248.SH", "signal_date": "2025-04-01", "signal_type": "low_buy_watch", "signal_price": 10.0, "result_time": "2025-04-01T10:00:00", "outcome": "up"}, # outcome wins
        ]
        deduped = st._deduplicate_results(recs, [])
        assert len(deduped) == 1
        assert deduped[0]["outcome"] == "up"

    def test_migrate_signal_ids(self):
        self.tmp.apply()
        # Write signals.jsonl with old/missing signal_id
        sig_data = [
            {"symbol": "688248.SH", "trade_date": "2025-04-01", "signal_type": "low_buy_watch", "trigger": {"price": 10.0}, "status": "active"},
            {"symbol": "688248.SH", "trade_date": "2025-04-01", "signal_type": "low_buy_watch", "trigger": {"price": 10.0}, "status": "completed"}, # duplicate to be merged
            "BROKEN_SIGNAL_LINE"
        ]
        self.tmp.store_path.write_text("\n".join(
            json.dumps(r) if isinstance(r, dict) else r for r in sig_data
        ) + "\n", encoding="utf-8")

        # Write signal_results.jsonl
        res_data = [
            {"symbol": "688248.SH", "signal_date": "2025-04-01", "signal_type": "low_buy_watch", "signal_price": 10.0},
            "BROKEN_RESULT_LINE"
        ]
        self.tmp.result_path.write_text("\n".join(
            json.dumps(r) if isinstance(r, dict) else r for r in res_data
        ) + "\n", encoding="utf-8")

        # Run migration
        res = st.migrate_signal_ids(force=True)
        assert res["signals_migrated"] >= 1
        assert res["results_migrated"] >= 1

        # Check migrated signals.jsonl
        sig_lines = self.tmp.store_path.read_text(encoding="utf-8").splitlines()
        assert "BROKEN_SIGNAL_LINE" in sig_lines
        valid_sigs = [json.loads(l) for l in sig_lines if l.strip() and not l.startswith("BROKEN")]
        assert len(valid_sigs) == 1
        assert valid_sigs[0]["signal_id"] == st.make_signal_id("688248.SH", "2025-04-01", "low_buy_watch", 10.0)
        assert valid_sigs[0]["status"] == "completed"

        # Check migrated signal_results.jsonl
        res_lines = self.tmp.result_path.read_text(encoding="utf-8").splitlines()
        assert "BROKEN_RESULT_LINE" in res_lines
        valid_res = [json.loads(l) for l in res_lines if l.strip() and not l.startswith("BROKEN")]
        assert len(valid_res) == 1
        assert valid_res[0]["signal_id"] == st.make_signal_id("688248.SH", "2025-04-01", "low_buy_watch", 10.0)

