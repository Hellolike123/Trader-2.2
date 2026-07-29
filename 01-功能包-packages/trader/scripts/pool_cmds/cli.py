"""Thin CLI for trader pool — argparse + dispatch only."""
from __future__ import annotations

import argparse
import sys

from pool_cmds import service as svc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Trader Pool candidate workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("analyze", "add", "add-pending"):
        item = sub.add_parser(command)
        item.add_argument("--target", required=True)
        item.add_argument("--offline", action="store_true")
    sub.add_parser("watch")
    sub.add_parser("list")
    sub.add_parser("show-pending")
    sub.add_parser("plan")
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--target", help="只刷新指定票（名称或代码），默认全池")
    sub.add_parser("rank")
    sub.add_parser("reconcile")
    sub.add_parser("add-last")
    review = sub.add_parser("review")
    review.add_argument("--offline", action="store_true")
    remove = sub.add_parser("remove")
    remove.add_argument("--target", required=True)
    confirm = sub.add_parser("confirm-to-pool")
    confirm.add_argument("--target", required=True)
    sub.add_parser("archive-exited")
    compare = sub.add_parser("compare")
    compare.add_argument("--targets", nargs="+", required=True)
    quick = sub.add_parser("quick-add")
    quick.add_argument("--target", required=True)
    quick.add_argument("--offline", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        from trader_shared.tushare_client import bypass_http_proxy_for_market

        bypass_http_proxy_for_market()
    except Exception:
        pass

    args = parse_args(argv)
    handlers = {
        "analyze": svc.cmd_analyze,
        "add": svc.cmd_add,
        "list": svc.cmd_list,
        "show-pending": svc.cmd_show_pending,
        "add-pending": svc.cmd_add_pending,
        "confirm-to-pool": svc.cmd_confirm_to_pool,
        "compare": svc.cmd_compare,
        "plan": svc.cmd_plan,
        "rank": svc.cmd_rank,
        "refresh": svc.cmd_refresh,
        "reconcile": svc.cmd_reconcile,
        "add-last": svc.cmd_add_last,
        "review": svc.cmd_review,
        "watch": svc.cmd_watch,
        "remove": svc.cmd_remove,
        "archive-exited": svc.cmd_archive_exited,
        "quick-add": _cmd_quick_add,
    }
    try:
        return handlers[args.command](args)
    except Exception as exc:
        print(f"trader pool failed: {exc}", file=sys.stderr)
        return 1


def _cmd_quick_add(args: argparse.Namespace) -> int:
    result = svc.quick_add(args.target, offline=args.offline)
    if result.get("ok"):
        rec = result.get("record", {})
        print(
            f"入池成功: {rec.get('target')} | 评分{rec.get('total_score')} | "
            f"阶段{rec.get('major_stage')} | 状态{rec.get('status')}"
        )
        return 0
    print(f"入池拒绝: {result.get('reason')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
