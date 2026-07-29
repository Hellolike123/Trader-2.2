"""测试 report_renderer 子包

验证以下内容：
1. 子包可以正确导入所有4个公共渲染函数
2. re-export 指向的是 report_core 的同一函数对象（无代码重复）
3. render_single 路由逻辑正确
4. 各子模块可独立导入
5. 渲染不崩溃，输出格式符合微信红线（无 # ** | > -）
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "02-共享模块-shared"))


_MINIMAL_REPORT = {
    "name": "单测股票",
    "symbol": "000001.SZ",
    "current": 10.5,
    "change_pct": 1.5,
}


class TestReportRendererImports:
    """验证子包导入完整性"""

    def test_package_level_imports(self):
        from trader_shared.report_renderer import (
            render_single,
            render_short_midline,
            render_single_legacy,
            render_pool_summary,
            render_backtest,
        )
        assert callable(render_single)
        assert callable(render_short_midline)
        assert callable(render_single_legacy)
        assert callable(render_pool_summary)
        assert callable(render_backtest)

    def test_short_midline_submodule(self):
        from trader_shared.report_renderer.short_midline import render_short_midline
        assert callable(render_short_midline)

    def test_legacy_submodule(self):
        from trader_shared.report_renderer.legacy import render_single_legacy
        assert callable(render_single_legacy)

    def test_pool_submodule(self):
        from trader_shared.report_renderer.pool import render_pool_summary
        assert callable(render_pool_summary)

    def test_backtest_submodule(self):
        from trader_shared.report_renderer.backtest import render_backtest
        assert callable(render_backtest)


class TestReportRendererCompatibility:
    """验证与 report_core 的兼容性（re-export 一致性）"""

    def test_render_short_midline_identity(self):
        """re-export 必须指向同一函数对象（无代码重复）"""
        from trader_shared.report_renderer import render_short_midline as f1
        from trader_shared.report_core import render_short_midline as f2
        assert f1 is f2

    def test_render_single_legacy_identity(self):
        from trader_shared.report_renderer import render_single_legacy as f1
        from trader_shared.report_core import render_single_legacy as f2
        assert f1 is f2

    def test_render_pool_summary_identity(self):
        from trader_shared.report_renderer import render_pool_summary as f1
        from trader_shared.report_core import render_pool_summary as f2
        assert f1 is f2

    def test_render_backtest_identity(self):
        from trader_shared.report_renderer import render_backtest as f1
        from trader_shared.report_core import render_backtest as f2
        assert f1 is f2


class TestRenderSingleRouting:
    """验证 render_single 路由逻辑"""

    def test_defaults_to_short_midline(self, monkeypatch):
        """默认情况下应路由到 render_short_midline"""
        monkeypatch.setenv("SHORT_MIDLINE_REPORT", "true")
        from trader_shared.report_renderer import render_single, render_short_midline
        out_route = render_single(_MINIMAL_REPORT)
        out_direct = render_short_midline(_MINIMAL_REPORT)
        assert out_route == out_direct

    def test_false_env_still_short_midline(self, monkeypatch):
        """SHORT_MIDLINE_REPORT=false 已忽略：仍走短中线。"""
        monkeypatch.setenv("SHORT_MIDLINE_REPORT", "false")
        import warnings

        from trader_shared.report_renderer import render_single, render_short_midline
        from trader_shared.report_renderer._helpers import _short_midline_enabled

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert _short_midline_enabled() is True
            out_route = render_single(_MINIMAL_REPORT)
            out_direct = render_short_midline(_MINIMAL_REPORT)
        assert out_route == out_direct
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TestRenderOutputFormat:
    """验证渲染输出符合微信格式红线"""

    def test_no_markdown_headers(self):
        """禁止 # 标题"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        lines = out.splitlines()
        for line in lines:
            assert not line.startswith("#"), f"发现 # 标题: {line!r}"

    def test_no_markdown_bold(self):
        """禁止 ** 粗体"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        assert "**" not in out, "发现 ** 粗体语法"

    def test_no_markdown_table(self):
        """禁止 |..| 表格（允许全角 ｜）"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        import re
        # 检查是否存在 ASCII | 开头或结尾的行（Markdown 表格特征）
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                raise AssertionError(f"疑似 Markdown 表格行: {line!r}")

    def test_no_blockquote(self):
        """禁止 > 块引用"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        for line in out.splitlines():
            assert not line.startswith(">"), f"发现 > 块引用: {line!r}"

    def test_first_line_format(self):
        """首行必须是「分析报告 — ...｜短中线」"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        first_line = out.splitlines()[0]
        assert "分析报告" in first_line or "短中线" in first_line, \
            f"首行格式不符: {first_line!r}"

    def test_returns_nonempty_string(self):
        """渲染结果不能为空字符串"""
        from trader_shared.report_renderer import render_short_midline
        out = render_short_midline(_MINIMAL_REPORT)
        assert isinstance(out, str) and len(out) > 0
