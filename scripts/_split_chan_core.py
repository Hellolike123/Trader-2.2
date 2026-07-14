#!/usr/bin/env python3
"""一次脚本：把 chan_core.py 行为保持地拆为
  chan_geometry.py  (叶子几何构建)
  chan_structure.py (分类/置信/买卖点/背离)
  chan_core.py      (facade：公开引擎 API + 全量 re-export)

通用版：同时处理 FunctionDef 与 ClassDef（ChanlunEngine）。
方法：ast 按函数/类名精确提取；先校验依赖无环再落盘。
"""
import ast
import os
import shutil
import sys

SRC = "02-共享模块-shared/trader_shared/chan_core.py"
OUT_DIR = "02-共享模块-shared/trader_shared"

GEOMETRY = [
    "unwrap_chan", "_calc_macd", "handle_inclusion", "find_fractions",
    "_aggregate_bars", "_higher_level_trend", "build_strokes", "_valid_strokes",
    "_merge_char_element", "build_segments", "_merge_zones", "build_zones",
    "_has_entry_exit_segments", "_detect_unilateral",
]
STRUCTURE = [
    "_structure_conf_thresholds", "_structure_confidence", "classify_structure",
    "_stroke_macd_area", "_stroke_force_weaker", "_stroke_force_weaker_multi",
    "_stroke_force_not_much_stronger", "_check_macd_for_2nd_buy",
    "_check_macd_for_2nd_sell", "_zone_last_end_index",
    "detect_buy_points", "detect_sell_points", "detect_divergence",
]
CORE = [
    "_chanlun_compute", "chanlun_analysis", "ChanlunEngine",
    "_chan_json_default", "_chan_type_canonical", "chanlun_strategy",
    "chanlun_strategy_midline", "format_chanlun_theory_line",
]

LEVEL = {"geometry": 0, "structure": 1, "core": 2}


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    defs = {}  # name -> node (FunctionDef or ClassDef)
    first_def_line = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node
            if first_def_line is None or node.lineno < first_def_line:
                first_def_line = node.lineno

    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node

    all_names = set(defs) | set(consts)
    partitions = {"geometry": set(GEOMETRY), "structure": set(STRUCTURE), "core": set(CORE)}
    for cname in consts:
        partitions["structure"].add(cname)  # 常量路由由引用分析决定，先占位

    covered = set().union(*partitions.values())
    assert not (all_names - covered), f"未分配: {all_names - covered}"
    assert not (covered - all_names), f"分配到不存在的名字: {covered - all_names}"

    name2part = {}
    for part, names in partitions.items():
        for n in names:
            name2part[n] = part

    def referenced_names(node):
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in all_names}

    edges = []
    for fname, fnode in defs.items():
        fpart = name2part[fname]
        for ref in referenced_names(fnode):
            rpart = name2part[ref]
            if rpart != fpart:
                edges.append((fpart, rpart, fname, ref))

    forbidden = [(c, r, fn, rn) for (c, r, fn, rn) in edges if LEVEL[c] < LEVEL[r]]
    if forbidden:
        print("❌ 禁止的依赖边（上游→下游，会成环）：")
        for c, r, fn, rn in forbidden:
            print(f"   {c}::{fn}  ->  {r}::{rn}")
        sys.exit(1)
    print(f"✅ 依赖校验通过。def/class {len(defs)} 个，常量 {len(consts)} 个，跨分区边 {len(edges)} 条（均下游→上游）")
    for c, r, fn, rn in edges:
        print(f"   {c}::{fn}  ->  {r}::{rn}")

    # 收集全部顶层 prologue（import / try-except 配置导入 / 模块 docstring），
    # 不限于文件头部——chan_core 的配置导入在文件中部（unwrap_chan 之后）。
    prologue_parts = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Try)):
            prologue_parts.append(ast.get_source_segment(source, node))
        elif isinstance(node, ast.Expr) and isinstance(getattr(node.value, "value", None), str):
            prologue_parts.append(ast.get_source_segment(source, node))
    import_block = "\n".join(p for p in prologue_parts if p) + "\n"

    def src(name):
        return ast.get_source_segment(source, defs[name])

    def const_src(name):
        return ast.get_source_segment(source, consts[name])

    def write_module(filename, doc, part, need_geometry_import, need_structure_import):
        parts = [f'"""{doc}"""\n', import_block]
        if need_geometry_import:
            parts.append("\nfrom .chan_geometry import (\n")
            parts.append(",\n".join(f"    {n}" for n in sorted(partitions["geometry"])))
            parts.append("\n)\n")
        if need_structure_import:
            parts.append("\nfrom .chan_structure import (\n")
            parts.append(",\n".join(f"    {n}" for n in sorted(partitions["structure"])))
            parts.append("\n)\n")
        for cname in sorted(consts):
            if cname in partitions[part]:
                parts.append("\n" + const_src(cname) + "\n")
        for fname in sorted(defs, key=lambda x: defs[x].lineno):
            if fname in partitions[part]:
                parts.append("\n" + src(fname) + "\n")
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write("".join(parts))
        print(f"✅ 写出 {filename} ({len(''.join(parts).splitlines())} 行)")

    shutil.copyfile(SRC, SRC + ".bak")
    print(f"📦 已备份原文件 -> {SRC}.bak")

    write_module("chan_geometry.py", "Chan geometry builders (leaf).", "geometry",
                 need_geometry_import=False, need_structure_import=False)
    write_module("chan_structure.py", "Chan structure classification + buy/sell points + divergence.", "structure",
                 need_geometry_import=True, need_structure_import=False)

    facade = ['"""Chan core facade: public engine API + re-export of split submodules."""\n', import_block]
    facade.append("\nfrom .chan_structure import (\n")
    facade.append(",\n".join(f"    {n}" for n in sorted(partitions["structure"])))
    facade.append("\n)\n")
    facade.append("\nfrom .chan_geometry import (\n")
    facade.append(",\n".join(f"    {n}" for n in sorted(partitions["geometry"])))
    facade.append("\n)\n")
    for fname in sorted(defs, key=lambda x: defs[x].lineno):
        if fname in partitions["core"]:
            facade.append("\n" + src(fname) + "\n")
    with open(SRC, "w", encoding="utf-8") as f:
        f.write("".join(facade))
    print(f"✅ 写出 chan_core.py (facade, {len(''.join(facade).splitlines())} 行)")


if __name__ == "__main__":
    main()
