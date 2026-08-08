"""D4 / #1：捕获 fusion 决策指纹基线（改前/改后各跑一次）。

用法：
  python scripts/dev_capture_fusion.py <out_json> [--diff <other_json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02-共享模块-shared"))

from tests.fusion_regression_helpers import SCENARIOS, capture_all  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: dev_capture_fusion.py <out_json> [--diff <other_json>]")
        return 2
    out = sys.argv[1]
    data = capture_all()
    payload = {
        "scenarios": SCENARIOS and [s["name"] for s in SCENARIOS],
        "fingerprints": data,
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"captured {len(data)} scenarios -> {out}")

    if "--diff" in sys.argv:
        idx = sys.argv.index("--diff") + 1
        other = sys.argv[idx]
        other_data = json.loads(Path(other).read_text(encoding="utf-8")).get("fingerprints", {})
        print("\n=== DIFF (pre -> post) ===")
        any_change = False
        for name in data:
            a = data[name]
            b = other_data.get(name)
            if b is None:
                print(f"  [{name}] 仅 pre 存在")
                any_change = True
                continue
            diffs = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
            marked = "★#1" if any(s["name"] == name and s.get("changed_by_fix") for s in SCENARIOS) else "  "
            if diffs:
                any_change = True
                print(f"  {marked} [{name}] CHANGED:")
                for k, (va, vb) in diffs.items():
                    print(f"        {k}: {va}  ->  {vb}")
            else:
                print(f"  {marked} [{name}] unchanged")
        if not any_change:
            print("  (无变化)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
