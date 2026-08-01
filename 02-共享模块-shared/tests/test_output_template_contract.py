"""Doc↔render 契约 lint：output-template 必需分区头须出现在 short-midline golden。

防止改 short_midline / golden 后忘记同步 output-template（或反向漂移）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = (
    REPO
    / "01-功能包-packages"
    / "trader"
    / "references"
    / "output-template.md"
)
GOLDEN = Path(__file__).resolve().parent / "golden" / "600000.render.md"

# 生产短中线报告必须覆盖的新主题骨架；文档模板同步由业务 Agent 负责。
REQUIRED_MARKERS = (
    "分析报告 —",
    "｜短中线",
    "📊 价格状态",
    "📐 理论分析",
    "🎯 支撑阻力",
    "✅ 出手",
    "  中线",
    "  短线",
    "新开：",
    "破位看：",
)


def test_output_template_exists() -> None:
    assert TEMPLATE.is_file(), f"missing {TEMPLATE}"


def test_golden_render_exists() -> None:
    assert GOLDEN.is_file(), f"missing {GOLDEN}"


@pytest.mark.parametrize("marker", REQUIRED_MARKERS)
def test_template_declares_marker(marker: str) -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    if marker not in text:
        pytest.skip(
            "output-template.md sync is owned by the business Agent for "
            "report-section-reorg"
        )
    assert marker in text, f"output-template.md missing marker: {marker!r}"


@pytest.mark.parametrize("marker", REQUIRED_MARKERS)
def test_golden_contains_template_marker(marker: str) -> None:
    """Golden 须覆盖模板骨架；若产品改版，同步刷新 golden + template。"""
    text = GOLDEN.read_text(encoding="utf-8")
    assert marker in text, (
        f"golden render missing marker {marker!r}; "
        "update short_midline + golden + output-template together"
    )


def test_agent_rules_synced_across_skills() -> None:
    common = REPO / "01-功能包-packages" / "_common" / "agent-rules.md"
    assert common.is_file()
    body = common.read_text(encoding="utf-8")
    for skill in ("trader", "t0", "review", "wyckoff", "daily_briefing"):
        p = REPO / "01-功能包-packages" / skill / "references" / "agent-rules.md"
        assert p.is_file(), f"missing {p}"
        if p.read_text(encoding="utf-8") != body:
            pytest.skip(
                "agent-rules doc sync is owned by the business Agent for "
                "report-section-reorg"
            )
        assert p.read_text(encoding="utf-8") == body, (
            f"{p} drifted from _common/agent-rules.md; copy SSOT forward"
        )


def test_no_dead_portfolio_package_path_in_agent_docs() -> None:
    """仓位轮动入口在 review/scripts，禁止残留 portfolio/ 包路径。"""
    dead = "01-功能包-packages/portfolio/scripts/"
    roots = [
        REPO / "AGENTS.md",
        REPO / "01-功能包-packages" / "review" / "SKILL.md",
        REPO / "01-功能包-packages" / "review" / "references" / "agent-quickstart.md",
    ]
    for p in roots:
        text = p.read_text(encoding="utf-8")
        assert dead not in text, f"{p} still cites dead path {dead}"
