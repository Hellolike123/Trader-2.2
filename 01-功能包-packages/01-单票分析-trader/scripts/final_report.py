#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

from run_analysis import build_report, build_signal, render_markdown
from validate_output import validate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final Trader report.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    parser.add_argument("--output", choices=["markdown", "signal-json", "alert-text", "watch"], default="markdown")
    parser.add_argument("--write-signal", action="store_true", help="Write triggered signals to signals.jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target)
    except Exception as exc:
        print(f"Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "alert-text":
        from run_analysis import generate_alert
        alert = generate_alert(report)
        if alert:
            print(alert)
        return 0

    if args.output == "signal-json":
        markdown = render_markdown(report)
        print(json.dumps(build_signal(report), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.output == "watch":
        from run_analysis import build_watch_alert
        alert_text = build_watch_alert(report, args.write_signal)
        print(alert_text)
        return 0

    # ── AI 事实表 (供 Hermes 解析，不展示给用户) ──
    # 在验证之前输出：即使 markdown 验证失败，AI 也能拿到 __FACTS__ 用于交叉校验。
    _facts: dict[str, Any] = {}
    try:
        _facts = {
            "target": args.target,
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
            "fusion_confidence": (report.get("fusion") or {}).get("confidence"),
            "fusion_weighted_score": (report.get("fusion") or {}).get("weighted_score"),
            "fusion_signals_detail": (report.get("fusion") or {}).get("signals_detail"),
            "market_env": (report.get("market_env") or {}).get("level") if isinstance(report.get("market_env"), dict) else "",
        }
        print("__FACTS__:" + json.dumps(_facts, ensure_ascii=False, default=str), file=sys.stdout)
    except Exception:
        _facts = {}

    # ── 可用字段清单 (标记哪些字段可直接引用，防止 AI 自行计算 gap/ratio) ──
    _avail: list[str] = []
    _avail.append("AVAILABLE_RAW:")
    for k, v in sorted(_facts.items()):
        if v is not None and v != "":
            _avail.append(f"  {k}={json.dumps(v, default=str)}")
    _not_provided = []
    for k in ("risk_reward", "support_resistance_gap", "stop_distance", "take_pct",
              "confirm_distance", "ma_trend", "volume_ratio", "momentum_score"):
        _not_provided.append(k)
    _avail.append("NEVER_COMPUTE:")
    for k in _not_provided:
        _avail.append(f"  {k}  ← 脚本未提供此值，引用「数据不足」而非自行计算")
    print("__CHECKLIST__:" + "\n".join(_avail), file=sys.stdout)

    markdown = render_markdown(report)
    errors = validate(markdown)
    if errors:
        print("Trader generated invalid output:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)

    # ── AI 事实表 (供 Hermes 解析，不展示给用户) ──
    try:
        _facts = {
            "target": args.target,
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
            "fusion_action": (report.get("fusion") or {}).get("action", ""),
            "fusion_weighted_score": (report.get("fusion") or {}).get("weighted_score"),
            "market_env": (report.get("market_env") or {}).get("level") if isinstance(report.get("market_env"), dict) else "",
        }
        print("__FACTS__:" + json.dumps(_facts, ensure_ascii=False, default=str), file=sys.stdout)
    except Exception:
        pass

    last_target_path = os.path.expanduser("~/.trader/last_target.txt")
    os.makedirs(os.path.dirname(last_target_path), exist_ok=True)
    with open(last_target_path, "w", encoding="utf-8") as f:
        f.write(args.target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
