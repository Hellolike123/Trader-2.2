"""D3 异常可见性：exception_tracker 单测（离线，无网络）。"""
from __future__ import annotations

import os

import pytest

from trader_shared import exception_tracker as et


@pytest.fixture(autouse=True)
def _isolate():
    et.reset()
    yield
    et.reset()


def test_record_and_collect():
    et.record(ValueError("x"), "mod.a")
    et.record(RuntimeError("y"), "mod.b")
    et.record(ValueError("x"), "mod.a")  # 同类型+位置累加
    items = et.collect()
    assert len(items) == 2
    # count 降序；ValueError 出现 2 次排第一
    assert items[0]["type"] == "ValueError"
    assert items[0]["location"] == "mod.a"
    assert items[0]["count"] == 2
    assert items[1]["count"] == 1


def test_reset_clears():
    et.record(KeyError("k"), "mod.c")
    assert et.collect()
    et.reset()
    assert et.collect() == []


def test_suppress_and_count_counts_and_swallows():
    with et.suppress_and_count("mod.d"):
        raise RuntimeError("boom")
    items = et.collect()
    assert len(items) == 1
    assert items[0]["type"] == "RuntimeError"
    assert items[0]["location"] == "mod.d"


def test_suppress_and_count_passes_through_no_error():
    with et.suppress_and_count("mod.e"):
        pass
    assert et.collect() == []


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("TRADER_EXCEPTION_TRACK", "0")
    monkeypatch.setattr(et, "ENABLED", False)
    et.record(ValueError("x"), "mod.f")
    assert et.collect() == []


def test_record_accepts_exception_class():
    et.record(ValueError, "mod.g")
    items = et.collect()
    assert items[0]["type"] == "ValueError"
    assert items[0]["location"] == "mod.g"
