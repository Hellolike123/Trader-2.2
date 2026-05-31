from __future__ import annotations

import pytest

from trader_shared.safe_cast import safe_float, safe_dict, safe_max, safe_min, require_positive


class TestSafeFloat:
    def test_none_value_returns_default(self):
        assert safe_float({"confidence": None}, "confidence") == 0.0

    def test_zero_value_preserved(self):
        assert safe_float({"confidence": 0.0}, "confidence") == 0.0

    def test_string_value_converted(self):
        assert safe_float({"price": "15.50"}, "price") == 15.5

    def test_non_numeric_string_returns_default(self):
        assert safe_float({"price": "N/A"}, "price") == 0.0

    def test_key_missing_returns_default(self):
        assert safe_float({}, "price") == 0.0

    def test_custom_default(self):
        assert safe_float({"price": None}, "price", default=-1.0) == -1.0

    def test_int_value(self):
        assert safe_float({"count": 5}, "count") == 5.0

    def test_float_value(self):
        assert safe_float({"val": 3.14}, "val") == 3.14


class TestSafeDict:
    def test_none_value_returns_empty(self):
        assert safe_dict({"buy": None}, "buy") == {}

    def test_dict_value_returned(self):
        assert safe_dict({"buy": {"price": 10.0}}, "buy") == {"price": 10.0}

    def test_key_missing_returns_empty(self):
        assert safe_dict({}, "buy") == {}

    def test_non_dict_returns_empty(self):
        assert safe_dict({"buy": "not_a_dict"}, "buy") == {}

    def test_empty_dict_value(self):
        assert safe_dict({"buy": {}}, "buy") == {}


class TestSafeMax:
    def test_empty_list(self):
        assert safe_max([]) is None

    def test_non_empty_list(self):
        assert safe_max([3, 1, 2]) == 3

    def test_empty_dict_keys(self):
        assert safe_max({}.keys()) is None

    def test_custom_default(self):
        assert safe_max([], default=0) == 0

    def test_single_element(self):
        assert safe_max([42]) == 42

    def test_generator(self):
        assert safe_max(x for x in [1, 5, 3]) == 5


class TestSafeMin:
    def test_empty_list(self):
        assert safe_min([]) is None

    def test_non_empty_list(self):
        assert safe_min([3, 1, 2]) == 1

    def test_custom_default(self):
        assert safe_min([], default=999) == 999


class TestRequirePositive:
    def test_zero_returns_none(self):
        assert require_positive(0, "price") is None

    def test_positive_returns_float(self):
        assert require_positive(15.5, "price") == 15.5

    def test_none_returns_none(self):
        assert require_positive(None, "price") is None

    def test_negative_returns_none(self):
        assert require_positive(-1.0, "price") is None

    def test_string_number(self):
        assert require_positive("10.5", "price") == 10.5

    def test_string_non_numeric(self):
        assert require_positive("abc", "price") is None
