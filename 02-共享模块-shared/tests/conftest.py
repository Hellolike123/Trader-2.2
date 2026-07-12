"""Test bootstrap for trader_shared.

Ensures the shared package root is importable regardless of pytest's
invocation directory, so `import trader_shared` (and its submodules)
resolve without relying on the legacy scripts/ path injection.
"""
import sys
from pathlib import Path

# 02-共享模块-shared/ — parent of this tests/ dir
_SHARED_ROOT = Path(__file__).resolve().parent.parent
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
