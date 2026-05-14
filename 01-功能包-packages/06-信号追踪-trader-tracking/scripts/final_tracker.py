#!/usr/bin/env python3
"""Trader Tracking — 信号追踪面板
自动从 signals.jsonl 拉历史价格计算结果，输出信号准确率面板。

用法:
  python3 final_tracker.py           # 显示面板
  python3 final_tracker.py --check   # 先检查更新信号结果
  python3 final_tracker.py --stock 南网科技      # 单只
  python3 final_tracker.py --days 30           # 天数
  python3 final_tracker.py self_check          # 自检
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _p in (
    _ROOT / "02-共享模块-shared" / "01-行情数据-market-data",
    _ROOT / "02-共享模块-shared" / "03-输出校验-contracts",
    _ROOT / "02-共享模块-shared",
    _ROOT / "02-共享模块-shared" / "scripts",
    _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate",
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from signal_tracker import show_all, show_single, check_recent


def main() -> int:
    parser = argparse.ArgumentParser(description="Trader Tracking — 信号追踪面板")
    parser.add_argument("--check", action="store_true", help="先检查更新信号结果")
    parser.add_argument("--days", type=int, default=5, help="回溯 N 天")
    parser.add_argument("--stock", default=None, help="查看单只股票")
    args = parser.parse_args()

    # Handle subcommands from signal_tracker.py
    if hasattr(args, 'command') and args.command:
        from signal_tracker import main as tracker_main
        return tracker_main()

    try:
        if args.check:
            result = check_recent(args.days)
            n = result.get("updated", 0) if isinstance(result, dict) else result
            if n > 0:
                print(f"更新了 {n} 条信号结果。")
        if args.stock:
            text = show_single(args.stock, args.days)
        else:
            text = show_all(args.days)
    except Exception as exc:
        print(f"信号追踪失败：{exc}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
