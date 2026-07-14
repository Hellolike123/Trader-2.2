#!/usr/bin/env python3
"""
一次脚本：把 wyckoff_core.py 行为保持地拆为
  wyckoff_events.py  (叶子事件探测器)
  wyckoff_phase.py   (相位状态机 + 持久化常量)
  wyckoff_core.py    (facade：保留 5 个公开函数 + 全量 re-export)

方法：ast 按函数名精确提取，不靠行号。先校验依赖无环再落盘。
可复跑：先备份原文件为 .bak。
"""
import ast
import os
import shutil
import sys

SRC = "02-共享模块-shared/trader_shared/wyckoff_core.py"
OUT_DIR = "02-共享模块-shared/trader_shared"

EVENTS = [
    "_spring_breach_level", "_price_pos_pct", "_is_bc_high_position", "_is_frozen_board",
    "_board_vol_scale", "_is_trading_range", "_compute_dynamic_support",
    "_detect_buying_climax", "_detect_selling_climax", "_detect_sign_of_weakness",
    "_detect_spring", "_detect_upthrust", "_detect_volume_divergence", "_detect_ar",
    "_detect_sos", "_detect_st", "_detect_lps", "_detect_lpsy",
    "_detect_effort_vs_result", "_detect_compression", "_detect_trend_pullback",
]
PHASE = [
    "_scan_for_signal", "_detect_phase", "_phase_key",
    "_load_phase_state", "_save_phase_state", "_transition_phase",
]
CORE = [
    "wyckoff_analysis", "wyckoff_strategy", "wyckoff_strategy_midline",
    "calculate_wyckoff_score", "format_wyckoff_oneline",
]

# 层级（数字越小越上游 / 越叶子）
LEVEL = {"events": 0, "phase": 1, "core": 2}


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    # 顶层函数
    funcs = {}
    first_def_line = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
            if first_def_line is None or node.lineno < first_def_line:
                first_def_line = node.lineno

    # 顶层常量（简单 Name 赋值）
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node

    all_names = set(funcs) | set(consts)
    partitions = {"events": set(EVENTS), "phase": set(PHASE), "core": set(CORE)}
    # 常量归属：_WYCKOFF_PHASE_FILE / _PHASE_ORDER -> phase
    for cname in consts:
        partitions["phase"].add(cname)

    # 校验：分区覆盖且无遗漏
    covered = set().union(*partitions.values())
    missing = all_names - covered
    overlap = covered - all_names
    assert not missing, f"未分配函数/常量: {missing}"
    assert not overlap, f"分配到不存在的名字: {overlap}"

    # 依赖边分析：对每个函数，找其引用的内部名（call 或 引用）
    edges = []  # (caller_part, callee_part, caller, callee)
    name2part = {}
    for part, names in partitions.items():
        for n in names:
            name2part[n] = part

    def referenced_names(func_node):
        refs = set()
        for n in ast.walk(func_node):
            if isinstance(n, ast.Name) and n.id in all_names:
                refs.add(n.id)
        return refs

    for fname, fnode in funcs.items():
        fpart = name2part[fname]
        for ref in referenced_names(fnode):
            rpart = name2part[ref]
            if rpart != fpart:
                edges.append((fpart, rpart, fname, ref))

    # 校验无环：禁止上游依赖下游（caller_level < callee_level）
    forbidden = [(c, r, fn, rn) for (c, r, fn, rn) in edges if LEVEL[c] < LEVEL[r]]
    if forbidden:
        print("❌ 发现禁止的依赖边（上游→下游，会成环）：")
        for c, r, fn, rn in forbidden:
            print(f"   {c}::{fn}  ->  {r}::{rn}")
        sys.exit(1)

    print(f"✅ 依赖校验通过。函数 {len(funcs)} 个，常量 {len(consts)} 个，跨分区边 {len(edges)} 条（均下游→上游，合法）")
    for c, r, fn, rn in edges:
        print(f"   {c}::{fn}  ->  {r}::{rn}")

    # 组装各 submodule 内容
    import_block = "".join(lines[: first_def_line - 1])

    def func_src(name):
        return ast.get_source_segment(source, funcs[name])

    def const_src(name):
        return ast.get_source_segment(source, consts[name])

    def write_module(filename, doc, part, need_events_import, need_phase_import):
        parts = []
        parts.append(f'"""{doc}"""\n')
        parts.append(import_block)
        # 跨分区相对 import（放在 import block 之后）
        if need_events_import:
            names = sorted(partitions["events"])
            parts.append("\nfrom .wyckoff_events import (\n")
            parts.append(",\n".join(f"    {n}" for n in names))
            parts.append("\n)\n")
        if need_phase_import:
            names = sorted(partitions["phase"] - {"events"})  # 避免自 import
            names = sorted(partitions["phase"])
            parts.append("\nfrom .wyckoff_phase import (\n")
            parts.append(",\n".join(f"    {n}" for n in names))
            parts.append("\n)\n")
        # 本分区常量
        for cname in sorted(consts):
            if cname in partitions[part]:
                parts.append("\n" + const_src(cname) + "\n")
        # 本分区函数
        for fname in sorted(funcs, key=lambda x: funcs[x].lineno):
            if fname in partitions[part]:
                parts.append("\n" + func_src(fname) + "\n")
        out = "".join(parts)
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(out)
        print(f"✅ 写出 {filename} ({len(out.splitlines())} 行)")

    # 备份原文件
    shutil.copyfile(SRC, SRC + ".bak")
    print(f"📦 已备份原文件 -> {SRC}.bak")

    # events：叶子，无跨分区 import
    write_module("wyckoff_events.py", "Wyckoff event detectors (leaf).", "events",
                 need_events_import=False, need_phase_import=False)
    # phase：依赖 events
    write_module("wyckoff_phase.py", "Wyckoff phase state machine + persistence.", "phase",
                 need_events_import=True, need_phase_import=False)
    # facade：保留 CORE 函数 + re-export 全部 moved 名
    facade_parts = []
    facade_parts.append('"""Wyckoff core facade: public API + re-export of split submodules."""\n')
    facade_parts.append(import_block)
    facade_parts.append("\nfrom .wyckoff_phase import (\n")
    facade_parts.append(",\n".join(f"    {n}" for n in sorted(partitions["phase"])))
    facade_parts.append("\n)\n")
    facade_parts.append("\nfrom .wyckoff_events import (\n")
    facade_parts.append(",\n".join(f"    {n}" for n in sorted(partitions["events"])))
    facade_parts.append("\n)\n")
    for fname in sorted(funcs, key=lambda x: funcs[x].lineno):
        if fname in partitions["core"]:
            facade_parts.append("\n" + func_src(fname) + "\n")
    with open(SRC, "w", encoding="utf-8") as f:
        f.write("".join(facade_parts))
    print(f"✅ 写出 wyckoff_core.py (facade, {len(''.join(facade_parts).splitlines())} 行)")


if __name__ == "__main__":
    main()
