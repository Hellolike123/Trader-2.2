#!/usr/bin/env python3
"""Pool reuses trader's run_analysis.py for build_report + render_markdown."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

def _candidate_trader_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    dirs: list[Path] = []

    # Hermes-style flat install: ~/.hermes/skills/<skill>/scripts
    hermes_trader = here.parents[2] / "trader" / "scripts"
    dirs.append(hermes_trader)

    # Repo-style layout: <repo>/01-功能包-packages/01-单票分析-trader/scripts
    repo_root = here.parents[3]
    repo_trader = repo_root / "01-功能包-packages" / "01-单票分析-trader" / "scripts"
    dirs.append(repo_trader)

    # Zip extracted with retained top folder: <root>/01-功能包-packages/...
    nested_root = here.parents[2]
    nested_trader = nested_root / "01-功能包-packages" / "01-单票分析-trader" / "scripts"
    dirs.append(nested_trader)

    return dirs


TRADER_DIR = next((p for p in _candidate_trader_dirs() if p.exists()), None)
if TRADER_DIR is None:
    raise RuntimeError("Cannot locate trader/scripts for trader-pool run_analysis")

if str(TRADER_DIR) not in sys.path:
    sys.path.insert(0, str(TRADER_DIR))

_trader_path = str(TRADER_DIR / "run_analysis.py")
_trader_spec = importlib.util.spec_from_file_location("_trader_ra", _trader_path)
if _trader_spec is None or _trader_spec.loader is None:
    raise RuntimeError(f"Failed to load trader run_analysis from: {_trader_path}")
_trader_ra = importlib.util.module_from_spec(_trader_spec)
_trader_spec.loader.exec_module(_trader_ra)

build_report = _trader_ra.build_report
render_markdown = _trader_ra.render_markdown
