"""T0 台账管理：记录每笔 T 操作，统计累计盈亏和有效 T 比例。

数据存储在 ~/.trader/t0_ledger.jsonl（每行一条记录）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from t0_account import (
    DEFAULT_FEE_RATE,
    DEFAULT_STAMP_TAX_RATE,
    LEDGER_FILE,
    calc_new_cost,
    calc_net_edge,
    calc_round_trip_cost,
)


def record_t_trade(
    symbol: str,
    mode: str,
    sell_price: float,
    buy_price: float,
    shares: int,
    avg_cost_before: float,
    fee_rate: float = DEFAULT_FEE_RATE,
    stamp_tax_rate: float = DEFAULT_STAMP_TAX_RATE,
    note: str = "",
) -> dict[str, Any]:
    """记录一笔 T 操作，写入台账。正 T 先卖后买。"""
    trade_date = datetime.now().strftime("%Y-%m-%d")
    trade_time = datetime.now().strftime("%H:%M:%S")

    gross = (sell_price - buy_price) * shares
    cost = calc_round_trip_cost(buy_price, sell_price, shares, fee_rate, stamp_tax_rate)
    net_pnl = round(gross - cost, 2)
    new_cost = calc_new_cost(avg_cost_before, 0, sell_price, buy_price, shares)

    record = {
        "symbol": symbol,
        "trade_date": trade_date,
        "trade_time": trade_time,
        "mode": mode,
        "sell_price": round(sell_price, 2),
        "buy_price": round(buy_price, 2),
        "shares": shares,
        "gross_pnl": round(gross, 2),
        "fee": round(cost, 2),
        "net_pnl": net_pnl,
        "avg_cost_before": round(avg_cost_before, 4),
        "note": note,
    }

    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def load_ledger(symbol: str | None = None, days: int | None = None) -> list[dict[str, Any]]:
    """读取台账记录。symbol=None 读全部，days=None 读全部。"""
    if not LEDGER_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    cutoff_date = None
    if days:
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if symbol and rec.get("symbol") != symbol:
                continue
            if cutoff_date and rec.get("trade_date", "") < cutoff_date:
                continue
            records.append(rec)
    return records


def ledger_summary(symbol: str | None = None, days: int | None = None) -> dict[str, Any]:
    """统计台账汇总。"""
    records = load_ledger(symbol, days)
    if not records:
        return {
            "count": 0, "total_net_pnl": 0.0, "win_count": 0, "loss_count": 0,
            "win_rate": 0.0, "avg_pnl": 0.0, "total_fee": 0.0,
            "text": "暂无 T 记录",
        }

    total_net = sum(r.get("net_pnl", 0) for r in records)
    total_fee = sum(r.get("fee", 0) for r in records)
    win = [r for r in records if r.get("net_pnl", 0) > 0]
    loss = [r for r in records if r.get("net_pnl", 0) < 0]
    win_rate = len(win) / len(records) * 100 if records else 0
    avg_pnl = total_net / len(records) if records else 0

    return {
        "count": len(records),
        "total_net_pnl": round(total_net, 2),
        "win_count": len(win),
        "loss_count": len(loss),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(avg_pnl, 2),
        "total_fee": round(total_fee, 2),
        "text": (
            f"共 {len(records)} 笔 T，净盈亏 {'+' if total_net >= 0 else ''}{total_net:.2f}元，"
            f"胜率 {win_rate:.0f}%，累计费用 {total_fee:.2f}元"
        ),
    }


def format_ledger_line(rec: dict[str, Any]) -> str:
    """格式化单条台账记录为一行文本。"""
    pnl = rec.get("net_pnl", 0)
    sign = "+" if pnl >= 0 else ""
    return (
        f"{rec.get('trade_date', '--')} {rec.get('trade_time', '--:--')} "
        f"卖{rec.get('sell_price', 0):.2f} 买{rec.get('buy_price', 0):.2f} "
        f"{rec.get('shares', 0)}股 {sign}{pnl:.2f}元"
    )


def today_summary(symbol: str | None = None) -> dict[str, Any]:
    """今日 T 汇总。"""
    today = datetime.now().strftime("%Y-%m-%d")
    records = load_ledger(symbol)
    today_records = [r for r in records if r.get("trade_date") == today]
    if not today_records:
        return {"count": 0, "net_pnl": 0.0, "text": "今日未做 T"}
    total = sum(r.get("net_pnl", 0) for r in today_records)
    return {
        "count": len(today_records),
        "net_pnl": round(total, 2),
        "text": f"今日 {len(today_records)} 笔 T，{'+' if total >= 0 else ''}{total:.2f}元",
    }
