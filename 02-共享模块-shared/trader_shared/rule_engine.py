"""Minimal decision rule engine for trader status/scoring decisions.

Rules are loaded from YAML and evaluated by priority. Each rule has:
    name: human-readable label
    result: value returned when the rule matches
    when: a boolean expression referencing context variables

Expressions support: comparison operators, 'and'/'or'/'not', arithmetic,
parentheses, and context variables. The evaluator is sandboxed: only
variables from the context dict are accessible, no builtins.

Usage:
    engine = RuleEngine.load("path/to/rules.yml")
    result = engine.evaluate({"current": 56.0, "stop": 54.0, ...})
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _safe_eval(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple boolean expression in a sandboxed context."""
    sandbox = {"__builtins__": {
        "abs": abs,
        "min": min,
        "max": max,
    }}
    try:
        return bool(eval(expr, sandbox, dict(context)))
    except Exception:
        return False


class RuleEngine:
    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = rules

    def evaluate(self, context: dict[str, Any]) -> Any:
        for rule in self._rules:
            when = rule.get("when", "True")
            if _safe_eval(when, context):
                return rule.get("result")
        return None

    @classmethod
    def from_yaml(cls, path: str | Path) -> RuleEngine:
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML required for rule engine; install with: pip install pyyaml")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", []) if isinstance(data, dict) else data
        return cls(rules)

    @classmethod
    def from_dicts(cls, rules: list[dict[str, Any]]) -> RuleEngine:
        return cls(rules)


class ScoreRuleEngine:
    """Evaluates all matching rules and sums all their results (both + and -)."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = rules

    def evaluate(self, context: dict[str, Any]) -> float:
        total = 0.0
        for rule in self._rules:
            when = rule.get("when", "True")
            result = rule.get("result", 0)
            if not isinstance(result, (int, float)):
                raise TypeError(f"Score rule result must be numeric, got {type(result).__name__}: {result}")
            if _safe_eval(when, context):
                total += result
        return total

    @classmethod
    def from_yaml(cls, path: str | Path) -> ScoreRuleEngine:
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML required for rule engine; install with: pip install pyyaml")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", []) if isinstance(data, dict) else data
        return cls(rules)

    @classmethod
    def from_dicts(cls, rules: list[dict[str, Any]]) -> ScoreRuleEngine:
        return cls(rules)
