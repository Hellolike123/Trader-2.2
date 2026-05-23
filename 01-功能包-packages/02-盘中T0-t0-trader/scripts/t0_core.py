from __future__ import annotations

from typing import Any

from light_data import to_float

try:
    from order_book import analyze as order_book_analyze
except ImportError:
    order_book_analyze = None

try:
    from big_order import analyze_big_orders
except ImportError:
    analyze_big_orders = None


def pct_text(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"


def observation_valid(model: dict[str, Any]) -> bool:
    return bool(model.get("observation_valid", True))


def bar_num(bar: dict[str, Any], key: str) -> float | None:
    try:
        value = bar.get(key)
        return None if value is None else float(value)
    except Exception:
        return None


def segment_avg_volume(segment: list[dict[str, Any]]) -> float:
    volumes = [value for value in (bar_num(bar, "volume") for bar in segment) if value is not None]
    return sum(volumes) / len(volumes) if volumes else 0.0


def summarize_intraday_segment(name: str, segment: list[dict[str, Any]], prev_avg_volume: float | None = None) -> str:
    first_open = bar_num(segment[0], "open") if segment else None
    last_close = bar_num(segment[-1], "close") if segment else None
    if first_open is None or last_close is None:
        return f"{name}：数据不足，只作观察。"
    avg_volume = segment_avg_volume(segment)
    if prev_avg_volume is None or prev_avg_volume <= 0:
        volume_text = "量能正常"
    elif avg_volume > prev_avg_volume * 1.25:
        volume_text = "量能放大"
    elif avg_volume < prev_avg_volume * 0.75:
        volume_text = "量能收缩"
    else:
        volume_text = "量能平稳"
    if last_close > first_open * 1.002:
        move_text = "上行"
        read_text = "有承接，但仍要等触发"
    elif last_close < first_open * 0.998:
        move_text = "回落"
        read_text = "抛压仍在，不能急接"
    else:
        move_text = "横盘"
        read_text = "多空暂时均衡"
    return f"{name}：{first_open:.2f}→{last_close:.2f}，{move_text}，{volume_text}，{read_text}。"


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def review_lines(history: list[dict[str, Any]] | None) -> list[str]:
    if not history:
        return ["暂无关键事件。"]
    lines = []
    for item in history[-3:]:
        time_text = str(item.get("time") or "--:--")
        level = str(item.get("level") or "")
        text = str(item.get("text") or "提醒")
        event_price = item.get("price")
        price_text = f"，现价{float(event_price):.2f}元" if isinstance(event_price, (int, float)) else ""
        lines.append(f"{time_text} {level}｜{text}{price_text}。")
    return lines


def numeric_or_none(value: Any) -> float | None:
    try:
        return None if value is None else round(float(value), 2)
    except Exception:
        return None


def side_status(model: dict[str, Any]) -> str:
    status = str(model.get("status") or "")
    if status in ("已触发", "买 10%", "买 23%") and model.get("execution_price") is not None:
        return "可执行"
    if status == "触发过期":
        return "已错过"
    if status == "被阻断":
        return "被阻断"
    if status == "数据不足":
        return "数据不足"
    return "未触发"


def side_display(model: dict[str, Any]) -> str:
    """Return display status: show '买 10%' or '买 23%' instead of '已触发'."""
    raw = str(model.get("status") or "")
    if raw in ("买 10%", "买 23%"):
        return raw
    return side_status(model)


def observation_value(model: dict[str, Any], suffix: str) -> str:
    if not observation_valid(model):
        return "暂无有效观察价"
    return f"{price(model.get('observation_price'))}{suffix}"


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def build_t0_signals(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        build_side_signal(plan, "buy"),
        build_side_signal(plan, "sell"),
    ]


def build_side_signal(plan: dict[str, Any], side: str) -> dict[str, Any]:
    model = plan[side]
    side_state = side_status(model)
    signal_type = side_signal_type(side, side_state)
    action = side_action(side, side_state)
    trigger_price = side_trigger_price(model, side_state)
    invalid_price = model.get("invalid_price")
    direction = "bullish_lean" if side == "buy" else "neutral"
    trigger_text = "等观察价以下 5m 止跌确认" if side == "buy" else "等观察价附近冲高失败确认"
    invalid_text = (
        f"跌破 {price(invalid_price)} 后停止低吸" if side == "buy" else f"放量站上 {price(invalid_price)} 后取消高抛"
    )
    return {
        "contract": "trader_signal_v1",
        "source_skill": "t0-trader",
        "symbol": str(plan.get("symbol") or ""),
        "name": str(plan.get("name") or ""),
        "trade_date": str((plan.get("analysis_time") or "").split(" ")[0] or "--"),
        "analysis_time": str(plan.get("analysis_time") or "--"),
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": "high" if side_state == "可执行" else "medium",
        "data_status": normalize_t0_data_status(str(plan.get("data_status") or "partial")),
        "trigger": {
            "type": "completed_5m_confirm" if side_state == "可执行" else "watch_price",
            "price": numeric_or_none(trigger_price),
            "text": trigger_text,
        },
        "invalidation": {"type": "price_break", "price": numeric_or_none(invalid_price), "text": invalid_text},
        "position": t0_position(plan),
        "risk_flags": side_risk_flags(model),
        "summary": side_summary(model, side, trigger_price),
    }


def build_t0_event_signal(event: str, plan: dict[str, Any]) -> dict[str, Any]:
    side = "buy" if event.startswith("BUY") else "sell"
    signal = build_side_signal(plan, side)
    mapping = {
        "BUY_TRIGGERED": ("low_buy_triggered", "low_buy"),
        "SELL_TRIGGERED": ("high_sell_triggered", "high_sell"),
    }
    if event in mapping:
        signal["signal_type"], signal["action"] = mapping[event]
    return signal


def render_markdown(plan: dict[str, Any]) -> str:
    buy = plan["buy"]
    sell = plan["sell"]
    buy_state = str(plan.get("buy_display_status") or side_display(buy))
    sell_state = str(plan.get("sell_display_status") or side_display(sell))
    buy_obs = str(plan.get("buy_display_obs") or observation_value(buy, "以下"))
    sell_obs = str(plan.get("sell_display_obs") or observation_value(sell, "附近"))

    current_price = numeric_or_none(plan.get('current_price'))
    current_text = "无" if current_price is None else f"{current_price:.2f}"
    big_order = None
    if analyze_big_orders and plan.get("data"):
        focus_price = numeric_or_none(buy.get("observation_price")) or numeric_or_none(sell.get("observation_price"))
        bars = (plan.get("data") or {}).get("kline_5m") or []
        trade_date = str(plan.get("analysis_time") or "").split(" ", 1)[0] or None
        big_order = analyze_big_orders(bars, focus_price=focus_price, trade_date=trade_date)

    lines = [
        "🎯 T0 盯盘助理",
        f"{plan.get('name','')}（{plan.get('symbol','')}）｜现价 {current_text}（{pct_text(numeric_or_none(plan.get('current_change_pct')))}）",
        "",
        "🔍 扫描",
        "",
        f"当前：{'低吸' if buy_state == '可执行' else '高抛' if sell_state == '可执行' else '不动'}",
        f"买入：{buy_state}，观察{buy_obs}。",
        f"卖出：{sell_state}，观察{sell_obs}。",
        "",
        "🚩 关键价位",
        "",
        f"低吸观察：{buy_obs} | 高抛观察：{sell_obs}",
        f"止损：{price(numeric_or_none(buy.get('invalid_price')))}",
        "",
    ]
    # 盘口验证
    if order_book_analyze and plan.get("order_book"):
        ob = order_book_analyze(plan["order_book"])
        lines.append(f"📊 盘口验证")
        lines.append("")
        lines.append(ob["line"])
        lines.append("")

    if big_order and big_order.get("events"):
        lines.extend(["📋 关注区大单确认", ""])
        for event in big_order["events"][-4:]:
            hands_text = f"约 {event['hands']:.0f} 手" if event.get("hands") is not None else "手数不足"
            amount_text = f"金额约 {event['amount_wan']:.0f} 万" if event.get("amount_wan") is not None else "金额不足"
            lines.append(f"{event['time']}  {event['side']}，{hands_text}，{amount_text}，{event['meaning']}，{event['level']}。")
        lines.append(f"总结：{big_order.get('summary')}")
        lines.append("")

    lines.extend([
        "",
        "🕒 今日关键事件",
        "",
    ])
    lines.extend(review_lines(plan.get("history")))
    lines.extend(
        [
            "",
            "💰 仓位管控",
            "",
            f"当前：{plan.get('today_action', '等待')}",
            f"触发后：{plan.get('max_move', '不动')}",
            f"止损：{price(numeric_or_none(buy.get('invalid_price')))}",
            "",
            "👀 下一步只盯",
            "",
            f"买入：{buy_obs}是否5m止跌。",
            f"卖出：{sell_obs}是否冲高失败。",
            f"止损：跌破{price(numeric_or_none(buy.get('invalid_price')))}后不再低吸。",
        ]
    )
    return "\n".join(lines)


def side_signal_type(side: str, side_state: str) -> str:
    if side_state == "可执行":
        return "low_buy_triggered" if side == "buy" else "high_sell_triggered"
    if side_state == "已错过":
        return "trigger_expired"
    if side_state == "被阻断":
        return "blocked"
    return "low_buy_watch" if side == "buy" else "high_sell_watch"


def side_action(side: str, side_state: str) -> str:
    if side_state == "可执行":
        return "low_buy" if side == "buy" else "high_sell"
    if side_state == "被阻断":
        return "stop_low_buy" if side == "buy" else "stop_high_sell"
    return "observe"


def side_trigger_price(model: dict[str, Any], side_state: str) -> Any:
    if side_state == "可执行":
        return model.get("execution_price")
    return model.get("observation_price")


def side_summary(model: dict[str, Any], side: str, trigger_price: Any) -> str:
    raw_status = str(model.get("status") or "")
    side_state = side_status(model)
    if side == "buy":
        if side_state == "可执行":
            if raw_status == "买 10%":
                return f"买 10%，参考 {price(trigger_price)}，超过可接受价不追。"
            if raw_status == "买 23%":
                return f"买 23%，参考 {price(trigger_price)}，超过可接受价不追。"
            return f"低吸已触发，参考 {price(trigger_price)}，超过可接受价不追。"
        return f"低吸未触发，只盯 {price(trigger_price)} 以下是否 5m 止跌。"
    if side_state == "可执行":
        if raw_status == "买 10%":
            return f"卖 10%，参考 {price(trigger_price)}，低于可接受价不砸。"
        if raw_status == "买 23%":
            return f"卖 23%，参考 {price(trigger_price)}，低于可接受价不砸。"
        return f"高抛已触发，参考 {price(trigger_price)}，低于可接受价不砸。"
    return f"高抛未触发，只盯 {price(trigger_price)} 附近是否冲高失败。"


def side_risk_flags(model: dict[str, Any]) -> list[str]:
    flags = [str(item) for item in (model.get("blocked_reasons") or []) if str(item)]
    if side_status(model) == "数据不足":
        flags.append("intraday_data_insufficient")
    if side_status(model) == "已错过":
        flags.append("trigger_expired")
    return flags


def t0_position(plan: dict[str, Any]) -> dict[str, int]:
    max_move = str(plan.get("max_move") or "")
    if "20%-30%" in max_move:
        return {"max_total_pct": 30, "max_single_move_pct": 30}
    if "10%-20%" in max_move:
        return {"max_total_pct": 20, "max_single_move_pct": 20}
    return {"max_total_pct": 0, "max_single_move_pct": 0}


def normalize_t0_data_status(value: str) -> str:
    if value == "delayed":
        return "degraded"
    if value in {"complete", "full"}:
        return "full"
    if value in {"fresh", "insufficient", "non_trading", "partial", "degraded"}:
        return value
    return "partial"
