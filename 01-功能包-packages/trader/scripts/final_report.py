#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from run_analysis import build_report, build_signal
from trader_shared.report_core import render_single as render_markdown
from validate_output import validate
from trader_shared.fetchers import TencentFetcher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final Trader report.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    parser.add_argument("--output", choices=["markdown", "json", "signal-json", "alert-text", "watch"], default="markdown")
    parser.add_argument(
        "--write-signal",
        action="store_true",
        help="将 build_signal（含 allow_new_recommend）写入 ~/.trader/signals.jsonl；watch 模式下仅在触发告警时写",
    )
    parser.add_argument("--cost", type=float, default=0.0, help="Cost price for existing position (e.g., --cost 60.00)")
    return parser.parse_args()


def _maybe_write_signal(report: dict[str, Any], *, enabled: bool) -> None:
    """落盘决策字段，供决策体检分组。失败不阻断主输出。"""
    if not enabled:
        return
    try:
        from trader_shared.signal_store import append_signal

        append_signal(build_signal(report))
    except Exception as exc:
        print(f"⚠️ 信号落盘失败: {exc}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    # 单票保持区间套默认开启（30m×800 确认日线买点）；要省时再 TRADER_CHAN_NESTING=0
    try:
        from trader_shared.tushare_client import bypass_http_proxy_for_market

        bypass_http_proxy_for_market()
    except Exception:
        pass
    # DI: 创建 TencentFetcher 实例供下游使用
    fetcher = TencentFetcher()
    try:
        report = build_report(args.target, cost_price=args.cost)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        print(f"Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "alert-text":
        from run_analysis import generate_alert
        alert = generate_alert(report)
        if alert:
            print(alert)
        return 0

    if args.output == "signal-json":
        sig = build_signal(report)
        print(json.dumps(sig, ensure_ascii=False, indent=2, default=str))
        _maybe_write_signal(report, enabled=args.write_signal)
        return 0

    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        _maybe_write_signal(report, enabled=args.write_signal)
        return 0

    if args.output == "watch":
        from run_analysis import build_watch_alert
        alert_text = build_watch_alert(report, args.write_signal)
        print(alert_text)
        return 0

    # ── AI 事实表 (供 Hermes 解析，不展示给用户) ──
    # 在验证之前输出：即使 markdown 验证失败，AI 也能拿到 __FACTS__ 用于交叉校验。
    # NEVER_COMPUTE 字段显式写进 JSON，值设为 "数据不足"——
    # 避免 AI 在 CHECKLIST 里看到"数据不足"四个字的说明时误判数据已断裂。
    _NEVER_COMPUTE = (
        "risk_reward", "support_resistance_gap", "stop_distance",
        "take_pct", "confirm_distance", "ma_trend",
        "volume_ratio", "momentum_score",
    )
    _facts: dict[str, Any] = {}
    try:
        _facts = {
            "target": args.target,
            "cost": args.cost,
            "fetched_at": report.get("fetched_at"),
            "data_status": report.get("data_status"),
            "current": report.get("current"),
            "change_pct": report.get("change_pct"),
            "ma": report.get("ma_raw", {}),
            "support": report.get("support"),
            "resistance": report.get("resistance"),
            "confirm": report.get("confirm"),
            "stop": report.get("stop"),
            "take": report.get("take"),
            "atr14": report.get("atr14"),
            "atr_ratio": report.get("atr_ratio"),
            "state_label": report.get("state_label"),
            "scene": report.get("scene"),
            "fusion_action": (report.get("fusion") or {}).get("action", ""),
            "fusion_holding_hint": report.get("fusion_holding_hint", ""),
            "fusion_confidence": (report.get("fusion") or {}).get("confidence"),
            "fusion_weighted_score": (report.get("fusion") or {}).get("weighted_score"),
            "fusion_signals_detail": (report.get("fusion") or {}).get("signals_detail"),
            "market_env": (report.get("market_env") or {}).get("level") if isinstance(report.get("market_env"), dict) else "",
            "suggested_pct": (report.get("position_info") or {}).get("suggested_pct", 0),
            "suggested_pct_context": report.get("suggested_pct_context", ""),
            "has_position": report.get("has_position", False),
            "theory_fusion_conflict": report.get("theory_fusion_conflict", False),
        }
        for k in _NEVER_COMPUTE:
            _facts[k] = "数据不足"
        print("__FACTS__:" + json.dumps(_facts, ensure_ascii=False, default=str), file=sys.stderr)
    except Exception:
        _facts = {}
        for k in _NEVER_COMPUTE:
            _facts[k] = "数据不足"

    # ── 可用字段清单 (标记哪些字段可直接引用，防止 AI 自行计算 gap/ratio) ──
    _avail: list[str] = []
    _avail.append("AVAILABLE_RAW:")
    for k, v in sorted(_facts.items()):
        if v is not None and v != "":
            _avail.append(f"  {k}={json.dumps(v, default=str)}")
    _avail.append("NEVER_COMPUTE:")
    for k in _NEVER_COMPUTE:
        _avail.append(f"  {k} ← _facts['{k}'] 引用而非自行计算")
    print("__CHECKLIST__:" + "\n".join(_avail), file=sys.stderr)

    markdown = render_markdown(report)
    errors = validate(markdown, report)
    if errors:
        print("Trader generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        # #27 修复：验证失败时仍输出报告（验证错误记为警告，不阻断输出）
        # 之前 return 2 会跳过 print(markdown)，用户什么都看不到

    print(markdown)
    _maybe_write_signal(report, enabled=args.write_signal)

    # ── AI 事实表 (供 Hermes 解析，不展示给用户) ──
    # 上面已在验证前输出完整 facts（含 NEVER_COMPUTE），此处仅写 last_target。

    last_target_path = os.path.expanduser("~/.trader/last_target.txt")
    os.makedirs(os.path.dirname(last_target_path), exist_ok=True)
    with open(last_target_path, "w", encoding="utf-8") as f:
        f.write(args.target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
