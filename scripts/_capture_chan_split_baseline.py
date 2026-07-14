#!/usr/bin/env python3
"""Capture PRE-SPLIT chan behavior baseline for the equivalence gate.

Loads ORIGINAL chan_core.py (.bak) under the shared offline deterministic seam,
runs chanlun_analysis + ChanlunEngine.get_analysis on deterministic bars, writes
canonical JSON fixture (tests/fixtures/chan_split_baseline.json). The committed
fixture is ground truth; tests/test_chan_split_equivalence.py asserts the SPLIT
(new) module matches it.
"""
from __future__ import annotations

import importlib.machinery
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

_BAK = _SHARED / "trader_shared" / "chan_core.py.bak"
_FIXTURE = _SHARED / "tests" / "fixtures" / "chan_split_baseline.json"

SYMBOL = "SPLITTEST"
BARS = gen_bars(120, 9.0, 0.05)


def _load_original():
    loader = importlib.machinery.SourceFileLoader("chan_core_orig", str(_BAK))
    spec = importlib.util.spec_from_loader("chan_core_orig", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chan_core_orig"] = mod
    loader.exec_module(mod)
    return mod


def main() -> None:
    if not _BAK.exists():
        sys.exit(f"❌ original backup missing: {_BAK}")
    patcher = _Patcher()
    apply_seam(patcher)
    orig = _load_original()

    current = BARS[-1]["close"]
    result = {
        "chanlun_analysis": orig.chanlun_analysis(BARS, current=current, symbol=SYMBOL),
        "chanlun_engine": orig.ChanlunEngine(BARS).get_analysis(current=current, symbol=SYMBOL),
    }
    patcher.undo()

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(dumps_fields(result), encoding="utf-8")
    print("✅ chan split baseline ->", _FIXTURE, f"({len(dumps_fields(result))} bytes)")


if __name__ == "__main__":
    main()
