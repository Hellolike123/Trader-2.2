"""P1: tests for pipeline.py, market_env.py, signal_tracker.py"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import sys

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from pipeline import (
    write_stock, write_market, add_warning, conflicting_signals,
    get_stock_weight, get_full_market, clear_old_warnings,
    _load, _save,
)
import pipeline as pl


@pytest.fixture
def tmp_state(tmp_path):
    """Use a temp file for pipeline state."""
    old_path = pl.STATE_PATH
    old_dir = pl.STATE_DIR
    pl.STATE_PATH = tmp_path / "pipeline_state.json"
    pl.STATE_DIR = tmp_path
    yield pl.STATE_PATH
    pl.STATE_PATH = old_path
    pl.STATE_DIR = old_dir


# ── pipeline tests ──

def test_basic_stock_write(tmp_state):
    write_stock("测试", "低吸观察", 80, "trader")
    data = _load()
    assert "测试" in data["stocks"]
    assert data["stocks"]["测试"]["status"] == "低吸观察"
    assert data["stocks"]["测试"]["weight"] == 80


def test_schema_version(tmp_state):
    write_stock("X", "测试", 50, "t")
    data = _load()
    assert data.get("schema_version") == 1


def test_warning_dedup(tmp_state):
    add_warning("msg_a", "测试")
    add_warning("msg_a", "测试")
    add_warning("msg_a", "测试")
    data = _load()
    matching = [w for w in data["warnings"] if w.get("msg") == "msg_a"]
    assert len(matching) == 1, f"Expected 1 dedup, got {len(matching)}"


def test_warning_max_cap(tmp_state):
    for i in range(60):
        add_warning(f"cap_{i}", str(i))
    data = _load()
    assert len(data["warnings"]) <= 55, f"Cap failed: {len(data['warnings'])}"


def test_conflicting_signals_exact(tmp_state):
    add_warning("冲突A", "测试")
    conflicts = conflicting_signals("测试")
    assert "冲突A" in conflicts


def test_conflicting_signals_empty_stock(tmp_state):
    """Empty-stock (global) warnings must not leak into per-stock queries."""
    add_warning("全局警告", "")
    conflicts = conflicting_signals("测试")
    assert "全局警告" not in conflicts
    # Global warnings are still saved in the state (just not returned by conflicting_signals)


def test_get_full_market_unknown(tmp_state):
    market = get_full_market()
    assert market.get("level") == "未知"


def test_clear_old_warnings_no_op(tmp_state):
    write_market("正常", "测试")
    count = clear_old_warnings(days=7)
    assert count == 0


def test_atomic_write(tmp_state):
    write_stock("原子", "测试", 10, "atomic")
    assert pl.STATE_PATH.exists()
    data = json.loads(pl.STATE_PATH.read_text())
    assert "原子" in data["stocks"]


def test_market_write(tmp_state):
    write_market("正常", "测试笔记")
    data = _load()
    assert data["market"]["level"] == "正常"
    assert data["market"]["note"] == "测试笔记"

# ── signal_tracker tests ──
import signal_tracker as st


@pytest.fixture
def tmp_log(tmp_path):
    old_path = st.LOG_PATH
    old_dir = st.LOG_DIR
    st.LOG_PATH = tmp_path / "signal_log.jsonl"
    st.LOG_DIR = tmp_path
    yield st.LOG_PATH
    st.LOG_PATH = old_path
    st.LOG_DIR = old_dir


def test_stable_id(tmp_log):
    sid1 = st.stable_id("trader", "南网科技", "2026-05-04", "低吸观察")
    sid2 = st.stable_id("trader", "南网科技", "2026-05-04", "低吸观察")
    assert sid1 == sid2
    sid3 = st.stable_id("trader", "南网科技", "2026-05-05", "低吸观察")
    assert sid1 != sid3


def test_log_safe_dedup(tmp_log):
    """FIX-T-BIAS-168: different prices produce different signal_ids."""
    id1 = st.log_safe("trader", "测试票", "000001.SZ", "低吸观察", 50.0)
    id2 = st.log_safe("trader", "测试票", "000001.SZ", "低吸观察", 51.0)
    assert id1 != id2, "Same target, different prices → different signal_id"
    records = st._load_all()
    assert len(records) == 2
    # Same price → dedup
    id3 = st.log_safe("trader", "测试票", "000001.SZ", "低吸观察", 50.0)
    assert id3 == id1
    records = st._load_all()
    assert len(records) == 2  # no new record


def test_fill(tmp_log):
    sid = st.log_safe("trader", "S1", "000001.SZ", "低吸观察", 50.0)
    ok, _ = st.fill(sid, 3.5, 5, "win")
    assert ok
    records = st._load_all()
    assert records[0]["outcome_pnl_pct"] == 3.5
    assert records[0]["outcome"] == "win"


def test_fill_by_target(tmp_log):
    st.log_safe("review-trader", "X票", "000001.SZ", "observe", 10.0)
    st.log_safe("t0-trader", "X票", "000001.SZ", "low_buy_watch", 11.0)
    count, ids = st.fill_by_target("X票", 2.0, 3, "win")
    assert count == 2
    records = st._load_all()
    assert all(r["outcome"] == "win" for r in records)


def test_load_recent_filter(tmp_log):
    st.log_safe("trader", "A", "000001.SZ", "低吸观察", 10.0)
    st.log_safe("t0-trader", "B", "000002.SZ", "low_buy_watch", 20.0)
    assert len(st.load_recent(target="A")) == 1
    assert st.load_recent(target="A")[0]["skill"] == "trader"
    assert len(st.load_recent(skill="t0-trader")) == 1
    assert len(st.load_recent(symbol="000001.SZ")) == 1


# ── market_env import pipeline test ──

@pytest.fixture
def _inject_market_env_path():
    import market_env as me  # noqa: F401
    old_has = me._HAS_PIPELINE
    yield me._HAS_PIPELINE
    me._HAS_PIPELINE = old_has


def test_market_env_pipeline_import_available(tmp_state, _inject_market_env_path):
    import market_env as me
    pl.STATE_PATH = tmp_state
    pl.STATE_DIR = tmp_state.parent
    env = me.refresh(write_pipeline=True)
    assert env.get("level") in ("正常", "偏弱", "很差", "未知")
    data = pl._load()
    assert "market" in data


def test_market_env_assess_no_net():
    import market_env as me
    with patch.object(me, "_fetch_index_data", return_value={}):
        env = me.assess()
    assert env["level"] == "未知"
    assert env["data_status"] == "insufficient"


def test_market_env_note_for_all_skills():
    import market_env as me
    env = {"level": "正常", "note": "测试"}
    for skill in ("t0", "trader", "portfolio"):
        note = me.env_note_for(env, skill)
        assert isinstance(note, str)
        assert len(note) > 0


def test_calibrator_uses_shared_assess():
    import calibrator as cal
    assert hasattr(cal, "_assess_market")


def test_market_env_pipeline_write_via_tradershared():
    import trader_shared as ts
    me = ts.get_market_env()
    with patch.object(me, "write_market") as mock_write:
        me.refresh(write_pipeline=True)
        mock_write.assert_called_once()


def test_stable_id_deprecated():
    """stable_id() should emit deprecation warning."""
    import signal_tracker as st
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sid = st.stable_id("trader", "南网科技", "2026-05-04", "低吸观察")
        assert len(w) == 1, f"Expected 1 warning, got {len(w)}"
        assert "deprecated" in str(w[0].message).lower()
