from __future__ import annotations

from decision_core import *  # noqa: F401,F403
from structure_core import *  # noqa: F401,F403


def build_candidate_levels(current, bars, change_pct=None, quote=None):
    """Compatibility wrapper for older callers/tests."""
    return build_structure_context(current, bars, change_pct=change_pct, quote=quote)
