"""五档盘口分析 — 用于 t0-trader 盯盘验证支撑/阻力

从 mootdx 提供的买一-买五、卖一-卖五挂单数据生成盘口信号。
"""
from __future__ import annotations

from typing import Any


def analyze(order_book: dict[str, Any] | None) -> dict[str, Any]:
    """分析盘口，返回信号摘要

    Returns：
        {"imbalance": 1.5, "direction": "buy_strong", "walls": {...}, "line": "..."}
    """
    if not order_book:
        return {"imbalance": 0, "direction": "none", "walls": {}, "line": "盘口数据缺失"}

    bid_total = int(order_book.get("bid_total", 0))
    ask_total = int(order_book.get("ask_total", 0))
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])

    ratio = round(bid_total / ask_total, 2) if ask_total > 0 else 99

    if ratio >= 1.5:
        direction = "buy_strong"
    elif ratio >= 1.2:
        direction = "buy_lean"
    elif ratio <= 0.5:
        direction = "sell_strong"
    elif ratio <= 0.8:
        direction = "sell_lean"
    else:
        direction = "balanced"

    walls = _find_walls(bids, asks)

    line = _build_line(ratio, direction, walls)

    return {
        "imbalance": ratio,
        "direction": direction,
        "walls": walls,
        "line": line,
    }


def _find_walls(bids: list[dict], asks: list[dict]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not bids:
        return result

    avg_bid_vol = sum(b["volume"] for b in bids) / len(bids)
    avg_ask_vol = sum(a["volume"] for a in asks) / len(asks) if asks else 0

    for b in bids:
        if b["volume"] >= avg_bid_vol * 2 and b["volume"] >= 1000:
            result["support_wall"] = {"price": b["price"], "volume": b["volume"]}
            break

    for a in asks:
        if a["volume"] >= avg_ask_vol * 2 and a["volume"] >= 1000:
            result["resistance_wall"] = {"price": a["price"], "volume": a["volume"]}
            break

    return result


def _build_line(ratio: float, direction: str, walls: dict) -> str:
    parts = []

    if direction == "buy_strong":
        parts.append(f"买盘强：买盘/卖盘 {ratio:.1f} 倍")
    elif direction == "buy_lean":
        parts.append(f"买盘偏强：买盘/卖盘 {ratio:.1f} 倍")
    elif direction == "sell_strong":
        parts.append(f"卖盘强：买盘/卖盘 {ratio:.1f} 倍")
    elif direction == "sell_lean":
        parts.append(f"卖盘偏强：买盘/卖盘 {ratio:.1f} 倍")
    else:
        parts.append(f"买卖均衡：买盘/卖盘 {ratio:.1f} 倍")

    sw = walls.get("support_wall")
    rw = walls.get("resistance_wall")

    if sw:
        parts.append(f"买一 {sw['price']} 有 {sw['volume']} 手护盘")

    if rw:
        parts.append(f"卖一 {rw['price']} 有 {rw['volume']} 手压单")

    if sw and not rw:
        parts.append("→ 下方支撑有效")
    elif rw and not sw:
        parts.append("→ 上方阻力较重")
    elif sw and rw:
        parts.append("→ 短期胶着")

    return "，".join(parts)
