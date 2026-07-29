#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from monitor import recent_history, run_monitor
from t0_run import build_plan, render_markdown
from validate_output import validate
from trader_shared.fetchers import TencentFetcher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate the final T0 card.")
    parser.add_argument("--target", required=True, help="A-share name or code, for example 南网科技 or 688248")
    parser.add_argument("--monitor", action="store_true", help="Run monitor mode and only alert on state changes")
    parser.add_argument("--once", action="store_true", help="Run one monitor check for Hermes scheduled calls")
    parser.add_argument("--interval", type=int, default=3, help="Monitor interval in minutes for long-running mode")
    parser.add_argument("--cost", type=float, default=None, help="Optional holding cost for personalized alerts")
    parser.add_argument("--position", type=int, default=None, help="Optional base position shares for T-share sizing")
    parser.add_argument("--max-alerts", type=int, default=20, help="Stop long-running monitor after this many alerts")
    parser.add_argument("--verbose", action="store_true", help="Print no-alert status in monitor mode")
    parser.add_argument("--reset-cache", action="store_true", help="Clear cached state for this target before checking")
    parser.add_argument("--t-mode", choices=["cost_cut", "grid", "reduce"], default=None,
                        help="持仓纪律参考（需有底仓）：cost_cut/grid/reduce；不构成自动做 T 指令")
    parser.add_argument("--min-edge-pct", type=float, default=0.8,
                        help="Minimum net edge %% after fees to allow T (default: 0.8)")
    parser.add_argument("--cash", type=float, default=None,
                        help="Cash available for reverse T (倒T), in yuan or shares")
    parser.add_argument("--day-loss-pct", type=float, default=1.0,
                        help="Daily T loss limit %% of market value (default: 1.0)")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    # ledger subcommands
    parser.add_argument("--ledger", action="store_true", help="Show T0 ledger summary")
    parser.add_argument("--ledger-add", nargs=4, metavar=("SELL", "BUY", "SHARES", "COST"),
                        help="Record a T trade: --ledger-add SELL_PRICE BUY_PRICE SHARES AVG_COST")
    parser.add_argument("--ledger-days", type=int, default=None, help="Filter ledger by recent N days")
    parser.add_argument("--scale", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fetcher = TencentFetcher()

    # ── Ledger 子命令 ──
    if args.ledger or args.ledger_add:
        return _handle_ledger(args)

    # ── Monitor 模式 ──
    if args.monitor:
        try:
            return run_monitor(
                args.target,
                interval=args.interval,
                cost=args.cost,
                position=args.position,
                once=args.once,
                max_alerts=args.max_alerts,
                verbose=args.verbose,
                reset_cache=args.reset_cache,
            )
        except Exception as exc:
            print(f"T0 monitor cannot run in this environment: {exc}", file=sys.stderr)
            return 1

    # ── 标准卡片模式 ──
    try:
        plan = build_plan(args.target)

        # 注入账户层信息
        _inject_account(plan, args)

        markdown = render_markdown(plan)
    except Exception as exc:
        print(f"T0 skill cannot run in this environment: {exc}", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
    else:
        errors = validate(markdown)
        if errors:
            print("T0 generated invalid output:", file=sys.stderr)
            for error in errors:
                print(error, file=sys.stderr)
            return 2
        print(markdown)

    return 0


def _inject_account(plan: dict, args: argparse.Namespace) -> None:
    """将账户层信息注入 plan。优先 CLI 参数，其次 position.json。"""
    try:
        from t0_account import load_position, decide_t_mode, is_worth_t, calc_new_cost
    except ImportError:
        return

    symbol = plan.get("symbol") or plan.get("target", "")
    pos = load_position(symbol)

    # CLI 参数覆盖
    if args.cost is not None and pos:
        pos["avg_cost"] = args.cost
    elif args.cost is not None and not pos:
        pos = {"avg_cost": args.cost, "total_shares": args.position or 0, "has_cash": bool(args.cash)}
    if args.position is not None and pos:
        pos["total_shares"] = args.position
    if args.cash is not None and pos:
        pos["has_cash"] = args.cash > 0
    if args.t_mode and pos:
        pos["force_mode"] = args.t_mode

    if pos:
        current_price = plan.get("current_price", 0)
        t_info = decide_t_mode(pos, current_price)
        plan["t0_account"] = {
            "avg_cost": pos.get("avg_cost", 0),
            "total_shares": pos.get("total_shares", 0),
            "mode": t_info["mode"],
            "allow_reverse_t": t_info["allow_reverse_t"],
            "max_t_shares": t_info["max_t_shares"],
            "max_t_pct": t_info["max_t_pct"],
            "float_pnl_pct": t_info.get("float_pnl_pct", 0),
        }
        # 费后判断
        sell_obs = plan.get("sell", {}).get("observation_price")
        buy_obs = plan.get("buy", {}).get("observation_price")
        if sell_obs and buy_obs and sell_obs > buy_obs:
            worth = is_worth_t(sell_obs, buy_obs, args.min_edge_pct)
            plan["t0_account"]["worth_t"] = worth
        # 预估新成本
        avg_cost = pos.get("avg_cost", 0)
        if avg_cost > 0 and sell_obs and buy_obs:
            t_shares = t_info["max_t_shares"]
            if t_shares > 0:
                new_cost = calc_new_cost(avg_cost, pos.get("total_shares", 0), sell_obs, buy_obs, t_shares)
                plan["t0_account"]["new_cost_estimate"] = new_cost


def _handle_ledger(args: argparse.Namespace) -> int:
    """处理台账子命令。"""
    try:
        from t0_ledger import ledger_summary, load_ledger, record_t_trade, format_ledger_line, today_summary
    except ImportError:
        print("t0_ledger 模块不可用", file=sys.stderr)
        return 1

    if args.ledger_add:
        sell, buy, shares, cost = [float(x) for x in args.ledger_add]
        symbol = args.target
        rec = record_t_trade(
            symbol=symbol,
            mode=args.t_mode or "grid",
            sell_price=sell,
            buy_price=buy,
            shares=int(shares),
            avg_cost_before=cost,
        )
        print(f"已记录：{format_ledger_line(rec)}")
        return 0

    # 显示台账
    symbol = args.target if args.target else None
    today = today_summary(symbol)
    summary = ledger_summary(symbol, days=args.ledger_days)
    records = load_ledger(symbol, days=args.ledger_days)

    lines = [
        f"📋 T0 台账{' — ' + symbol if symbol else ''}",
        today["text"],
        summary["text"],
        "",
    ]
    if records:
        lines.append("最近记录：")
        for rec in records[-10:]:
            lines.append(f"  {format_ledger_line(rec)}")
    else:
        lines.append("暂无记录")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
