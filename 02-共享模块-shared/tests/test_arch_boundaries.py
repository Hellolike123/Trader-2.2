"""架构边界红线（加固 A）。

docs/designs/analysis-strategy-boundaries.md
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "trader_shared"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# strategy 层禁止直接依赖的「检测实现」模块
_STRATEGY_FORBIDDEN_IMPORTS = frozenset({
    "trader_shared.wyckoff_events",
    "trader_shared.wyckoff_phase",
    "trader_shared.chan_structure",
    "trader_shared.chan_geometry",
    "trader_shared.chip_distribution",
    "trader_shared.chan_nesting",
})

_STRATEGY_FILES = [
    PKG / "strategy" / "match.py",
    PKG / "strategy_match.py",  # 兼容 re-export 桩（不得含检测 import）
]


def _imports_in_file(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
    return found


def test_strategy_match_file_no_forbidden_analysis_impl_imports():
    """strategy_match 不得 import 缠/威检测实现模块。"""
    for path in _STRATEGY_FILES:
        assert path.is_file(), f"missing {path}"
        imports = _imports_in_file(path)
        bad = imports & _STRATEGY_FORBIDDEN_IMPORTS
        # also catch relative-looking full names
        for imp in imports:
            for forb in _STRATEGY_FORBIDDEN_IMPORTS:
                if imp == forb or imp.startswith(forb + "."):
                    bad.add(imp)
        assert not bad, f"{path.name} forbids analysis impl imports, found {bad}"


def test_strategy_match_does_not_import_chan_core_detect():
    """允许文档提及；源码 import 列表不应含 chan_core（检测在 analysis）。"""
    for rel in ("strategy/match.py", "strategy_match.py"):
        text = (PKG / rel).read_text(encoding="utf-8")
        assert "from trader_shared.chan_core" not in text
        assert "from trader_shared.wyckoff_core" not in text
        assert "from trader_shared.wyckoff_events" not in text


def test_analysis_and_strategy_packages_exist():
    """Arch D：物理包目录存在。"""
    assert (PKG / "analysis" / "cards.py").is_file()
    assert (PKG / "analysis" / "fusion_card_signals.py").is_file()
    assert (PKG / "strategy" / "match.py").is_file()
    assert (PKG / "strategy" / "packs").is_dir()
    assert list((PKG / "strategy" / "packs").glob("*.yaml"))


def test_ensure_report_analysis_cards_keys():
    """B：ensure 后键齐全。"""
    from trader_shared.analysis_cards import ensure_report_analysis_cards

    report: dict = {
        "current": 10.0,
        "chanlun": {"chanlun": {"buy_points": [], "sell_points": [], "divergence": {}, "trend_label": ""}},
        "fusion": {"signals_detail": {}},
    }
    cards = ensure_report_analysis_cards(report)
    for k in ("chan", "wyckoff", "wyckoff_midline", "momentum", "chip", "vpf"):
        assert k in cards
        assert isinstance(cards[k], dict)
        assert "schema_version" in cards[k]
        assert "source" in cards[k]
    assert report["analysis_cards"] is cards


def test_match_prefers_analysis_cards_over_raw():
    """上下文优先读卡：卡上是一买，顶层错误字段应被卡覆盖。"""
    from trader_shared.strategy_match import build_match_context, match_strategies

    report = {
        "current": 20.0,
        "has_position": False,
        "allow_new_entry": True,
        "checklist_all_green": True,
        "chan_type_short": "二买",  # 错误桩
        "analysis_cards": {
            "chan": {
                "schema_version": "chan_card_v1",
                "source": "chan",
                "type_short": "一买",
                "type_raw": "一类买",
                "direction": 1,
            },
            "wyckoff": {"event_code": "—", "source": "wyckoff"},
            "chip": {"support_tag": "", "trapped_tag": ""},
        },
        "discipline": {"allow_new_entry": True, "entry_checklist": {"all_green": True}},
    }
    ctx = build_match_context(report)
    assert ctx["chan_type_short"] == "一买"
    r = match_strategies(report)
    ent = r["gates"]["entry"]
    assert ent["primary"] is not None
    assert ent["primary"]["id"] == "entry.chan_buy1_probe"
