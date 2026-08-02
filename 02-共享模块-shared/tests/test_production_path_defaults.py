"""生产契约冻结：短中线 + fusion cards 为默认路径。"""
from __future__ import annotations

import os

import pytest


def test_short_midline_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHORT_MIDLINE_REPORT", raising=False)
    # 重新读配置模块上的解析逻辑（与 config 缺省一致）
    from trader_shared.report_renderer._helpers import _short_midline_enabled

    assert _short_midline_enabled() is True


def test_fusion_default_mode_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUSION_FROM_CARDS", raising=False)
    from trader_shared.fusion_core import _fusion_input_mode

    assert _fusion_input_mode() == "cards"


def test_classic_fusion_emits_deprecation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", "classic")
    from trader_shared.fusion_core import _fusion_input_mode

    with pytest.warns(DeprecationWarning, match="retired"):
        assert _fusion_input_mode() == "cards"


def test_compare_fusion_emits_deprecation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", "compare")
    from trader_shared.fusion_core import _fusion_input_mode

    with pytest.warns(DeprecationWarning, match="retired"):
        assert _fusion_input_mode() == "cards"


def test_legacy_env_ignored_still_short_midline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORT_MIDLINE_REPORT", "false")
    from trader_shared.report_renderer._helpers import _short_midline_enabled

    with pytest.warns(DeprecationWarning, match="SHORT_MIDLINE_REPORT=false"):
        assert _short_midline_enabled() is True


def test_render_single_always_short_midline() -> None:
    from trader_shared.report_core import render_single, render_short_midline

    r = {"name": "单测", "symbol": "000001.SZ", "current": 10.0, "change_pct": 0.0}
    assert render_single(r) == render_short_midline(r)
