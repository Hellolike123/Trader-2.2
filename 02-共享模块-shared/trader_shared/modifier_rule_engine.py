"""Score modifier rule engine — sum of all modifiers from YAML rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .rule_engine import ScoreRuleEngine, RuleEngine

_ENGINE_CACHE: ScoreRuleEngine | None = None
_ENGINE_FAILED = False
_MODIFIER_RULES_PATH = Path(__file__).parent / "score_rules.yml"
_LIVERMORE_RULES_PATH = Path(__file__).parent / "livermore_rules.yml"
_LIVERMORE_ENGINE_CACHE: RuleEngine | None = None
_LIVERMORE_ENGINE_FAILED = False


def apply_score_modifiers(item: dict[str, Any]) -> float | None:
    """Return sum of all score modifiers from loaded rules.

    Returns None if YAML is missing or engine fails to load.
    """
    global _ENGINE_CACHE, _ENGINE_FAILED
    if _ENGINE_FAILED:
        return None
    if _ENGINE_CACHE is None:
        try:
            _ENGINE_CACHE = ScoreRuleEngine.from_yaml(_MODIFIER_RULES_PATH)
            return _ENGINE_CACHE.evaluate(item)
        except Exception:
            _ENGINE_FAILED = True
            return None
    return _ENGINE_CACHE.evaluate(item)


def apply_livermore_scale(status: str, score: float) -> int | None:
    """Return livermore scale tier based on YAML rules.

    Returns None if YAML is missing or engine fails to load.
    """
    global _LIVERMORE_ENGINE_CACHE, _LIVERMORE_ENGINE_FAILED
    if _LIVERMORE_ENGINE_FAILED:
        return None
    if _LIVERMORE_ENGINE_CACHE is None:
        try:
            _LIVERMORE_ENGINE_CACHE = RuleEngine.from_yaml(_LIVERMORE_RULES_PATH)
        except Exception:
            _LIVERMORE_ENGINE_FAILED = True
            return None
    result = _LIVERMORE_ENGINE_CACHE.evaluate({"status": status, "score": score})
    if result is not None:
        return min(int(result), 5)
    return None
