"""Pool commands — watch.py"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from pool_cmds.common import *  # noqa: F403

def cmd_watch(args: argparse.Namespace) -> int:
    """Monitor top pool items with live prices and proximity alerts."""
    pool = load_pool()
    items = sort_items(active_items(pool))
    if not items:
        print("选股池为空，无需盯盘")
        return 0

    # FIX-T-BIAS-148: always include ready/execution items beyond rank 3
    # so that high-risk stocks are never silently ignored.
    # Prefer lane==ready（分道 SSOT）；无 lane 时回退 status==执行（等价纳入）。
    def _watch_ready(it: dict[str, Any]) -> bool:
        lane = it.get("lane")
        if lane is not None and str(lane).strip() != "":
            return str(lane) == "ready"
        return it.get("status") == "执行"

    exec_items = [item for item in items if _watch_ready(item)]
    rank_items = [item for item in items if not _watch_ready(item)]
    top3 = rank_items[:3]
    for item in exec_items:
        if item not in top3:
            top3.append(item)
    now = datetime.now().strftime("%H:%M")

    all_alerts: list[str] = []

    for i, item in enumerate(top3, 1):
        name = item.get("name", "?")
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        defense = to_float(item.get("defense")) or 0
        trail = to_float(item.get("trailing_stop")) or 0
        if trail > 0:
            defense = max(defense, trail)
        support_raw = to_float(item.get("support")) or 0
        scene = str(item.get("scene") or "")
        status = str(item.get("status") or "?")

        # Try to get live quote
        change_pct = 0.0
        try:
            from trader_shared.light_data import fetch_quote, HttpClient, resolve_security
            sec = resolve_security(name)
            q = fetch_quote(sec, HttpClient())
            if q and to_float(q.get("current_price")):
                current = to_float(q.get("current_price"))
                change_pct = to_float(q.get("current_change_pct")) or 0.0
        except Exception:
            pass

        if current <= 0:
            continue

        # Dynamic threshold: ATR% × 2（比例），上限 3%。勿用 atr14（元）当比例。
        atr_ratio = to_float(item.get("atr_ratio"))
        atr14 = to_float(item.get("atr14")) or 0.0
        if (atr_ratio is None or atr_ratio <= 0) and atr14 > 0 and current > 0:
            atr_ratio = atr14 / current
        atr_ratio = float(atr_ratio or 0.0)
        thresh_pct = min(atr_ratio * 2, 0.03) if atr_ratio > 0 else 0.02

        stock_alerts: list[str] = []
        atr_note = f"（ATR {atr_ratio * 100:.1f}%）" if atr_ratio > 0 else ""

        # 1. Defense breach (highest priority)
        if defense > 0 and current < defense:
            stock_alerts.append("🛑 破防守位！跌破防守位" + atr_note)
        # 2. Near defense (within adaptive threshold)
        elif defense > 0 and current > defense:
            dist_def = abs(current - defense) / current * 100
            if dist_def < thresh_pct * 100:
                stock_alerts.append(f"⚠️ 靠近防守，距防守仅 {dist_def:.1f}%" + atr_note)
        # 3. Near trigger
        elif trigger > 0:
            dist_trig = abs(trigger - current) / current * 100
            if dist_trig < thresh_pct * 100:
                if current >= trigger:
                    stock_alerts.append("🟢 已到触发位附近" + atr_note)
                else:
                    stock_alerts.append(f"⚡ 距触发仅 {dist_trig:.1f}%" + atr_note)
        # 4. Near support — only alert if price genuinely breached (within 1% margin)
        if support_raw > 0 and current <= support_raw * 1.01:
            dist_sup = abs(current - support_raw) / current * 100
            if dist_sup < thresh_pct * 100:
                stock_alerts.append(f"📊 距支撑仅 {dist_sup:.1f}%" + atr_note)

        # Build output for this stock
        rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
        if stock_alerts:
            alert_line = " | ".join(stock_alerts)
            all_alerts.append(f"{rank_emoji} {name}  {current:.2f}（{change_pct:+.1f}%）  {alert_line}")
        else:
            action = action_summary_for_scene(scene)
            all_alerts.append(f"{rank_emoji} {name}  {current:.2f}（{change_pct:+.1f}%）  👉 {action}" + atr_note)

    # Print output
    print(f"📡 选股池盯盘 — {now} | Top3")
    print()
    for line in all_alerts:
        print(f"  {line}")

    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from run_analysis import build_report
    from concurrent.futures import ThreadPoolExecutor

    targets = [t.strip() for t in (args.targets or []) if t.strip()]
    if len(targets) < 2:
        print("至少需要两只股票做比较", file=sys.stderr)
        return 1
    # 并行分析：多只票的 build_report 互相独立，并行执行总耗时≈最慢一只。
    # build_report 内部已对单票的缠论/威科夫/动量做并行，这里再做一层票间并行。
    results: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(targets), 5)) as ex:
        future_to_target = {ex.submit(build_report, t): t for t in targets}
        for fut, t in future_to_target.items():
            try:
                results.append(fut.result())
            except Exception as exc:
                errors[t] = str(exc)
    for t, msg in errors.items():
        print(f"{t}：数据获取失败（{msg}）", file=sys.stderr)
    if len(results) < 2:
        print("至少需要两只股票数据成功才能比较", file=sys.stderr)
        return 1
    print(render_compare(results))
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    """视图调和：对比 pool 快照与实时行情，暴露不一致。"""
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    sorted_items = sort_items_unified(items)

    lines = ["📋 视图调和报告", ""]
    issues_found = 0

    for item in sorted_items:
        name = item.get("name", "?")
        item_lines = [f"{name}"]

        # 1. 触发价偏离检查
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        if current > 0 and trigger > 0:
            trigger_pct = (trigger - current) / current * 100
            if abs(trigger_pct) > 5:
                item_lines.append(f"  触发价 {trigger:.2f} vs 现价 {current:.2f}（偏离 {trigger_pct:+.0f}%）← 建议运行 pool refresh")
                issues_found += 1

        # 2. 价格过期检查
        fw = _price_freshness_warning(item)
        if fw:
            item_lines.append(f"  {fw}")
            issues_found += 1

        # 3. 阶段快照过期检查
        major_stage = str(item.get("major_stage") or "-")
        momentum = str(item.get("momentum") or "-")
        item_lines.append(f"  阶段快照：{major_stage}+{momentum}")

        if len(item_lines) > 1:
            lines.extend(item_lines)
            lines.append("")

    if issues_found == 0:
        lines.append("✅ 所有视图一致，无异常。")
    else:
        lines.append(f"共 {issues_found} 项不一致，建议运行 pool refresh 同步数据。")

    print("\n".join(lines))
    return 0

