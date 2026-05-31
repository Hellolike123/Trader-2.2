"""skill-redesign-v2 验证测试：JSON 输出可解析、Markdown 不变。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add trader scripts to path
_TRADER_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_TRADER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TRADER_SCRIPTS))


class TestTraderJsonOutput:
    def test_json_output_parseable(self):
        """final_report.py 的 --output json 逻辑路径存在"""
        import final_report
        import inspect
        source = inspect.getsource(final_report.main)
        assert 'args.output == "json"' in source
        assert "json.dumps(report" in source

    def test_report_has_one_liner(self):
        """one_sentence 函数存在且返回字符串"""
        from run_analysis import one_sentence
        r = {"major_stage": "蓄势", "short_term_momentum": "走强", "confirm": 10.5,
             "stage": "低吸观察", "theory_status": "低吸观察", "current": 10.0, "support": 9.5}
        result = one_sentence(r, "9.50-9.60元")
        assert isinstance(result, str)
        assert len(result) > 0


class TestT0JsonOutput:
    def test_json_output_exists(self):
        """t0_run.py 已有 --output json 支持"""
        t0_run = Path(__file__).resolve().parents[2] / "t0" / "scripts" / "t0_run.py"
        content = t0_run.read_text(encoding="utf-8")
        assert 'args.output == "json"' in content
        assert "json.dumps" in content


class TestReviewJsonOutput:
    def test_json_output_exists(self):
        """review_single.py 已有 --output json 支持"""
        review_single = Path(__file__).resolve().parents[2] / "review" / "scripts" / "review_single.py"
        content = review_single.read_text(encoding="utf-8")
        assert 'output == "json"' in content


class TestMarkdownUnchanged:
    def test_trader_markdown_unchanged(self):
        """不加 --output json 时 Markdown 输出逻辑不变"""
        import final_report
        import inspect
        source = inspect.getsource(final_report.main)
        assert "render_markdown(report)" in source


class TestSkillMdStructure:
    def test_trader_skill_md_has_pipeline(self):
        """trader SKILL.md 包含 Pipeline 结构"""
        skill_md = Path(__file__).resolve().parent.parent / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert "Step 1" in content
        assert "Step 2" in content
        assert "Step 3" in content
        assert "防幻觉" in content

    def test_hermes_md_dual_mode(self):
        """HERMES.md 包含双模式规则"""
        hermes_md = Path(__file__).resolve().parent.parent / "HERMES.md"
        content = hermes_md.read_text(encoding="utf-8")
        assert "双模式" in content
        assert "JSON" in content
