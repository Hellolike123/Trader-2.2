#!/usr/bin/env python3
"""Capture PRE-SPLIT stage behavior baseline for the equivalence gate.

Loads ORIGINAL stage_positioning.py (.bak), runs check_time_stop on
deterministic inputs, writes fixture. The DETECT and POSITION partitions
are already verified by the full CI gate (build_report → assess_stage etc.).
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SHARED = _REPO / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import apply_seam, _Patcher, dumps_fields

_BAK = _SHARED / "trader_shared" / "stage_positioning.py.bak"
_FIXTURE = _SHARED / "tests" / "fixtures" / "stage_split_baseline.json"


def _load_original():
    loader = importlib.machinery.SourceFileLoader("stage_positioning_orig", str(_BAK))
    spec = importlib.util.spec_from_loader("stage_positioning_orig", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["stage_positioning_orig"] = mod
    loader.exec_module(mod)
    return mod


def main() -> None:
    if not _BAK.exists():
        sys.exit(f"❌ original backup missing: {_BAK}")
    patcher = _Patcher()
    apply_seam(patcher)
    orig = _load_original()
    orig._save_stage_state = lambda *a, **k: None
    orig._load_stage_state = lambda *a, **k: None

    result = {
        "check_time_stop": orig.check_time_stop(
            "2026-07-01", "蓄势", 20, False,
        ),
    }
    patcher.undo()

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(dumps_fields(result), encoding="utf-8")
    print("✅ stage split baseline ->", _FIXTURE, f"({len(dumps_fields(result))} bytes)")


if __name__ == "__main__":
    main()
