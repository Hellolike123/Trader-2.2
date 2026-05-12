"""Score modifier rule engine — sum of all modifiers from YAML rules."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .rule_engine import ScoreRuleEngine, RuleEngine

_ENGINE_CACHE: ScoreRuleEngine | None = None
_ENGINE_FAILED_AT: float = 0  # timestamp of last failure, 0 = never failed
_RETRY_SECONDS = 60
_MODIFIER_RULES_PATH = Path(__file__).parent / "score_rules.yml"
_LIVERMORE_RULES_PATH = Path(__file__).parent / "livermore_rules.yml"
_LIVERMORE_ENGINE_CACHE: RuleEngine | None = None
_LIVERMORE_FAILED_AT: float = 0


def apply_score_modifiers(item: dict[str, Any]) -> float | None:
    """Return sum of all score modifiers from loaded rules.

    Returns None if YAML is missing or engine fails to load.
    Retries after 60 seconds on failure.
    """
    global _ENGINE_CACHE, _ENGINE_FAILED_AT
    if _ENGINE_FAILED_AT and time.time() - _ENGINE_FAILED_AT < _RETRY_SECONDS:
        return None
    if _ENGINE_CACHE is None:
        try:
            _ENGINE_CACHE = ScoreRuleEngine.from_yaml(_MODIFIER_RULES_PATH)
            return _ENGINE_CACHE.evaluate(item)
        except Exception:
            _ENGINE_FAILED_AT = time.time()
            return None
    return _ENGINE_CACHE.evaluate(item)


def apply_livermore_scale(status: str, score: float) -> int | None:
    """Return livermore scale tier based on YAML rules.

    Returns None if YAML is missing or engine fails to load.
    Retries after 60 seconds on failure.
    """
    global _LIVERMORE_ENGINE_CACHE, _LIVERMORE_FAILED_AT
    if _LIVERMORE_FAILED_AT and time.time() - _LIVERMORE_FAILED_AT < _RETRY_SECONDS:
        return None
    if _LIVERMORE_ENGINE_CACHE is None:
        try:
            _LIVERMORE_ENGINE_CACHE = RuleEngine.from_yaml(_LIVERMORE_RULES_PATH)
        except Exception:
            _LIVERMORE_FAILED_AT = time.time()
            return None
    result = _LIVERMORE_ENGINE_CACHE.evaluate({"status": status, "score": score})
    if result is not None:
        return min(int(result), 5)
    return None
