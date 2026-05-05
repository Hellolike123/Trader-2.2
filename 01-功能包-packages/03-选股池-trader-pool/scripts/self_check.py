#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "final_pool.py"


def run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, env=env, cwd=ROOT)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for args in (
            ("analyze", "--target", "南网科技", "--offline"),
            ("add", "--target", "南网科技", "--offline"),
            ("show",),
            ("plan",),
            ("review", "--offline"),
        ):
            result = run(home, *args)
            if result.returncode != 0:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                return result.returncode
        print("TRADER_POOL_SELF_CHECK=OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
