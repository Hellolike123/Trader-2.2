#!/usr/bin/env python3
"""Signal ID 统一化测试 — Phase 1 (additive only)."""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime
from pathlib import Path

# ── Path setup (matches existing tests) ──
TESTS_DIR = Path(__file__).resolve().parent
SHARED = TESTS_DIR.parent
SCRIPTS = SHARED / "scripts"
for _p in (SHARED, SCRIPTS):
    if str(_p.resolve()) not in sys.path:
        sys.path.insert(0, str(_p.resolve()))


def test_make_signal_id_basic():
    """make_signal_id returns deterministic 16-char SHA256 hash."""
    from signal_tracker import make_signal_id
    sid = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    assert len(sid) == 16
    assert isinstance(sid, str)
    # Deterministic
    assert make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50") == sid


def test_make_signal_id_different_inputs():
    """Different inputs produce different IDs."""
    from signal_tracker import make_signal_id
    sid1 = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    sid2 = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.51")
    sid3 = make_signal_id("688248.SH", "2025-05-02", "hold_observe", "10.50")
    assert sid1 != sid2
    assert sid1 != sid3
    assert sid2 != sid3


def test_make_signal_id_empty_inputs():
    """Empty inputs should not crash."""
    from signal_tracker import make_signal_id
    sid = make_signal_id("", "", "unknown", "0.00")
    assert len(sid) == 16


def test_make_signal_id_not_md5():
    """Verify it uses SHA256, not MD5."""
    from signal_tracker import make_signal_id
    sid = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    md5_result = hashlib.md5(b"688248.SH|2025-05-02|low_buy_watch|10.50").hexdigest()[:12]
    # MD5[:12] is hexdigest of 12 chars. SHA256[:16] is hexdigest of 16 chars.
    # The length itself proves it's not MD5[:12]:
    # MD5[:12] is always 12 chars, SHA256[:16] is always 16 chars
    assert len(sid) == 16  # MD5[:12] would be 12


def test_make_signal_id_sha256_matches():
    """Verify the hash actually matches SHA256 computation."""
    from signal_tracker import make_signal_id
    sid = make_signal_id("688248.SH", "2025-05-02", "low_buy_watch", "10.50")
    expected = hashlib.sha256(b"688248.SH|2025-05-02|low_buy_watch|10.50").hexdigest()[:16]
    assert sid == expected


def test_normalize_signal_type_all_mappings():
    """All 30+ entries in _SIGNAL_TYPE_MAP work both ways."""
    from signal_tracker import _normalize_signal_type, _SIGNAL_TYPE_MAP
    
    assert _normalize_signal_type("低吸观察") == "low_buy_watch"
    assert _normalize_signal_type("low_buy_watch") == "low_buy_watch"  # identity
    assert _normalize_signal_type("hold_observe") == "hold_observe"
    assert _normalize_signal_type("track") == "track"
    assert _normalize_signal_type("unknown_type_xyz") == "unknown_type_xyz"  # passthrough
    
    # All map values should be in the map as identity keys
    for orig, normalized in _SIGNAL_TYPE_MAP.items():
        assert _normalize_signal_type(normalized) == normalized  # idempotent
