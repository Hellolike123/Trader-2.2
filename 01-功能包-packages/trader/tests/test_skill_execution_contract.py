"""执行型 skill 契约：SKILL / quickstart 必须是命令包装器，禁止知识库式诱导。"""

from __future__ import annotations

from pathlib import Path

import pytest

PACKAGES = Path(__file__).resolve().parents[2]
SKILLS = ("trader", "t0", "review", "daily_briefing", "wyckoff")
ENTRY = {
    "trader": "final_report.py",
    "t0": "final_t0.py",
    "review": "final_review.py",
    "daily_briefing": "briefing.py",
    "wyckoff": "final_wyckoff.py",
}
RULES_SKILLS = ("trader", "t0", "review", "wyckoff", "daily_briefing")


def _skill_md(name: str) -> str:
    return (PACKAGES / name / "SKILL.md").read_text(encoding="utf-8")


def _quickstart(name: str) -> str:
    return (PACKAGES / name / "references" / "agent-quickstart.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_is_thin_execution_wrapper(skill: str) -> None:
    text = _skill_md(skill)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) <= 55, f"{skill} SKILL.md too long ({len(lines)} non-empty lines)"
    assert ENTRY[skill] in text
    assert "原样" in text
    assert "禁止手写" in text or "禁止手写/编造" in text or "禁止手写面板" in text
    assert "禁止默认" in text and "json" in text.lower()
    assert "执行包装器" in text or "做且只做" in text


@pytest.mark.parametrize("skill", SKILLS)
def test_quickstart_hard_gates(skill: str) -> None:
    text = _quickstart(skill)
    assert ENTRY[skill] in text
    assert "原样" in text
    assert "code fence" in text.lower()
    assert "禁止" in text
    assert "Exit" in text or "停" in text
    if skill == "trader":
        assert "JSON 回退" in text


def test_common_agent_rules_execution_contract() -> None:
    common = PACKAGES / "_common" / "agent-rules.md"
    body = common.read_text(encoding="utf-8")
    assert "执行契约" in body
    assert "命令包装器" in body
    assert "凭记忆" in body
    assert "fenced code block" in body.lower()
    for skill in RULES_SKILLS:
        p = PACKAGES / skill / "references" / "agent-rules.md"
        assert p.read_text(encoding="utf-8") == body, f"{p} drifted from SSOT"


def test_anti_hallucination_is_json_fallback_only() -> None:
    text = (PACKAGES / "trader" / "references" / "anti-hallucination.md").read_text(
        encoding="utf-8"
    )
    assert "JSON 回退" in text
    assert "生成报告前必读" not in text
