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

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.signal_tracker import show_all, show_single, check_recent


def main() -> int:
    parser = argparse.ArgumentParser(description="Trader Tracking — 信号追踪面板")
    parser.add_argument("--check", action="store_true", help="先检查更新信号结果")
    parser.add_argument("--days", type=int, default=90, help="回溯 N 天（默认90天）")
    parser.add_argument("--stock", default=None, help="查看单只股票")
    args = parser.parse_args()

    # Handle subcommands from signal_tracker.py
    if hasattr(args, 'command') and args.command:
        from trader_shared.signal_tracker import main as tracker_main
        return tracker_main()

    try:
        # 1. 先执行 backfill（宽窗口 90 天），确保 signal_results.jsonl 有数据
        from trader_shared.signal_tracker import backfill
        bf_result = backfill(days_window=90)
        bf_updated = bf_result.get("updated", 0)
        if bf_updated > 0:
            print(f"已回补 {bf_updated} 条历史信号结果。")

        # 2. 再检查近期新结果（默认窗口放大到 90 天）
        result = check_recent(args.days if args.days else 90)
        n = result.get("updated", 0) if isinstance(result, dict) else result
        if args.check and n > 0:
            print(f"更新了 {n} 条信号结果。")

        # 3. 显示面板
        if args.stock:
            text = show_single(args.stock, args.days)
        else:
            text = show_all(args.days)

        # 4. 如果回补后结果为空，提示用户
        if "无有效结果" in text or "无结果" in text:
            print("\n💡 提示：当前无已结算信号，可尝试:")
            print("   python3 final_tracker.py --days 90    # 扩大回溯窗口")
            print("   python3 final_tracker.py self_check   # 自检数据完整性")
    except Exception as exc:
        print(f"信号追踪失败：{exc}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
