"""Aggregate self_check for all trader skills.

Usage:
    cd /path/to/Trader\\ 2.0 && python3 -m trader_shared.self_check_agg    # check all
    python3 -m trader_shared.self_check_agg trader                          # check single
    python3 -m trader_shared.self_check_agg --list                          # list available
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Resolve workspace root from this file's location
_SHARED = Path(__file__).resolve().parent
_WORKSPACE = _SHARED.parents[1]

SKILLS = {
    "trader": _WORKSPACE / "01-功能包-packages" / "01-单票分析-trader",
    "t0-trader": _WORKSPACE / "01-功能包-packages" / "02-盘中T0-t0-trader",
    "pool": _WORKSPACE / "01-功能包-packages" / "03-选股池-trader-pool",
    "portfolio": _WORKSPACE / "01-功能包-packages" / "04-仓位轮动-trader-portfolio",
    "review": _WORKSPACE / "01-功能包-packages" / "05-盘后复盘-review-trader",
}


def list_skills() -> None:
    print("Available skills:")
    for name in sorted(SKILLS):
        print(f"  {name}")


def check_one(skill: str, quiet: bool = False) -> int:
    script = SKILLS[skill] / "scripts" / "self_check.py"
    if not script.exists():
        if not quiet:
            print(f"SKIP={skill}: no self_check.py found", file=sys.stderr)
        return 0
    result = subprocess.run([sys.executable, str(script)], capture_output=not quiet, text=True)
    if not quiet:
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"FAIL={skill}", file=sys.stderr)
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
    return result.returncode


def run(skills: list[str] | None = None, list_only: bool = False) -> int:
    if list_only:
        list_skills()
        return 0
    if skills is None:
        skills = sorted(SKILLS)
    total = len(skills)
    passed = 0
    failed = 0
    skipped = 0
    for skill in skills:
        if skill not in SKILLS:
            print(f"SKIP={skill}: unknown skill", file=sys.stderr)
            skipped += 1
            continue
        rc = check_one(skill)
        if rc == 0:
            passed += 1
        else:
            failed += 1
    print(f"\n{'=' * 40}")
    print(f"Self-check summary: {total} skills")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")
    if failed == 0 and skipped == 0:
        print("ALL_CHECKS_PASSED=YES")
    return 1 if failed else 0


def main() -> int:
    args = sys.argv[1:]
    if "--list" in args:
        return run(list_only=True)
    skills_to_check = [a for a in args if a not in ("--list", "-l")]
    if not skills_to_check:
        return run()
    return run(skills=skills_to_check)


if __name__ == "__main__":
    raise SystemExit(main())
