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


def test_classic_fusion_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", "classic")
    from trader_shared.fusion_core import _fusion_input_mode

    with pytest.raises(ValueError, match="classic"):
        _fusion_input_mode()


def test_compare_fusion_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", "compare")
    from trader_shared.fusion_core import _fusion_input_mode

    with pytest.raises(ValueError, match="compare"):
        _fusion_input_mode()


@pytest.mark.parametrize("value", ["cards", "true", "1", "on", "auto"])
def test_fusion_cards_env_values_accepted(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", value)
    from trader_shared.fusion_core import _fusion_input_mode

    assert _fusion_input_mode() == "cards"


@pytest.mark.parametrize("value", ["classic", "compare", "false", "0", "off", "both", "dual"])
def test_fusion_retired_env_values_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FUSION_FROM_CARDS", value)
    from trader_shared.fusion_core import _fusion_input_mode

    with pytest.raises(ValueError, match="removed"):
        _fusion_input_mode()


def test_fusion_explicit_bool_cards_and_rejected() -> None:
    from trader_shared.fusion_core import _fusion_input_mode

    assert _fusion_input_mode(True) == "cards"
    with pytest.raises(ValueError, match="removed"):
        _fusion_input_mode(False)


def test_legacy_env_ignored_still_short_midline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORT_MIDLINE_REPORT", "false")
    from trader_shared.report_renderer._helpers import _short_midline_enabled

    with pytest.warns(DeprecationWarning, match="SHORT_MIDLINE_REPORT=false"):
        assert _short_midline_enabled() is True


def test_render_single_always_short_midline() -> None:
    from trader_shared.report_core import render_single, render_short_midline

    r = {"name": "单测", "symbol": "000001.SZ", "current": 10.0, "change_pct": 0.0}
    assert render_single(r) == render_short_midline(r)
