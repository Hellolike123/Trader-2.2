"""report 标识字段写入与渲染兜底（report-wyckoff-state-fixes-handoff §1.1）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from trader_shared.testing.mock_seam import apply_seam, build_under_seam  # noqa: E402


def test_build_report_writes_identity_fields(monkeypatch):
    apply_seam(monkeypatch)
    report = build_under_seam(monkeypatch, "600000")
    assert report.get("ts_code"), report
    assert report.get("code"), report
    assert report.get("symbol"), report


def test_render_falls_back_to_symbol(monkeypatch):
    from trader_shared import wyckoff_view
    from trader_shared.report_core import render_short_midline

    captured: dict[str, str] = {}

    def _fake_display(wyckoff, *, symbol="", direction=None):
        captured["symbol"] = str(symbol)
        return "威科夫：测试"

    monkeypatch.setattr(wyckoff_view, "format_midline_display", _fake_display)

    from test_report_mid_short_sources import _report

    report = _report()
    assert "ts_code" not in report and "code" not in report  # 旧格式 report
    md = render_short_midline(report)
    assert captured.get("symbol") == "000988.SZ"
    assert "威科夫：测试" in md


def test_chan_direction_string_does_not_crash(monkeypatch):
    """direction 为字符串/None 时渲染不崩（_safe_int 兜底）。"""
    from trader_shared.report_renderer import short_midline

    for value in ("1", "-1", "看多", None, 1, -1):
        assert short_midline._safe_int(value) in (1, -1, 0)
