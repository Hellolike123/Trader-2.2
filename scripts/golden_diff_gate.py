#!/usr/bin/env python3
"""Golden-diff gate: behavior-preserving regression harness for build_report.

Consolidates the three ad-hoc equivalence tests (build_report golden, ADR-002
routing, ADR-003b render split) into ONE reusable seam + a standalone CLI that
the pre-push gate and humans can both run.

Subcommands
-----------
  capture   Regenerate golden baselines (masked render md + exact field json)
            for every ticker in the config. Run ONLY after you have confirmed a
            behavioral change is intentional.
  check     Run build_report under the offline seam and diff against the
            committed golden. Exit code 1 on any mismatch. This is what the
            pre-push gate enforces.

Flags
-----
  --replicas PATH [PATH ...]
            Run the SAME capture against an alternate source tree (e.g. a stale
            skill install such as ~/.hermes/skills/trader) and diff its output
            against the primary golden. Directly catches the 07-08 class of bug
            where one of two skill install copies drifted out of sync.

  --config PATH     Default: 02-共享模块-shared/tests/golden/golden_config.json
  --golden-dir PATH Default: 02-共享模块-shared/tests/golden

Examples
--------
  python scripts/golden_diff_gate.py capture
  python scripts/golden_diff_gate.py check
  python scripts/golden_diff_gate.py check --replicas ~/.hermes/skills/trader
"""
from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED = _REPO_ROOT / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

GATE_SCRIPT = _REPO_ROOT / "scripts" / "golden_diff_gate.py"

from trader_shared.testing.mock_seam import (  # noqa: E402
    _Patcher,
    approx_equal,
    build_under_seam,
    extract_fields,
    render_under_seam,
)


DEFAULT_CONFIG = _SHARED / "tests" / "golden" / "golden_config.json"
DEFAULT_GOLDEN_DIR = _SHARED / "tests" / "golden"


def _print(*a, **k):
    print(*a, **k, flush=True)


# ── path / config helpers ──────────────────────────────────────────────────

def resolve_pythonpath(tree_root: Path) -> str | None:
    """Find a ``trader_shared`` package under *tree_root* and return a PYTHONPATH
    string (shared dir + optional trader pkg scripts) so the replica can import
    the same modules. Returns None if no package is found.
    """
    tree_root = Path(tree_root)
    candidates = []

    # Case A: tree_root looks like a repo / skill bundle with 02-共享模块-shared
    shared_a = tree_root / "02-共享模块-shared"
    if (shared_a / "trader_shared").is_dir():
        candidates.append(shared_a)

    # Case B: tree_root itself is the shared dir
    if (tree_root / "trader_shared").is_dir():
        candidates.append(tree_root)

    # Case C: search for a trader_shared dir up to depth 3
    for depth in (1, 2, 3):
        for hit in tree_root.rglob("trader_shared"):
            if hit.is_dir():
                candidates.append(hit.parent)
                break
        if candidates:
            break

    if not candidates:
        return None

    shared = candidates[0]
    parts = [str(shared)]
    pkg_scripts = shared.parent / "01-功能包-packages" / "trader" / "scripts"
    if pkg_scripts.is_dir():
        parts.append(str(pkg_scripts))
    return os.pathsep.join(parts)


def load_config(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    # Accept .json directly; for .yaml/.yml fall back to json if unavailable.
    if str(path).endswith((".yaml", ".yml")):
        try:
            import yaml
            return yaml.safe_load(text)
        except ImportError:
            pass
    return json.loads(text)


# ── capture / check core ────────────────────────────────────────────────────

def capture_ticker(ticker: dict) -> tuple[str | None, str | None]:
    """Return (render_md_masked, fields_json) for one ticker under the seam."""
    patcher = _Patcher()
    try:
        symbol = ticker["symbol"]
        render_md = None
        fields_json = None
        if ticker.get("render", True):
            render_md = render_under_seam(patcher, symbol)
        if ticker.get("fields"):
            report = build_under_seam(patcher, symbol)
            fields = extract_fields(report, ticker["fields"])
            fields_json = json.dumps(fields, ensure_ascii=False, indent=2, default=_json_default)
    finally:
        patcher.undo()
    return render_md, fields_json


def _json_default(o):
    if isinstance(o, bool):
        return o
    if isinstance(o, int):
        return int(o)
    if isinstance(o, float):
        return float(o)
    try:
        import numpy as _np
        if isinstance(o, _np.floating):
            return float(o)
        if isinstance(o, _np.integer):
            return int(o)
        if isinstance(o, _np.ndarray):
            return o.tolist()
    except Exception:
        pass
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def cmd_capture(config: dict, golden_dir: Path) -> int:
    golden_dir = Path(golden_dir)
    golden_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for ticker in config.get("tickers", []):
        symbol = ticker["symbol"]
        try:
            render_md, fields_json = capture_ticker(ticker)
        except Exception as exc:  # noqa: BLE001
            _print(f"  [FAIL] {symbol}: capture raised {type(exc).__name__}: {exc}")
            failures += 1
            continue
        if render_md is not None:
            (golden_dir / f"{symbol}.render.md").write_text(render_md, encoding="utf-8")
            _print(f"  [ok] {symbol}.render.md  ({len(render_md)} chars)")
        if fields_json is not None:
            (golden_dir / f"{symbol}.fields.json").write_text(fields_json, encoding="utf-8")
            _print(f"  [ok] {symbol}.fields.json")
    _print(f"capture -> {golden_dir}  ({'OK' if failures == 0 else str(failures) + ' FAILURES'})")
    return 1 if failures else 0


def _diff_render(expected: str, actual: str) -> list[str]:
    if expected == actual:
        return []
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    diff = difflib.unified_diff(exp_lines, act_lines, "golden", "actual", lineterm="")
    out = list(diff)[:40]
    return out


def cmd_check(config: dict, golden_dir: Path) -> int:
    golden_dir = Path(golden_dir)
    if not golden_dir.is_dir():
        _print(f"golden dir missing: {golden_dir}  (run `capture` first)")
        return 1
    failures = 0
    for ticker in config.get("tickers", []):
        symbol = ticker["symbol"]
        try:
            render_md, fields_json = capture_ticker(ticker)
        except Exception as exc:  # noqa: BLE001
            _print(f"  [FAIL] {symbol}: build raised {type(exc).__name__}: {exc}")
            failures += 1
            continue

        if ticker.get("render", True):
            g = golden_dir / f"{symbol}.render.md"
            if not g.exists():
                _print(f"  [MISS] {symbol}.render.md golden missing")
                failures += 1
            else:
                diff = _diff_render(g.read_text(encoding="utf-8"), render_md or "")
                if diff:
                    failures += 1
                    _print(f"  [DRIFT] {symbol}.render.md changed:")
                    for line in diff:
                        _print("      " + line)
                else:
                    _print(f"  [ok] {symbol}.render.md")

        if ticker.get("fields"):
            g = golden_dir / f"{symbol}.fields.json"
            if not g.exists():
                _print(f"  [MISS] {symbol}.fields.json golden missing")
                failures += 1
            else:
                expected = json.loads(g.read_text(encoding="utf-8"))
                actual = json.loads(fields_json or "{}")
                field_drift = [
                    f"{k}: {expected.get(k)} -> {actual.get(k)}"
                    for k in expected
                    if not approx_equal(expected.get(k), actual.get(k))
                ]
                if field_drift:
                    failures += 1
                    _print(f"  [DRIFT] {symbol}.fields.json:")
                    for line in field_drift:
                        _print("      " + line)
                else:
                    _print(f"  [ok] {symbol}.fields.json")

    if failures:
        _print(f"CHECK FAILED: {failures} ticker(s) drifted from golden.")
    else:
        _print("CHECK PASSED: all tickers match golden baseline.")
    return 1 if failures else 0


# ── multi-replica comparison (the 07-08 guard) ─────────────────────────────

def _find_replica_gate(tree_root: Path) -> Path | None:
    """Locate the replica's own copy of this gate script."""
    direct = tree_root / "scripts" / "golden_diff_gate.py"
    if direct.is_file():
        return direct
    for hit in tree_root.rglob("golden_diff_gate.py"):
        return hit
    return None


def _capture_replica(replica: str, config_path: Path, tmp_dir: Path, python_exe: str) -> int:
    tree = Path(replica)
    py = resolve_pythonpath(tree)
    if py is None:
        _print(f"  [SKIP] {replica}: no trader_shared package found")
        return 2
    gate = _find_replica_gate(tree)
    if gate is None:
        _print(f"  [SKIP] {replica}: golden_diff_gate.py not found in tree")
        return 2
    env = {**os.environ, "PYTHONPATH": py, "PYTHONUNBUFFERED": "1"}
    cmd = [python_exe, str(gate), "capture",
           "--config", str(config_path), "--golden-dir", str(tmp_dir)]
    res = os.system(" ".join(_shell_quote(c) for c in cmd))
    return 0 if res == 0 else 1


def _shell_quote(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"' if " " in s else s


def cmd_check_replicas(config: dict, golden_dir: Path, replicas: list[str], python_exe: str) -> int:
    import shutil
    import tempfile

    golden_dir = Path(golden_dir)
    total_fail = 0
    for replica in replicas:
        _print(f"\n== replica: {replica} ==")
        tmp = Path(tempfile.mkdtemp(prefix="golden_replica_"))
        try:
            rc = _capture_replica(replica, DEFAULT_CONFIG, tmp, python_exe)
            if rc == 2:
                total_fail += 1
                continue
            if rc != 0:
                _print(f"  [FAIL] replica capture failed (rc={rc})")
                total_fail += 1
                continue
            # diff replica output against primary golden
            rep_fail = 0
            for ticker in config.get("tickers", []):
                symbol = ticker["symbol"]
                if ticker.get("render", True):
                    g = golden_dir / f"{symbol}.render.md"
                    r = tmp / f"{symbol}.render.md"
                    if g.exists() and r.exists():
                        d = _diff_render(g.read_text(encoding="utf-8"), r.read_text(encoding="utf-8"))
                        if d:
                            rep_fail += 1
                            _print(f"  [DRIFT] {symbol}.render.md vs replica:")
                            for line in d[:20]:
                                _print("      " + line)
                if ticker.get("fields"):
                    g = golden_dir / f"{symbol}.fields.json"
                    r = tmp / f"{symbol}.fields.json"
                    if g.exists() and r.exists():
                        exp = json.loads(g.read_text(encoding="utf-8"))
                        act = json.loads(r.read_text(encoding="utf-8"))
                        drift = [k for k in exp if not approx_equal(exp.get(k), act.get(k))]
                        if drift:
                            rep_fail += 1
                            _print(f"  [DRIFT] {symbol}.fields.json vs replica: {drift}")
            if rep_fail:
                total_fail += 1
                _print(f"  [FAIL] replica drifted on {rep_fail} ticker(s)")
            else:
                _print(f"  [ok] replica matches primary golden")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return 1 if total_fail else 0


# ── CLI entry ───────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Golden-diff gate for build_report")
    sub = parser.add_subparsers(dest="cmd")
    capture_p = sub.add_parser("capture", help="regenerate golden baselines")
    check_p = sub.add_parser("check", help="diff current output against golden")
    check_p.add_argument("--replicas", nargs="+", default=None,
                         help="also compare these alternate source trees")
    for p in (capture_p, check_p):
        p.add_argument("--config", default=str(DEFAULT_CONFIG))
        p.add_argument("--golden-dir", default=str(DEFAULT_GOLDEN_DIR))

    args = parser.parse_args(argv)
    config = load_config(Path(args.config))

    if args.cmd == "capture":
        return cmd_capture(config, Path(args.golden_dir))
    if args.cmd == "check":
        rc = cmd_check(config, Path(args.golden_dir))
        if getattr(args, "replicas", None):
            rc |= cmd_check_replicas(config, Path(args.golden_dir), args.replicas, sys.executable)
        return rc
    # default: check
    return cmd_check(config, Path(args.golden_dir))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
