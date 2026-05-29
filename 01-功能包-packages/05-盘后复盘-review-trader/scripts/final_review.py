#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
for _p in (
    _ROOT / "01-功能包-packages" / "05-盘后复盘-review-trader" / "scripts",
    _ROOT / "02-共享模块-shared" / "01-行情数据-market-data",
    _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate",
    _ROOT / "02-共享模块-shared",
    _ROOT / "02-共享模块-shared" / "03-输出校验-contracts",
    _ROOT / "02-共享模块-shared" / "scripts",
):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from review_compare import run_compare, run_compare_recent
from review_single import run_single
from validate_output import validate


def parse_holding(value: str) -> tuple[str, float]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("--holding must use 股票:成本价")
    name, cost_text = value.split(":", 1)
    try:
        cost = float(cost_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--holding cost must be numeric") from exc
    return name, cost


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate review-trader single review or multi-stock comparison.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", help="A-share name or code for single-stock review")
    group.add_argument("--compare", nargs="+", help="Compare 2-5 A-share names/codes")
    group.add_argument("--compare-recent", action="store_true", help="Compare recently reviewed stocks from cache")
    parser.add_argument("--cost", type=float, help="Optional cost for --target")
    parser.add_argument("--holding", action="append", type=parse_holding, default=[], help="Optional compare holding: 股票:成本价")
    parser.add_argument("--date", help="Optional trade date YYYY-MM-DD")
    parser.add_argument("--session", choices=["close", "midday"], default="close", help="Review session for --target; close is after-close, midday is noon review")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.target:
            text = run_single(args.target, cost=args.cost, trade_date=args.date, output=args.output, session=args.session)
        elif args.compare:
            if not 2 <= len(args.compare) <= 5:
                raise RuntimeError("--compare requires 2-5 stocks")
            costs = {name: cost for name, cost in args.holding}
            text = run_compare(args.compare, costs=costs, trade_date=args.date, output=args.output)
        elif args.compare_recent:
            text = run_compare_recent(output=args.output)
        else:
            raise RuntimeError("no command specified")
    except RuntimeError:
        raise
    except Exception as exc:
        print(f"Review Trader skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "markdown":
        errors = validate(text)
        if errors:
            print("Review Trader generated invalid output:", file=sys.stderr)
            for error in errors:
                print(error, file=sys.stderr)
            return 2
    print(text)
    
    if args.output == "markdown":
        try:
            run_postmarket_backfill_and_calibration()
        except Exception as e:
            print(f"\n📡 [AutoBackfill-Warn] 盘后回填与校准处理发生异常: {e}", file=sys.stderr)
            
    return 0


def run_postmarket_backfill_and_calibration() -> None:
    import json
    from pathlib import Path
    import time as _time

    trader_dir = Path.home() / ".trader"
    signals_file = trader_dir / "signals.jsonl"
    results_file = trader_dir / "signal_results.jsonl"

    if not signals_file.exists():
        _trigger_async_calibration()
        return

    # 1. 读取 signals.jsonl
    signals = []
    with open(signals_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    signals.append(json.loads(line))
                except Exception:
                    continue

    # 2. 读取 signal_results.jsonl，提取已平仓 ID
    outcomes = set()
    if results_file.exists():
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        sid = r.get("signal_id") or r.get("id")
                        if sid:
                            outcomes.add(sid)
                    except Exception:
                        continue

    # 3. 筛选活跃的买入触发信号
    active_signals = []
    for sig in signals:
        sid = sig.get("signal_id")
        sig_type = sig.get("signal_type")
        if sid and sig_type == "low_buy_triggered" and sid not in outcomes:
            active_signals.append(sig)

    if not active_signals:
        _trigger_async_calibration()
        return

    print("\n" + "=" * 60)
    print("💬 [信号平仓回填提示] 今日复盘结束，发现以下处于活跃状态的持仓信号：")
    print("=" * 60)

    skipped_all = False
    for sig in active_signals:
        if skipped_all:
            break

        symbol = sig.get("symbol", "")
        trade_date = sig.get("trade_date", "")
        trigger = sig.get("trigger") or {}
        entry_price = float(trigger.get("price") or sig.get("price") or 0.0)
        sid = sig.get("signal_id")

        if not entry_price:
            continue

        print(f"\n· 信号ID: {sid[:8]}... | 股票: {symbol} | 买入日期: {trade_date} | 买入均价: {entry_price:.2f}元")
        user_input = input("👉 如果您已实盘平仓退出，请输入平仓成交价（例如 59.33）；\n   如果您未操作（继续作为模拟盘在后台自动跟踪跑完），请直接按回车；\n   跳过后续所有请输入 skip: ").strip()

        if user_input.lower() == "skip":
            skipped_all = True
            print("➔ 已跳过后续所有活跃信号。")
            break

        if not user_input:
            print("➔ 未操作，该信号将继续作为模拟盘在后台自动跟踪。")
            continue

        try:
            exit_price = float(user_input)
            pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)
            won = pnl_pct > 0
            
            result_record = {
                "signal_id": sid,
                "symbol": symbol,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return_pct": pnl_pct,
                "outcome": "win" if won else "loss",
                "source": "manual_backfill",
                "timestamp": int(_time.time())
            }

            # 原子写入 signal_results.jsonl
            tmp_file = results_file.with_suffix(".tmp")
            results_file.parent.mkdir(parents=True, exist_ok=True)
            
            existing_lines = []
            if results_file.exists():
                existing_lines = results_file.read_text(encoding="utf-8").splitlines()
            
            with open(tmp_file, "w", encoding="utf-8") as f:
                for line in existing_lines:
                    if line.strip():
                        f.write(line + "\n")
                f.write(json.dumps(result_record, ensure_ascii=False) + "\n")
            
            tmp_file.replace(results_file)
            print(f"✅ 成功记录真实平仓！退出价格: {exit_price:.2f}元，收益率: {pnl_pct:+.2f}%")

        except ValueError:
            print("❌ 输入格式错误，平仓价必须为数字，已跳过该信号。")

    print("\n" + "=" * 60)
    _trigger_async_calibration()


def _trigger_async_calibration() -> None:
    import sys
    import subprocess
    from pathlib import Path
    
    script_path = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "scripts" / "self_calibration.py"
    if script_path.exists():
        try:
            subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
            print("📡 [AutoCalibration] 已在后台异步拉起自校准参数引擎。")
        except Exception as e:
            print(f"📡 [AutoCalibration-Warn] 后台自校准启动失败: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
