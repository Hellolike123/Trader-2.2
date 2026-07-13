"""Split report_builder.py into domain (report_builder) + presentation (report_renderer).

AST-based: each top-level node is classified by name and emitted to the correct
file verbatim (ast.get_source_segment preserves exact source). No line-range slicing.

Domain stays in report_builder.py:
  build_report, _degraded_quote_report, determine_stage, structure_replay,
  sync_report_with_data, _calc_volume_ratio_from_bars  (+ _logger, SCRIPT_DIR)
Presentation moves to report_renderer.py:
  the 22 view/format helpers + _get_kelly_data, _get_major_stage (presentation-
  support fetchers, only called by presentation) + module consts
  (_kelly_cache, CONTRACT_VERSION, _SIGNAL_TYPE_LABELS).

report_builder.py re-exports every presentation name at its bottom so the public
API (run_analysis.py's 31-name import) is unchanged. Dependency is strictly
builder -> renderer (no cycle).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "02-共享模块-shared" / "trader_shared" / "report_builder.py"
REND = REPO / "02-共享模块-shared" / "trader_shared" / "report_presentation.py"

src = SRC.read_text(encoding="utf-8")
tree = ast.parse(src)

# 22 view/format helpers + 2 presentation-support fetchers => move to renderer
RENDERER_FUNCS = {
    # view/format helpers
    "today_text", "_signal_type_label", "_signal_direction_text", "_fusion_breakdown",
    "price", "pct", "numeric_values", "ma_text", "chunks", "short_date",
    "volume_observation", "upward_momentum_observation", "_get_buy_label",
    "render_markdown", "signal_state", "signal_max_total_pct", "signal_risk_flags",
    "structure_view", "volume_view", "generate_alert", "build_watch_alert",
    "action_text_for_scene",
    # presentation-support fetchers (only called by presentation funcs)
    "_get_kelly_data", "_get_major_stage",
}
REEXPORT_NAMES = sorted(RENDERER_FUNCS)  # 24 names

# module consts that live with presentation
RENDERER_CONSTS = {"_kelly_cache", "CONTRACT_VERSION", "_SIGNAL_TYPE_LABELS"}
# emitted to BOTH files (imports + logger)
SHARED_BOTH = {"_logger"}


def seg(node: ast.AST) -> str:
    return ast.get_source_segment(src, node) or ""


renderer_parts: list[str] = []
builder_parts: list[str] = []

for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.Try)):
        # imports (incl. try/except import blocks) -> both
        s = seg(node)
        renderer_parts.append(s)
        builder_parts.append(s)
    elif isinstance(node, ast.Assign):
        name = node.targets[0].id
        s = seg(node)
        if name in SHARED_BOTH:
            renderer_parts.append(s)
            builder_parts.append(s)
        elif name in RENDERER_CONSTS:
            renderer_parts.append(s)
        else:
            builder_parts.append(s)  # e.g. SCRIPT_DIR
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        name = node.target.id
        s = seg(node)
        if name in RENDERER_CONSTS:
            renderer_parts.append(s)
        elif name in SHARED_BOTH:
            renderer_parts.append(s)
            builder_parts.append(s)
        else:
            builder_parts.append(s)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        s = seg(node)
        if node.name in RENDERER_FUNCS:
            renderer_parts.append(s)
        else:
            builder_parts.append(s)
    else:
        s = seg(node).strip()
        if s:
            builder_parts.append(s)  # docstring / other -> builder

# bottom re-export in builder keeps the public API stable
reexport = (
    "# Re-export presentation API so external consumers (run_analysis.py) are unaffected.\n"
    "from .report_presentation import (\n"
    + ",\n".join(f"    {n}" for n in REEXPORT_NAMES)
    + ",\n)\n"
)
builder_parts.append(reexport)

header_rend = (
    '# -*- coding: utf-8 -*-\n'
    '"""Presentation layer: render_markdown + view/format helpers.\n'
    'Domain orchestration lives in report_builder.py (build_report)."""\n\n'
)
header_build = (
    '# -*- coding: utf-8 -*-\n'
    '"""Domain layer: build_report orchestration + analysis.\n'
    'Presentation (render_markdown + helpers) is in report_renderer.py."""\n\n'
)

REND.write_text(header_rend + "\n\n".join(renderer_parts) + "\n", encoding="utf-8")
SRC.write_text(header_build + "\n\n".join(builder_parts) + "\n", encoding="utf-8")

print("renderer lines:", (header_rend + "\n\n".join(renderer_parts)).count("\n") + 1)
print("builder lines:", (header_build + "\n\n".join(builder_parts)).count("\n") + 1)
print("reexport count:", len(REEXPORT_NAMES))
