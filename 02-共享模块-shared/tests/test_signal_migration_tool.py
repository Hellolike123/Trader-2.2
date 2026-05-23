#!/usr/bin/env python3
"""Tests for migrate_signal_ids() one-time migration tool."""
from __future__ import annotations

import json
import sys
from pathlib import Path

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


# ═══════ TESTS ═══════


def test_normalize_symbol():
    """_normalize_symbol strips / uppercases / adds exchange suffix."""
    assert st._normalize_symbol("688248") == "688248.SH"
    assert st._normalize_symbol("688248.SH") == "688248.SH"
    assert st._normalize_symbol("000001") == "000001.SZ"
    assert st._normalize_symbol("") == ""


def test_normalize_signal_type():
    """_normalize_signal_type maps Chinese/old names to v1 standard."""
    assert st._normalize_signal_type("低吸观察") == "low_buy_watch"
    assert st._normalize_signal_type("low_buy_watch") == "low_buy_watch"
    assert st._normalize_signal_type("low_buy") == "low_buy_watch"
    assert st._normalize_signal_type("review_result") == "review_result"
    assert st._normalize_signal_type("track") == "track"


def test_norm_date():
    """_norm_date normalizes various date formats to YYYY-MM-DD."""
    assert st._norm_date("2025-5-2") == "2025-05-02"
    assert st._norm_date("2025-04-1") == "2025-04-01"
    assert st._norm_date("2025-05-02") == "2025-05-02"


def test_build_signal_id_inputs_from_signal():
    """_build_signal_id_inputs extracts normalized fields from a signal record."""
    old_signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "低吸观察",  # Chinese old name
        "trigger": {"price": 10.5, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "data_status": "full",
    }

    inputs = st._build_signal_id_inputs(old_signal)
    assert inputs[0] == "688248.SH"  # symbol normalized
    assert inputs[1] == "2025-05-02"  # date normalized
    assert inputs[2] == "low_buy_watch"  # type normalized (Chinese -> English)
    assert inputs[3] == "10.50"  # price formatted


def test_build_signal_id_inputs_from_result():
    """_build_signal_id_inputs extracts normalized fields from a result record."""
    old_result = {
        "symbol": "688248.SH",
        "signal_date": "2025-4-1",  # Non-zero-padded
        "signal_type": "low_buy_watch",
        "signal_price": 10.50,
    }

    inputs = st._build_signal_id_inputs(old_result)
    assert inputs[0] == "688248.SH"
    assert inputs[1] == "2025-04-01"  # _norm_date fixed the date
    assert inputs[2] == "low_buy_watch"
    assert inputs[3] == "10.50"


def test_build_signal_id_inputs_price_fallback_to_current():
    """When no trigger.price, falls back to 'current' field."""
    record = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "signal_type": "track",
        "current": 11.25,
    }

    inputs = st._build_signal_id_inputs(record)
    assert inputs[3] == "11.25"  # From current field


def test_build_signal_id_inputs_no_price():
    """When no trigger.price, no current, no signal_price, use '0.00'."""
    record = {
        "symbol": "600519.SH",
        "signal_date": "2025-05-02",
        "signal_type": "review_result",
        # No price field at all
    }

    inputs = st._build_signal_id_inputs(record)
    assert inputs[3] == "0.00"


def test_migrate_file_single_record(tmp_path):
    """_migrate_file adds signal_id to records that don't have one."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    old_signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "name": "南网科技",
        "data_status": "full",
        "trigger": {"price": 10.5, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "risk_flags": [],
        "summary": "test",
    }
    tp.store_path.write_text(json.dumps(old_signal, ensure_ascii=False) + "\n", encoding="utf-8")

    result = st._migrate_file(tp.store_path, is_signal=True)

    assert result["migrated"] == 1
    assert result["skipped"] == 0

    # Read and verify signal_id was added
    lines = tp.store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16

    tp.restore()


def test_migrate_file_idempotent(tmp_path):
    """Running _migrate_file twice: second run should skip all records."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    old_signal = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "low_buy_watch",
        "direction": "bullish",
        "action": "observe",
        "confidence": "medium",
        "trigger": {"price": 10.5, "type": "price_confirm", "text": ""},
        "invalidation": {"price": 10.0, "type": "price_break", "text": ""},
        "position": {"max_total_pct": 30, "max_single_move_pct": 10},
        "data_status": "full",
    }
    tp.store_path.write_text(json.dumps(old_signal, ensure_ascii=False) + "\n", encoding="utf-8")

    result1 = st._migrate_file(tp.store_path, is_signal=True)
    assert result1["migrated"] == 1
    assert result1["skipped"] == 0

    # Now run again — should be idempotent
    result2 = st._migrate_file(tp.store_path, is_signal=True)
    assert result2["migrated"] == 0  # Nothing new to migrate
    assert result2["skipped"] == 1  # All skipped (already have signal_id)

    tp.restore()


def test_migrate_file_bad_line_survival(tmp_path):
    """Files with JSONDecodeError lines survive without data loss."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    # Mixed valid and invalid lines
    lines = [
        json.dumps({"symbol": "688248.SH", "signal_type": "track"}) + "\n",  # valid
        "NOT VALID JSON\n",  # bad line
        json.dumps({"symbol": "600519.SH", "signal_type": "hold_observe"}) + "\n",  # valid
    ]
    tp.store_path.write_text("".join(lines), encoding="utf-8")

    result = st._migrate_file(tp.store_path, is_signal=True)

    assert result["migrated"] == 2  # 2 valid records migrated
    assert result["skipped"] == 0

    # Bad line should survive unchanged
    output = tp.store_path.read_text(encoding="utf-8")
    assert "NOT VALID JSON" in output  # Bad line preserved

    tp.restore()


def test_migrate_file_empty_file(tmp_path):
    """_migrate_file on an empty file returns zero counts."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    tp.store_path.write_text("", encoding="utf-8")

    result = st._migrate_file(tp.store_path, is_signal=True)
    assert result["migrated"] == 0
    assert result["skipped"] == 0

    tp.restore()


def test_migrate_file_nonexistent(tmp_path):
    """_migrate_file on a nonexistent file returns zero counts."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    result = st._migrate_file(tp.store_path, is_signal=True)
    assert result["migrated"] == 0
    assert result["skipped"] == 0

    tp.restore()


def test_migrate_file_already_has_signal_id(tmp_path):
    """Records that already have signal_id are skipped by _migrate_file."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    record = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "track",
        "signal_id": "existing123456789012",  # already has one
        "trigger": {"price": 10.5},
    }
    tp.store_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    result = st._migrate_file(tp.store_path, is_signal=True)
    assert result["migrated"] == 0
    assert result["skipped"] == 1

    # signal_id should remain unchanged
    lines = tp.store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert written["signal_id"] == "existing123456789012"

    tp.restore()


def test_migrate_file_results_jsonl(tmp_path):
    """_migrate_file works on results JSONL too."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    old_record = {
        "symbol": "688248.SH",
        "signal_date": "2025-4-1",
        "signal_type": "low_buy_watch",
        "signal_price": 10.50,
        "outcome": "win",
    }
    tp.result_path.write_text(json.dumps(old_record, ensure_ascii=False) + "\n", encoding="utf-8")

    result = st._migrate_file(tp.result_path, is_signal=False)
    assert result["migrated"] == 1
    assert result["skipped"] == 0

    lines = tp.result_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16

    tp.restore()


def test_migrate_signal_ids_integration(tmp_path):
    """migrate_signal_ids() processes both files and returns aggregate counts."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    # Write signals
    sig = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "低吸观察",
        "trigger": {"price": 10.5},
        "data_status": "full",
    }
    tp.store_path.write_text(json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8")

    # Write results
    res = {
        "symbol": "600519.SH",
        "signal_date": "2025-04-01",
        "signal_type": "review_result",
        "signal_price": 1750.0,
    }
    tp.result_path.write_text(json.dumps(res, ensure_ascii=False) + "\n", encoding="utf-8")

    result = st.migrate_signal_ids(tp.store_path, tp.result_path)

    assert result["signals_migrated"] == 1
    assert result["results_migrated"] == 1
    assert result["signals_skipped"] == 0
    assert result["results_skipped"] == 0

    # Verify both files got signal_ids
    sig_line = json.loads(tp.store_path.read_text(encoding="utf-8").strip())
    res_line = json.loads(tp.result_path.read_text(encoding="utf-8").strip())
    assert len(sig_line["signal_id"]) == 16
    assert len(res_line["signal_id"]) == 16

    tp.restore()


def test_migrate_signal_ids_idempotent(tmp_path):
    """migrate_signal_ids() is idempotent — second call skips all."""
    tp = _TempPaths(tmp_path)
    tp.apply()

    sig = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "track",
        "trigger": {"price": 10.5},
        "data_status": "full",
    }
    tp.store_path.write_text(json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8")
    tp.result_path.write_text("", encoding="utf-8")

    st.migrate_signal_ids(tp.store_path, tp.result_path)

    # Second call — all skipped
    result = st.migrate_signal_ids(tp.store_path, tp.result_path)
    assert result["signals_migrated"] == 0
    assert result["signals_skipped"] == 1
    assert result["results_migrated"] == 0
    assert result["results_skipped"] == 0

    tp.restore()


def test_make_signal_id_deterministic():
    """make_signal_id is deterministic: same inputs always produce same ID."""
    id1 = st.make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    id2 = st.make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    assert id1 == id2
    assert len(id1) == 16


def test_make_signal_id_different_inputs():
    """Different inputs produce different IDs."""
    ids = set()
    ids.add(st.make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50"))
    ids.add(st.make_signal_id("600519.SH", "2025-05-02", "low_buy_watch", "10.50"))
    ids.add(st.make_signal_id("688248.SH", "2025-05-03", "low_buy_watch", "10.50"))
    ids.add(st.make_signal_id("688248.SH", "2025-05-02", "high_sell_watch", "10.50"))
    ids.add(st.make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "11.00"))
    assert len(ids) == 5


def test_migration_tool_cli_entrypoint(tmp_path):
    """Verify that signal_migration_tool's main() can run successfully with custom paths."""
    import signal_migration_tool
    
    tp = _TempPaths(tmp_path)
    tp.apply()
    
    # Write a signal record that needs migration
    sig = {
        "symbol": "688248.SH",
        "trade_date": "2025-05-02",
        "analysis_time": "2025-05-02 10:00",
        "signal_type": "track",
        "trigger": {"price": 10.5},
        "data_status": "full",
    }
    tp.store_path.write_text(json.dumps(sig, ensure_ascii=False) + "\n", encoding="utf-8")
    tp.result_path.write_text("", encoding="utf-8")
    
    # Call main with custom arguments programmatically
    sys_argv_backup = sys.argv
    sys.argv = ["signal_migration_tool.py", "--signals", str(tp.store_path), "--results", str(tp.result_path)]
    try:
        exit_code = signal_migration_tool.main()
        assert exit_code == 0
    finally:
        sys.argv = sys_argv_backup
        tp.restore()
        
    # Verify migration did happen
    lines = tp.store_path.read_text(encoding="utf-8").strip().splitlines()
    written = json.loads(lines[0])
    assert "signal_id" in written
    assert len(written["signal_id"]) == 16

