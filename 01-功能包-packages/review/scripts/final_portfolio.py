#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portfolio_run import build_portfolio, build_snapshot_portfolio, load_snapshot
from portfolio_validate_output import validate

# Optional monkeypatch override (None → live trader_paths registry).
POSITIONS_PATH: Path | None = None


def _positions_path() -> Path:
    """Runtime path (honors TRADER_ROOT); tests may monkeypatch POSITIONS_PATH."""
    override = globals().get("POSITIONS_PATH")
    if isinstance(override, Path):
        return override
    from trader_shared.trader_paths import path as _tp

    return _tp("positions_portfolio")


def _dual_write_holdings_row(row: dict, *, clear: bool = False) -> None:
    """Dual-write portfolio row into holdings SSOT when a symbol/code is present."""
    try:
        from trader_shared.holdings import clear_holding, upsert_holding
    except Exception:
        return
    code = row.get("symbol") or row.get("code") or row.get("ts_code")
    if not code:
        return  # name-only: cannot map into holdings SSOT without inventing codes
    sym = str(code)
    if clear:
        try:
            clear_holding(sym)
        except Exception:
            pass
        return
    try:
        upsert_holding(
            sym,
            cost=float(row.get("cost") or 0),
            shares=int(row.get("shares") or 0),
            name=str(row.get("name") or ""),
            source="portfolio",
        )
    except Exception:
        pass


def _holdings_ssot_as_rows() -> list[dict]:
    """Prefer holdings SSOT when present; map to portfolio row shape."""
    try:
        from trader_shared.holdings import list_holdings

        rows = []
        for sym, rec in list_holdings().items():
            if not isinstance(rec, dict):
                continue
            rows.append(
                {
                    "name": str(rec.get("name") or sym),
                    "shares": int(rec.get("shares") or 0),
                    "cost": float(rec.get("cost") or 0),
                    "symbol": sym,
                }
            )
        return rows
    except Exception:
        return []


def load_all() -> dict:
    p = _positions_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"holdings": [], "account": {}}


def save_all(data: dict) -> None:
    p = _positions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_positions() -> list[dict]:
    """Merge legacy positions.json with holdings SSOT.

    - Name-only legacy rows are never dropped (and never get invented codes).
    - Coded legacy rows get cost/shares overlaid from holdings when present.
    - Holdings-only symbols (e.g. from T0) are appended.
    """
    legacy = [dict(r) for r in (load_all().get("holdings") or []) if isinstance(r, dict)]
    ssot = _holdings_ssot_as_rows()
    if not ssot:
        return legacy

    by_bare: dict[str, dict] = {}
    name_only_names: set[str] = set()
    for row in legacy:
        code = row.get("symbol") or row.get("code") or row.get("ts_code")
        if code:
            by_bare[str(code).split(".")[0]] = row
        else:
            name = str(row.get("name") or "")
            if name:
                name_only_names.add(name)

    extras: list[dict] = []
    for sr in ssot:
        sym = str(sr.get("symbol") or "")
        bare = sym.split(".")[0] if sym else ""
        name = str(sr.get("name") or "")
        if bare and bare in by_bare:
            by_bare[bare]["cost"] = sr.get("cost", by_bare[bare].get("cost"))
            by_bare[bare]["shares"] = sr.get("shares", by_bare[bare].get("shares"))
            if not (by_bare[bare].get("symbol") or by_bare[bare].get("code")):
                by_bare[bare]["symbol"] = sym
            continue
        # Do not invent a code onto a name-only legacy row; skip duplicate by name.
        if name and name in name_only_names:
            continue
        extras.append(sr)

    out: list[dict] = []
    for row in legacy:
        code = row.get("symbol") or row.get("code") or row.get("ts_code")
        if code:
            bare = str(code).split(".")[0]
            out.append(by_bare.get(bare, row))
        else:
            out.append(row)
    out.extend(extras)
    return out


def load_account() -> dict:
    return load_all().get("account", {})


def save_positions(positions: list[dict]) -> None:
    data = load_all()
    data["holdings"] = positions
    save_all(data)
    # Dual-write rows that carry a symbol/code
    for row in positions:
        if isinstance(row, dict):
            _dual_write_holdings_row(row)


def find_position(positions: list[dict], name: str) -> int | None:
    for i, p in enumerate(positions):
        if p.get("name") == name:
            return i
    return None


def record_buy(name: str, shares: int, cost: float, symbol: str | None = None) -> dict:
    positions = load_positions()
    idx = find_position(positions, name)
    if idx is not None:
        old = positions[idx]
        total_shares = old.get("shares", 0) + shares
        total_cost = old.get("cost", 0) * old.get("shares", 0) + cost * shares
        avg_cost = round(total_cost / total_shares, 2) if total_shares else cost
        row = {"name": name, "shares": total_shares, "cost": avg_cost}
        code = symbol or old.get("symbol") or old.get("code")
        if code:
            row["symbol"] = code
        positions[idx] = row
    else:
        row = {"name": name, "shares": shares, "cost": cost}
        if symbol:
            row["symbol"] = symbol
        positions.append(row)
    save_positions(positions)
    _dual_write_holdings_row(positions[find_position(positions, name)])
    return {"name": name, "shares": shares, "cost": cost, "total_shares": positions[find_position(positions, name)]["shares"]}


def record_sell(name: str, shares: int) -> dict:
    positions = load_positions()
    idx = find_position(positions, name)
    if idx is None:
        return {"error": f"持仓中找不到 {name}"}
    old = positions[idx]
    remaining = old["shares"] - shares
    if remaining <= 0:
        cleared = positions.pop(idx)
        save_positions(positions)
        _dual_write_holdings_row(cleared, clear=True)
        return {"name": name, "sold": old["shares"], "remaining": 0}
    row = {"name": name, "shares": remaining, "cost": old["cost"]}
    if old.get("symbol") or old.get("code"):
        row["symbol"] = old.get("symbol") or old.get("code")
    positions[idx] = row
    save_positions(positions)
    _dual_write_holdings_row(row)
    return {"name": name, "sold": shares, "remaining": remaining}


def record_account(cash: float) -> dict:
    data = load_all()
    data["account"] = {"total_cash": cash}
    save_all(data)
    return {"total_cash": cash}


def holdings_to_snapshot(targets: list[str]) -> dict | None:
    data = load_all()
    holdings = [p for p in data.get("holdings", []) if p.get("name") in targets]
    if not holdings:
        return None
    snapshot = {"targets": targets, "holdings": holdings, "candidates": []}
    account = data.get("account", {})
    if account.get("total_cash"):
        snapshot["account"] = {
            "max_move_pct": 10,
            "total_position_pct": 60,
            "cash_pct": 40,
        }
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="仓位轮动 + 交易记录")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", nargs="+", help="股票名或代码")
    group.add_argument("--snapshot", help="JSON snapshot 文件路径")
    group.add_argument("--record", choices=["buy", "sell", "account"], help="记录买入/卖出/账户资金")
    parser.add_argument("--name", help="股票名")
    parser.add_argument("--shares", type=int, help="股数")
    parser.add_argument("--cost", type=float, help="成交价")
    parser.add_argument("--cash", type=float, help="账户总资金（元）")
    parser.add_argument("--max-total", type=int, default=80)
    parser.add_argument("--cash-floor", type=int, default=20)
    parser.add_argument("--main-cap", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # --- record mode ---
    if args.record:
        if args.record == "account":
            if not args.cash:
                print("--record account 需要 --cash <总资金>", file=sys.stderr)
                return 1
            result = record_account(args.cash)
            print(f"已记录：账户总资金 {result['total_cash']:.0f} 元")
            return 0
        if not args.name or not args.shares:
            print("--record buy/sell 需要 --name 和 --shares", file=sys.stderr)
            return 1
        if args.record == "buy":
            cost = args.cost or 0
            result = record_buy(args.name, args.shares, cost)
            print(f"已记录：买入 {result['name']} {result['shares']} 股")
            print(f"总持仓：{result['total_shares']} 股")
        elif args.record == "sell":
            result = record_sell(args.name, args.shares)
            if "error" in result:
                print(result["error"], file=sys.stderr)
                return 1
            print(f"已记录：卖出 {result['name']} {result['sold']} 股")
            print(f"剩余：{result['remaining']} 股")
        return 0

    # --- build mode ---
    try:
        if args.snapshot:
            markdown = build_snapshot_portfolio(
                load_snapshot(args.snapshot),
                max_total=args.max_total,
                cash_floor=args.cash_floor,
            )["portfolio_markdown"]
        else:
            positions = load_positions()
            # 用 provider 把 targets 转成 stock name，再用 name 匹配持仓
            from trader_shared.data_provider import get_provider
            provider = get_provider()
            target_names = {}
            for t in args.targets:
                try:
                    sec = provider.resolve_security(t)
                    quote = provider.fetch_quote(sec)
                    name = quote.get("name") or t
                    target_names[name] = t
                    target_names[sec.ts_code] = t
                except Exception:
                    target_names[t] = t
            holdings = {p["name"]: p for p in positions if p.get("name") in target_names}
            # 也检查 symbol 匹配
            for p in positions:
                pn = p.get("name", "")
                if pn not in holdings and p.get("symbol"):
                    if p["name"] in target_names:
                        holdings[pn] = p
            markdown = build_portfolio(
                args.targets,
                holdings=holdings or None,
                max_total=args.max_total,
                cash_floor=args.cash_floor,
                main_cap=args.main_cap,
            )["portfolio_markdown"]
    except Exception as exc:
        print(f"轮动仓位失败：{exc}", file=sys.stderr)
        return 1

    errors = validate(markdown)
    if errors:
        print("输出校验失败：", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
