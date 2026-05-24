import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

# Ensure candidates directory and shared modules are in python path
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
SCRIPTS = SHARED / "scripts"
CONTRACTS = SHARED / "03-输出校验-contracts"

for p in (SHARED, SCRIPTS, CONTRACTS):
    if str(p.resolve()) not in sys.path:
        sys.path.insert(0, str(p.resolve()))

import signal_tracker as st

def test_consolidate_legacy_log_e2e():
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        log_path = tmp_path / "signal_log.jsonl"
        store_path = tmp_path / "signals.jsonl"
        
        # 1. Write legacy record
        legacy_rec = {
            "symbol": "688248.SH",
            "target": "南网科技",
            "timestamp": "2025-05-02 10:00",
            "signal_type": "低吸观察",
            "price": 55.90,
            "skill": "trader",
            "env_level": "正常",
            "env_note": "大盘环境温和"
        }
        log_path.write_text(json.dumps(legacy_rec, ensure_ascii=False) + "\n", encoding="utf-8")
        
        # 2. Consolidate
        result = st.consolidate_legacy_log(log_path=log_path, store_path=store_path)
        assert result["migrated"] == 1
        assert result["skipped"] == 0
        
        # 3. Verify standard signals.jsonl content
        assert store_path.exists()
        lines = store_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        sig = json.loads(lines[0])
        assert sig["contract"] == "trader_signal_v1"
        assert sig["symbol"] == "688248.SH"
        assert sig["name"] == "南网科技"
        assert sig["signal_type"] == "low_buy_watch"
        assert sig["trigger"]["price"] == 55.90
        assert sig["status"] == "active"
        
        # 4. Verify legacy file was backed up
        bak_path = log_path.with_name("signal_log.jsonl.bak")
        assert bak_path.exists()
        assert not log_path.exists()

def test_consolidate_legacy_log_merge_existing():
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        log_path = tmp_path / "signal_log.jsonl"
        store_path = tmp_path / "signals.jsonl"
        
        # 1. Pre-populate signals.jsonl with an active signal
        sig_id = st.make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", 55.90)
        existing = {
            "contract": "trader_signal_v1",
            "signal_id": sig_id,
            "symbol": "688248.SH",
            "name": "南网科技",
            "trade_date": "2025-05-02",
            "status": "active"
        }
        store_path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
        
        # 2. Write legacy record with outcome to merge
        legacy_rec = {
            "symbol": "688248.SH",
            "target": "南网科技",
            "timestamp": "2025-05-02 10:00",
            "signal_type": "低吸观察",
            "price": 55.90,
            "outcome": "win",
            "outcome_pnl_pct": 5.2,
            "outcome_days": 3,
            "filled_at": "2025-05-05 15:00"
        }
        log_path.write_text(json.dumps(legacy_rec) + "\n", encoding="utf-8")
        
        # 3. Consolidate
        result = st.consolidate_legacy_log(log_path=log_path, store_path=store_path)
        assert result["migrated"] == 1
        
        # 4. Verify fields merged and status updated to completed
        lines = store_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        sig = json.loads(lines[0])
        assert sig["status"] == "completed"
        assert sig["outcome"] == "win"
        assert sig["outcome_pnl_pct"] == 5.2
        assert sig["outcome_days"] == 3
