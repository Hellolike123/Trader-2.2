"""[DEPRECATED] Capture the render-equivalence fixture through the test seam."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SHARED = _REPO / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from trader_shared.testing.mock_seam import _Patcher, render_under_seam


def main() -> None:
    patcher = _Patcher()
    masked = render_under_seam(patcher, "600000")

    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(masked, encoding="utf-8")
    print("RENDER EQ CAPTURE ->", out)
    print("  len =", len(masked), "lines =", masked.count("\n") + 1)


if __name__ == "__main__":
    main()
