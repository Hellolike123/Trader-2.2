# -*- coding: utf-8 -*-
"""Offline review_core seams (no network)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_build_review_assigns_symbol_before_wyckoff_call():
    """Regression: symbol must be bound before wyckoff_analysis(..., symbol=symbol)."""
    src_path = ROOT / "trader_shared" / "review_core.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))

    build_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build_review":
            build_fn = node
            break
    assert build_fn is not None

    assign_lineno = None
    wyckoff_lineno = None
    for node in ast.walk(build_fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "symbol":
                    assign_lineno = node.lineno if assign_lineno is None else min(assign_lineno, node.lineno)
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "wyckoff_analysis":
                wyckoff_lineno = node.lineno

    assert assign_lineno is not None, "symbol assignment missing in build_review"
    assert wyckoff_lineno is not None, "wyckoff_analysis call missing in build_review"
    assert assign_lineno < wyckoff_lineno, (
        f"symbol assigned at L{assign_lineno} but wyckoff uses it at L{wyckoff_lineno}"
    )
