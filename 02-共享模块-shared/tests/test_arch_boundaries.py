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
    # 法源 BUSINESS §2.0：无周线载荷 → insufficient midline，禁日线冒充
    assert cards["wyckoff_midline"].get("role") == "midline"
    assert cards["wyckoff_midline"].get("timeframe") == "insufficient"


def test_ensure_wyckoff_midline_no_daily_fallback():
    """ensure 不得用日线 wyckoff 填充 wyckoff_midline。"""
    from trader_shared.analysis_cards import ensure_report_analysis_cards

    report: dict = {
        "current": 10.0,
        "wyckoff": {
            "phase": "markup",
            "phase_label": "上涨",
            "timeframe": "daily",
            "spring_signal": True,
        },
        "fusion": {"signals_detail": {}},
    }
    cards = ensure_report_analysis_cards(report)
    mid = cards["wyckoff_midline"]
    assert mid.get("role") == "midline"
    assert mid.get("timeframe") == "insufficient"
    assert mid.get("phase") in ("", None) or mid.get("timeframe") == "insufficient"


def test_ensure_wyckoff_midline_rejects_sparse_unknown():
    """稀疏/无 weekly timeframe 的 wyckoff_midline 不得建成可用中线卡。"""
    from trader_shared.analysis_cards import ensure_report_analysis_cards

    report: dict = {
        "current": 10.0,
        "wyckoff_midline": {"phase": "none"},
        "fusion": {"signals_detail": {}},
    }
    cards = ensure_report_analysis_cards(report)
    mid = cards["wyckoff_midline"]
    assert mid.get("timeframe") == "insufficient"
    assert mid.get("status") == "insufficient"


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


def _ast_mentions_name(node: ast.AST, name: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == name:
            return True
    return False


def _is_call_to(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False


def test_build_signal_gates_map_fusion_behind_override_flag():
    """R1/#50 M6：build_signal 内 _map_fusion_to_signal 须在 FUSION_OVERRIDE_ENABLED 闸内。

    假实现「无闸 remap」应失败：所有 map 调用必须落在检查该名的 If 体内。
    """
    path = PKG / "signal_core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    build_fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "build_signal"
        ),
        None,
    )
    assert build_fn is not None, "signal_core.build_signal missing"

    gated_calls = 0
    ungated_calls = 0

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._gate_depth = 0

        def visit_If(self, node: ast.If) -> None:
            gated = _ast_mentions_name(node.test, "FUSION_OVERRIDE_ENABLED")
            if gated:
                self._gate_depth += 1
                self.generic_visit(node)
                self._gate_depth -= 1
            else:
                self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            nonlocal gated_calls, ungated_calls
            if _is_call_to(node, "_map_fusion_to_signal"):
                if self._gate_depth > 0:
                    gated_calls += 1
                else:
                    ungated_calls += 1
            self.generic_visit(node)

    _Visitor().visit(build_fn)
    assert gated_calls >= 1, "expected _map_fusion_to_signal under FUSION_OVERRIDE_ENABLED"
    assert ungated_calls == 0, f"ungated _map_fusion_to_signal calls: {ungated_calls}"


def test_report_builder_no_tencent_fetcher_ctor():
    """R3/A3：report_builder 源码不得再构造 TencentFetcher()。"""
    src = (PKG / "report_builder.py").read_text(encoding="utf-8")
    assert "TencentFetcher()" not in src
    assert "from trader_shared.fetchers import TencentFetcher" not in src


def test_analysis_package_no_classic_mappers_import():
    """F1d/A1：analysis/*.py 不得 import fusion_classic_mappers。"""
    analysis_dir = PKG / "analysis"
    bad: list[tuple[str, str]] = []
    for path in sorted(analysis_dir.glob("*.py")):
        imports = _imports_in_file(path)
        for imp in imports:
            if imp == "trader_shared.fusion_classic_mappers" or imp.startswith(
                "trader_shared.fusion_classic_mappers."
            ):
                bad.append((path.name, imp))
            elif imp == "fusion_classic_mappers" or imp.endswith(".fusion_classic_mappers"):
                bad.append((path.name, imp))
    assert not bad, f"analysis must not import classic_mappers: {bad}"


def test_score_to_confidence_neutral_reexport_same_values():
    """F1e/A2：中性模块与 classic re-export / fusion_core 懒导入数值一致。"""
    from trader_shared.fusion_classic_mappers import _score_to_confidence as via_classic
    from trader_shared.fusion_confidence import _score_to_confidence as via_neutral
    from trader_shared.fusion_core import _score_to_confidence as via_core

    samples = (0, 20, 25, 35, 40, 45, 50, 60, 65, 75, 90, 100, None, "abc")
    for s in samples:
        a, b, c = via_neutral(s), via_classic(s), via_core(s)
        assert a == b == c, f"score={s!r}: neutral={a} classic={b} core={c}"


def test_build_daily_ruling_source_ignores_fusion_action():
    """A3：build_daily_ruling 源码不读 fusion.action / reduce_like。"""
    import inspect

    from trader_shared.conclusion_block import build_daily_ruling

    src = inspect.getsource(build_daily_ruling)
    assert 'fusion.get("action")' not in src
    assert "fusion['action']" not in src
    assert '["action"]' not in src
    assert "reduce_like" not in src
