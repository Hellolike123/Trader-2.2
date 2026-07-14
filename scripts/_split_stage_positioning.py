#!/usr/bin/env python3
"""一次脚本：把 stage_positioning.py 行为保持地拆为
  stage_state.py     (叶子：状态持久化 + 组合相关)
  stage_detect.py    (阶段探测引擎)
  stage_stops.py     (止损/退出)
  stage_position.py  (持仓评估 + 打分 + 止盈)
  stage_positioning.py (facade: 全量 re-export)

轮辐结构：detect/stops/position 都只依赖 state（无环）。
"""
import ast
import os
import shutil
import sys

SRC = "02-共享模块-shared/trader_shared/stage_positioning.py"
OUT_DIR = "02-共享模块-shared/trader_shared"

STATE = [
    "calc_portfolio_correlation", "_load_stage_state", "_save_stage_state",
]
DETECT = [
    "_bearish_alignment", "_assess_volume_price", "_detect_main_force_stage",
    "_volume_price_confirm", "_downgrade_stage", "_upgrade_stage",
    "_detect_major_stage", "_detect_short_term_momentum",
    "_layer1_multi_day_confirm", "_layer2_confidence_gate",
    "_layer3_cross_validation", "_layer4_stage_lock",
    "compute_position_with_env", "assess_stage", "action_for_holding_state",
]
STOPS = [
    "compute_stop_losses", "compute_exit_plan", "compute_stage_stop",
    "check_time_stop", "compute_stop_summary",
]
POSITION = [
    "evaluate_position_state", "_calc_pullback_add_score",
    "_calc_reentry_score", "_calc_rally_reduce_score",
    "_assess_resistance_strength", "_make_position_state",
    "_empty_position_state", "compute_conditional_take_profit",
    "compute_take_profit",
]

LEVEL = {"state": 0, "detect": 1, "stops": 1, "position": 1, "facade": 2}


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node

    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            consts[node.target.id] = node

    all_names = set(defs) | set(consts)
    partitions = {
        "state": set(STATE),
        "detect": set(DETECT),
        "stops": set(STOPS),
        "position": set(POSITION),
        "facade": set(),
    }
    # route constants via reference analysis
    name2part = {}
    for part, names in partitions.items():
        for n in names:
            name2part[n] = part

    def referenced_names(node):
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in all_names}

    # assign constants to partitions that reference them
    const_partitions = {cname: set() for cname in consts}
    for fname, fnode in defs.items():
        fpart = name2part.get(fname, "facade")
        for ref in referenced_names(fnode):
            if ref in consts:
                const_partitions[ref].add(fpart)
    for cname, ref_parts in const_partitions.items():
        if not ref_parts:
            ref_parts = {"state"}  # unreferenced → safest leaf
        for rp in ref_parts:
            partitions.setdefault(rp, set()).add(cname)
        name2part[cname] = min(ref_parts, key=lambda p: LEVEL.get(p, 99))

    covered = set().union(*partitions.values())
    assert not (all_names - covered), f"未分配: {all_names - covered}"
    assert not ({n for p in partitions for n in partitions[p]} - all_names), "分区包含不存在的名字"

    edges = []
    for fname, fnode in defs.items():
        fpart = name2part.get(fname, "facade")
        for ref in referenced_names(fnode):
            rpart = name2part.get(ref)
            if rpart and rpart != fpart:
                edges.append((fpart, rpart, fname, ref))

    # level-based: forbidden if caller_level < callee_level (upstream depends on downstream)
    forbidden = [(c, r, fn, rn) for (c, r, fn, rn) in edges
                 if LEVEL.get(c, 99) < LEVEL.get(r, 99)]
    # cross-peer edges are also flagged (potential cycles)
    cross_peer = [(c, r, fn, rn) for (c, r, fn, rn) in edges
                  if LEVEL.get(c, 99) == LEVEL.get(r, 99) and c != r and c != "facade"]
    if forbidden:
        print("❌ 禁止的依赖边（上游→下游）：")
        for c, r, fn, rn in forbidden:
            print(f"   {c}::{fn}  ->  {r}::{rn}")
        sys.exit(1)
    if cross_peer:
        print("⚠️  跨对等分区依赖边（若双向则成环，建议合并相关分区）：")
        for c, r, fn, rn in cross_peer:
            print(f"   {c}::{fn}  ->  {r}::{rn}")

    print(f"✅ 依赖校验通过。def {len(defs)} 个，常量 {len(consts)} 个，跨分区边 {len(edges)} 条")
    for c, r, fn, rn in edges:
        arrow = "⚠️" if LEVEL.get(c, 99) == LEVEL.get(r, 99) and c != r else "->"
        print(f"   {c}::{fn}  {arrow}  {r}::{rn}")

    # prologue collection (imports/try-except only; skip module docstring
    # since each write_module already supplies its own)
    prologue_parts = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Try)):
            prologue_parts.append(ast.get_source_segment(source, node))
        # skip ast.Expr (docstring) — each submodule gets its own from write_module
    import_block = "\n".join(p for p in prologue_parts if p) + "\n"

    def src(name):
        return ast.get_source_segment(source, defs[name])

    def const_src(name):
        return ast.get_source_segment(source, consts[name])

    def write_module(filename, doc, part):
        parts = [f'"""{doc}"""\n', import_block]
        # auto-derive cross-submodule imports from edges
        needed = {"state": False, "detect": False, "stops": False, "position": False}
        for c, r, _, rn in edges:
            if c == part and r in needed:
                needed[r] = True
        if needed["state"]:
            parts.append("\nfrom .stage_state import (\n" +
                         ",\n".join(f"    {n}" for n in sorted(partitions["state"])) + "\n)\n")
        if needed["detect"]:
            parts.append("\nfrom .stage_detect import (\n" +
                         ",\n".join(f"    {n}" for n in sorted(partitions["detect"])) + "\n)\n")
        if needed["stops"]:
            parts.append("\nfrom .stage_stops import (\n" +
                         ",\n".join(f"    {n}" for n in sorted(partitions["stops"])) + "\n)\n")
        if needed["position"]:
            parts.append("\nfrom .stage_position import (\n" +
                         ",\n".join(f"    {n}" for n in sorted(partitions["position"])) + "\n)\n")
        for cname in sorted(consts):
            if cname in partitions.get(part, set()):
                parts.append("\n" + const_src(cname) + "\n")
        for fname in sorted(defs, key=lambda x: defs[x].lineno):
            if fname in partitions.get(part, set()):
                parts.append("\n" + src(fname) + "\n")
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write("".join(parts))
        print(f"✅ 写出 {filename} ({len(''.join(parts).splitlines())} 行)")

    shutil.copyfile(SRC, SRC + ".bak")
    print(f"📦 已备份原文件 -> {SRC}.bak")

    write_module("stage_state.py", "Stage state persistence + portfolio correlation (leaf).", "state")
    write_module("stage_detect.py", "Stage detection engine.", "detect")
    write_module("stage_stops.py", "Stop loss / exit computation.", "stops")
    write_module("stage_position.py", "Position evaluation + scoring + take-profit.", "position")

    # facade
    facade = ['"""Stage positioning facade: re-export of all split submodules."""\n', import_block]
    for part, prefix in [("state", "stage_state"), ("detect", "stage_detect"),
                         ("stops", "stage_stops"), ("position", "stage_position")]:
        names = sorted(partitions[part])
        if names:
            facade.append(f"\nfrom .{prefix} import (\n" +
                          ",\n".join(f"    {n}" for n in names) + "\n)\n")
    with open(SRC, "w", encoding="utf-8") as f:
        f.write("".join(facade))
    print(f"✅ 写出 stage_positioning.py (facade, {len(''.join(facade).splitlines())} 行)")


if __name__ == "__main__":
    main()
