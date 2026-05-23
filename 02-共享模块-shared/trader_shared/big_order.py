from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from light_data import to_float


@dataclass(frozen=True)
class BigOrderEvent:
    time: str
    side: str
    hands: float | None
    amount_wan: float | None
    meaning: str
    level: str


def _bar_time(bar: dict[str, Any]) -> str:
    text = str(bar.get("time") or bar.get("date") or "")
    if " " in text:
        return text.split(" ", 1)[1][:5]
    if len(text) >= 16 and text[10] in {" ", "T"}:
        return text[11:16]
    return text[-8:-3] if ":" in text else ""


def _trade_hands(bar: dict[str, Any]) -> float | None:
    volume = to_float(bar.get("volume"))
    if volume is None:
        return None
    return round(volume / 100.0, 2)


def _trade_amount_wan(bar: dict[str, Any]) -> float | None:
    amount = to_float(bar.get("amount"))
    if amount is None:
        close = to_float(bar.get("close"))
        volume = to_float(bar.get("volume"))
        if close is None or volume is None:
            return None
        amount = close * volume
    return round(amount / 10000.0, 2)


def _direction(bar: dict[str, Any]) -> str:
    open_price = to_float(bar.get("open"))
    close_price = to_float(bar.get("close"))
    if open_price is None or close_price is None:
        return "中性"
    if close_price > open_price * 1.001:
        return "主动买入"
    if close_price < open_price * 0.999:
        return "主动卖出"
    return "中性"


def _meaning(side: str, hands: float | None, consecutive: bool, near_focus: bool) -> str:
    if side == "主动买入":
        if consecutive and near_focus:
            return "承接明显"
        if consecutive:
            return "资金持续表态"
        return "偏试盘"
    if side == "主动卖出":
        if consecutive and near_focus:
            return "抛压较明显"
        if consecutive:
            return "抛压释放"
        return "偏试压"
    if hands is not None and hands >= 5000:
        return "放量但方向不明"
    return "观察"


def _level(hands: float | None, consecutive: bool) -> str:
    if hands is None:
        return "观察"
    if hands >= 12000 or (consecutive and hands >= 8000):
        return "强提醒"
    if hands >= 5000 or consecutive:
        return "注意"
    return "观察"


def analyze_big_orders(
    bars_5m: list[dict[str, Any]],
    *,
    focus_price: float | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    events: list[BigOrderEvent] = []
    bars = [bar for bar in bars_5m if not trade_date or str(bar.get("time") or bar.get("date") or "").startswith(trade_date)]
    prev_side = ""
    prev_time = ""
    for bar in bars:
        time_text = _bar_time(bar)
        if not time_text:
            continue
        side = _direction(bar)
        if side == "中性":
            prev_side = ""
            prev_time = ""
            continue
        hands = _trade_hands(bar)
        amount_wan = _trade_amount_wan(bar)
        if hands is None or amount_wan is None:
            prev_side = ""
            prev_time = ""
            continue
        near_focus = False
        if focus_price is not None:
            close = to_float(bar.get("close"))
            if close is not None:
                diff_pct = abs(close - focus_price) / focus_price if focus_price else 0
                near_focus = diff_pct <= 0.015 or abs(close - focus_price) <= max(0.05, focus_price * 0.01)
        consecutive = bool(prev_side == side and prev_time and int(time_text.replace(":", "")) - int(prev_time.replace(":", "")) <= 120)
        events.append(
            BigOrderEvent(
                time=time_text,
                side=side,
                hands=hands,
                amount_wan=amount_wan,
                meaning=_meaning(side, hands, consecutive, near_focus),
                level=_level(hands, consecutive),
            )
        )
        prev_side = side
        prev_time = time_text

    if not events:
        return {
            "events": [],
            "summary": "暂无明显大单回溯。",
            "direction_summary": "暂无明显方向。",
            "total_hands": None,
            "total_amount_wan": None,
            "by_side": {"主动买入": None, "主动卖出": None},
        }

    total_hands = round(sum(event.hands or 0 for event in events), 2)
    total_amount_wan = round(sum(event.amount_wan or 0 for event in events), 2)
    buy_hands = round(sum(event.hands or 0 for event in events if event.side == "主动买入"), 2)
    sell_hands = round(sum(event.hands or 0 for event in events if event.side == "主动卖出"), 2)
    buy_amount = round(sum(event.amount_wan or 0 for event in events if event.side == "主动买入"), 2)
    sell_amount = round(sum(event.amount_wan or 0 for event in events if event.side == "主动卖出"), 2)
    direction_summary = "买方更强" if buy_hands > sell_hands else "卖方更强" if sell_hands > buy_hands else "买卖接近"
    summary = f"全天回溯到 {len(events)} 次大单事件，累计约 {total_hands:.0f} 手、{total_amount_wan:.0f} 万元，{direction_summary}。"
    return {
        "events": [event.__dict__ for event in events],
        "summary": summary,
        "direction_summary": direction_summary,
        "total_hands": total_hands,
        "total_amount_wan": total_amount_wan,
        "by_side": {
            "主动买入": {"hands": buy_hands, "amount_wan": buy_amount},
            "主动卖出": {"hands": sell_hands, "amount_wan": sell_amount},
        },
    }
