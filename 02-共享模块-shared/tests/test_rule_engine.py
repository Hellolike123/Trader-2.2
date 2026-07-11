"""rule_engine 模块测试。"""

from __future__ import annotations

import sys

for mod in ("trader_shared.rule_engine",):
    if mod in sys.modules:
        del sys.modules[mod]

from trader_shared.rule_engine import (
    RuleEngine,
    ScoreRuleEngine,
    _safe_eval,
)


class TestSafeEval:
    def test_simple_comparison(self):
        assert _safe_eval("x > 5", {"x": 10}) is True
        assert _safe_eval("x > 5", {"x": 3}) is False

    def test_boolean_operators(self):
        assert _safe_eval("a and b", {"a": True, "b": True}) is True
        assert _safe_eval("a and b", {"a": True, "b": False}) is False
        assert _safe_eval("a or b", {"a": False, "b": True}) is True

    def test_not_operator(self):
        assert _safe_eval("not x", {"x": False}) is True
        assert _safe_eval("not x", {"x": True}) is False

    def test_arithmetic(self):
        assert _safe_eval("x + y > 10", {"x": 5, "y": 6}) is True

    def test_abs_function(self):
        assert _safe_eval("abs(x) > 5", {"x": -10}) is True
        assert _safe_eval("abs(x) > 5", {"x": 3}) is False

    def test_min_max_functions(self):
        assert _safe_eval("min(a, b) == 3", {"a": 3, "b": 5}) is True
        assert _safe_eval("max(a, b) == 5", {"a": 3, "b": 5}) is True

    def test_invalid_expression_returns_false(self):
        assert _safe_eval("x / 0", {"x": 1}) is False
        assert _safe_eval("undefined_var", {}) is False

    def test_no_builtins_access(self):
        # Should not be able to import or call arbitrary functions
        assert _safe_eval("__import__('os')", {}) is False


class TestRuleEngine:
    def test_first_matching_rule_wins(self):
        rules = [
            {"when": "x > 10", "result": "high"},
            {"when": "x > 5", "result": "medium"},
            {"when": "x > 0", "result": "low"},
        ]
        engine = RuleEngine.from_dicts(rules)
        assert engine.evaluate({"x": 15}) == "high"
        assert engine.evaluate({"x": 7}) == "medium"
        assert engine.evaluate({"x": 1}) == "low"

    def test_no_match_returns_none(self):
        rules = [{"when": "x > 100", "result": "high"}]
        engine = RuleEngine.from_dicts(rules)
        assert engine.evaluate({"x": 5}) is None

    def test_empty_rules_returns_none(self):
        engine = RuleEngine.from_dicts([])
        assert engine.evaluate({"x": 5}) is None

    def test_default_when_is_true(self):
        rules = [{"result": "default"}]
        engine = RuleEngine.from_dicts(rules)
        assert engine.evaluate({}) == "default"

    def test_complex_condition(self):
        rules = [
            {"when": "price < stop and pct < -1.5", "result": "stop_loss"},
        ]
        engine = RuleEngine.from_dicts(rules)
        assert engine.evaluate({"price": 50, "stop": 55, "pct": -2.0}) == "stop_loss"
        assert engine.evaluate({"price": 60, "stop": 55, "pct": -2.0}) is None


class TestScoreRuleEngine:
    def test_sum_matching_rules(self):
        rules = [
            {"when": "x > 5", "result": 10},
            {"when": "x > 3", "result": 5},
            {"when": "x > 1", "result": 2},
        ]
        engine = ScoreRuleEngine.from_dicts(rules)
        # x=10 matches all three: 10+5+2 = 17
        assert engine.evaluate({"x": 10}) == 17

    def test_no_match_returns_zero(self):
        rules = [{"when": "x > 100", "result": 10}]
        engine = ScoreRuleEngine.from_dicts(rules)
        assert engine.evaluate({"x": 5}) == 0.0

    def test_negative_results(self):
        rules = [
            {"when": "x > 5", "result": 10},
            {"when": "x < 3", "result": -5},
        ]
        engine = ScoreRuleEngine.from_dicts(rules)
        assert engine.evaluate({"x": 10}) == 10
        assert engine.evaluate({"x": 1}) == -5
        assert engine.evaluate({"x": 4}) == 0.0

    def test_non_numeric_result_raises(self):
        rules = [{"when": "True", "result": "not_a_number"}]
        engine = ScoreRuleEngine.from_dicts(rules)
        import pytest
        with pytest.raises(TypeError, match="Score rule result must be numeric"):
            engine.evaluate({})

    def test_empty_rules_returns_zero(self):
        engine = ScoreRuleEngine.from_dicts([])
        assert engine.evaluate({}) == 0.0
