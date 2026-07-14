#!/usr/bin/env python3
"""Capture the PRE-SPLIT wyckoff behavior baseline for the equivalence gate.

Loads the ORIGINAL wyckoff_core.py (from .bak) under the shared offline
deterministic seam (mock_seam.apply_seam), runs wyckoff_analysis +
calculate_wyckoff_score on deterministic bars, and writes a canonical JSON
fixture (tests/fixtures/wyckoff_split_baseline.json).

The committed fixture is the ground truth; tests/test_wyckoff_split_equivalence.py
asserts the SPLIT (new) module produces an identical result. This proves the
events/phase split is behavior-preserving.

Run AFTER the split lands, re-run ONLY to refresh the baseline when an
intentional behavior change is made.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SHARED = _REPO / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import (
    apply_seam, _Patcher, gen_bars, dumps_fields,
)

_BAK = _SHARED / "trader_shared" / "wyckoff_core.py.bak"
_FIXTURE = _SHARED / "tests" / "fixtures" / "wyckoff_split_baseline.json"

SYMBOL = "SPLITTEST"
BARS = gen_bars(120, 9.0, 0.05)  # > WYCKOFF_MIN_BARS; deterministic


def _load_original():
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("wyckoff_core_orig", str(_BAK))
    spec = importlib.util.spec_from_loader("wyckoff_core_orig", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wyckoff_core_orig"] = mod
    loader.exec_module(mod)
    return mod


def main() -> None:
    if not _BAK.exists():
        sys.exit(f"❌ original backup missing: {_BAK} (run before deleting .bak)")
    patcher = _Patcher()
    apply_seam(patcher)

    orig = _load_original()
    # kill phase disk persistence for offline determinism
    orig._save_phase_state = lambda *a, **k: None
    orig._load_phase_state = lambda *a, **k: None

    result = {
        "wyckoff_analysis": orig.wyckoff_analysis(BARS, symbol=SYMBOL),
        "calculate_wyckoff_score": orig.calculate_wyckoff_score(BARS, symbol=SYMBOL),
    }
    patcher.undo()

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(dumps_fields(result), encoding="utf-8")
    print("✅ wyckoff split baseline ->", _FIXTURE,
          f"({len(dumps_fields(result))} bytes)")


if __name__ == "__main__":
    main()
