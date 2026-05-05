#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJ_SCRIPTS = Path(__file__).resolve().parent
PROJECT_ROOT = PROJ_SCRIPTS.parent
PACKAGES_DIR = PROJECT_ROOT / "01-功能包-packages"
SHARED_DIR = PROJECT_ROOT / "02-共享模块-shared"


def run_self_check(pkg_name: str) -> str:
    script = PACKAGES_DIR / pkg_name / "scripts" / "self_check.py"
    if not script.exists():
        return "SKIP (no self_check.py)"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, cwd=str(script.parent),
    )
    return proc.stdout.strip() + ("\n" + proc.stderr.strip() if proc.stderr else "")


def run_tests() -> str:
    test_dirs = []
    for p in (PACKAGES_DIR / "01-单票分析-trader" / "tests",
              PACKAGES_DIR / "02-盘中T0-t0-trader" / "tests",
              PACKAGES_DIR / "03-选股池-trader-pool" / "tests",
              PACKAGES_DIR / "04-仓位轮动-trader-portfolio" / "tests",
              PACKAGES_DIR / "05-盘后复盘-review-trader" / "tests",
              SHARED_DIR / "tests"):
        if p.exists():
            test_dirs.append(str(p))

    if not test_dirs:
        return "SKIP (no test dirs)"

    proc = subprocess.run(
        [sys.executable, "-m", "pytest"] + test_dirs + ["-q"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() + ("\n" + proc.stderr.strip() if proc.stderr else "")


def check_gitignore_valid() -> str:
    gitignore = PROJECT_ROOT / ".gitignore"
    if not gitignore.exists():
        return "WARN (.gitignore not found)"
    missing = []
    with open(gitignore) as f:
        content = f.read()
    for pattern in ("__pycache__", "*.pyc", ".DS_Store"):
        if pattern not in content:
            missing.append(pattern)
    if missing:
        return f"WARN (gitignore missing patterns: {', '.join(missing)})"
    return "OK (.gitignore valid)"


def check_pipeline_schema() -> str:
    try:
        sys.path.insert(0, str(SHARED_DIR / "scripts"))
        from pipeline import STATE_SCHEMA
        if not STATE_SCHEMA.get("version"):
            return "WARN (pipeline schema missing version)"
    except ImportError:
        return "WARN (pipeline not importable)"
    return "OK"


def main() -> int:
    results = {}

    print("=" * 60)
    print("Trader 2.0 - Full Self-Check")
    print("=" * 60)

    results["gitignore"] = check_gitignore_valid()
    print(f"\n[git] {results['gitignore']}")

    results["pipeline"] = check_pipeline_schema()
    print(f"[pipeline] {results['pipeline']}")

    results["skills"] = {}
    for p in PACKAGES_DIR.iterdir():
        if p.is_file():
            continue
        name = p.name.split("-", 1)[-1] if "-" in p.name else p.name
        result = run_self_check(p.name)
        results["skills"][name] = result
        status = "OK" if "INVALID" not in result.upper() else "FAIL"
        print(f"[skill:{name}] {status}")

    results["tests"] = run_tests()
    if "passed" in results["tests"].lower() or "skipped" in results["tests"].lower() or not results["tests"]:
        test_status = "OK"
    elif "failed" in results["tests"].lower():
        test_status = "FAIL"
    else:
        test_status = "WARN"
    print(f"[tests] {test_status}")

    failures = {k: v for k, v in results.items() if "FAIL" in str(v)}
    if failures:
        print(f"\nFAILED: {list(failures.keys())}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
