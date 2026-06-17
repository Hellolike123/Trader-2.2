#!/usr/bin/env python3
"""每日简报（daily-briefing）— 从大量候选池中自动分析、排序、分层。

用法：
    # 刷新选股池
    python3 briefing.py

    # 只分析指定票
    python3 briefing.py --watch A B C

    # 分析候选文件
    python3 briefing.py --candidates candidates.json

    # 刷新全池数据
    python3 briefing.py --refresh

    # 快速分析并加入池
    python3 briefing.py --candidate A --add
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure the project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "02-共享模块-shared"))
sys.path.insert(0, str(PROJECT_ROOT / "01-功能包-packages" / "trader" / "scripts"))

from trader_shared.light_data import to_float
from trader_shared.config import LOOKBACK_DAYS


# ── Paths ────────────────────────────────────────────────────────────────
POOLS_DIR = Path(os.path.expanduser("~/.trader"))
POOL_FILE = POOLS_DIR / "pool.json"
CANDIDATES_FILE = POOLS_DIR / "candidates.json"
LAST_PLAN_FILE = POOLS_DIR / "last_plan.json"


# ── Pool helpers ─────────────────────────────────────────────────────────
def load_pool() -> dict[str, Any]:
    """Load pool.json, returning empty dict if missing."""
    if not POOL_FILE.exists():
        return {"items": []}
    try:
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"items": []}


def save_pool(data: dict[str, Any]) -> None:
    """Save pool.json."""
    POOLS_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Build report (parallel) ─────────────────────────────────────────────
def _build_report_one(target: str) -> dict[str, Any]:
    """Run build_report for a single stock, returning result dict."""
    try:
        from run_analysis import build_report
        from final_pool import score_report
        report = build_report(target)
        scores = score_report(report)
        report.update(scores)
        return {"target": target, "success": True, "report": report}
    except Exception as exc:
        return {"target": target, "success": False, "error": str(exc), "report": None}


def build_reports_parallel(targets: list[str], max_workers: int = 8) -> list[dict[str, Any]]:
    """Build reports for multiple stocks in parallel."""
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_build_report_one, t): t for t in targets}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    return results


# ── Admission & Layering ─────────────────────────────────────────────────
# Reuse existing admission thresholds
ADMISSION_SCORE_EXECUTE = {
    "蓄势": 80,
    "主升": 60,
    "派发": 999,  # disabled for execution
    "衰退": 999,  # disabled
}
ADMISSION_SCORE_OBSERVE = {
    "蓄势": 70,
    "主升": 999,  # disabled (main-sheng is always execution)
    "派发": 70,
    "衰退": 999,  # disabled
}


def evaluate_admission(major_stage: str, total_score: int, current: float, stop: float) -> dict[str, Any]:
    """Evaluate admission and determine layer."""
    # Layer 1: stage screening
    if major_stage == "衰退":
        return {"result": "拒绝", "reason": "衰退期，直接拒绝入池。", "status": "放弃"}

    # Layer 2: score thresholds
    exec_threshold = ADMISSION_SCORE_EXECUTE.get(major_stage, 999)
    obs_threshold = ADMISSION_SCORE_OBSERVE.get(major_stage, 999)

    if total_score >= exec_threshold:
        status = "执行"
    elif total_score >= obs_threshold:
        status = "观察"
    else:
        return {"result": "待补", "reason": f"{major_stage}期但评分不足，暂不入池。", "status": "待补"}

    # Layer 3: risk check
    if stop > 0 and current <= stop:
        return {"result": "拒绝", "reason": "破防守位。", "status": "放弃"}

    return {"result": "入池", "reason": "结构成立，触发位和防守位清楚。", "status": status}


def layer_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Layer items into: 执行 / 观察 / 待补 / 放弃."""
    layers = {"执行": [], "观察": [], "待补": [], "放弃": []}
    for item in items:
        status = item.get("status", "放弃")
        if status in layers:
            layers[status].append(item)
        else:
            layers["放弃"].append(item)
    return layers


# ── Sorting ──────────────────────────────────────────────────────────────
def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort items by: status_rank > total_score > -atr_ratio > fusion_confidence."""
    status_rank = {"执行": 4, "观察": 3, "待补": 2, "放弃": 1}
    stage_priority = {"主升": 1, "蓄势": 2, "派发": 3, "衰退": 4}

    def _fusion_rank(fc: Any) -> int:
        if isinstance(fc, str):
            return {"high": 3, "medium": 2, "low": 1}.get(fc, 0)
        return 0

    return sorted(items, key=lambda item: (
        status_rank.get(item.get("status", "放弃"), 0),
        -stage_priority.get(item.get("major_stage", ""), 5),
        int(item.get("total_score") or 0),
        -float(item.get("atr_ratio") or 0),
        _fusion_rank(item.get("fusion_confidence", "")),
    ), reverse=True)


# ── Rendering ────────────────────────────────────────────────────────────
def _trade_hint(item: dict[str, Any]) -> str:
    """Generate a one-line trade hint for an item."""
    current = to_float(item.get("current")) or 0
    trigger = to_float(item.get("trigger") or item.get("confirm")) or 0
    defense = to_float(item.get("defense")) or 0
    support = to_float(item.get("support")) or 0

    if item.get("status") == "执行":
        if trigger > 0:
            return f"买 {support:.2f}-{trigger:.2f} ｜ 止损 {defense:.2f}"
        return f"买 {support:.2f} 附近 ｜ 止损 {defense:.2f}"
    elif item.get("status") == "观察":
        if trigger > 0:
            return f"关注 {trigger:.2f} 是否站稳，不买"
        return f"关注支撑位，等确认"
    elif item.get("status") == "待补":
        return f"评分不足，等转强（≥70）再观察"
    return "放弃"


def _format_layer_name(layer: str, count: int) -> str:
    emoji_map = {"执行": "🔥", "观察": "👀", "待补": "⏳", "放弃": "🚫"}
    desc_map = {
        "执行": "执行区（可交易）",
        "观察": "观察区（只看不买）",
        "待补": "待补区（评分不足）",
        "放弃": "放弃区",
    }
    emoji = emoji_map.get(layer, "⚪")
    desc = desc_map.get(layer, layer)
    return f"{emoji} {desc}（{count}只）"


def render_briefing(layers: dict[str, list[dict[str, Any]]], date_str: str) -> str:
    """Render the briefing output in微信-compatible format."""
    lines = []

    # Header
    total = sum(len(v) for v in layers.values())
    exec_count = len(layers["执行"])
    obs_count = len(layers["观察"])
    lines.append(f"📊 每日简报 — {date_str}")
    lines.append(f"容量 {total} ｜ 执行 {exec_count} ｜ 观察 {obs_count}")
    lines.append("")

    # Layer order: 执行 → 观察 → 待补 → 放弃
    layer_order = ["执行", "观察", "待补", "放弃"]
    rank_counters = {layer: 0 for layer in layer_order}

    for layer in layer_order:
        items = layers[layer]
        if not items:
            continue

        sorted_items = sort_items(items)
        layer_header = _format_layer_name(layer, len(sorted_items))
        lines.append(layer_header)

        for item in sorted_items:
            rank_counters[layer] += 1
            rank = rank_counters[layer]
            name = item.get("name") or item.get("target", "?")
            score = item.get("total_score", 0)
            major_stage = item.get("major_stage", "")
            momentum = item.get("momentum", "")

            # Rank emoji
            if rank == 1:
                rank_emoji = "🥇"
            elif rank == 2:
                rank_emoji = "🥈"
            elif rank == 3:
                rank_emoji = "🥉"
            else:
                rank_emoji = f"{rank}."

            # Main line: rank + name + score + stage
            stage_label = f"{major_stage}+{momentum}" if major_stage else momentum
            lines.append(f"  {rank_emoji} {name} {score}分 {stage_label}")

            # Trade hint
            hint = _trade_hint(item)
            if hint:
                lines.append(f"    {hint}")

            # Admission reason for 待补/放弃
            if layer in ("待补", "放弃"):
                reason = item.get("admission_reason", "") or item.get("reason", "")
                if reason:
                    lines.append(f"    原因：{reason}")

            lines.append("")

    # Footer
    lines.append("---")
    lines.append("仓位纪律：执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")

    return "\n".join(lines)


# ── Candidates file ──────────────────────────────────────────────────────
def load_candidates(filepath: str | None = None) -> list[str]:
    """Load candidate stock identifiers from JSON file or stdin."""
    path = filepath or str(CANDIDATES_FILE)
    if not Path(path).exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "candidates" in data:
            return data["candidates"]
        return []
    except (json.JSONDecodeError, IOError):
        return []


# ── Main command ─────────────────────────────────────────────────────────
def cmd_briefing(args: argparse.Namespace) -> None:
    """Main briefing command."""
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Collect targets
    targets = set()
    refresh_requested = getattr(args, "refresh", False)
    quick_add = getattr(args, "candidate", None)
    add_to_pool = getattr(args, "add", False)

    # 1. Pool items
    if not getattr(args, "watch", None):
        pool = load_pool()
        for item in pool.get("items", []):
            if item.get("status", "") not in ("淘汰", "淘汰"):
                targets.add(item.get("target") or item.get("name", ""))

    # 2. Candidates
    if getattr(args, "candidates", None):
        candidates = load_candidates(args.candidates)
        for c in candidates:
            if isinstance(c, dict):
                targets.add(c.get("target") or c.get("name", ""))
            else:
                targets.add(str(c))

    # 3. Watch list
    if getattr(args, "watch", None):
        for w in args.watch:
            targets.add(w)

    # 4. Quick add
    if quick_add:
        targets.add(quick_add)

    if not targets:
        print("没有需要分析的标的。请提供 --watch 或 --candidates。")
        return

    target_list = sorted(targets)
    print(f"🔍 分析 {len(target_list)} 只标的...")

    # Build reports
    t0 = time.time()
    results = build_reports_parallel(target_list, max_workers=8)
    elapsed = time.time() - t0

    # Process results
    scored_items: list[dict[str, Any]] = []
    errors = []
    for r in results:
        if not r["success"]:
            errors.append(f"  {r['target']}: {r['error']}")
            continue
        report = r["report"]
        target = r["target"]
        name = report.get("name") or target
        symbol = report.get("symbol") or target

        # Extract key fields
        major_stage = report.get("major_stage", "") or ""
        momentum = report.get("momentum", "") or ""
        total_score = report.get("total_score", 0)
        current = to_float(report.get("current")) or 0
        confirm = to_float(report.get("confirm")) or 0
        stop = to_float(report.get("stop")) or 0

        # Evaluate admission
        admission = evaluate_admission(major_stage, total_score, current, stop)

        item = {
            "target": target,
            "name": name,
            "symbol": symbol,
            "major_stage": major_stage,
            "momentum": momentum,
            "total_score": total_score,
            "chanlun_score": report.get("chanlun_score", 0),
            "wyckoff_score": report.get("wyckoff_score", 0),
            "chip_score": report.get("chip_score", 0),
            "fusion_score": report.get("fusion_score", 0),
            "momentum_score": report.get("momentum_score", 0),
            "momentum_tag": report.get("momentum_tag", ""),
            "current": current,
            "trigger": to_float(report.get("trigger", 0)),
            "confirm": confirm,
            "support": to_float(report.get("support", 0)),
            "stop": stop,
            "defense": to_float(report.get("defense", 0)),
            "status": admission["status"],
            "admission_result": admission["result"],
            "admission_reason": admission["reason"],
            "atr14": report.get("atr14", 0),
            "atr_ratio": report.get("atr_ratio", 0),
            "fusion_action": (report.get("fusion") or {}).get("action", ""),
            "fusion_confidence": (report.get("fusion") or {}).get("confidence", ""),
            "fusion_score_val": report.get("fusion_score", 0),
            "one_liner": report.get("one_liner", ""),
            "trade_hint": _trade_hint({**report, "status": admission["status"]}),
        }
        scored_items.append(item)

    # Layer items
    layers = layer_items(scored_items)

    # Render
    output = render_briefing(layers, date_str)
    print(output)

    # Save last briefing
    POOLS_DIR.mkdir(parents=True, exist_ok=True)
    last_briefing = {
        "contract_version": "daily_briefing_v1",
        "date": date_str,
        "total_analyzed": len(target_list),
        "success": len(scored_items),
        "errors": len(errors),
        "layers": {k: len(v) for k, v in layers.items()},
        "executed_at": datetime.now().isoformat(),
    }
    with open(POOLS_DIR / "last_briefing.json", "w", encoding="utf-8") as f:
        json.dump(last_briefing, f, ensure_ascii=False, indent=2)

    # Quick add to pool
    if quick_add and add_to_pool:
        item = next((i for i in scored_items if i["target"] == quick_add), None)
        if item and item["status"] in ("执行", "观察"):
            pool = load_pool()
            # Check if already in pool
            existing = None
            for p in pool.get("items", []):
                if p.get("target") == quick_add or p.get("name") == quick_add:
                    existing = p
                    break
            if existing:
                existing.update(item)
            else:
                pool.setdefault("items", []).append(item)
            save_pool(pool)
            print(f"\n✅ {quick_add} 已加入选股池（{item['status']}）")

    # Show errors
    if errors:
        print(f"\n⚠️ {len(errors)} 只分析失败:")
        for e in errors:
            print(e)

    print(f"\n📊 完成：{len(scored_items)}/{len(target_list)} 只成功（{elapsed:.1f}s）")
    print(f"   执行 {len(layers['执行'])} 观察 {len(layers['观察'])} 待补 {len(layers['待补'])} 放弃 {len(layers['放弃'])}")


def main():
    parser = argparse.ArgumentParser(description="每日简报 — 从候选池中自动分析、排序、分层")
    parser.add_argument("--candidates", type=str, help="候选文件路径（JSON）")
    parser.add_argument("--watch", nargs="+", help="只分析指定标的")
    parser.add_argument("--refresh", action="store_true", help="刷新全池数据")
    parser.add_argument("--candidate", type=str, help="快速分析一只候选")
    parser.add_argument("--add", action="store_true", help="加入选股池（配合 --candidate）")
    parser.add_argument("--output", type=str, default="text", help="输出格式：text/markdown/json")
    parser.add_argument("--json", action="store_true", dest="use_json", help="JSON 输出")

    args = parser.parse_args()
    cmd_briefing(args)


if __name__ == "__main__":
    main()
